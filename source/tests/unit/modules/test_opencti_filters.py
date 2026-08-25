#!/usr/bin/env python3
"""
Comprehensive tests for OpenCTI filtering functionality.

Tests follow TDD principles: write failing test first, verify it fails,
then implement to pass.
"""

import pytest
from datetime import datetime, timedelta
from iris_opencti_module.opencti_handler.filters import (
    BaseFilter,
    EntityFilter,
    LabelFilter,
    DateRangeFilter,
    ScoreFilter,
    ConfidenceFilter,
    AndFilter,
    OrFilter,
    NotFilter,
    FilterBuilder,
    apply_filters,
)


# ============================================================================
# EntityFilter Tests
# ============================================================================

class TestEntityFilter:
    """Tests for EntityFilter class."""

    def test_single_entity_type_match(self):
        """EntityFilter should match entities of specified type."""
        filter = EntityFilter('Indicator')
        entity = {'entity_type': 'Indicator', 'name': 'test'}

        assert filter.matches(entity) is True

    def test_single_entity_type_no_match(self):
        """EntityFilter should not match different entity types."""
        filter = EntityFilter('Indicator')
        entity = {'entity_type': 'Malware', 'name': 'test'}

        assert filter.matches(entity) is False

    def test_multiple_entity_types_match(self):
        """EntityFilter should match any of specified types."""
        filter = EntityFilter(['Indicator', 'Malware'])
        entity1 = {'entity_type': 'Indicator'}
        entity2 = {'entity_type': 'Malware'}
        entity3 = {'entity_type': 'AttackPattern'}

        assert filter.matches(entity1) is True
        assert filter.matches(entity2) is True
        assert filter.matches(entity3) is False

    def test_exclude_entity_type(self):
        """EntityFilter with exclude=True should exclude specified types."""
        filter = EntityFilter('Indicator', exclude=True)
        entity1 = {'entity_type': 'Indicator'}
        entity2 = {'entity_type': 'Malware'}

        assert filter.matches(entity1) is False
        assert filter.matches(entity2) is True

    def test_exclude_multiple_entity_types(self):
        """EntityFilter should exclude multiple types when exclude=True."""
        filter = EntityFilter(['Indicator', 'Malware'], exclude=True)
        entity1 = {'entity_type': 'Indicator'}
        entity2 = {'entity_type': 'Malware'}
        entity3 = {'entity_type': 'AttackPattern'}

        assert filter.matches(entity1) is False
        assert filter.matches(entity2) is False
        assert filter.matches(entity3) is True

    def test_entity_filter_repr(self):
        """EntityFilter __repr__ should be readable."""
        filter_include = EntityFilter('Indicator')
        filter_exclude = EntityFilter('Indicator', exclude=True)

        assert 'Indicator' in repr(filter_include)
        assert '!' in repr(filter_exclude)


# ============================================================================
# LabelFilter Tests
# ============================================================================

