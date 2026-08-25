import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timedelta
from iris_opencti_module.opencti_handler.history import EnrichmentHistory


class TestEnrichmentHistory:
    """Tests for enrichment history tracking and deduplication"""

    def test_history_initialized_empty(self):
        """History should start empty for new IOCs"""
        history = EnrichmentHistory()
        
        result = history.check_history("example.com", "domain")
        
        assert result["in_history"] is False
        assert result["should_enrich"] is True

    def test_stores_enrichment_record(self):
        """Should store enrichment records with timestamp"""
        history = EnrichmentHistory()
        
        record = {
            "query_value": "example.com",
            "ioc_type": "domain",
            "status": "match",
            "match_count": 3,
            "timestamp": "2026-01-15T10:30:00Z"
        }
        history.add_record(record)
        
        # Use reference time that makes the record not expired
        reference_time = datetime(2026, 1, 15, 11, 0, 0)
        result = history.check_history("example.com", "domain", reference_time)
        
        assert result["in_history"] is True
        assert result["record"]["status"] == "match"
        assert result["record"]["match_count"] == 3

    def test_deduplication_by_canonical_value(self):
        """Should deduplicate based on canonicalized IOC value"""
        history = EnrichmentHistory()
        
        # Store with one case
        record = {
            "query_value": "example.com",
            "ioc_type": "domain",
            "status": "match",
            "timestamp": "2026-01-15T10:30:00Z"
        }
        history.add_record(record)
        
        # Check with different case - should find match
        reference_time = datetime(2026, 1, 15, 11, 0, 0)
        result = history.check_history("EXAMPLE.COM", "domain", reference_time)
        assert result["in_history"] is True

    def test_different_ioc_types_not_deduplicated(self):
        """Same value but different types should be separate"""
        history = EnrichmentHistory()
        
        record = {
            "query_value": "8.8.8.8",
            "ioc_type": "ipv4",
            "status": "no_match",
            "timestamp": "2026-01-15T10:30:00Z"
        }
        history.add_record(record)
        
        # Check as domain - should not find match
        result = history.check_history("8.8.8.8", "domain")
        assert result["in_history"] is False

    def test_history_expiry(self):
        """Old records should expire based on configured TTL"""
        history = EnrichmentHistory(history_ttl_hours=1)
        
        # Add record from 2 hours ago
        old_time = (datetime.utcnow() - timedelta(hours=2)).isoformat() + "Z"
        record = {
            "query_value": "example.com",
            "ioc_type": "domain",
            "status": "match",
            "timestamp": old_time
        }
        history.add_record(record)
        
        # Should be expired
        result = history.check_history("example.com", "domain")
        assert result["in_history"] is False
        assert result["should_enrich"] is True

    def test_skip_enrichment_on_recent_match(self):
        """Should recommend skipping enrichment for recent successful matches"""
        history = EnrichmentHistory(history_ttl_hours=24)
        
        # Add recent successful match
        recent_time = (datetime.utcnow() - timedelta(hours=1)).isoformat() + "Z"
        record = {
            "query_value": "malicious.com",
            "ioc_type": "domain",
            "status": "match",
            "match_count": 5,
            "timestamp": recent_time
        }
        history.add_record(record)
        
        result = history.check_history("malicious.com", "domain")
        assert result["in_history"] is True
        assert result["should_enrich"] is False
        assert result["cached_status"] == "match"

    def test_should_enrich_on_recent_error(self):
        """Should recommend enrichment even for recent errors (retry logic)"""
        history = EnrichmentHistory(history_ttl_hours=24)
        
        # Add recent error
        recent_time = (datetime.utcnow() - timedelta(hours=1)).isoformat() + "Z"
        record = {
            "query_value": "example.com",
            "ioc_type": "domain",
            "status": "error",
            "error": "Connection timeout",
            "timestamp": recent_time
        }
        history.add_record(record)
        
        result = history.check_history("example.com", "domain")
        assert result["in_history"] is True
        assert result["should_enrich"] is True  # Should retry on errors

    def test_should_enrich_on_no_match(self):
        """Should recommend enrichment for no_match status"""
        history = EnrichmentHistory(history_ttl_hours=24)
        
        # Add no_match record
        recent_time = (datetime.utcnow() - timedelta(hours=1)).isoformat() + "Z"
        record = {
            "query_value": "clean.com",
            "ioc_type": "domain",
            "status": "no_match",
            "timestamp": recent_time
        }
        history.add_record(record)
        
        result = history.check_history("clean.com", "domain")
        assert result["in_history"] is True
        assert result["should_enrich"] is True  # May have new data

    def test_get_historical_matches(self):
        """Should retrieve all historical matches for analysis"""
        history = EnrichmentHistory()
        
        history.add_record({
            "query_value": "malicious1.com",
            "ioc_type": "domain",
            "status": "match",
            "match_count": 3,
            "timestamp": "2026-01-15T10:00:00Z"
        })
        history.add_record({
            "query_value": "malicious2.com",
            "ioc_type": "domain",
            "status": "match",
            "match_count": 5,
            "timestamp": "2026-01-15T11:00:00Z"
        })
        history.add_record({
            "query_value": "clean.com",
            "ioc_type": "domain",
            "status": "no_match",
            "timestamp": "2026-01-15T12:00:00Z"
        })
        
        reference_time = datetime(2026, 1, 15, 12, 30, 0)
        matches = history.get_historical_matches(reference_time)
        assert len(matches) == 2
        assert all(m["status"] == "match" for m in matches)

    def test_get_history_stats(self):
        """Should return statistics about enrichment history"""
        history = EnrichmentHistory()
        
        history.add_record({
            "query_value": "ioc1.com",
            "ioc_type": "domain",
            "status": "match",
            "timestamp": "2026-01-15T10:00:00Z"
        })
        history.add_record({
            "query_value": "ioc2.com",
            "ioc_type": "domain",
            "status": "match",
            "timestamp": "2026-01-15T11:00:00Z"
        })
        history.add_record({
            "query_value": "ioc3.com",
            "ioc_type": "domain",
            "status": "no_match",
            "timestamp": "2026-01-15T12:00:00Z"
        })
        history.add_record({
            "query_value": "ioc4.com",
            "ioc_type": "domain",
            "status": "error",
            "timestamp": "2026-01-15T13:00:00Z"
        })
        
        reference_time = datetime(2026, 1, 15, 13, 30, 0)
        stats = history.get_stats(reference_time)
        assert stats["total_records"] == 4
        assert stats["match_count"] == 2
        assert stats["no_match_count"] == 1
        assert stats["error_count"] == 1

    def test_clear_expired_records(self):
        """Should remove expired records from history"""
        history = EnrichmentHistory(history_ttl_hours=1)
        
        # Add old record
        old_time = (datetime.utcnow() - timedelta(hours=2)).isoformat() + "Z"
        history.add_record({
            "query_value": "old.com",
            "ioc_type": "domain",
            "status": "match",
            "timestamp": old_time
        })
        
        # Add recent record
        recent_time = (datetime.utcnow() - timedelta(minutes=30)).isoformat() + "Z"
        history.add_record({
            "query_value": "recent.com",
            "ioc_type": "domain",
            "status": "match",
            "timestamp": recent_time
        })
        
        # Clear expired
        history.clear_expired()
        
        # Old should be gone
        result = history.check_history("old.com", "domain")
        assert result["in_history"] is False
        
        # Recent should remain
        result = history.check_history("recent.com", "domain")
        assert result["in_history"] is True

    def test_canonicalize_ioc_value(self):
        """Should canonicalize IOC values for consistent deduplication"""
        history = EnrichmentHistory()
        
        # Test domain canonicalization
        assert history._canonicalize("EXAMPLE.COM", "domain") == "example.com"
        assert history._canonicalize("example.com.", "domain") == "example.com"
        
        # Test IP canonicalization (should remain unchanged)
        assert history._canonicalize("8.8.8.8", "ipv4") == "8.8.8.8"
        
        # Test email canonicalization
        assert history._canonicalize("User@Example.COM", "email") == "user@example.com"

    def test_duplicate_detection_prevents_multiple_adds(self):
        """Should update existing record instead of creating duplicate"""
        history = EnrichmentHistory()
        
        # Add initial record
        history.add_record({
            "query_value": "example.com",
            "ioc_type": "domain",
            "status": "no_match",
            "timestamp": "2026-01-15T10:00:00Z"
        })
        
        # Update with new data
        history.add_record({
            "query_value": "example.com",
            "ioc_type": "domain",
            "status": "match",
            "match_count": 3,
            "timestamp": "2026-01-15T11:00:00Z"
        })
        
        # Should have only one record
        reference_time = datetime(2026, 1, 15, 12, 0, 0)
        result = history.check_history("example.com", "domain", reference_time)
        assert result["in_history"] is True
        assert result["record"]["status"] == "match"
        assert result["record"]["match_count"] == 3
