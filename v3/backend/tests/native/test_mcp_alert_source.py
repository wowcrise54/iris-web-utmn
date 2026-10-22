"""Raw alert pagination through the real MCP dispatcher, with inert ACL/DB doubles."""
import ast
import hashlib
import json
import logging
from pathlib import Path
import runpy
from types import SimpleNamespace
from unittest.mock import Mock

import pytest


SOURCE = Path(__file__).resolve().parents[2] / 'source/app'
MCP = SOURCE / 'blueprints/rest/v2/mcp'
TOOL = 'iris_alerts_source_get'
BUDGET = runpy.run_path(str(MCP / 'result_budget.py'))
CLASSIFICATION = runpy.run_path(str(MCP / 'classification.py'))


def extract(path, names, scope):
    nodes = [node for node in ast.parse(path.read_text(encoding='utf-8')).body
             if getattr(node, 'name', None) in names]
    assert len(nodes) == len(names), f'Missing implementation: {names}'
    future = ast.ImportFrom(module='__future__', names=[ast.alias(name='annotations')], level=0)
    tree = ast.fix_missing_locations(ast.Module(body=[future, *nodes], type_ignores=[]))
    exec(compile(tree, str(path), 'exec'), scope)


@pytest.fixture
def runtime():
    registry = {}

    def register(**kwargs):
        def decorate(handler):
            registry[kwargs['name']] = SimpleNamespace(
                handler=handler, admin_only=False, case_scoped=False, war_room_scoped=False, **kwargs)
            return handler
        return decorate

    permission = SimpleNamespace(name='alerts_read')
    scope = dict(json=json, hashlib=hashlib, mcp_tool=register,
                 Permissions=SimpleNamespace(alerts_read=permission),
                 protocol=SimpleNamespace(INVALID_PARAMS=-32602, INTERNAL_ERROR=-32603,
                                          METHOD_NOT_FOUND=-32601, IRIS_ACCESS_DENIED=-32001),
                 MAX_RESULT_BYTES=BUDGET['MAX_RESULT_BYTES'],
                 iris_current_user=SimpleNamespace(id=7, mcp_allowed=True),
                 ac_current_user_permissions_mask=Mock(return_value=1),
                 ac_current_user_has_customer_access=Mock(),
                 alerts_get=Mock(return_value=SimpleNamespace(alert_source_content=None, alert_context={})),
                 ObjectNotFoundError=LookupError, TOOL_REGISTRY=registry,
                 get_srv_settings=lambda: SimpleNamespace(mcp_tool_allowlist='', mcp_tool_denylist=''),
                 active_tool_names=lambda *_: set(registry),
                 _user_has_at_least_a_required_permission=Mock(return_value=True),
                 apply_result_budget=BUDGET['apply_result_budget'],
                 mutates=CLASSIFICATION['mutates'], track_activity=Mock(),
                 log=logging.getLogger(__name__), _JSON_TYPE_MAP={
                     'string': str, 'integer': int, 'object': dict})
    extract(MCP / 'dispatch.py', ['MCPError', '_validate_args', '_augmented_input_schema',
                                  'dispatch_tool_call'], scope)
    extract(MCP / 'tools/alerts.py', ['_get_alert', TOOL], scope)
    return SimpleNamespace(scope=scope, spec=registry[TOOL],
                           call=lambda args: scope['dispatch_tool_call'](TOOL, args),
                           error=scope['MCPError'])


