"""
Enrichment Rules Engine for OpenCTI module.

Provides configurable filtering and rules for IOC enrichment decisions.
"""
import logging
import re
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Pattern


logger = logging.getLogger(__name__)


@dataclass
class EnrichmentRule:
    """Definition of a single enrichment rule."""
    name: str
    min_confidence: int = 0
    min_score: int = 0
    required_labels: List[str] = field(default_factory=list)
    excluded_labels: List[str] = field(default_factory=list)
    entity_types: List[str] = field(default_factory=list)
    description: str = ""

    def __post_init__(self):
        """Validate rule configuration."""
        if self.min_confidence < 0 or self.min_confidence > 100:
            raise ValueError(f"min_confidence must be between 0 and 100, got {self.min_confidence}")
        if self.min_score < 0:
            raise ValueError(f"min_score must be >= 0, got {self.min_score}")


class RulesEngine:
    """
    Enrichment filtering and rules engine for OpenCTI IOC processing.
    
    Provides filtering capabilities based on:
    - Confidence thresholds
    - Match scores
    - Label inclusion/exclusion
    - Entity type filtering
    - Safe IOC patterns (e.g., Google DNS, localhost)
    """

    # Default safe patterns to skip enrichment
    DEFAULT_SAFE_PATTERNS: List[str] = [
        r'^8\.8\.\d+\.\d+$',           # Google DNS
        r'^8\.8\.4\.4$',               # Google DNS secondary
        r'^1\.1\.\d+\.\d+$',           # Cloudflare DNS
        r'^1\.0\.0\.1$',               # Cloudflare DNS secondary
        r'^localhost$',                # Localhost
        r'^127\.\d+\.\d+\.\d+$',       # Loopback range
        r'^0\.0\.0\.0$',               # Null route
        r'^255\.255\.255\.255$',       # Broadcast
    ]

    def __init__(
        self,
        rules: Optional[List[EnrichmentRule]] = None,
        min_confidence: Optional[int] = None,
        min_score: Optional[int] = None,
        required_labels: Optional[List[str]] = None,
        excluded_labels: Optional[List[str]] = None,
        safe_patterns: Optional[List[str]] = None
    ):
        """
        Initialize the rules engine.
        
        Args:
            rules: List of EnrichmentRule objects
            min_confidence: Global minimum confidence threshold (0-100)
            min_score: Global minimum score threshold
            required_labels: Labels that matches must have
            excluded_labels: Labels that matches must not have
            safe_patterns: Custom safe IOC patterns (regex strings)
        """
        self.rules = rules or []
        self.min_confidence = min_confidence or 0
        self.min_score = min_score or 0
        self.required_labels = required_labels or []
        self.excluded_labels = excluded_labels or []
        
        # Compile safe patterns for efficiency
        self._safe_patterns: List[Pattern] = []
        patterns = safe_patterns or self.DEFAULT_SAFE_PATTERNS
        for pattern in patterns:
            try:
                self._safe_patterns.append(re.compile(pattern, re.IGNORECASE))
            except re.error as e:
                logger.warning(f"Invalid safe pattern '{pattern}': {e}")
        
        logger.info(f"RulesEngine initialized with {len(self.rules)} rules, "
                   f"{len(self._safe_patterns)} safe patterns")

    def filter_matches(self, matches: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Filter matches based on configured rules and thresholds.
        
        Args:
            matches: List of match dictionaries with keys like 'confidence', 
                    'score', 'labels', 'entity_type'
        
        Returns:
            Filtered list of matches that pass all rules
        """
        if not matches:
            return []
        
        filtered = matches.copy()
        
        # Apply global confidence filter
        if self.min_confidence > 0:
            before = len(filtered)
            filtered = [m for m in filtered if m.get('confidence', 0) >= self.min_confidence]
            if before != len(filtered):
                logger.debug(f"Confidence filter removed {before - len(filtered)} matches")
        
        # Apply global score filter
        if self.min_score > 0:
            before = len(filtered)
            filtered = [m for m in filtered if m.get('score', 0) >= self.min_score]
            if before != len(filtered):
                logger.debug(f"Score filter removed {before - len(filtered)} matches")
        
        # Apply global required labels filter
        if self.required_labels:
            before = len(filtered)
            filtered = [
                m for m in filtered
                if any(label in m.get('labels', []) for label in self.required_labels)
            ]
            if before != len(filtered):
                logger.debug(f"Required labels filter removed {before - len(filtered)} matches")
        
        # Apply global excluded labels filter
        if self.excluded_labels:
            before = len(filtered)
            filtered = [
                m for m in filtered
                if not any(label in m.get('labels', []) for label in self.excluded_labels)
            ]
            if before != len(filtered):
                logger.debug(f"Excluded labels filter removed {before - len(filtered)} matches")
        
        # Apply individual rule filters
        for rule in self.rules:
            before = len(filtered)
            
            # Rule-specific confidence
            if rule.min_confidence > 0:
                filtered = [
                    m for m in filtered
                    if m.get('confidence', 0) >= rule.min_confidence
                ]
            
            # Rule-specific score
            if rule.min_score > 0:
                filtered = [
                    m for m in filtered
                    if m.get('score', 0) >= rule.min_score
                ]
            
            # Rule-specific required labels
            if rule.required_labels:
                filtered = [
                    m for m in filtered
                    if any(label in m.get('labels', []) for label in rule.required_labels)
                ]
            
            # Rule-specific excluded labels
            if rule.excluded_labels:
                filtered = [
                    m for m in filtered
                    if not any(label in m.get('labels', []) for label in rule.excluded_labels)
                ]
            
            # Rule-specific entity types
            if rule.entity_types:
                filtered = [
                    m for m in filtered
                    if m.get('entity_type') in rule.entity_types
                ]
            
            if before != len(filtered):
                logger.debug(f"Rule '{rule.name}' removed {before - len(filtered)} matches")
        
        logger.info(f"Filter matches: {len(matches)} -> {len(filtered)}")
        return filtered

    def should_enrich_ioc(self, ioc_value: str, ioc_type: str = None) -> bool:
        """
        Determine if an IOC should be enriched based on rules.
        
        Args:
            ioc_value: The IOC value (IP, domain, hash, etc.)
            ioc_type: Optional IOC type (ipv4-addr, domain-name, etc.)
        
        Returns:
            True if IOC should be enriched, False if it should be skipped
        """
        # Check against safe patterns
        for pattern in self._safe_patterns:
            if pattern.match(ioc_value):
                logger.debug(f"Skipping safe IOC '{ioc_value}' (matched pattern)")
                return False
        
        # Future: Add type-specific rules
        # e.g., skip certain internal IP ranges, known safe TLDs, etc.
        
        return True

    def add_rule(self, rule: EnrichmentRule) -> None:
        """Add a rule to the engine."""
        self.rules.append(rule)
        logger.info(f"Added rule '{rule.name}' to engine")

    def remove_rule(self, rule_name: str) -> bool:
        """
        Remove a rule by name.
        
        Args:
            rule_name: Name of the rule to remove
        
        Returns:
            True if rule was removed, False if not found
        """
        for i, rule in enumerate(self.rules):
            if rule.name == rule_name:
                self.rules.pop(i)
                logger.info(f"Removed rule '{rule_name}' from engine")
                return True
        logger.warning(f"Rule '{rule_name}' not found in engine")
        return False

    def get_matching_rules(self, match: Dict[str, Any]) -> List[str]:
        """
        Get list of rule names that match the given data.
        
        Args:
            match: Match dictionary to evaluate
        
        Returns:
            List of rule names that match
        """
        matching = []
        
        for rule in self.rules:
            is_match = True
            
            if rule.min_confidence > 0 and match.get('confidence', 0) < rule.min_confidence:
                is_match = False
            
            if rule.min_score > 0 and match.get('score', 0) < rule.min_score:
                is_match = False
            
            if rule.required_labels:
                if not any(label in match.get('labels', []) for label in rule.required_labels):
                    is_match = False
            
            if rule.excluded_labels:
                if any(label in match.get('labels', []) for label in rule.excluded_labels):
                    is_match = False
            
            if rule.entity_types:
                if match.get('entity_type') not in rule.entity_types:
                    is_match = False
            
            if is_match:
                matching.append(rule.name)
        
        return matching

    def to_dict(self) -> Dict[str, Any]:
        """Export engine configuration to dictionary."""
        return {
            'rules': [
                {
                    'name': r.name,
                    'min_confidence': r.min_confidence,
                    'min_score': r.min_score,
                    'required_labels': r.required_labels,
                    'excluded_labels': r.excluded_labels,
                    'entity_types': r.entity_types,
                    'description': r.description
                }
                for r in self.rules
            ],
            'min_confidence': self.min_confidence,
            'min_score': self.min_score,
            'required_labels': self.required_labels,
            'excluded_labels': self.excluded_labels,
            'safe_patterns': [p.pattern for p in self._safe_patterns]
        }
