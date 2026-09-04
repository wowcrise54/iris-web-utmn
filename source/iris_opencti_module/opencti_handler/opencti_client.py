#!/usr/bin/env python3

import os
import time
import logging
import requests
from datetime import datetime
from typing import List, Optional, Union, Dict, Any

from iris_opencti_module.opencti_handler.cache import OpenCTICache
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

logger = logging.getLogger(__name__)


class OpenCTIClientError(Exception):
    pass


class OpenCTIClient:
    # OpenCTI 7 exposes objectLabel/objectMarking as lists. Older releases
    # exposed Relay connections, which are handled by _LEGACY_SEARCH_QUERY.
    _SEARCH_QUERY = """
    query IrisOpenCTISearch($search: String!, $first: Int!) {
      indicators(search: $search, first: $first) {
        edges {
          node {
            id
            standard_id
            entity_type
            name
            description
            pattern
            pattern_type
            confidence
            x_opencti_score
            revoked
            valid_from
            valid_until
            created_at
            updated_at
            objectLabel {
              value
              color
            }
            objectMarking {
              definition
              x_opencti_color
            }
            externalReferences {
              edges {
                node {
                  source_name
                  external_id
                  url
                }
              }
            }
          }
        }
      }
      stixCyberObservables(search: $search, first: $first) {
        edges {
          node {
            id
            standard_id
            entity_type
            observable_value
            x_opencti_score
            created_at
            updated_at
            objectLabel {
              value
              color
            }
            objectMarking {
              definition
              x_opencti_color
            }
            externalReferences {
              edges {
                node {
                  source_name
                  external_id
                  url
                }
              }
            }
          }
        }
      }
    }
    """

    _LEGACY_SEARCH_QUERY = """
    query IrisOpenCTISearchLegacy($search: String!, $first: Int!) {
      indicators(search: $search, first: $first) {
        edges {
          node {
            id
            standard_id
            entity_type
            name
            description
            pattern
            pattern_type
            confidence
            x_opencti_score
            revoked
            valid_from
            valid_until
            created_at
            updated_at
            objectLabel {
              edges {
                node {
                  value
                  color
                }
              }
            }
            objectMarking {
              edges {
                node {
                  definition
                  x_opencti_color
                }
              }
            }
            externalReferences {
              edges {
                node {
                  source_name
                  external_id
                  url
                }
              }
            }
          }
        }
      }
      stixCyberObservables(search: $search, first: $first) {
        edges {
          node {
            id
            standard_id
            entity_type
            observable_value
            x_opencti_score
            created_at
            updated_at
            objectLabel {
              edges {
                node {
                  value
                  color
                }
              }
            }
            objectMarking {
              edges {
                node {
                  definition
                  x_opencti_color
                }
              }
            }
            externalReferences {
              edges {
                node {
                  source_name
                  external_id
                  url
                }
              }
            }
          }
        }
      }
    }
    """

    _RELATED_QUERY = """
    query IrisOpenCTIRelated($ids: [String], $objectId: Any!, $first: Int!) {
      stixCoreRelationships(fromOrToId: $ids, first: $first) {
        edges {
          node {
            id
            relationship_type
            from {
              ... on StixCoreObject {
                id
                entity_type
                representative {
                  main
                }
              }
            }
            to {
              ... on StixCoreObject {
                id
                entity_type
                representative {
                  main
                }
              }
            }
          }
        }
      }
      containers(
        first: $first
        filters: {
          mode: and
          filters: [{ key: ["objects"], values: [$objectId] }]
          filterGroups: []
        }
      ) {
        edges {
          node {
            ... on StixCoreObject {
              id
              entity_type
              representative {
                main
              }
              created_at
              updated_at
            }
          }
        }
      }
    }
    """

    _SIGHTINGS_QUERY = """
    query IrisOpenCTISightings($ids: [String], $first: Int!) {
      stixSightingRelationships(fromOrToId: $ids, first: $first) {
        edges {
          node {
            id
            first_seen
            last_seen
            attribute_count
          }
        }
      }
    }
    """

    _GRAPH_QUERY = """
    query IrisOpenCTIGraph($ids: [String], $first: Int!, $after: ID) {
      stixCoreRelationships(fromOrToId: $ids, first: $first, after: $after) {
        pageInfo { hasNextPage endCursor }
        edges {
          node {
            id
            relationship_type
            created_at
            updated_at
            from {
              ... on StixCoreObject {
                id entity_type created_at updated_at
                representative { main }
              }
            }
            to {
              ... on StixCoreObject {
                id entity_type created_at updated_at
                representative { main }
              }
            }
          }
        }
      }
    }
    """

    _MINIMAL_SEARCH_QUERY = """
    query IrisOpenCTISearchMinimal($search: String!, $first: Int!) {
      indicators(search: $search, first: $first) {
        edges {
          node {
            id
            standard_id
            entity_type
            name
            description
            pattern
            x_opencti_score
            confidence
          }
        }
      }
      stixCyberObservables(search: $search, first: $first) {
        edges {
          node {
            id
            standard_id
            entity_type
            observable_value
            description
            x_opencti_score
          }
        }
      }
    }
    """

    _BARE_SEARCH_QUERY = """
    query IrisOpenCTISearchBare($search: String!, $first: Int!) {
      indicators(search: $search, first: $first) {
        edges {
          node {
            id
            entity_type
            name
            pattern
          }
        }
      }
      stixCyberObservables(search: $search, first: $first) {
        edges {
          node {
            id
            entity_type
            observable_value
          }
        }
      }
    }
    """

    _HEALTH_QUERY = """
    query IrisOpenCTIHealthCheck {
      about {
        version
      }
    }
    """

    def __init__(self, url, token, verify_ssl=True, timeout=20, proxies=None, retry_attempts=3, retry_delay=1.0):
        self.api_url = self._normalize_graphql_url(url)
        self.token = token
        self.verify_ssl = verify_ssl
        self.timeout = timeout
        self.proxies = proxies or {}
        self.session = requests.Session()
        self.retry_attempts = retry_attempts
        self.retry_delay = retry_delay
        
        # Initialize cache with configurable size and TTL
        self.cache = OpenCTICache(
            max_size=int(os.getenv("OPENCTI_CACHE_SIZE", 1000)),
            ttl=int(os.getenv("OPENCTI_CACHE_TTL", 300))
        )

    @staticmethod
    def _normalize_graphql_url(url):
        if not url:
            return ""

        normalized = url.rstrip("/")
        if normalized.endswith("/graphql"):
            return normalized

        return f"{normalized}/graphql"

    def _headers(self):
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.token}",
        }

    def _execute_query(self, query: str, variables: dict = None) -> dict:
        """Execute GraphQL query with retry logic and exponential backoff"""
        last_error = None

        for attempt in range(self.retry_attempts):
            try:
                return self._make_request(query, variables)
            except OpenCTIClientError as e:
                last_error = e

                # Don't retry on errors that will not heal themselves:
                # authentication/authorization failures, GraphQL validation
                # errors, and HTTP 403. (403 messages read "Forbidden", which
                # the old "unauthorized" check missed, so auth-403s were
                # pointlessly retried with backoff.)
                message = str(e).lower()
                if (
                    "unauthorized" in message
                    or "forbidden" in message
                    or "validation" in message
                    or "graphql_error" in message
                ):
                    logger.warning(f"Non-retryable error, not retrying: {e}")
                    raise

                if attempt < self.retry_attempts - 1:
                    delay = self.retry_delay * (2 ** attempt)  # Exponential backoff
                    logger.warning(
                        f"Request failed (attempt {attempt + 1}/{self.retry_attempts}): {e}. "
                        f"Retrying in {delay:.1f}s..."
                    )
                    time.sleep(delay)
                else:
                    logger.error(f"All {self.retry_attempts} attempts failed: {e}")
                    raise

        raise last_error

    def _make_request(self, query: str, variables: dict = None) -> dict:
        """Make a single GraphQL request without retry logic"""
        if not self.api_url:
            raise OpenCTIClientError("OpenCTI URL is not configured")
        if not self.token:
            raise OpenCTIClientError("OpenCTI token is not configured")

        try:
            response = self.session.post(
                self.api_url,
                json={"query": query, "variables": variables or {}},
                headers=self._headers(),
                verify=self.verify_ssl,
                proxies=self.proxies,
                timeout=self.timeout,
            )
            response.raise_for_status()
            payload = response.json()
        except Exception as exc:
            raise OpenCTIClientError(str(exc)) from exc

        # GraphQL returns HTTP 200 with an "errors" array for schema/argument
        # problems. Mark the error so the retry loop can skip retrying a
        # deterministic query failure (otherwise it burns the full retry
        # budget on every call).
        if payload.get("errors"):
            raise OpenCTIClientError(f"graphql_error: {payload['errors']}")

        return payload.get("data") or {}

    def query(self, query, variables=None):
        """Execute a GraphQL query (wrapper for backward compatibility)"""
        return self._execute_query(query, variables)

    def health_check(self):
        return self.query(self._HEALTH_QUERY)

    def search_ioc(self, value, first=20):
        """Search OpenCTI for an IOC with caching support.
        
        Args:
            value: The IOC value to search for (e.g., "8.8.8.8", "example.com")
            first: Maximum number of results to return
            
        Returns:
            Query result dictionary containing indicators and stixCyberObservables
            
        Note:
            Results are cached to improve performance for repeated queries.
            Cache key includes the query value and type for proper deduplication.
        """
        # Check cache first. The key includes the requested result count so a
        # query for first=5 is not served a cached first=20 payload (and vice
        # versa) from a different call for the same IOC value.
        cache_type = f"indicator:{first}"
        cached = self.cache.get(value, cache_type)
        if cached:
            logger.info(f"Cache hit for IOC: {value}")
            return cached

        # Execute query with retry logic
        variables = {"search": value, "first": first}
        try:
            result = self.query(self._SEARCH_QUERY, variables)
        except OpenCTIClientError as exc:
            if "Cannot query field" not in str(exc) and "Unknown argument" not in str(exc):
                raise

            # Schema changed (e.g. OpenCTI 6 vs 7): drop every cached result
            # for this value (all query_type/first variants) so a stale,
            # differently-shaped payload is not served until TTL expires.
            self.cache.invalidate_value(value)

            # Try fallback queries
            result = None
            for query in (self._LEGACY_SEARCH_QUERY, self._MINIMAL_SEARCH_QUERY):
                try:
                    result = self.query(query, variables)
                    break
                except OpenCTIClientError as exc:
                    if "Cannot query field" not in str(exc) and "Unknown argument" not in str(exc):
                        raise

            # Last resort: bare query
            if result is None:
                result = self.query(self._BARE_SEARCH_QUERY, variables)

        # Cache the result
        self.cache.set(value, result, cache_type)
        logger.debug(f"Cached result for IOC: {value}")

        return result

    def get_related_entities(self, object_id, first=20):
        return self.query(
            self._RELATED_QUERY,
            {
                "ids": [object_id],
                "objectId": object_id,
                "first": first,
            },
        )

    def get_sightings(self, object_id, first=50):
        try:
            return self.query(self._SIGHTINGS_QUERY, {"ids": [object_id], "first": first})
        except OpenCTIClientError as exc:
            if "Cannot query field" in str(exc) or "Unknown argument" in str(exc):
                # The sightings query is not supported by this OpenCTI version.
                # Log it so the degradation is visible in the logs instead of
                # silently producing zero sightings for every IOC.
                logger.warning(
                    f"Sightings query not supported by this OpenCTI schema "
                    f"(object {object_id}); returning empty sightings: {exc}"
                )
                return {"stixSightingRelationships": {"edges": []}}
            raise

    def get_graph_relationships(self, object_ids, first=100, after=None):
        return self.query(
            self._GRAPH_QUERY,
            {"ids": list(object_ids), "first": first, "after": after},
        )

    def search_with_filters(
        self,
        value: str,
        filter: Optional[BaseFilter] = None,
        first: int = 20,
        entity_type: Optional[Union[str, List[str]]] = None,
        labels: Optional[Union[str, List[str]]] = None,
        min_score: Optional[int] = None,
        max_score: Optional[int] = None,
        min_confidence: Optional[int] = None,
        max_confidence: Optional[int] = None,
        valid_from: Optional[Union[str, datetime]] = None,
        valid_until: Optional[Union[str, datetime]] = None,
    ) -> Dict[str, Any]:
        """Search OpenCTI with advanced filtering.

        Args:
            value: Search term (IOC value)
            filter: Pre-built filter object (overrides individual params)
            first: Maximum number of results
            entity_type: Filter by entity type(s)
            labels: Filter by labels
            min_score: Minimum score threshold
            max_score: Maximum score threshold
            min_confidence: Minimum confidence threshold
            max_confidence: Maximum confidence threshold
            valid_from: Start of validity date range
            valid_until: End of validity date range

        Returns:
            Filtered query results
        """
        # Build filter from parameters if not provided
        if filter is None:
            builder = FilterBuilder()

            if entity_type:
                builder.entity_type(entity_type if isinstance(entity_type, list) else [entity_type])

            if labels:
                builder.label(labels if isinstance(labels, list) else [labels])

            if min_score is not None or max_score is not None:
                builder.score(min_score, max_score)

            if min_confidence is not None or max_confidence is not None:
                builder.confidence(min_confidence, max_confidence)

            if valid_from is not None or valid_until is not None:
                builder.date_range('valid_from', valid_from, valid_until)

            filter = builder.build()

        # Execute search
        result = self.search_ioc(value, first=first)

        # Extract entities from both indicators and observables
        entities = []

        for edge in result.get('indicators', {}).get('edges', []):
            node = edge.get('node', {})
            node['source'] = 'indicator'
            entities.append(node)

        for edge in result.get('stixCyberObservables', {}).get('edges', []):
            node = edge.get('node', {})
            node['source'] = 'observable'
            entities.append(node)

        # Apply filter
        if filter:
            filtered_entities = apply_filters(entities, filter)
            logger.info(f"Filtered {len(entities)} entities down to {len(filtered_entities)}")
            return filtered_entities

        return entities

    def filter_entities(
        self,
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
        return apply_filters(entities, filter)

    def get_high_confidence_matches(
        self,
        value: str,
        min_confidence: int = 50,
        first: int = 20
    ) -> List[Dict[str, Any]]:
        """Get high-confidence matches for an IOC.

        Args:
            value: IOC value to search
            min_confidence: Minimum confidence threshold (default: 50)
            first: Maximum results

        Returns:
            List of high-confidence entities
        """
        return self.search_with_filters(
            value,
            min_confidence=min_confidence,
            first=first
        )

    def get_malicious_entities(
        self,
        value: str,
        first: int = 20
    ) -> List[Dict[str, Any]]:
        """Get entities with malicious labels.

        Args:
            value: Search term
            first: Maximum results

        Returns:
            List of malicious entities
        """
        return self.search_with_filters(
            value,
            labels=['malicious'],
            first=first
        )

    def get_recent_entities(
        self,
        value: str,
        days: int = 30,
        first: int = 20
    ) -> List[Dict[str, Any]]:
        """Get recently created/updated entities.

        Args:
            value: Search term
            days: Number of days to look back
            first: Maximum results

        Returns:
            List of recent entities
        """
        from datetime import datetime, timedelta

        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=days)

        return self.search_with_filters(
            value,
            valid_from=start_date.isoformat(),
            valid_until=end_date.isoformat(),
            first=first
        )
