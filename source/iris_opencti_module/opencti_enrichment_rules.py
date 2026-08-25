"""
Default enrichment rules for OpenCTI module.

Defines production-ready rules for IOC enrichment filtering.
"""
from iris_opencti_module.opencti_handler.rules_engine import EnrichmentRule


# Default rules for enrichment filtering
DEFAULT_ENRICHMENT_RULES = [
    EnrichmentRule(
        name="high_confidence_only",
        min_confidence=50,
        description="Only enrich high-confidence matches (>=50%)"
    ),
    EnrichmentRule(
        name="exclude_safe_entities",
        excluded_labels=["safe", "whitelisted", "clean"],
        description="Exclude entities marked as safe or whitelisted"
    ),
    EnrichmentRule(
        name="malicious_only",
        required_labels=["malicious", "suspicious"],
        description="Only enrich entities with malicious or suspicious labels"
    ),
    EnrichmentRule(
        name="threat_intel_priority",
        min_score=60,
        excluded_labels=["unverified", "community-only"],
        description="Prioritize high-scoring threat intelligence"
    ),
    EnrichmentRule(
        name="exclude_inactive",
        excluded_labels=["inactive", "deprecated", "retired"],
        description="Exclude inactive or deprecated entities"
    ),
]

# Rule configuration for different use cases
ENRICHMENT_PRESETS = {
    "conservative": [
        EnrichmentRule(
            name="very_high_confidence",
            min_confidence=80,
            min_score=70,
            description="Very strict: only very high confidence matches"
        ),
        EnrichmentRule(
            name="verified_threats",
            required_labels=["malicious"],
            excluded_labels=["unverified", "suspicious"],
            description="Only verified malicious entities"
        ),
    ],
    
    "balanced": DEFAULT_ENRICHMENT_RULES,
    
    "aggressive": [
        EnrichmentRule(
            name="low_threshold",
            min_confidence=20,
            description="Low threshold: enrich most matches"
        ),
        EnrichmentRule(
            name="include_suspicious",
            required_labels=["malicious", "suspicious", "unverified"],
            description="Include suspicious and unverified entities"
        ),
    ],
    
    "malware_focus": [
        EnrichmentRule(
            name="high_confidence",
            min_confidence=60,
            description="High confidence baseline"
        ),
        EnrichmentRule(
            name="malware_related",
            required_labels=["malware", "apt", "ransomware", "botnet", "c2"],
            description="Focus on malware-related indicators"
        ),
    ],
    
    "phishing_focus": [
        EnrichmentRule(
            name="domain_priority",
            entity_types=["domain-name", "url", "email-addr"],
            min_confidence=40,
            description="Focus on domain/email indicators"
        ),
        EnrichmentRule(
            name="phishing_labels",
            required_labels=["phishing", "spam", "social-engineering"],
            description="Prioritize phishing-related indicators"
        ),
    ],
}


def get_rules_preset(preset_name: str = "balanced") -> list:
    """
    Get a predefined set of rules by preset name.
    
    Args:
        preset_name: Name of the preset ('conservative', 'balanced', 'aggressive', 
                    'malware_focus', 'phishing_focus')
    
    Returns:
        List of EnrichmentRule objects
    """
    if preset_name not in ENRICHMENT_PRESETS:
        raise ValueError(f"Unknown preset: {preset_name}. Available: {list(ENRICHMENT_PRESETS.keys())}")
    
    return ENRICHMENT_PRESETS[preset_name]


def create_custom_rule(
    name: str,
    min_confidence: int = 0,
    min_score: int = 0,
    required_labels: list = None,
    excluded_labels: list = None,
    entity_types: list = None,
    description: str = ""
) -> EnrichmentRule:
    """
    Factory function to create a custom enrichment rule.
    
    Args:
        name: Rule name (must be unique)
        min_confidence: Minimum confidence threshold (0-100)
        min_score: Minimum score threshold
        required_labels: Labels that must be present
        excluded_labels: Labels that must not be present
        entity_types: Specific entity types to match
        description: Human-readable description
    
    Returns:
        EnrichmentRule instance
    """
    return EnrichmentRule(
        name=name,
        min_confidence=min_confidence,
        min_score=min_score,
        required_labels=required_labels or [],
        excluded_labels=excluded_labels or [],
        entity_types=entity_types or [],
        description=description
    )
