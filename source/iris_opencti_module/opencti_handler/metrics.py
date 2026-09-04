#!/usr/bin/env python3
"""
OpenCTI Metrics Collection Module.

Provides comprehensive performance metrics collection for the OpenCTI plugin,
including enrichment timing, cache statistics, error rates, and operational insights.
"""
import time
import logging
import threading
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from collections import deque
from dataclasses import dataclass, field, asdict
from enum import Enum

logger = logging.getLogger(__name__)


class MetricType(Enum):
    """Types of metrics that can be collected."""
    COUNTER = "counter"
    GAUGE = "gauge"
    HISTOGRAM = "histogram"
    TIMER = "timer"


@dataclass
class MetricPoint:
    """Single metric data point."""
    name: str
    value: float
    timestamp: datetime
    tags: Dict[str, str] = field(default_factory=dict)
    metric_type: MetricType = MetricType.GAUGE


@dataclass
class EnrichmentMetrics:
    """Metrics related to IOC enrichment operations."""
    total_enrichments: int = 0
    successful_enrichments: int = 0
    failed_enrichments: int = 0
    skipped_enrichments: int = 0  # Cached/deduplicated
    total_iocs_processed: int = 0
    total_matches_found: int = 0
    total_errors: int = 0
    
    # Timing metrics
    total_enrichment_time_seconds: float = 0.0
    min_enrichment_time_seconds: float = float('inf')
    max_enrichment_time_seconds: float = 0.0
    enrichment_times: deque = field(default_factory=lambda: deque(maxlen=1000))
    
    # Per-alert metrics
    alerts_enriched: int = 0
    avg_iocs_per_alert: float = 0.0
    
    def record_enrichment(self, success: bool, duration_seconds: float, ioc_count: int = 1, 
                         matched: bool = False, skipped: bool = False):
        """Record a single enrichment operation."""
        if skipped:
            self.skipped_enrichments += 1
            return
            
        self.total_enrichments += 1
        self.total_iocs_processed += ioc_count
        
        if success:
            self.successful_enrichments += 1
            if matched:
                self.total_matches_found += 1
        else:
            self.failed_enrichments += 1
            self.total_errors += 1
        
        # Update timing metrics
        self.enrichment_times.append(duration_seconds)
        self.total_enrichment_time_seconds += duration_seconds
        self.min_enrichment_time_seconds = min(self.min_enrichment_time_seconds, duration_seconds)
        self.max_enrichment_time_seconds = max(self.max_enrichment_time_seconds, duration_seconds)
    
    def record_alert_enrichment(self, ioc_count: int):
        """Record completion of alert enrichment."""
        self.alerts_enriched += 1
        self.avg_iocs_per_alert = self.total_iocs_processed / self.alerts_enriched
    
    @property
    def avg_enrichment_time_seconds(self) -> float:
        """Calculate average enrichment time."""
        if not self.enrichment_times:
            return 0.0
        return sum(self.enrichment_times) / len(self.enrichment_times)
    
    @property
    def success_rate(self) -> float:
        """Calculate success rate as percentage."""
        if self.total_enrichments == 0:
            return 100.0
        return (self.successful_enrichments / self.total_enrichments) * 100
    
    @property
    def error_rate(self) -> float:
        """Calculate error rate as percentage."""
        if self.total_enrichments == 0:
            return 0.0
        return (self.failed_enrichments / self.total_enrichments) * 100
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "total_enrichments": self.total_enrichments,
            "successful_enrichments": self.successful_enrichments,
            "failed_enrichments": self.failed_enrichments,
            "skipped_enrichments": self.skipped_enrichments,
            "total_iocs_processed": self.total_iocs_processed,
            "total_matches_found": self.total_matches_found,
            "total_errors": self.total_errors,
            "avg_enrichment_time_seconds": round(self.avg_enrichment_time_seconds, 3),
            "min_enrichment_time_seconds": round(self.min_enrichment_time_seconds, 3) if self.min_enrichment_time_seconds != float('inf') else 0,
            "max_enrichment_time_seconds": round(self.max_enrichment_time_seconds, 3),
            "alerts_enriched": self.alerts_enriched,
            "avg_iocs_per_alert": round(self.avg_iocs_per_alert, 2),
            "success_rate_percent": round(self.success_rate, 2),
            "error_rate_percent": round(self.error_rate, 2),
        }


