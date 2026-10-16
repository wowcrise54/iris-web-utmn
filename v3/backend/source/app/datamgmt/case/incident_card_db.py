"""Incident-card persistence and case-scoped source queries."""

from copy import deepcopy
from datetime import datetime, timezone
from app.db import db
from app.models.cases import Cases
from app.models.incident_cards import IncidentCard
from app.models.assets import CaseAssets
from app.models.alerts import Alert, AlertCaseAssociation
from app.models.iocs import Ioc
from app.models.models import CaseTasks, DataStoreFile
from app.models.authorization import User
from app.business.incident_cards import (
    build_snapshot,
    merge_fields,
    unresolved_sources,
    validate_update,
    derive,
    CardValidationError,
    CardConflictError,
    SELECTIONS,
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
        fields=deepcopy(row.fields),
        selections=deepcopy(row.selections),
        author_id=row.author_id,
        author_name=row.author_name,
        created_at=iso(row.created_at),
        updated_at=iso(row.updated_at),
        missing_sources=deepcopy(row.missing_sources or []),
    )


def get_stored_incident_card(case_id):
    return serialize_card(IncidentCard.query.filter_by(case_id=case_id).first())


def source_context(case, stored):
    selected = deepcopy(SELECTIONS)
    selected.update((stored or {}).get("selections", {}))
    alerts = (
        Alert.query.join(
            AlertCaseAssociation, AlertCaseAssociation.alert_id == Alert.alert_id
        )
        .filter(
            AlertCaseAssociation.case_id == case.case_id,
            Alert.alert_customer_id == case.client_id,
        )
        .all()
    )
    assets = CaseAssets.query.filter_by(case_id=case.case_id).all()
    iocs = Ioc.query.filter_by(case_id=case.case_id).all()
    files = DataStoreFile.query.filter_by(file_case_id=case.case_id).all()
    tasks = CaseTasks.query.filter_by(task_case_id=case.case_id).all()
    collections = {
        "alerts": {x.alert_id: x for x in alerts},
        "assets": {x.asset_id: x for x in assets},
        "iocs": {x.ioc_id: x for x in iocs},
        "files": {x.file_id: x for x in files},
        "tasks": {x.id: x for x in tasks},
    }
    sources = {
        key: [
            {
                "id": identifier,
                "label": str(
                    getattr(
                        x,
                        {
                            "alerts": "alert_title",
                            "assets": "asset_name",
                            "iocs": "ioc_value",
                            "files": "file_original_name",
                            "tasks": "task_title",
                        }[key],
                    )
                    or identifier
                ),
            }
            for identifier, x in rows.items()
        ]
        for key, rows in collections.items()
    }
    automatic = {
        "id": (str(case.case_id), "case.case_id"),
        "title": (case.name, "case.name"),
        "description": (case.description, "case.description"),
        "organization": (case.client.name if case.client else None, "case.client"),
        "criticality": (
            case.severity.severity_name if case.severity else None,
            "case.severity",
        ),
    }
    missing_sources = set((stored or {}).get("missing_sources", []))
    alert = collections["alerts"].get(selected["alert_id"])
    if alert and "alert_id" not in missing_sources:
        automatic.update(
            detection_source=(alert.alert_source, "alert:" + str(alert.alert_id)),
            external_id=(alert.alert_source_ref, "alert:" + str(alert.alert_id)),
            incident_at=(
                iso(alert.alert_source_event_time),
                "alert:" + str(alert.alert_id),
            ),
        )
    for key, selection in [
        ("affected_assets", "affected_asset_ids"),
        ("attack_source", "source_asset_id"),
        ("attack_target", "target_asset_id"),
        ("files", "file_ids"),
        ("hashes", "ioc_ids"),
        ("performed_actions", "performed_task_ids"),
        ("planned_actions", "planned_task_ids"),
    ]:
        if selection in missing_sources:
            continue
        group = {
            "affected_assets": "assets",
            "attack_source": "assets",
            "attack_target": "assets",
            "files": "files",
            "hashes": "iocs",
            "performed_actions": "tasks",
            "planned_actions": "tasks",
        }[key]
        ids = (
            selected[selection]
            if isinstance(selected[selection], list)
            else [selected[selection]]
            if selected[selection]
            else []
        )
        rows = [collections[group].get(identifier) for identifier in ids]
        if not ids or any((x is None for x in rows)):
            continue
        if group == "assets":
            text = "\n".join(
                (
                    " | ".join(
                        (
                            str(v)
                            for v in [x.asset_name, x.asset_ip, x.asset_domain]
                            if v
                        )
                    )
                    for x in rows
                )
            )
        elif group == "files":
            text = "\n".join(
                (
                    x.file_original_name
                    + (" | SHA256 " + x.file_sha256 if x.file_sha256 else "")
                    for x in rows
                )
            )
        elif group == "iocs":
            if any(
                (
                    not x.ioc_type
                    or not any(
                        (
                            k in x.ioc_type.type_name.lower()
                            for k in ("hash", "md5", "sha1", "sha256", "sha512")
                        )
                    )
                    for x in rows
                )
            ):
                continue
            text = "\n".join((x.ioc_value for x in rows))
        else:
            performed = key == "performed_actions"
            if any(
                (
                    (x.status is not None and x.status.status_name.lower() == "done")
                    != performed
                    or (
                        not performed
                        and x.status
                        and (x.status.status_name.lower() == "canceled")
                    )
                    for x in rows
                )
            ):
                continue
            text = "\n".join(
                (
                    x.task_title
                    + (": " + x.task_description if x.task_description else "")
                    for x in rows
                )
            )
        automatic[key] = (text, selection + ":" + ",".join(map(str, ids)))
    warnings = [
        "Source unavailable: " + str(x)
        for x in (stored or {}).get("missing_sources", [])
    ]
    return dict(
        meta=dict(
            case_id=case.case_id,
            author=(stored or {}).get("author_name"),
            created_at=(stored or {}).get("created_at"),
            updated_at=(stored or {}).get("updated_at"),
            status=case.state.state_name
            if case.state
            else "closed"
            if case.close_date
            else "open",
        ),
        sources=sources,
        automatic=automatic,
        warnings=warnings,
        collections=collections,
    )


