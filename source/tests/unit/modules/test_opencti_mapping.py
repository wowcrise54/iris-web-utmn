from unittest import TestCase

from iris_opencti_module.opencti_handler.opencti_mapping import canonicalize_ioc_value
from iris_opencti_module.opencti_handler.opencti_mapping import extract_value_from_pattern
from iris_opencti_module.opencti_handler.opencti_mapping import infer_ioc_type
from iris_opencti_module.opencti_handler.opencti_mapping import is_exact_ioc_match
from iris_opencti_module.opencti_handler.opencti_mapping import normalize_related_entities
from iris_opencti_module.opencti_handler.opencti_mapping import normalize_search_results


class TestOpenCTIMapping(TestCase):
    def test_extract_value_from_ipv4_indicator_pattern(self):
        value, iris_type = extract_value_from_pattern("[ipv4-addr:value = '1.2.3.4']")

        self.assertEqual(value, "1.2.3.4")
        self.assertEqual(iris_type, "ip-dst")

    def test_extract_value_from_file_hash_indicator_pattern(self):
        sha256_value = "a" * 64
        value, iris_type = extract_value_from_pattern(f"[file:hashes.'SHA-256' = '{sha256_value}']")

        self.assertEqual(value, sha256_value)
        self.assertEqual(iris_type, "sha256")

    def test_infer_ioc_type_from_value(self):
        self.assertEqual(infer_ioc_type("https://example.com/a"), "url")
        self.assertEqual(infer_ioc_type("example.com"), "domain")
        self.assertEqual(infer_ioc_type("user@example.com"), "email")
        self.assertEqual(infer_ioc_type("1.2.3.4"), "ip-dst")
        self.assertEqual(infer_ioc_type("a" * 64), "sha256")

    def test_normalize_search_results_filters_score_and_deduplicates(self):
        payload = {
            "indicators": {
                "edges": [
                    {
                        "node": {
                            "id": "indicator--1",
                            "entity_type": "Indicator",
                            "name": "Known IPv4",
                            "pattern": "[ipv4-addr:value = '1.2.3.4']",
                            "x_opencti_score": 80,
                        }
                    },
                    {
                        "node": {
                            "id": "indicator--1",
                            "entity_type": "Indicator",
                            "name": "Known IPv4 duplicate",
                            "pattern": "[ipv4-addr:value = '1.2.3.4']",
                            "x_opencti_score": 80,
                        }
                    },
                    {
                        "node": {
                            "id": "indicator--2",
                            "entity_type": "Indicator",
                            "name": "Low score",
                            "pattern": "[domain-name:value = 'low.example']",
                            "x_opencti_score": 10,
                        }
                    },
                ]
            },
            "stixCyberObservables": {"edges": []},
        }

        matches = normalize_search_results(payload, min_score=50)

        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["value"], "1.2.3.4")
        self.assertEqual(matches[0]["iris_ioc_type"], "ip-dst")

    def test_canonicalize_exact_match_types(self):
        sha256_upper = "A" * 64

        self.assertEqual(canonicalize_ioc_value("2001:0db8::1", "ip-any"), "2001:db8::1")
        self.assertEqual(canonicalize_ioc_value("EXAMPLE.COM.", "domain"), "example.com")
        self.assertEqual(canonicalize_ioc_value("User@Example.COM", "email"), "user@example.com")
        self.assertEqual(
            canonicalize_ioc_value("HTTPS://EXAMPLE.COM/CaseSensitive", "url"),
            "https://example.com/CaseSensitive",
        )
        self.assertEqual(canonicalize_ioc_value(sha256_upper, "filename|sha256"), sha256_upper.lower())

    def test_exact_match_rejects_broad_search_result(self):
        exact_match = {
            "value": "example.com",
            "iris_ioc_type": "domain",
        }
        broad_match = {
            "value": "sub.example.com",
            "iris_ioc_type": "domain",
        }

        self.assertTrue(is_exact_ioc_match("EXAMPLE.COM.", exact_match, query_type="domain"))
        self.assertFalse(is_exact_ioc_match("example.com", broad_match, query_type="domain"))

    def test_normalize_search_results_applies_exact_filter(self):
        payload = {
            "indicators": {"edges": []},
            "stixCyberObservables": {
                "edges": [
                    {
                        "node": {
                            "id": "observable--exact",
                            "entity_type": "Domain-Name",
                            "observable_value": "example.com",
                            "x_opencti_score": 80,
                        }
                    },
                    {
                        "node": {
                            "id": "observable--broad",
                            "entity_type": "Domain-Name",
                            "observable_value": "sub.example.com",
                            "x_opencti_score": 90,
                        }
                    },
                ]
            },
        }

        matches = normalize_search_results(
            payload,
            min_score=0,
            query_value="EXAMPLE.COM.",
            query_type="domain",
        )

        self.assertEqual([match["id"] for match in matches], ["observable--exact"])

    def test_opencti_7_list_labels_markings_and_safe_entity_link(self):
        payload = {
            "indicators": {
                "edges": [{
                    "node": {
                        "id": "indicator--1",
                        "entity_type": "Indicator",
                        "pattern": "[domain-name:value = 'example.com']",
                        "objectLabel": [{"value": "phishing"}, {"value": "credential theft"}],
                        "objectMarking": [{"definition": "TLP:AMBER"}],
                        "externalReferences": {"edges": []},
                    }
                }]
            },
            "stixCyberObservables": {"edges": []},
        }

        matches = normalize_search_results(
            payload,
            query_value="example.com",
            query_type="domain",
            base_url="http://opencti:8080/graphql",
        )

        self.assertEqual(matches[0]["labels"], ["phishing", "credential theft"])
        self.assertEqual(matches[0]["markings"], ["TLP:AMBER"])
        self.assertEqual(
            matches[0]["opencti_url"],
            "http://opencti:8080/dashboard/id/indicator--1",
        )

    def test_related_entities_filter_dedupe_and_limit(self):
        relationship_edges = []
        for index in range(25):
            relationship_edges.append({
                "node": {
                    "relationship_type": "indicates",
                    "from": {"id": "indicator--1", "entity_type": "Indicator"},
                    "to": {
                        "id": f"malware--{index}",
                        "entity_type": "Malware",
                        "representative": {"main": f"Malware {index}"},
                    },
                }
            })
        relationship_edges.append(relationship_edges[0])
        relationship_edges.append({
            "node": {
                "relationship_type": "based-on",
                "from": {"id": "indicator--1", "entity_type": "Indicator"},
                "to": {
                    "id": "file--1",
                    "entity_type": "StixFile",
                    "representative": {"main": "ignored"},
                },
            }
        })
        payload = {
            "stixCoreRelationships": {"edges": relationship_edges},
            "containers": {
                "edges": [{
                    "node": {
                        "id": "report--1",
                        "entity_type": "Report",
                        "representative": {"main": "Report one"},
                    }
                }]
            },
        }

        related = normalize_related_entities(
            payload,
            object_id="indicator--1",
            base_url="http://opencti:8080",
            limit=20,
        )

        self.assertEqual(len(related), 20)
        self.assertEqual(related[0]["name"], "Malware 0")
        self.assertTrue(all(entity["entity_type"] in {"Malware", "Report"} for entity in related))
