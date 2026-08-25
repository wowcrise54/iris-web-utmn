#!/usr/bin/env python3
"""
Tests for OpenCTI metrics collection module.

These tests verify the metrics collection, aggregation, and reporting
functionality for the OpenCTI plugin.
"""
import pytest
import time
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock

from iris_opencti_module.opencti_handler.metrics import (
    MetricType,
    MetricPoint,
    EnrichmentMetrics,
    CacheMetrics,
    APIMetrics,
    MetricsCollector,
    MetricsContextManager,
    get_metrics_collector,
    record_enrichment,
    record_cache_hit,
    record_cache_miss,
    record_api_call,
)


class TestMetricPoint:
    """Tests for MetricPoint dataclass."""
    
    def test_metric_point_creation(self):
        """Test basic MetricPoint creation."""
        point = MetricPoint(
            name="test_metric",
            value=42.0,
            timestamp=datetime.utcnow(),
            tags={"env": "test"},
            metric_type=MetricType.COUNTER
        )
        
        assert point.name == "test_metric"
        assert point.value == 42.0
        assert point.tags["env"] == "test"
        assert point.metric_type == MetricType.COUNTER
    
    def test_metric_point_default_tags(self):
        """Test that MetricPoint has empty dict for tags by default."""
        point = MetricPoint(
            name="test",
            value=1.0,
            timestamp=datetime.utcnow()
        )
        assert point.tags == {}


class TestEnrichmentMetrics:
    """Tests for EnrichmentMetrics dataclass."""
    
    def test_initial_state(self):
        """Test initial state of enrichment metrics."""
        metrics = EnrichmentMetrics()
        
        assert metrics.total_enrichments == 0
        assert metrics.successful_enrichments == 0
        assert metrics.failed_enrichments == 0
        assert metrics.skipped_enrichments == 0
        assert metrics.total_iocs_processed == 0
        assert metrics.total_matches_found == 0
        assert metrics.total_errors == 0
        assert metrics.alerts_enriched == 0
        assert metrics.min_enrichment_time_seconds == float('inf')
    
    def test_record_enrichment_success(self):
        """Test recording a successful enrichment."""
        metrics = EnrichmentMetrics()
        
        metrics.record_enrichment(
            success=True,
            duration_seconds=1.5,
            ioc_count=5,
            matched=True
        )
        
        assert metrics.total_enrichments == 1
        assert metrics.successful_enrichments == 1
        assert metrics.total_iocs_processed == 5
        assert metrics.total_matches_found == 1
        assert metrics.enrichment_times[0] == 1.5
        assert metrics.min_enrichment_time_seconds == 1.5
        assert metrics.max_enrichment_time_seconds == 1.5
    
    def test_record_enrichment_failure(self):
        """Test recording a failed enrichment."""
        metrics = EnrichmentMetrics()
        
        metrics.record_enrichment(
            success=False,
            duration_seconds=2.0,
            ioc_count=1
        )
        
        assert metrics.failed_enrichments == 1
        assert metrics.total_errors == 1
    
    def test_record_enrichment_skipped(self):
        """Test recording a skipped enrichment."""
        metrics = EnrichmentMetrics()
        
        metrics.record_enrichment(
            success=True,
            duration_seconds=0.1,
            skipped=True
        )
        
        assert metrics.skipped_enrichments == 1
        assert metrics.total_enrichments == 0  # Should not count
    
    def test_avg_enrichment_time(self):
        """Test average enrichment time calculation."""
        metrics = EnrichmentMetrics()
        
        metrics.record_enrichment(success=True, duration_seconds=1.0)
        metrics.record_enrichment(success=True, duration_seconds=2.0)
        metrics.record_enrichment(success=True, duration_seconds=3.0)
        
        assert metrics.avg_enrichment_time_seconds == 2.0
    
    def test_success_rate(self):
        """Test success rate calculation."""
        metrics = EnrichmentMetrics()
        
        # 8 success, 2 failures = 80% success rate
        for _ in range(8):
            metrics.record_enrichment(success=True, duration_seconds=1.0)
        for _ in range(2):
            metrics.record_enrichment(success=False, duration_seconds=1.0)
        
        assert metrics.success_rate == 80.0
    
    def test_error_rate(self):
        """Test error rate calculation."""
        metrics = EnrichmentMetrics()
        
        # 3 errors out of 10 = 30% error rate
        for _ in range(7):
            metrics.record_enrichment(success=True, duration_seconds=1.0)
        for _ in range(3):
            metrics.record_enrichment(success=False, duration_seconds=1.0)
        
        assert metrics.error_rate == 30.0
    
    def test_record_alert_enrichment(self):
        """Test alert enrichment recording."""
        metrics = EnrichmentMetrics()
        
        metrics.total_iocs_processed = 50
        metrics.record_alert_enrichment(ioc_count=10)
        
        assert metrics.alerts_enriched == 1
        assert metrics.avg_iocs_per_alert == 50.0
    
    def test_to_dict(self):
        """Test conversion to dictionary."""
        metrics = EnrichmentMetrics()
        
        metrics.record_enrichment(success=True, duration_seconds=1.5, ioc_count=5, matched=True)
        metrics.record_enrichment(success=False, duration_seconds=2.0, ioc_count=1)
        metrics.record_enrichment(success=True, duration_seconds=1.0, skipped=True)
        metrics.record_alert_enrichment(ioc_count=6)
        
        result = metrics.to_dict()
        
        assert result["total_enrichments"] == 2
        assert result["successful_enrichments"] == 1
        assert result["failed_enrichments"] == 1
        assert result["skipped_enrichments"] == 1
        assert result["total_iocs_processed"] == 6  # 5 + 1
        assert result["total_matches_found"] == 1
        assert result["alerts_enriched"] == 1
        assert "avg_enrichment_time_seconds" in result
        assert "success_rate_percent" in result
        assert "error_rate_percent" in result
    
    def test_empty_success_rate(self):
        """Test success rate when no enrichments recorded."""
        metrics = EnrichmentMetrics()
        assert metrics.success_rate == 100.0  # Default to 100% when no data
    
    def test_empty_error_rate(self):
        """Test error rate when no enrichments recorded."""
        metrics = EnrichmentMetrics()
        assert metrics.error_rate == 0.0  # Default to 0% when no data


