#!/usr/bin/env python3
"""
Advanced filtering and search capabilities for OpenCTI data.

This module provides filter classes for entity type filtering, label filtering,
date range filtering, and score thresholding.
"""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Dict, List, Optional, Union
import logging

logger = logging.getLogger(__name__)


class BaseFilter(ABC):
    """Abstract base class for all filters."""

    @abstractmethod
    def matches(self, entity: Dict[str, Any]) -> bool:
        """Check if an entity matches this filter.

        Args:
            entity: Entity dictionary from OpenCTI

        Returns:
            True if entity matches the filter criteria
        """
        pass

    def __and__(self, other: 'BaseFilter') -> 'AndFilter':
        """Combine filters with AND logic."""
        return AndFilter(self, other)

    def __or__(self, other: 'BaseFilter') -> 'OrFilter':
        """Combine filters with OR logic."""
        return OrFilter(self, other)

    def __invert__(self) -> 'NotFilter':
        """Negate the filter."""
        return NotFilter(self)


class EntityFilter(BaseFilter):
    """Filter entities by their type.

    Supports filtering by single entity type or multiple types.
    Entity types include: Indicator, StixCyberObservable, Malware, AttackPattern, etc.
    """

    def __init__(
        self,
        entity_types: Union[str, List[str]],
        exclude: bool = False
    ):
        """Initialize entity filter.

        Args:
            entity_types: Single entity type or list of types to match
            exclude: If True, exclude entities of these types instead
        """
        if isinstance(entity_types, str):
            self.entity_types = {entity_types}
        else:
            self.entity_types = set(entity_types)
        self.exclude = exclude

    def matches(self, entity: Dict[str, Any]) -> bool:
        """Check if entity matches the type filter.

        Args:
            entity: Entity dictionary with 'entity_type' field

        Returns:
            True if entity type matches (or doesn't match if exclude=True)
        """
        entity_type = entity.get('entity_type', '')
        matches_type = entity_type in self.entity_types

        return not matches_type if self.exclude else matches_type

    def __repr__(self) -> str:
        exclude_str = "!" if self.exclude else ""
        return f"EntityFilter({exclude_str}{self.entity_types})"


class LabelFilter(BaseFilter):
    """Filter entities by their labels.

    Supports filtering by required labels (must have all) or any labels
    (must have at least one).
    """

    def __init__(
        self,
        labels: Union[str, List[str]],
        require_all: bool = True,
        exclude: bool = False
    ):
        """Initialize label filter.

        Args:
            labels: Single label or list of labels
            require_all: If True, entity must have all labels. If False, at least one.
            exclude: If True, exclude entities with these labels
        """
        if isinstance(labels, str):
            self.labels = {labels.lower()}
        else:
            self.labels = {label.lower() for label in labels}
        self.require_all = require_all
        self.exclude = exclude

    def matches(self, entity: Dict[str, Any]) -> bool:
        """Check if entity matches the label filter.

        Args:
            entity: Entity dictionary with 'objectLabel' field (list of dicts with 'value')

        Returns:
            True if entity labels match the criteria
        """
        # Extract label values from entity
        object_labels = entity.get('objectLabel', [])
        if isinstance(object_labels, list):
            # Handle both direct list of strings and list of label objects
            if object_labels and isinstance(object_labels[0], dict):
                entity_labels = {
                    label.get('value', '').lower()
                    for label in object_labels
                }
            else:
                entity_labels = {label.lower() for label in object_labels}
        else:
            entity_labels = set()

        if self.exclude:
            # Exclude if any label matches
            has_excluded = bool(entity_labels & self.labels)
            return not has_excluded
        else:
            # Require all or any labels
            if self.require_all:
                return self.labels.issubset(entity_labels)
            else:
                return bool(entity_labels & self.labels)

    def __repr__(self) -> str:
        mode = "all" if self.require_all else "any"
        exclude_str = "!" if self.exclude else ""
        return f"LabelFilter({exclude_str}{mode}:{self.labels})"


