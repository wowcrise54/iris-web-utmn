"""Transfer only regulation fields, with no links to source-instance entities."""

from copy import deepcopy
from app.business.incident_card_cleanup import clean_fields


def encode_card_references(stored):
    payload = deepcopy(stored)
    payload["fields"] = clean_fields(payload.get("fields"))
    payload["selections"] = {}
    payload["missing_sources"] = []
    return payload


def decode_card_references(stored, ref_map):
    return encode_card_references(stored)