class TestLabelFilter:
    """Tests for LabelFilter class."""

    def test_single_label_match(self):
        """LabelFilter should match entities with specified label."""
        filter = LabelFilter('malicious')
        entity = {
            'entity_type': 'Indicator',
            'objectLabel': [{'value': 'malicious', 'color': 'red'}]
        }

        assert filter.matches(entity) is True

    def test_single_label_no_match(self):
        """LabelFilter should not match entities without label."""
        filter = LabelFilter('malicious')
        entity = {
            'entity_type': 'Indicator',
            'objectLabel': [{'value': 'suspicious', 'color': 'yellow'}]
        }

        assert filter.matches(entity) is False

    def test_require_all_labels(self):
        """LabelFilter with require_all=True needs all labels."""
        filter = LabelFilter(['malicious', 'phishing'], require_all=True)
        entity1 = {
            'entity_type': 'Indicator',
            'objectLabel': [
                {'value': 'malicious'},
                {'value': 'phishing'}
            ]
        }
        entity2 = {
            'entity_type': 'Indicator',
            'objectLabel': [{'value': 'malicious'}]
        }

        assert filter.matches(entity1) is True
        assert filter.matches(entity2) is False

    def test_require_any_label(self):
        """LabelFilter with require_all=False needs at least one label."""
        filter = LabelFilter(['malicious', 'phishing'], require_all=False)
        entity1 = {
            'entity_type': 'Indicator',
            'objectLabel': [{'value': 'malicious'}]
        }
        entity2 = {
            'entity_type': 'Indicator',
            'objectLabel': [{'value': 'phishing'}]
        }
        entity3 = {
            'entity_type': 'Indicator',
            'objectLabel': [{'value': 'safe'}]
        }

        assert filter.matches(entity1) is True
        assert filter.matches(entity2) is True
        assert filter.matches(entity3) is False

    def test_exclude_label(self):
        """LabelFilter with exclude=True should exclude entities with label."""
        filter = LabelFilter('safe', exclude=True)
        entity1 = {
            'entity_type': 'Indicator',
            'objectLabel': [{'value': 'safe'}]
        }
        entity2 = {
            'entity_type': 'Indicator',
            'objectLabel': [{'value': 'malicious'}]
        }

        assert filter.matches(entity1) is False
        assert filter.matches(entity2) is True

    def test_label_filter_case_insensitive(self):
        """LabelFilter should be case-insensitive."""
        filter = LabelFilter('MALICIOUS')
        entity = {
            'entity_type': 'Indicator',
            'objectLabel': [{'value': 'malicious'}]
        }

        assert filter.matches(entity) is True

    def test_label_filter_empty_labels(self):
        """LabelFilter should handle entities without labels."""
        filter = LabelFilter('malicious')
        entity = {
            'entity_type': 'Indicator',
            'objectLabel': []
        }

        assert filter.matches(entity) is False

    def test_label_filter_no_labels_field(self):
        """LabelFilter should handle entities missing labels field."""
        filter = LabelFilter('malicious')
        entity = {'entity_type': 'Indicator'}

        assert filter.matches(entity) is False

    def test_label_filter_repr(self):
        """LabelFilter __repr__ should be readable."""
        filter_all = LabelFilter(['malicious'], require_all=True)
        filter_any = LabelFilter(['malicious'], require_all=False)
        filter_exclude = LabelFilter('safe', exclude=True)

        assert 'all' in repr(filter_all)
        assert 'any' in repr(filter_any)
        assert '!' in repr(filter_exclude)


# ============================================================================
# DateRangeFilter Tests
# ============================================================================

