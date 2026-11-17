"""Normalize older card snapshots without touching any source entity."""

from copy import deepcopy
from app.business.incident_card_catalog import (
    FIELDS,
    normalize_criticality,
    normalize_preparers,
)


def clean_fields(fields):
    result = {}
    for key, entry in normalize_preparers(fields).items():
        if key not in FIELDS:
            continue
        value = deepcopy(entry.get("value"))
        if key == "criticality" and value is not None:
            # Recognized legacy labels remain importable; unknown values fail validation.
            value = normalize_criticality(value) or value
        if key == "investigators" and isinstance(value, list):
            # The form asks for names, not positions; preserve both existing values as text.
            value = "\n".join(
                " / ".join(str(p.get(k) or "") for k in ("name", "position")).strip(
                    " /"
                )
                for p in value
            )
        result[key] = dict(value=value, mode="manual", source=None, status="manual")
    location = (fields or {}).get("report_location", {}).get("value")
    if location:
        previous = result.get("report_url", {}).get("value")
        result["report_url"] = dict(
            value="\n".join(str(v) for v in (previous, location) if v),
            mode="manual",
            source=None,
            status="manual",
        )
    return result
