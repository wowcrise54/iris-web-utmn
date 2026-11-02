"""Private immutable JSON objects for bounded alert-analysis checkpoints."""
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile

MAX_WORKSPACE_BYTES = 512 * 1024 * 1024


class Workspace:
    def __init__(self, folder):
        self.folder = Path(folder)
        if self.folder.is_symlink():
            raise ValueError('Invalid analysis cache directory')
        self.folder.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.normalized = None
        self.coverage = {}

    def put(self, value):
        # Node/manifest offsets refer to this exact insertion order; never sort on reload.
        raw = json.dumps(value, ensure_ascii=False, separators=(',', ':'),
                         allow_nan=False).encode('utf-8')
        key = hashlib.sha256(raw).hexdigest()
        target = self.folder / (key + '.json')
        if target.is_symlink():
            raise ValueError('Invalid analysis cache object')
        if target.exists():
            self.get(key)
            return key
        used = sum(p.stat().st_size for p in self.folder.iterdir() if p.is_file() and not p.is_symlink())
        if used + len(raw) > MAX_WORKSPACE_BYTES:
            raise ValueError('Analysis cache capacity reached; progress was saved.')
        with tempfile.NamedTemporaryFile(dir=self.folder, delete=False) as handle:
            temporary = Path(handle.name)
            os.chmod(temporary, 0o600)
            handle.write(raw)
        try:
            temporary.replace(target)
        finally:
            temporary.unlink(missing_ok=True)
        return key

    def get(self, key):
        if not isinstance(key, str) or not re.fullmatch(r'[a-f0-9]{64}', key):
            raise ValueError('Invalid analysis cache reference')
        path = self.folder / (key + '.json')
        if path.is_symlink() or not path.is_file():
            raise ValueError('Analysis snapshot is unavailable; start a new analysis.')
        if path.stat().st_size > MAX_WORKSPACE_BYTES:
            raise ValueError('Analysis cache object exceeds the safety limit')
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != key:
            raise ValueError('Analysis cache integrity check failed')
        return json.loads(raw)

    def source(self, identifier):
        if self.normalized is None:
            raise ValueError('Analysis source manifest is unavailable')
        if identifier == 'manifest':
            return json.dumps(self.normalized['manifest'], ensure_ascii=False,
                              separators=(',', ':'), allow_nan=False)
        for unit in self.normalized['units']:
            if unit['id'] == identifier:
                return unit['text']
        raise ValueError('Analysis source not found')

    def cached(self, key):
        if not isinstance(key, str) or not re.fullmatch(r'[a-f0-9]{64}', key):
            raise ValueError('Invalid cached response key')
        pointer = self.folder / ('response-' + key + '.json')
        if not pointer.exists():
            return None
        if pointer.is_symlink() or pointer.stat().st_size > 256:
            raise ValueError('Invalid cached response pointer')
        return self.get(json.loads(pointer.read_text(encoding='utf-8'))['object'])

    def cache(self, key, value):
        if not isinstance(key, str) or not re.fullmatch(r'[a-f0-9]{64}', key):
            raise ValueError('Invalid cached response key')
        identifier = self.put(value)
        pointer = self.folder / ('response-' + key + '.json')
        if pointer.is_symlink():
            raise ValueError('Invalid cached response pointer')
        raw = json.dumps({'object': identifier}).encode()
        with tempfile.NamedTemporaryFile(dir=self.folder, delete=False) as handle:
            temporary = Path(handle.name)
            os.chmod(temporary, 0o600)
            handle.write(raw)
        try:
            temporary.replace(pointer)
        finally:
            temporary.unlink(missing_ok=True)
        return identifier