class DateRangeFilter(BaseFilter):
    """Filter entities by date fields.

    Supports filtering by various date fields: valid_from, valid_until,
    created_at, updated_at, etc.
    """

    def __init__(
        self,
        field: str = 'valid_from',
        start: Optional[Union[str, datetime]] = None,
        end: Optional[Union[str, datetime]] = None
    ):
        """Initialize date range filter.

        Args:
            field: Date field to filter on (default: 'valid_from')
            start: Start date (inclusive). Can be ISO string or datetime.
            end: End date (inclusive). Can be ISO string or datetime.
        """
        self.field = field
        self.start = self._parse_date(start) if start else None
        self.end = self._parse_date(end) if end else None

    def _parse_date(self, date_value: Union[str, datetime]) -> datetime:
        """Parse date from string or datetime.

        Args:
            date_value: Date as ISO string or datetime object

        Returns:
            datetime object
        """
        if isinstance(date_value, datetime):
            return date_value
        if isinstance(date_value, str):
            # Try common ISO formats
            for fmt in ('%Y-%m-%dT%H:%M:%S.%fZ', '%Y-%m-%dT%H:%M:%SZ', '%Y-%m-%d'):
                try:
                    return datetime.strptime(date_value, fmt)
                except ValueError:
                    continue
            # Try fromisoformat as fallback
            try:
                return datetime.fromisoformat(date_value.replace('Z', '+00:00').replace('+00:00', ''))
            except ValueError:
                raise ValueError(f"Cannot parse date: {date_value}")
        raise TypeError(f"Date must be str or datetime, got {type(date_value)}")

    def matches(self, entity: Dict[str, Any]) -> bool:
        """Check if entity's date field matches the range.

        Args:
            entity: Entity dictionary with date field

        Returns:
            True if date is within range (inclusive)
        """
        date_value = entity.get(self.field)
        if not date_value:
            return False

        try:
            entity_date = self._parse_date(date_value)
        except (ValueError, TypeError):
            logger.warning(f"Invalid date format for field {self.field}: {date_value}")
            return False

        # Check start date (inclusive)
        if self.start and entity_date < self.start:
            return False

        # Check end date (inclusive)
        if self.end and entity_date > self.end:
            return False

        return True

    def __repr__(self) -> str:
        start_str = self.start.isoformat() if self.start else "None"
        end_str = self.end.isoformat() if self.end else "None"
        return f"DateRangeFilter({self.field}: {start_str} - {end_str})"


class ScoreFilter(BaseFilter):
    """Filter entities by their score.

    Supports filtering by x_opencti_score field with min/max thresholds.
    """

    def __init__(
        self,
        min_score: Optional[int] = None,
        max_score: Optional[int] = None,
        field: str = 'x_opencti_score'
    ):
        """Initialize score filter.

        Args:
            min_score: Minimum score (inclusive). None means no lower bound.
            max_score: Maximum score (inclusive). None means no upper bound.
            field: Score field name (default: 'x_opencti_score')
        """
        if min_score is not None and not (0 <= min_score <= 100):
            raise ValueError("min_score must be between 0 and 100")
        if max_score is not None and not (0 <= max_score <= 100):
            raise ValueError("max_score must be between 0 and 100")

        self.min_score = min_score
        self.max_score = max_score
        self.field = field

    def matches(self, entity: Dict[str, Any]) -> bool:
        """Check if entity's score matches the range.

        Args:
            entity: Entity dictionary with score field

        Returns:
            True if score is within range
        """
        score = entity.get(self.field)
        if score is None:
            return False

        try:
            score = int(score)
        except (ValueError, TypeError):
            return False

        if self.min_score is not None and score < self.min_score:
            return False

        if self.max_score is not None and score > self.max_score:
            return False

        return True

    def __repr__(self) -> str:
        return f"ScoreFilter({self.field}: {self.min_score or 0}-{self.max_score or 100})"


class ConfidenceFilter(BaseFilter):
    """Filter entities by their confidence level.

    Supports filtering by confidence field with min/max thresholds.
    """

    def __init__(
        self,
        min_confidence: Optional[int] = None,
        max_confidence: Optional[int] = None,
        field: str = 'confidence'
    ):
        """Initialize confidence filter.

        Args:
            min_confidence: Minimum confidence (inclusive, 0-100)
            max_confidence: Maximum confidence (inclusive, 0-100)
            field: Confidence field name (default: 'confidence')
        """
        if min_confidence is not None and not (0 <= min_confidence <= 100):
            raise ValueError("min_confidence must be between 0 and 100")
        if max_confidence is not None and not (0 <= max_confidence <= 100):
            raise ValueError("max_confidence must be between 0 and 100")

        self.min_confidence = min_confidence
        self.max_confidence = max_confidence
        self.field = field

    def matches(self, entity: Dict[str, Any]) -> bool:
        """Check if entity's confidence matches the range.

        Args:
            entity: Entity dictionary with confidence field

        Returns:
            True if confidence is within range
        """
        confidence = entity.get(self.field)
        if confidence is None:
            return False

        try:
            confidence = int(confidence)
        except (ValueError, TypeError):
            return False

        if self.min_confidence is not None and confidence < self.min_confidence:
            return False

        if self.max_confidence is not None and confidence > self.max_confidence:
            return False

        return True

    def __repr__(self) -> str:
        return f"ConfidenceFilter({self.field}: {self.min_confidence or 0}-{self.max_confidence or 100})"