class TestDateRangeFilter:
    """Tests for DateRangeFilter class."""

    def test_date_within_range(self):
        """DateRangeFilter should match dates within range."""
        start = datetime(2024, 1, 1)
        end = datetime(2024, 12, 31)
        filter = DateRangeFilter('valid_from', start, end)
        entity = {
            'entity_type': 'Indicator',
            'valid_from': '2024-06-15T00:00:00Z'
        }

        assert filter.matches(entity) is True

    def test_date_before_range(self):
        """DateRangeFilter should not match dates before range."""
        start = datetime(2024, 1, 1)
        end = datetime(2024, 12, 31)
        filter = DateRangeFilter('valid_from', start, end)
        entity = {
            'entity_type': 'Indicator',
            'valid_from': '2023-06-15T00:00:00Z'
        }

        assert filter.matches(entity) is False

    def test_date_after_range(self):
        """DateRangeFilter should not match dates after range."""
        start = datetime(2024, 1, 1)
        end = datetime(2024, 12, 31)
        filter = DateRangeFilter('valid_from', start, end)
        entity = {
            'entity_type': 'Indicator',
            'valid_from': '2025-06-15T00:00:00Z'
        }

        assert filter.matches(entity) is False

    def test_date_on_start_boundary(self):
        """DateRangeFilter should include start boundary (inclusive)."""
        start = datetime(2024, 1, 1)
        end = datetime(2024, 12, 31)
        filter = DateRangeFilter('valid_from', start, end)
        entity = {
            'entity_type': 'Indicator',
            'valid_from': '2024-01-01T00:00:00Z'
        }

        assert filter.matches(entity) is True

    def test_date_on_end_boundary(self):
        """DateRangeFilter should include end boundary (inclusive)."""
        start = datetime(2024, 1, 1)
        end = datetime(2024, 12, 31)
        filter = DateRangeFilter('valid_from', start, end)
        entity = {
            'entity_type': 'Indicator',
            'valid_from': '2024-12-31T00:00:00Z'
        }

        assert filter.matches(entity) is True

    def test_only_start_date(self):
        """DateRangeFilter with only start should match dates >= start."""
        start = datetime(2024, 1, 1)
        filter = DateRangeFilter('valid_from', start, None)
        entity1 = {'entity_type': 'Indicator', 'valid_from': '2024-06-15'}
        entity2 = {'entity_type': 'Indicator', 'valid_from': '2023-06-15'}

        assert filter.matches(entity1) is True
        assert filter.matches(entity2) is False

    def test_only_end_date(self):
        """DateRangeFilter with only end should match dates <= end."""
        end = datetime(2024, 12, 31)
        filter = DateRangeFilter('valid_from', None, end)
        entity1 = {'entity_type': 'Indicator', 'valid_from': '2024-06-15'}
        entity2 = {'entity_type': 'Indicator', 'valid_from': '2025-06-15'}

        assert filter.matches(entity1) is True
        assert filter.matches(entity2) is False

    def test_filter_different_date_field(self):
        """DateRangeFilter should work with different date fields."""
        start = datetime(2024, 1, 1)
        end = datetime(2024, 12, 31)
        filter = DateRangeFilter('created_at', start, end)
        entity = {
            'entity_type': 'Indicator',
            'created_at': '2024-06-15T00:00:00Z'
        }

        assert filter.matches(entity) is True

    def test_no_date_field(self):
        """DateRangeFilter should return False when date field missing."""
        filter = DateRangeFilter('valid_from', datetime(2024, 1, 1))
        entity = {'entity_type': 'Indicator'}

        assert filter.matches(entity) is False

    def test_invalid_date_format(self):
        """DateRangeFilter should handle invalid date formats gracefully."""
        filter = DateRangeFilter('valid_from', datetime(2024, 1, 1))
        entity = {
            'entity_type': 'Indicator',
            'valid_from': 'not-a-date'
        }

        assert filter.matches(entity) is False

    def test_date_range_filter_repr(self):
        """DateRangeFilter __repr__ should be readable."""
        start = datetime(2024, 1, 1)
        end = datetime(2024, 12, 31)
        filter = DateRangeFilter('valid_from', start, end)

        assert 'valid_from' in repr(filter)
        assert '2024' in repr(filter)


# ============================================================================
# ScoreFilter Tests
# ============================================================================