@dataclass
class CacheMetrics:
    """Metrics related to cache operations."""
    cache_hits: int = 0
    cache_misses: int = 0
    cache_evictions: int = 0
    cache_clears: int = 0
    current_cache_size: int = 0
    max_cache_size: int = 1000
    cache_ttl_seconds: int = 300
    
    def record_hit(self):
        """Record a cache hit."""
        self.cache_hits += 1
    
    def record_miss(self):
        """Record a cache miss."""
        self.cache_misses += 1
    
    def record_eviction(self):
        """Record a cache eviction."""
        self.cache_evictions += 1
    
    def record_clear(self):
        """Record a cache clear."""
        self.cache_clears += 1
    
    @property
    def hit_rate(self) -> float:
        """Calculate cache hit rate as percentage."""
        total = self.cache_hits + self.cache_misses
        if total == 0:
            return 0.0
        return (self.cache_hits / total) * 100
    
    @property
    def miss_rate(self) -> float:
        """Calculate cache miss rate as percentage."""
        total = self.cache_hits + self.cache_misses
        if total == 0:
            return 100.0
        return (self.cache_misses / total) * 100
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "cache_hits": self.cache_hits,
            "cache_misses": self.cache_misses,
            "cache_evictions": self.cache_evictions,
            "cache_clears": self.cache_clears,
            "current_cache_size": self.current_cache_size,
            "max_cache_size": self.max_cache_size,
            "cache_ttl_seconds": self.cache_ttl_seconds,
            "hit_rate_percent": round(self.hit_rate, 2),
            "miss_rate_percent": round(self.miss_rate, 2),
            "utilization_percent": round((self.current_cache_size / self.max_cache_size) * 100, 2) if self.max_cache_size > 0 else 0,
        }


@dataclass
class APIMetrics:
    """Metrics related to API/Client operations."""
    api_calls_total: int = 0
    api_calls_successful: int = 0
    api_calls_failed: int = 0
    api_timeout_errors: int = 0
    api_rate_limit_hits: int = 0
    total_api_time_seconds: float = 0.0
    
    # Per-endpoint metrics
    endpoint_stats: Dict[str, Dict[str, int]] = field(default_factory=dict)
    
    def record_api_call(self, endpoint: str = None, success: bool = True, 
                       duration_seconds: float = 0.0, is_timeout: bool = False,
                       is_rate_limited: bool = False):
        """Record an API call."""
        self.api_calls_total += 1
        self.total_api_time_seconds += duration_seconds
        
        if success:
            self.api_calls_successful += 1
        else:
            self.api_calls_failed += 1
            if is_timeout:
                self.api_timeout_errors += 1
            if is_rate_limited:
                self.api_rate_limit_hits += 1
        
        # Track per-endpoint stats
        if endpoint:
            if endpoint not in self.endpoint_stats:
                self.endpoint_stats[endpoint] = {"total": 0, "success": 0, "failed": 0}
            self.endpoint_stats[endpoint]["total"] += 1
            if success:
                self.endpoint_stats[endpoint]["success"] += 1
            else:
                self.endpoint_stats[endpoint]["failed"] += 1
    
    @property
    def avg_api_time_seconds(self) -> float:
        """Calculate average API call time."""
        if self.api_calls_total == 0:
            return 0.0
        return self.total_api_time_seconds / self.api_calls_total
    
    @property
    def api_success_rate(self) -> float:
        """Calculate API success rate as percentage."""
        if self.api_calls_total == 0:
            return 100.0
        return (self.api_calls_successful / self.api_calls_total) * 100
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "api_calls_total": self.api_calls_total,
            "api_calls_successful": self.api_calls_successful,
            "api_calls_failed": self.api_calls_failed,
            "api_timeout_errors": self.api_timeout_errors,
            "api_rate_limit_hits": self.api_rate_limit_hits,
            "avg_api_time_seconds": round(self.avg_api_time_seconds, 3),
            "api_success_rate_percent": round(self.api_success_rate, 2),
            "endpoint_stats": self.endpoint_stats,
        }


