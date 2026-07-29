#!/usr/bin/env python3

import ipaddress
import re
from datetime import datetime
from urllib.parse import urlsplit
from urllib.parse import urlunsplit


HASH_TYPE_BY_LENGTH = {
    32: "md5",
    40: "sha1",
    56: "sha224",
    64: "sha256",
    96: "sha384",
    128: "sha512",
}

OPENCTI_TO_IRIS_TYPE = {
    "IPv4-Addr": "ip-dst",
    "IPv6-Addr": "ip-dst",
    "Domain-Name": "domain",
    "Hostname": "hostname",
    "Url": "url",
    "Email-Addr": "email",
    "File": "filename",
    "Autonomous-System": "AS",
    "X509-Certificate": "x509-fingerprint-sha256",
}

STIX_PATTERN_TYPE_TO_IRIS = {
    "ipv4-addr": "ip-dst",
    "ipv6-addr": "ip-dst",
    "domain-name": "domain",
    "url": "url",
    "email-addr": "email",
    "hostname": "hostname",
    "autonomous-system": "AS",
}

RELATED_ENTITY_TYPES = {
    "Report",
    "Malware",
    "Threat-Actor",
    "Campaign",
    "Vulnerability",
    "Attack-Pattern",
}


def utc_now_iso():
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def canonicalize_ioc_value(value, ioc_type=None):
    if value is None:
        return None

    normalized = str(value).strip()
    if not normalized:
        return None

    normalized_type = (ioc_type or infer_ioc_type(normalized) or "").lower()

    try:
        if normalized_type in {"ip-any", "ip-dst", "ip-src", "ipv4", "ipv6"}:
            return ipaddress.ip_address(normalized).compressed
    except ValueError:
        return None

    hash_types = set(HASH_TYPE_BY_LENGTH.values())
    if normalized_type in hash_types or any(
        normalized_type.endswith(f"|{hash_type}") for hash_type in hash_types
    ):
        return normalized.lower()

    if normalized_type in {"domain", "hostname"}:
        return normalized.lower().rstrip(".")

    if normalized_type in {"email", "email-src", "email-dst", "target-email"}:
        return normalized.lower()

    if normalized_type == "url":
        try:
            parsed = urlsplit(normalized)
        except ValueError:
            return None
        if not parsed.scheme or not parsed.netloc:
            return None
        return urlunsplit((
            parsed.scheme.lower(),
            parsed.netloc.lower(),
            parsed.path or "",
            parsed.query,
            parsed.fragment,
        ))

    return normalized


def is_exact_ioc_match(query_value, match, query_type=None):
    match_value = match.get("value")
    match_type = match.get("iris_ioc_type")
    canonical_query = canonicalize_ioc_value(query_value, query_type)
    canonical_match = canonicalize_ioc_value(match_value, match_type)
    return canonical_query is not None and canonical_query == canonical_match


def connection_edges(connection):
    if isinstance(connection, list):
        return [node for node in connection if isinstance(node, dict)]

    return [
        edge.get("node")
        for edge in (connection or {}).get("edges", [])
        if edge.get("node")
    ]


def flatten_connection_values(connection, field):
    return [
        node.get(field)
        for node in connection_edges(connection)
        if node.get(field)
    ]


def flatten_external_references(connection):
    refs = []
    for node in connection_edges(connection):
        refs.append({
            "source_name": node.get("source_name"),
            "external_id": node.get("external_id"),
            "url": node.get("url"),
        })
    return refs


def opencti_entity_url(base_url, entity_id):
    if not base_url or not entity_id:
        return None
    normalized = str(base_url).strip().rstrip("/")
    if normalized.endswith("/graphql"):
        normalized = normalized[:-8].rstrip("/")
    return f"{normalized}/dashboard/id/{entity_id}"


def normalize_related_entities(payload, object_id, base_url=None, limit=20):
    related = []

    for relationship in connection_edges(payload.get("stixCoreRelationships")):
        source = relationship.get("from") or {}
        target = relationship.get("to") or {}
        entity = target if source.get("id") == object_id else source
        if entity.get("id") == object_id or entity.get("entity_type") not in RELATED_ENTITY_TYPES:
            continue
        related.append({
            "id": entity.get("id"),
            "entity_type": entity.get("entity_type"),
            "name": (entity.get("representative") or {}).get("main"),
            "relationship_type": relationship.get("relationship_type"),
            "direction": "outgoing" if source.get("id") == object_id else "incoming",
            "created_at": entity.get("created_at"),
            "updated_at": entity.get("updated_at"),
            "opencti_url": opencti_entity_url(base_url, entity.get("id")),
        })

    for container in connection_edges(payload.get("containers")):
        if container.get("entity_type") not in RELATED_ENTITY_TYPES:
            continue
        related.append({
            "id": container.get("id"),
            "entity_type": container.get("entity_type"),
            "name": (container.get("representative") or {}).get("main"),
            "relationship_type": "contains",
            "direction": "incoming",
            "created_at": container.get("created_at"),
            "updated_at": container.get("updated_at"),
            "opencti_url": opencti_entity_url(base_url, container.get("id")),
        })

    deduped = []
    seen = set()
    for entity in related:
        key = (entity.get("id"), entity.get("entity_type"))
        if not entity.get("id") or key in seen:
            continue
        seen.add(key)
        deduped.append(entity)
        if len(deduped) >= max(0, int(limit)):
            break

    return deduped