class TestCacheMetrics:
    """Tests for CacheMetrics dataclass."""
    
    def test_initial_state(self):
        """Test initial state of cache metrics."""
        metrics = CacheMetrics()
        
        assert metrics.cache_hits == 0
        assert metrics.cache_misses == 0
        assert metrics.cache_evictions == 0
        assert metrics.cache_clears == 0
        assert metrics.current_cache_size == 0
        assert metrics.max_cache_size == 1000
        assert metrics.cache_ttl_seconds == 300
    
    def test_record_hit(self):
        """Test recording cache hits."""
        metrics = CacheMetrics()
        
        metrics.record_hit()
        metrics.record_hit()
        metrics.record_hit()
        
        assert metrics.cache_hits == 3
    
    def test_record_miss(self):
        """Test recording cache misses."""
        metrics = CacheMetrics()
        
        metrics.record_miss()
        metrics.record_miss()
        
        assert metrics.cache_misses == 2
    
    def test_record_eviction(self):
        """Test recording cache evictions."""
        metrics = CacheMetrics()
        
        metrics.record_eviction()
        
        assert metrics.cache_evictions == 1
    
    def test_record_clear(self):
        """Test recording cache clears."""
        metrics = CacheMetrics()
        
        metrics.record_clear()
        metrics.record_clear()
        
        assert metrics.cache_clears == 2
    
    def test_hit_rate(self):
        """Test cache hit rate calculation."""
        metrics = CacheMetrics()
        
        # 75 hits, 25 misses = 75% hit rate
        for _ in range(75):
            metrics.record_hit()
        for _ in range(25):
            metrics.record_miss()
        
        assert metrics.hit_rate == 75.0
    
    def test_miss_rate(self):
        """Test cache miss rate calculation."""
        metrics = CacheMetrics()
        
        # 40 hits, 60 misses = 60% miss rate
        for _ in range(40):
            metrics.record_hit()
        for _ in range(60):
            metrics.record_miss()
        
        assert metrics.miss_rate == 60.0
    
    def test_hit_rate_empty(self):
        """Test hit rate when no cache operations."""
        metrics = CacheMetrics()
        assert metrics.hit_rate == 0.0
    
    def test_miss_rate_empty(self):
        """Test miss rate when no cache operations."""
        metrics = CacheMetrics()
        assert metrics.miss_rate == 100.0
    
    def test_to_dict(self):
        """Test conversion to dictionary."""
        metrics = CacheMetrics()
        
        metrics.record_hit()
        metrics.record_hit()
        metrics.record_miss()
        metrics.record_eviction()
        metrics.record_clear()
        metrics.current_cache_size = 500
        
        result = metrics.to_dict()
        
        assert result["cache_hits"] == 2
        assert result["cache_misses"] == 1
        assert result["cache_evictions"] == 1
        assert result["cache_clears"] == 1
        assert result["current_cache_size"] == 500
        assert result["max_cache_size"] == 1000
        assert result["hit_rate_percent"] == 66.67
        assert "utilization_percent" in result


