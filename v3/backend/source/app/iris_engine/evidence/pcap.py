"""Bounded metadata-only offline capture analysis; packet payloads never leave TShark."""
import gzip
import hashlib
import io
import ipaddress
import math
import logging
import subprocess
import sys
import tempfile
from pathlib import Path

MAX_INPUT = 100 * 1024**2
MAX_OUTPUT = 16 * 1024**2
MAGICS = (b'\xd4\xc3\xb2\xa1', b'\xa1\xb2\xc3\xd4', b'\x4d\x3c\xb2\xa1', b'\xa1\xb2\x3c\x4d', b'\x0a\x0d\x0d\x0a')


def capture_bytes(raw):
    if len(raw) > MAX_INPUT:
        raise ValueError('Capture exceeds 100 MiB limit')
    if raw.startswith(b'\x1f\x8b'):
        with gzip.GzipFile(fileobj=io.BytesIO(raw)) as source:
            raw = source.read(MAX_INPUT + 1)
    elif raw.startswith(b'\x28\xb5\x2f\xfd'):
        import zstandard
        with zstandard.ZstdDecompressor().stream_reader(io.BytesIO(raw)) as source:
            raw = source.read(MAX_INPUT + 1)
    if len(raw) > MAX_INPUT:
        raise ValueError('Expanded capture exceeds 100 MiB limit')
    if raw[:4] not in MAGICS:
        raise ValueError('Only PCAP and PCAPNG are supported; video and other binaries are excluded')
    return raw


def parse_rows(lines):
    nodes, flows, indicators = {}, {}, {}
    count, total, skipped = 0, 0, 0
    first = last = None
    omitted = 0
    for line in lines:
        cells = line.rstrip('\r\n').split('\t')
        if len(cells) != 15:
            continue
        frame, timestamp, size, ipv4s, ipv6s, ipv4d, ipv6d, ts, us, td, ud, proto, dns, sni, host = cells
        try:
            frame, stamp, size = int(frame), float(timestamp), int(size)
            if not math.isfinite(stamp) or size < 0:
                raise ValueError('Invalid packet metadata')
            count += 1
            total += size
            first = stamp if first is None else min(first, stamp)
            last = stamp if last is None else max(last, stamp)
            src, dst = str(ipaddress.ip_address(ipv4s or ipv6s)), str(ipaddress.ip_address(ipv4d or ipv6d))
        except (ValueError, TypeError):
            skipped += 1
            continue
        for ip in (src, dst):
            if ip not in nodes and len(nodes) < 100:
                nodes[ip] = {'id': ip, 'label': ip, 'group': 'host'}
        # Fixed metadata only; no HTTP URI, headers, credentials, raw bytes or objects.
        for value in (dns, sni, host):
            name = value.lower().strip().rstrip('.')[:253]
            if name and all(c.isalnum() or c in '.-_' for c in name) and len(indicators) < 100:
                indicators.setdefault(name, {'value': name, 'frame': frame, 'timestamp': stamp})
        key = (src, dst, (ts or us)[:5], (td or ud)[:5], proto[:24])
        if key not in flows:
            if len(flows) >= 150 or src not in nodes or dst not in nodes:
                omitted += 1
                continue
            flows[key] = {'from': src, 'to': dst, 'port': (td or ud)[:5], 'source_port': (ts or us)[:5], 'protocol': proto[:24],
                          'packets': 0, 'bytes': 0, 'first_frame': frame, 'first_seen': stamp, 'last_seen': stamp}
        flow = flows[key]
        flow['packets'] += 1
        flow['bytes'] += size
        flow['last_seen'] = max(flow['last_seen'], stamp)
    edges = [dict(value, id=str(index), label=f"{value['protocol']}:{value['port']}")
             for index, value in enumerate(flows.values())]
    return {'packets': count, 'bytes': total, 'first_seen': first, 'last_seen': last,
            'nodes': list(nodes.values()), 'edges': edges, 'indicators': list(indicators.values()),
            'non_ip_or_invalid_records': skipped, 'omitted_packets_from_graph': omitted, 'partial': bool(omitted or count >= 100000),
            'limits': {'input_bytes': MAX_INPUT, 'packets': 100000, 'nodes': 100, 'edges': 150, 'seconds': 120}}


def analyze_capture(raw):
    if sys.platform != 'linux':
        raise ValueError('Offline PCAP isolation requires Linux')
    raw = capture_bytes(raw)
    with tempfile.TemporaryDirectory(prefix='iris-pcap-') as directory:
        folder = Path(directory)
        folder.chmod(0o755)
        capture = folder / 'capture.pcap'
        capture.write_bytes(raw)
        capture.chmod(0o444)
        with (folder / 'metadata.tsv').open('w+b') as output, (folder / 'error.log').open('w+b') as errors:
            try:
                child = subprocess.run([sys.executable, str(Path(__file__).with_name('pcap_child.py')), str(capture)],
                                       stdout=output, stderr=errors, stdin=subprocess.DEVNULL, timeout=120, close_fds=True, cwd=directory,
                                       env={'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8'})
            except subprocess.TimeoutExpired:
                raise ValueError('PCAP analysis exceeded 120 seconds; no complete result is available') from None
            output.seek(0)
            data = output.read(MAX_OUTPUT)
            output_limited = len(data) >= MAX_OUTPUT
            if child.returncode != 0 and not output_limited:
                logging.getLogger('iris.evidence.pcap').warning('pcap_child_failed returncode=%s', child.returncode)
                raise ValueError('Offline PCAP analyzer failed or isolation is unavailable; see worker diagnostics')
        result = parse_rows(data.decode('utf-8', errors='replace').splitlines())
        result['sha256'] = hashlib.sha256(raw).hexdigest()
        result['partial'] |= output_limited
        if output_limited:
            result['omissions'] = ['Metadata output size limit reached']
        return result