def extract_value_from_pattern(pattern):
    if not pattern:
        return None, None

    file_hash = re.search(
        r"file:hashes\.(?:'|\")?(MD5|SHA-1|SHA-224|SHA-256|SHA-384|SHA-512)(?:'|\")?\s*=\s*(?:'|\")([^'\"]+)(?:'|\")",
        pattern,
        re.IGNORECASE,
    )
    if file_hash:
        hash_type = file_hash.group(1).lower().replace("-", "")
        return file_hash.group(2), hash_type

    observable = re.search(
        r"\b([a-z0-9_-]+):value\s*=\s*(?:'|\")([^'\"]+)(?:'|\")",
        pattern,
        re.IGNORECASE,
    )
    if observable:
        return observable.group(2), STIX_PATTERN_TYPE_TO_IRIS.get(observable.group(1).lower())

    generic_value = re.search(r"(?:'|\")([^'\"]+)(?:'|\")", pattern)
    if generic_value:
        return generic_value.group(1), None

    return None, None


def infer_ioc_type(value, entity_type=None, pattern=None):
    if entity_type in OPENCTI_TO_IRIS_TYPE:
        mapped_type = OPENCTI_TO_IRIS_TYPE[entity_type]
        if mapped_type != "filename":
            return mapped_type

    pattern_value, pattern_type = extract_value_from_pattern(pattern)
    value = value or pattern_value
    if pattern_type:
        return pattern_type

    if not value:
        return "other"

    lowered = value.lower()
    if lowered.startswith(("http://", "https://", "hxxp://", "hxxps://")):
        return "url"

    if "@" in value and re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", value):
        return "email"

    try:
        ipaddress.ip_address(value)
        return "ip-dst"
    except ValueError:
        pass

    normalized_hash = lowered
    if re.fullmatch(r"[a-f0-9]+", normalized_hash):
        hash_type = HASH_TYPE_BY_LENGTH.get(len(normalized_hash))
        if hash_type:
            return hash_type

    domain_candidate = lowered.rstrip(".")
    if re.match(r"^[a-z0-9][a-z0-9.-]+\.[a-z]{2,}$", domain_candidate):
        return "domain"

    if entity_type == "File":
        return "filename"

    return "other"


def normalize_opencti_node(node, source, base_url=None):
    value = node.get("observable_value") or node.get("value")
    extracted_value, extracted_type = extract_value_from_pattern(node.get("pattern"))
    value = value or extracted_value
    score = node.get("x_opencti_score")

    return {
        "id": node.get("id"),
        "standard_id": node.get("standard_id"),
        "source": source,
        "entity_type": node.get("entity_type"),
        "name": node.get("name"),
        "value": value,
        "iris_ioc_type": extracted_type or infer_ioc_type(
            value=value,
            entity_type=node.get("entity_type"),
            pattern=node.get("pattern"),
        ),
        "description": node.get("description"),
        "pattern": node.get("pattern"),
        "pattern_type": node.get("pattern_type"),
        "confidence": node.get("confidence"),
        "score": score if score is not None else 0,
        "revoked": node.get("revoked"),
        "valid_from": node.get("valid_from"),
        "valid_until": node.get("valid_until"),
        "created_at": node.get("created_at"),
        "updated_at": node.get("updated_at"),
        "labels": flatten_connection_values(node.get("objectLabel"), "value"),
        "markings": flatten_connection_values(node.get("objectMarking"), "definition"),
        "external_references": flatten_external_references(node.get("externalReferences")),
        "opencti_url": opencti_entity_url(base_url, node.get("id")),
        "related_entities": [],
    }


def dedupe_matches(matches):
    seen = set()
    deduped = []
    for match in matches:
        key = (
            match.get("id"),
            match.get("iris_ioc_type"),
            match.get("value"),
            match.get("pattern"),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(match)
    return deduped


def normalize_search_results(search_results, min_score=0, query_value=None, query_type=None, base_url=None):
    matches = []
    for node in connection_edges(search_results.get("indicators")):
        match = normalize_opencti_node(node, source="indicator", base_url=base_url)
        if safe_int(match.get("score")) >= min_score:
            matches.append(match)

    for node in connection_edges(search_results.get("stixCyberObservables")):
        match = normalize_opencti_node(node, source="observable", base_url=base_url)
        if safe_int(match.get("score")) >= min_score:
            matches.append(match)

    matches = dedupe_matches(matches)
    if query_value is not None:
        matches = [
            match
            for match in matches
            if is_exact_ioc_match(query_value, match, query_type=query_type)
        ]
    return matches


def safe_int(value, default=0):
    try:
        return int(value or default)
    except (TypeError, ValueError):
        return default


def build_enrichment_payload(
    query_value,
    matches,
    status=None,
    last_attempt_utc=None,
    last_success_utc=None,
    error=None,
    generated_tags=None,
):
    lookup_time = last_attempt_utc or utc_now_iso()
    return {
        "provider": "OpenCTI",
        "query_value": query_value,
        "last_lookup_utc": lookup_time,
        "status": status or ("match" if matches else "no_match"),
        "last_attempt_utc": lookup_time,
        "last_success_utc": last_success_utc or lookup_time,
        "error": error,
        "generated_tags": generated_tags or [],
        "match_count": len(matches),
        "matches": matches,
    }
