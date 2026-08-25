"""
Comprehensive tests for the OpenCTI Enrichment Rules Engine.

Tests cover:
- RulesEngine initialization and configuration
- Filter operations (confidence, score, labels, entity types)
- Safe IOC pattern matching
- Rule management (add, remove, get_matching)
- Default rules and presets
- Edge cases and error handling
"""
import pytest
import re
from unittest.mock import Mock, patch

from iris_opencti_module.opencti_handler.rules_engine import (
    RulesEngine,
    EnrichmentRule,
)
from iris_opencti_module.opencti_enrichment_rules import (
    DEFAULT_ENRICHMENT_RULES,
    ENRICHMENT_PRESETS,
    get_rules_preset,
    create_custom_rule,
)


# ============================================================================
# EnrichmentRule Tests
# ============================================================================

class TestEnrichmentRule:
    """Tests for the EnrichmentRule dataclass."""

    def test_rule_creation_minimal(self):
        """Test creating a rule with only required fields."""
        rule = EnrichmentRule(name="test_rule")
        assert rule.name == "test_rule"
        assert rule.min_confidence == 0
        assert rule.min_score == 0
        assert rule.required_labels == []
        assert rule.excluded_labels == []
        assert rule.entity_types == []
        assert rule.description == ""

    def test_rule_creation_full(self):
        """Test creating a rule with all fields."""
        rule = EnrichmentRule(
            name="full_rule",
            min_confidence=75,
            min_score=60,
            required_labels=["malicious"],
            excluded_labels=["safe"],
            entity_types=["ipv4-addr", "domain-name"],
            description="A full rule"
        )
        assert rule.name == "full_rule"
        assert rule.min_confidence == 75
        assert rule.min_score == 60
        assert rule.required_labels == ["malicious"]
        assert rule.excluded_labels == ["safe"]
        assert rule.entity_types == ["ipv4-addr", "domain-name"]
        assert rule.description == "A full rule"

    def test_rule_invalid_confidence_negative(self):
        """Test that negative confidence raises ValueError."""
        with pytest.raises(ValueError, match="min_confidence must be between 0 and 100"):
            EnrichmentRule(name="invalid", min_confidence=-10)

    def test_rule_invalid_confidence_over_100(self):
        """Test that confidence > 100 raises ValueError."""
        with pytest.raises(ValueError, match="min_confidence must be between 0 and 100"):
            EnrichmentRule(name="invalid", min_confidence=150)

    def test_rule_invalid_score_negative(self):
        """Test that negative score raises ValueError."""
        with pytest.raises(ValueError, match="min_score must be >= 0"):
            EnrichmentRule(name="invalid", min_score=-5)

    def test_rule_valid_boundaries(self):
        """Test valid boundary values."""
        rule_min = EnrichmentRule(name="min", min_confidence=0, min_score=0)
        rule_max = EnrichmentRule(name="max", min_confidence=100, min_score=1000)
        assert rule_min.min_confidence == 0
        assert rule_max.min_confidence == 100


# ============================================================================
# RulesEngine Initialization Tests
# ============================================================================

class TestRulesEngineInit:
    """Tests for RulesEngine initialization."""

    def test_engine_empty_init(self):
        """Test engine initialized with defaults."""
        engine = RulesEngine()
        assert engine.rules == []
        assert engine.min_confidence == 0
        assert engine.min_score == 0
        assert engine.required_labels == []
        assert engine.excluded_labels == []
        assert len(engine._safe_patterns) > 0  # Has default patterns

    def test_engine_with_rules(self):
        """Test engine initialized with rules."""
        rules = [
            EnrichmentRule(name="rule1", min_confidence=50),
            EnrichmentRule(name="rule2", min_score=60),
        ]
        engine = RulesEngine(rules=rules)
        assert len(engine.rules) == 2
        assert engine.rules[0].name == "rule1"

    def test_engine_with_global_filters(self):
        """Test engine initialized with global filter thresholds."""
        engine = RulesEngine(
            min_confidence=70,
            min_score=50,
            required_labels=["malicious"],
            excluded_labels=["safe"]
        )
        assert engine.min_confidence == 70
        assert engine.min_score == 50
        assert engine.required_labels == ["malicious"]
        assert engine.excluded_labels == ["safe"]

    def test_engine_custom_safe_patterns(self):
        """Test engine with custom safe patterns."""
        engine = RulesEngine(safe_patterns=[r'^192\.168\.\d+\.\d+$'])
        assert len(engine._safe_patterns) == 1
        assert engine._safe_patterns[0].pattern == r'^192\.168\.\d+\.\d+$'

    def test_engine_invalid_pattern_warning(self):
        """Test that invalid patterns are logged but don't crash."""
        with patch('logging.Logger.warning') as mock_warn:
            engine = RulesEngine(safe_patterns=[r'[invalid(regex'])
            # Engine should still be created
            assert engine is not True  # Just verify it didn't crash

    def test_engine_safe_pattern_compilation(self):
        """Test that safe patterns are compiled as regex."""
        engine = RulesEngine()
        for pattern in engine._safe_patterns:
            assert isinstance(pattern, type(re.compile('')))


