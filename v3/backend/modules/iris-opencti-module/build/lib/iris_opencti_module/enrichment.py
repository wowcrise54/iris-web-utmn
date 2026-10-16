"""Enrichment orchestration shared by automatic and manual DIM hooks."""
import hashlib
import json
from copy import deepcopy
from datetime import datetime, timedelta, timezone

from .client import OpenCTIError, normalize_ioc, timestamp


CACHEABLE = {'matched', 'no_match', 'partial'}


def enrich_iocs(iocs, store, client, force=False, ttl=21600):
    started = timestamp()
    since = started if force else (datetime.now(timezone.utc) - timedelta(seconds=ttl)).isoformat()
    batch = {}
    for ioc in iocs:
        if not store.active():
            break
        kind = ioc.ioc_type.type_name if ioc.ioc_type else ''
        base = {'schema_version': 1, 'checked_at': timestamp(), 'source': client.url,
                'input': {'type': kind, 'value': ioc.ioc_value}}
        try:
            typed = normalize_ioc(kind, ioc.ioc_value)
        except ValueError:
            store.save(ioc, {**base, 'status': 'unsupported', 'observables': [], 'indicators': [], 'relationships': []})
            continue
        key = hashlib.sha256(json.dumps([client.url, client.token, typed, store.scope(ioc)], sort_keys=True).encode()).hexdigest()
        try:
            with store.lock(key):
                if not store.active():
                    break
                result = batch.get(key)
                if result is None:
                    result = store.cached(key, since)
                    if result and result.get('status') not in CACHEABLE:
                        result = None
                if result is None:
                    try:
                        result = {**client.lookup(kind, ioc.ioc_value), 'checked_at': timestamp()}
                    except OpenCTIError as error:
                        result = {'status': error.status, 'checked_at': timestamp(), 'observables': [], 'indicators': [], 'relationships': []}
                    except (ValueError, TypeError, KeyError, AttributeError):
                        result = {'status': 'invalid_response', 'checked_at': timestamp(), 'observables': [], 'indicators': [], 'relationships': []}
                    result.update(cache_key=key, source=client.url, schema_version=1)
                    batch[key] = result
                if store.active():
                    store.save(ioc, {**deepcopy(result), 'input': base['input']})
        except OpenCTIError as error:
            if store.active():
                store.save(ioc, {**base, 'status': error.status, 'observables': [], 'indicators': [], 'relationships': []})
