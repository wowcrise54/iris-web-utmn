"""Context and alert ACL gates without booting the application or database."""
import ast
import importlib.util
import itertools
import json
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

SOURCE = Path(__file__).parents[2] / 'source'

# Reuse the isolated existing loop harness without importing unrelated schema
# tests (which require the complete backend marshmallow installation).
_harness_path = Path(__file__).with_name('test_yuki_limits.py')
_harness = ast.parse(_harness_path.read_text(encoding='utf-8'))
_helpers = [node for node in _harness.body if isinstance(node, ast.FunctionDef)
            and node.name in ('load', 'extract', 'loop_scope')]
exec(compile(ast.fix_missing_locations(ast.Module(body=_helpers, type_ignores=[])),
             str(_harness_path), 'exec'), globals())

def test_request_budget_refusal_preserves_history_and_prevents_egress_and_provider():
    fn, scope, conv, cfg, consume, biz = loop_scope()
    history = [SimpleNamespace(role='user',content=[{'type':'text','text':'evidence'}])]
    scope['_load_history'] = lambda *args: history
    scope['check_chat_request_budget'].return_value = SimpleNamespace(
        fits=False,input_tokens=None,method='utf8_bytes_fallback',request_bytes=99999,limit=16384)
    emitted=[]; fn(conversation=conv,emit=emitted.append)
    assert emitted[-1].payload['code'] == 'context_budget_exceeded'
    assert 'background analysis' in emitted[-1].payload['message']
    assert history[0].content == [{'type':'text','text':'evidence'}]
    consume.assert_not_called()
    biz.record_egress.assert_not_called()


@pytest.mark.parametrize('physical,working', [(0,32768),(64000,64000)])
def test_request_budget_receives_full_input_and_physical_context(physical,working):
    fn, scope, conv, cfg, consume, biz = loop_scope(limit=1)
    cfg.context_window_tokens=physical
    history=[SimpleNamespace(role='user',content=[{'type':'text','text':'evidence'}])]
    tools=[SimpleNamespace(name='inspect',input_schema={'type':'object'})]
    scope['_load_history']=lambda *args:history
    scope['_prepare_tools']=lambda *args,**kwargs:tools
    fn(conversation=conv,emit=lambda _:None)
    args=scope['check_chat_request_budget'].call_args.kwargs
    assert args['messages'] is history and args['tools'] is tools
    assert args['system']=='system' and args['max_output_tokens']==0
    assert args['working_input_tokens']==working and args['context_window_tokens']==physical


def test_alert_acl_refusal_precedes_context_check_egress_and_llm():
    fn, scope, conv, cfg, consume, biz = loop_scope()
    conv.case_id,conv.alert_id=None,23
    scope['_authorize_alert_scope'].side_effect=LookupError()
    emitted=[];fn(conversation=conv,emit=emitted.append)
    assert emitted[-1].payload['message']=='Alert access is no longer available.'
    scope['check_chat_request_budget'].assert_not_called()
    consume.assert_not_called()
    biz.record_egress.assert_not_called()


def test_alert_scope_is_read_only_and_prompt_prefers_bounded_background_analysis():
    path=SOURCE/'app/blueprints/rest/v2/case_chat/loop.py'
    readonly=extract(path,'_scope_is_read_only',{})
    assert readonly(SimpleNamespace(alert_id=17,case_id=None,war_room_id=None)) is True
    prompt=load(SOURCE/'app/iris_engine/llm/system_prompt.py','bounded_alert_prompt').system_prompt(case_id=None,alert_id=17)
    assert 'iris_alerts_analyze_start' in prompt
    assert 'metadata' in prompt and 'next_offset' in prompt
    assert 'alert #17' in prompt


