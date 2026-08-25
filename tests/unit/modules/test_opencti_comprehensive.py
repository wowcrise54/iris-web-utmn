#!/usr/bin/env python3
"""
Comprehensive integration tests for OpenCTI plugin enhancements
Tests all implemented features with correct API signatures
"""

import pytest
import sys
import time
from unittest.mock import Mock, patch, MagicMock

sys.path.insert(0, 'source')

from iris_opencti_module.opencti_handler.cache import OpenCTICache
from iris_opencti_module.opencti_handler.auto_enrich import should_auto_enrich, trigger_auto_enrichment
from iris_opencti_module.opencti_handler.batch_processor import BatchProcessor
from iris_opencti_module.opencti_handler.rules_engine import RulesEngine, EnrichmentRule
from iris_opencti_module.opencti_handler.filters import (
    EntityFilter, LabelFilter, DateRangeFilter, ScoreFilter, 
    ConfidenceFilter, AndFilter, OrFilter, NotFilter, FilterBuilder
)
from iris_opencti_module.opencti_handler.history import EnrichmentHistory
from iris_opencti_module.opencti_handler.metrics import MetricsCollector, EnrichmentMetrics


class TestRetryLogic:
    """Tests for retry logic in OpenCTIClient"""
    
    def test_retry_parameters_exist(self):
        """Test that retry parameters are accepted"""
        from iris_opencti_module.opencti_handler.opencti_client import OpenCTIClient
        
        client = OpenCTIClient(
            url="http://test.local",
            token="test",
            retry_attempts=3,
            retry_delay=0.1
        )
        
        assert client.retry_attempts == 3
        assert client.retry_delay == 0.1


class TestCaching:
    """Tests for LRU caching"""
    
    def test_cache_basic_operations(self):
        """Test basic cache operations"""
        cache = OpenCTICache(max_size=100, ttl=300)
        
        cache.set("key1", {"data": "value1"})
        assert cache.get("key1") == {"data": "value1"}
        
        cache.delete("key1")
        assert cache.get("key1") is None
    
    def test_cache_ttl_expiration(self):
        """Test cache TTL expiration"""
        cache = OpenCTICache(max_size=100, ttl=0.1)
        
        cache.set("key1", {"data": "value1"})
        assert cache.get("key1") is not None
        
        time.sleep(0.2)
        assert cache.get("key1") is None
    
    def test_cache_lru_eviction(self):
        """Test LRU eviction when cache is full"""
        cache = OpenCTICache(max_size=3, ttl=300)
        
        cache.set("key1", "value1")
        cache.set("key2", "value2")
        cache.set("key3", "value3")
        
        # Access key1 to make it recently used
        cache.get("key1")
        
        # Add new key, should evict key2 (least recently used)
        cache.set("key4", "value4")
        
        assert cache.get("key1") is not None
        assert cache.get("key2") is None
        assert cache.get("key3") is not None
        assert cache.get("key4") is not None
    
    def test_cache_statistics(self):
        """Test cache statistics tracking"""
        cache = OpenCTICache(max_size=100, ttl=300)
        
        cache.set("key1", "value1")
        cache.get("key1")  # Hit
        cache.get("key2")  # Miss
        
        stats = cache.get_stats()
        
        assert stats["hits"] == 1
        assert stats["misses"] == 1
        assert stats["size"] == 1
        assert stats["hit_rate"] == 0.5


