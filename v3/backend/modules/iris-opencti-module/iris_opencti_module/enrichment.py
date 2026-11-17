"""Enrichment orchestration shared by automatic and manual DIM hooks."""
import hashlib
import json
import logging
from collections import Counter
from time import monotonic
from copy import deepcopy
from datetime import datetime, timedelta, timezone

from .client import OpenCTIError, normalize_ioc, timestamp


CACHEABLE = {'matched', 'no_match', 'partial'}


def enrich_iocs(iocs, store, client, force=False, ttl=21600):
    log = logging.getLogger(__name__)
    clock = monotonic()
    counts = Counter()
    log.info('OpenCTI batch_started total=%d force=%s', len(iocs), force)
    started = timestamp()
    since = started if force else (datetime.now(timezone.utc) - timedelta(seconds=ttl)).isoformat()
    batch = {}
    for ioc in iocs:
        if not store.active():
            log.info('OpenCTI batch_stopped reason=disabled')
            break
        kind = ioc.ioc_type.type_name if ioc.ioc_type else ''
        base = {'schema_version': 1, 'checked_at': timestamp(), 'source': client.url,
                'input': {'type': kind, 'value': ioc.ioc_value}}
        item_clock = monotonic()
        def save(result):
            try:
                store.save(ioc, result)
            except Exception:
                log.error('OpenCTI save_failed ioc_id=%s', ioc.ioc_id)
                raise
            counts[result['status']] += 1
            level = logging.INFO if result['status'] in CACHEABLE | {'unsupported'} else logging.WARNING
            if result['status'] == 'partial':
                level = logging.WARNING
            log.log(level, 'OpenCTI ioc_completed ioc_id=%s status=%s observables=%d indicators=%d relationships=%d duration_ms=%.1f',
                    ioc.ioc_id, result['status'], len(result.get('observables', [])),
                    len(result.get('indicators', [])), len(result.get('relationships', [])),
                    (monotonic() - item_clock) * 1000)
        try:
            typed = normalize_ioc(kind, ioc.ioc_value)
        except ValueError:
            save({**base, 'status': 'unsupported', 'observables': [], 'indicators': [], 'relationships': []})
            continue
        key = hashlib.sha256(json.dumps([client.url, client.token, typed, store.scope(ioc)], sort_keys=True).encode()).hexdigest()
        try:
            with store.lock(key):
                if not store.active():
                    log.info('OpenCTI batch_stopped reason=disabled ioc_id=%s', ioc.ioc_id)
                    break
                result = batch.get(key)
                cache = 'batch' if result is not None else 'miss'
                if result is None:
                    result = store.cached(key, since)
                    if result and result.get('status') not in CACHEABLE:
                        result = None
                if result is not None and cache != 'batch':
                    cache = 'persistent'
                log.debug('OpenCTI cache_checked ioc_id=%s cache=%s', ioc.ioc_id, cache)
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
                    save({**deepcopy(result), 'input': base['input']})
                else:
                    log.info('OpenCTI result_discarded ioc_id=%s reason=disabled', ioc.ioc_id)
        except OpenCTIError as error:
            if store.active():
                save({**base, 'status': error.status, 'observables': [], 'indicators': [], 'relationships': []})

    log.info('OpenCTI batch_completed total=%d saved=%d statuses=%s duration_ms=%.1f',
             len(iocs), sum(counts.values()), dict(counts), (monotonic() - clock) * 1000)
