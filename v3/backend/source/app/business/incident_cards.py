"""Pure incident-card validation, derivation and source projection."""

from copy import deepcopy
from datetime import datetime, timezone
import json
import re
from app.business.incident_card_catalog import (
    FIELDS,
    SECTIONS,
    normalize_criticality,
    normalize_preparers,
)

SELECTIONS = {}


class CardValidationError(ValueError):
    pass


class CardConflictError(ValueError):
    pass


def alert_defaults(case, alerts):
    """Use one same-customer origin alert and its persisted escalation history."""
    candidates = []
    for alert in alerts:
        if alert.alert_customer_id != case.client_id:
            continue
        moments = []
        history = (
            alert.modification_history
            if isinstance(alert.modification_history, dict)
            else {}
        )
        for stamp, event in history.items():
            if not isinstance(event, dict) or not re.search(
                r"^Alert (?:escalated to|escalated into new|merged into existing) case #"
                + re.escape(str(case.case_id))
                + r"$",
                str(event.get("action", "")),
                re.I,
            ):
                continue
            try:
                moments.append(datetime.fromtimestamp(float(stamp), timezone.utc))
            except (TypeError, ValueError, OverflowError, OSError):
                continue
        moment = min(moments) if moments else None
        candidates.append(
            (
                moment.timestamp() if moment else float("inf"),
                alert.alert_id,
                alert,
                moment,
            )
        )
    if not candidates:
        return {}
    _, _, alert, moment = min(candidates, key=lambda item: (item[0], item[1]))
    source = "alert:" + str(alert.alert_id)
    time_source = source
    if moment is None:
        moment = getattr(case, "initial_date", None)
        time_source = "case.initial_date"
        if moment is not None and moment.tzinfo is None:
            moment = moment.replace(tzinfo=timezone.utc)

    severity = alert.severity.severity_name if alert.severity else None
    # The card has three levels; a critical source alert belongs to its highest bucket.
    level = (
        "Высокий"
        if str(severity).strip().casefold()
        in ("critical", "критический", "критическая")
        else normalize_criticality(severity)
    )
    event_time = alert.alert_source_event_time
    if event_time is not None and event_time.tzinfo is None:
        event_time = event_time.replace(tzinfo=timezone.utc)
    return dict(
        criticality=(level, source),
        detection_source=(alert.alert_source, source),
        incident_at=(
            moment.astimezone(timezone.utc).isoformat() if moment else None,
            time_source,
        ),
        occurred_at=(
            event_time.astimezone(timezone.utc).isoformat() if event_time else None,
            source,
        ),
    )


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
                not isinstance(value, str)
                or len(value)
                > {"investigators": 50200, "report_url": 40001}.get(key, 20000)
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
                                not isinstance(v, str)
                                or len(v) > (20000 if key == "prepared_by" else 500)
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
        column = ["auxiliary", "key", "target"].index(asset_type)
        values = [matrix[c - 1][column] if c != 8 else "low" for c in categories]
        importance = max(values, key=levels.index)
    base_priority = (
        {"auxiliary": [9, 8, 6], "key": [7, 5, 3], "target": [4, 2, 1]}[asset_type][
            levels.index(importance)
        ]
        if importance
        else None
    )
    priority = (
        v("priority_override")
        if v("priority_override") is not None
        and fields.get("priority_override", {}).get("mode") != "auto"
        else base_priority
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
    )


def merge_fields(stored_fields, submitted_fields):
    """Auto fallback values and provenance belong exclusively to the server."""
    merged = {k: deepcopy(v) for k, v in stored_fields.items() if k in FIELDS}
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

    fields = {
        k: v
        for k, v in normalize_preparers(stored.get("fields", {})).items()
        if k in FIELDS
    }
    automatic = context.get("automatic", {})
    warnings = []
    for key, spec in FIELDS.items():
        entry = fields.get(
            key, {"value": None, "mode": "auto" if spec["auto"] else "manual"}
        )
        if key in (
            "incident_at",
            "detection_source",
            "occurred_at",
            "priority_override",
        ) and entry.get("value") in (None, ""):
            entry = dict(entry, mode="auto")
        if key == "priority_override" and entry["mode"] == "auto":
            entry = dict(value=None, mode="auto", source=None)
        if entry["mode"] == "auto" and spec["auto"]:
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
        if key == "criticality":
            previous = entry["value"]
            entry["value"] = normalize_criticality(previous)
            if previous is not None and entry["value"] is None:
                entry["status"] = "missing"
                warnings.append(
                    "Выберите уровень критичности: Высокий, Средний или Низкий"
                )
        fields[key] = entry
    try:
        derived = derive(fields)
    except CardValidationError as exc:
        warnings.append(str(exc))
        derived = dict(
            importance=None,
            priority=None,
            incident_duration_seconds=None,
        )
    if fields["priority_override"]["mode"] == "auto":
        fields["priority_override"] = dict(
            value=derived["priority"],
            mode="auto",
            source="regulation",
            status="ok" if derived["priority"] is not None else "missing",
        )
    return dict(
        schema_version=1,
        revision=stored.get("revision", 0),
        meta=context["meta"],
        fields=fields,
        selections=selected,
        derived=derived,
        catalog={"sections": deepcopy(SECTIONS)},
        warnings=warnings + context.get("warnings", []),
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
