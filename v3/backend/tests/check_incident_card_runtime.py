"""Live incident-card acceptance. Run inside app container; never prints credentials.

Creates only uniquely named scratch cases/users/sources and removes only those IDs.
Original case 1/2 and alert 1 rows are fingerprinted before and after cleanup.
"""

import base64
from datetime import datetime, timezone
from copy import deepcopy
import hashlib
import io
import json
import sys
import uuid
import urllib.error
import urllib.request
import zipfile

sys.path.insert(0, "/iriswebapp")
from app import app
from app.db import db
from app.business.auth import generate_auth_tokens
from app.datamgmt.case_transfer.transfer_db import (
    read_case_bundle,
    _entity_query,
)
from app.datamgmt.case_transfer.transfer_spec import ENTITIES
from app.models.alerts import Alert, AlertCaseAssociation, Severity, AlertStatus
from app.models.assets import CaseAssets
from app.models.authorization import (
    User,
    Group,
    UserGroup,
    UserClient,
    UserCaseAccess,
    UserCaseEffectiveAccess,
    GroupCaseAccess,
    OrganisationCaseAccess,
    UserAuthSession,
    CaseAccessLevel,
    Permissions,
)
from app.models.cases import Cases
from app.models.incident_cards import IncidentCard
from app.models.iocs import Ioc
from app.models.models import (
    CaseTasks,
    DataStoreFile,
    UserActivity,
)
from sqlalchemy import select

PREFIX = "incident-card-acceptance-" + uuid.uuid4().hex[:12]
BASE = "http://127.0.0.1:8000"
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))
CHECKS = []
OWNED_CASES = []
OWNED_ALERTS = []
OWNED_USERS = []
OWNED_GROUPS = []
OWNED_SESSIONS = []


def expect(condition, message):
    if not condition:
        raise AssertionError(message)


def checked(name):
    CHECKS.append(name)


