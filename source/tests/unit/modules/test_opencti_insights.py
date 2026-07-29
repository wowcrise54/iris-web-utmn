import unittest
from datetime import datetime, timezone

from iris_opencti_module.opencti_handler.opencti_insights import calculate_verdict
from iris_opencti_module.opencti_handler.opencti_insights import normalize_graph
from iris_opencti_module.opencti_handler.opencti_insights import severity_for_risk


class OpenCTIInsightsTests(unittest.TestCase):
    def test_severity_boundaries(self):
        self.assertEqual(severity_for_risk(19), "Informational")
        self.assertEqual(severity_for_risk(20), "Low")
        self.assertEqual(severity_for_risk(40), "Medium")
        self.assertEqual(severity_for_risk(60), "High")
        self.assertEqual(severity_for_risk(80), "Critical")

    def test_verdict_formula_and_reasons(self):
        verdict = calculate_verdict([{
            "id": "indicator--1", "score": 80, "confidence": 90,
            "related_entities": [{"entity_type": "Malware"}],
            "sightings": {"count": 3, "first_seen": "2026-01-01", "last_seen": "2026-01-02"},
        }])
        self.assertEqual(verdict["risk_score"], 84)
        self.assertEqual(verdict["severity"], "Critical")
        self.assertIn("Наблюдения: 3", verdict["reasons"])

    def test_revoked_and_expired_are_capped(self):
        now = datetime(2026, 7, 29, tzinfo=timezone.utc)
        revoked = calculate_verdict([{"score": 100, "confidence": 100, "revoked": True}], now)
        expired = calculate_verdict([{
            "score": 100, "confidence": 100, "valid_until": "2026-01-01T00:00:00Z"
        }], now)
        self.assertEqual(revoked["risk_score"], 39)
        self.assertEqual(revoked["severity"], "Low")
        self.assertEqual(expired["state"], "expired")

    def test_graph_dedupes_cycles_and_obeys_limits(self):
        relation = {
            "id": "relationship--1", "relationship_type": "uses",
            "from": {"id": "malware--1", "entity_type": "Malware", "representative": {"main": "M"}},
            "to": {"id": "tool--1", "entity_type": "Tool", "representative": {"main": "T"}},
        }
        graph = normalize_graph(
            [{"relationships": [relation, relation]}],
            {"malware--1"}, "https://opencti.local",
            node_limit=2, edge_limit=1,
        )
        self.assertEqual(len(graph["nodes"]), 2)
        self.assertEqual(len(graph["edges"]), 1)
        self.assertTrue(graph["nodes"][0]["opencti_url"].startswith("https://"))

    def test_graph_rejects_unsafe_base_url(self):
        graph = normalize_graph(
            [{"relationships": [{
                "relationship_type": "related-to",
                "from": {"id": "malware--1", "entity_type": "Malware"},
                "to": {"id": "tool--1", "entity_type": "Tool"},
            }]}],
            set(), "javascript:alert(1)",
        )
        self.assertTrue(all(node["opencti_url"] is None for node in graph["nodes"]))


if __name__ == "__main__":
    unittest.main()
