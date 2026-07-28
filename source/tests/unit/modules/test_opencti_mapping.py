from unittest import TestCase

from iris_opencti_module.opencti_handler.opencti_mapping import extract_value_from_pattern
from iris_opencti_module.opencti_handler.opencti_mapping import infer_ioc_type
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
