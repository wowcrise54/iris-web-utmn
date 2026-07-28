#!/usr/bin/env python3

import traceback

from flask_login import current_user
from jinja2 import Template
from sqlalchemy.orm.attributes import flag_modified

import iris_interface.IrisInterfaceStatus as InterfaceStatus
from app import db
from app.datamgmt.case.case_iocs_db import add_ioc
from app.datamgmt.manage.manage_attribute_db import add_tab_attribute_field
from app.datamgmt.manage.manage_attribute_db import get_default_custom_attributes
from app.models.alerts import Alert
from app.models.cases import Cases
from app.models.models import Ioc
from app.models.models import IocType
from app.models.authorization import User

from iris_opencti_module.opencti_handler.opencti_client import OpenCTIClient
from iris_opencti_module.opencti_handler.opencti_client import OpenCTIClientError
from iris_opencti_module.opencti_handler.opencti_mapping import build_enrichment_payload
from iris_opencti_module.opencti_handler.opencti_mapping import normalize_search_results


class OpenCTIHandler:
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

    @staticmethod
    def _current_user_id(fallback_user_id=None):
        try:
            if current_user and current_user.is_authenticated:
                return current_user.id
        except Exception:
            pass

        if fallback_user_id:
            return fallback_user_id

        user = User.query.first()
        return user.id if user else None

    @staticmethod
    def _get_ioc_type(type_name):
        ioc_type = IocType.query.filter(IocType.type_name == type_name).first()
        if ioc_type:
            return ioc_type

        return IocType.query.filter(IocType.type_name == "other").first()

    @staticmethod
    def _tag_list(tags):
        if not tags:
            return []

        return [tag.strip() for tag in tags.split(",") if tag.strip()]

    def _append_tags(self, ioc, tags):
        if not self.mod_config.get("opencti_add_tags", True):
            return

        current_tags = self._tag_list(ioc.ioc_tags)
        for tag in tags:
            if tag and tag not in current_tags:
                current_tags.append(tag)

        ioc.ioc_tags = ",".join(current_tags)[:512]

    def _render_report(self, query_value, matches):
        template = Template(self.mod_config.get("opencti_report_template") or "")
        return template.render(query_value=query_value, matches=matches)

    def _store_enrichment(self, ioc, enrichment):
        if self.mod_config.get("opencti_store_raw_enrichment", True):
            ioc.ioc_enrichment = ioc.ioc_enrichment or {}
            ioc.ioc_enrichment["opencti"] = enrichment
            flag_modified(ioc, "ioc_enrichment")

        if self.mod_config.get("opencti_report_as_attribute", True):
            rendered_report = self._render_report(
                query_value=enrichment.get("query_value"),
                matches=enrichment.get("matches", []),
            )
            add_tab_attribute_field(
                ioc,
                tab_name="OpenCTI Report",
                field_name="HTML report",
                field_type="html",
                field_value=rendered_report,
            )

    def _enrich_ioc(self, ioc):
        if not ioc or not ioc.ioc_value:
            return InterfaceStatus.I2Success(), []

        self.log.info(f"Searching OpenCTI for IOC {ioc.ioc_value}")
        try:
            raw_results = self.client.search_ioc(
                value=ioc.ioc_value,
                first=int(self.mod_config.get("opencti_max_results") or 20),
            )
        except OpenCTIClientError as exc:
            self.log.error(f"OpenCTI lookup failed for {ioc.ioc_value}: {exc}")
            return InterfaceStatus.I2Error(message=str(exc)), []

        matches = normalize_search_results(
            raw_results,
            min_score=int(self.mod_config.get("opencti_min_score") or 0),
        )

        enrichment = build_enrichment_payload(ioc.ioc_value, matches)
        self._store_enrichment(ioc, enrichment)

        if matches:
            tags = ["opencti:match"]
            for match in matches:
                for label in match.get("labels", []):
                    tags.append(f"opencti:{label}")
            self._append_tags(ioc, tags)

        db.session.commit()
        return InterfaceStatus.I2Success(message="OpenCTI enrichment completed"), matches

    def _make_ioc_from_match(self, match, case_id=None, user_id=None):
        ioc_type = self._get_ioc_type(match.get("iris_ioc_type"))
        if not ioc_type:
            return None

        ioc = Ioc()
        ioc.ioc_value = match.get("value")
        ioc.ioc_type_id = ioc_type.type_id
        ioc.ioc_description = self._build_ioc_description(match)
        ioc.ioc_tags = self._build_ioc_tags(match)
        ioc.case_id = case_id
        ioc.user_id = user_id
        ioc.custom_attributes = self._safe_default_ioc_attributes()
        ioc.ioc_enrichment = {
            "opencti": build_enrichment_payload(match.get("value"), [match])
        }
        return ioc

    def _safe_default_ioc_attributes(self):
        try:
            return get_default_custom_attributes("ioc")
        except Exception:
            return {}

    @staticmethod
    def _build_ioc_tags(match):
        tags = ["opencti", f"opencti:{match.get('source')}"]
        for label in match.get("labels", []):
            tags.append(f"opencti:{label}")
        return ",".join([tag for tag in tags if tag])[:512]

    @staticmethod
    def _build_ioc_description(match):
        lines = [
            "Imported from OpenCTI.",
            f"OpenCTI ID: {match.get('id') or 'n/a'}",
            f"Entity type: {match.get('entity_type') or 'n/a'}",
        ]
        if match.get("name"):
            lines.append(f"Name: {match.get('name')}")
        if match.get("score") is not None:
            lines.append(f"OpenCTI score: {match.get('score')}")
        if match.get("description"):
            lines.append("")
            lines.append(match.get("description"))
        if match.get("pattern"):
            lines.append("")
            lines.append(match.get("pattern"))
        return "\n".join(lines)

    @staticmethod
    def _same_ioc(existing_ioc, value, type_id):
        return existing_ioc.ioc_value == value and existing_ioc.ioc_type_id == type_id

    def _attach_matches_to_alert(self, alert, matches):
        if not self.mod_config.get("opencti_add_matching_iocs", True):
            return 0

        added = 0
        user_id = self._current_user_id(alert.alert_owner_id)
        for match in matches:
            value = match.get("value")
            if not value:
                continue

            ioc_type = self._get_ioc_type(match.get("iris_ioc_type"))
            if not ioc_type:
                continue

            if any(self._same_ioc(ioc, value, ioc_type.type_id) for ioc in alert.iocs):
                continue

            ioc = self._make_ioc_from_match(match, case_id=None, user_id=user_id)
            if ioc is None:
                continue
            db.session.add(ioc)

            alert.iocs.append(ioc)
            added += 1

        if added:
            db.session.commit()

        return added

    def _attach_matches_to_case(self, case, matches):
        if not self.mod_config.get("opencti_add_matching_iocs", True):
            return 0

        added = 0
        user_id = self._current_user_id(case.owner_id or case.user_id)
        for match in matches:
            value = match.get("value")
            if not value:
                continue

            ioc_type = self._get_ioc_type(match.get("iris_ioc_type"))
            if not ioc_type:
                continue

            existing = (
                Ioc.query
                .filter(Ioc.case_id == case.case_id)
                .filter(Ioc.ioc_value == value)
                .filter(Ioc.ioc_type_id == ioc_type.type_id)
                .first()
            )
            if existing:
                continue

            ioc = self._make_ioc_from_match(match, case_id=case.case_id, user_id=user_id)
            if ioc is None:
                continue
            add_ioc(ioc, user_id, case.case_id)
            added += 1

        return added

    def handle_iocs(self, data):
        in_status = InterfaceStatus.IIStatus(code=InterfaceStatus.I2CodeNoError)

        for ioc in data:
            status, _ = self._enrich_ioc(ioc)
            in_status = InterfaceStatus.merge_status(in_status, status)

        return in_status(data=data)

    def handle_alerts(self, data):
        in_status = InterfaceStatus.IIStatus(code=InterfaceStatus.I2CodeNoError)

        for alert in data:
            if not isinstance(alert, Alert):
                continue

            all_matches = []
            for ioc in alert.iocs:
                status, matches = self._enrich_ioc(ioc)
                in_status = InterfaceStatus.merge_status(in_status, status)
                all_matches.extend(matches)

            added = self._attach_matches_to_alert(alert, all_matches)
            self.log.info(f"Attached {added} OpenCTI IOC(s) to alert #{alert.alert_id}")

        return in_status(data=data)

    def handle_cases(self, data):
        in_status = InterfaceStatus.IIStatus(code=InterfaceStatus.I2CodeNoError)

        for case in data:
            if not isinstance(case, Cases):
                continue

            iocs = Ioc.query.filter(Ioc.case_id == case.case_id).all()
            all_matches = []
            for ioc in iocs:
                status, matches = self._enrich_ioc(ioc)
                in_status = InterfaceStatus.merge_status(in_status, status)
                all_matches.extend(matches)

            added = self._attach_matches_to_case(case, all_matches)
            self.log.info(f"Attached {added} OpenCTI IOC(s) to case #{case.case_id}")

        return in_status(data=data)

    def safe_handle(self, handler, data):
        try:
            return handler(data)
        except Exception:
            self.log.error(traceback.format_exc())
            return InterfaceStatus.I2Error(message="OpenCTI handler failed", logs=[traceback.format_exc()])