class TestScoreFilter:
    """Tests for ScoreFilter class."""

    def test_score_within_range(self):
        """ScoreFilter should match scores within range."""
        filter = ScoreFilter(min_score=50, max_score=80)
        entity = {'entity_type': 'Indicator', 'x_opencti_score': 65}

        assert filter.matches(entity) is True

    def test_score_below_range(self):
        """ScoreFilter should not match scores below range."""
        filter = ScoreFilter(min_score=50, max_score=80)
        entity = {'entity_type': 'Indicator', 'x_opencti_score': 30}

        assert filter.matches(entity) is False

    def test_score_above_range(self):
        """ScoreFilter should not match scores above range."""
        filter = ScoreFilter(min_score=50, max_score=80)
        entity = {'entity_type': 'Indicator', 'x_opencti_score': 95}

        assert filter.matches(entity) is False

    def test_score_on_min_boundary(self):
        """ScoreFilter should include minimum boundary (inclusive)."""
        filter = ScoreFilter(min_score=50, max_score=80)
        entity = {'entity_type': 'Indicator', 'x_opencti_score': 50}

        assert filter.matches(entity) is True

    def test_score_on_max_boundary(self):
        """ScoreFilter should include maximum boundary (inclusive)."""
        filter = ScoreFilter(min_score=50, max_score=80)
        entity = {'entity_type': 'Indicator', 'x_opencti_score': 80}

        assert filter.matches(entity) is True

    def test_only_min_score(self):
        """ScoreFilter with only min should match scores >= min."""
        filter = ScoreFilter(min_score=50, max_score=None)
        entity1 = {'entity_type': 'Indicator', 'x_opencti_score': 70}
        entity2 = {'entity_type': 'Indicator', 'x_opencti_score': 30}

        assert filter.matches(entity1) is True
        assert filter.matches(entity2) is False

    def test_only_max_score(self):
        """ScoreFilter with only max should match scores <= max."""
        filter = ScoreFilter(min_score=None, max_score=50)
        entity1 = {'entity_type': 'Indicator', 'x_opencti_score': 30}
        entity2 = {'entity_type': 'Indicator', 'x_opencti_score': 70}

        assert filter.matches(entity1) is True
        assert filter.matches(entity2) is False

    def test_no_score_field(self):
        """ScoreFilter should return False when score field missing."""
        filter = ScoreFilter(min_score=50)
        entity = {'entity_type': 'Indicator'}

        assert filter.matches(entity) is False

    def test_invalid_score_value(self):
        """ScoreFilter should handle invalid score values gracefully."""
        filter = ScoreFilter(min_score=50)
        entity = {'entity_type': 'Indicator', 'x_opencti_score': 'invalid'}

        assert filter.matches(entity) is False

    def test_score_filter_custom_field(self):
        """ScoreFilter should work with custom score field."""
        filter = ScoreFilter(min_score=50, field='custom_score')
        entity = {'entity_type': 'Indicator', 'custom_score': 75}

        assert filter.matches(entity) is True

    def test_score_filter_repr(self):
        """ScoreFilter __repr__ should be readable."""
        filter = ScoreFilter(min_score=50, max_score=80)

        assert 'x_opencti_score' in repr(filter)
        assert '50' in repr(filter)
        assert '80' in repr(filter)


# ============================================================================
# ConfidenceFilter Tests
# ============================================================================

class TestConfidenceFilter:
    """Tests for ConfidenceFilter class."""

    def test_confidence_within_range(self):
        """ConfidenceFilter should match confidence within range."""
        filter = ConfidenceFilter(min_confidence=50, max_confidence=80)
        entity = {'entity_type': 'Indicator', 'confidence': 65}

        assert filter.matches(entity) is True

    def test_confidence_below_range(self):
        """ConfidenceFilter should not match confidence below range."""
        filter = ConfidenceFilter(min_confidence=50, max_confidence=80)
        entity = {'entity_type': 'Indicator', 'confidence': 30}

        assert filter.matches(entity) is False

    def test_confidence_above_range(self):
        """ConfidenceFilter should not match confidence above range."""
        filter = ConfidenceFilter(min_confidence=50, max_confidence=80)
        entity = {'entity_type': 'Indicator', 'confidence': 95}

        assert filter.matches(entity) is False

    def test_no_confidence_field(self):
        """ConfidenceFilter should return False when confidence field missing."""
        filter = ConfidenceFilter(min_confidence=50)
        entity = {'entity_type': 'Indicator'}

        assert filter.matches(entity) is False

    def test_confidence_filter_repr(self):
        """ConfidenceFilter __repr__ should be readable."""
        filter = ConfidenceFilter(min_confidence=50, max_confidence=80)

        assert 'confidence' in repr(filter)


# ============================================================================
# Combined Filter Tests (AndFilter, OrFilter, NotFilter)
# ============================================================================

class TestAndFilter:
    """Tests for AndFilter class."""

    def test_and_filter_all_match(self):
        """AndFilter should match when all filters match."""
        filter1 = EntityFilter('Indicator')
        filter2 = ScoreFilter(min_score=50)
        combined = AndFilter(filter1, filter2)
        entity = {'entity_type': 'Indicator', 'x_opencti_score': 70}

        assert combined.matches(entity) is True

    def test_and_filter_one_no_match(self):
        """AndFilter should not match when any filter doesn't match."""
        filter1 = EntityFilter('Indicator')
        filter2 = ScoreFilter(min_score=80)
        combined = AndFilter(filter1, filter2)
        entity = {'entity_type': 'Indicator', 'x_opencti_score': 50}

        assert combined.matches(entity) is False

    def test_and_operator(self):
        """AndFilter should be created with & operator."""
        filter1 = EntityFilter('Indicator')
        filter2 = ScoreFilter(min_score=50)
        combined = filter1 & filter2

        assert isinstance(combined, AndFilter)
        assert combined.matches({'entity_type': 'Indicator', 'x_opencti_score': 70}) is True


