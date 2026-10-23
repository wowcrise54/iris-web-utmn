"""Case-scoped incident cards. Form cleanup never modifies source case objects."""

from datetime import datetime, timezone
from app.db import db
from app.models.cases import Cases
from app.models.incident_cards import IncidentCard
from app.models.authorization import User
from app.business.incident_card_catalog import FIELDS, normalize_preparers
from app.business.incident_cards import (
    build_snapshot,
    alert_defaults,
    merge_fields,
    validate_update,
    derive,
    CardConflictError,
)


def iso(value):
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def serialize_card(row):
    if not row:
        return None
    return dict(
        schema_version=row.schema_version,
        revision=row.revision,
        fields={
            k: v for k, v in normalize_preparers(row.fields).items() if k in FIELDS
        },
        selections={},
        author_id=row.author_id,
        author_name=row.author_name,
        created_at=iso(row.created_at),
        updated_at=iso(row.updated_at),
        missing_sources=[],
    )


def get_stored_incident_card(case_id):
    return serialize_card(IncidentCard.query.filter_by(case_id=case_id).first())


def source_context(case, stored):
    automatic = {
        "id": (str(case.case_id), "case.case_id"),
        "description": (case.description, "case.description"),
    }
    automatic.update(alert_defaults(case, getattr(case, "alerts", []) or []))
    return dict(meta=dict(case_id=case.case_id), automatic=automatic)


def get_incident_card(case_id):
    case = Cases.query.filter_by(case_id=case_id).first()
    if case is None:
        raise LookupError("Case not found")
    stored = get_stored_incident_card(case_id)
    return build_snapshot(source_context(case, stored), stored)


def save_incident_card(case_id, payload, actor_id, audit=None):
    payload = validate_update(payload)
    try:
        case = Cases.query.filter_by(case_id=case_id).with_for_update().first()
        if case is None:
            raise LookupError("Case not found")
        row = IncidentCard.query.filter_by(case_id=case_id).first()
        stored = serialize_card(row) or {}
        if payload["revision"] != stored.get("revision", 0):
            raise CardConflictError("Incident card changed; reload before saving")
        closing = payload["fields"].get("completed", {}).get("value") is True
        was_closed = stored.get("fields", {}).get("completed", {}).get("value") is True
        if (
            closing
            and not was_closed
            and not payload["fields"].get("incident_ended_at", {}).get("value")
        ):
            payload["fields"]["incident_ended_at"] = dict(
                value=datetime.now(timezone.utc).isoformat(), mode="manual"
            )
        fields = merge_fields(stored.get("fields", {}), payload["fields"])
        snapshot = build_snapshot(
            source_context(case, stored), dict(stored, fields=fields)
        )
        derive(snapshot["fields"])
        now = datetime.now(timezone.utc)
        if row is None:
            actor = User.query.filter_by(id=actor_id).first()
            row = IncidentCard(
                case_id=case_id,
                author_id=actor_id,
                author_name=(actor.name or actor.user) if actor else None,
                created_at=now,
            )
            db.session.add(row)
        row.schema_version = 1
        row.revision = stored.get("revision", 0) + 1
        row.fields = snapshot["fields"]
        row.selections = {}
        row.missing_sources = []
        row.updated_at = now
        if audit is not None:
            audit(case_id, row.revision)
        else:
            db.session.commit()
        return get_incident_card(case_id)
    except Exception:
        db.session.rollback()
        raise
