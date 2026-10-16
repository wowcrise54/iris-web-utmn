"""Pure incident-card validation, derivation and source projection."""

from copy import deepcopy
from datetime import datetime, timezone
import json
from app.business.incident_card_catalog import FIELDS, SECTIONS

SELECTIONS = {
    "alert_id": None,
    "affected_asset_ids": [],
    "source_asset_id": None,
    "target_asset_id": None,
    "ioc_ids": [],
    "file_ids": [],
    "performed_task_ids": [],
    "planned_task_ids": [],
}


class CardValidationError(ValueError):
    pass


class CardConflictError(ValueError):
    pass


def timestamp(value):
    if not isinstance(value, str):
        raise CardValidationError("Datetime must be an ISO timestamp")
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise CardValidationError("Invalid datetime")
    if result.tzinfo is None or result.utcoffset() is None:
        raise CardValidationError("Datetime requires timezone")
    return result.astimezone(timezone.utc)


def validate_update(payload):
    if not isinstance(payload, dict) or set(payload) - {
        "schema_version",
        "revision",
        "fields",
        "selections",
    }:
        raise CardValidationError("Unknown request properties")
    if len(json.dumps(payload, ensure_ascii=False).encode()) > 256000:
        raise CardValidationError("Card exceeds 256 KB")
    if type(payload.get("schema_version")) is not int or payload["schema_version"] != 1:
        raise CardValidationError("Unsupported schema version")
    if type(payload.get("revision")) is not int or payload["revision"] < 0:
        raise CardValidationError("Invalid revision")
    fields = payload.get("fields", {})
    if not isinstance(fields, dict):
        raise CardValidationError("Fields must be an object")
    cleaned = {}
    for key, entry in fields.items():
        if key not in FIELDS:
            raise CardValidationError("Unknown field: " + key)
        spec = FIELDS[key]
        if not isinstance(entry, dict) or set(entry) != {"value", "mode"}:
            raise CardValidationError("Invalid field entry: " + key)
        mode, value = (entry["mode"], entry["value"])
        if mode not in ("auto", "manual") or (mode == "auto" and (not spec["auto"])):
            raise CardValidationError("Invalid field mode: " + key)
        kind = spec["type"]
        if value is not None:
            if kind in ("text", "textarea") and (
                not isinstance(value, str) or len(value) > 20000
            ):
                raise CardValidationError("Invalid text: " + key)
            if kind == "boolean" and type(value) is not bool:
                raise CardValidationError("Invalid boolean: " + key)
            if kind == "datetime":
                value = timestamp(value).isoformat()
            choices = [x["value"] for x in spec.get("options", [])]
            if kind == "choice" and (
                type(value) not in (str, int) or value not in choices
            ):
                raise CardValidationError("Invalid choice: " + key)
            if kind == "multichoice" and (
                not isinstance(value, list)
                or len(value) > 50
                or any((type(x) not in (str, int) or x not in choices for x in value))
                or (len(set(value)) != len(value))
            ):
                raise CardValidationError("Invalid choices: " + key)
            if kind == "people":
                if not isinstance(value, list) or len(value) > 50:
                    raise CardValidationError("Invalid people: " + key)
                for person in value:
                    if (
                        not isinstance(person, dict)
                        or set(person) != {"name", "position"}
                        or any(
                            (
                                not isinstance(v, str) or len(v) > 500
                                for v in person.values()
                            )
                        )
                    ):
                        raise CardValidationError("Invalid person: " + key)
        if (
            key == "incident_types"
            and isinstance(value, list)
            and "unknown" in value
            and len(value) > 1
        ):
            raise CardValidationError(
                "Unknown incident type cannot be combined with known types"
            )
        cleaned[key] = {"value": value, "mode": mode}
    selected = payload.get("selections", {})
    if not isinstance(selected, dict) or set(selected) - set(SELECTIONS):
        raise CardValidationError("Unknown selections")
    selected = deepcopy(selected)
    for key, value in selected.items():
        if key.endswith("_ids"):
            if (
                not isinstance(value, list)
                or len(value) > 200
                or any((type(v) is not int or v <= 0 for v in value))
                or (len(set(value)) != len(value))
            ):
                raise CardValidationError("Invalid IDs: " + key)
        elif value is not None and (type(value) is not int or value <= 0):
            raise CardValidationError("Invalid ID: " + key)
    return dict(
        schema_version=1,
        revision=payload["revision"],
        fields=cleaned,
        selections=selected,
    )