class AndFilter(BaseFilter):
    """Combine multiple filters with AND logic."""

    def __init__(self, *filters: BaseFilter):
        """Initialize AND filter.

        Args:
            *filters: One or more filters to combine
        """
        self.filters = list(filters)

    def matches(self, entity: Dict[str, Any]) -> bool:
        """Check if entity matches ALL filters.

        Args:
            entity: Entity dictionary

        Returns:
            True if all filters match
        """
        return all(f.matches(entity) for f in self.filters)

    def __repr__(self) -> str:
        return f"AndFilter([{', '.join(repr(f) for f in self.filters)}])"


class OrFilter(BaseFilter):
    """Combine multiple filters with OR logic."""

    def __init__(self, *filters: BaseFilter):
        """Initialize OR filter.

        Args:
            *filters: One or more filters to combine
        """
        self.filters = list(filters)

    def matches(self, entity: Dict[str, Any]) -> bool:
        """Check if entity matches ANY filter.

        Args:
            entity: Entity dictionary

        Returns:
            True if at least one filter matches
        """
        return any(f.matches(entity) for f in self.filters)

    def __repr__(self) -> str:
        return f"OrFilter([{', '.join(repr(f) for f in self.filters)}])"


class NotFilter(BaseFilter):
    """Negate a filter."""

    def __init__(self, filter: BaseFilter):
        """Initialize NOT filter.

        Args:
            filter: Filter to negate
        """
        self.filter = filter

    def matches(self, entity: Dict[str, Any]) -> bool:
        """Check if entity does NOT match the filter.

        Args:
            entity: Entity dictionary

        Returns:
            True if filter does not match
        """
        return not self.filter.matches(entity)

    def __repr__(self) -> str:
        return f"NotFilter({repr(self.filter)})"


class FilterBuilder:
    """Fluent API for building complex filters."""

    def __init__(self):
        """Initialize filter builder."""
        self._filters: List[BaseFilter] = []

    def entity_type(self, *types: str, exclude: bool = False) -> 'FilterBuilder':
        """Add entity type filter.

        Args:
            *types: Entity types to filter
            exclude: Exclude these types instead

        Returns:
            Self for chaining
        """
        self._filters.append(EntityFilter(list(types), exclude=exclude))
        return self

    def label(self, *labels: str, require_all: bool = True, exclude: bool = False) -> 'FilterBuilder':
        """Add label filter.

        Args:
            *labels: Labels to filter
            require_all: Require all labels or any
            exclude: Exclude entities with these labels

        Returns:
            Self for chaining
        """
        self._filters.append(LabelFilter(list(labels), require_all=require_all, exclude=exclude))
        return self

    def date_range(
        self,
        field: str = 'valid_from',
        start: Optional[Union[str, datetime]] = None,
        end: Optional[Union[str, datetime]] = None
    ) -> 'FilterBuilder':
        """Add date range filter.

        Args:
            field: Date field to filter
            start: Start date
            end: End date

        Returns:
            Self for chaining
        """
        self._filters.append(DateRangeFilter(field, start, end))
        return self

    def score(
        self,
        min_score: Optional[int] = None,
        max_score: Optional[int] = None
    ) -> 'FilterBuilder':
        """Add score filter.

        Args:
            min_score: Minimum score
            max_score: Maximum score

        Returns:
            Self for chaining
        """
        self._filters.append(ScoreFilter(min_score, max_score))
        return self

    def confidence(
        self,
        min_confidence: Optional[int] = None,
        max_confidence: Optional[int] = None
    ) -> 'FilterBuilder':
        """Add confidence filter.

        Args:
            min_confidence: Minimum confidence
            max_confidence: Maximum confidence

        Returns:
            Self for chaining
        """
        self._filters.append(ConfidenceFilter(min_confidence, max_confidence))
        return self

    def build(self) -> BaseFilter:
        """Build the combined filter.

        Returns:
            Combined filter using AND logic
        """
        if not self._filters:
            return _AlwaysTrueFilter()
        if len(self._filters) == 1:
            return self._filters[0]
        return AndFilter(*self._filters)


class _AlwaysTrueFilter(BaseFilter):
    """Filter that always matches."""

    def matches(self, entity: Dict[str, Any]) -> bool:
        return True

    def __repr__(self) -> str:
        return "AlwaysTrueFilter()"


def apply_filters(
    entities: List[Dict[str, Any]],
    filter: BaseFilter
) -> List[Dict[str, Any]]:
    """Apply a filter to a list of entities.

    Args:
        entities: List of entity dictionaries
        filter: Filter to apply

    Returns:
        Filtered list of entities
    """
    return [entity for entity in entities if filter.matches(entity)]
