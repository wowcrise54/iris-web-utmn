"""Revoking alert access blocks historical reports and existing chat actions."""
import ast
from pathlib import Path
from types import SimpleNamespace as NS
from types import ModuleType
import sys
from unittest.mock import Mock

import pytest

ROOT = Path(__file__).parents[2] / 'source/app/blueprints/rest/v2/case_chat'


class Missing(Exception):
    pass


def selected(path, names, env):
    tree = ast.parse((ROOT / path).read_text())
    tree.body = [node for node in tree.body if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.name in names]
    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            node.decorator_list = []
    exec(compile(tree, '<alert-chat-access>', 'exec'), env)
    return env


def principal():
    return NS(_get_current_object=lambda: NS(id=2), id=2)


@pytest.mark.parametrize('operation', ['get_conversation', 'rename_conversation', 'delete_conversation'])
def test_revoked_customer_access_blocks_read_and_metadata_mutations(operation):
    conv = NS(id=8, user_id=2, alert_id=7)
    business = NS(get_conversation=Mock(return_value=conv), list_messages=Mock(),
                  archive_conversation=Mock(), rename_conversation=Mock())
    env = selected('transport.py', {'_require_own_conversation', operation}, {
        'case_chat_biz': business, 'iris_current_user': principal(),
        'ObjectNotFoundError': Missing, 'authorize_alert_conversation': Mock(side_effect=Missing), 'authorize_alert': Mock(side_effect=Missing),
        'ac_api_return_access_denied': lambda: 'denied',
    })
    assert env[operation](8) == 'denied'
    business.list_messages.assert_not_called()
    business.archive_conversation.assert_not_called()
    business.rename_conversation.assert_not_called()


def test_revoked_access_blocks_alert_conversation_listing_before_query():
    query = Mock()
    env = selected('transport.py', {'list_alert_conversations'}, {
        'iris_current_user': principal(), 'ObjectNotFoundError': Missing,
        'authorize_alert_conversation': Mock(side_effect=Missing), 'authorize_alert': Mock(side_effect=Missing),
        'ac_api_return_access_denied': lambda: 'denied', 'CaseChatConversation': NS(query=query),
    })
    assert env['list_alert_conversations'](7) == 'denied'
    query.filter_by.assert_not_called()


@pytest.mark.parametrize('operation,payload', [
    ('on_join_conversation', {'conversation_id': 8}),
    ('on_send', {'conversation_id': 8, 'user_text': 'continue'}),
    ('on_approve_tool', {'pending_tool_call_id': 4, 'conversation_id': 999}),
    ('on_deny_tool', {'pending_tool_call_id': 4, 'conversation_id': 999}),
])
def test_revoked_access_blocks_join_send_approve_and_deny(operation, payload):
    conv = NS(id=8, alert_id=7, user_id=2)
    business = NS(get_conversation=Mock(return_value=conv), append_message=Mock())
    env = selected('namespace.py', {'ChatNamespace', '_int', '_require_alert_conversation_access', '_pending_conversation'}, {
        'Namespace': object, 'Any': object, 'case_chat_biz': business,
        '_install_auth_context': lambda: 2, '_current_user_id': lambda: 2,
        'iris_current_user': principal(), 'ObjectNotFoundError': Missing,
        'authorize_alert_conversation': Mock(side_effect=Missing), 'authorize_alert': Mock(side_effect=Missing), 'emit': Mock(), 'join_room': Mock(),
        'CaseChatPendingToolCall': NS(query=Mock()),
        'approve_pending_tool_call': Mock(), 'deny_pending_tool_call': Mock(),
    })
    env['CaseChatPendingToolCall'].query.filter_by.return_value.first.return_value = NS(conversation_id=8)
    getattr(env['ChatNamespace'](), operation)(payload)
    env['emit'].assert_called_once_with('error', {'message': 'No access to this alert.'})
    env['join_room'].assert_not_called()
    business.append_message.assert_not_called()
    env['approve_pending_tool_call'].assert_not_called()
    env['deny_pending_tool_call'].assert_not_called()


def test_source_route_accepts_manifest_and_hashed_unit_ids():
    # The route converter must retain the colon in u:<sha256>; the worker
    # validates membership in the snapshot manifest, never an OS filename.
    source = (ROOT.parent / 'alerts_routes/analysis.py').read_text()
    tree = ast.parse(source)
    route = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'get_analysis_source')
    decorator = route.decorator_list[0]
    assert decorator.args[0].value.endswith('/sources/<source_id>')


def test_prejoined_socket_emitter_rechecks_acl_without_current_request_user(monkeypatch):
    db_module = ModuleType('app.db')
    owner = NS(id=2, active=True)
    db_module.db = NS(session=NS(get=Mock(return_value=owner)))
    auth_module = ModuleType('app.models.authorization')
    auth_module.User = object
    monkeypatch.setitem(sys.modules, 'app.db', db_module)
    monkeypatch.setitem(sys.modules, 'app.models.authorization', auth_module)
    conv = NS(id=8, user_id=2, alert_id=7)
    authorize = Mock(side_effect=Missing)
    env = selected('namespace.py', {'_emit_for_conv'}, {
        'case_chat_biz': NS(get_conversation=Mock(return_value=conv)),
        'authorize_alert_conversation': authorize, 'ObjectNotFoundError': Missing,
        'ChatEvent': object,
    })
    # No request/iris_current_user is installed: this is also usable for worker
    # emissions. Denial returns before broadcasting private report content.
    env['_emit_for_conv'](8)(NS(name='assistant_delta', payload={'text': 'private report'}))
    authorize.assert_called_once_with(conv, owner)


def test_alert_pending_write_cannot_be_approved_even_with_current_alert_access():
    conv = NS(id=8, alert_id=7, user_id=2)
    pending = NS(conversation_id=8, tool_name='iris_alerts_update')
    query = Mock()
    query.filter_by.return_value.first.return_value = pending
    env = selected('namespace.py', {'_pending_conversation'}, {
        'CaseChatPendingToolCall': NS(query=query),
        'case_chat_biz': NS(get_conversation=Mock(return_value=conv)),
        '_current_user_id': lambda: 2, '_require_alert_conversation_access': lambda conv: True,
        'mutates': lambda name: name == 'iris_alerts_update', 'emit': Mock(),
    })
    assert env['_pending_conversation'](4, approve=True) is None
    env['emit'].assert_called_once_with('error', {'message': 'Alert analysis conversations cannot execute write tools.'})