class TestOrFilter:
    """Tests for OrFilter class."""

    def test_or_filter_one_match(self):
        """OrFilter should match when any filter matches."""
        filter1 = EntityFilter('Indicator')
        filter2 = EntityFilter('Malware')
        combined = OrFilter(filter1, filter2)
        entity = {'entity_type': 'Indicator'}

        assert combined.matches(entity) is True

    def test_or_filter_all_match(self):
        """OrFilter should match when all filters match."""
        filter1 = EntityFilter('Indicator')
        filter2 = ScoreFilter(min_score=50)
        combined = OrFilter(filter1, filter2)
        entity = {'entity_type': 'Indicator', 'x_opencti_score': 70}

        assert combined.matches(entity) is True

    def test_or_filter_no_match(self):
        """OrFilter should not match when no filters match."""
        filter1 = EntityFilter('Indicator')
        filter2 = ScoreFilter(min_score=80)
        combined = OrFilter(filter1, filter2)
        entity = {'entity_type': 'Malware', 'x_opencti_score': 50}

        assert combined.matches(entity) is False

    def test_or_operator(self):
        """OrFilter should be created with | operator."""
        filter1 = EntityFilter('Indicator')
        filter2 = EntityFilter('Malware')
        combined = filter1 | filter2

        assert isinstance(combined, OrFilter)
        assert combined.matches({'entity_type': 'Malware'}) is True


class TestNotFilter:
    """Tests for NotFilter class."""

    def test_not_filter_inverts_match(self):
        """NotFilter should invert the match result."""
        filter = EntityFilter('Indicator')
        not_filter = NotFilter(filter)
        entity = {'entity_type': 'Indicator'}

        assert not_filter.matches(entity) is False

    def test_not_filter_inverts_no_match(self):
        """NotFilter should invert the no-match result."""
        filter = EntityFilter('Indicator')
        not_filter = NotFilter(filter)
        entity = {'entity_type': 'Malware'}

        assert not_filter.matches(entity) is True

    def test_invert_operator(self):
        """NotFilter should be created with ~ operator."""
        filter = EntityFilter('Indicator')
        not_filter = ~filter

        assert isinstance(not_filter, NotFilter)
        assert not_filter.matches({'entity_type': 'Malware'}) is True


# ============================================================================
# FilterBuilder Tests
# ============================================================================

class TestFilterBuilder:
    """Tests for FilterBuilder class."""

    def test_builder_entity_type(self):
        """FilterBuilder should add entity type filter."""
        filter = FilterBuilder().entity_type('Indicator').build()

        assert filter.matches({'entity_type': 'Indicator'}) is True
        assert filter.matches({'entity_type': 'Malware'}) is False

    def test_builder_label(self):
        """FilterBuilder should add label filter."""
        filter = FilterBuilder().label('malicious').build()
        entity = {'entity_type': 'Indicator', 'objectLabel': [{'value': 'malicious'}]}

        assert filter.matches(entity) is True

    def test_builder_score(self):
        """FilterBuilder should add score filter."""
        filter = FilterBuilder().score(min_score=50, max_score=80).build()
        entity1 = {'entity_type': 'Indicator', 'x_opencti_score': 65}
        entity2 = {'entity_type': 'Indicator', 'x_opencti_score': 30}

        assert filter.matches(entity1) is True
        assert filter.matches(entity2) is False

    def test_builder_confidence(self):
        """FilterBuilder should add confidence filter."""
        filter = FilterBuilder().confidence(min_confidence=60).build()
        entity1 = {'entity_type': 'Indicator', 'confidence': 70}
        entity2 = {'entity_type': 'Indicator', 'confidence': 40}

        assert filter.matches(entity1) is True
        assert filter.matches(entity2) is False

    def test_builder_date_range(self):
        """FilterBuilder should add date range filter."""
        filter = FilterBuilder().date_range(
            'valid_from',
            '2024-01-01',
            '2024-12-31'
        ).build()
        entity = {'entity_type': 'Indicator', 'valid_from': '2024-06-15'}

        assert filter.matches(entity) is True

    def test_builder_combined_filters(self):
        """FilterBuilder should combine multiple filters with AND."""
        filter = (
            FilterBuilder()
            .entity_type('Indicator')
            .score(min_score=50)
            .label('malicious')
            .build()
        )
        entity = {
            'entity_type': 'Indicator',
            'x_opencti_score': 70,
            'objectLabel': [{'value': 'malicious'}]
        }
        entity_wrong_type = {
            'entity_type': 'Malware',
            'x_opencti_score': 70,
            'objectLabel': [{'value': 'malicious'}]
        }

        assert filter.matches(entity) is True
        assert filter.matches(entity_wrong_type) is False

    def test_builder_empty(self):
        """FilterBuilder with no filters should match all."""
        filter = FilterBuilder().build()
        entity = {'entity_type': 'Indicator'}

        assert filter.matches(entity) is True


