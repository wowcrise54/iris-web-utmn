"""Rewrite nested card selections using the case bundle's typed references."""

from copy import deepcopy


SELECTION_KINDS = {
    "alert_id": "alert",
    "affected_asset_ids": "asset",
    "source_asset_id": "asset",
    "target_asset_id": "asset",
    "ioc_ids": "ioc",
    "file_ids": "dsfile",
    "performed_task_ids": "task",
    "planned_task_ids": "task",
}


def encode_card_references(stored):
    payload = deepcopy(stored)
    selected = payload.get("selections", {})
    for key, kind in SELECTION_KINDS.items():
        value = selected.get(key)
        if isinstance(value, list):
            selected[key] = [f"{kind}:{identifier}" for identifier in value]
        elif value is not None:
            selected[key] = f"{kind}:{value}"
    return payload


def decode_card_references(stored, ref_map):
    payload = deepcopy(stored)
    selected = payload.get("selections", {})
    missing = set(payload.get("missing_sources") or []) & set(SELECTION_KINDS)
    for key, kind in SELECTION_KINDS.items():
        value = selected.get(key)
        plural = key.endswith("_ids")
        values = (
            value if isinstance(value, list) else [value] if value is not None else []
        )
        mapped = []
        for ref in values:
            if isinstance(ref, str) and ref.startswith(f"{kind}:") and ref in ref_map:
                mapped.append(ref_map[ref])
            else:
                missing.add(key)
        selected[key] = mapped if plural else mapped[0] if mapped else None
    payload["missing_sources"] = sorted(missing)
    return payload