def get_incident_card(case_id):
    case = Cases.query.filter_by(case_id=case_id).first()
    if case is None:
        raise LookupError("Case not found")
    stored = get_stored_incident_card(case_id)
    return build_snapshot(source_context(case, stored), stored)


def validate_scope(selected, collections, previous=None):
    mapping = {
        "alert_id": "alerts",
        "affected_asset_ids": "assets",
        "source_asset_id": "assets",
        "target_asset_id": "assets",
        "ioc_ids": "iocs",
        "file_ids": "files",
        "performed_task_ids": "tasks",
        "planned_task_ids": "tasks",
    }
    previous = previous or {}
    for key, group in mapping.items():
        ids = (
            selected[key]
            if isinstance(selected[key], list)
            else [selected[key]]
            if selected[key]
            else []
        )
        previous_ids = (
            previous.get(key, [])
            if isinstance(previous.get(key), list)
            else [previous[key]]
            if previous.get(key)
            else []
        )
        for identifier in ids:
            obj = collections[group].get(identifier)
            if obj is None:
                # Existing missing sources remain visible; newly supplied foreign IDs fail.
                if identifier in previous_ids:
                    continue
                raise CardValidationError("Source does not belong to this case: " + key)
            if key in ("performed_task_ids", "planned_task_ids"):
                done = (
                    obj.status is not None and obj.status.status_name.lower() == "done"
                )
                if done != (key == "performed_task_ids") or (
                    key == "planned_task_ids"
                    and obj.status
                    and (obj.status.status_name.lower() == "canceled")
                ):
                    raise CardValidationError("Task status inconsistent with " + key)
    if set(selected["performed_task_ids"]) & set(selected["planned_task_ids"]):
        raise CardValidationError("Task cannot be both performed and planned")


def save_incident_card(case_id, payload, actor_id, audit=None):
    payload = validate_update(payload)
    try:
        # Lock the existing parent, including on first save when no card row exists.
        case = Cases.query.filter_by(case_id=case_id).with_for_update().first()
        if case is None:
            raise LookupError("Case not found")
        row = IncidentCard.query.filter_by(case_id=case_id).first()
        stored = serialize_card(row) or {}
        if payload["revision"] != stored.get("revision", 0):
            raise CardConflictError("Incident card changed; reload before saving")
        selected = deepcopy(SELECTIONS)
        selected.update(stored.get("selections", {}))
        selected.update(payload["selections"])
        candidate = dict(stored, selections=selected)
        context = source_context(case, candidate)
        validate_scope(selected, context["collections"], stored.get("selections"))
        selection_groups = {
            "alert_id": "alerts",
            "affected_asset_ids": "assets",
            "source_asset_id": "assets",
            "target_asset_id": "assets",
            "ioc_ids": "iocs",
            "file_ids": "files",
            "performed_task_ids": "tasks",
            "planned_task_ids": "tasks",
        }
        available = {
            key: set(context["collections"][group])
            for key, group in selection_groups.items()
        }
        candidate["missing_sources"] = unresolved_sources(
            stored, payload["selections"], available
        )
        if candidate["missing_sources"] != stored.get("missing_sources", []):
            context = source_context(case, candidate)
        fields = merge_fields(stored.get("fields", {}), payload["fields"])
        candidate["fields"] = fields
        snapshot = build_snapshot(context, candidate)
        derive(snapshot["fields"])
        now = datetime.now(timezone.utc)
        if row is None:
            actor = User.query.filter_by(id=actor_id).first()
            row = IncidentCard(
                case_id=case_id,
                author_id=actor_id,
                author_name=actor.name or actor.user if actor else None,
                created_at=now,
            )
            db.session.add(row)
        row.schema_version = 1
        row.revision = stored.get("revision", 0) + 1
        row.fields = snapshot["fields"]
        row.selections = selected
        row.missing_sources = candidate["missing_sources"]
        row.updated_at = now
        if audit is not None:
            # track_activity adds its row and commits card + activity together.
            audit(case_id, row.revision)
        else:
            db.session.commit()
        return get_incident_card(case_id)
    except Exception:
        db.session.rollback()
        raise
