#!/usr/bin/env python3
"""
Comprehensive tests for the OpenCTI caching layer.

Tests cover:
- Basic cache operations (get/set/delete)
- LRU eviction policy
- TTL expiration
- Cache statistics
- Key generation
"""
import time
import pytest
from iris_opencti_module.opencti_handler.cache import OpenCTICache


class TestOpenCTICacheBasicOperations:
    """Test basic cache operations."""
    
    def test_cache_hit(self):
        """Test cache hit returns stored result."""
        cache = OpenCTICache(max_size=100, ttl=300)
        
        cache.set("8.8.8.8", {"data": {"indicator": {"id": "test"}}})
        result = cache.get("8.8.8.8")
        
        assert result == {"data": {"indicator": {"id": "test"}}}
    
    def test_cache_miss(self):
        """Test cache miss returns None."""
        cache = OpenCTICache(max_size=100, ttl=300)
        result = cache.get("nonexistent")
        assert result is None
    
    def test_set_overwrites_existing_entry(self):
        """Test that setting an existing key updates the value."""
        cache = OpenCTICache(max_size=100, ttl=300)
        
        cache.set("test", {"value": "first"})
        cache.set("test", {"value": "second"})
        
        result = cache.get("test")
        assert result == {"value": "second"}
    
    def test_delete_removes_entry(self):
        """Test that delete removes the cached entry."""
        cache = OpenCTICache(max_size=100, ttl=300)
        
        cache.set("test", {"value": "data"})
        cache.delete("test")
        
        assert cache.get("test") is None
    
    def test_clear_removes_all_entries(self):
        """Test that clear removes all cached entries."""
        cache = OpenCTICache(max_size=100, ttl=300)
        
        cache.set("key1", {"value": "data1"})
        cache.set("key2", {"value": "data2"})
        cache.set("key3", {"value": "data3"})
        
        cache.clear()
        
        assert cache.get("key1") is None
        assert cache.get("key2") is None
        assert cache.get("key3") is None
        assert cache.get_stats()["size"] == 0


class TestOpenCTICacheLRUEviction:
    """Test LRU eviction policy."""
    
    def test_lru_eviction_when_at_capacity(self):
        """Test that LRU entry is evicted when cache is full."""
        cache = OpenCTICache(max_size=3, ttl=300)
        
        cache.set("key1", {"value": "data1"})
        cache.set("key2", {"value": "data2"})
        cache.set("key3", {"value": "data3"})
        
        # Add fourth entry - should evict key1 (least recently used)
        cache.set("key4", {"value": "data4"})
        
        assert cache.get("key1") is None  # Evicted
        assert cache.get("key2") is not None
        assert cache.get("key3") is not None
        assert cache.get("key4") is not None
    
    def test_access_updates_lru_order(self):
        """Test that accessing an entry moves it to most recently used."""
        cache = OpenCTICache(max_size=3, ttl=300)
        
        cache.set("key1", {"value": "data1"})
        cache.set("key2", {"value": "data2"})
        cache.set("key3", {"value": "data3"})
        
        # Access key1 to make it most recently used
        cache.get("key1")
        
        # Add fourth entry - should evict key2 (now least recently used)
        cache.set("key4", {"value": "data4"})
        
        assert cache.get("key1") is not None  # Still there
        assert cache.get("key2") is None  # Evicted
        assert cache.get("key3") is not None
        assert cache.get("key4") is not None
    
    def test_update_moves_to_mru_position(self):
        """Test that updating an existing entry moves it to most recently used."""
        cache = OpenCTICache(max_size=3, ttl=300)
        
        cache.set("key1", {"value": "data1"})
        cache.set("key2", {"value": "data2"})
        cache.set("key3", {"value": "data3"})
        
        # Update key1 - this moves it to MRU position
        cache.set("key1", {"value": "updated_data1"})
        
        # Add fourth entry - should evict key2 (now LRU since key1 was updated)
        cache.set("key4", {"value": "data4"})
        
        assert cache.get("key1") is not None  # Updated and moved to MRU
        assert cache.get("key2") is None  # Evicted (was LRU)
        assert cache.get("key3") is not None
        assert cache.get("key4") is not None


class TestOpenCTICacheTTL:
    """Test TTL expiration functionality."""
    
    def test_cache_expiration(self):
        """Test that cache entries expire after TTL."""
        cache = OpenCTICache(max_size=100, ttl=0.1)  # 100ms TTL
        
        cache.set("test", {"data": "value"})
        assert cache.get("test") is not None
        
        time.sleep(0.2)
        assert cache.get("test") is None
    
    def test_cache_entry_not_expired_before_ttl(self):
        """Test that cache entries are valid before TTL expires."""
        cache = OpenCTICache(max_size=100, ttl=1.0)  # 1 second TTL
        
        cache.set("test", {"data": "value"})
        
        # Should still be valid after 100ms
        time.sleep(0.1)
        assert cache.get("test") is not None
    
    def test_different_ttl_per_cache_instance(self):
        """Test that different cache instances can have different TTLs."""
        cache_short = OpenCTICache(max_size=100, ttl=0.05)
        cache_long = OpenCTICache(max_size=100, ttl=1.0)
        
        cache_short.set("test", {"data": "short"})
        cache_long.set("test", {"data": "long"})
        
        time.sleep(0.1)
        
        assert cache_short.get("test") is None  # Expired
        assert cache_long.get("test") is not None  # Still valid