class TestAPIMetrics:
    """Tests for APIMetrics dataclass."""
    
    def test_initial_state(self):
        """Test initial state of API metrics."""
        metrics = APIMetrics()
        
        assert metrics.api_calls_total == 0
        assert metrics.api_calls_successful == 0
        assert metrics.api_calls_failed == 0
        assert metrics.api_timeout_errors == 0
        assert metrics.api_rate_limit_hits == 0
        assert metrics.endpoint_stats == {}
    
    def test_record_successful_api_call(self):
        """Test recording a successful API call."""
        metrics = APIMetrics()
        
        metrics.record_api_call(
            endpoint="/api/indicator",
            success=True,
            duration_seconds=0.5
        )
        
        assert metrics.api_calls_total == 1
        assert metrics.api_calls_successful == 1
        assert metrics.total_api_time_seconds == 0.5
        assert metrics.endpoint_stats["/api/indicator"]["total"] == 1
        assert metrics.endpoint_stats["/api/indicator"]["success"] == 1
    
    def test_record_failed_api_call(self):
        """Test recording a failed API call."""
        metrics = APIMetrics()
        
        metrics.record_api_call(
            endpoint="/api/indicator",
            success=False,
            duration_seconds=1.0,
            is_timeout=True
        )
        
        assert metrics.api_calls_failed == 1
        assert metrics.api_timeout_errors == 1
    
    def test_record_rate_limited_call(self):
        """Test recording a rate-limited API call."""
        metrics = APIMetrics()
        
        metrics.record_api_call(
            endpoint="/api/indicator",
            success=False,
            is_rate_limited=True
        )
        
        assert metrics.api_rate_limit_hits == 1
    
    def test_avg_api_time(self):
        """Test average API time calculation."""
        metrics = APIMetrics()
        
        metrics.record_api_call(success=True, duration_seconds=0.5)
        metrics.record_api_call(success=True, duration_seconds=1.0)
        metrics.record_api_call(success=True, duration_seconds=1.5)
        
        assert metrics.avg_api_time_seconds == 1.0
    
    def test_api_success_rate(self):
        """Test API success rate calculation."""
        metrics = APIMetrics()
        
        for _ in range(8):
            metrics.record_api_call(success=True)
        for _ in range(2):
            metrics.record_api_call(success=False)
        
        assert metrics.api_success_rate == 80.0
    
    def test_api_success_rate_empty(self):
        """Test API success rate when no calls."""
        metrics = APIMetrics()
        assert metrics.api_success_rate == 100.0
    
    def test_to_dict(self):
        """Test conversion to dictionary."""
        metrics = APIMetrics()
        
        metrics.record_api_call(endpoint="/api/test", success=True, duration_seconds=0.5)
        metrics.record_api_call(endpoint="/api/test", success=False, is_timeout=True)
        
        result = metrics.to_dict()
        
        assert result["api_calls_total"] == 2
        assert result["api_calls_successful"] == 1
        assert result["api_calls_failed"] == 1
        assert result["api_timeout_errors"] == 1
        assert "/api/test" in result["endpoint_stats"]


