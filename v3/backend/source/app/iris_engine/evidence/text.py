"""Sequential, bounded UTF-8 decoding and private on-disk pages for large logs."""
import codecs
import contextlib
import gzip
import io
import os
import re
import time
import struct
from pathlib import Path

PAGE_CHARS = 12000
MAX_LOG_BYTES = 256 * 1024 * 1024
MAX_CACHE_BYTES = 512 * 1024 * 1024
INDEX = struct.Struct('<QI')


class BinaryLogError(ValueError):
    pass


def binary_blocks(raw):
    if raw.startswith(b'\x1f\x8b'):
        with gzip.GzipFile(fileobj=io.BytesIO(raw)) as stream:
            while chunk := stream.read(65536):
                yield chunk
    elif raw.startswith(b'\x28\xb5\x2f\xfd'):
        import zstandard
        context = zstandard.ZstdDecompressor(max_window_size=128 * 1024 * 1024)
        decoder = context.decompressobj()
        # Small compressed input blocks bound transient expansion; eof detects truncated frames.
        for offset in range(0, len(raw), 128):
            pending = raw[offset:offset + 128]
            while pending:
                output = decoder.decompress(pending)
                for start in range(0, len(output), 65536):
                    yield output[start:start + 65536]
                pending = decoder.unused_data if decoder.eof else b''
                if decoder.eof and (pending or offset + 128 < len(raw)):
                    decoder = context.decompressobj()
        if not decoder.eof:
            raise EOFError('Truncated zstd log')
    else:
        for offset in range(0, len(raw), 65536):
            yield raw[offset:offset + 65536]


def text_chunks(raw, state, *, limit=MAX_LOG_BYTES):
    """Consume the whole stream up to a byte limit; never silently sample it."""
    state.update(decoded_bytes=0, truncated=False)
    if len(raw) > 100 * 1024 * 1024:
        raise ValueError('Compressed log exceeds 100 MiB')
    decoder = codecs.getincrementaldecoder('utf-8')(errors='replace')
    first = True
    with contextlib.closing(binary_blocks(raw)) as blocks:
        for data in blocks:
            if first:
                first = False
                if b'\x00' in data[:4096] or data[:4] in (
                        b'\xd4\xc3\xb2\xa1', b'\xa1\xb2\xc3\xd4', b'\x4d\x3c\xb2\xa1',
                        b'\xa1\xb2\x3c\x4d', b'\x0a\x0d\x0d\x0a', b'PK\x03\x04'):
                    raise BinaryLogError('Binary log excluded from text analysis')
            remaining = limit - state['decoded_bytes']
            state['decoded_bytes'] += min(len(data), remaining)
            if len(data) > remaining:
                state['truncated'] = True
                yield decoder.decode(data[:remaining], final=True)
                return
            yield decoder.decode(data)
        tail = decoder.decode(b'', final=True)
        if tail:
            yield tail


def write_pages(folder, number, chunks, *, budget=MAX_CACHE_BYTES):
    """Store a bounded stream and a tiny fixed-size index; keep offsets in characters."""
    characters = pages = size = 0
    pending = ''
    truncated = False
    error = None
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, 'O_NOFOLLOW', 0)
    with contextlib.ExitStack() as stack, os.fdopen(os.open(folder / f'{number}.text', flags, 0o600), 'wb') as data, \
            os.fdopen(os.open(folder / f'{number}.idx', flags, 0o600), 'wb') as index:
        if hasattr(chunks, 'close'):
            stack.callback(chunks.close)
        def store(text):
            nonlocal characters, pages, size, truncated
            encoded = text.encode('utf-8')
            if size + len(encoded) > budget:
                truncated = True
                return False
            index.write(INDEX.pack(size, len(encoded)))
            data.write(encoded)
            characters += len(text)
            pages += 1
            size += len(encoded)
            return True
        try:
            for chunk in chunks:
                pending += chunk
                while len(pending) >= PAGE_CHARS:
                    if not store(pending[:PAGE_CHARS]):
                        return dict(characters=characters, pages=pages, size=size, truncated=True, error=None)
                    pending = pending[PAGE_CHARS:]
        except Exception as exc:
            error = type(exc).__name__
        if pending and not truncated:
            store(pending)
    return dict(characters=characters, pages=pages, size=size, truncated=truncated, error=error)