class TestAutoEnrichment:
    """Tests for auto-enrichment on alert creation"""
    
    def test_auto_enrich_disabled_by_default(self):
        """Test that auto-enrichment is disabled by default"""
        config = {"opencti_auto_enrich_alerts": False}
        assert should_auto_enrich(config) is False
    
    def test_auto_enrich_enabled(self):
        """Test auto-enrichment when enabled"""
        config = {"opencti_auto_enrich_alerts": True}
        alert = Mock(iocs=[Mock(ioc_value="8.8.8.8")])
        
        assert should_auto_enrich(config, alert) is True
    
    def test_auto_enrich_skips_empty_alerts(self):
        """Test auto-enrichment skips alerts without IOCs"""
        config = {"opencti_auto_enrich_alerts": True}
        alert = Mock(iocs=[])
        
        assert should_auto_enrich(config, alert) is False
    
    def test_auto_enrich_min_iocs(self):
        """Test auto-enrichment respects minimum IOC threshold"""
        config = {
            "opencti_auto_enrich_alerts": True,
            "opencti_auto_enrich_min_iocs": 3
        }
        alert = Mock(iocs=[Mock(ioc_value="8.8.8.8"), Mock(ioc_value="1.1.1.1")])
        
        assert should_auto_enrich(config, alert) is False
        
        alert.iocs = [Mock(ioc_value="8.8.8.8") for _ in range(3)]
        assert should_auto_enrich(config, alert) is True


class TestBatchProcessing:
    """Tests for batch IOC processing"""
    
    def test_batch_size_limits(self):
        """Test batch size limits"""
        processor = BatchProcessor(max_batch_size=10, rate_limit=10)
        
        result = processor.add_batch([f"ioc{i}" for i in range(10)])
        assert result["accepted"] is True
        
        result = processor.add_batch([f"ioc{i}" for i in range(11)])
        assert result["accepted"] is False
    
    def test_fifo_processing_order(self):
        """Test FIFO processing order"""
        processor = BatchProcessor(max_batch_size=5, rate_limit=10)
        
        processor.add_batch(["ioc1", "ioc2"])
        processor.add_batch(["ioc3", "ioc4"])
        
        assert processor.get_next_batch() == ["ioc1", "ioc2"]
        assert processor.get_next_batch() == ["ioc3", "ioc4"]
    
    def test_empty_batch_rejection(self):
        """Test empty batch rejection"""
        processor = BatchProcessor(max_batch_size=10, rate_limit=10)
        
        result = processor.add_batch([])
        assert result["accepted"] is False
    
    def test_single_ioc_batch(self):
        """Test single IOC batch"""
        processor = BatchProcessor(max_batch_size=10, rate_limit=10)
        
        result = processor.add_batch(["ioc1"])
        assert result["accepted"] is True
        assert processor.get_next_batch() == ["ioc1"]


class TestRulesEngine:
    """Tests for rules engine"""
    
    def test_confidence_filtering(self):
        """Test filtering by confidence"""
        engine = RulesEngine(min_confidence=50)
        
        matches = [
            {"confidence": 30, "name": "Low"},
            {"confidence": 70, "name": "High"},
            {"confidence": 80, "name": "Very High"}
        ]
        
        filtered = engine.filter_matches(matches)
        assert len(filtered) == 2
        assert all(m["confidence"] >= 50 for m in filtered)
    
    def test_label_filtering(self):
        """Test filtering by labels"""
        engine = RulesEngine(required_labels=["malicious"])
        
        matches = [
            {"labels": ["suspicious"], "name": "Not malicious"},
            {"labels": ["malicious"], "name": "Malicious"},
            {"labels": ["malicious", "phishing"], "name": "Both"}
        ]
        
        filtered = engine.filter_matches(matches)
        assert len(filtered) == 2
        assert all("malicious" in m["labels"] for m in filtered)
    
    def test_safe_ioc_detection(self):
        """Test safe IOC pattern detection"""
        engine = RulesEngine()
        
        assert engine.should_enrich_ioc("8.8.8.8", "ip-addr") is False
        assert engine.should_enrich_ioc("1.1.1.1", "ip-addr") is False
        assert engine.should_enrich_ioc("localhost", "domain") is False
        assert engine.should_enrich_ioc("127.0.0.1", "ip-addr") is False
        
        assert engine.should_enrich_ioc("185.220.101.1", "ip-addr") is True