class TestMetricsCollector:
    """Tests for MetricsCollector singleton."""
    
    def test_singleton_pattern(self):
        """Test that MetricsCollector is a singleton."""
        collector1 = MetricsCollector()
        collector2 = MetricsCollector()
        
        assert collector1 is collector2
    
    def test_get_metrics_collector(self):
        """Test get_metrics_collector function."""
        collector = get_metrics_collector()
        assert isinstance(collector, MetricsCollector)
    
    def test_record_enrichment(self):
        """Test recording enrichment through collector."""
        collector = MetricsCollector()
        collector.reset()  # Start fresh
        
        collector.record_enrichment(success=True, duration_seconds=1.0, ioc_count=5)
        
        assert collector.enrichment.total_enrichments == 1
        assert collector.enrichment.successful_enrichments == 1
    
    def test_record_cache_operations(self):
        """Test recording cache operations."""
        collector = MetricsCollector()
        collector.reset()
        
        collector.record_cache_hit()
        collector.record_cache_hit()
        collector.record_cache_miss()
        
        assert collector.cache.cache_hits == 2
        assert collector.cache.cache_misses == 1
    
    def test_update_cache_size(self):
        """Test updating cache size."""
        collector = MetricsCollector()
        collector.reset()
        
        collector.update_cache_size(size=500, max_size=1000, ttl=600)
        
        assert collector.cache.current_cache_size == 500
        assert collector.cache.max_cache_size == 1000
        assert collector.cache.cache_ttl_seconds == 600
    
    def test_record_api_call(self):
        """Test recording API calls through collector."""
        collector = MetricsCollector()
        collector.reset()
        
        collector.record_api_call(endpoint="/test", success=True, duration_seconds=0.5)
        
        assert collector.api.api_calls_total == 1
    
    def test_get_metrics_all(self):
        """Test getting all metrics."""
        collector = MetricsCollector()
        collector.reset()
        
        collector.record_enrichment(success=True, duration_seconds=1.0)
        collector.record_cache_hit()
        collector.record_api_call(success=True)
        
        metrics = collector.get_metrics(time_range="all")
        
        assert "timestamp" in metrics
        assert "enrichment" in metrics
        assert "cache" in metrics
        assert "api" in metrics
    
    def test_get_summary(self):
        """Test getting metrics summary."""
        collector = MetricsCollector()
        collector.reset()
        
        collector.record_enrichment(success=True, duration_seconds=0.5, ioc_count=10)
        collector.record_alert_enrichment(ioc_count=10)
        collector.record_cache_hit()
        collector.update_cache_size(size=100)
        
        summary = collector.get_summary()
        
        assert "timestamp" in summary
        assert "kpi" in summary
        assert "enrichment" in summary
        assert "cache" in summary
        assert "api" in summary
        
        # Check KPI values
        assert summary["kpi"]["total_enrichments"] == 1
        assert summary["kpi"]["alerts_enriched"] == 1
        assert summary["kpi"]["total_iocs_processed"] == 10
    
    def test_reset(self):
        """Test resetting metrics."""
        collector = MetricsCollector()
        
        collector.record_enrichment(success=True, duration_seconds=1.0)
        collector.reset()
        
        assert collector.enrichment.total_enrichments == 0
        assert collector.cache.cache_hits == 0
        assert collector.api.api_calls_total == 0


class TestMetricsContextManager:
    """Tests for MetricsContextManager."""
    
    def test_context_manager_success(self):
        """Test context manager on successful operation."""
        collector = MetricsCollector()
        collector.reset()
        
        with MetricsContextManager(collector, "enrichment"):
            time.sleep(0.1)
        
        assert collector.enrichment.successful_enrichments == 1
    
    def test_context_manager_failure(self):
        """Test context manager on failed operation."""
        collector = MetricsCollector()
        collector.reset()
        
        try:
            with MetricsContextManager(collector, "enrichment"):
                raise Exception("Test error")
        except Exception:
            pass
        
        assert collector.enrichment.failed_enrichments == 1
    
    def test_context_manager_api_call(self):
        """Test context manager for API calls."""
        collector = MetricsCollector()
        collector.reset()
        
        with MetricsContextManager(collector, "api_call"):
            time.sleep(0.05)
        
        assert collector.api.api_calls_successful == 1
    
    def test_context_manager_timeout(self):
        """Test context manager with timeout error."""
        collector = MetricsCollector()
        collector.reset()
        
        try:
            with MetricsContextManager(collector, "api_call"):
                raise TimeoutError("Timeout")
        except TimeoutError:
            pass
        
        assert collector.api.api_timeout_errors == 1