def api(method, path, token=None, body=None):
    headers = {"Accept": "application/json", "Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    raw = None if body is None else json.dumps(body).encode()
    request = urllib.request.Request(
        BASE + path, data=raw, headers=headers, method=method
    )
    try:
        with OPENER.open(request, timeout=60) as response:
            status = response.status
            content = response.read()
    except urllib.error.HTTPError as error:
        status = error.code
        content = error.read()
    try:
        result = json.loads(content)
    except (UnicodeDecodeError, json.JSONDecodeError):
        result = {}
    return status, result


def data(method, path, token, body=None, status=200):
    actual, result = api(method, path, token, body)
    expect(
        actual == status,
        method + " " + path + " returned " + str(actual) + " expected " + str(status),
    )
    # Native v2 returns data directly; also accept a connector/proxy envelope.
    return (
        result["data"]
        if "data" in result
        and "schema_version" not in result
        and "case_id" not in result
        else result
    )


def token_for(user):
    before = {row.sid for row in UserAuthSession.query.filter_by(user_id=user.id).all()}
    result = generate_auth_tokens(user, mfa_verified=True)
    after = {row.sid for row in UserAuthSession.query.filter_by(user_id=user.id).all()}
    OWNED_SESSIONS.extend(after - before)
    return result["access_token"]


def fingerprint():
    content = {}
    for model, condition in [
        (Cases, Cases.case_id.in_([1, 2, 3])),
        (Alert, Alert.alert_id.in_([1, 2])),
        (CaseAssets, CaseAssets.case_id.in_([1, 2, 3])),
        (Ioc, Ioc.case_id.in_([1, 2, 3])),
        (DataStoreFile, DataStoreFile.file_case_id.in_([1, 2, 3])),
        (CaseTasks, CaseTasks.task_case_id.in_([1, 2, 3])),
        (IncidentCard, IncidentCard.case_id.in_([1, 2, 3])),
    ]:
        rows = (
            db.session.execute(select(model.__table__).where(condition))
            .mappings()
            .all()
        )
        content[model.__tablename__] = sorted(
            [dict(row) for row in rows],
            key=lambda row: json.dumps(row, sort_keys=True, default=str),
        )
    return {
        "cases": Cases.query.count(),
        "alerts": Alert.query.count(),
        "original_sha256": hashlib.sha256(
            json.dumps(content, sort_keys=True, default=str).encode()
        ).hexdigest(),
    }


def put_body(card, fields=None, selections=None):
    return dict(
        schema_version=1,
        revision=card["revision"],
        fields=fields or {},
        selections=deepcopy(card["selections"]) if selections is None else selections,
    )


def cleanup():
    db.session.rollback()
    for case_id in reversed(OWNED_CASES):
        case = Cases.query.filter_by(case_id=case_id).first()
        if case is None:
            continue
        scratch_name = (
            case.name.split(" - ", 1)[-1] if case.name.startswith("#") else case.name
        )
        expect(
            scratch_name.strip().startswith(PREFIX),
            "Cleanup refused unexpected case name",
        )
        # Delete case-owned transfer entities in dependency order; do not call
        # legacy delete_case, whose asset-link query has an unscoped predicate.
        for spec in reversed(ENTITIES):
            for row in _entity_query(spec, case_id).all():
                db.session.delete(row)
            db.session.flush()
        for model in [
            AlertCaseAssociation,
            UserCaseAccess,
            UserCaseEffectiveAccess,
            GroupCaseAccess,
            OrganisationCaseAccess,
            UserActivity,
        ]:
            for row in model.query.filter_by(case_id=case_id).all():
                db.session.delete(row)
        db.session.flush()
        db.session.delete(case)
        db.session.flush()
    for identifier in OWNED_ALERTS:
        row = Alert.query.filter_by(alert_id=identifier).first()
        if row:
            expect(
                row.alert_title.startswith(PREFIX), "Cleanup refused unexpected alert"
            )
            db.session.delete(row)
    for sid in OWNED_SESSIONS:
        for row in UserAuthSession.query.filter_by(sid=sid).all():
            db.session.delete(row)
    for identifier in OWNED_USERS:
        user = User.query.filter_by(id=identifier).first()
        if not user:
            continue
        expect(user.user.startswith(PREFIX), "Cleanup refused unexpected user")
        for model in [
            UserGroup,
            UserClient,
            UserCaseAccess,
            UserCaseEffectiveAccess,
            UserActivity,
        ]:
            for row in model.query.filter_by(user_id=identifier).all():
                db.session.delete(row)
        db.session.flush()
        db.session.delete(user)
    for identifier in OWNED_GROUPS:
        group = Group.query.filter_by(group_id=identifier).first()
        if group:
            expect(
                group.group_name.startswith(PREFIX), "Cleanup refused unexpected group"
            )
            db.session.delete(group)
    db.session.commit()


def run():
    admin = (
        User.query.filter_by(user="administrator").first()
        or User.query.filter_by(user="admin").first()
    )
    expect(admin is not None, "Administrator not found")
    admin_token = token_for(admin)
    customer_id = Cases.query.filter_by(case_id=1).first().client_id
    created = data(
        "POST",
        "/api/v2/cases",
        admin_token,
        dict(
            case_name=PREFIX + "-source",
            case_description="Acceptance scratch case",
            case_soc_id=PREFIX,
            case_customer_id=customer_id,
        ),
        201,
    )
    case_id = created["case_id"]
    OWNED_CASES.append(case_id)
    endpoint = "/api/v2/cases/" + str(case_id) + "/incident-card"
    card = data("GET", endpoint, admin_token)
    db.session.expire_all()
    expect(
        card["revision"] == 0
        and IncidentCard.query.filter_by(case_id=case_id).first() is None,
        "GET must remain virtual",
    )
    expect(
        set(card["meta"]) == {"case_id"}
        and card["selections"] == {}
        and "sources" not in card
        and "completeness" not in card,
        "Removed metadata returned",
    )
    checked("virtual GET and regulation-only API")
    for level in ("Высокий", "Средний", "Низкий"):
        card = data(
            "PUT",
            endpoint,
            admin_token,
            put_body(card, {"criticality": dict(value=level, mode="manual")}),
        )
        expect(
            card["fields"]["criticality"]["value"] == level,
            "Russian enum did not round trip",
        )
    for rejected in ("Highbla", "High", "Критический", "Critical"):
        expect(
            api(
                "PUT",
                endpoint,
                admin_token,
                put_body(card, {"criticality": dict(value=rejected, mode="manual")}),
            )[0]
            == 400,
            "Invalid criticality accepted",
        )
    checked("three Russian criticality values; arbitrary text and critical rejected")

    narrative = "<script>alert(1)</script> " + "Полный текст расследования. " * 700
    fields = {
        k: dict(value=v, mode="manual")
        for k, v in dict(
            categories=[8],
            prioritization_type="key",
            occurred_at="2026-10-13T05:00:00+05:00",
            detected_at="2026-10-13T00:10:00Z",
            investigation_started_at="2026-10-13T00:15:00Z",
            incident_ended_at="2026-10-13T01:00:00Z",
            completed=True,
            reporter_name="Acceptance Reporter",
            prepared_by=[
                {"name": "Автор первый", "position": "Аналитик"},
                {"name": "Автор второй", "position": "Руководитель"},
            ],
            description=narrative,
            incident_types=["natural_fire_repeat"],
            incident_location="Проверочный адрес",
        ).items()
    }
    card = data("PUT", endpoint, admin_token, put_body(card, fields))
    expect(
        card["revision"] == 4
        and card["derived"]["importance"] == "low"
        and card["derived"]["priority"] == 7,
        "Category8 priority wrong",
    )
    expect(card["derived"]["incident_duration_seconds"] == 3600, "Duration wrong")
    expect(
        card["fields"]["occurred_at"]["value"] == "2026-10-13T00:00:00+00:00",
        "UTC normalization wrong",
    )
    checked("save/reopen, category8, independent repeated checkbox, UTC and duration")
    stale = put_body(card)
    stale["revision"] = 0
    expect(
        api("PUT", endpoint, admin_token, stale)[0] == 409, "Stale revision must reject"
    )
    for key in [
        "title",
        "external_id",
        "organization",
        "mitre_tactic",
        "attack_source",
        "attack_target",
        "account",
        "files",
        "hashes",
        "additional_info",
        "category8_reason",
        "prepared_position",
    ]:
        expect(
            api(
                "PUT",
                endpoint,
                admin_token,
                put_body(card, {key: dict(value="forbidden", mode="manual")}),
            )[0]
            == 400,
            "Obsolete field accepted: " + key,
        )
    expect(
        api("PUT", endpoint, admin_token, put_body(card, selections={"file_ids": [1]}))[
            0
        ]
        == 400,
        "Obsolete link accepted",
    )
    checked("real HTTP409 and rejection of deleted fields and links")
    card = data(
        "PUT",
        endpoint,
        admin_token,
        put_body(card, {"priority_override": dict(value=2, mode="manual")}),
    )
    expect(card["derived"]["priority"] == 2, "Expert override wrong")
    reopened = data("GET", endpoint, admin_token)
    expect(reopened["fields"] == card["fields"], "Saved fields did not round trip")
    checked("expert priority override and saved snapshot")
    exported = data("GET", endpoint + "/export?timezone=UTC", admin_token)
    expect(exported["revision"] == card["revision"], "Export snapshot mismatch")
    expect(
        "<script>" not in exported["html"] and "&lt;script&gt;" in exported["html"],
        "Unsafe export HTML",
    )
    with zipfile.ZipFile(
        io.BytesIO(base64.b64decode(exported["docx_base64"]))
    ) as archive:
        xml = archive.read("word/document.xml").decode()
        expect(
            "Продолжение." in xml
            and narrative.replace("<script>", "&lt;script&gt;").replace(
                "</script>", "&lt;/script&gt;"
            )
            in xml,
            "Continuation lost text",
        )
        expect(
            len([n for n in archive.namelist() if n.startswith("word/media/")]) == 0,
            "Native export must not embed scanned pages",
        )
    expect(
        api("GET", endpoint + "/export?timezone=invalid/not-a-zone", admin_token)[0]
        == 400,
        "Invalid timezone accepted",
    )
    expect(
        "Автор первый" in xml and "Автор второй" in xml and "Руководитель" in xml,
        "Repeatable preparers lost during export",
    )
    checked(
        "real DOCX and HTML exports with full continuation and repeatable preparers"
    )
    for method, suffix, body in [
        ("GET", "", None),
        ("PUT", "", put_body(card)),
        ("GET", "/export", None),
    ]:
        expect(
            api(method, endpoint + suffix, None, body)[0] in (401, 403),
            "Anonymous access accepted",
        )
    checked("anonymous read/write/export denied")
    readonly = User(
        user=PREFIX + "-reader",
        name="Acceptance reader",
        email=PREFIX + "@invalid.test",
        password="unusable",
        active=True,
    )
    group = Group(
        group_name=PREFIX + "-reader-group",
        group_description="Acceptance only",
        group_permissions=Permissions.standard_user.value,
    )
    db.session.add_all([readonly, group])
    db.session.flush()
    OWNED_USERS.append(readonly.id)
    OWNED_GROUPS.append(group.group_id)
    db.session.add_all(
        [
            UserGroup(user_id=readonly.id, group_id=group.group_id),
            UserClient(
                user_id=readonly.id,
                client_id=customer_id,
                access_level=CaseAccessLevel.read_only.value,
                allow_alerts=False,
            ),
            UserCaseAccess(
                user_id=readonly.id,
                case_id=case_id,
                access_level=CaseAccessLevel.read_only.value,
            ),
            UserCaseEffectiveAccess(
                user_id=readonly.id,
                case_id=case_id,
                access_level=CaseAccessLevel.read_only.value,
            ),
        ]
    )
    db.session.commit()
    read_token = token_for(readonly)
    data("GET", endpoint, read_token)
    expect(
        api("PUT", endpoint, read_token, put_body(card))[0] == 403,
        "Read-only user save must deny",
    )
    data("GET", endpoint + "/export?timezone=UTC", read_token)
    checked("real read-only ACL read/export allowed write denied")

    case_payload, entities, collector = read_case_bundle(case_id)
    bundle_card = entities["incident_card"][0]
    expect(
        bundle_card["selections"] == {} and "files" not in bundle_card["fields"],
        "Case bundle leaked old links or fields",
    )
    expect(
        bundle_card["fields"]["description"]["value"] == narrative,
        "Case bundle lost narrative",
    )
    checked("case transfer export preserves regulation snapshot without source links")
    medium = Severity.query.filter(Severity.severity_name.ilike("Medium")).first()
    expect(medium is not None, "Medium source severity missing")
    state = AlertStatus.query.order_by(AlertStatus.status_id).first()
    origin = Alert(
        alert_title=PREFIX + "-autofill",
        alert_source="Acceptance SIEM",
        alert_severity_id=medium.severity_id,
        alert_status_id=state.status_id,
        alert_customer_id=customer_id,
        alert_owner_id=admin.id,
        alert_source_event_time=datetime(2026, 10, 19, 8),
        alert_creation_time=datetime.now(timezone.utc).replace(tzinfo=None),
    )
    db.session.add(origin)
    db.session.commit()
    OWNED_ALERTS.append(origin.alert_id)
    before = datetime.now(timezone.utc)
    status, created = api(
        "POST",
        "/api/v2/alerts/escalate/" + str(origin.alert_id),
        admin_token,
        dict(
            iocs_import_list=[],
            assets_import_list=[],
            import_as_event=False,
            case_title=PREFIX + "-escalated",
            case_tags="",
            case_template_id=0,
        ),
    )
    db.session.expire_all()
    for row in Cases.query.filter(Cases.name.contains(PREFIX + "-escalated")).all():
        if row.case_id not in OWNED_CASES:
            OWNED_CASES.append(row.case_id)
    expect(status == 200, "Escalation returned " + str(status))
    created = created.get("data", created)
    escalated_id = created["case_id"]
    expect(
        escalated_id in OWNED_CASES, "Escalation case was not registered for cleanup"
    )
    high = Severity.query.filter(Severity.severity_name.ilike("High")).first()
    case_row = Cases.query.filter_by(case_id=escalated_id).one()
    case_row.severity_id = high.severity_id
    db.session.commit()
    route = "/api/v2/cases/" + str(escalated_id) + "/incident-card"
    automatic = data("GET", route, admin_token)
    expect(
        automatic["fields"]["criticality"]["value"] == "Средний",
        "Alert severity did not map to card",
    )
    expect(
        automatic["fields"]["detection_source"]["value"] == "Acceptance SIEM",
        "Detection source missing",
    )
    moment = datetime.fromisoformat(automatic["fields"]["incident_at"]["value"])
    expect(
        before <= moment <= datetime.now(timezone.utc),
        "Incident time is not escalation time",
    )
    expect(
        automatic["fields"]["occurred_at"]["value"] == "2026-10-19T08:00:00+00:00",
        "Occurrence time did not map",
    )
    expect(
        automatic["fields"]["priority_override"]["mode"] == "auto",
        "Priority must default to auto",
    )
    automatic = data(
        "PUT",
        route,
        admin_token,
        put_body(
            automatic,
            {
                "criticality": dict(value="Низкий", mode="manual"),
                "completed": dict(value=True, mode="manual"),
                "categories": dict(value=[2], mode="manual"),
                "prioritization_type": dict(value="target", mode="manual"),
            },
        ),
    )
    expect(
        automatic["fields"]["criticality"]["value"] == "Низкий",
        "Manual criticality overwritten",
    )
    expect(
        automatic["fields"]["incident_ended_at"]["value"]
        and automatic["derived"]["incident_duration_seconds"] > 0,
        "Close time/duration not populated",
    )
    expect(
        automatic["derived"]["priority"] == 1
        and automatic["fields"]["priority_override"]["value"] == 1,
        "Computed priority selector not populated",
    )
    checked(
        "actual alert escalation defaults, editable severity, automatic close time and computed priority selector"
    )


def main():
    with app.app_context():
        baseline = fingerprint()
        try:
            run()
        finally:
            cleanup()
            db.session.expire_all()
            expect(fingerprint() == baseline, "Original baseline changed after cleanup")
        print(
            json.dumps(
                {
                    "status": "passed",
                    "checks": CHECKS,
                    "scratch_cases_removed": len(OWNED_CASES),
                    "scratch_users_removed": len(OWNED_USERS),
                    "original_baseline_unchanged": True,
                },
                ensure_ascii=False,
            )
        )


if __name__ == "__main__":
    main()