class TestAdvancedFiltering:
    """Tests for advanced filtering with correct API"""
    
    def test_entity_filter(self):
        """Test entity type filtering"""
        filter_obj = EntityFilter(entity_types=["indicator", "malware"])
        
        entities = [
            {"entity_type": "indicator", "name": "Ind1"},
            {"entity_type": "malware", "name": "Mal1"},
            {"entity_type": "report", "name": "Rep1"}
        ]
        
        filtered = [e for e in entities if filter_obj.matches(e)]
        assert len(filtered) == 2
        assert all(e["entity_type"] in ["indicator", "malware"] for e in filtered)
    
    def test_label_filter_require_all(self):
        """Test label filter with require_all"""
        filter_obj = LabelFilter(labels=["malicious", "phishing"], require_all=True)
        
        matches = [
            {"labels": ["malicious", "phishing"], "name": "Both"},
            {"labels": ["malicious"], "name": "One"},
            {"labels": ["suspicious"], "name": "None"}
        ]
        
        filtered = [m for m in matches if filter_obj.matches(m)]
        assert len(filtered) == 1
        assert filtered[0]["name"] == "Both"
    
    def test_score_filter(self):
        """Test score filtering"""
        filter_obj = ScoreFilter(min_score=60, max_score=80)
        
        matches = [
            {"x_opencti_score": 30, "name": "Low"},
            {"x_opencti_score": 70, "name": "Medium"},
            {"x_opencti_score": 90, "name": "High"}
        ]
        
        filtered = [m for m in matches if filter_obj.matches(m)]
        assert len(filtered) == 1
        assert filtered[0]["name"] == "Medium"
    
    def test_combined_filters(self):
        """Test combined filters using operator overloading"""
        entity_filter = EntityFilter(entity_types=["indicator"])
        score_filter = ScoreFilter(min_score=60)
        label_filter = LabelFilter(labels=["malicious"], require_all=True)
        
        # Combine with AND
        combined = entity_filter & score_filter & label_filter
        
        matches = [
            {"entity_type": "indicator", "x_opencti_score": 70, "labels": ["malicious"], "name": "Match"},
            {"entity_type": "indicator", "x_opencti_score": 70, "labels": ["suspicious"], "name": "No label"},
            {"entity_type": "indicator", "x_opencti_score": 30, "labels": ["malicious"], "name": "Low score"},
            {"entity_type": "malware", "x_opencti_score": 70, "labels": ["malicious"], "name": "Wrong type"}
        ]
        
        filtered = [m for m in matches if combined.matches(m)]
        assert len(filtered) == 1
        assert filtered[0]["name"] == "Match"


class TestHistoryAndDeduplication:
    """Tests for enrichment history and deduplication"""
    
    def test_history_storage(self):
        """Test history storage and retrieval"""
        history = EnrichmentHistory(history_ttl_hours=24, max_history_size=100)
        
        history.store("8.8.8.8", "ip-addr", "match", {"data": "result"})
        
        record = history.get_history("8.8.8.8", "ip-addr")
        assert record is not None
        assert record["status"] == "match"
    
    def test_deduplication(self):
        """Test deduplication by canonical value"""
        history = EnrichmentHistory(history_ttl_hours=24, max_history_size=100)
        
        history.store("8.8.8.8", "ip-addr", "match", {"data": "result"})
        
        # Should skip enrichment for same value
        should_skip = history.should_skip_enrichment("8.8.8.8", "ip-addr")
        assert should_skip is True
        
        # Different type should not skip
        should_skip = history.should_skip_enrichment("8.8.8.8", "domain")
        assert should_skip is False
    
    def test_case_insensitive_dedup(self):
        """Test case-insensitive deduplication for domains"""
        history = EnrichmentHistory(history_ttl_hours=24, max_history_size=100)
        
        history.store("EXAMPLE.COM", "domain", "match", {"data": "result"})
        
        should_skip = history.should_skip_enrichment("example.com", "domain")
        assert should_skip is True
    
    def test_history_ttl_expiration(self):
        """Test history TTL expiration"""
        history = EnrichmentHistory(history_ttl_hours=0.001, max_history_size=100)  # ~3.6 seconds
        
        history.store("8.8.8.8", "ip-addr", "match", {"data": "result"})
        
        time.sleep(4)
        
        should_skip = history.should_skip_enrichment("8.8.8.8", "ip-addr")
        assert should_skip is False


