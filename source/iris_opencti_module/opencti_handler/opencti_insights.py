#!/usr/bin/env python3

import hashlib
import json
from datetime import datetime, timezone


GRAPH_ENTITY_TYPES = {
    "Indicator", "StixCyberObservable", "IPv4-Addr", "IPv6-Addr",
    "Domain-Name", "Url", "Email-Addr", "StixFile", "Report", "Malware",
    "Threat-Actor", "Intrusion-Set", "Campaign", "Vulnerability",
    "Attack-Pattern", "Infrastructure", "Tool", "Identity",
}

SEVERITY_ORDER = {
    "Informational": 0,
    "Low": 1,
    "Medium": 2,
    "High": 3,
    "Critical": 4,
}


def _number(value):
    try:
        return max(0.0, min(100.0, float(value or 0)))
    except (TypeError, ValueError):
        return 0.0


def _parse_datetime(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def severity_for_risk(risk):
    if risk < 20:
        return "Informational"
    if risk < 40:
        return "Low"
    if risk < 60:
        return "Medium"
    if risk < 80:
        return "High"
    return "Critical"


def calculate_verdict(matches, now=None):
    now = now or datetime.now(timezone.utc)
    candidates = []
    for match in matches or []:
        related_types = {
            entity.get("entity_type")
            for entity in match.get("related_entities", [])
        }
        sightings = match.get("sightings") or {}
        sighting_count = int(sightings.get("count") or 0)
        risk = round(
            _number(match.get("score")) * 0.7
            + _number(match.get("confidence")) * 0.2
            + (5 if related_types.intersection({"Malware", "Threat-Actor", "Intrusion-Set", "Campaign"}) else 0)
            + (5 if sighting_count else 0)
        )
        state = "active"
        if match.get("revoked") is True:
            state = "revoked"
        elif _parse_datetime(match.get("valid_until")) and _parse_datetime(match["valid_until"]) < now:
            state = "expired"
        if state in {"expired", "revoked"}:
            risk = min(risk, 39)

        reasons = [f"OpenCTI score: {round(_number(match.get('score')))}",
                   f"Confidence: {round(_number(match.get('confidence')))}"]
        if related_types.intersection({"Malware", "Threat-Actor", "Intrusion-Set", "Campaign"}):
            reasons.append("Связано с вредоносной активностью")
        if sighting_count:
            reasons.append(f"Наблюдения: {sighting_count}")
        if state in {"expired", "revoked"}:
            reasons.append(f"Индикатор {state}; рекомендация ограничена уровнем Low")

        candidates.append({
            "risk_score": int(risk),
            "severity": severity_for_risk(risk),
            "state": state,
            "reasons": reasons,
            "sightings": {
                "count": sighting_count,
                "first_seen": sightings.get("first_seen"),
                "last_seen": sightings.get("last_seen"),
            },
            "source_object_id": match.get("id"),
        })

    if not candidates:
        return {
            "risk_score": 0, "severity": "Informational", "state": "unknown",
            "reasons": ["Точное совпадение в OpenCTI не найдено"],
            "sightings": {"count": 0, "first_seen": None, "last_seen": None},
            "source_object_id": None,
        }
    return max(candidates, key=lambda item: item["risk_score"])


def alert_recommendation(iocs):
    candidates = []
    for ioc in iocs or []:
        enrichment = ((ioc.ioc_enrichment or {}).get("opencti") or {})
        verdict = enrichment.get("verdict")
        if verdict:
            candidates.append({
                **verdict,
                "ioc_id": ioc.ioc_id,
                "ioc_value": ioc.ioc_value,
                "last_success_utc": enrichment.get("last_success_utc"),
            })
    candidates.sort(key=lambda item: item.get("risk_score", 0), reverse=True)
    winner = candidates[0] if candidates else calculate_verdict([])
    fingerprint_data = [
        [item.get("ioc_id"), item.get("last_success_utc"), item.get("risk_score")]
        for item in candidates
    ]
    return {
        "severity": winner["severity"],
        "risk_score": winner["risk_score"],
        "reasons": winner.get("reasons", [])[:3],
        "source_ioc_ids": [item["ioc_id"] for item in candidates[:3]],
        "fingerprint": hashlib.sha256(
            json.dumps(fingerprint_data, sort_keys=True).encode("utf-8")
        ).hexdigest(),
    }


def graph_fingerprint(iocs):
    values = []
    for ioc in iocs or []:
        enrichment = ((ioc.ioc_enrichment or {}).get("opencti") or {})
        values.append([ioc.ioc_id, enrichment.get("last_success_utc"),
                       [match.get("id") for match in enrichment.get("matches", [])]])
    return hashlib.sha256(json.dumps(values, sort_keys=True).encode("utf-8")).hexdigest()


def normalize_graph(payloads, root_ids, base_url, node_limit=100, edge_limit=200, root_nodes=None):
    nodes, edges, errors = {}, {}, []
    truncated = False
    root_ids = set(root_ids)
    for entity in root_nodes or []:
        entity_id = entity.get("id")
        if entity_id and entity_id not in nodes and len(nodes) < node_limit:
            nodes[entity_id] = {
                "id": entity_id,
                "entity_type": entity.get("entity_type"),
                "name": entity.get("name") or entity.get("value") or entity_id,
                "description": entity.get("description"),
                "score": entity.get("score"),
                "confidence": entity.get("confidence"),
                "markings": entity.get("markings") or [],
                "labels": entity.get("labels") or [],
                "created_at": entity.get("created_at"),
                "updated_at": entity.get("updated_at"),
                "opencti_url": entity.get("opencti_url"),
                "is_root": True,
            }
    for payload in payloads:
        if payload.get("error"):
            errors.append(payload["error"])
        for relationship in payload.get("relationships", []):
            source = relationship.get("from") or {}
            target = relationship.get("to") or {}
            if source.get("entity_type") not in GRAPH_ENTITY_TYPES or target.get("entity_type") not in GRAPH_ENTITY_TYPES:
                continue
            for entity in (source, target):
                entity_id = entity.get("id")
                if not entity_id or entity_id in nodes:
                    continue
                if len(nodes) >= node_limit:
                    truncated = True
                    continue
                nodes[entity_id] = {
                    "id": entity_id,
                    "entity_type": entity.get("entity_type"),
                    "name": (entity.get("representative") or {}).get("main") or entity_id,
                    "description": entity.get("description"),
                    "score": entity.get("x_opencti_score"),
                    "confidence": entity.get("confidence"),
                    "markings": entity.get("markings") or [],
                    "labels": entity.get("labels") or [],
                    "created_at": entity.get("created_at"),
                    "updated_at": entity.get("updated_at"),
                    "opencti_url": (
                        f"{str(base_url).rstrip('/')}/dashboard/id/{entity_id}"
                        if str(base_url).lower().startswith(("http://", "https://")) else None
                    ),
                    "is_root": entity_id in root_ids,
                }
            key = (source.get("id"), target.get("id"), relationship.get("relationship_type"))
            if key in edges:
                continue
            if len(edges) >= edge_limit:
                truncated = True
                continue
            if key[0] in nodes and key[1] in nodes:
                edges[key] = {
                    "id": relationship.get("id") or "|".join(str(value) for value in key),
                    "source": key[0], "target": key[1],
                    "relationship_type": key[2] or "related-to",
                    "created_at": relationship.get("created_at"),
                    "updated_at": relationship.get("updated_at"),
                }
    return {"nodes": list(nodes.values()), "edges": list(edges.values()),
            "truncated": truncated, "errors": errors}
