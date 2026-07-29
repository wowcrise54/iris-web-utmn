from unittest import TestCase
from unittest.mock import MagicMock
from unittest.mock import patch

from app import app
from app.models.alerts import Alert
from app.models.models import Ioc
from iris_opencti_module.opencti_handler.opencti_client import OpenCTIClientError
from iris_opencti_module.opencti_handler.opencti_handler import OpenCTIHandler


def observable_payload(value, description=None, labels=None, external_references=None):
    return {
        "indicators": {"edges": []},
        "stixCyberObservables": {
            "edges": [
                {
                    "node": {
                        "id": f"observable--{value}",
                        "entity_type": "Domain-Name" if "." in value else "IPv4-Addr",
                        "observable_value": value,
                        "description": description,
                        "x_opencti_score": 80,
                        "objectLabel": {
                            "edges": [
                                {"node": {"value": label}}
                                for label in (labels or [])
                            ]
                        },
                        "objectMarking": {"edges": []},
                        "externalReferences": {
                            "edges": [
                                {"node": reference}
                                for reference in (external_references or [])
                            ]
                        },
                    }
                }
            ]
        },
    }


class TestOpenCTIHandler(TestCase):
    def setUp(self):
        self.handler = OpenCTIHandler.__new__(OpenCTIHandler)
        self.handler.mod_config = {
            "opencti_url": "http://opencti:8080",
            "opencti_public_url": "http://127.0.0.1:4000",
            "opencti_max_results": 20,
            "opencti_min_score": 0,
            "opencti_store_raw_enrichment": True,
            "opencti_report_as_attribute": True,
            "opencti_add_tags": True,
            "opencti_manual_alert_max_iocs": 100,
            "opencti_report_template": (
                "{{ query_value }}{% for match in matches %}"
                "{{ match.description }}"
                "{% for ref in match.external_references %}"
                "{% if ref.url %}<a href=\"{{ ref.url }}\">ref</a>{% endif %}"
                "{% endfor %}{% endfor %}"
            ),
        }
        self.handler.server_config = {}
        self.handler.log = MagicMock()
        self.handler.client = MagicMock()
        self.handler.client.get_related_entities.return_value = {
            "stixCoreRelationships": {"edges": []},
            "containers": {"edges": []},
        }

    @staticmethod
    def make_ioc(value, tags="analyst-tag"):
        ioc = Ioc()
        ioc.ioc_value = value
        ioc.ioc_tags = tags
        ioc.ioc_enrichment = {}
        ioc.custom_attributes = {}
        return ioc

    def test_successful_lookup_updates_state_tags_and_safe_report(self):
        ioc = self.make_ioc("example.com")
        self.handler.client.search_ioc.return_value = observable_payload(
            "example.com",
            description="<script>alert(1)</script>",
            labels=["Malicious Traffic"],
            external_references=[
                {"source_name": "unsafe", "url": "javascript:alert(1)"},
                {"source_name": "safe", "url": "https://opencti.local/object/1"},
            ],
        )

        status, matches = self.handler._enrich_ioc(ioc)

        enrichment = ioc.ioc_enrichment["opencti"]
        report = ioc.custom_attributes["OpenCTI Report"]["HTML report"]["value"]
        self.assertFalse(status.is_failure())
        self.assertEqual(len(matches), 1)
        self.assertEqual(enrichment["status"], "match")
        self.assertEqual(enrichment["match_count"], 1)
        self.assertIn("opencti:match", ioc.ioc_tags)
        self.assertIn("opencti:label:malicious-traffic", ioc.ioc_tags)
        self.assertIn("&lt;script&gt;", report)
        self.assertNotIn("javascript:", report)
        self.assertIn("https://opencti.local/object/1", report)

    def test_successful_lookup_adds_key_related_entities(self):
        ioc = self.make_ioc("example.com")
        self.handler.client.search_ioc.return_value = observable_payload("example.com")
        self.handler.client.get_related_entities.return_value = {
            "stixCoreRelationships": {
                "edges": [{
                    "node": {
                        "relationship_type": "indicates",
                        "from": {
                            "id": "observable--example.com",
                            "entity_type": "Domain-Name",
                        },
                        "to": {
                            "id": "malware--1",
                            "entity_type": "Malware",
                            "representative": {"main": "Mimikatz"},
                        },
                    }
                }]
            },
            "containers": {
                "edges": [{
                    "node": {
                        "id": "report--1",
                        "entity_type": "Report",
                        "representative": {"main": "Investigation report"},
                    }
                }]
            },
        }

        status, matches = self.handler._enrich_ioc(ioc)

        self.assertFalse(status.is_failure())
        self.assertEqual(
            [entity["entity_type"] for entity in matches[0]["related_entities"]],
            ["Malware", "Report"],
        )
        self.assertEqual(matches[0]["related_entities"][0]["name"], "Mimikatz")
        self.assertEqual(
            matches[0]["related_entities"][0]["opencti_url"],
            "http://127.0.0.1:4000/dashboard/id/malware--1",
        )

    def test_related_lookup_error_keeps_exact_match(self):
        ioc = self.make_ioc("example.com")
        self.handler.client.search_ioc.return_value = observable_payload("example.com")
        self.handler.client.get_related_entities.side_effect = OpenCTIClientError("relations unavailable")

        status, matches = self.handler._enrich_ioc(ioc)

        self.assertFalse(status.is_failure())
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["related_entities"], [])
        self.assertEqual(matches[0]["related_error"], "relations unavailable")

    def test_no_match_replaces_success_and_removes_only_generated_tags(self):
        ioc = self.make_ioc(
            "example.com",
            tags="analyst-tag,opencti:match,opencti:label:old-label,opencti:manual",
        )
        ioc.ioc_enrichment = {
            "opencti": {
                "generated_tags": ["opencti:match", "opencti:label:old-label"],
                "match_count": 1,
                "matches": [{"value": "example.com"}],
            }
        }
        self.handler.client.search_ioc.return_value = {
            "indicators": {"edges": []},
            "stixCyberObservables": {"edges": []},
        }

        status, matches = self.handler._enrich_ioc(ioc)

        self.assertFalse(status.is_failure())
        self.assertEqual(matches, [])
        self.assertEqual(ioc.ioc_enrichment["opencti"]["status"], "no_match")
        self.assertEqual(ioc.ioc_enrichment["opencti"]["match_count"], 0)
        self.assertEqual(ioc.ioc_tags, "analyst-tag,opencti:manual")

    def test_api_error_preserves_last_success_and_report(self):
        ioc = self.make_ioc("example.com", tags="analyst-tag,opencti:match")
        ioc.ioc_enrichment = {
            "opencti": {
                "status": "match",
                "last_success_utc": "2026-01-01T00:00:00Z",
                "generated_tags": ["opencti:match"],
                "match_count": 1,
                "matches": [{"value": "example.com"}],
            }
        }
        ioc.custom_attributes = {
            "OpenCTI Report": {
                "HTML report": {"mandatory": False, "type": "html", "value": "last report"}
            }
        }
        self.handler.client.search_ioc.side_effect = OpenCTIClientError("connection failed")

        status, matches = self.handler._enrich_ioc(ioc)

        enrichment = ioc.ioc_enrichment["opencti"]
        self.assertTrue(status.is_failure())
        self.assertEqual(matches, [])
        self.assertEqual(enrichment["status"], "error")
        self.assertEqual(enrichment["last_success_utc"], "2026-01-01T00:00:00Z")
        self.assertEqual(enrichment["match_count"], 1)
        self.assertEqual(enrichment["error"], "connection failed")
        self.assertEqual(
            ioc.custom_attributes["OpenCTI Report"]["HTML report"]["value"],
            "last report",
        )
        self.assertIn("opencti:match", ioc.ioc_tags)

    def test_alert_deduplicates_requests_and_does_not_add_iocs(self):
        alert = Alert()
        alert.alert_id = 42
        first = self.make_ioc("EXAMPLE.COM.")
        second = self.make_ioc("example.com")
        alert.iocs.extend([first, second])
        self.handler.client.search_ioc.return_value = observable_payload("example.com")

        with app.app_context(), patch.object(db_session(), "commit"):
            status = self.handler.handle_alerts([alert])

        self.assertFalse(status.is_failure())
        self.assertEqual(self.handler.client.search_ioc.call_count, 1)
        self.assertEqual(len(alert.iocs), 2)
        self.assertEqual(first.ioc_enrichment["opencti"]["match_count"], 1)
        self.assertEqual(second.ioc_enrichment["opencti"]["match_count"], 1)

    def test_alert_limit_rejects_lookup_before_requests(self):
        alert = Alert()
        alert.alert_id = 43
        alert.iocs.extend([
            self.make_ioc(f"ioc-{index}.example")
            for index in range(101)
        ])

        status = self.handler.handle_alerts([alert])

        self.assertTrue(status.is_failure())
        self.handler.client.search_ioc.assert_not_called()


def db_session():
    from app import db

    return db.session