# ============================================================================
# Filter Matches Tests
# ============================================================================

class TestFilterMatches:
    """Tests for the filter_matches method."""

    def test_filter_empty_matches(self):
        """Test filtering empty list returns empty."""
        engine = RulesEngine(min_confidence=50)
        result = engine.filter_matches([])
        assert result == []

    def test_filter_by_confidence(self):
        """Test filtering by confidence threshold."""
        engine = RulesEngine(min_confidence=50)
        
        matches = [
            {"confidence": 30, "name": "Low"},
            {"confidence": 50, "name": "Exact min"},
            {"confidence": 70, "name": "Medium"},
            {"confidence": 90, "name": "High"},
        ]
        
        filtered = engine.filter_matches(matches)
        assert len(filtered) == 3
        assert all(m["confidence"] >= 50 for m in filtered)
        assert filtered[0]["name"] == "Exact min"

    def test_filter_by_score(self):
        """Test filtering by score threshold."""
        engine = RulesEngine(min_score=60)
        
        matches = [
            {"score": 40, "name": "Low"},
            {"score": 60, "name": "Exact min"},
            {"score": 80, "name": "High"},
        ]
        
        filtered = engine.filter_matches(matches)
        assert len(filtered) == 2
        assert all(m["score"] >= 60 for m in filtered)

    def test_filter_by_required_labels(self):
        """Test filtering by required labels."""
        engine = RulesEngine(required_labels=["malicious"])
        
        matches = [
            {"labels": ["suspicious"], "name": "Not malicious"},
            {"labels": ["malicious"], "name": "Malicious"},
            {"labels": ["malicious", "phishing"], "name": "Both"},
            {"labels": [], "name": "No labels"},
        ]
        
        filtered = engine.filter_matches(matches)
        assert len(filtered) == 2
        assert all("malicious" in m["labels"] for m in filtered)

    def test_filter_by_excluded_labels(self):
        """Test filtering by excluded labels."""
        engine = RulesEngine(excluded_labels=["safe", "whitelisted"])
        
        matches = [
            {"labels": ["malicious"], "name": "Bad"},
            {"labels": ["safe"], "name": "Safe"},
            {"labels": ["whitelisted"], "name": "White"},
            {"labels": ["malicious", "safe"], "name": "Mixed"},
        ]
        
        filtered = engine.filter_matches(matches)
        assert len(filtered) == 1
        assert filtered[0]["name"] == "Bad"

    def test_filter_by_entity_types(self):
        """Test filtering by entity types via rules."""
        rule = EnrichmentRule(name="ip_only", entity_types=["ipv4-addr", "ipv6-addr"])
        engine = RulesEngine(rules=[rule])
        
        matches = [
            {"entity_type": "ipv4-addr", "name": "IPv4"},
            {"entity_type": "domain-name", "name": "Domain"},
            {"entity_type": "ipv6-addr", "name": "IPv6"},
            {"entity_type": "file-hash", "name": "Hash"},
        ]
        
        filtered = engine.filter_matches(matches)
        assert len(filtered) == 2
        assert all(m["entity_type"] in ["ipv4-addr", "ipv6-addr"] for m in filtered)

    def test_filter_combined_criteria(self):
        """Test filtering with multiple criteria combined."""
        engine = RulesEngine(
            min_confidence=50,
            excluded_labels=["safe"]
        )
        
        matches = [
            {"confidence": 30, "labels": ["malicious"], "name": "Low conf"},
            {"confidence": 70, "labels": ["safe"], "name": "Safe high"},
            {"confidence": 80, "labels": ["malicious"], "name": "Good"},
            {"confidence": 60, "labels": [], "name": "No labels"},
        ]
        
        filtered = engine.filter_matches(matches)
        assert len(filtered) == 2
        names = {m["name"] for m in filtered}
        assert names == {"Good", "No labels"}

    def test_filter_rule_specific_criteria(self):
        """Test filtering with rule-specific criteria."""
        rules = [
            EnrichmentRule(name="high_conf", min_confidence=80),
            EnrichmentRule(name="malicious_only", required_labels=["malicious"]),
        ]
        engine = RulesEngine(rules=rules)
        
        matches = [
            {"confidence": 90, "labels": ["malicious"], "name": "Perfect"},
            {"confidence": 90, "labels": ["suspicious"], "name": "High conf not malicious"},
            {"confidence": 50, "labels": ["malicious"], "name": "Malicious low conf"},
        ]
        
        filtered = engine.filter_matches(matches)
        # Only "Perfect" passes both rules
        assert len(filtered) == 1
        assert filtered[0]["name"] == "Perfect"

    def test_filter_preserves_original(self):
        """Test that filtering doesn't modify original list."""
        engine = RulesEngine(min_confidence=50)
        matches = [
            {"confidence": 30, "name": "Low"},
            {"confidence": 70, "name": "High"},
        ]
        original_len = len(matches)
        
        engine.filter_matches(matches)
        assert len(matches) == original_len


