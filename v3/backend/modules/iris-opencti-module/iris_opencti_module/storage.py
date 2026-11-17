"""IRIS persistence adapter; no schema migration and no hooks fired by writes."""
import hashlib
import json
from contextlib import contextmanager
from time import monotonic, sleep

from sqlalchemy import cast, func, text, update
from sqlalchemy.dialects.postgresql import JSONB

from app.db import db
from app.models.alerts import Alert
from app.models.cases import Cases
from app.models.iocs import Ioc
from app.models.models import IrisModule, IrisModuleHook

from .client import OpenCTIError, timestamp
from .enrichment import CACHEABLE


PACKAGE = 'iris_opencti_module'


def module_row(module_id=None):
    query = IrisModule.query.filter(IrisModule.id == module_id) if module_id is not None else IrisModule.query.filter(IrisModule.module_name == PACKAGE)
    return query.populate_existing().first()


def configuration(row):
    return {entry['param_name']: entry.get('value', entry.get('default')) for entry in row.module_config or []}


def remove_hooks(module_id):
    IrisModuleHook.query.filter(IrisModuleHook.module_id == module_id).delete(synchronize_session=False)
    db.session.commit()


def case_iocs(case):
    own = Ioc.query.filter(Ioc.case_id == case.case_id).populate_existing().all()
    linked = [ioc for alert in case.alerts for ioc in alert.iocs]
    return list({ioc.ioc_id: ioc for ioc in own + linked}.values())


def collect_targets(data):
    iocs, cases = {}, set()
    for obj in data:
        if isinstance(obj, Ioc):
            targets = [obj]
        elif isinstance(obj, Alert):
            targets = list(obj.iocs)
            cases.update(case.case_id for case in obj.cases)
        elif isinstance(obj, Cases):
            targets = case_iocs(obj)
            cases.add(obj.case_id)
        else:
            continue
        for ioc in targets:
            iocs[ioc.ioc_id] = ioc
            if ioc.case_id is not None:
                cases.add(ioc.case_id)
            cases.update(case.case_id for alert in ioc.alerts for case in alert.cases)
    return list(iocs.values()), cases


class IrisStore:
    def __init__(self, config):
        self.config = config

    def active(self):
        row = module_row()
        return bool(row and row.is_active and configuration(row) == self.config)

    def scope(self, ioc):
        customers = {alert.alert_customer_id for alert in ioc.alerts}
        if ioc.case is not None:
            customers.add(ioc.case.client_id)
        # Orphan IOCs are not used as a shared cache across customers.
        return sorted(customers) or ['orphan', ioc.ioc_id]

    @contextmanager
    def lock(self, key):
        lock_id = int.from_bytes(hashlib.sha256(key.encode()).digest()[:8], 'big', signed=True)
        with db.engine.connect() as connection:
            acquired = False
            deadline = monotonic() + 30
            try:
                while not acquired:
                    acquired = connection.execute(text('SELECT pg_try_advisory_lock(:key)'), {'key': lock_id}).scalar()
                    if not acquired:
                        if monotonic() >= deadline:
                            raise OpenCTIError('busy')
                        sleep(0.1)
                yield
            finally:
                if acquired:
                    connection.execute(text('SELECT pg_advisory_unlock(:key)'), {'key': lock_id})

    def cached(self, key, since):
        rows = Ioc.query.filter(Ioc.ioc_enrichment['opencti']['cache_key'].astext == key).populate_existing().all()
        for row in rows:
            result = (row.ioc_enrichment or {}).get('opencti', {})
            if not isinstance(result, dict):
                continue
            if result.get('status') in CACHEABLE and result.get('checked_at', '') > since:
                return result
        return None

    def save(self, ioc, result):
        # Atomic provider-only update preserves other modules, including concurrent writes.
        payload = func.jsonb_set(func.coalesce(Ioc.ioc_enrichment, cast({}, JSONB)), '{opencti}', cast(result, JSONB), True)
        db.session.execute(update(Ioc).where(
            Ioc.ioc_id == ioc.ioc_id, Ioc.ioc_value == result['input']['value'],
            Ioc.ioc_type.has(type_name=result['input']['type'])
        ).values(ioc_enrichment=payload).execution_options(synchronize_session=False))
        db.session.commit()
        db.session.expire(ioc)

    def summarize(self, identifiers):
        for case_id in sorted(identifiers):
            if not self.active():
                return
            case = Cases.query.filter(Cases.case_id == case_id).populate_existing().with_for_update().first()
            if case is None:
                continue
            counts = {}
            items = []
            for ioc in case_iocs(case):
                result = (ioc.ioc_enrichment or {}).get('opencti', {})
                if not isinstance(result, dict):
                    result = {}
                expected = {'type': ioc.ioc_type.type_name if ioc.ioc_type else '', 'value': ioc.ioc_value}
                state = result.get('status', 'not_checked') if result.get('input') == expected else 'not_checked'
                counts[state] = counts.get(state, 0) + 1
                items.append({'ioc_id': ioc.ioc_id, 'value': ioc.ioc_value, 'status': state,
                              'checked_at': result.get('checked_at'),
                              'alert_ids': [a.alert_id for a in ioc.alerts if case in a.cases]})
            summary = {'schema_version': 1, 'updated_at': timestamp(), 'total': len(items), 'counts': counts, 'iocs': items}
            attributes = dict(case.custom_attributes or {})
            attributes['__iris_opencti'] = {'type': 'textarea', 'value': json.dumps(summary, ensure_ascii=False)}
            case.custom_attributes = attributes
            db.session.commit()
