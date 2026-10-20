"""Boundary tests with persistence/query seams replaced, not application boot."""

import importlib.util
import sys
import types
import unittest
from unittest.mock import Mock, patch
import test_incident_cards_unit as pure

ROOT = pure.ROOT.parent


def module(name, **attrs):
    result = types.ModuleType(name)
    result.__dict__.update(attrs)
    return result


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    sys.modules[name] = result
    spec.loader.exec_module(result)
    return result


logic = load("app.business.incident_cards", ROOT / "business/incident_cards.py")


class Boundaries(unittest.TestCase):
    def persistence(self):
        models = {
            name: type(name, (), {})
            for name in [
                "Cases",
                "IncidentCard",
                "CaseAssets",
                "Alert",
                "AlertCaseAssociation",
                "Ioc",
                "CaseTasks",
                "DataStoreFile",
                "User",
            ]
        }
        models["IncidentCard"].__init__ = lambda obj, **kw: obj.__dict__.update(kw)
        modules = {
            "app.db": module("app.db", db=types.SimpleNamespace(session=Mock())),
            "app.models.cases": module("cases", Cases=models["Cases"]),
            "app.models.incident_cards": module(
                "card", IncidentCard=models["IncidentCard"]
            ),
            "app.models.assets": module("assets", CaseAssets=models["CaseAssets"]),
            "app.models.alerts": module(
                "alerts",
                Alert=models["Alert"],
                AlertCaseAssociation=models["AlertCaseAssociation"],
            ),
            "app.models.iocs": module("iocs", Ioc=models["Ioc"]),
            "app.models.models": module(
                "models",
                CaseTasks=models["CaseTasks"],
                DataStoreFile=models["DataStoreFile"],
            ),
            "app.models.authorization": module("auth", User=models["User"]),
        }
        with patch.dict(sys.modules, modules):
            result = load(
                "incident_card_db_test", ROOT / "datamgmt/case/incident_card_db.py"
            )
        return result

    def test_serialization_filters_obsolete_fields_and_links(self):
        mod = self.persistence()
        row = types.SimpleNamespace(
            schema_version=1,
            revision=2,
            fields={
                "description": {"value": "kept", "mode": "manual"},
                "files": {"value": "secret", "mode": "manual"},
            },
            selections={"file_ids": [1]},
            author_id=1,
            author_name="actor",
            created_at=None,
            updated_at=None,
            missing_sources=["file_ids"],
        )
        actual = mod.serialize_card(row)
        self.assertEqual(set(actual["fields"]), {"description"})
        self.assertEqual(actual["selections"], {})
        self.assertEqual(actual["missing_sources"], [])

    def test_db_read_preserves_legacy_author_position_before_filtering(self):
        mod = self.persistence()
        row = types.SimpleNamespace(
            schema_version=1,
            revision=2,
            fields={
                "prepared_by": {"value": "Иванов", "mode": "manual"},
                "prepared_position": {"value": "Аналитик", "mode": "manual"},
            },
            selections={},
            author_id=1,
            author_name="actor",
            created_at=None,
            updated_at=None,
            missing_sources=[],
        )
        result = mod.serialize_card(row)
        self.assertEqual(
            result["fields"]["prepared_by"]["value"],
            [{"name": "Иванов", "position": "Аналитик"}],
        )
        self.assertNotIn("prepared_position", result["fields"])
        self.assertEqual(row.fields["prepared_position"]["value"], "Аналитик")

    def test_source_context_reads_only_regulation_case_values(self):
        mod = self.persistence()
        case = types.SimpleNamespace(case_id=1, description="kept", severity=None)
        context = mod.source_context(case, None)
        self.assertEqual(context["meta"], {"case_id": 1})
        self.assertEqual(set(context["automatic"]), {"id", "description"})
        self.assertNotIn("sources", context)

    def test_rejected_links_do_not_access_or_mutate_the_database(self):
        mod = self.persistence()
        with self.assertRaises(logic.CardValidationError):
            mod.save_incident_card(
                1,
                dict(
                    schema_version=1,
                    revision=0,
                    fields={},
                    selections={"planned_task_ids": [1]},
                ),
                9,
            )
        mod.db.session.add.assert_not_called()
        mod.db.session.commit.assert_not_called()

    def test_stale_revision_rolls_back_after_parent_lock(self):
        mod = self.persistence()
        calls = []

        class Query:
            def filter_by(self, **kw):
                return self

            def with_for_update(self):
                calls.append("lock")
                return self

            def first(self):
                calls.append("case")
                return types.SimpleNamespace(case_id=1)

        mod.Cases.query = Query()
        mod.IncidentCard.query = Mock()
        mod.serialize_card = Mock(return_value={"revision": 2})
        with self.assertRaises(logic.CardConflictError):
            mod.save_incident_card(
                1, dict(schema_version=1, revision=1, fields={}, selections={}), 9
            )
        self.assertEqual(calls, ["lock", "case"])
        mod.db.session.rollback.assert_called_once()
        mod.db.session.commit.assert_not_called()

    def test_first_save_locks_parent_and_attributes_server_actor(self):
        mod = self.persistence()
        calls = []
        case = types.SimpleNamespace(case_id=1)

        class Query:
            def filter_by(self, **kw):
                return self

            def with_for_update(self):
                calls.append("lock")
                return self

            def first(self):
                return case

        mod.Cases.query = Query()
        mod.IncidentCard.query = Mock()
        mod.IncidentCard.query.filter_by.return_value.first.return_value = None
        mod.User.query = Mock()
        mod.User.query.filter_by.return_value.first.return_value = (
            types.SimpleNamespace(name="Actor", user="actor")
        )
        mod.source_context = Mock(
            return_value={
                "meta": {},
                "sources": {},
                "automatic": {},
                "collections": {
                    key: {} for key in ["alerts", "assets", "iocs", "files", "tasks"]
                },
            }
        )
        mod.get_incident_card = Mock(return_value={"revision": 1})
        result = mod.save_incident_card(
            1,
            dict(
                schema_version=1,
                revision=0,
                fields={"categories": {"value": [8], "mode": "manual"}},
                selections={},
            ),
            9,
        )
        self.assertEqual(calls, ["lock"])
        self.assertEqual(result["revision"], 1)
        row = mod.db.session.add.call_args.args[0]
        self.assertEqual(row.author_id, 9)
        self.assertEqual(row.author_name, "Actor")
        self.assertEqual(row.revision, 1)
        self.assertIsNotNone(row.created_at.tzinfo)
        mod.db.session.commit.assert_called_once()

    def test_audit_failure_rolls_back_without_committing_card(self):
        mod = self.persistence()
        mod.Cases.query = Mock()
        mod.Cases.query.filter_by.return_value.with_for_update.return_value.first.return_value = types.SimpleNamespace(
            case_id=1
        )
        mod.IncidentCard.query = Mock()
        mod.IncidentCard.query.filter_by.return_value.first.return_value = None
        mod.User.query = Mock()
        mod.User.query.filter_by.return_value.first.return_value = (
            types.SimpleNamespace(name="Actor", user="actor")
        )
        mod.source_context = Mock(
            return_value={
                "meta": {},
                "sources": {},
                "automatic": {},
                "collections": {
                    key: {} for key in ["alerts", "assets", "iocs", "files", "tasks"]
                },
            }
        )

        def fail_audit(_case_id, _revision):
            raise RuntimeError("audit unavailable")

        with self.assertRaises(RuntimeError):
            mod.save_incident_card(
                1,
                dict(schema_version=1, revision=0, fields={}, selections={}),
                9,
                audit=fail_audit,
            )
        mod.db.session.commit.assert_not_called()
        mod.db.session.rollback.assert_called_once()

    def test_business_audit_callback_attributes_actor_and_case(self):
        tracker = Mock()

        def persistence(case_id, payload, actor_id, audit):
            self.assertEqual((case_id, actor_id), (7, 9))
            audit(case_id, 3)
            return {"revision": 3}

        with patch.dict(
            sys.modules,
            {
                "app.datamgmt.case.incident_card_db": module(
                    "persistence", save_incident_card=persistence
                ),
                "app.iris_engine.utils.tracker": module(
                    "tracker", track_activity=tracker
                ),
            },
        ):
            self.assertEqual(logic.save_incident_card(7, {}, 9), {"revision": 3})
        tracker.assert_called_once_with(
            "updated incident card revision 3", caseid=7, user_id_override=9
        )

    def routes(self):
        class Blueprint:
            def __init__(self, *a, **kw):
                pass

            def get(self, *a):
                return lambda fn: fn

            def put(self, *a):
                return lambda fn: fn

        auth = types.SimpleNamespace(read_only="read", full_access="write")
        modules = {
            "app.web": module(
                "web",
                Blueprint=Blueprint,
                request=types.SimpleNamespace(content_length=0, get_json=lambda: {}),
            ),
            "app.blueprints.access_controls": module(
                "access",
                ac_api_requires=lambda: lambda fn: fn,
                ac_fast_check_current_user_has_case_access=Mock(return_value=False),
                ac_api_return_access_denied=lambda **kw: ("denied", kw),
            ),
            "app.blueprints.iris_user": module(
                "user", iris_current_user=types.SimpleNamespace(id=9)
            ),
            "app.models.authorization": module("auth", CaseAccessLevel=auth),
            "app.blueprints.rest.endpoints": module(
                "endpoints",
                response_api_success=lambda data: ("ok", data),
                response_api_error=lambda _message, **kw: (
                    "error",
                    kw.get("status", 400),
                ),
                response_api_not_found=lambda: ("missing", 404),
            ),
            "app.business.incident_cards": module(
                "db",
                get_incident_card=Mock(),
                save_incident_card=Mock(),
                CardValidationError=logic.CardValidationError,
                CardConflictError=logic.CardConflictError,
            ),
            "app.iris_engine.utils.tracker": module("tracker", track_activity=Mock()),
        }
        with patch.dict(sys.modules, modules):
            return load(
                "incident_card_routes_test",
                ROOT / "blueprints/rest/v2/case_routes/incident_card.py",
            )

    def test_acl_denies_reads_writes_exports_before_data_access(self):
        mod = self.routes()
        for fn in [
            mod.read_incident_card,
            mod.update_incident_card,
            mod.export_incident_card,
        ]:
            self.assertEqual(fn(7)[0], "denied")
        mod.get_incident_card.assert_not_called()
        mod.save_incident_card.assert_not_called()
        self.assertEqual(
            mod.ac_fast_check_current_user_has_case_access.call_args_list[1].args,
            (7, ["write"]),
        )

    def test_export_rejects_invalid_timezone_before_reading_sources(self):
        mod = self.routes()
        mod.ac_fast_check_current_user_has_case_access.return_value = True
        mod.request.args = {"timezone": "invalid/not-a-zone"}
        with patch.dict(
            sys.modules,
            {
                "app.business.reports.incident_card_report": module(
                    "report", build_export=lambda *_args, **_kw: {}
                )
            },
        ):
            self.assertEqual(mod.export_incident_card(7), ("error", 400))
        mod.get_incident_card.assert_not_called()

    def test_write_conflict_409_and_success_envelope(self):
        mod = self.routes()
        mod.ac_fast_check_current_user_has_case_access.return_value = True
        mod.save_incident_card.side_effect = logic.CardConflictError("stale")
        self.assertEqual(mod.update_incident_card(7), ("error", 409))
        mod.save_incident_card.side_effect = None
        mod.save_incident_card.return_value = {"revision": 3}
        self.assertEqual(mod.update_incident_card(7)[0], "ok")


if __name__ == "__main__":
    unittest.main()