def test_invented_alert_mutation_never_creates_an_approval_or_dispatch(monkeypatch):
    client=SimpleNamespace(load_config=lambda **kw:SimpleNamespace(auto_execute_read_tools=True,auto_approve_write_tools=False))
    monkeypatch.setitem(sys.modules,'app.iris_engine.llm.client',client)
    biz=SimpleNamespace(append_message=Mock(return_value=SimpleNamespace(id=1)),create_pending_tool_call=Mock())
    scope=dict(case_chat_biz=biz, ROLE_ASSISTANT='assistant',ROLE_TOOL='tool',
               tool_classification=SimpleNamespace(mutates=lambda _:True,is_read_only=lambda _:False,is_write=lambda _:True),
               ChatEvent=lambda name,payload:SimpleNamespace(name=name,payload=payload),
               _TurnResult=lambda **kwargs:SimpleNamespace(**kwargs),_tool_result_content=json.dumps)
    finalise=extract(SOURCE/'app/blueprints/rest/v2/case_chat/loop.py','_finalise_turn',scope)
    conv=SimpleNamespace(id=1,user_id=7,alert_id=17,case_id=None,war_room_id=None,resolved_policy_id=None)
    emitted=[]
    finalise(text='',tool_uses=[{'id':'call1','name':'iris_alerts_update','input':{}}],
             stop_reason='tool_use',conversation=conv,emit=emitted.append)
    biz.create_pending_tool_call.assert_not_called()
    assert biz.append_message.call_args_list[-1].kwargs['content'][0]['is_error'] is True
    assert emitted[-1].name=='error'


def test_dispatch_rechecks_alert_access_after_provider_stream_before_tool():
    dispatch=Mock()
    scope=dict(_authorize_alert_scope=Mock(side_effect=LookupError()), ObjectNotFoundError=LookupError,
               BusinessProcessingError=ValueError,dispatch_tool_call=dispatch)
    fn=extract(SOURCE/'app/blueprints/rest/v2/case_chat/loop.py','_dispatch_and_track',scope)
    result=fn(conversation=SimpleNamespace(alert_id=17),tool_use={'name':'read','id':'1','input':{}},emit=Mock())
    assert result=={'error':'Alert access is no longer available.'}
    dispatch.assert_not_called()


def test_alert_conversation_cannot_redirect_read_to_a_different_customer_alert():
    dispatch = Mock(return_value={'ok': True})
    scope = dict(_authorize_alert_scope=Mock(), ObjectNotFoundError=LookupError,
        BusinessProcessingError=ValueError, dispatch_tool_call=dispatch,
        tool_classification=SimpleNamespace(mutates=lambda _:False, is_write=lambda _:False),
        ALERT_READ_TOOLS=frozenset(('iris_alerts_get', 'iris_alerts_source_get', 'iris_alerts_analyze_start', 'iris_alerts_analysis_get')),
        ChatEvent=lambda name,payload:SimpleNamespace(name=name,payload=payload), track_activity=Mock(), logger=Mock(), MCPError=RuntimeError)
    fn=extract(SOURCE/'app/blueprints/rest/v2/case_chat/loop.py','_dispatch_and_track',scope)
    conv=SimpleNamespace(id=1,alert_id=17,case_id=None,war_room_id=None)
    assert fn(conversation=conv,tool_use={'name':'iris_alerts_get','id':'1','input':{'alert_identifier':99}},emit=Mock())=={'ok':True}
    assert dispatch.call_args.args[1]['alert_identifier']==17
    dispatch.reset_mock()
    result=fn(conversation=conv,tool_use={'name':'iris_cases_get','id':'2','input':{}},emit=Mock())
    assert 'error' in result
    dispatch.assert_not_called()


def test_alert_tool_catalog_is_bound_to_its_own_alert():
    raw=[{'name':name,'inputSchema':{'properties':{'alert_identifier':{'type':'integer'}},'required':['alert_identifier']}}
         for name in ('iris_alerts_get','iris_cases_get')]
    scope=dict(build_tools_list=lambda:raw, tool_classification=SimpleNamespace(mutates=lambda _:False),
        ALERT_READ_TOOLS=frozenset(('iris_alerts_get',)),_mutates_the_scope=lambda *a:False, ToolSpec=lambda **kw:SimpleNamespace(**kw))
    fn=extract(SOURCE/'app/blueprints/rest/v2/case_chat/loop.py','_prepare_tools',scope)
    tools=fn(SimpleNamespace(alert_id=17,case_id=None,war_room_id=None), read_only_scope=True)
    assert [tool.name for tool in tools]==['iris_alerts_get']
    assert 'alert_identifier' not in tools[0].input_schema['properties']


