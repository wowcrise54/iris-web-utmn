#!/usr/bin/env python3
"""
Enrichment history tracking and deduplication for OpenCTI module.

This module provides:
- Historical tracking of enrichment results
- Deduplication logic to avoid redundant lookups
- Configuration-based TTL for history records
- Statistics and reporting capabilities
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from collections import OrderedDict


logger = logging.getLogger(__name__)


class EnrichmentHistory:
    """
    Tracks enrichment history for IOCs and provides deduplication logic.
    
    This class maintains a history of enrichment results, allowing the system to:
    - Avoid redundant enrichment calls for recently enriched IOCs
    - Track historical match rates and statistics
    - Implement intelligent retry logic for failed enrichments
    - Provide historical context for analyst review
    
    Attributes:
        history_ttl_hours: TTL in hours for history records before expiration
        max_history_size: Maximum number of records to keep in memory
    """
    
    def __init__(self, history_ttl_hours: int = 24, max_history_size: int = 10000):
        """
        Initialize enrichment history tracker.
        
        Args:
            history_ttl_hours: How long to keep history records (default 24 hours)
            max_history_size: Maximum records to keep in memory (default 10000)
        """
        self.history_ttl_hours = history_ttl_hours
        self.max_history_size = max_history_size
        self._history: OrderedDict[str, Dict[str, Any]] = OrderedDict()
    
    def _canonicalize(self, ioc_value: str, ioc_type: str) -> str:
        """
        Canonicalize IOC value for consistent deduplication.
        
        Args:
            ioc_value: The raw IOC value
            ioc_type: Type of the IOC (domain, ipv4, email, etc.)
            
        Returns:
            Canonicalized IOC value
        """
        if not ioc_value:
            return ""
        
        value = str(ioc_value).strip()
        
        # Domain names: lowercase, remove trailing dot
        if ioc_type == "domain":
            value = value.lower().rstrip('.')
        
        # Email addresses: lowercase the domain part
        elif ioc_type == "email":
            if '@' in value:
                local, domain = value.rsplit('@', 1)
                value = f"{local.lower()}@{domain.lower()}"
        
        # IPv4/IPv6: normalize format (already standardized)
        elif ioc_type in ("ipv4", "ipv6"):
            value = value.lower()
        
        # URL: lowercase the domain part
        elif ioc_type == "url":
            # Simple URL canonicalization - just lowercase for now
            value = value.lower()
        
        return value
    
    def _make_dedupe_key(self, ioc_value: str, ioc_type: str) -> str:
        """
        Create a unique deduplication key for an IOC.
        
        Args:
            ioc_value: The IOC value
            ioc_type: The IOC type
            
        Returns:
            Unique key combining canonicalized value and type
        """
        canonical = self._canonicalize(ioc_value, ioc_type)
        return f"{ioc_type}:{canonical}"
    
    def _is_expired(self, timestamp: str, reference_time: Optional[datetime] = None) -> bool:
        """
        Check if a record timestamp is expired based on TTL.
        
        Args:
            timestamp: ISO format timestamp string
            reference_time: Optional reference time for testing (defaults to now)
            
        Returns:
            True if the record is expired
        """
        try:
            record_time = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
            if reference_time:
                # Use provided reference time (for testing with fixed timestamps)
                now = reference_time
            else:
                now = datetime.now(record_time.tzinfo) if record_time.tzinfo else datetime.utcnow()
            
            # Handle timezone-aware vs naive datetime comparison
            if record_time.tzinfo and not now.tzinfo:
                # Make now timezone-aware to match record_time
                from datetime import timezone
                now = now.replace(tzinfo=timezone.utc)
            elif not record_time.tzinfo and now.tzinfo:
                # Make record_time naive to match now
                record_time = record_time.replace(tzinfo=None)
            
            return now - record_time > timedelta(hours=self.history_ttl_hours)
        except (ValueError, TypeError):
            # Invalid timestamp format, treat as expired
            return True
    
    def _cleanup_if_needed(self):
        """Remove expired records if history exceeds max size."""
        if len(self._history) <= self.max_history_size:
            return
        
        # Remove expired records first
        expired_keys = [
            key for key, record in self._history.items()
            if self._is_expired(record.get("timestamp", ""))
        ]
        for key in expired_keys:
            del self._history[key]
        
        # If still over limit, remove oldest records
        if len(self._history) > self.max_history_size:
            # OrderedDict maintains insertion order, remove from beginning (oldest)
            while len(self._history) > self.max_history_size:
                self._history.popitem(last=False)
    
    def add_record(self, record: Dict[str, Any]) -> None:
        """
        Add or update an enrichment history record.
        
        Args:
            record: Dictionary containing:
                - query_value: The original IOC value queried
                - ioc_type: Type of the IOC
                - status: 'match', 'no_match', or 'error'
                - timestamp: ISO format timestamp (optional, defaults to now)
                - match_count: Number of matches found (optional)
                - error: Error message if status is 'error' (optional)
                - Any other enrichment data to preserve
        """
        ioc_type = record.get("ioc_type", "unknown")
        query_value = record.get("query_value", "")
        
        dedupe_key = self._make_dedupe_key(query_value, ioc_type)
        
        # Ensure timestamp is present
        if "timestamp" not in record:
            record["timestamp"] = datetime.utcnow().isoformat() + "Z"
        
        # Store the record
        self._history[dedupe_key] = record
        
        # Cleanup if needed
        self._cleanup_if_needed()
        
        logger.debug(f"Added history record for {dedupe_key}")
    
    def check_history(self, ioc_value: str, ioc_type: str, reference_time: Optional[datetime] = None) -> Dict[str, Any]:
        """
        Check if an IOC exists in history and whether it should be enriched.
        
        Args:
            ioc_value: The IOC value to check
            ioc_type: Type of the IOC
            reference_time: Optional reference time for testing
            
        Returns:
            Dictionary containing:
                - in_history: bool - Whether IOC exists in history
                - should_enrich: bool - Whether enrichment should proceed
                - record: dict - The cached record if found (None otherwise)
                - cached_status: str - Status of cached result if found
        """
        dedupe_key = self._make_dedupe_key(ioc_value, ioc_type)
        
        record = self._history.get(dedupe_key)
        
        if not record:
            return {
                "in_history": False,
                "should_enrich": True,
                "record": None,
                "cached_status": None
            }
        
        # Check if record is expired
        if self._is_expired(record.get("timestamp", ""), reference_time):
            # Remove expired record
            del self._history[dedupe_key]
            return {
                "in_history": False,
                "should_enrich": True,
                "record": None,
                "cached_status": None
            }
        
        # Determine if we should enrich based on status
        status = record.get("status", "unknown")
        
        # Should enrich if:
        # - Status is 'error' (retry the lookup)
        # - Status is 'no_match' (data may have changed)
        # - Status is 'match' but TTL is very old (re-verify)
        # Should NOT enrich if:
        # - Status is 'match' and still within TTL
        should_enrich = status in ("error", "no_match")
        
        return {
            "in_history": True,
            "should_enrich": should_enrich,
            "record": record,
            "cached_status": status
        }
    
    def get_historical_matches(self, reference_time: Optional[datetime] = None) -> List[Dict[str, Any]]:
        """
        Get all historical records with 'match' status.
        
        Args:
            reference_time: Optional reference time for testing
            
        Returns:
            List of match records
        """
        return [
            record for record in self._history.values()
            if record.get("status") == "match" and not self._is_expired(record.get("timestamp", ""), reference_time)
        ]
    
    def get_historical_errors(self, reference_time: Optional[datetime] = None) -> List[Dict[str, Any]]:
        """
        Get all historical records with 'error' status.
        
        Args:
            reference_time: Optional reference time for testing
            
        Returns:
            List of error records
        """
        return [
            record for record in self._history.values()
            if record.get("status") == "error" and not self._is_expired(record.get("timestamp", ""), reference_time)
        ]
    
    def get_stats(self, reference_time: Optional[datetime] = None) -> Dict[str, Any]:
        """
        Get statistics about the enrichment history.
        
        Returns:
            Dictionary containing:
                - total_records: Total number of records
                - match_count: Number of successful matches
                - no_match_count: Number of no-match results
                - error_count: Number of errors
                - expired_count: Number of expired records
        """
        match_count = 0
        no_match_count = 0
        error_count = 0
        expired_count = 0
        
        for record in self._history.values():
            if self._is_expired(record.get("timestamp", ""), reference_time):
                expired_count += 1
                continue
            
            status = record.get("status", "unknown")
            if status == "match":
                match_count += 1
            elif status == "no_match":
                no_match_count += 1
            elif status == "error":
                error_count += 1
        
        return {
            "total_records": len(self._history),
            "active_records": len(self._history) - expired_count,
            "match_count": match_count,
            "no_match_count": no_match_count,
            "error_count": error_count,
            "expired_count": expired_count,
            "match_rate": match_count / (match_count + no_match_count) if (match_count + no_match_count) > 0 else 0
        }
    
    def clear_expired(self) -> int:
        """
        Remove all expired records from history.
        
        Returns:
            Number of records removed
        """
        expired_keys = [
            key for key, record in self._history.items()
            if self._is_expired(record.get("timestamp", ""))
        ]
        
        for key in expired_keys:
            del self._history[key]
        
        if expired_keys:
            logger.info(f"Cleared {len(expired_keys)} expired history records")
        
        return len(expired_keys)
    
    def clear_all(self) -> None:
        """Clear all history records."""
        count = len(self._history)
        self._history.clear()
        logger.info(f"Cleared {count} history records")
    
    def get_record(self, ioc_value: str, ioc_type: str) -> Optional[Dict[str, Any]]:
        """
        Get a specific record from history.
        
        Args:
            ioc_value: The IOC value
            ioc_type: The IOC type
            
        Returns:
            The record if found and not expired, None otherwise
        """
        dedupe_key = self._make_dedupe_key(ioc_value, ioc_type)
        record = self._history.get(dedupe_key)
        
        if record and self._is_expired(record.get("timestamp", "")):
            del self._history[dedupe_key]
            return None
        
        return record


# Singleton instance for use across the module
_history_instance: Optional[EnrichmentHistory] = None


def get_enrichment_history(config: Optional[Dict[str, Any]] = None) -> EnrichmentHistory:
    """
    Get or create the singleton enrichment history instance.
    
    Args:
        config: Optional configuration dictionary with:
            - history_ttl_hours: TTL for history records
            - max_history_size: Maximum records to keep
            
    Returns:
        EnrichmentHistory instance
    """
    global _history_instance
    
    if _history_instance is None:
        config = config or {}
        ttl = int(config.get("opencti_history_ttl_hours", 24))
        max_size = int(config.get("opencti_history_max_size", 10000))
        _history_instance = EnrichmentHistory(
            history_ttl_hours=ttl,
            max_history_size=max_size
        )
    
    return _history_instance


def reset_enrichment_history() -> None:
    """Reset the singleton history instance (useful for testing)."""
    global _history_instance
    if _history_instance:
        _history_instance.clear_all()
    _history_instance = None