# ============================================================================
# Should Enrich IOC Tests
# ============================================================================

class TestShouldEnrichIOC:
    """Tests for the should_enrich_ioc method."""

    def test_skip_google_dns(self):
        """Test that Google DNS IPs are skipped."""
        engine = RulesEngine()
        
        assert engine.should_enrich_ioc("8.8.8.8") is False
        assert engine.should_enrich_ioc("8.8.4.4") is False
        assert engine.should_enrich_ioc("8.8.1.1") is False

    def test_skip_cloudflare_dns(self):
        """Test that Cloudflare DNS IPs are skipped."""
        engine = RulesEngine()
        
        assert engine.should_enrich_ioc("1.1.1.1") is False
        assert engine.should_enrich_ioc("1.0.0.1") is False

    def test_skip_localhost(self):
        """Test that localhost is skipped."""
        engine = RulesEngine()
        
        assert engine.should_enrich_ioc("localhost") is False
        assert engine.should_enrich_ioc("LOCALHOST") is False  # Case insensitive

    def test_skip_loopback_range(self):
        """Test that loopback range is skipped."""
        engine = RulesEngine()
        
        assert engine.should_enrich_ioc("127.0.0.1") is False
        assert engine.should_enrich_ioc("127.255.255.255") is False

    def test_skip_null_and_broadcast(self):
        """Test that null and broadcast addresses are skipped."""
        engine = RulesEngine()
        
        assert engine.should_enrich_ioc("0.0.0.0") is False
        assert engine.should_enrich_ioc("255.255.255.255") is False

    def test_enrich_malicious_ip(self):
        """Test that malicious IPs are not skipped."""
        engine = RulesEngine()
        
        assert engine.should_enrich_ioc("192.168.1.100") is True
        assert engine.should_enrich_ioc("45.33.32.156") is True
        assert engine.should_enrich_ioc("evil.example.com") is True

    def test_custom_safe_pattern(self):
        """Test custom safe patterns."""
        engine = RulesEngine(safe_patterns=[r'^10\.\d+\.\d+\.\d+$'])
        
        assert engine.should_enrich_ioc("10.0.0.1") is False
        assert engine.should_enrich_ioc("192.168.1.1") is True

    def test_ioc_type_parameter_ignored(self):
        """Test that ioc_type parameter is accepted (for future use)."""
        engine = RulesEngine()
        
        # Currently type doesn't affect decision, but parameter should be accepted
        assert engine.should_enrich_ioc("8.8.8.8", ioc_type="ipv4-addr") is False
        assert engine.should_enrich_ioc("example.com", ioc_type="domain-name") is True


# ============================================================================
# Rule Management Tests
# ============================================================================