class TestConvenienceFunctions:
    """Tests for convenience functions."""
    
    def test_record_enrichment_function(self):
        """Test record_enrichment convenience function."""
        with patch('iris_opencti_module.opencti_handler.metrics.metrics') as mock_metrics:
            record_enrichment(success=True, duration_seconds=1.0, ioc_count=5)
            mock_metrics.record_enrichment.assert_called_once_with(
                success=True,
                duration_seconds=1.0,
                ioc_count=5,
                matched=False,
                skipped=False
            )
    
    def test_record_cache_hit_function(self):
        """Test record_cache_hit convenience function."""
        with patch('iris_opencti_module.opencti_handler.metrics.metrics') as mock_metrics:
            record_cache_hit()
            mock_metrics.record_cache_hit.assert_called_once()
    
    def test_record_cache_miss_function(self):
        """Test record_cache_miss convenience function."""
        with patch('iris_opencti_module.opencti_handler.metrics.metrics') as mock_metrics:
            record_cache_miss()
            mock_metrics.record_cache_miss.assert_called_once()
    
    def test_record_api_call_function(self):
        """Test record_api_call convenience function."""
        with patch('iris_opencti_module.opencti_handler.metrics.metrics') as mock_metrics:
            record_api_call(endpoint="/test", success=True, duration_seconds=0.5)
            mock_metrics.record_api_call.assert_called_once_with(
                endpoint="/test",
                success=True,
                duration_seconds=0.5,
                is_timeout=False
            )


class TestIntegrationScenarios:
    """Integration-style tests for common scenarios."""
    
    def test_full_enrichment_workflow(self):
        """Test complete enrichment workflow with metrics."""
        collector = MetricsCollector()
        collector.reset()
        
        # Simulate enriching an alert with multiple IOCs
        # We want 70% success rate = 7 successful, 3 failed out of 10
        # Use pattern: fail every 3rd starting from i=7 (i.e., i=7,8,9 fail)
        # Actually simpler: first 7 succeed, last 3 fail
        for i in range(10):
            success = i < 7  # First 7 succeed, last 3 fail = 70% success rate
            matched = success and i % 2 == 0
            
            collector.record_enrichment(
                success=success,
                duration_seconds=0.5 + (i * 0.1),
                ioc_count=1,
                matched=matched
            )
        
        collector.record_alert_enrichment(ioc_count=10)
        
        summary = collector.get_summary()
        
        assert summary["kpi"]["total_enrichments"] == 10
        assert summary["kpi"]["alerts_enriched"] == 1
        assert summary["kpi"]["total_iocs_processed"] == 10
        # 7 successful out of 10 = 70%
        assert summary["enrichment"]["success_rate_percent"] == 70.0
    
    def test_cache_efficiency_scenario(self):
        """Test scenario with good cache efficiency."""
        collector = MetricsCollector()
        collector.reset()
        
        # Simulate repeated queries with good cache hit rate
        for i in range(100):
            if i % 4 == 0:
                collector.record_cache_miss()
            else:
                collector.record_cache_hit()
        
        assert collector.cache.hit_rate == 75.0
    
    def test_api_stress_scenario(self):
        """Test scenario with many API calls."""
        collector = MetricsCollector()
        collector.reset()
        
        endpoints = ["/api/indicator", "/api/observable", "/api/report"]
        
        for i in range(100):
            endpoint = endpoints[i % 3]
            success = i % 10 != 0  # 90% success rate
            
            collector.record_api_call(
                endpoint=endpoint,
                success=success,
                duration_seconds=0.1 + (i % 5) * 0.05
            )
        
        assert collector.api.api_calls_total == 100
        assert collector.api.api_calls_successful == 90
        assert collector.api.api_success_rate == 90.0
        assert len(collector.api.endpoint_stats) == 3


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
