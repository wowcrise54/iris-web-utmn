"""Lossless content-addressed alert sources and bounded evidence packets.

The encoding is deliberately typed: user objects containing ``$ref`` cannot be
mistaken for references. Objects preserve key order; only byte-identical encoded
subtrees are interned. No field names (including vendor-private ones) are filtered.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False)


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def _pointer(path: str, part: Any) -> str:
    return path + '/' + str(part).replace('~', '~0').replace('/', '~1')


def _identity(value: Any) -> str | None:
    if isinstance(value, dict):
        for key in ('uuid', 'event_uuid', 'event_id'):
            item = value.get(key)
            if isinstance(item, (str, int)) and not isinstance(item, bool):
                return str(item)
    return None


def parse_source_json(text: str) -> Any:
    def unique_object(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('Duplicate JSON keys require raw-text analysis')
            result[key] = value
        return result
    return json.loads(text, object_pairs_hook=unique_object)


def _coverage(value: Any) -> dict:
    # A textual source remains an exact string, but its collection declaration
    # can still describe source completeness.
    if isinstance(value, dict) and 'alert_source_content' in value:
        value = value['alert_source_content']
    parsed = True
    if isinstance(value, str):
        try:
            value = parse_source_json(value)
        except (ValueError, TypeError, RecursionError):
            value = None
            parsed = False
    parsed = parsed and isinstance(value, dict)
    value = value if isinstance(value, dict) else {}
    collection = value.get('event_collection')
    collection = collection if isinstance(collection, dict) else {}
    events = value.get('events', [])
    if isinstance(events, dict):
        events = list(events.values())
    if not isinstance(events, list):
        events = []
    identities = {_identity(event) or 'anonymous:' + _sha(_json(event)) for event in events}
    missing = collection.get('missing_uuids', [])
    missing = list(dict.fromkeys(str(item) for item in missing)) if isinstance(missing, list) else []
    return {'available_events': len(identities), 'missing_events': missing,
            'source_complete': collection.get('complete') is True and not missing and not collection.get('errors'),
            'normalization_complete': parsed}


def normalize_source(value: Any) -> dict:
    """Factor JSON-compatible input without changing or excluding any content.

    ``units[].text`` is a typed JSON node. ``ref`` points to another unit;
    ``object`` is an ordered sequence of [key, node] pairs, ``array`` holds nodes,
    and ``value`` is a literal scalar. Strings retain their original characters.
    ``manifest`` holds the root node and occurrence/provenance metadata.
    """
    source_text = _json(value)  # Also rejects unsupported/non-finite inputs.
    units: dict[str, dict] = {}

    def visit(item, path, inherited):
        identity = _identity(item)
        event_ids = set(inherited)
        if identity:
            event_ids.add(identity)
        if isinstance(item, dict):
            node = {'object': [[key, visit(child, _pointer(path, key), event_ids)]
                               for key, child in item.items()]}
        elif isinstance(item, list):
            node = {'array': [visit(child, _pointer(path, i), event_ids)
                              for i, child in enumerate(item)]}
        else:
            node = {'value': item}
            if not isinstance(item, str) or len(item) < 256:
                return node
        text = _json(node)
        digest = _sha(text)
        unit_id = 'u:' + digest
        unit = units.setdefault(unit_id, {'id': unit_id, 'sha256': digest, 'text': text,
                                         'paths': [], 'event_ids': [], 'occurrences': 0})
        unit['paths'].append(path)
        unit['occurrences'] += 1
        unit['event_ids'] = sorted(set(unit['event_ids']) | event_ids)
        return {'ref': unit_id}

    root = visit(value, '', set())
    # Scalar roots need a unit too, so an empty or short string is still evidence.
    if 'ref' not in root:
        text = _json(root)
        digest = _sha(text)
        unit_id = 'u:' + digest
        units[unit_id] = {'id': unit_id, 'sha256': digest, 'text': text,
                          'paths': [''], 'event_ids': [], 'occurrences': 1}
        root = {'ref': unit_id}
    coverage = _coverage(value)
    manifest = {'encoding': 'iris-source-nodes-v1', 'root': root,
                'coverage': coverage,
                # Paths are derivable from the typed graph; repeating every
                # occurrence's full JSON pointer can dwarf the original source.
                'units': [{key: unit[key] for key in ('id', 'event_ids', 'occurrences')}
                          for unit in units.values()]}
    return {'version': 1, 'source_sha256': _sha(source_text), 'units': list(units.values()),
            'coverage': coverage, 'manifest': manifest}


def reconstruct_source(normalized: dict) -> Any:
    """Reconstruct the exact JSON value (including original string input)."""
    nodes = {unit['id']: json.loads(unit['text']) for unit in normalized['units']}

    def expand(node):
        if 'ref' in node:
            return expand(nodes[node['ref']])
        if 'object' in node:
            return {key: expand(child) for key, child in node['object']}
        if 'array' in node:
            return [expand(child) for child in node['array']]
        return node['value']

    return expand(normalized['manifest']['root'])


def manifest_text(normalized: dict) -> str:
    """Canonical packet source for structural references and multiplicities."""
    return _json(normalized['manifest'])


def pack_units(normalized: dict, max_chars: int = 6000, overlap: int = 128) -> list[dict]:
    """Cover every unit and the complete manifest with exact character offsets.

    Metadata is outside ``text`` so it never changes source offsets. All packets
    obey ``max_chars``. Small units share packets; a long unit's continuation
    repeats ``overlap`` source characters, with explicit reference offsets.
    """
    if max_chars <= 0 or overlap < 0 or overlap >= max_chars:
        raise ValueError('Require max_chars > overlap >= 0')
    sources = [{'id': 'manifest', 'text': manifest_text(normalized), 'event_ids': []},
               *normalized['units']]
    packets = []
    fragments, references, event_ids = [], [], set()
    size = 0

    def flush():
        nonlocal fragments, references, event_ids, size
        if not references:
            return
        packets.append({'id': f'packet:{len(packets)}', 'text': '\n'.join(fragments),
                        'source_ids': list(dict.fromkeys(ref['source_id'] for ref in references)),
                        'references': references, 'event_ids': sorted(event_ids)})
        fragments, references, event_ids, size = [], [], set(), 0

    for source in sources:
        text = source['text']
        start = 0
        while start < len(text):
            separator = 1 if fragments else 0
            room = max_chars - size - separator
            # Avoid creating an overlap-only fragment at a nearly full boundary.
            if room <= overlap or (start == 0 and len(text) <= max_chars and len(text) > room):
                flush()
                room, separator = max_chars, 0
            end = min(start + room, len(text))
            fragments.append(text[start:end])
            references.append({'source_id': source['id'], 'offset': start, 'end_offset': end})
            event_ids.update(source['event_ids'])
            size += end - start + separator
            if end == len(text):
                break
            flush()
            start = end - overlap
    flush()
    return packets