@pytest.mark.parametrize('value', [
    {'events': [{'host': 'srv-306', 'cmdline': f'process-{i}', 'detail': 'x' * 200}
                for i in range(1700)]},
    'Событие шифрования 🐧 "\\\n\t' * 18000,
], ids=['structured-events', 'unicode-and-escapes'])
def test_large_payload_survives_dispatch_and_reassembles_exactly(runtime, value):
    alert = runtime.scope['alerts_get'].return_value
    alert.alert_source_content = value
    expected = value if isinstance(value, str) else json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    assert len(expected.encode('utf-8')) > 361_000
    args = {'alert_identifier': 306}
    parts = []
    while True:
        page = runtime.call(args)
        assert '_truncated' not in page
        assert len(json.dumps(page).encode('utf-8')) <= BUDGET['MAX_RESULT_BYTES']
        assert len(json.dumps(page, ensure_ascii=False).encode('utf-8')) <= BUDGET['MAX_RESULT_BYTES']
        assert page['offset'] == sum(map(len, parts))
        assert page['total_chars'] == len(expected)
        assert page['source_sha256'] == hashlib.sha256(expected.encode('utf-8')).hexdigest()
        assert page['untrusted_data'] is True
        parts.append(page['text'])
        if page['next_offset'] is None:
            break
        assert page['next_offset'] > page['offset']
        args.update(offset=page['next_offset'], expected_sha256=page['source_sha256'])
    assert len(parts) > 1
    assert ''.join(parts) == expected
    assert runtime.scope['alerts_get'].call_count == len(parts)
    _, kwargs = runtime.scope['alerts_get'].call_args
    assert kwargs['fallback_customer_access'] is runtime.scope['ac_current_user_has_customer_access']


@pytest.mark.parametrize('value,expected', [(None, 'null'), ({}, '{}'), ([], '[]'), ('', '')])
def test_empty_payload_and_exact_end_offset(runtime, value, expected):
    runtime.scope['alerts_get'].return_value.alert_source_content = value
    page = runtime.call({'alert_identifier': 306})
    assert page['text'] == expected and page['next_offset'] is None
    end = runtime.call({'alert_identifier': 306, 'offset': len(expected)})
    assert end['text'] == '' and end['next_offset'] is None


def test_context_field_and_requested_page_length(runtime):
    runtime.scope['alerts_get'].return_value.alert_context = {'rule': 'ransom'}
    page = runtime.call({'alert_identifier': 306, 'field': 'alert_context', 'limit': 5})
    assert page['text'] == '{"rul' and page['next_offset'] == 5


@pytest.mark.parametrize('args', [
    {'offset': -1}, {'offset': True}, {'offset': 1.5}, {'offset': '0'},
    {'offset': None}, {'offset': 1_000_000}, {'limit': 0}, {'limit': -1},
    {'limit': True}, {'limit': 30_001}, {'field': 'alert_customer_id'},
    {'field': '__dict__'}, {'field': None},
])
def test_invalid_ranges_and_fields_are_rejected(runtime, args):
    with pytest.raises(runtime.error) as caught:
        runtime.call({'alert_identifier': 306, **args})
    assert caught.value.code == -32602


def test_changed_payload_cannot_be_mixed_with_an_earlier_page(runtime):
    runtime.scope['alerts_get'].return_value.alert_source_content = 'abcdef'
    first = runtime.call({'alert_identifier': 306, 'limit': 3})
    runtime.scope['alerts_get'].return_value.alert_source_content = 'abcXYZ'
    with pytest.raises(runtime.error, match='changed'):
        runtime.call({'alert_identifier': 306, 'offset': first['next_offset'],
                      'expected_sha256': first['source_sha256']})


def test_permissions_and_customer_acl_are_enforced(runtime):
    runtime.scope['_user_has_at_least_a_required_permission'].return_value = False
    with pytest.raises(runtime.error) as caught:
        runtime.call({'alert_identifier': 306})
    assert caught.value.code == -32001
    runtime.scope['alerts_get'].assert_not_called()
    runtime.scope['_user_has_at_least_a_required_permission'].return_value = True
    runtime.scope['alerts_get'].side_effect = LookupError('denied')
    with pytest.raises(runtime.error, match='not found or access denied'):
        runtime.call({'alert_identifier': 306})


def test_tool_is_available_to_yuki_as_a_default_read(runtime):
    assert runtime.spec.mvp is True
    assert runtime.spec.permissions == (runtime.scope['Permissions'].alerts_read,)
    assert CLASSIFICATION['is_read_only'](TOOL)
    assert not CLASSIFICATION['mutates'](TOOL)


def test_prompt_and_truncation_hint_point_to_recoverable_reads():
    prompt = runpy.run_path(str(SOURCE / 'iris_engine/llm/system_prompt.py'))['system_prompt'](case_id=None)
    assert TOOL in prompt and 'next_offset' in prompt
    _, report = BUDGET['apply_result_budget']({'alert_source_content': {'x': 'x' * 100_000}})
    assert TOOL in report['hint']
