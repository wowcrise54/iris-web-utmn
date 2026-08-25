from unittest import TestCase
from unittest.mock import MagicMock, patch

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

    def test_search_ioc_uses_cache_on_subsequent_calls(self):
        """Test that search_ioc caches results and returns cached data on repeat queries."""
        # First call - should query OpenCTI
        expected = {"indicators": {"edges": [{"node": {"id": "test"}}]}}
        self.client.query.return_value = expected

        result1 = self.client.search_ioc("8.8.8.8", first=10)
        self.assertEqual(result1, expected)
        self.assertEqual(self.client.query.call_count, 1)

        # Second call with same value - should use cache
        result2 = self.client.search_ioc("8.8.8.8", first=10)
        self.assertEqual(result2, expected)
        # query should not be called again (still 1 call)
        self.assertEqual(self.client.query.call_count, 1)

    def test_search_ioc_caches_after_fallback_queries(self):
        """Test that search_ioc caches results even when falling back to legacy queries."""
        # First call falls back to legacy query
        fallback_result = {"indicators": {"edges": []}}
        self.client.query.side_effect = [
            OpenCTIClientError("Cannot query field"),
            fallback_result,
        ]

        result1 = self.client.search_ioc("example.com", first=10)
        self.assertEqual(result1, fallback_result)
        self.assertEqual(self.client.query.call_count, 2)

        # Second call should use cache
        result2 = self.client.search_ioc("example.com", first=10)
        self.assertEqual(result2, fallback_result)
        # query should not be called again
        self.assertEqual(self.client.query.call_count, 2)

    def test_cache_stats_accessible(self):
        """Test that cache statistics are accessible."""
        self.client.query.return_value = {"indicators": {"edges": []}}

        # Make some queries
        self.client.search_ioc("8.8.8.8", first=10)
        self.client.search_ioc("8.8.8.8", first=10)  # cache hit
        self.client.search_ioc("1.1.1.1", first=10)  # cache miss then store

        stats = self.client.cache.get_stats()
        self.assertEqual(stats["size"], 2)
        self.assertGreaterEqual(stats["hits"], 1)

    def test_retry_on_transient_error(self):
        """Test that client retries on transient errors with exponential backoff"""
        # Create client with short retry delay for testing
        client = OpenCTIClient(
            url="http://test-opencti.local",
            token="test-token",
            timeout=5,
            retry_attempts=3,
            retry_delay=0.1
        )
        
        # Mock transient failures then success
        with patch.object(client, '_make_request') as mock_execute:
            mock_execute.side_effect = [
                OpenCTIClientError("Transient error"),
                OpenCTIClientError("Transient error"),
                {"data": {"indicator": {"id": "test"}}}
            ]
            
            result = client.search_ioc("8.8.8.8", first=10)
            
            # Should have retried twice (3 total attempts)
            self.assertEqual(mock_execute.call_count, 3)
            self.assertEqual(result["data"]["indicator"]["id"], "test")

    def test_no_retry_on_auth_error(self):
        """Test that client does NOT retry on authentication errors"""
        client = OpenCTIClient(
            url="http://test-opencti.local",
            token="test-token",
            timeout=5,
            retry_attempts=3,
            retry_delay=0.1
        )
        
        # Mock auth error - should not retry
        with patch.object(client, '_make_request') as mock_execute:
            mock_execute.side_effect = OpenCTIClientError("unauthorized")
            
            with self.assertRaises(OpenCTIClientError):
                client.search_ioc("8.8.8.8", first=10)
            
            # Should have only tried once, no retries
            self.assertEqual(mock_execute.call_count, 1)

    def test_no_retry_on_validation_error(self):
        """Test that client does NOT retry on validation errors"""
        client = OpenCTIClient(
            url="http://test-opencti.local",
            token="test-token",
            timeout=5,
            retry_attempts=3,
            retry_delay=0.1
        )
        
        # Mock validation error - should not retry
        with patch.object(client, '_make_request') as mock_execute:
            mock_execute.side_effect = OpenCTIClientError("validation error")
            
            with self.assertRaises(OpenCTIClientError):
                client.search_ioc("8.8.8.8", first=10)
            
            # Should have only tried once, no retries
            self.assertEqual(mock_execute.call_count, 1)