def read_page(folder, number, page):
    with (folder / f'{number}.idx').open('rb') as index:
        index.seek(page * INDEX.size)
        record = index.read(INDEX.size)
    if len(record) != INDEX.size:
        raise ValueError('Analysis cache is incomplete; start a new analysis')
    offset, length = INDEX.unpack(record)
    if length > PAGE_CHARS * 4:
        raise ValueError('Invalid analysis cache page')
    with (folder / f'{number}.text').open('rb') as stream:
        stream.seek(offset)
        raw = stream.read(length)
    if len(raw) != length:
        raise ValueError('Analysis cache is incomplete; start a new analysis')
    return raw.decode('utf-8')


def cache_folder(job_id, *, create=True):
    from app import app
    root = Path(app.config['DATASTORE_PATH']).parent / 'evidence-analysis'
    if create:
        root.mkdir(mode=0o700, parents=True, exist_ok=True)
    folder = root / str(int(job_id))
    if folder.is_symlink():
        raise ValueError('Invalid analysis cache directory')
    if create:
        folder.mkdir(mode=0o700, exist_ok=True)
        folder.touch()
    return folder


def clear_cache(job_id):
    folder = cache_folder(job_id, create=False)
    if not folder.exists():
        return
    for path in folder.iterdir():
        if path.stem.isdecimal() and path.suffix in ('.text', '.idx'):
            path.unlink(missing_ok=True)
    folder.rmdir()


class TextPages:
    def __init__(self, folder, manifest):
        self.folder, self.manifest = folder, manifest

    def __len__(self):
        return sum(item['pages'] for item in self.manifest)

    def __getitem__(self, position):
        for number, item in enumerate(self.manifest):
            if position < item['pages']:
                text = read_page(self.folder, number, position)
                offset = position * PAGE_CHARS
                url = item['source_url']
                if item.get('log_id'):
                    url += f'&offset={offset}#sandbox-log-{item["log_id"]}'
                return dict(source=item['source'], offset=offset, end_offset=offset + len(text),
                            text=text, source_url=url)
            position -= item['pages']
        raise IndexError(position)

    def coverage(self, progress):
        rows = []
        for item in self.manifest:
            done = min(max(0, progress), item['pages'])
            progress -= done
            rows.append({**item, 'processed_pages': done,
                         'processed_characters': min(done * PAGE_CHARS, item['characters']),
                         'complete': done == item['pages'] and not item['truncated'] and not item['error']
                                     and not item.get('excluded')})
        return rows


    def references(self, notes, limit=4):
        found = []
        seen = set()
        for label, raw in re.findall(r'(sandbox:\d+:(?:log:\d+|report))@(\d{1,12})', notes):
            offset = int(raw)
            if (label, offset) in seen:
                continue
            seen.add((label, offset))
            for number, item in enumerate(self.manifest):
                if item['source'] == label and 0 <= offset < item['characters']:
                    text = read_page(self.folder, number, offset // PAGE_CHARS)
                    text = text[offset % PAGE_CHARS:]
                    url = item['source_url']
                    if item.get('log_id'):
                        url += f'&offset={offset}#sandbox-log-{item["log_id"]}'
                    found.append(dict(source=label, offset=offset, end_offset=offset+len(text), text=text, source_url=url))
                    break
            if len(found) == limit:
                break
        return found


def prune_caches():
    from app import app
    root = Path(app.config['DATASTORE_PATH']).parent / 'evidence-analysis'
    if not root.is_dir():
        return
    removed = 0
    for folder in root.iterdir():
        if folder.name.isdecimal() and not folder.is_symlink() and folder.is_dir() and time.time() - folder.stat().st_mtime > 72 * 3600:
            try:
                clear_cache(int(folder.name))
                removed += 1
            except OSError:
                continue
            if removed >= 100:
                break
