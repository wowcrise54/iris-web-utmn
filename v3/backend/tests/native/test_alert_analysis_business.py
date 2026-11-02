"""Exercise lifecycle and tenant guards without a database or an app server."""
import ast
import datetime as dt
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace as NS
from types import ModuleType
import sys
from unittest.mock import Mock

import pytest

SOURCE = Path(__file__).parents[2] / 'source/app'


def functions(**values):
    tree = ast.parse((SOURCE / 'business/alert_analysis.py').read_text())
    tree.body = [node for node in tree.body if isinstance(node, ast.FunctionDef)]
    namespace = dict(dt=dt, **values)
    exec(compile(tree, '<alert-analysis-business>', 'exec'), namespace)
    return namespace


def job(**values):
    return NS(id=4, alert_id=7, conversation_id=8, status=values.pop('status', 'running'),
              requested_by=2, progress=2, total=10, error=None, created_at=None, updated_at=None,
              result=values.pop('result', {}), **values)


def test_public_projection_hides_snapshot_paths_and_raw_source():
    api = functions()
    value = job(result={'stage': 'mapping', '_snapshot': {'path': '/private'}, 'raw': 'secret',
                        'sources': [{'id': 's1', 'path': '/private', 'content': 'secret', 'sha256': 'hash'}],
                        'coverage': {'completed': 2}, 'report': 'report'})
    projected = api['alert_projection'](value)
    assert projected['result'] == {'stage': 'mapping', 'sources': [{'id': 's1', 'sha256': 'hash'}],
                                   'coverage': {'completed': 2}, 'report': 'report'}
    metadata = api['alert_metadata'](value)
    assert 'result' not in metadata and 'report' not in metadata
    assert metadata['coverage'] == {'completed': 2}
    assert metadata['source_url'] == '/alerts/7?analysis=4'


def test_mcp_metadata_reports_large_missing_sets_without_replaying_them():
    api = functions()
    value = job(result={'coverage': {'missing_events': [str(i) for i in range(1000)], 'source_complete': False}})
    metadata = api['alert_metadata'](value)
    assert 'missing_events' not in metadata['coverage']
    assert metadata['coverage']['missing_events_count'] == 1000
    assert metadata['coverage']['missing_events_omitted'] == 1000
    assert len(value.result['coverage']['missing_events']) == 1000


@pytest.mark.parametrize('active,mask,allowed', [(False, 4, False), (True, 0, False), (True, 4, True), (True, 2, True)])
def test_alert_acl_rechecks_enabled_user_and_effective_read_permission(active, mask, allowed):
    class Missing(Exception):
        pass
    lookup = Mock(return_value='alert')
    class User(NS):
        pass
    api = functions(User=User, Alert=object, db=NS(session=Mock()), ObjectNotFoundError=Missing, Permissions=NS(alerts_read=NS(value=4), server_administrator=NS(value=2)),
                    ac_get_effective_permissions_of_user=lambda user: mask,
                    ac_flag_match_mask=lambda value, bit: bool(value & bit), alerts_get=lookup)
    user = User(id=2, active=active)
    if allowed:
        assert api['authorize_alert'](7, user) == 'alert'
        lookup.assert_called_once_with(user, mask, 7)
    else:
        with pytest.raises(Missing):
            api['authorize_alert'](7, user)
        lookup.assert_not_called()


def test_token_principal_is_resolved_to_persisted_enabled_user():
    class User(NS):
        pass
    user = User(id=2, active=True)
    db = NS(session=NS(get=Mock(return_value=user), refresh=Mock()))
    lookup = Mock(return_value='alert')
    api = functions(User=User, Alert=object, db=db, ObjectNotFoundError=LookupError,
                    Permissions=NS(alerts_read=NS(value=4), server_administrator=NS(value=2)),
                    ac_get_effective_permissions_of_user=lambda value: 4,
                    ac_flag_match_mask=lambda value, bit: bool(value & bit), alerts_get=lookup)
    assert api['authorize_alert'](7, NS(id=2, is_active=True)) == 'alert'
    db.session.get.assert_any_call(User, 2)
    lookup.assert_called_once_with(user, 4, 7)


@pytest.mark.parametrize('customer,policy,owner,allowed', [(3, 4, 2, True), (6, 4, 2, False),
                                                        (3, 5, 2, False), (3, 4, 8, False)])
def test_saved_snapshot_binding_rejects_customer_policy_or_owner_changes(monkeypatch, customer, policy, owner, allowed):
    module = ModuleType('app.iris_engine.llm.policy')
    module.resolve_for_alert = lambda _: NS(policy=NS(id=policy), restriction_level=0)
    monkeypatch.setitem(sys.modules, 'app.iris_engine.llm.policy', module)
    api = functions(ObjectNotFoundError=LookupError)
    # Even a caller authorized for the NEW customer must not read the OLD snapshot.
    api['authorize_alert'] = lambda identifier, user: NS(alert_id=identifier, alert_customer_id=customer)
    conv = NS(user_id=2, alert_id=7, case_id=None, war_room_id=None,
              alert_customer_id=3, resolved_policy_id=4)
    if allowed:
        assert api['authorize_alert_conversation'](conv, NS(id=owner)).alert_customer_id == 3
    else:
        with pytest.raises(LookupError):
            api['authorize_alert_conversation'](conv, NS(id=owner))


