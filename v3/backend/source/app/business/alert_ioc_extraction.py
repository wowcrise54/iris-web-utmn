"""Attach extracted IOC rows in the caller's alert transaction."""
from iris_maxpatrol_module.iocs import STATE_KEY, pending_iocs


def extract_alert_iocs(alert, previous_content=None):
    if isinstance(previous_content, dict) and STATE_KEY in previous_content and isinstance(alert.alert_source_content, dict):
        alert.alert_source_content = {**alert.alert_source_content, STATE_KEY: previous_content[STATE_KEY]}
    pending, seen = pending_iocs(alert)
    if not seen:
        return
    if pending:
        from app.db import db
        from app.models.iocs import Ioc, Tlp
        from app.models.models import IocType

        types = {row.type_name: row.type_id for row in db.session.query(IocType).filter(
            IocType.type_name.in_({key[0] for key in pending})).all()}
        pending, seen = pending_iocs(alert, {identifier: name for name, identifier in types.items()})
        tlp = db.session.query(Tlp).filter_by(tlp_name='amber').one()
        for (kind, value), fields in pending.items():
            if kind not in types:
                # Retry after the catalogue is repaired instead of losing candidates.
                seen.remove([kind, value])
                continue
            alert.iocs.append(Ioc(ioc_value=value, ioc_type_id=types[kind],
                ioc_tlp_id=tlp.tlp_id, ioc_description='Automatically extracted from MaxPatrol: ' + ', '.join(fields)))
    alert.alert_source_content = {**alert.alert_source_content, STATE_KEY: seen}