# ============================================================================
# apply_filters Tests
# ============================================================================

class TestApplyFilters:
    """Tests for apply_filters function."""

    def test_apply_filter_to_list(self):
        """apply_filters should filter list of entities."""
        filter = EntityFilter('Indicator')
        entities = [
            {'entity_type': 'Indicator', 'name': 'ind1'},
            {'entity_type': 'Malware', 'name': 'mal1'},
            {'entity_type': 'Indicator', 'name': 'ind2'},
        ]

        result = apply_filters(entities, filter)

        assert len(result) == 2
        assert all(e['entity_type'] == 'Indicator' for e in result)

    def test_apply_filter_empty_list(self):
        """apply_filters should handle empty list."""
        filter = EntityFilter('Indicator')
        entities = []

        result = apply_filters(entities, filter)

        assert result == []

    def test_apply_filter_no_matches(self):
        """apply_filters should return empty list when no matches."""
        filter = EntityFilter('Indicator')
        entities = [
            {'entity_type': 'Malware'},
            {'entity_type': 'AttackPattern'},
        ]

        result = apply_filters(entities, filter)

        assert result == []


# ============================================================================
# Integration Tests
# ============================================================================

class TestFilterIntegration:
    """Integration tests combining multiple filter types."""

    def test_complex_filter_chain(self):
        """Test complex filter combining multiple types."""
        # Find high-confidence malicious indicators
        filter = (
            EntityFilter('Indicator') &
            LabelFilter('malicious') &
            ScoreFilter(min_score=60) &
            ConfidenceFilter(min_confidence=70)
        )

        matching_entity = {
            'entity_type': 'Indicator',
            'objectLabel': [{'value': 'malicious'}],
            'x_opencti_score': 75,
            'confidence': 80
        }
        wrong_type = {
            'entity_type': 'Malware',
            'objectLabel': [{'value': 'malicious'}],
            'x_opencti_score': 75,
            'confidence': 80
        }
        low_score = {
            'entity_type': 'Indicator',
            'objectLabel': [{'value': 'malicious'}],
            'x_opencti_score': 40,
            'confidence': 80
        }

        assert filter.matches(matching_entity) is True
        assert filter.matches(wrong_type) is False
        assert filter.matches(low_score) is False

    def test_exclude_safe_entities(self):
        """Test filter that excludes safe entities."""
        filter = (
            EntityFilter('Indicator', exclude=True) |
            LabelFilter('safe', exclude=True)
        )

        safe_indicator = {
            'entity_type': 'Indicator',
            'objectLabel': [{'value': 'safe'}]
        }
        malicious_indicator = {
            'entity_type': 'Indicator',
            'objectLabel': [{'value': 'malicious'}]
        }
        malware = {
            'entity_type': 'Malware',
            'objectLabel': [{'value': 'safe'}]
        }

        # Should exclude safe indicators but allow malware
        assert filter.matches(safe_indicator) is False
        assert filter.matches(malicious_indicator) is True
        assert filter.matches(malware) is True
