# OpenCTI Plugin Configuration Reference

> **Version:** 1.3.0  
> **Last Updated:** August 2026

---

## Overview

This document provides a complete reference for all configuration parameters available in the DFIR-IRIS OpenCTI plugin. Parameters are organized by section for easier navigation.

---

## Configuration Sections

1. [OpenCTI Connection](#opencti-connection)
2. [Performance](#performance)
3. [Filtering](#filtering)
4. [Insights](#insights)
5. [Automation](#automation)
6. [Reliability](#reliability)
7. [Triggers](#triggers)
8. [Templates](#templates)

---

## OpenCTI Connection

### opencti_url

**Type:** `string`  
**Mandatory:** Yes  
**Default:** `""`

Base URL of your OpenCTI instance. The module will append `/graphql` when making API requests.

**Example:**
```json
{
  "opencti_url": "https://opencti.example.com"
}
```

**Notes:**
- Do not include trailing slash
- Include protocol (http:// or https://)
- The module automatically appends `/graphql`

---

### opencti_token

**Type:** `sensitive_string`  
**Mandatory:** Yes  
**Default:** `""`

OpenCTI API authentication token. This token is used as a Bearer token for all API requests.

**Example:**
```json
{
  "opencti_token": "your-api-token-here"
}
```

**Security Notes:**
- Store securely using IRIS sensitive string handling
- Token is encrypted at rest in the database
- Never commit tokens to version control
- Rotate tokens periodically

**Token Permissions Required:**
- Read access to Indicators
- Read access to StixCyberObservables
- Read access to relationships and containers

---

### opencti_public_url

**Type:** `string`  
**Mandatory:** No  
**Default:** Same as `opencti_url`

Browser-reachable URL for OpenCTI links in reports and UI elements. Useful when the API URL differs from the browser URL (e.g., internal API, external web interface).

**Example:**
```json
{
  "opencti_url": "http://opencti-internal:8080",
  "opencti_public_url": "https://opencti.example.com"
}
```

**Use Cases:**
- API accessible internally, web UI externally
- Different ports for API and web interface
- Load balancer vs. backend service URLs

---

### opencti_verify_ssl

**Type:** `bool`  
**Mandatory:** Yes  
**Default:** `true`

Whether to verify TLS/SSL certificates when connecting to OpenCTI.

**Example:**
```json
{
  "opencti_verify_ssl": true
}
```

**Recommendations:**
- **Production:** Always `true`
- **Development/Testing:** Can be `false` for self-signed certs
- **Security:** Never disable in production environments

---

### opencti_timeout

**Type:** `int`  
**Mandatory:** Yes  
**Default:** `20`

Timeout in seconds for GraphQL requests to OpenCTI.

**Example:**
```json
{
  "opencti_timeout": 30
}
```

**Guidelines:**
- **Fast network (same datacenter):** 10-15 seconds
- **Standard network:** 20-30 seconds
- **Slow network/remote:** 30-60 seconds
- **Very large result sets:** Consider increasing max_results instead

---

### opencti_max_results

**Type:** `int`  
**Mandatory:** Yes  
**Default:** `20`

Maximum number of indicators and observables to retrieve for each IOC lookup.

**Example:**
```json
{
  "opencti_max_results": 50
}
```

**Guidelines:**
- **Quick lookups:** 10-20 results
- **Standard enrichment:** 20-50 results
- **Deep analysis:** 50-100 results (may impact performance)

**Performance Impact:**
- More results = longer query time
- More results = larger enrichment data
- Balance between completeness and performance

---

### opencti_manual_alert_max_iocs

**Type:** `int`  
**Mandatory:** Yes  
**Default:** `100`

Maximum number of unique IOCs allowed in a manual alert enrichment request.

**Example:**
```json
{
  "opencti_manual_alert_max_iocs": 50
}
```

**Purpose:**
- Prevents overwhelming OpenCTI with massive batch requests
- Protects against accidental bulk operations
- Can be increased for dedicated high-performance instances

---

## Performance

### opencti_cache_enabled

**Type:** `bool`  
**Mandatory:** Yes  
**Default:** `true`

Enable in-memory caching of OpenCTI query results.

**Example:**
```json
{
  "opencti_cache_enabled": true
}
```

**Benefits:**
- Reduces redundant API calls
- Improves response time for repeated queries
- Decreases load on OpenCTI server

**When to Disable:**
- Need always-fresh data (not recommended)
- Debugging cache-related issues
- Extremely limited memory environments

---

### opencti_cache_ttl

**Type:** `int`  
**Mandatory:** Yes  
**Default:** `300`

Time-to-live for cached OpenCTI queries in seconds.

**Example:**
```json
{
  "opencti_cache_ttl": 600
}
```

**Guidelines:**
- **High-frequency queries:** 60-120 seconds (2-2 minutes)
- **Standard:** 300 seconds (5 minutes)
- **Low-change environments:** 600-1800 seconds (10-30 minutes)

**Trade-offs:**
- Shorter TTL = fresher data, more API calls
- Longer TTL = better performance, potentially stale data

---

### opencti_cache_size

**Type:** `int`  
**Mandatory:** Yes  
**Default:** `1000`

Maximum number of entries in the query cache.

**Example:**
```json
{
  "opencti_cache_size": 2000
}
```

**Memory Impact:**
- Each cache entry: ~10-50 KB (depending on result size)
- 1000 entries: ~10-50 MB
- 10000 entries: ~100-500 MB

**Guidelines:**
- **Small instances:** 500-1000 entries
- **Medium instances:** 1000-5000 entries
- **Large instances:** 5000-10000 entries

---

## Filtering

### opencti_min_score

**Type:** `int`  
**Mandatory:** Yes  
**Default:** `0`

Minimum `x_opencti_score` value for matches to be included. Range: 0-100.

**Example:**
```json
{
  "opencti_min_score": 50
}
```

**Score Interpretation:**
- **0-20:** Low confidence / informational
- **20-50:** Medium confidence / suspicious
- **50-80:** High confidence / malicious
- **80-100:** Very high confidence / confirmed threat

**Recommendations:**
- **Strict filtering:** 50-70 (high-confidence only)
- **Balanced:** 30-50 (standard)
- **Lenient:** 0-20 (include all matches)

---

### opencti_min_confidence

**Type:** `int`  
**Mandatory:** Yes  
**Default:** `20`

Minimum OpenCTI confidence score (0-100) for matches.

**Example:**
```json
{
  "opencti_min_confidence": 50
}
```

**Confidence Levels:**
- **0-20:** Unverified / unconfirmed
- **20-50:** Partially verified
- **50-80:** Verified / confirmed
- **80-100:** Highly verified / authoritative

---

## Insights

### opencti_store_raw_enrichment

**Type:** `bool`  
**Mandatory:** Yes  
**Default:** `true`

Store raw OpenCTI enrichment data in the IOC's `ioc_enrichment` field.

**Example:**
```json
{
  "opencti_store_raw_enrichment": true
}
```

**When True:**
- Full match data stored in IOC
- Available for future analysis
- Can be exported/reused

**When False:**
- Only summary data stored
- Smaller database footprint
- Raw matches not preserved

---

### opencti_report_as_attribute

**Type:** `bool`  
**Mandatory:** Yes  
**Default:** `true`

Render a human-readable HTML report as a custom IOC attribute.

**Example:**
```json
{
  "opencti_report_as_attribute": true
}
```

**Benefits:**
- Quick visual reference in IRIS UI
- Formatted presentation of enrichment data
- Easy sharing with analysts

**Attribute Name:** "OpenCTI Report"

---

### opencti_add_tags

**Type:** `bool`  
**Mandatory:** Yes  
**Default:** `true`

Automatically add OpenCTI-derived tags to enriched IOCs.

**Example:**
```json
{
  "opencti_add_tags": true
}
```

**Generated Tags:**
- `opencti:match` - Indicates OpenCTI match
- `opencti:label:<label-name>` - For each entity label

**Tag Management:**
- Tags are automatically managed (replaced on re-enrichment)
- Can be disabled to preserve manual tagging
- Useful for automated workflows and filtering

---

## Automation

### opencti_auto_enrich_alerts

**Type:** `bool`  
**Mandatory:** Yes  
**Default:** `false`

Automatically trigger OpenCTI enrichment when alerts are created.

**Example:**
```json
{
  "opencti_auto_enrich_alerts": true
}
```

**Behavior:**
- Triggers on alert creation via API or UI
- Runs asynchronously via Celery
- Analysts see results when alert opens
- No manual action required

**Considerations:**
- May increase alert creation latency slightly
- Requires Celery/Redis infrastructure
- Best for high-volume environments

---

### opencti_auto_enrich_min_iocs

**Type:** `int`  
**Mandatory:** Yes  
**Default:** `1`

Minimum number of IOCs required in an alert for auto-enrichment to trigger.

**Example:**
```json
{
  "opencti_auto_enrich_min_iocs": 3
}
```

**Use Cases:**
- **1:** Enrich all alerts with any IOC
- **3+:** Only enrich alerts with multiple IOCs (reduce noise)
- **Higher values:** Focus on high-priority alerts only

---

## Reliability

### opencti_retry_enabled

**Type:** `bool`  
**Mandatory:** Yes  
**Default:** `true`

Enable automatic retry of failed OpenCTI requests with exponential backoff.

**Example:**
```json
{
  "opencti_retry_enabled": true
}
```

**Retry Behavior:**
- Attempt 1: Immediate
- Attempt 2: After 1 second (default delay)
- Attempt 3: After 2 seconds
- Attempt 4: After 4 seconds

**When to Disable:**
- Debugging connection issues
- Want immediate failure feedback
- Custom retry logic elsewhere

---

### opencti_retry_attempts

**Type:** `int`  
**Mandatory:** Yes  
**Default:** `3`

Number of retry attempts for failed requests (not including initial attempt).

**Example:**
```json
{
  "opencti_retry_attempts": 5
}
```

**Guidelines:**
- **Standard:** 3 attempts
- **Unreliable network:** 5-7 attempts
- **Critical systems:** More attempts with longer delays

---

### opencti_retry_delay

**Type:** `int`  
**Mandatory:** Yes  
**Default:** `1`

Initial delay in seconds before the first retry attempt.

**Example:**
```json
{
  "opencti_retry_delay": 2
}
```

**Exponential Backoff:**
- Delay doubles with each retry
- Formula: `delay * (2 ^ attempt_number)`
- With default (1s): 1s → 2s → 4s

**Adjustments:**
- Increase for rate-limited APIs
- Decrease for fast-failing errors

---

## Triggers

### opencti_manual_ioc_hook_enabled

**Type:** `bool`  
**Mandatory:** Yes  
**Default:** `true`

Enable the manual "Get OpenCTI data" action on individual IOCs.

**Example:**
```json
{
  "opencti_manual_ioc_hook_enabled": true
}
```

**UI Impact:**
- Shows right-click context menu option on IOCs
- Allows on-demand IOC enrichment
- Useful for ad-hoc investigations

---

### opencti_manual_alert_hook_enabled

**Type:** `bool`  
**Mandatory:** Yes  
**Default:** `true`

Enable the manual "Enrich alert with OpenCTI" action on alerts.

**Example:**
```json
{
  "opencti_manual_alert_hook_enabled": true
}
```

**UI Impact:**
- Shows alert action button/menu item
- Allows manual trigger of full alert enrichment
- Primary method for enrichment when auto-enrich is disabled

---

## Templates

### opencti_report_template

**Type:** `textfield_html`  
**Mandatory:** No  
**Default:** (see below)

Jinja2 HTML template for rendering the OpenCTI report attribute.

**Default Template:**
```html
<div class="row">
  <div class="col-12">
    <h3>OpenCTI results for {{ query_value }}</h3>
    <p>{{ matches|length }} matching object(s) returned by OpenCTI.</p>
    {% for match in matches %}
      <div class="card mb-2">
        <div class="card-header">
          <strong>{{ match.name or match.value or match.id }}</strong>
          <span class="badge badge-light ml-2">{{ match.entity_type }}</span>
          {% if match.score is not none %}
            <span class="badge badge-info ml-2">score: {{ match.score }}</span>
          {% endif %}
          {% if match.confidence is not none %}
            <span class="badge badge-secondary ml-2">confidence: {{ match.confidence }}</span>
          {% endif %}
          {% if match.opencti_url %}
            <a class="btn btn-sm btn-outline-primary float-right" 
               href="{{ match.opencti_url }}" target="_blank" 
               rel="noopener noreferrer">Open in OpenCTI</a>
          {% endif %}
        </div>
        <div class="card-body">
          {% if match.description %}
            <p>{{ match.description }}</p>
          {% endif %}
          {% if match.pattern %}
            <pre>{{ match.pattern }}</pre>
          {% endif %}
          {% if match.labels %}
            <p><strong>Labels:</strong> {{ match.labels|join(", ") }}</p>
          {% endif %}
          {% if match.markings %}
            <p><strong>Markings:</strong> {{ match.markings|join(", ") }}</p>
          {% endif %}
          {% if match.valid_from or match.valid_until %}
            <p><strong>Validity:</strong> {{ match.valid_from or "unknown" }} — {{ match.valid_until or "open" }}</p>
          {% endif %}
          {% if match.external_references %}
            <ul>
              {% for ref in match.external_references %}
                <li>{{ ref.source_name }}{% if ref.external_id %}: {{ ref.external_id }}{% endif %}
                {% if ref.url %} - <a href="{{ ref.url }}" target="_blank" rel="noreferrer">{{ ref.url }}</a>{% endif %}</li>
              {% endfor %}
            </ul>
          {% endif %}
          {% if match.related_entities %}
            <p><strong>Related entities:</strong></p>
            <ul>
              {% for entity in match.related_entities %}
                <li>
                  {{ entity.entity_type }}: {{ entity.name or entity.id }}
                  {% if entity.relationship_type %} ({{ entity.relationship_type }}){% endif %}
                  {% if entity.opencti_url %}
                    - <a href="{{ entity.opencti_url }}" target="_blank" rel="noopener noreferrer">OpenCTI</a>
                  {% endif %}
                </li>
              {% endfor %}
            </ul>
          {% endif %}
        </div>
      </div>
    {% endfor %}
  </div>
</div>
```

**Available Variables:**
- `query_value`: The IOC value that was queried
- `matches`: Array of matched entities with:
  - `id`, `name`, `value`, `entity_type`
  - `description`, `pattern`
  - `score`, `confidence`
  - `labels`, `markings`
  - `valid_from`, `valid_until`
  - `external_references`
  - `related_entities`
  - `opencti_url`

**Customization Tips:**
- Use Bootstrap classes for styling
- Add conditional logic with Jinja2 `{% if %}`
- Loop through collections with `{% for %}`
- Filter data with Jinja2 filters (`|join`, `|length`, etc.)
- Test templates in a development environment first

---

## Complete Configuration Example

```json
{
  "opencti_url": "https://opencti.example.com",
  "opencti_token": "your-api-token",
  "opencti_public_url": "https://opencti.example.com",
  "opencti_verify_ssl": true,
  "opencti_timeout": 30,
  "opencti_max_results": 50,
  "opencti_min_score": 30,
  "opencti_min_confidence": 50,
  "opencti_store_raw_enrichment": true,
  "opencti_report_as_attribute": true,
  "opencti_add_tags": true,
  "opencti_manual_alert_max_iocs": 100,
  "opencti_manual_ioc_hook_enabled": true,
  "opencti_manual_alert_hook_enabled": true,
  "opencti_cache_enabled": true,
  "opencti_cache_ttl": 600,
  "opencti_cache_size": 2000,
  "opencti_retry_enabled": true,
  "opencti_retry_attempts": 3,
  "opencti_retry_delay": 1,
  "opencti_auto_enrich_alerts": true,
  "opencti_auto_enrich_min_iocs": 3,
  "opencti_report_template": "..."
}
```

---

## Configuration Validation

### Common Validation Errors

| Error | Cause | Solution |
|-------|-------|----------|
| `Invalid URL` | URL missing protocol or malformed | Add `https://` prefix |
| `Unauthorized` | Invalid or expired token | Regenerate token in OpenCTI |
| `SSL verification failed` | Self-signed cert with verify_ssl=true | Set to false (dev only) or add cert |
| `Connection timeout` | Timeout too short or network issue | Increase timeout or check network |
| `Invalid score` | Score outside 0-100 range | Use value between 0-100 |

### Testing Configuration

1. **Connection Test:**
   - Use the module's "Test Connection" button
   - Verify API response and authentication

2. **Enrichment Test:**
   - Create test alert with known IOC
   - Trigger enrichment manually
   - Verify results appear correctly

3. **Performance Test:**
   - Monitor enrichment time with different `max_results`
   - Adjust cache settings based on usage patterns

---

## Environment Variables

Some configuration can also be set via environment variables:

| Environment Variable | Config Parameter | Priority |
|---------------------|------------------|----------|
| `OPENCTI_URL` | `opencti_url` | Low |
| `OPENCTI_TOKEN` | `opencti_token` | Low |
| `OPENCTI_CACHE_SIZE` | `opencti_cache_size` | Low |
| `OPENCTI_CACHE_TTL` | `opencti_cache_ttl` | Low |

**Note:** UI configuration takes precedence over environment variables.

---

## Migration Guide

### From Version 1.2.x to 1.3.0

**New Parameters:**
- `opencti_min_confidence` (default: 20) - Add if filtering by confidence needed
- `opencti_retry_enabled`, `opencti_retry_attempts`, `opencti_retry_delay` - Add for reliability

**No Breaking Changes:** All existing configurations remain compatible.

---

## Support

For configuration assistance:
- Review the [User Guide](opencti-plugin-guide.md)
- Check [Troubleshooting Guide](opencti-troubleshooting.md)
- Contact DFIR-IRIS support

---

*This reference is part of the comprehensive DFIR-IRIS OpenCTI plugin documentation.*