class TestMetrics:
    """Tests for metrics collection"""
    
    def test_metrics_initialization(self):
        """Test metrics collector initialization"""
        metrics = MetricsCollector()
        
        assert metrics is not None
    
    def test_enrichment_metrics(self):
        """Test enrichment metrics tracking"""
        metrics = MetricsCollector()
        
        metrics.record_enrichment(success=True, duration_seconds=0.5, ioc_count=1, matched=True)
        metrics.record_enrichment(success=False, duration_seconds=0.3, ioc_count=1, matched=False)
        
        enrichment_metrics = metrics.get_enrichment_metrics()
        
        assert enrichment_metrics.total_enrichments == 2
        assert enrichment_metrics.successful_enrichments == 1
        assert enrichment_metrics.failed_enrichments == 1
    
    def test_cache_metrics(self):
        """Test cache metrics tracking"""
        metrics = MetricsCollector()
        
        metrics.record_cache_hit()
        metrics.record_cache_hit()
        metrics.record_cache_miss()
        
        cache_metrics = metrics.get_cache_metrics()
        
        assert cache_metrics.hits == 2
        assert cache_metrics.misses == 1
        assert cache_metrics.hit_rate == 2/3
    
    def test_enrichment_metrics_dataclass(self):
        """Test EnrichmentMetrics dataclass"""
        enrichment = EnrichmentMetrics()
        
        enrichment.record_enrichment(success=True, duration_seconds=0.5, ioc_count=2, matched=True)
        enrichment.record_enrichment(success=True, duration_seconds=0.3, ioc_count=1, matched=False)
        
        assert enrichment.total_enrichments == 2
        assert enrichment.successful_enrichments == 2
        assert enrichment.total_iocs_processed == 3
        assert enrichment.total_matches_found == 1


class TestIntegration:
    """Integration tests for combined features"""
    
    def test_rules_with_filters(self):
        """Test rules engine combined with filters"""
        rules_engine = RulesEngine(min_confidence=50)
        
        entity_filter = EntityFilter(entity_types=["indicator"])
        score_filter = ScoreFilter(min_score=60)
        label_filter = LabelFilter(labels=["malicious"], require_all=True)
        
        combined_filter = entity_filter & score_filter & label_filter
        
        matches = [
            {"entity_type": "indicator", "x_opencti_score": 70, "confidence": 80, "labels": ["malicious"], "name": "Match"},
            {"entity_type": "indicator", "x_opencti_score": 70, "confidence": 80, "labels": ["suspicious"], "name": "No label"},
            {"entity_type": "indicator", "x_opencti_score": 30, "confidence": 80, "labels": ["malicious"], "name": "Low score"},
            {"entity_type": "malware", "x_opencti_score": 70, "confidence": 80, "labels": ["malicious"], "name": "Wrong type"}
        ]
        
        # Apply filter first
        filtered = [m for m in matches if combined_filter.matches(m)]
        
        # Then apply rules
        final = rules_engine.filter_matches(filtered)
        
        assert len(final) == 1
        assert final[0]["name"] == "Match"
    
    def test_cache_with_retry(self):
        """Test cache works with retry logic"""
        from iris_opencti_module.opencti_handler.opencti_client import OpenCTIClient, OpenCTIClientError
        
        client = OpenCTIClient(
            url="http://test.local",
            token="test",
            retry_attempts=3,
            retry_delay=0.01
        )
        
        call_count = 0
        
        def mock_request(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise OpenCTIClientError("Transient error")
            return {"data": {"indicator": {"id": "test"}}}
        
        with patch.object(client, '_make_request', side_effect=mock_request):
            # First call - will retry, then cache
            result1 = client._execute_query("query { test }")
            assert call_count == 2
            
            # Second call - should use cache
            call_count_before = call_count
            result2 = client._execute_query("query { test }")
            assert call_count == call_count_before  # No additional calls


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