def test_manual_read_approval_retains_the_bound_alert(monkeypatch):
    from types import ModuleType
    module=ModuleType('app.blueprints.rest.v2.case_chat.loop')
    module._tool_result_content=json.dumps
    monkeypatch.setitem(sys.modules,module.__name__,module)
    conv=SimpleNamespace(id=1,user_id=7,alert_id=17,case_id=None,war_room_id=None)
    row=SimpleNamespace(conversation_id=1,arguments={'alert_identifier':99},tool_name='iris_alerts_get',
                        tool_use_id='call1',assistant_message_id=2)
    biz=SimpleNamespace(resolve_pending_tool_call=Mock(return_value=(row,True)),get_conversation=lambda _:conv,
                        append_message=Mock(),count_pending_tool_calls=lambda *a:0)
    dispatch=Mock(return_value={'ok':True})
    scope=dict(case_chat_biz=biz,iris_current_user=SimpleNamespace(_get_current_object=lambda:SimpleNamespace(id=7)),
        ObjectNotFoundError=LookupError,BusinessProcessingError=ValueError,MCPError=RuntimeError,
        _authorize_alert_scope=Mock(),ALERT_READ_TOOLS=frozenset(('iris_alerts_get',)),
        ChatEvent=lambda name,payload:SimpleNamespace(name=name,payload=payload),
        dispatch_tool_call=dispatch,tool_classification=SimpleNamespace(is_write=lambda _:False),
        track_activity=Mock(),logger=Mock(),ROLE_TOOL='tool',run_one_iteration=Mock())
    fn=extract(SOURCE/'app/blueprints/rest/v2/case_chat/approve_tool.py','approve_pending_tool_call',scope)
    fn(pending_tool_call_id=2,emit=Mock())
    assert dispatch.call_args.args[1]['alert_identifier']==17
    scope['_authorize_alert_scope'].assert_called_once_with(conv)


def test_confirm_all_policy_stores_scoped_read_arguments(monkeypatch):
    client=SimpleNamespace(load_config=lambda **kw:SimpleNamespace(auto_execute_read_tools=False,auto_approve_write_tools=False))
    monkeypatch.setitem(sys.modules,'app.iris_engine.llm.client',client)
    biz=SimpleNamespace(append_message=Mock(return_value=SimpleNamespace(id=1)),
                        create_pending_tool_call=Mock(return_value=SimpleNamespace(id=2)))
    scope=dict(case_chat_biz=biz,ROLE_ASSISTANT='assistant',ROLE_TOOL='tool',ALERT_READ_TOOLS=frozenset(('iris_alerts_get',)),
        tool_classification=SimpleNamespace(mutates=lambda _:False,is_read_only=lambda _:True,is_write=lambda _:False),
        ChatEvent=lambda name,payload:SimpleNamespace(name=name,payload=payload),_TurnResult=lambda **kw:SimpleNamespace(**kw))
    fn=extract(SOURCE/'app/blueprints/rest/v2/case_chat/loop.py','_finalise_turn',scope)
    conv=SimpleNamespace(id=1,user_id=7,alert_id=17,case_id=None,war_room_id=None,resolved_policy_id=None)
    fn(text='',tool_uses=[{'id':'call1','name':'iris_alerts_get','input':{'alert_identifier':99}}],
       stop_reason='tool_use',conversation=conv,emit=Mock())
    assert biz.create_pending_tool_call.call_args.kwargs['arguments']['alert_identifier']==17


@pytest.mark.parametrize('history_text,allowed', [('hello',True),('raw evidence '*100000,False)],
                         ids=['greeting-large-catalog','oversized-history'])
def test_real_chat_guard_preserves_greeting_with_catalog_and_stops_oversized_history(history_text,allowed):
    fn,scope,conv,cfg,consume,biz=loop_scope(limit=1)
    guard=load(SOURCE/'app/iris_engine/llm/request_budget.py','chat_guard_integration')
    scope['check_chat_request_budget']=guard.check_chat_request_budget
    scope['_prepare_tools']=lambda *a,**kw:[{'description':'schema documentation '*12000}]
    scope['_load_history']=lambda *a:[{'role':'user','content':history_text}]
    scope['get_llm_provider']=lambda cfg:SimpleNamespace(name='test',_build_body=lambda model,system,messages,tools,max_tokens:{
        'model':model,'system':system,'messages':messages,'tools':tools,'max_tokens':max_tokens})
    consume.side_effect=[SimpleNamespace(terminated=True,paused_on_write=False)]
    emitted=[];fn(conversation=conv,emit=emitted.append)
    assert consume.call_count==int(allowed)
    assert biz.record_egress.call_count==int(allowed)
    if not allowed:
        assert emitted[-1].payload['code']=='context_budget_exceeded'