def derive(fields):
    def v(key):
        return fields.get(key, {}).get("value")

    categories = v("categories") or []
    asset_type = v("prioritization_type")
    importance = None
    matrix = [
        ["medium", "high", "high"],
        ["high", "high", "high"],
        ["medium", "high", "high"],
        ["low", "medium", "medium"],
        ["low", "low", "medium"],
        ["low", "medium", "medium"],
        ["low", "low", "low"],
    ]
    levels = ["low", "medium", "high"]
    if categories and asset_type in ("auxiliary", "key", "target"):
        if 8 not in categories or (
            v("category8_importance") in levels
            and isinstance(v("category8_reason"), str)
            and v("category8_reason").strip()
        ):
            values = [
                matrix[c - 1][["auxiliary", "key", "target"].index(asset_type)]
                for c in categories
                if 1 <= c <= 7
            ]
            if 8 in categories:
                values.append(v("category8_importance"))
            if values:
                importance = max(values, key=levels.index)
    priority = (
        {"auxiliary": [9, 8, 6], "key": [7, 5, 3], "target": [4, 2, 1]}[asset_type][
            levels.index(importance)
        ]
        if importance
        else None
    )
    pairs = [
        ("occurred_at", "detected_at"),
        ("detected_at", "notified_at"),
        ("detected_at", "investigation_started_at"),
        ("occurred_at", "incident_ended_at"),
        ("incident_ended_at", "impact_ended_at"),
        ("investigation_started_at", "investigation_ended_at"),
    ]
    for start, end in pairs:
        if v(start) and v(end) and (timestamp(v(end)) < timestamp(v(start))):
            raise CardValidationError(end + " precedes " + start)

    def elapsed(start, end):
        return (
            int((timestamp(v(end)) - timestamp(v(start))).total_seconds())
            if v(start) and v(end)
            else None
        )

    return dict(
        importance=importance,
        priority=priority,
        incident_duration_seconds=elapsed("occurred_at", "incident_ended_at")
        if v("completed") is True
        else None,
        reaction_seconds=elapsed("detected_at", "investigation_started_at"),
    )


def unresolved_sources(stored, submitted, available):
    """Echoing selections does not resolve an imported partial or missing source."""
    unresolved = []
    for key in stored.get("missing_sources", []):
        value = submitted.get(key)
        previous = stored.get("selections", {}).get(key)
        ids = value if isinstance(value, list) else [value] if value is not None else []
        changed = (
            (set(value) != set(previous))
            if isinstance(value, list) and isinstance(previous, list)
            else value != previous
        )
        if (
            key not in submitted
            or not ids
            or not changed
            or not set(ids).issubset(available.get(key, set()))
        ):
            unresolved.append(key)
    return unresolved


def merge_fields(stored_fields, submitted_fields):
    """Auto fallback values and provenance belong exclusively to the server."""
    merged = deepcopy(stored_fields)
    for key, entry in submitted_fields.items():
        if entry["mode"] == "manual":
            merged[key] = deepcopy(entry)
        else:
            previous = merged.get(key, {})
            merged[key] = {
                "value": previous.get("value"),
                "source": previous.get("source"),
                "mode": "auto",
            }
    return merged


def build_snapshot(context, stored=None):
    stored = stored or {}
    selected = deepcopy(SELECTIONS)
    selected.update(stored.get("selections", {}))
    fields = deepcopy(stored.get("fields", {}))
    automatic = context.get("automatic", {})
    warnings = []
    for key, spec in FIELDS.items():
        entry = fields.get(
            key, {"value": None, "mode": "auto" if spec["auto"] else "manual"}
        )
        if entry["mode"] == "auto":
            value, source = automatic.get(key, (None, None))
            if value is not None:
                entry = dict(value=value, mode="auto", source=source, status="ok")
            else:
                entry = dict(
                    value=entry.get("value"),
                    mode="auto",
                    source=entry.get("source"),
                    status="missing",
                )
                if entry["value"] is not None:
                    warnings.append(
                        "Source unavailable for " + key + "; retained last snapshot"
                    )
        else:
            entry = dict(
                value=entry.get("value"), mode="manual", source=None, status="manual"
            )
        fields[key] = entry
    missing = [
        key
        for key, entry in fields.items()
        if entry["value"] is None
        or entry["value"] == ""
        or entry["value"] == []
        or (entry["status"] == "missing")
    ]
    try:
        derived = derive(fields)
    except CardValidationError as exc:
        warnings.append(str(exc))
        derived = dict(
            importance=None,
            priority=None,
            incident_duration_seconds=None,
            reaction_seconds=None,
        )
    if 8 in (fields["categories"]["value"] or []) and derived["importance"] is None:
        warnings.append("Category 8 requires importance and rationale")
    return dict(
        schema_version=1,
        revision=stored.get("revision", 0),
        meta=context["meta"],
        fields=fields,
        selections=selected,
        derived=derived,
        catalog={"sections": deepcopy(SECTIONS)},
        sources=context["sources"],
        warnings=warnings + context.get("warnings", []),
        completeness=dict(
            missing=missing, total=len(FIELDS), filled=len(FIELDS) - len(missing)
        ),
    )


def get_incident_card(case_id):
    from app.datamgmt.case.incident_card_db import get_incident_card as read

    return read(case_id)


def save_incident_card(case_id, payload, actor_id):
    from app.datamgmt.case.incident_card_db import save_incident_card as save

    from app.iris_engine.utils.tracker import track_activity

    def audit(identifier, revision):
        track_activity(
            "updated incident card revision " + str(revision),
            caseid=identifier,
            user_id_override=actor_id,
        )

    return save(case_id, payload, actor_id, audit=audit)
