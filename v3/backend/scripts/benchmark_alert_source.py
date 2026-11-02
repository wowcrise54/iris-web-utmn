"""Offline source-factoring benchmark. Never sends evidence to a provider."""
import argparse
import importlib.util
import json
from pathlib import Path
import sys
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path)
    args = parser.parse_args()
    path = Path(__file__).parents[1] / 'source/app/iris_engine/evidence/alert_source.py'
    spec = importlib.util.spec_from_file_location('alert_source_benchmark', path)
    source = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = source
    spec.loader.exec_module(source)
    raw = args.input.read_bytes()
    value = json.loads(raw.decode('utf-8-sig'))
    started = time.monotonic()
    normalized = source.normalize_source(value)
    elapsed = (time.monotonic() - started) * 1000
    roundtrip = source.reconstruct_source(normalized) == value
    canonical_bytes = len(json.dumps(value, ensure_ascii=False, separators=(',', ':')).encode())
    content_bytes = sum(len(u['text'].encode()) for u in normalized['units'])
    content_bytes += len(source.manifest_text(normalized).encode())
    print(json.dumps({
        'offline_only': True, 'model_requests': 0, 'original_file_bytes': len(raw),
        'canonical_source_bytes': canonical_bytes, 'unique_analysis_content_bytes': content_bytes,
        'content_reduction_ratio': round(canonical_bytes / max(1, content_bytes), 3),
        'normalization_ms': round(elapsed, 2), 'lossless_roundtrip': roundtrip,
        'unique_units': len(normalized['units']),
        'initial_packets_16000_chars': len(source.pack_units(normalized, max_chars=16000)),
        'available_events': normalized['coverage']['available_events'],
        'missing_events': len(normalized['coverage']['missing_events']),
        'source_complete': normalized['coverage']['source_complete'],
        'note': 'Content reduction only; token totals and inference latency require a real provider benchmark.',
    }, indent=2))
    return 0 if roundtrip else 1


if __name__ == '__main__':
    raise SystemExit(main())