@pytest.mark.parametrize('status,expected', [('queued', 'cancelled'), ('running', 'running'), ('completed', 'completed')])
def test_cancel_is_cooperative_and_preserves_checkpoint(status, expected):
    db = NS(session=Mock())
    api = functions(db=db)
    api['authorize_alert_analysis'] = Mock()
    api['_lock_job'] = lambda value: value
    value = job(status=status, result={'_checkpoint': [1, 2]})
    api['cancel_alert_job'](value)
    assert value.status == expected
    assert value.result['_checkpoint'] == [1, 2]
    assert value.result.get('_cancel_requested', False) == (status != 'completed')
    assert db.session.commit.call_count == (status != 'completed')


def test_retry_keeps_snapshot_and_conversation_and_requeues():
    db = NS(session=Mock())
    api = functions(db=db, User=NS(id=2), BusinessProcessingError=ValueError)
    api['authorize_alert_analysis'] = Mock()
    api['_lock_job'] = lambda value: value
    api['_active'] = lambda *args: None
    api['_quota'] = Mock()
    api['_queue'] = Mock()
    value = job(status='partial', result={'_snapshot': '/private', '_checkpoint': [1], '_cancel_requested': True})
    api['retry_alert_job'](value)
    assert value.status == 'queued' and value.conversation_id == 8
    assert value.result == {'stage': 'queued', '_snapshot': '/private', '_checkpoint': [1]}
    api['_queue'].assert_called_once_with(value)


def test_config_context_override_preserves_zero_and_existing_unlimited_settings():
    tree = ast.parse((SOURCE / 'iris_engine/llm/client.py').read_text())
    tree.body = [node for node in tree.body if isinstance(node, (ast.FunctionDef, ast.ClassDef))
                 and node.name in ('ChatbotConfig', 'load_config')]
    settings = NS(chatbot_enabled=True, chatbot_context_window_tokens=64000,
                  chatbot_max_output_tokens=0, chatbot_max_turns_per_conversation=0,
                  chatbot_daily_token_budget_per_user=0)
    env = {'dataclass': dataclass, 'get_srv_settings': lambda: settings}
    exec(compile(tree, '<config>', 'exec'), env)
    cfg = env['load_config']()
    assert cfg.context_window_tokens == 64000
    assert cfg.max_output_tokens == cfg.max_turns_per_conversation == cfg.daily_token_budget_per_user == 0
    cfg = env['load_config'](NS(api_key='', context_window_tokens=0))
    assert cfg.context_window_tokens == 0
    cfg = env['load_config'](NS(api_key='', context_window_tokens=128000))
    assert cfg.context_window_tokens == 128000


def test_conversation_policy_routes_alert_to_its_customer_resolver():
    tree = ast.parse((SOURCE / 'iris_engine/llm/policy.py').read_text())
    tree.body = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'resolve_for_conversation']
    alert = Mock(return_value='customer-policy')
    case = Mock()
    war_room = Mock()
    env = {'CaseChatConversation': object, 'ResolvedPolicy': object, 'resolve_for_alert': alert,
           'resolve_for_case': case, 'resolve_for_war_room': war_room}
    exec(compile(tree, '<policy>', 'exec'), env)
    assert env['resolve_for_conversation'](NS(alert_id=7, case_id=None, war_room_id=None)) == 'customer-policy'
    alert.assert_called_once_with(7)
    case.assert_not_called()
    war_room.assert_not_called()


def test_migration_extends_unique_head_and_refuses_destructive_downgrade():
    path = SOURCE / 'alembic/versions'
    revisions = {}
    for file in path.glob('*.py'):
        fields = {}
        for node in ast.parse(file.read_text(encoding='utf-8-sig')).body:
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id in ('revision', 'down_revision'):
                        fields[target.id] = ast.literal_eval(node.value)
        if fields.get('revision'):
            revisions[fields['revision']] = fields.get('down_revision')
    parents = {parent for value in revisions.values() for parent in (value if isinstance(value, tuple) else (value,))}
    assert set(revisions) - parents == {'utmn_alert_analysis01'}
    operations = Mock()
    tree = ast.parse((path / 'utmn_alert_analysis01.py').read_text())
    tree.body = [node for node in tree.body if isinstance(node, ast.FunctionDef)]
    env = {'op': operations, 'sa': NS(Column=lambda *a, **kw: a, BigInteger=lambda: 'bigint', Integer=lambda: 'int', text=lambda s: s)}
    exec(compile(tree, '<migration>', 'exec'), env)
    env['upgrade']()
    assert any('(case_id IS NULL) <> (alert_id IS NULL)' in str(call) for call in operations.create_check_constraint.call_args_list)
    assert "status IN ('queued', 'running')" in str(operations.create_index.call_args_list)
    env['downgrade']()
    assert 'RAISE EXCEPTION' in operations.execute.call_args.args[0]
