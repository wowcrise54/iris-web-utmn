from unittest import TestCase
from unittest.mock import MagicMock

from iris_opencti_module.opencti_handler.opencti_client import OpenCTIClient
from iris_opencti_module.opencti_handler.opencti_client import OpenCTIClientError


class TestOpenCTIClient(TestCase):
    def setUp(self):
        self.client = OpenCTIClient("http://opencti:8080", "token")
        self.client.query = MagicMock()

    def test_opencti_7_search_query_is_used_first(self):
        expected = {"indicators": {"edges": []}}
        self.client.query.return_value = expected

        result = self.client.search_ioc("example.com", first=10)

        self.assertEqual(result, expected)
        query, variables = self.client.query.call_args.args
        self.assertEqual(query, self.client._SEARCH_QUERY)
        self.assertEqual(variables, {"search": "example.com", "first": 10})
        self.assertIn("objectLabel {\n              value", query)

    def test_search_falls_back_to_legacy_query_on_schema_error(self):
        expected = {"stixCyberObservables": {"edges": []}}
        self.client.query.side_effect = [
            OpenCTIClientError("Cannot query field value"),
            expected,
        ]

        result = self.client.search_ioc("example.com")

        self.assertEqual(result, expected)
        self.assertEqual(self.client.query.call_args_list[1].args[0], self.client._LEGACY_SEARCH_QUERY)

    def test_related_query_uses_bounded_object_id_variables(self):
        self.client.query.return_value = {"stixCoreRelationships": {"edges": []}}

        self.client.get_related_entities("indicator--1", first=20)

        query, variables = self.client.query.call_args.args
        self.assertEqual(query, self.client._RELATED_QUERY)
        self.assertEqual(
            variables,
            {"ids": ["indicator--1"], "objectId": "indicator--1", "first": 20},
        )
