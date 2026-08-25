# DFIR-IRIS OpenCTI Plugin User Guide

> **Version:** 1.3.0  
> **Last Updated:** August 2026  
> **Compatibility:** DFIR-IRIS 2.x+, OpenCTI 6.x+

---

## Table of Contents

1. [Introduction](#introduction)
2. [Quick Start](#quick-start)
3. [Installation](#installation)
4. [Configuration](#configuration)
5. [Usage Scenarios](#usage-scenarios)
6. [Enrichment Features](#enrichment-features)
7. [Advanced Features](#advanced-features)
8. [Best Practices](#best-practices)
9. [FAQ](#faq)

---

## Introduction

The DFIR-IRIS OpenCTI plugin integrates DFIR-IRIS with OpenCTI (Open Cyber Threat Intelligence), enabling automatic enrichment of IOCs (Indicators of Compromise) with threat intelligence data from your OpenCTI instance.

### Key Features

- **Automatic IOC Enrichment**: Enrich IOCs from alerts with OpenCTI threat intelligence
- **Real-time Progress Tracking**: WebSocket-based progress updates during enrichment
- **Smart Deduplication**: Avoid redundant lookups with intelligent caching
- **Advanced Filtering**: Filter results by confidence, score, labels, and entity types
- **Batch Processing**: Handle bulk IOC enrichment efficiently
- **Customizable Reports**: Jinja2 templates for tailored enrichment reports
- **Auto-enrichment**: Automatically enrich alerts on creation
- **Enrichment History**: Track and reuse historical enrichment results

### Architecture Overview

```
┌─────────────┐     ┌──────────────────┐     ┌─────────────┐
│   DFIR-IRIS │ ──► │ OpenCTI Module   │ ──► │  OpenCTI    │
│   (Alerts)  │     │ (Handler + Client)│    │  (GraphQL)  │
└─────────────┘     └──────────────────┘     └─────────────┘
                            │
                            ▼
                    ┌──────────────────┐
                    │  Enrichment      │
                    │  History & Cache │
                    └──────────────────┘
```

---

## Quick Start

### Prerequisites

- DFIR-IRIS 2.x or later
- OpenCTI 6.x or later instance
- OpenCTI API token with read permissions
- Python 3.11+ (for module development)

### Installation Steps

1. **Install the module** via DFIR-IRIS module management:
   ```bash
   # Clone or copy the module to IRIS modules directory
   cp -r iris_opencti_module /opt/irisapp/modules/
   ```

2. **Configure the module** in DFIR-IRIS:
   - Navigate to **Configuration → Modules**
   - Click **Add Module**
   - Select `IrisOpenCTI`
   - Fill in required parameters (see Configuration section)

3. **Test the connection**:
   - Go to **Modules → IrisOpenCTI**
   - Click **Test Connection**
   - Verify successful connection to OpenCTI

### First Enrichment

1. Create or open an alert with IOCs
2. Click **Enrich with OpenCTI** from the alert actions
3. Watch the real-time progress bar
4. Review enrichment results in the IOC details

---

## Configuration

### Required Parameters

| Parameter | Description | Example |
|-----------|-------------|---------|
| `opencti_url` | Base URL of your OpenCTI instance | `https://opencti.yourcompany.com` |
| `opencti_token` | OpenCTI API authentication token | `your-api-token-here` |
| `opencti_verify_ssl` | Verify TLS certificate | `true` |
| `opencti_timeout` | Request timeout in seconds | `20` |

### Optional Parameters

#### OpenCTI Connection
| Parameter | Default | Description |
|-----------|---------|-------------|
| `opencti_public_url` | (same as opencti_url) | Browser-reachable URL for links |
| `opencti_max_results` | `20` | Maximum results per IOC lookup |
| `opencti_min_score` | `0` | Minimum x_opencti_score to include |

#### Performance
| Parameter | Default | Description |
|-----------|---------|-------------|
| `opencti_cache_enabled` | `true` | Enable query caching |
| `opencti_cache_ttl` | `300` | Cache TTL in seconds |
| `opencti_cache_size` | `1000` | Maximum cache entries |
| `opencti_retry_enabled` | `true` | Enable retry with backoff |
| `opencti_retry_attempts` | `3` | Number of retry attempts |
| `opencti_retry_delay` | `1` | Initial retry delay (seconds) |

#### Automation
| Parameter | Default | Description |
|-----------|---------|-------------|
| `opencti_auto_enrich_alerts` | `false` | Auto-enrich on alert creation |
| `opencti_auto_enrich_min_iocs` | `1` | Minimum IOCs for auto-enrichment |

#### Filtering
| Parameter | Default | Description |
|-----------|---------|-------------|
| `opencti_min_confidence` | `20` | Minimum confidence score (0-100) |

#### Insights
| Parameter | Default | Description |
|-----------|---------|-------------|
| `opencti_store_raw_enrichment` | `true` | Store raw enrichment data |
| `opencti_report_as_attribute` | `true` | Add HTML report as IOC attribute |
| `opencti_add_tags` | `true` | Add opencti:* tags to IOCs |

### Configuration Example

```json
{
  "opencti_url": "https://opencti.example.com",
  "opencti_token": "your-api-token",
  "opencti_verify_ssl": true,
  "opencti_timeout": 30,
  "opencti_max_results": 50,
  "opencti_min_score": 30,
  "opencti_min_confidence": 50,
  "opencti_cache_enabled": true,
  "opencti_cache_ttl": 600,
  "opencti_auto_enrich_alerts": true,
  "opencti_auto_enrich_min_iocs": 3
}
```

---

## Usage Scenarios

### Scenario 1: Manual Alert Enrichment

**When to use:** You've received an alert and want to enrich it with threat intelligence.

**Steps:**
1. Open the alert in DFIR-IRIS
2. Click **Actions → Enrich with OpenCTI**
3. Wait for enrichment to complete (progress shown in real-time)
4. Review the enrichment results:
   - Matched entities with scores and confidence
   - Related entities and relationships
   - Sightings data
   - Generated tags

**Expected Output:**
- IOC tags updated with `opencti:match` and label-based tags
- Custom attribute "OpenCTI Report" with formatted HTML
- Enrichment data stored in `ioc_enrichment` field

### Scenario 2: Automatic Enrichment on Alert Creation

**When to use:** You want all new alerts to be enriched automatically.

**Configuration:**
```json
{
  "opencti_auto_enrich_alerts": true,
  "opencti_auto_enrich_min_iocs": 1
}
```

**Behavior:**
- When an alert is created with IOCs, enrichment triggers automatically
- Enrichment runs asynchronously via Celery
- Analysts receive real-time progress updates
- No manual intervention required

### Scenario 3: Manual IOC Enrichment

**When to use:** You want to enrich a specific IOC without creating an alert.

**Steps:**
1. Navigate to the IOC in DFIR-IRIS
2. Right-click the IOC
3. Select **Get OpenCTI data**
4. View results in the IOC detail panel

### Scenario 4: Batch IOC Enrichment

**When to use:** You have a list of IOCs to enrich (e.g., from a CSV export).

**Steps:**
1. Export IOCs from your source system
2. Import into DFIR-IRIS as a bulk alert or use the batch API
3. Trigger enrichment with the batch processor
4. Review aggregated results

---

## Enrichment Features

### IOC Type Support

The plugin supports all standard STIX 2.1 cyber observables:

| IOC Type | Example | Enrichment Data |
|----------|---------|-----------------|
| Domain Name | `malicious.example.com` | Domain registration, related domains, sightings |
| IPv4 Address | `192.168.1.100` | Geolocation, ASN, related infrastructure |
| IPv6 Address | `2001:db8::1` | Geolocation, ASN, related infrastructure |
| URL | `https://evil.com/malware.exe` | Domain, IP, file hashes |
| File Hash (MD5/SHA1/SHA256) | `e99a18c428cb38d5f260853678922e03` | Malware families, samples, sightings |
| Email Address | `phishing@evil.com` | Sender reputation, related campaigns |

### Enrichment Data Fields

For each matched entity, the plugin retrieves:

- **Basic Information**: Name, description, entity type, pattern
- **Scoring**: `x_opencti_score`, confidence level
- **Labels**: Threat type, severity, TLP markings
- **Validity**: `valid_from`, `valid_until` dates
- **External References**: Source information, URLs
- **Related Entities**: Connected indicators, malware, campaigns
- **Sightings**: Count, first/last seen timestamps
- **Graph Data**: Relationship context (optional)

### Tag Generation

The plugin automatically generates tags based on matched entities:

```
opencti:match                    # Indicates OpenCTI match
opencti:label:malicious          # Based on entity labels
opencti:label:phishing
opencti:label:tlp:amber
```

Tags are added to the IOC's `ioc_tags` field and can be used for filtering and automation.

### Report Generation

A formatted HTML report is generated for each enriched IOC using a Jinja2 template. The default template includes:

- Match summary with count
- Entity cards with key information
- Labels and markings
- Validity periods
- External references
- Related entities
- Links to OpenCTI

**Customize the report** by modifying `opencti_report_template` in the configuration.

---

## Advanced Features

### Filtering and Search

The plugin supports advanced filtering of OpenCTI results:

#### Entity Type Filtering
```python
from iris_opencti_module.opencti_handler.filters import EntityFilter

# Only match Indicators
filter = EntityFilter('Indicator')

# Match multiple types
filter = EntityFilter(['Indicator', 'StixCyberObservable'])

# Exclude types
filter = EntityFilter(['Malware'], exclude=True)
```

#### Label Filtering
```python
from iris_opencti_module.opencti_handler.filters import LabelFilter

# Must have all labels
filter = LabelFilter(['malicious', 'phishing'], require_all=True)

# Must have any label
filter = LabelFilter(['malicious', 'suspicious'], require_all=False)

# Exclude entities with labels
filter = LabelFilter(['safe', 'whitelisted'], exclude=True)
```

#### Score and Confidence Filtering
```python
from iris_opencti_module.opencti_handler.filters import ScoreFilter, ConfidenceFilter

# Score between 50-100
filter = ScoreFilter(min_score=50, max_score=100)

# Confidence at least 70
filter = ConfidenceFilter(min_confidence=70)
```

#### Date Range Filtering
```python
from iris_opencti_module.opencti_handler.filters import DateRangeFilter

# Valid within last 30 days
from datetime import datetime, timedelta
end = datetime.utcnow()
start = end - timedelta(days=30)

filter = DateRangeFilter('valid_from', start=start.isoformat(), end=end.isoformat())
```

#### Combining Filters
```python
from iris_opencti_module.opencti_handler.filters import AndFilter, OrFilter

# Complex filter: Indicator with high score AND malicious label
complex_filter = (
    EntityFilter('Indicator') &
    ScoreFilter(min_score=50) &
    LabelFilter('malicious')
)

# Alternative syntax using builder
from iris_opencti_module.opencti_handler.filters import FilterBuilder

builder = FilterBuilder()
filter = (
    builder
    .entity_type('Indicator')
    .score(min_score=50)
    .label('malicious')
    .build()
)
```

### Caching and Deduplication

The plugin implements intelligent caching to improve performance:

#### Cache Configuration
```json
{
  "opencti_cache_enabled": true,
  "opencti_cache_ttl": 300,
  "opencti_cache_size": 1000
}
```

#### Enrichment History
- **TTL-based expiration**: Records expire after configured hours (default: 24)
- **Smart deduplication**: Skips redundant lookups for recent matches
- **Retry logic**: Errors are retried, successful matches are cached
- **Size limits**: Automatic cleanup when history exceeds max size

**History Behavior:**
- **Match**: Cached and reused within TTL (no re-enrichment)
- **No Match**: Cached but re-enriched on next request
- **Error**: Always retried on next request

### WebSocket Progress Updates

Real-time progress updates are provided during enrichment:

```javascript
// Client-side JavaScript example
const socket = io();

socket.emit('join_enrichment', { alert_id: 123 });

socket.on('opencti_progress', (data) => {
    console.log(`Progress: ${data.processed}/${data.total}`);
    console.log(`Matched: ${data.matched}, Errors: ${data.errors}`);
    updateProgressBar(data.processed / data.total * 100);
});
```

**Progress Data Structure:**
```json
{
  "alert_id": 123,
  "kind": "opencti_enrichment",
  "total": 10,
  "processed": 5,
  "matched": 3,
  "no_match": 1,
  "errors": 1,
  "current_ioc": "8.8.8.8",
  "status": "running"
}
```

### Batch Processing

For bulk enrichment operations:

```python
from iris_opencti_module.opencti_handler.batch_processor import BatchProcessor

processor = BatchProcessor(
    max_batch_size=50,
    rate_limit=10  # queries per second
)

result = processor.add_batch([
    "malicious.example.com",
    "192.168.1.100",
    "e99a18c428cb38d5f260853678922e03"
])

if result["accepted"]:
    print(f"Batch accepted. Queue size: {result['queue_size']}")
else:
    print(f"Batch rejected: {result['error']}")
```

---

## Best Practices

### Configuration Recommendations

1. **Start Conservative**: Begin with higher `opencti_min_score` (30-50) to reduce noise
2. **Enable Caching**: Always enable caching for performance
3. **Set Reasonable Timeouts**: 20-30 seconds for most networks
4. **Configure SSL Verification**: Keep `opencti_verify_ssl: true` in production

### Performance Optimization

1. **Use Caching**: Enable caching with appropriate TTL (5-10 minutes)
2. **Batch IOCs**: Group related IOCs for single enrichment runs
3. **Limit Results**: Set `opencti_max_results` based on your needs (10-20 typical)
4. **Filter Early**: Use minimum score/confidence to reduce processing

### Security Considerations

1. **Token Management**: Store API tokens securely using IRIS sensitive string fields
2. **SSL Verification**: Always verify SSL certificates in production
3. **Proxy Configuration**: Use proxies for network isolation if required
4. **Rate Limiting**: Respect OpenCTI server rate limits with `rate_limit` settings

### Tagging Strategy

1. **Consistent Labels**: Use standardized label naming in OpenCTI
2. **TLP Markings**: Ensure TLP labels are properly configured
3. **Tag Cleanup**: Review `opencti_add_tags` behavior to avoid tag bloat
4. **Custom Tags**: Add organization-specific tags alongside OpenCTI tags

### Error Handling

1. **Retry Logic**: Enable retry with exponential backoff
2. **Timeout Tuning**: Increase timeout for slow OpenCTI instances
3. **Error Logging**: Monitor logs for recurring enrichment failures
4. **Fallback Behavior**: Configure graceful degradation for OpenCTI outages

---

## FAQ

### Q: Why are some IOCs not being enriched?
**A:** Check the following:
- IOC has fewer than `opencti_auto_enrich_min_iocs` (for auto-enrichment)
- IOC value matches a safe pattern (e.g., Google DNS)
- Cache contains a recent successful result
- OpenCTI has no matching entities

### Q: How do I customize the enrichment report?
**A:** Modify the `opencti_report_template` configuration parameter with a custom Jinja2 template. See the default template in `IrisOpenCTIConfig.py` for reference.

### Q: Can I disable automatic tag generation?
**A:** Yes, set `opencti_add_tags: false` in the configuration.

### Q: How long are enrichment results cached?
**A:** By default, 300 seconds (5 minutes). Configure via `opencti_cache_ttl`.

### Q: What happens when OpenCTI is unavailable?
**A:** The plugin will:
1. Retry failed requests (if `opencti_retry_enabled: true`)
2. Store error status in enrichment data
3. Continue processing remaining IOCs
4. Mark alert enrichment as "partial" if some fail

### Q: How do I view historical enrichment data?
**A:** Enrichment history is stored in memory and expires based on TTL. For persistent history, enable `opencti_store_raw_enrichment: true` to store results in the IOC's `ioc_enrichment` field.

### Q: Can I filter out specific labels from results?
**A:** Yes, use the `LabelFilter` with `exclude=True` or configure `opencti_min_confidence` to filter low-confidence matches.

### Q: How do I troubleshoot connection issues?
**A:** 
1. Verify `opencti_url` is correct and accessible
2. Check `opencti_token` is valid
3. Test SSL certificate with `opencti_verify_ssl: false` temporarily
4. Check network proxies if configured
5. Review logs for specific error messages

---

## Support

For issues or questions:
- Check the [Troubleshooting Guide](opencti-troubleshooting.md)
- Review the [Configuration Reference](opencti-configuration-reference.md)
- Consult the DFIR-IRIS community forums
- Open an issue on the project repository

---

*This guide is part of the comprehensive DFIR-IRIS OpenCTI plugin documentation.*
