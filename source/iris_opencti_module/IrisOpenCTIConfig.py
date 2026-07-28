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
module_version = "1.0.0"
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
          {% if match.external_references %}
            <ul>
              {% for ref in match.external_references %}
                <li>{{ ref.source_name }}{% if ref.external_id %}: {{ ref.external_id }}{% endif %}
                {% if ref.url %} - <a href="{{ ref.url }}" target="_blank" rel="noreferrer">{{ ref.url }}</a>{% endif %}</li>
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
        "param_name": "opencti_add_matching_iocs",
        "param_human_name": "Add matching OpenCTI IOCs",
        "param_description": "Attach matching indicators/observables returned by OpenCTI to alerts and cases.",
        "default": True,
        "mandatory": True,
        "type": "bool",
        "section": "Insights"
    },
    {
        "param_name": "opencti_manual_ioc_hook_enabled",
        "param_human_name": "Manual trigger on IOCs",
        "param_description": "Offer a manual OpenCTI lookup action on IOCs.",
        "default": True,
        "mandatory": True,
        "type": "bool",
        "section": "Triggers"
    },
    {
        "param_name": "opencti_manual_alert_hook_enabled",
        "param_human_name": "Manual trigger on alerts",
        "param_description": "Offer a manual OpenCTI enrichment action on alerts.",
        "default": True,
        "mandatory": True,
        "type": "bool",
        "section": "Triggers"
    },
    {
        "param_name": "opencti_manual_case_hook_enabled",
        "param_human_name": "Manual trigger on cases",
        "param_description": "Offer a manual OpenCTI enrichment action on cases.",
        "default": True,
        "mandatory": True,
        "type": "bool",
        "section": "Triggers"
    },
    {
        "param_name": "opencti_on_ioc_create_hook_enabled",
        "param_human_name": "Run on IOC create",
        "param_description": "Automatically enrich IOCs after they are created.",
        "default": False,
        "mandatory": True,
        "type": "bool",
        "section": "Triggers"
    },
    {
        "param_name": "opencti_on_ioc_update_hook_enabled",
        "param_human_name": "Run on IOC update",
        "param_description": "Automatically enrich IOCs after they are updated.",
        "default": False,
        "mandatory": True,
        "type": "bool",
        "section": "Triggers"
    },
    {
        "param_name": "opencti_on_alert_create_hook_enabled",
        "param_human_name": "Run on alert create",
        "param_description": "Automatically enrich alert IOCs after an alert is created.",
        "default": False,
        "mandatory": True,
        "type": "bool",
        "section": "Triggers"
    },
    {
        "param_name": "opencti_on_alert_update_hook_enabled",
        "param_human_name": "Run on alert update",
        "param_description": "Automatically enrich alert IOCs after an alert is updated.",
        "default": False,
        "mandatory": True,
        "type": "bool",
        "section": "Triggers"
    },
    {
        "param_name": "opencti_on_case_update_hook_enabled",
        "param_human_name": "Run on case update",
        "param_description": "Automatically enrich case IOCs after a case is updated.",
        "default": False,
        "mandatory": True,
        "type": "bool",
        "section": "Triggers"
    }
]