class MetricsCollector:
    """
    Central metrics collector for OpenCTI module.
    
    Thread-safe singleton that collects, aggregates, and exposes metrics
    for enrichment operations, cache performance, and API calls.
    """
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        """Thread-safe singleton pattern."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        """Initialize metrics collectors."""
        if self._initialized:
            return
            
        self._initialized = True
        self._lock = threading.RLock()
        
        # Initialize metric collectors
        self.enrichment = EnrichmentMetrics()
        self.cache = CacheMetrics()
        self.api = APIMetrics()
        
        # Time-series data for trends (last 24 hours)
        self._time_series_window = timedelta(hours=24)
        self._metrics_history: deque = deque(maxlen=1440)  # 1440 minutes = 24 hours at 1/min
        
        # Start background aggregation if not running
        self._aggregation_running = False
        self._start_aggregation()
    
    def _start_aggregation(self):
        """Start background metrics aggregation thread."""
        if self._aggregation_running:
            return
        
        def aggregation_loop():
            import time as time_module
            while self._aggregation_running:
                try:
                    self._aggregate_metrics()
                    time_module.sleep(60)  # Aggregate every minute
                except Exception as e:
                    logger.error(f"Metrics aggregation error: {e}")
        
        thread = threading.Thread(target=aggregation_loop, daemon=True)
        thread.start()
        self._aggregation_running = True
        logger.info("OpenCTI metrics aggregation started")
    
    def _aggregate_metrics(self):
        """Aggregate metrics into time series."""
        with self._lock:
            snapshot = {
                # Store as an ISO string (same shape get_metrics() at the
                # time_range filter parses with fromisoformat); a raw datetime
                # here made that filter raise TypeError -> 500 after 60s.
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "enrichment": self.enrichment.to_dict(),
                "cache": self.cache.to_dict(),
                "api": self.api.to_dict(),
            }
            self._metrics_history.append(snapshot)
    
    def record_enrichment(self, success: bool, duration_seconds: float, 
                         ioc_count: int = 1, matched: bool = False, 
                         skipped: bool = False):
        """Record enrichment operation metrics."""
        with self._lock:
            self.enrichment.record_enrichment(
                success=success,
                duration_seconds=duration_seconds,
                ioc_count=ioc_count,
                matched=matched,
                skipped=skipped
            )
            logger.debug(f"Recorded enrichment: success={success}, duration={duration_seconds:.3f}s")
    
    def record_alert_enrichment(self, ioc_count: int):
        """Record alert enrichment completion."""
        with self._lock:
            self.enrichment.record_alert_enrichment(ioc_count)
    
    def record_cache_hit(self):
        """Record a cache hit."""
        with self._lock:
            self.cache.record_hit()
    
    def record_cache_miss(self):
        """Record a cache miss."""
        with self._lock:
            self.cache.record_miss()
    
    def record_cache_eviction(self):
        """Record a cache eviction."""
        with self._lock:
            self.cache.record_eviction()
    
    def record_cache_clear(self):
        """Record a cache clear."""
        with self._lock:
            self.cache.record_clear()
    
    def update_cache_size(self, size: int, max_size: int = 1000, ttl: int = 300):
        """Update current cache size statistics."""
        with self._lock:
            self.cache.current_cache_size = size
            self.cache.max_cache_size = max_size
            self.cache.cache_ttl_seconds = ttl
    
    def record_api_call(self, endpoint: str = None, success: bool = True,
                       duration_seconds: float = 0.0, is_timeout: bool = False,
                       is_rate_limited: bool = False):
        """Record an API call."""
        with self._lock:
            self.api.record_api_call(
                endpoint=endpoint,
                success=success,
                duration_seconds=duration_seconds,
                is_timeout=is_timeout,
                is_rate_limited=is_rate_limited
            )
    
    def get_metrics(self, time_range: str = "all") -> Dict[str, Any]:
        """
        Get current metrics snapshot.
        
        Args:
            time_range: Time range for historical data ("all", "1h", "6h", "24h")
            
        Returns:
            Dictionary containing all metrics
        """
        with self._lock:
            result = {
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "enrichment": self.enrichment.to_dict(),
                "cache": self.cache.to_dict(),
                "api": self.api.to_dict(),
            }
            
            # Add historical data if requested
            if time_range != "all":
                range_map = {
                    "1h": timedelta(hours=1),
                    "6h": timedelta(hours=6),
                    "24h": timedelta(hours=24),
                }
                delta = range_map.get(time_range, timedelta(hours=24))
                cutoff = datetime.utcnow() - delta
                
                history = [
                    m for m in self._metrics_history
                    if datetime.fromisoformat(m["timestamp"].replace("Z", "")) > cutoff
                ]
                result["history"] = history
                result["time_range"] = time_range
            
            return result
    
    def get_summary(self) -> Dict[str, Any]:
        """
        Get a summary of key metrics for dashboard display.
        
        Returns:
            Summary dictionary with key performance indicators
        """
        with self._lock:
            return {
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "kpi": {
                    "total_enrichments": self.enrichment.total_enrichments,
                    "success_rate": round(self.enrichment.success_rate, 2),
                    "error_rate": round(self.enrichment.error_rate, 2),
                    "avg_enrichment_time_ms": round(self.enrichment.avg_enrichment_time_seconds * 1000, 2),
                    "cache_hit_rate": round(self.cache.hit_rate, 2),
                    "api_success_rate": round(self.api.api_success_rate, 2),
                    "alerts_enriched": self.enrichment.alerts_enriched,
                    "total_iocs_processed": self.enrichment.total_iocs_processed,
                },
                "enrichment": self.enrichment.to_dict(),
                "cache": self.cache.to_dict(),
                "api": self.api.to_dict(),
            }
    
    def reset(self):
        """Reset all metrics (for testing or manual reset)."""
        with self._lock:
            self.enrichment = EnrichmentMetrics()
            self.cache = CacheMetrics()
            self.api = APIMetrics()
            self._metrics_history.clear()
            logger.info("OpenCTI metrics reset")


_metrics_collector = None


def _get_metrics() -> MetricsCollector:
    """Lazily create the global metrics collector.

    The collector starts a daemon aggregation thread on construction.
    Creating it at import time (the previous behavior) leaked that thread in
    every process that imported metrics.py (e.g. the web app) even though the
    enrichment path never recorded anything. Lazy init starts the thread only
    in processes that actually use the metrics.
    """
    global _metrics_collector, metrics
    if _metrics_collector is None:
        _metrics_collector = MetricsCollector()
        # Rebind the public name to the real collector so subsequent accesses
        # (and identity checks) go straight to it.
        metrics = _metrics_collector
    return _metrics_collector


class _LazyMetrics:
    """Transparent lazy proxy around the global metrics collector.

    ``opencti_routes.py`` does ``from ...metrics import metrics`` and calls
    ``metrics.get_summary()`` etc. The collector must not be constructed at
    import time (it would start a daemon aggregation thread in every
    importing process), but the import must keep working, so this proxy
    creates the singleton on first attribute access and forwards everything
    to it afterwards.
    """

    def __getattr__(self, name):
        return getattr(_get_metrics(), name)


# Global metrics collector (a lazy proxy; the real singleton is created on
# first use).
metrics = _LazyMetrics()


class MetricsContextManager:
    """Context manager for timing operations and recording metrics."""
    
    def __init__(self, metric_collector: MetricsCollector = None, 
                 operation_type: str = "enrichment"):
        self.collector = metric_collector or metrics
        self.operation_type = operation_type
        self.start_time = None
        self.duration = None
    
    def __enter__(self):
        self.start_time = time.time()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.duration = time.time() - self.start_time
        
        if exc_type is None:
            # Success
            if self.operation_type == "enrichment":
                self.collector.record_enrichment(
                    success=True, 
                    duration_seconds=self.duration
                )
            elif self.operation_type == "api_call":
                self.collector.record_api_call(success=True, duration_seconds=self.duration)
        else:
            # Failure
            if self.operation_type == "enrichment":
                self.collector.record_enrichment(
                    success=False, 
                    duration_seconds=self.duration
                )
            elif self.operation_type == "api_call":
                self.collector.record_api_call(
                    success=False, 
                    duration_seconds=self.duration,
                    is_timeout=isinstance(exc_val, TimeoutError)
                )
        
        return False  # Don't suppress exceptions


def get_metrics_collector() -> MetricsCollector:
    """Get the global metrics collector instance."""
    return metrics


def record_enrichment(success: bool, duration_seconds: float, 
                     ioc_count: int = 1, matched: bool = False,
                     skipped: bool = False):
    """Convenience function to record enrichment metrics."""
    metrics.record_enrichment(
        success=success,
        duration_seconds=duration_seconds,
        ioc_count=ioc_count,
        matched=matched,
        skipped=skipped
    )


def record_cache_hit():
    """Convenience function to record cache hit."""
    metrics.record_cache_hit()


def record_cache_miss():
    """Convenience function to record cache miss."""
    metrics.record_cache_miss()


def record_api_call(endpoint: str = None, success: bool = True,
                   duration_seconds: float = 0.0, is_timeout: bool = False):
    """Convenience function to record API call metrics."""
    metrics.record_api_call(
        endpoint=endpoint,
        success=success,
        duration_seconds=duration_seconds,
        is_timeout=is_timeout
    )
