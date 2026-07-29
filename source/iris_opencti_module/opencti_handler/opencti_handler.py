#!/usr/bin/env python3

import copy
import re
import traceback
from urllib.parse import urlsplit

from jinja2 import Environment
from jinja2 import select_autoescape
from sqlalchemy.orm.attributes import flag_modified
from celery import current_task

import iris_interface.IrisInterfaceStatus as InterfaceStatus
from app import db
from app.models.alerts import Alert

from iris_opencti_module.opencti_handler.opencti_client import OpenCTIClient
from iris_opencti_module.opencti_handler.opencti_client import OpenCTIClientError
from iris_opencti_module.opencti_handler.opencti_mapping import build_enrichment_payload
from iris_opencti_module.opencti_handler.opencti_mapping import canonicalize_ioc_value
from iris_opencti_module.opencti_handler.opencti_mapping import normalize_related_entities
from iris_opencti_module.opencti_handler.opencti_mapping import normalize_search_results
from iris_opencti_module.opencti_handler.opencti_mapping import utc_now_iso
from iris_opencti_module.opencti_handler.opencti_insights import alert_recommendation
from iris_opencti_module.opencti_handler.opencti_insights import calculate_verdict
from iris_opencti_module.opencti_handler.opencti_insights import graph_fingerprint
from iris_opencti_module.opencti_handler.opencti_insights import normalize_graph


