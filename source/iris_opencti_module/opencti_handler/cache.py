#!/usr/bin/env python3
"""
LRU Cache module for OpenCTI query results.

Provides in-memory caching with configurable TTL and LRU eviction policy
to improve performance for repeated OpenCTI queries.
"""
import time
import hashlib
import logging
from collections import OrderedDict
from typing import Optional, Any

logger = logging.getLogger(__name__)


class OpenCTICache:
    """Simple in-memory LRU cache for OpenCTI query results.
    
    Features:
    - LRU eviction when cache reaches max_size
    - TTL-based expiration for cache entries
    - Cache hit/miss statistics tracking
    - Thread-safe operations (single-threaded by design for this module)
    
    Attributes:
        max_size: Maximum number of entries before LRU eviction kicks in
        ttl: Time-to-live in seconds for cache entries
    """
    
    def __init__(self, max_size: int = 1000, ttl: int = 300):
        """Initialize the cache.
        
        Args:
            max_size: Maximum number of entries (default 1000)
            ttl: Time-to-live in seconds (default 300 = 5 minutes)
        """
        self.max_size = max_size
        self.ttl = ttl
        self._cache = OrderedDict()
        self._timestamps = {}
        self._hits = 0
        self._misses = 0
        
    def _get_key(self, query_value: str, query_type: str = None) -> str:
        """Generate cache key from query parameters.
        
        Args:
            query_value: The IOC value being queried (e.g., "8.8.8.8")
            query_type: Optional type of query (e.g., "indicator", "stixCyberObservable")
            
        Returns:
            A SHA256 hash of the query parameters (truncated to 16 chars)
        """
        key_data = f"{query_type}:{query_value}" if query_type else query_value
        return hashlib.sha256(key_data.encode()).hexdigest()[:16]
    
    def get(self, query_value: str, query_type: str = None) -> Optional[Any]:
        """Get cached result if available and not expired.
        
        Args:
            query_value: The IOC value to look up
            query_type: Optional type of query for key generation
            
        Returns:
            Cached result if found and not expired, None otherwise
        """
        key = self._get_key(query_value, query_type)
        
        if key not in self._cache:
            self._misses += 1
            return None
            
        # Check expiration
        if time.time() - self._timestamps[key] > self.ttl:
            logger.debug(f"Cache entry expired for key: {key}")
            self.delete(query_value, query_type)
            self._misses += 1
            return None
            
        # Move to end (most recently used)
        self._cache.move_to_end(key)
        self._hits += 1
        logger.debug(f"Cache hit for key: {key}")
        return self._cache[key]
    
    def set(self, query_value: str, result: Any, query_type: str = None):
        """Store result in cache.
        
        Args:
            query_value: The IOC value that was queried
            result: The query result to cache
            query_type: Optional type of query for key generation
            
        Note:
            If cache is at capacity, the least recently used entry is evicted.
            Updating an existing entry moves it to most recently used position.
        """
        key = self._get_key(query_value, query_type)
        
        # If key already exists, update it and move to end (MRU position)
        if key in self._cache:
            self._cache.move_to_end(key)
            self._cache[key] = result
            self._timestamps[key] = time.time()
            logger.debug(f"Updated cache entry for key: {key}")
            return
        
        # Evict oldest if at capacity
        if len(self._cache) >= self.max_size:
            oldest = next(iter(self._cache))
            del self._cache[oldest]
            del self._timestamps[oldest]
            logger.debug(f"Evicted oldest entry: {oldest}")
            
        self._cache[key] = result
        self._timestamps[key] = time.time()
        logger.debug(f"Stored cache entry for key: {key}")
        
    def delete(self, query_value: str, query_type: str = None):
        """Delete cached entry.
        
        Args:
            query_value: The IOC value to remove from cache
            query_type: Optional type of query for key generation
        """
        key = self._get_key(query_value, query_type)
        if key in self._cache:
            del self._cache[key]
            del self._timestamps[key]
            logger.debug(f"Deleted cache entry for key: {key}")
        
    def clear(self):
        """Clear entire cache."""
        logger.info("Clearing entire OpenCTI cache")
        self._cache.clear()
        self._timestamps.clear()
        self._hits = 0
        self._misses = 0
        
    def get_stats(self) -> dict:
        """Return cache statistics.
        
        Returns:
            Dictionary with cache metrics including size, hits, misses, and hit rate
        """
        total = self._hits + self._misses
        return {
            "size": len(self._cache),
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": self._hits / total if total > 0 else 0.0,
            "max_size": self.max_size,
            "ttl": self.ttl
        }