class TestOpenCTICacheStatistics:
    """Test cache statistics tracking."""
    
    def test_cache_stats_initial_state(self):
        """Test that cache stats start at zero."""
        cache = OpenCTICache(max_size=100, ttl=300)
        stats = cache.get_stats()
        
        assert stats["hits"] == 0
        assert stats["misses"] == 0
        assert stats["size"] == 0
        assert stats["hit_rate"] == 0.0
    
    def test_cache_stats_hit_tracking(self):
        """Test that cache hits are tracked correctly."""
        cache = OpenCTICache(max_size=100, ttl=300)
        
        cache.set("test", {"data": "value"})
        cache.get("test")  # First hit
        cache.get("test")  # Second hit
        
        stats = cache.get_stats()
        assert stats["hits"] == 2
        assert stats["misses"] == 0
        assert stats["hit_rate"] == 1.0
    
    def test_cache_stats_miss_tracking(self):
        """Test that cache misses are tracked correctly."""
        cache = OpenCTICache(max_size=100, ttl=300)
        
        cache.get("nonexistent1")
        cache.get("nonexistent2")
        
        stats = cache.get_stats()
        assert stats["hits"] == 0
        assert stats["misses"] == 2
        assert stats["hit_rate"] == 0.0
    
    def test_cache_stats_mixed_hits_and_misses(self):
        """Test cache stats with mixed hits and misses."""
        cache = OpenCTICache(max_size=100, ttl=300)
        
        cache.set("key1", {"data": "value1"})
        cache.get("key1")  # hit
        cache.get("nonexistent")  # miss
        cache.get("key1")  # hit
        cache.get("nonexistent2")  # miss
        
        stats = cache.get_stats()
        assert stats["hits"] == 2
        assert stats["misses"] == 2
        assert stats["hit_rate"] == 0.5
        assert stats["size"] == 1
    
    def test_cache_stats_size_tracking(self):
        """Test that cache size is tracked correctly."""
        cache = OpenCTICache(max_size=100, ttl=300)
        
        cache.set("key1", {"data": "value1"})
        cache.set("key2", {"data": "value2"})
        cache.set("key3", {"data": "value3"})
        
        stats = cache.get_stats()
        assert stats["size"] == 3
        
        cache.delete("key2")
        stats = cache.get_stats()
        assert stats["size"] == 2


class TestOpenCTICacheKeyGeneration:
    """Test cache key generation."""
    
    def test_key_generation_without_type(self):
        """Test key generation without query type."""
        cache = OpenCTICache(max_size=100, ttl=300)
        
        # Same value should produce same key
        key1 = cache._get_key("8.8.8.8")
        key2 = cache._get_key("8.8.8.8")
        assert key1 == key2
        
        # Different values should produce different keys
        key3 = cache._get_key("1.1.1.1")
        assert key1 != key3
    
    def test_key_generation_with_type(self):
        """Test key generation with query type."""
        cache = OpenCTICache(max_size=100, ttl=300)
        
        # Same value with same type should produce same key
        key1 = cache._get_key("8.8.8.8", "indicator")
        key2 = cache._get_key("8.8.8.8", "indicator")
        assert key1 == key2
        
        # Same value with different type should produce different key
        key3 = cache._get_key("8.8.8.8", "stixCyberObservable")
        assert key1 != key3
    
    def test_key_is_hash_truncated(self):
        """Test that generated keys are truncated to 16 characters."""
        cache = OpenCTICache(max_size=100, ttl=300)
        
        key = cache._get_key("test_value", "test_type")
        assert len(key) == 16


class TestOpenCTICacheIntegration:
    """Integration tests for cache usage patterns."""
    
    def test_typical_query_pattern(self):
        """Test typical query pattern: miss then hit."""
        cache = OpenCTICache(max_size=100, ttl=300)
        
        # First query - cache miss
        result = cache.get("8.8.8.8", "indicator")
        assert result is None
        
        # Simulate API call and cache result
        api_result = {"data": {"indicator": {"id": "indicator--123", "name": "8.8.8.8"}}}
        cache.set("8.8.8.8", api_result, "indicator")
        
        # Second query - cache hit
        result = cache.get("8.8.8.8", "indicator")
        assert result == api_result
        
        stats = cache.get_stats()
        assert stats["hits"] == 1
        assert stats["misses"] == 1
    
    def test_multiple_ioc_caching(self):
        """Test caching multiple different IOCs."""
        cache = OpenCTICache(max_size=100, ttl=300)
        
        iocs = [
            ("8.8.8.8", "ip-addr"),
            ("1.1.1.1", "ip-addr"),
            ("example.com", "domain-name"),
            ("malware.exe", "file-name"),
        ]
        
        # Cache all IOCs
        for value, ioc_type in iocs:
            cache.set(value, {"data": {"id": value}}, ioc_type)
        
        # Verify all can be retrieved
        for value, ioc_type in iocs:
            result = cache.get(value, ioc_type)
            assert result is not None
            assert result["data"]["id"] == value
        
        stats = cache.get_stats()
        assert stats["size"] == 4
    
    def test_cache_with_different_query_types_same_value(self):
        """Test that same value with different types are cached separately."""
        cache = OpenCTICache(max_size=100, ttl=300)
        
        cache.set("8.8.8.8", {"type": "indicator"}, "indicator")
        cache.set("8.8.8.8", {"type": "observable"}, "stixCyberObservable")
        
        indicator_result = cache.get("8.8.8.8", "indicator")
        observable_result = cache.get("8.8.8.8", "stixCyberObservable")
        
        assert indicator_result == {"type": "indicator"}
        assert observable_result == {"type": "observable"}