class TestRuleManagement:
    """Tests for rule management methods."""

    def test_add_rule(self):
        """Test adding a rule."""
        engine = RulesEngine()
        rule = EnrichmentRule(name="new_rule", min_confidence=60)
        
        engine.add_rule(rule)
        assert len(engine.rules) == 1
        assert engine.rules[0].name == "new_rule"

    def test_remove_rule_found(self):
        """Test removing an existing rule."""
        rules = [
            EnrichmentRule(name="rule1"),
            EnrichmentRule(name="rule2"),
            EnrichmentRule(name="rule3"),
        ]
        engine = RulesEngine(rules=rules)
        
        result = engine.remove_rule("rule2")
        assert result is True
        assert len(engine.rules) == 2
        assert engine.rules[0].name == "rule1"
        assert engine.rules[1].name == "rule3"

    def test_remove_rule_not_found(self):
        """Test removing a non-existent rule."""
        engine = RulesEngine()
        
        result = engine.remove_rule("nonexistent")
        assert result is False
        assert len(engine.rules) == 0

    def test_get_matching_rules(self):
        """Test getting rules that match given data."""
        rules = [
            EnrichmentRule(name="high_conf", min_confidence=70),
            EnrichmentRule(name="malicious", required_labels=["malicious"]),
            EnrichmentRule(name="low_score", min_score=30),
        ]
        engine = RulesEngine(rules=rules)
        
        match = {
            "confidence": 80,
            "score": 50,
            "labels": ["malicious", "suspicious"]
        }
        
        matching = engine.get_matching_rules(match)
        assert "high_conf" in matching
        assert "malicious" in matching
        assert "low_score" in matching

    def test_get_matching_rules_none(self):
        """Test when no rules match."""
        rules = [EnrichmentRule(name="strict", min_confidence=95)]
        engine = RulesEngine(rules=rules)
        
        match = {"confidence": 50}
        matching = engine.get_matching_rules(match)
        assert matching == []


# ============================================================================
# To Dict Export Tests
# ============================================================================

class TestToDict:
    """Tests for the to_dict export method."""

    def test_to_dict_empty(self):
        """Test exporting empty engine config."""
        engine = RulesEngine()
        config = engine.to_dict()
        
        assert config["rules"] == []
        assert config["min_confidence"] == 0
        assert config["min_score"] == 0
        assert "safe_patterns" in config

    def test_to_dict_with_rules(self):
        """Test exporting engine with rules."""
        rules = [
            EnrichmentRule(
                name="test_rule",
                min_confidence=70,
                min_score=50,
                required_labels=["malicious"],
                excluded_labels=["safe"],
                entity_types=["ipv4-addr"],
                description="Test description"
            ),
        ]
        engine = RulesEngine(rules=rules, min_confidence=60)
        config = engine.to_dict()
        
        assert len(config["rules"]) == 1
        assert config["rules"][0]["name"] == "test_rule"
        assert config["rules"][0]["min_confidence"] == 70
        assert config["rules"][0]["description"] == "Test description"
        assert config["min_confidence"] == 60


# ============================================================================
# Default Rules Tests
# ============================================================================

class TestDefaultRules:
    """Tests for default rules configuration."""

    def test_default_rules_exist(self):
        """Test that default rules are defined."""
        assert len(DEFAULT_ENRICHMENT_RULES) > 0

    def test_default_rules_have_names(self):
        """Test that all default rules have unique names."""
        names = [r.name for r in DEFAULT_ENRICHMENT_RULES]
        assert len(names) == len(set(names))  # All unique

    def test_default_rules_valid(self):
        """Test that all default rules are valid."""
        for rule in DEFAULT_ENRICHMENT_RULES:
            # Should not raise
            assert rule.name is not None
            assert 0 <= rule.min_confidence <= 100
            assert rule.min_score >= 0

    def test_preset_names(self):
        """Test that all presets are defined."""
        expected = {"conservative", "balanced", "aggressive", "malware_focus", "phishing_focus"}
        assert set(ENRICHMENT_PRESETS.keys()) == expected

    def test_get_preset_balanced(self):
        """Test getting balanced preset."""
        rules = get_rules_preset("balanced")
        assert rules == DEFAULT_ENRICHMENT_RULES

    def test_get_preset_conservative(self):
        """Test getting conservative preset."""
        rules = get_rules_preset("conservative")
        assert len(rules) == 2
        assert rules[0].min_confidence == 80

    def test_get_preset_invalid(self):
        """Test getting invalid preset raises error."""
        with pytest.raises(ValueError, match="Unknown preset"):
            get_rules_preset("invalid_preset")

    def test_create_custom_rule(self):
        """Test creating custom rule via factory."""
        rule = create_custom_rule(
            name="my_rule",
            min_confidence=75,
            required_labels=["threat"],
            description="My custom rule"
        )
        assert rule.name == "my_rule"
        assert rule.min_confidence == 75
        assert rule.required_labels == ["threat"]
        assert rule.description == "My custom rule"


