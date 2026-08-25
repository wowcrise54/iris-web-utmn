#!/usr/bin/env python3
#
#  IRIS OpenCTI Module Source Code
#  contact@dfir-iris.org
#
#  This program is free software; you can redistribute it and/or
#  modify it under the terms of the GNU Lesser General Public
#  License as published by the Free Software Foundation; either
#  version 3 of the License, or (at your option) any later version.

module_name = "IrisOpenCTI"
module_description = "Provides an interface between OpenCTI and IRIS"
interface_version = "1.2.0"
module_version = "1.3.0"
pipeline_support = False
pipeline_info = {}

DEFAULT_REPORT_TEMPLATE = """
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
            <a class="btn btn-sm btn-outline-primary float-right" href="{{ match.opencti_url }}"
               target="_blank" rel="noopener noreferrer">Open in OpenCTI</a>
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
                    - <a href="{{ entity.opencti_url }}" target="_blank"
                         rel="noopener noreferrer">OpenCTI</a>
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
"""

module_configuration = [
    {
        "param_name": "opencti_url",
        "param_human_name": "OpenCTI URL",
        "param_description": "Base OpenCTI URL. The module appends /graphql when needed.",
        "default": "",
        "mandatory": True,
        "type": "string",
        "section": "OpenCTI"
    },
    {
        "param_name": "opencti_token",
        "param_human_name": "OpenCTI API token",
        "param_description": "OpenCTI API token used as Bearer authentication.",
        "default": "",
        "mandatory": True,
        "type": "sensitive_string",
        "section": "OpenCTI"
    },
    {
        "param_name": "opencti_public_url",
        "param_human_name": "OpenCTI browser URL",
        "param_description": (
            "Optional URL reachable from analyst browsers. "
            "Used only for links; defaults to the OpenCTI API URL."
        ),
        "default": "",
        "mandatory": False,
        "type": "string",
        "section": "OpenCTI"
    },
    {
        "param_name": "opencti_verify_ssl",
        "param_human_name": "Verify TLS certificate",
        "param_description": "Verify the OpenCTI TLS certificate.",
        "default": True,
        "mandatory": True,
        "type": "bool",
        "section": "OpenCTI"
    },
    {
        "param_name": "opencti_timeout",
        "param_human_name": "Request timeout",
        "param_description": "Timeout in seconds for OpenCTI GraphQL requests.",
        "default": 20,
        "mandatory": True,
        "type": "int",
        "section": "OpenCTI"
    },
    {
        "param_name": "opencti_max_results",
        "param_human_name": "Maximum search results",
        "param_description": "Maximum number of indicators and observables to retrieve for each IOC lookup.",
        "default": 20,
        "mandatory": True,
        "type": "int",
        "section": "OpenCTI"
    },
    {
        "param_name": "opencti_min_score",
        "param_human_name": "Minimum OpenCTI score",
        "param_description": "Ignore OpenCTI objects with a lower x_opencti_score. Use 0 to keep all matches.",
        "default": 0,
        "mandatory": True,
        "type": "int",
        "section": "OpenCTI"
    },
    {
        "param_name": "opencti_store_raw_enrichment",
        "param_human_name": "Store raw enrichment",
        "param_description": "Store OpenCTI matches in the IOC ioc_enrichment field.",
        "default": True,
        "mandatory": True,
        "type": "bool",
        "section": "Insights"
    },
    {
        "param_name": "opencti_report_as_attribute",
        "param_human_name": "Add OpenCTI report as IOC attribute",
        "param_description": "Render a human-readable OpenCTI report in the IOC custom attributes.",
        "default": True,
        "mandatory": True,
        "type": "bool",
        "section": "Insights"
    },
    {
        "param_name": "opencti_report_template",
        "param_human_name": "OpenCTI report template",
        "param_description": "Jinja2 HTML template used for the IOC OpenCTI report attribute.",
        "default": DEFAULT_REPORT_TEMPLATE,
        "mandatory": False,
        "type": "textfield_html",
        "section": "Templates"
    },
    {
        "param_name": "opencti_add_tags",
        "param_human_name": "Tag enriched IOCs",
        "param_description": "Add opencti:* tags to IOCs enriched from OpenCTI.",
        "default": True,
        "mandatory": True,
        "type": "bool",
        "section": "Insights"
    },
    {
        "param_name": "opencti_manual_alert_max_iocs",
        "param_human_name": "Maximum IOCs per alert lookup",
        "param_description": "Reject a manual alert lookup when it contains more unique IOCs than this limit.",
        "default": 100,
        "mandatory": True,
        "type": "int",
        "section": "OpenCTI"
    },
    {
        "param_name": "opencti_manual_ioc_hook_enabled",
        "param_human_name": "Manual trigger on IOCs",
        "param_description": "Offer the manual 'Получить данные из OpenCTI' action on IOCs.",
        "default": True,
        "mandatory": True,
        "type": "bool",
        "section": "Triggers"
    },
    {
        "param_name": "opencti_manual_alert_hook_enabled",
        "param_human_name": "Manual trigger on alerts",
        "param_description": "Offer the manual 'Обогатить IOC алёрта через OpenCTI' action on alerts.",
        "default": True,
        "mandatory": True,
        "type": "bool",
        "section": "Triggers"
    },
    {
        "param_name": "opencti_cache_enabled",
        "param_human_name": "Enable query caching",
        "param_description": "Cache OpenCTI query results to improve performance.",
        "default": True,
        "mandatory": True,
        "type": "bool",
        "section": "Performance"
    },
    {
        "param_name": "opencti_cache_ttl",
        "param_human_name": "Cache TTL (seconds)",
        "param_description": "Time-to-live for cached OpenCTI queries.",
        "default": 300,
        "mandatory": True,
        "type": "int",
        "section": "Performance"
    },
    {
        "param_name": "opencti_cache_size",
        "param_human_name": "Cache size",
        "param_description": "Maximum number of entries in the cache.",
        "default": 1000,
        "mandatory": True,
        "type": "int",
        "section": "Performance"
    },
    {
        "param_name": "opencti_retry_enabled",
        "param_human_name": "Enable retry logic",
        "param_description": "Retry failed OpenCTI requests with exponential backoff.",
        "default": True,
        "mandatory": True,
        "type": "bool",
        "section": "Reliability"
    },
    {
        "param_name": "opencti_retry_attempts",
        "param_human_name": "Retry attempts",
        "param_description": "Number of retry attempts for failed requests.",
        "default": 3,
        "mandatory": True,
        "type": "int",
        "section": "Reliability"
    },
    {
        "param_name": "opencti_retry_delay",
        "param_human_name": "Initial retry delay (seconds)",
        "param_description": "Initial delay before first retry attempt.",
        "default": 1,
        "mandatory": True,
        "type": "int",
        "section": "Reliability"
    },
    {
        "param_name": "opencti_auto_enrich_alerts",
        "param_human_name": "Auto-enrich alerts on creation",
        "param_description": "Automatically enrich alerts with OpenCTI data when created.",
        "default": False,
        "mandatory": True,
        "type": "bool",
        "section": "Automation"
    },
    {
        "param_name": "opencti_auto_enrich_min_iocs",
        "param_human_name": "Minimum IOCs for auto-enrichment",
        "param_description": "Minimum number of IOCs required for auto-enrichment.",
        "default": 1,
        "mandatory": True,
        "type": "int",
        "section": "Automation"
    },
    {
        "param_name": "opencti_min_confidence",
        "param_human_name": "Minimum confidence score",
        "param_description": "Minimum OpenCTI confidence score (0-100) for matches.",
        "default": 20,
        "mandatory": True,
        "type": "int",
        "section": "Filtering"
    }
]
