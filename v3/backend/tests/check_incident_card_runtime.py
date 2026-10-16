"""Live incident-card acceptance. Run inside app container; never prints credentials.

Creates only uniquely named scratch cases/users/sources and removes only those IDs.
Original case 1/2 and alert 1 rows are fingerprinted before and after cleanup.
"""

import base64
from copy import deepcopy
from datetime import datetime, timezone
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
from app.datamgmt.case.incident_card_db import get_incident_card
from app.datamgmt.case_transfer.transfer_db import (
    read_case_bundle,
    create_case_row,
    write_case_bundle,
    _entity_query,
)
from app.datamgmt.case_transfer.transfer_spec import ENTITIES
from app.models.alerts import Alert, AlertCaseAssociation, AlertStatus, Severity
from app.models.assets import CaseAssets, AssetsType
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
    IocType,
    CaseTasks,
    TaskStatus,
    DataStoreFile,
    DataStorePath,
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
        (Cases, Cases.case_id.in_([1, 2])),
        (Alert, Alert.alert_id == 1),
        (CaseAssets, CaseAssets.case_id.in_([1, 2])),
        (Ioc, Ioc.case_id.in_([1, 2])),
        (DataStoreFile, DataStoreFile.file_case_id.in_([1, 2])),
        (CaseTasks, CaseTasks.task_case_id.in_([1, 2])),
        (IncidentCard, IncidentCard.case_id.in_([1, 2])),
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
        expect(scratch_name.startswith(PREFIX), "Cleanup refused unexpected case name")
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
    if admin is None:
        admin = (
            User.query.join(UserGroup, UserGroup.user_id == User.id)
            .join(Group, Group.group_id == UserGroup.group_id)
            .filter(
                Group.group_permissions.op("&")(Permissions.server_administrator.value)
                != 0
            )
            .order_by(User.id)
            .first()
        )
    expect(admin is not None, "Administrator not found")
    admin_id = admin.id
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
        card["meta"]["author"] is None and card["meta"]["created_at"] is None,
        "Virtual card attribution must be empty",
    )
    checked("virtual GET without persistence")
    fields = {
        key: {"value": value, "mode": "manual"}
        for key, value in {
            "categories": [1, 4],
            "prioritization_type": "key",
            "occurred_at": "2026-10-13T05:00:00+05:00",
            "detected_at": "2026-10-13T00:10:00Z",
            "investigation_started_at": "2026-10-13T00:15:00Z",
            "incident_ended_at": "2026-10-13T01:00:00Z",
            "completed": True,
            "reporter_name": "Acceptance Reporter",
            "additional_info": "<script>alert(1)</script>",
        }.items()
    }
    card = data("PUT", endpoint, admin_token, put_body(card, fields))
    expect(
        card["revision"] == 1 and card["derived"]["priority"] == 3,
        "Saved priority/revision wrong",
    )
    expect(
        card["derived"]["reaction_seconds"] == 300
        and card["derived"]["incident_duration_seconds"] == 3600,
        "Timing derivation wrong",
    )
    expect(
        card["fields"]["occurred_at"]["value"] == "2026-10-13T00:00:00+00:00",
        "UTC normalization wrong",
    )
    expect(
        card["meta"]["author"] and card["meta"]["created_at"],
        "Server attribution missing",
    )
    checked("save, attribution, UTC, importance and timing")
    stale = put_body(card)
    stale["revision"] = 0
    expect(
        api("PUT", endpoint, admin_token, stale)[0] == 409,
        "Stale revision must return409",
    )
    checked("real HTTP409")
    severity = Severity.query.order_by(Severity.severity_id).first()
    alert_status = AlertStatus.query.order_by(AlertStatus.status_id).first()
    asset_type = AssetsType.query.order_by(AssetsType.asset_id).first()
    done = TaskStatus.query.filter(TaskStatus.status_name.ilike("Done")).first()
    todo = TaskStatus.query.filter(TaskStatus.status_name.ilike("To do")).first()
    hash_type = IocType.query.filter(IocType.type_name.ilike("%sha256%")).first()
    expect(
        all([severity, alert_status, asset_type, done, todo, hash_type]),
        "Required source lookups unavailable",
    )
    alert = Alert(
        alert_title=PREFIX + "-alert",
        alert_source="acceptance-source",
        alert_source_ref="acceptance-reference",
        alert_severity_id=severity.severity_id,
        alert_status_id=alert_status.status_id,
        alert_customer_id=customer_id,
        alert_source_event_time=datetime(2026, 10, 13, 0, 0),
        alert_creation_time=datetime.now(timezone.utc).replace(tzinfo=None),
    )
    db.session.add(alert)
    db.session.flush()
    OWNED_ALERTS.append(alert.alert_id)
    db.session.add(AlertCaseAssociation(case_id=case_id, alert_id=alert.alert_id))
    asset = CaseAssets(
        case_id=case_id,
        asset_name=PREFIX + "-asset",
        asset_ip="192.0.2.17",
        asset_type_id=asset_type.asset_id,
        user_id=admin_id,
    )
    ioc = Ioc(
        case_id=case_id,
        ioc_value="a" * 64,
        ioc_type_id=hash_type.type_id,
        user_id=admin_id,
    )
    performed = CaseTasks(
        task_case_id=case_id,
        task_title=PREFIX + "-done",
        task_description="Completed action",
        task_status_id=done.id,
        task_userid_open=admin_id,
    )
    planned = CaseTasks(
        task_case_id=case_id,
        task_title=PREFIX + "-todo",
        task_description="Planned action",
        task_status_id=todo.id,
        task_userid_open=admin_id,
    )
    path = DataStorePath(
        path_name=PREFIX, path_parent_id=0, path_is_root=True, path_case_id=case_id
    )
    db.session.add_all([asset, ioc, performed, planned, path])
    db.session.flush()
    file = DataStoreFile(
        file_original_name=PREFIX + ".txt",
        file_local_name="/tmp/" + PREFIX + "-never-created",
        file_parent_id=path.path_id,
        file_case_id=case_id,
        added_by_user_id=admin_id,
        file_sha256="b" * 64,
        file_size=0,
    )
    db.session.add(file)
    db.session.commit()
    source_ids = dict(
        alert_id=alert.alert_id,
        affected_asset_ids=[asset.asset_id],
        source_asset_id=asset.asset_id,
        target_asset_id=asset.asset_id,
        ioc_ids=[ioc.ioc_id],
        file_ids=[file.file_id],
        performed_task_ids=[performed.id],
        planned_task_ids=[planned.id],
    )
    card = data("PUT", endpoint, admin_token, put_body(card, selections=source_ids))
    expect(
        card["fields"]["detection_source"]["value"] == "acceptance-source",
        "Selected alert projection missing",
    )
    expect(
        "192.0.2.17" in card["fields"]["affected_assets"]["value"],
        "Selected asset projection missing",
    )
    expect(
        card["fields"]["hashes"]["value"] == "a" * 64,
        "Hash-only IOC source projection wrong",
    )
    expect(
        PREFIX + ".txt" in card["fields"]["files"]["value"],
        "Selected file projection missing",
    )
    expect(
        "Completed action" in card["fields"]["performed_actions"]["value"],
        "Done task projection missing",
    )
    checked("explicit alert/asset/hash/file/task source projections")
    card = data(
        "PUT",
        endpoint,
        admin_token,
        put_body(card, {"title": {"value": "Manual title", "mode": "manual"}}),
    )
    case = Cases.query.filter_by(case_id=case_id).first()
    case.name = PREFIX + "-edited"
    alert.alert_source = "source-live-edited"
    asset.asset_name = PREFIX + "-asset-live-edited"
    db.session.commit()
    card = data("GET", endpoint, admin_token)
    expect(
        card["fields"]["title"]["value"] == "Manual title", "Manual title overwritten"
    )
    expect(
        card["fields"]["detection_source"]["value"] == "source-live-edited",
        "Auto source not refreshed live",
    )
    card = data(
        "PUT",
        endpoint,
        admin_token,
        put_body(card, {"title": {"value": "forged fallback", "mode": "auto"}}),
    )
    expect(
        card["fields"]["title"]["value"] == PREFIX + "-edited",
        "Auto reset did not use live case",
    )
    checked("manual preservation, auto reset and live refresh")
    foreign = Alert.query.filter_by(alert_id=1).first()
    if foreign:
        expect(
            api(
                "PUT", endpoint, admin_token, put_body(card, selections={"alert_id": 1})
            )[0]
            == 400,
            "Foreign alert must reject",
        )
    foreign_asset = CaseAssets.query.filter(CaseAssets.case_id.in_([1, 2])).first()
    if foreign_asset:
        expect(
            api(
                "PUT",
                endpoint,
                admin_token,
                put_body(
                    card, selections={"affected_asset_ids": [foreign_asset.asset_id]}
                ),
            )[0]
            == 400,
            "Foreign asset must reject",
        )
    bad_task = deepcopy(source_ids)
    bad_task["planned_task_ids"] = [performed.id]
    expect(
        api("PUT", endpoint, admin_token, put_body(card, selections=bad_task))[0]
        == 400,
        "Task role inconsistent status must reject",
    )
    checked("foreign scopes and task status rejection")
    for method, suffix, body in [
        ("GET", "", None),
        ("PUT", "", put_body(card)),
        ("GET", "/export", None),
    ]:
        expect(
            api(method, endpoint + suffix, None, body)[0] in [401, 403],
            "Anonymous access must reject",
        )
    checked("anonymous read/save/export denied")
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
    card = data(
        "PUT",
        endpoint,
        admin_token,
        put_body(
            card,
            {
                "categories": {"value": [8], "mode": "manual"},
                "category8_importance": {"value": None, "mode": "manual"},
                "category8_reason": {"value": None, "mode": "manual"},
            },
        ),
    )
    expect(
        card["derived"]["importance"] is None and card["warnings"],
        "Category8 draft must save with warnings",
    )
    checked("incomplete category8 draft")
    exported = data("GET", endpoint + "/export?timezone=UTC", admin_token)
    expect(exported["revision"] == card["revision"], "Export revision mismatch")
    expect(
        "<script>alert(1)</script>" not in exported["html"],
        "HTML export executed unsanitized content",
    )
    raw = base64.b64decode(exported["docx_base64"])
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        expect(
            "word/document.xml" in archive.namelist(), "DOCX archive missing document"
        )
        xml = archive.read("word/document.xml").decode()
        expect("00:00" in xml, "UTC export missing expected time")
    expect(
        api("GET", endpoint + "/export?timezone=invalid/not-a-zone", admin_token)[0]
        == 400,
        "Invalid timezone must reject",
    )
    checked("DOCX/HTML escaped export and timezone validation")
    # Export the live resolved snapshot before deleting its source alert.
    case_payload, entities, collector = read_case_bundle(case_id)
    expect(
        entities["incident_card"][0]["fields"]["affected_assets"]["value"].find(
            "asset-live-edited"
        )
        >= 0,
        "Transfer captured stale persisted auto source",
    )
    ref_map = {
        "user:" + str(identifier): identifier for identifier in collector.principal_ids
    }
    for key, identifiers in collector.lookup_ids.items():
        ref_map.update(
            {key + ":" + str(identifier): identifier for identifier in identifiers}
        )
    for card_payload in entities.get("incident_card", []):
        for key in ("created_at", "updated_at"):
            if isinstance(card_payload.get(key), datetime):
                card_payload[key] = card_payload[key].isoformat()
    case_payload["name"] = PREFIX + "-clone"
    clone = create_case_row(case_payload, ref_map, admin_id, uuid.uuid4())
    OWNED_CASES.append(clone.case_id)
    write_case_bundle(clone.case_id, entities, ref_map)
    db.session.commit()
    clone_card = get_incident_card(clone.case_id)
    expect(
        clone_card["selections"]["affected_asset_ids"]
        and clone_card["selections"]["affected_asset_ids"][0] != asset.asset_id,
        "Transfer did not remap asset ID",
    )
    expect(
        clone_card["selections"]["ioc_ids"][0] != ioc.ioc_id,
        "Transfer did not remap IOC ID",
    )
    expect(
        clone_card["selections"]["file_ids"][0] != file.file_id,
        "Transfer did not remap file ID",
    )
    expect(
        clone_card["selections"]["performed_task_ids"][0] != performed.id,
        "Transfer did not remap task ID",
    )
    expect(
        clone_card["selections"]["alert_id"] is None
        and clone_card["fields"]["detection_source"]["value"] == "source-live-edited"
        and clone_card["fields"]["detection_source"]["status"] == "missing",
        "Transfer lost missing alert snapshot",
    )
    expect(
        any("alert_id" in warning for warning in clone_card["warnings"]),
        "Transferred alert warning missing",
    )
    expect(
        "asset-live-edited" in clone_card["fields"]["affected_assets"]["value"],
        "Transferred live asset snapshot wrong",
    )
    checked(
        "real transfer remaps assets/IOCs/files/tasks and retains missing alert snapshot"
    )
    db.session.add(
        UserCaseEffectiveAccess(
            user_id=admin_id,
            case_id=clone.case_id,
            access_level=CaseAccessLevel.full_access.value,
        )
    )
    db.session.commit()
    clone_endpoint = "/api/v2/cases/" + str(clone.case_id) + "/incident-card"
    clone_card = data(
        "PUT",
        clone_endpoint,
        admin_token,
        put_body(
            clone_card,
            {"reporter_name": {"value": "Unrelated manual edit", "mode": "manual"}},
        ),
    )
    expect(
        any("alert_id" in warning for warning in clone_card["warnings"])
        and clone_card["fields"]["detection_source"]["value"] == "source-live-edited",
        "Echoed full selections erased imported missing-source warning/snapshot",
    )
    checked("echoed full selections preserve imported missing source on manual edit")
    alert_value = card["fields"]["detection_source"]["value"]
    alert_provenance = card["fields"]["detection_source"]["source"]
    AlertCaseAssociation.query.filter_by(
        case_id=case_id, alert_id=alert.alert_id
    ).delete()
    db.session.delete(alert)
    db.session.commit()
    card = data(
        "PUT",
        endpoint,
        admin_token,
        put_body(
            card,
            {"detection_source": {"value": "forged missing source", "mode": "auto"}},
        ),
    )
    expect(
        card["fields"]["detection_source"]["value"] == alert_value
        and card["fields"]["detection_source"]["source"] == alert_provenance
        and card["fields"]["detection_source"]["status"] == "missing",
        "Missing source save lost snapshot/provenance",
    )
    checked(
        "deleted source preserves snapshot/provenance and rejects forged auto fallback"
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