# ============================================================================
# Edge Cases and Integration Tests
# ============================================================================

class TestEdgeCases:
    """Tests for edge cases and integration scenarios."""

    def test_filter_with_missing_fields(self):
        """Test filtering when matches have missing fields."""
        engine = RulesEngine(min_confidence=50)
        
        matches = [
            {"name": "No confidence"},  # Missing confidence
            {"confidence": 70, "name": "Has confidence"},
            {},  # Empty dict
        ]
        
        # Should handle gracefully
        filtered = engine.filter_matches(matches)
        # Only the one with confidence >= 50 should pass
        assert len(filtered) == 1

    def test_filter_case_sensitivity_labels(self):
        """Test that label filtering is case-sensitive."""
        engine = RulesEngine(required_labels=["Malicious"])
        
        matches = [
            {"labels": ["malicious"], "name": "Lowercase"},
            {"labels": ["Malicious"], "name": "Capitalized"},
            {"labels": ["MALICIOUS"], "name": "Uppercase"},
        ]
        
        filtered = engine.filter_matches(matches)
        # Only exact match should pass
        assert len(filtered) == 1
        assert filtered[0]["name"] == "Capitalized"

    def test_multiple_rules_same_criteria(self):
        """Test engine with multiple rules having same criteria."""
        rules = [
            EnrichmentRule(name="rule1", min_confidence=50),
            EnrichmentRule(name="rule2", min_confidence=50),
        ]
        engine = RulesEngine(rules=rules)
        
        matches = [
            {"confidence": 30},
            {"confidence": 70},
        ]
        
        filtered = engine.filter_matches(matches)
        # Both rules apply same filter, should still work
        assert len(filtered) == 1

    def test_engine_state_persistence(self):
        """Test that engine state persists across operations."""
        engine = RulesEngine(min_confidence=50)
        
        # First filter
        matches1 = [{"confidence": 70}, {"confidence": 30}]
        result1 = engine.filter_matches(matches1)
        
        # Second filter with different data
        matches2 = [{"confidence": 80}, {"confidence": 40}]
        result2 = engine.filter_matches(matches2)
        
        # Both should use same threshold
        assert len(result1) == 1
        assert len(result2) == 1

    def test_large_batch_filter(self):
        """Test filtering a large batch of matches."""
        engine = RulesEngine(min_confidence=50)
        
        matches = [{"confidence": i % 100, "id": i} for i in range(1000)]
        filtered = engine.filter_matches(matches)
        
        assert len(filtered) == 500  # Half should pass
        assert all(m["confidence"] >= 50 for m in filtered)

    def test_rule_with_all_criteria(self):
        """Test rule with all possible criteria."""
        rule = EnrichmentRule(
            name="comprehensive",
            min_confidence=60,
            min_score=50,
            required_labels=["malicious"],
            excluded_labels=["false-positive"],
            entity_types=["ipv4-addr", "domain-name"]
        )
        engine = RulesEngine(rules=[rule])
        
        matches = [
            {
                "confidence": 70,
                "score": 60,
                "labels": ["malicious"],
                "entity_type": "ipv4-addr"
            },
            {
                "confidence": 70,
                "score": 60,
                "labels": ["malicious", "false-positive"],
                "entity_type": "ipv4-addr"
            },
            {
                "confidence": 70,
                "score": 60,
                "labels": ["malicious"],
                "entity_type": "url"  # Wrong type
            },
        ]
        
        filtered = engine.filter_matches(matches)
        assert len(filtered) == 1
        assert filtered[0]["entity_type"] == "ipv4-addr"


# ============================================================================
# Run tests
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
