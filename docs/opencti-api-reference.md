# OpenCTI Plugin API Reference

> **Version:** 1.3.0  
> **Last Updated:** August 2026

---

## Table of Contents

1. [Overview](#overview)
2. [Client API](#client-api)
3. [Handler API](#handler-api)
4. [Filter API](#filter-api)
5. [Cache API](#cache-api)
6. [History API](#history-api)
7. [Data Models](#data-models)
8. [GraphQL Queries](#graphql-queries)
9. [Error Handling](#error-handling)

---

## Overview

This document provides comprehensive API documentation for the DFIR-IRIS OpenCTI plugin. It covers all public classes, methods, and data structures available for programmatic access.

### Module Structure

```
iris_opencti_module/
├── opencti_handler/
│   ├── opencti_client.py      # OpenCTI GraphQL client
│   ├── opencti_handler.py     # Main enrichment handler
│   ├── opencti_mapping.py     # Data transformation
│   ├── opencti_insights.py    # Analytics and recommendations
│   ├── filters.py             # Advanced filtering
│   ├── cache.py               # Query caching
│   └── history.py             # Enrichment history
├── IrisOpenCTIConfig.py       # Configuration definitions
└── opencti_enrichment_rules.py # Default rules
```

---

## Client API

### OpenCTIClient

Main client for communicating with OpenCTI GraphQL API.

#### Constructor

```python
OpenCTIClient(
    url: str,
    token: str,
    verify_ssl: bool = True,
    timeout: int = 20,
    proxies: dict = None,
    retry_attempts: int = 3,
    retry_delay: float = 1.0
)
```

**Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `url` | str | Required | OpenCTI base URL (e.g., `https://opencti.example.com`) |
| `token` | str | Required | OpenCTI API token |
| `verify_ssl` | bool | `True` | Verify SSL certificates |
| `timeout` | int | `20` | Request timeout in seconds |
| `proxies` | dict | `{}` | Proxy configuration (`{'http': ..., 'https': ...}`) |
| `retry_attempts` | int | `3` | Number of retry attempts |
| `retry_delay` | float | `1.0` | Initial retry delay in seconds |

**Example:**
```python
from iris_opencti_module.opencti_handler.opencti_client import OpenCTIClient

client = OpenCTIClient(
    url="https://opencti.example.com",
    token="your-api-token",
    timeout=30,
    retry_attempts=5
)
```

---

#### Methods

##### `health_check() -> dict`

Check OpenCTI server health and version.

**Returns:**
```python
{
    "about": {
        "version": "6.0.0"
    }
}
```

**Example:**
```python
try:
    health = client.health_check()
    print(f"OpenCTI version: {health['about']['version']}")
except OpenCTIClientError as e:
    print(f"Connection failed: {e}")
```

---

##### `search_ioc(value: str, first: int = 20) -> dict`

Search for an IOC in OpenCTI.

**Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `value` | str | Required | IOC value to search (e.g., "8.8.8.8", "malicious.com") |
| `first` | int | `20` | Maximum number of results |

**Returns:**
```python
{
    "indicators": {
        "edges": [
            {
                "node": {
                    "id": "indicator--123",
                    "standard_id": "indicator--abc",
                    "entity_type": "Indicator",
                    "name": "Malicious Domain",
                    "description": "Known C2 domain",
                    "pattern": "[domain-name:value = 'malicious.com']",
                    "pattern_type": "stix",
                    "confidence": 80,
                    "x_opencti_score": 75,
                    "revoked": False,
                    "valid_from": "2024-01-01T00:00:00Z",
                    "valid_until": "2025-01-01T00:00:00Z",
                    "created_at": "2024-01-01T00:00:00Z",
                    "updated_at": "2024-06-01T00:00:00Z",
                    "objectLabel": [
                        {"value": "malicious", "color": "#ff0000"},
                        {"value": "phishing", "color": "#ff6600"}
                    ],
                    "objectMarking": [
                        {"definition": "TLP:AMBER", "x_opencti_color": "#ff9900"}
                    ],
                    "externalReferences": {
                        "edges": [
                            {
                                "node": {
                                    "source_name": "ThreatFeed",
                                    "external_id": "TF-123",
                                    "url": "https://threatfeed.example.com/ioc/123"
                                }
                            }
                        ]
                    }
                }
            }
        ]
    },
    "stixCyberObservables": {
        "edges": [...]
    }
}
```

**Example:**
```python
results = client.search_ioc(value="8.8.8.8", first=10)

# Process indicators
for edge in results["indicators"]["edges"]:
    indicator = edge["node"]
    print(f"Found: {indicator['name']} (score: {indicator['x_opencti_score']})")

# Process observables
for edge in results["stixCyberObservables"]["edges"]:
    observable = edge["node"]
    print(f"Observable: {observable['observable_value']}")
```

**Caching:** Results are automatically cached based on `opencti_cache_ttl` configuration.

---

##### `get_related_entities(object_id: str, first: int = 20) -> dict`

Get entities related to a given OpenCTI object.

**Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `object_id` | str | Required | OpenCTI object standard ID |
| `first` | int | `20` | Maximum number of relationships |

**Returns:**
```python
{
    "stixCoreRelationships": {
        "edges": [
            {
                "node": {
                    "id": "relationship--123",
                    "relationship_type": "indicates",
                    "from": {
                        "id": "indicator--abc",
                        "entity_type": "Indicator",
                        "representative": {"main": "Malicious Domain"}
                    },
                    "to": {
                        "id": "malware--xyz",
                        "entity_type": "Malware",
                        "representative": {"main": "Emotet"}
                    }
                }
            }
        ]
    },
    "containers": {
        "edges": [
            {
                "node": {
                    "id": "report--123",
                    "entity_type": "Report",
                    "representative": {"main": "Emotet Campaign Report"},
                    "created_at": "2024-01-01T00:00:00Z",
                    "updated_at": "2024-06-01T00:00:00Z"
                }
            }
        ]
    }
}
```

**Example:**
```python
related = client.get_related_entities(object_id="indicator--123", first=10)

for edge in related["stixCoreRelationships"]["edges"]:
    rel = edge["node"]
    print(f"{rel['from']['main']} --{rel['relationship_type']}--> {rel['to']['main']}")
```

---

##### `get_sightings(object_id: str, first: int = 20) -> dict`

Get sighting information for an OpenCTI object.

**Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `object_id` | str | Required | OpenCTI object standard ID |
| `first` | int | `20` | Maximum number of sightings |

**Returns:**
```python
{
    "stixSightingRelationships": {
        "edges": [
            {
                "node": {
                    "id": "sighting--123",
                    "first_seen": "2024-01-01T00:00:00Z",
                    "last_seen": "2024-06-01T00:00:00Z",
                    "attribute_count": 5
                }
            }
        ]
    }
}
```

**Example:**
```python
sightings = client.get_sightings(object_id="indicator--123")
total_sightings = sum(
    edge["node"]["attribute_count"] 
    for edge in sightings["stixSightingRelationships"]["edges"]
)
print(f"Total sightings: {total_sightings}")
```

---

##### `get_graph_relationships(object_ids: list, first: int = 100, after: str = None) -> dict`

Get relationship graph data for building entity graphs.

**Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `object_ids` | list | Required | List of object IDs to get relationships for |
| `first` | int | `100` | Maximum relationships per page |
| `after` | str | `None` | Cursor for pagination |

**Returns:**
```python
{
    "stixCoreRelationships": {
        "pageInfo": {
            "hasNextPage": True,
            "endCursor": "cursor-abc123"
        },
        "edges": [
            {
                "node": {
                    "id": "relationship--123",
                    "relationship_type": "indicates",
                    "created_at": "2024-01-01T00:00:00Z",
                    "updated_at": "2024-06-01T00:00:00Z",
                    "from": {
                        "id": "indicator--abc",
                        "entity_type": "Indicator",
                        "created_at": "...",
                        "updated_at": "...",
                        "representative": {"main": "Malicious Domain"}
                    },
                    "to": {
                        "id": "malware--xyz",
                        "entity_type": "Malware",
                        "created_at": "...",
                        "updated_at": "...",
                        "representative": {"main": "Emotet"}
                    }
                }
            }
        ]
    }
}
```

**Pagination Example:**
```python
all_relationships = []
cursor = None

while True:
    result = client.get_graph_relationships(
        object_ids=["indicator--123"],
        first=100,
        after=cursor
    )
    
    relationships = result["stixCoreRelationships"]["edges"]
    all_relationships.extend(relationships)
    
    page_info = result["stixCoreRelationships"]["pageInfo"]
    if not page_info["hasNextPage"]:
        break
    cursor = page_info["endCursor"]

print(f"Total relationships: {len(all_relationships)}")
```

---

##### `query(query: str, variables: dict = None) -> dict`

Execute a raw GraphQL query.

**Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `query` | str | Required | GraphQL query string |
| `variables` | dict | `None` | Query variables |

**Example:**
```python
custom_query = """
query GetIndicator($id: String!) {
    indicator(id: $id) {
        id
        name
        pattern
        confidence
    }
}
"""

result = client.query(
    query=custom_query,
    variables={"id": "indicator--123"}
)

print(result["indicator"]["name"])
```

---

### OpenCTIClientError

Exception raised for OpenCTI client errors.

```python
class OpenCTIClientError(Exception):
    """Base exception for OpenCTI client errors."""
    pass
```

**Example:**
```python
from iris_opencti_module.opencti_handler.opencti_client import OpenCTIClient, OpenCTIClientError

try:
    client = OpenCTIClient(url="invalid-url", token="token")
    client.health_check()
except OpenCTIClientError as e:
    print(f"Client error: {e}")
```

---

## Handler API

### OpenCTIHandler

Main handler for OpenCTI enrichment operations.

#### Constructor

```python
OpenCTIHandler(
    mod_config: dict,
    server_config: dict,
    logger: logging.Logger
)
```

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `mod_config` | dict | Module configuration (from IrisOpenCTIConfig) |
| `server_config` | dict | Server configuration (proxies, etc.) |
| `logger` | Logger | Python logger instance |

**Example:**
```python
import logging
from iris_opencti_module.opencti_handler.opencti_handler import OpenCTIHandler

logger = logging.getLogger(__name__)
mod_config = {
    "opencti_url": "https://opencti.example.com",
    "opencti_token": "token",
    "opencti_max_results": 20
}
server_config = {"http_proxy": None, "https_proxy": None}

handler = OpenCTIHandler(mod_config, server_config, logger)
```

---

#### Methods

##### `set_progress_callback(callback: callable)`

Set a callback function for progress updates.

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `callback` | callable | Function that accepts a progress dict |

**Example:**
```python
def progress_callback(data):
    print(f"Progress: {data['processed']}/{data['total']}")

handler.set_progress_callback(progress_callback)
```

---

##### `handle_iocs(data: list) -> InterfaceStatus`

Enrich a list of IOCs.

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `data` | list | List of IOC objects with `ioc_value` and `ioc_type` |

**Returns:** `InterfaceStatus` object with success/error status

**Example:**
```python
from app.models.iocs import IOC

iocs = IOC.query.filter(IOC.alert_id == alert_id).all()
status = handler.handle_iocs(iocs)

if status.is_success():
    print("All IOCs enriched successfully")
else:
    print(f"Enrichment completed with errors: {status.msg}")
```

---

##### `handle_alerts(data: list) -> InterfaceStatus`

Enrich all IOCs in a list of alerts.

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `data` | list | List of Alert objects |

**Returns:** `InterfaceStatus` object

**Example:**
```python
from app.models.alerts import Alert

alerts = Alert.query.filter(Alert.alert_id.in_([123, 456])).all()
status = handler.handle_alerts(alerts)

# Check enrichment progress
for alert in alerts:
    progress = (alert.alert_context or {}).get("opencti", {}).get("progress", {})
    print(f"Alert {alert.alert_id}: {progress.get('status')}")
```

---

## Filter API

Advanced filtering capabilities for OpenCTI results.

### BaseFilter

Abstract base class for all filters.

```python
from iris_opencti_module.opencti_handler.filters import BaseFilter

class BaseFilter(ABC):
    @abstractmethod
    def matches(self, entity: dict) -> bool:
        """Check if entity matches filter criteria."""
        pass
    
    def __and__(self, other: BaseFilter) -> AndFilter:
        """Combine with AND logic."""
        pass
    
    def __or__(self, other: BaseFilter) -> OrFilter:
        """Combine with OR logic."""
        pass
    
    def __invert__(self) -> NotFilter:
        """Negate the filter."""
        pass
```

---

### EntityFilter

Filter by entity type.

```python
from iris_opencti_module.opencti_handler.filters import EntityFilter

# Single type
filter = EntityFilter("Indicator")

# Multiple types
filter = EntityFilter(["Indicator", "StixCyberObservable"])

# Exclude types
filter = EntityFilter(["Malware", "Campaign"], exclude=True)
```

**Methods:**

- `matches(entity: dict) -> bool`

---

### LabelFilter

Filter by entity labels.

```python
from iris_opencti_module.opencti_handler.filters import LabelFilter

# Require all labels
filter = LabelFilter(["malicious", "phishing"], require_all=True)

# Require any label
filter = LabelFilter(["malicious", "suspicious"], require_all=False)

# Exclude labels
filter = LabelFilter(["safe", "whitelisted"], exclude=True)
```

**Methods:**

- `matches(entity: dict) -> bool`

---

### ScoreFilter

Filter by entity score.

```python
from iris_opencti_module.opencti_handler.filters import ScoreFilter

# Minimum score
filter = ScoreFilter(min_score=50)

# Score range
filter = ScoreFilter(min_score=30, max_score=80)
```

**Methods:**

- `matches(entity: dict) -> bool`

---

### ConfidenceFilter

Filter by confidence level.

```python
from iris_opencti_module.opencti_handler.filters import ConfidenceFilter

# Minimum confidence
filter = ConfidenceFilter(min_confidence=50)

# Confidence range
filter = ConfidenceFilter(min_confidence=30, max_confidence=80)
```

**Methods:**

- `matches(entity: dict) -> bool`

---

### DateRangeFilter

Filter by date fields.

```python
from iris_opencti_module.opencti_handler.filters import DateRangeFilter
from datetime import datetime, timedelta

# Date range
end = datetime.utcnow()
start = end - timedelta(days=30)

filter = DateRangeFilter(
    field="valid_from",
    start=start.isoformat(),
    end=end.isoformat()
)
```

**Methods:**

- `matches(entity: dict) -> bool`

---

### AndFilter, OrFilter, NotFilter

Combine filters with logic operators.

```python
from iris_opencti_module.opencti_handler.filters import (
    EntityFilter, ScoreFilter, LabelFilter,
    AndFilter, OrFilter, NotFilter
)

# Using operators (recommended)
complex_filter = (
    EntityFilter("Indicator") &
    ScoreFilter(min_score=50) &
    LabelFilter("malicious")
)

# Using explicit classes
complex_filter = AndFilter([
    EntityFilter("Indicator"),
    ScoreFilter(min_score=50),
    LabelFilter("malicious")
])

# Negation
filtered = ~LabelFilter("safe")
```

---

### FilterBuilder

Fluent API for building complex filters.

```python
from iris_opencti_module.opencti_handler.filters import FilterBuilder

builder = FilterBuilder()
filter = (
    builder
    .entity_type("Indicator", "StixCyberObservable")
    .score(min_score=50, max_score=100)
    .label("malicious", require_all=False)
    .date_range(field="valid_from", start="2024-01-01")
    .build()
)
```

**Methods:**

- `entity_type(*types: str, exclude: bool = False) -> FilterBuilder`
- `label(*labels: str, require_all: bool = True, exclude: bool = False) -> FilterBuilder`
- `date_range(field: str, start: str = None, end: str = None) -> FilterBuilder`
- `score(min_score: int = None, max_score: int = None) -> FilterBuilder`
- `build() -> BaseFilter`

---

### apply_filters

Apply filters to a list of entities.

```python
from iris_opencti_module.opencti_handler.filters import apply_filters, EntityFilter, ScoreFilter

entities = [...]  # List of entity dicts from OpenCTI
filter = EntityFilter("Indicator") & ScoreFilter(min_score=50)

filtered_entities = apply_filters(entities, filter)
```

---

## Cache API

### OpenCTICache

In-memory LRU cache for OpenCTI queries.

```python
from iris_opencti_module.opencti_handler.cache import OpenCTICache

cache = OpenCTICache(max_size=1000, ttl=300)
```

**Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `max_size` | int | `1000` | Maximum cache entries |
| `ttl` | int | `300` | TTL in seconds |

**Methods:**

- `get(key: str, query_type: str) -> dict | None` - Get cached result
- `set(key: str, value: dict, query_type: str) -> None` - Store result
- `delete(key: str) -> bool` - Remove entry
- `clear() -> None` - Clear all entries
- `size() -> int` - Current cache size
- `stats() -> dict` - Cache statistics

**Example:**
```python
# Check cache
cached = cache.get("8.8.8.8", "indicator")
if cached:
    print("Cache hit!")
else:
    # Perform query and cache result
    result = client.search_ioc("8.8.8.8")
    cache.set("8.8.8.8", result, "indicator")
```

---

## History API

### EnrichmentHistory

Track enrichment history for deduplication.

```python
from iris_opencti_module.opencti_handler.history import EnrichmentHistory

history = EnrichmentHistory(history_ttl_hours=24, max_history_size=10000)
```

**Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `history_ttl_hours` | int | `24` | TTL for history records |
| `max_history_size` | int | `10000` | Maximum history entries |

**Methods:**

- `add_record(record: dict) -> None` - Add enrichment record
- `check_history(ioc_value: str, ioc_type: str) -> dict` - Check if IOC in history
- `get_record(ioc_value: str, ioc_type: str) -> dict | None` - Get specific record
- `get_historical_matches() -> list` - Get all match records
- `get_historical_errors() -> list` - Get all error records
- `get_stats() -> dict` - Get history statistics
- `clear_expired() -> int` - Remove expired records
- `clear_all() -> None` - Clear all history

**Example:**
```python
# Check history before enrichment
result = history.check_history("8.8.8.8", "ipv4-addr")

if result["in_history"] and not result["should_enrich"]:
    print(f"Using cached result: {result['cached_status']}")
else:
    # Perform enrichment
    ...
    # Store result
    history.add_record({
        "query_value": "8.8.8.8",
        "ioc_type": "ipv4-addr",
        "status": "match",
        "match_count": 3,
        "timestamp": datetime.utcnow().isoformat() + "Z"
    })
```

---

## Data Models

### Enrichment Result Structure

```python
{
    "query_value": "8.8.8.8",
    "status": "match",  # or "no_match", "error"
    "match_count": 3,
    "matches": [
        {
            "id": "indicator--123",
            "name": "Suspicious IP",
            "entity_type": "Indicator",
            "score": 75,
            "confidence": 80,
            "labels": ["suspicious", "scanner"],
            "markings": ["TLP:AMBER"],
            "valid_from": "2024-01-01T00:00:00Z",
            "valid_until": "2025-01-01T00:00:00Z",
            "description": "Known scanner IP",
            "pattern": "[ipv4-addr:value = '8.8.8.8']",
            "external_references": [...],
            "related_entities": [...],
            "sightings": {
                "count": 10,
                "first_seen": "2024-01-01T00:00:00Z",
                "last_seen": "2024-06-01T00:00:00Z"
            },
            "opencti_url": "https://opencti.example.com/dashboard/.../indicator--123"
        }
    ],
    "generated_tags": ["opencti:match", "opencti:label:suspicious"],
    "verdict": "suspicious",  # or "malicious", "clean", "unknown"
    "provider": "OpenCTI",
    "last_lookup_utc": "2024-06-15T10:30:00Z"
}
```

### Progress Data Structure

```python
{
    "kind": "opencti_enrichment",
    "alert_id": 123,
    "total": 10,
    "processed": 5,
    "matched": 3,
    "no_match": 1,
    "errors": 1,
    "current_ioc": "8.8.8.8",
    "status": "running"  # or "success", "partial", "error"
}
```

---

## GraphQL Queries

### Built-in Queries

The client includes several pre-defined GraphQL queries:

- `_SEARCH_QUERY` - Standard IOC search
- `_LEGACY_SEARCH_QUERY` - Fallback for older OpenCTI versions
- `_MINIMAL_SEARCH_QUERY` - Minimal result set
- `_BARE_SEARCH_QUERY` - Minimal fields only
- `_RELATED_QUERY` - Related entities
- `_SIGHTINGS_QUERY` - Sighting data
- `_GRAPH_QUERY` - Relationship graph
- `_HEALTH_QUERY` - Health check

---

## Error Handling

### Error Types

| Error | Cause | Handling |
|-------|-------|----------|
| `OpenCTIClientError` | Connection, auth, or query errors | Catch and handle appropriately |
| `ValueError` | Invalid parameter values | Validate inputs before calling |
| `TimeoutError` | Request timeout | Increase timeout or retry |

### Retry Logic

The client implements automatic retry with exponential backoff:

```python
# Retry behavior
# Attempt 1: Immediate
# Attempt 2: delay * 2^1 = 1 * 2 = 2 seconds
# Attempt 3: delay * 2^2 = 1 * 4 = 4 seconds
# Attempt 4: delay * 2^3 = 1 * 8 = 8 seconds
```

**Non-retryable errors:**
- Authentication errors (401)
- Validation errors (GraphQL syntax)
- Forbidden errors (403)

**Retryable errors:**
- Connection timeouts
- Network errors
- Server errors (5xx)

**Example:**
```python
from iris_opencti_module.opencti_handler.opencti_client import OpenCTIClient, OpenCTIClientError

client = OpenCTIClient(
    url="https://opencti.example.com",
    token="token",
    retry_attempts=5,
    retry_delay=2  # Start with 2 second delay
)

try:
    result = client.search_ioc("8.8.8.8")
except OpenCTIClientError as e:
    if "unauthorized" in str(e).lower():
        # Don't retry auth errors
        print("Authentication failed")
    else:
        # All retries exhausted
        print(f"All attempts failed: {e}")
```

---

## Best Practices

### Performance

1. **Use caching:** Enable cache with appropriate TTL
2. **Limit results:** Set `first` parameter appropriately
3. **Batch operations:** Use `handle_alerts()` for multiple IOCs
4. **Avoid redundant queries:** Check history before enrichment

### Error Handling

1. **Always catch exceptions:** Use try/except around client calls
2. **Implement retries:** For transient failures
3. **Log errors:** For debugging and monitoring
4. **Graceful degradation:** Continue processing on individual failures

### Security

1. **Secure tokens:** Never commit tokens to version control
2. **Verify SSL:** Always verify certificates in production
3. **Use proxies:** For network isolation if required
4. **Principle of least privilege:** Use tokens with minimal required permissions

---

## Support

For additional assistance:
- Review the [User Guide](opencti-plugin-guide.md)
- Check the [Configuration Reference](opencti-configuration-reference.md)
- Consult the [Troubleshooting Guide](opencti-troubleshooting.md)

---

*This API reference is part of the comprehensive DFIR-IRIS OpenCTI plugin documentation.*