class OpenCTIHandler:
    _RELATED_ENTITIES_LIMIT = 20

    def __init__(self, mod_config, server_config, logger):
        self.mod_config = mod_config
        self.server_config = server_config
        self.log = logger
        self.client = self._build_client()

    def _build_client(self):
        proxies = {}
        http_proxy = self.server_config.get("http_proxy")
        https_proxy = self.server_config.get("https_proxy")
        if http_proxy:
            proxies["http"] = http_proxy
        if https_proxy:
            proxies["https"] = https_proxy

        return OpenCTIClient(
            url=self.mod_config.get("opencti_url"),
            token=self.mod_config.get("opencti_token"),
            verify_ssl=self.mod_config.get("opencti_verify_ssl", True),
            timeout=int(self.mod_config.get("opencti_timeout") or 20),
            proxies=proxies,
        )

    def _display_base_url(self):
        return self.mod_config.get("opencti_public_url") or self.mod_config.get("opencti_url")

    @staticmethod
    def _tag_list(tags):
        if not tags:
            return []

        return [tag.strip() for tag in tags.split(",") if tag.strip()]

    @staticmethod
    def _label_tag(label):
        slug = re.sub(r"[^a-z0-9._-]+", "-", str(label).strip().lower()).strip("-")
        return f"opencti:label:{slug}" if slug else None

    def _replace_generated_tags(self, ioc, generated_tags, previous_generated_tags=None):
        current_tags = self._tag_list(ioc.ioc_tags)
        removable_tags = set(previous_generated_tags or [])
        removable_tags.add("opencti:match")
        removable_tags.update(tag for tag in current_tags if tag.startswith("opencti:label:"))
        current_tags = [tag for tag in current_tags if tag not in removable_tags]

        if not self.mod_config.get("opencti_add_tags", True):
            ioc.ioc_tags = ",".join(current_tags)[:512]
            return

        for tag in generated_tags:
            if tag and tag not in current_tags:
                current_tags.append(tag)

        ioc.ioc_tags = ",".join(current_tags)[:512]

    @staticmethod
    def _safe_report_matches(matches):
        safe_matches = copy.deepcopy(matches)
        for match in safe_matches:
            match["opencti_url"] = OpenCTIHandler._safe_http_url(match.get("opencti_url"))
            safe_references = []
            for reference in match.get("external_references", []):
                reference["url"] = OpenCTIHandler._safe_http_url(reference.get("url"))
                safe_references.append(reference)
            match["external_references"] = safe_references
            for entity in match.get("related_entities", []):
                entity["opencti_url"] = OpenCTIHandler._safe_http_url(entity.get("opencti_url"))
        return safe_matches

    @staticmethod
    def _safe_http_url(url):
        if not url:
            return None
        try:
            scheme = urlsplit(url).scheme.lower()
        except ValueError:
            return None
        return url if scheme in {"http", "https"} else None

    def _render_report(self, query_value, matches):
        environment = Environment(
            autoescape=select_autoescape(default=True),
        )
        template = environment.from_string(self.mod_config.get("opencti_report_template") or "")
        return template.render(
            query_value=query_value,
            matches=self._safe_report_matches(matches),
        )

    @staticmethod
    def _set_report_attribute(ioc, rendered_report):
        custom_attributes = copy.deepcopy(ioc.custom_attributes or {})
        report_tab = custom_attributes.setdefault("OpenCTI Report", {})
        report_tab["HTML report"] = {
            "mandatory": False,
            "type": "html",
            "value": rendered_report,
        }
        ioc.custom_attributes = custom_attributes
        flag_modified(ioc, "custom_attributes")

    def _store_enrichment(self, ioc, enrichment, update_report=True):
        stored_enrichment = copy.deepcopy(enrichment)
        if not self.mod_config.get("opencti_store_raw_enrichment", True):
            stored_enrichment["matches"] = []
        ioc_enrichment = copy.deepcopy(ioc.ioc_enrichment or {})
        ioc_enrichment["opencti"] = stored_enrichment
        ioc.ioc_enrichment = ioc_enrichment
        flag_modified(ioc, "ioc_enrichment")

        if update_report and self.mod_config.get("opencti_report_as_attribute", True):
            rendered_report = self._render_report(
                query_value=enrichment.get("query_value"),
                matches=enrichment.get("matches", []),
            )
            self._set_report_attribute(ioc, rendered_report)

    @staticmethod
    def _previous_enrichment(ioc):
        return copy.deepcopy((ioc.ioc_enrichment or {}).get("opencti") or {})

    def _store_lookup_error(self, ioc, error):
        previous = self._previous_enrichment(ioc)
        previous.update({
            "provider": "OpenCTI",
            "query_value": ioc.ioc_value,
            "status": "error",
            "last_attempt_utc": utc_now_iso(),
            "error": str(error),
        })
        previous.setdefault("generated_tags", [])
        previous.setdefault("match_count", 0)
        previous.setdefault("matches", [])
        previous.setdefault("last_lookup_utc", previous.get("last_success_utc"))
        previous.setdefault("last_success_utc", None)
        self._store_enrichment(ioc, previous, update_report=False)

    @staticmethod
    def _normalize_sightings(payload):
        edges = ((payload or {}).get("stixSightingRelationships") or {}).get("edges") or []
        nodes = [(edge or {}).get("node") or {} for edge in edges]
        counts = [int(node.get("attribute_count") or 1) for node in nodes]
        first_seen = sorted(filter(None, (node.get("first_seen") for node in nodes)))
        last_seen = sorted(filter(None, (node.get("last_seen") for node in nodes)))
        return {
            "count": sum(counts),
            "first_seen": first_seen[0] if first_seen else None,
            "last_seen": last_seen[-1] if last_seen else None,
        }

    @staticmethod
    def _update_task_progress(meta):
        try:
            if current_task and current_task.request and current_task.request.id:
                current_task.update_state(state="PROGRESS", meta=meta)
        except Exception:
            pass

    @staticmethod
    def _ioc_type_name(ioc):
        ioc_type = getattr(ioc, "ioc_type", None)
        return getattr(ioc_type, "type_name", None)

    def _enrich_ioc(self, ioc):
        if not ioc or not ioc.ioc_value:
            return InterfaceStatus.I2Success(), []

        previous = self._previous_enrichment(ioc)
        self.log.info(f"Searching OpenCTI for IOC {ioc.ioc_value}")
        try:
            raw_results = self.client.search_ioc(
                value=ioc.ioc_value,
                first=int(self.mod_config.get("opencti_max_results") or 20),
            )
        except OpenCTIClientError as exc:
            self.log.error(f"OpenCTI lookup failed for {ioc.ioc_value}: {exc}")
            self._store_lookup_error(ioc, exc)
            return InterfaceStatus.I2Error(message=str(exc)), []

        matches = normalize_search_results(
            raw_results,
            min_score=int(self.mod_config.get("opencti_min_score") or 0),
            query_value=ioc.ioc_value,
            query_type=self._ioc_type_name(ioc),
            base_url=self._display_base_url(),
        )

        for match in matches:
            try:
                related_payload = self.client.get_related_entities(
                    match.get("id"),
                    first=self._RELATED_ENTITIES_LIMIT,
                )
                match["related_entities"] = normalize_related_entities(
                    related_payload,
                    object_id=match.get("id"),
                    base_url=self._display_base_url(),
                    limit=self._RELATED_ENTITIES_LIMIT,
                )
                match["related_error"] = None
            except OpenCTIClientError as exc:
                self.log.warning(
                    f"Unable to load related OpenCTI entities for {match.get('id')}: {exc}"
                )
                match["related_entities"] = []
                match["related_error"] = str(exc)
            try:
                match["sightings"] = self._normalize_sightings(
                    self.client.get_sightings(match.get("id"))
                )
            except OpenCTIClientError as exc:
                match["sightings"] = {"count": 0, "first_seen": None, "last_seen": None}
                match["sightings_error"] = str(exc)

        generated_tags = []
        if matches:
            generated_tags.append("opencti:match")
            for match in matches:
                for label in match.get("labels", []):
                    tag = self._label_tag(label)
                    if tag and tag not in generated_tags:
                        generated_tags.append(tag)

        enrichment = build_enrichment_payload(
            ioc.ioc_value,
            matches,
            generated_tags=generated_tags,
        )
        enrichment["verdict"] = calculate_verdict(matches)
        self._store_enrichment(ioc, enrichment)
        self._replace_generated_tags(
            ioc,
            generated_tags,
            previous_generated_tags=previous.get("generated_tags", []),
        )
        return InterfaceStatus.I2Success(message="OpenCTI enrichment completed"), matches

    def _apply_cached_result(self, source_ioc, target_ioc, failed=False):
        source_enrichment = self._previous_enrichment(source_ioc)
        if failed:
            self._store_lookup_error(target_ioc, source_enrichment.get("error") or "OpenCTI lookup failed")
            return

        target_previous = self._previous_enrichment(target_ioc)
        source_enrichment["query_value"] = target_ioc.ioc_value
        self._store_enrichment(target_ioc, source_enrichment)
        self._replace_generated_tags(
            target_ioc,
            source_enrichment.get("generated_tags", []),
            previous_generated_tags=target_previous.get("generated_tags", []),
        )

    def handle_iocs(self, data):
        in_status = InterfaceStatus.IIStatus(code=InterfaceStatus.I2CodeNoError)

        for ioc in data:
            status, _ = self._enrich_ioc(ioc)
            in_status = InterfaceStatus.merge_status(in_status, status)

        db.session.commit()
        return in_status(data=data)

    def handle_alerts(self, data):
        in_status = InterfaceStatus.IIStatus(code=InterfaceStatus.I2CodeNoError)

        for alert in data:
            if not isinstance(alert, Alert):
                continue

            grouped_iocs = {}
            for ioc in alert.iocs:
                canonical_value = canonicalize_ioc_value(
                    ioc.ioc_value,
                    self._ioc_type_name(ioc),
                )
                dedupe_key = canonical_value or str(ioc.ioc_value).strip()
                grouped_iocs.setdefault(dedupe_key, []).append(ioc)

            max_iocs = int(self.mod_config.get("opencti_manual_alert_max_iocs") or 100)
            if len(grouped_iocs) > max_iocs:
                message = (
                    f"Alert #{alert.alert_id} contains {len(grouped_iocs)} unique IOCs; "
                    f"the manual OpenCTI limit is {max_iocs}"
                )
                self.log.error(message)
                return InterfaceStatus.I2Error(message=message)

            progress = {
                "kind": "opencti_enrichment", "alert_id": alert.alert_id,
                "total": len(grouped_iocs), "processed": 0, "matched": 0,
                "no_match": 0, "errors": 0, "current_ioc": None,
            }
            alert_context = copy.deepcopy(alert.alert_context or {})
            alert_context["opencti"] = {**(alert_context.get("opencti") or {}),
                                        "progress": {**progress, "status": "running",
                                                     "started_at": utc_now_iso()}}
            alert.alert_context = alert_context
            flag_modified(alert, "alert_context")
            db.session.commit()
            self._update_task_progress(progress)

            for grouped in grouped_iocs.values():
                source_ioc = grouped[0]
                progress["current_ioc"] = source_ioc.ioc_value
                status, _ = self._enrich_ioc(source_ioc)
                in_status = InterfaceStatus.merge_status(in_status, status)
                for duplicate_ioc in grouped[1:]:
                    self._apply_cached_result(
                        source_ioc,
                        duplicate_ioc,
                        failed=status.is_failure(),
                    )
                progress["processed"] += 1
                stored = self._previous_enrichment(source_ioc)
                if status.is_failure():
                    progress["errors"] += 1
                elif stored.get("status") == "match":
                    progress["matched"] += 1
                else:
                    progress["no_match"] += 1
                alert_context = copy.deepcopy(alert.alert_context or {})
                opencti_context = alert_context.setdefault("opencti", {})
                opencti_context["progress"] = {**progress, "status": "running"}
                alert.alert_context = alert_context
                flag_modified(alert, "alert_context")
                db.session.commit()
                self._update_task_progress(progress)

            recommendation = alert_recommendation(alert.iocs)
            alert_context = copy.deepcopy(alert.alert_context or {})
            opencti_context = alert_context.setdefault("opencti", {})
            opencti_context["recommendation"] = recommendation
            opencti_context["progress"] = {
                **progress, "current_ioc": None,
                "status": "partial" if progress["errors"] else "success",
                "completed_at": utc_now_iso(),
            }
            graph = opencti_context.get("graph")
            if graph and graph.get("fingerprint") != graph_fingerprint(alert.iocs):
                graph["stale"] = True
            alert.alert_context = alert_context
            flag_modified(alert, "alert_context")

            self.log.info(
                f"Enriched {len(grouped_iocs)} unique existing IOC(s) on alert #{alert.alert_id}"
            )

        db.session.commit()
        return in_status(data=data)

    @staticmethod
    def _graph_connection(payload):
        return ((payload or {}).get("stixCoreRelationships") or {})

    @staticmethod
    def _prepare_graph_relationships(connection):
        relationships = []
        for edge in connection.get("edges") or []:
            node = (edge or {}).get("node") or {}
            for endpoint_name in ("from", "to"):
                endpoint = node.get(endpoint_name) or {}
                endpoint["labels"] = [
                    item.get("value") for item in (endpoint.get("objectLabel") or []) if item.get("value")
                ]
                endpoint["markings"] = [
                    item.get("definition") for item in (endpoint.get("objectMarking") or []) if item.get("definition")
                ]
            relationships.append(node)
        return relationships

    def _fetch_graph_level(self, object_ids, remaining_edges):
        relationships, errors, cursor = [], [], None
        while object_ids and len(relationships) < remaining_edges:
            try:
                payload = self.client.get_graph_relationships(
                    object_ids, first=min(100, remaining_edges - len(relationships)), after=cursor
                )
            except OpenCTIClientError as exc:
                errors.append(str(exc))
                break
            connection = self._graph_connection(payload)
            relationships.extend(self._prepare_graph_relationships(connection))
            page_info = connection.get("pageInfo") or {}
            if not page_info.get("hasNextPage"):
                break
            cursor = page_info.get("endCursor")
            if not cursor:
                break
        return {"relationships": relationships, "errors": errors}

    def handle_alert_graphs(self, data):
        for alert in data:
            if not isinstance(alert, Alert):
                continue
            root_ids = {
                match.get("id")
                for ioc in alert.iocs
                for match in self._previous_enrichment(ioc).get("matches", [])
                if match.get("id")
            }
            if not root_ids:
                return InterfaceStatus.I2Error(message="Сначала выполните обогащение IOC alert")
            root_nodes = [
                match
                for ioc in alert.iocs
                for match in self._previous_enrichment(ioc).get("matches", [])
                if match.get("id") in root_ids
            ]

            payloads = []
            first_level = self._fetch_graph_level(root_ids, 200)
            payloads.append(first_level)
            first_level_ids = {
                endpoint.get("id")
                for relation in first_level["relationships"]
                for endpoint in (relation.get("from") or {}, relation.get("to") or {})
                if endpoint.get("id") and endpoint.get("id") not in root_ids
            }
            if first_level_ids:
                payloads.append(self._fetch_graph_level(first_level_ids, 200))
            graph = normalize_graph(
                payloads, root_ids, self._display_base_url(), node_limit=100, edge_limit=200,
                root_nodes=root_nodes,
            )
            graph.update({
                "status": "partial" if graph["errors"] else "success",
                "generated_at": utc_now_iso(),
                "fingerprint": graph_fingerprint(alert.iocs),
                "stale": False,
            })
            alert_context = copy.deepcopy(alert.alert_context or {})
            alert_context.setdefault("opencti", {})["graph"] = graph
            alert.alert_context = alert_context
            flag_modified(alert, "alert_context")
            db.session.commit()
        return InterfaceStatus.I2Success(data=data, message="OpenCTI graph completed")

    def safe_handle(self, handler, data):
        try:
            return handler(data)
        except Exception:
            db.session.rollback()
            self.log.error(traceback.format_exc())
            return InterfaceStatus.I2Error(message="OpenCTI handler failed", logs=[traceback.format_exc()])
