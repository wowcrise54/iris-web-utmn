"""Unlimited Yuki settings, provider wire contracts and live loop checks."""
import ast
import importlib.util
import itertools
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from marshmallow import Schema, fields, ValidationError
from marshmallow.validate import Range

SOURCE = Path(__file__).parents[2] / 'source'
LIMITS = ('max_output_tokens', 'max_turns_per_conversation', 'max_tool_calls_per_turn',
          'daily_token_budget_per_user', 'daily_token_budget_org')


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def extract(path, name, scope):
    node = next(n for n in ast.parse(path.read_text()).body if getattr(n, 'name', None) == name)
    if isinstance(node, ast.FunctionDef):
        node.decorator_list = []
    tree = ast.fix_missing_locations(ast.Module(body=[ast.ImportFrom(module='__future__', names=[ast.alias(name='annotations')], level=0), node], type_ignores=[]))
    exec(compile(tree, str(path), 'exec'), scope)
    return scope[name]


@pytest.mark.parametrize('kind,prefix', [('ServerSettingsSchema', 'chatbot_'), ('ChatbotPolicySchema', '')])
def test_actual_limit_fields_accept_zero_and_large_integers_but_reject_overflows(kind, prefix):
    tree = ast.parse((SOURCE/'app/schema/marshables.py').read_text())
    cls = next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name==kind)
    scope = {'fields':fields, 'Range':Range, 'auto_field':lambda name, **kwargs:fields.Integer(**kwargs)}
    definitions = {}
    for field in LIMITS:
        name = prefix+field
        node = next(n for n in cls.body if isinstance(n,ast.AnnAssign) and n.target.id==name)
        value = eval(compile(ast.Expression(node.value), '<actual schema field>', 'eval'), scope)
        definitions[name] = value
    schema = Schema.from_dict(definitions)()
    for field in definitions:
        for value in (0, 201, 100_000_001, 2_147_483_647):
            assert schema.load({field:value})[field] == value
        for value in (-1, 2_147_483_648, 1.5, True, None, float('inf')):
            with pytest.raises(ValidationError): schema.load({field:value})


def test_zero_limits_survive_policy_and_server_config_fallbacks():
    import dataclasses
    scope = {'dataclass':dataclasses.dataclass}
    path = SOURCE/'app/iris_engine/llm/client.py'
    extract(path, 'ChatbotConfig', scope)
    settings = SimpleNamespace(chatbot_enabled=True, chatbot_api_key='', **{'chatbot_'+key:10 for key in LIMITS})
    scope.update(get_srv_settings=lambda:settings, decrypt_secret=lambda value:value, logger=Mock())
    configure = extract(path, 'load_config', scope)
    policy = SimpleNamespace(api_key='', **{key:0 for key in LIMITS})
    assert all(getattr(configure(policy), key)==0 for key in LIMITS)
    for key in LIMITS:setattr(settings,'chatbot_'+key,0)
    assert all(getattr(configure(), key)==0 for key in LIMITS)


def test_zero_history_retains_every_message():
    rows = [SimpleNamespace(role='user',content=[{'type':'text','text':str(i)}]) for i in range(200)]
    scope = dict(case_chat_biz=SimpleNamespace(list_messages=lambda _:rows), ROLE_TOOL='tool',
                 ChatMessage=lambda **kwargs:SimpleNamespace(**kwargs), _stitch_orphan_tool_uses=lambda values:values)
    history = extract(SOURCE/'app/blueprints/rest/v2/case_chat/loop.py', '_load_history', scope)
    assert len(history(SimpleNamespace(id=1), SimpleNamespace(max_turns_per_conversation=0)))==200
    assert len(history(SimpleNamespace(id=1), SimpleNamespace(max_turns_per_conversation=2)))==8


def loop_scope(limit=0, budget=0):
    conv = SimpleNamespace(id=1, user_id=7, archived_at=None, resolved_policy_id=None,
                           resolved_restriction_level=0, case_id=2, war_room_id=None)
    user = SimpleNamespace(id=7,active=True)
    token_type = extract(SOURCE/'app/blueprints/iris_user.py','TokenUser',{})
    token_user = token_type({'user_id':7,'user_login':'test','user_name':'Test','user_email':'test@example.test'})
    cfg = SimpleNamespace(enabled=True, provider='test', model='test', max_tool_calls_per_turn=limit,
        daily_token_budget_per_user=budget, daily_token_budget_org=0, max_output_tokens=0)
    consume = Mock(side_effect=[SimpleNamespace(terminated=False,paused_on_write=False)]*70+
                              [SimpleNamespace(terminated=True,paused_on_write=False)])
    biz = SimpleNamespace(sum_tokens_today=Mock(return_value=0), record_egress=Mock(return_value=SimpleNamespace(id=1)))
    scope = dict(count=itertools.count, db=SimpleNamespace(session=Mock()), logger=Mock(),
        resolve_for_conversation=lambda _:SimpleNamespace(restriction_level=0),
        iris_current_user=SimpleNamespace(_get_current_object=lambda:token_user), User=object(), load_config=Mock(return_value=cfg),
        get_llm_provider=lambda _:SimpleNamespace(name='test'), ChatbotDisabledError=RuntimeError,
        case_chat_biz=biz, ChatEvent=lambda name,payload:SimpleNamespace(name=name,payload=payload),
        ac_fast_check_current_user_has_case_access=Mock(return_value=True),
        ac_fast_check_current_user_has_war_room_access=Mock(return_value=True),
        CaseAccessLevel=SimpleNamespace(read_only=1,full_access=2), WarRoomAccessLevel=SimpleNamespace(read_only=1,full_access=2),
        _load_history=lambda *args:[], _scope_is_read_only=lambda _:False, _prepare_tools=lambda *args,**kwargs:[],
        system_prompt=lambda **kwargs:'system', _estimate_request_bytes=lambda *args:1,
        _history_was_redacted=lambda *args:False, _build_request_snapshot=lambda *args:{}, _consume_stream=consume)
    scope['db'].session.get.return_value=user
    fn = extract(SOURCE/'app/blueprints/rest/v2/case_chat/loop.py', 'run_one_iteration', scope)
    return fn, scope, conv, cfg, consume, biz


@pytest.mark.parametrize('limit,expected', [(0,71),(3,3),(-1,1)])
def test_unlimited_loop_is_not_silently_capped_and_finite_limits_still_work(limit, expected):
    fn, scope, conv, cfg, consume, biz = loop_scope(limit)
    emitted=[];fn(conversation=conv,emit=emitted.append)
    assert consume.call_count==expected
    assert all(call.kwargs['max_tokens']==0 for call in consume.call_args_list)
    assert bool(emitted)==bool(limit)
    biz.sum_tokens_today.assert_not_called()


@pytest.mark.parametrize('stop', ['budget', 'disabled', 'archived', 'case_access', 'finite_cap', 'stricter_policy', 'deleted_user', 'inactive_user', 'write_approval'])
def test_unlimited_loop_rechecks_stops_before_another_provider_request(stop):
    fn, scope, conv, cfg, consume, biz = loop_scope(budget=5 if stop=='budget' else 0)
    if stop=='budget':biz.sum_tokens_today.side_effect=[0,5]
    if stop=='disabled':scope['load_config'].side_effect=[cfg,SimpleNamespace(enabled=False)]
    if stop=='finite_cap':
        finite=SimpleNamespace(**vars(cfg));finite.max_tool_calls_per_turn=1
        scope['load_config'].side_effect=[cfg,finite]
    if stop=='stricter_policy':
        scope['resolve_for_conversation']=Mock(side_effect=[SimpleNamespace(restriction_level=0),SimpleNamespace(restriction_level=1)])
        biz.archive_conversation=Mock()
    if stop=='case_access':scope['ac_fast_check_current_user_has_case_access'].side_effect=[True,False]
    if stop=='deleted_user':scope['db'].session.get.side_effect=[scope['db'].session.get.return_value,None]
    if stop=='inactive_user':
        def deactivate(**kwargs):
            scope['db'].session.get.return_value.active=False
            return SimpleNamespace(terminated=False,paused_on_write=False)
        consume.side_effect=deactivate
    if stop=='archived':
        def archive(**kwargs):
            conv.archived_at=True
            return SimpleNamespace(terminated=False,paused_on_write=False)
        consume.side_effect=archive
    if stop=='write_approval':consume.side_effect=[SimpleNamespace(terminated=False,paused_on_write=True)]
    emitted=[];fn(conversation=conv,emit=emitted.append)
    assert consume.call_count==1
    assert bool(emitted)==(stop!='write_approval')


@pytest.fixture
def events(monkeypatch):
    base = load(SOURCE/'app/iris_engine/llm/providers/base.py', 'unlimited_event_base')
    monkeypatch.setitem(sys.modules,'app.iris_engine.llm.providers.base',base)
    return base


def test_provider_unlimited_wire_values(events):
    openai = load(SOURCE/'app/iris_engine/llm/providers/openai.py','unlimited_openai')
    ollama = load(SOURCE/'app/iris_engine/llm/providers/ollama.py','unlimited_ollama')
    assert 'max_tokens' not in openai.OpenAIProvider._build_body('m','s',[],[],None)
    assert openai.OpenAIProvider._build_body('m','s',[],[],8192)['max_tokens']==8192
    assert ollama.OllamaProvider._build_body('m','s',[],[],None)['options']['num_predict']==-1


def test_anthropic_uses_advertised_model_maximum_and_never_a_fake_unlimited_cap(events, monkeypatch):
    module = load(SOURCE/'app/iris_engine/llm/providers/anthropic.py','unlimited_anthropic')
    response = Mock(status_code=200)
    response.json.return_value={'max_tokens':65536}
    get = Mock(return_value=response)
    monkeypatch.setattr(module.requests,'get',get)
    provider = module.AnthropicProvider(api_key='test-key',base_url='https://provider.test')
    assert provider._model_output_limit('model')==65536
    assert provider._model_output_limit('model')==65536
    get.assert_called_once();response.close.assert_called_once()
    response.json.return_value={}
    assert provider._model_output_limit('other-model').provider_code=='model_limits_unavailable'
    stream = Mock(status_code=200)
    stream.iter_lines.return_value=['event: message_stop','data: {"type":"message_stop"}','']
    post=Mock(return_value=stream);monkeypatch.setattr(module.requests,'post',post)
    list(provider.stream_completion(model='model',system='s',messages=[],tools=[],max_tokens=None))
    assert post.call_args.kwargs['json']['max_tokens']==65536


def test_unlimited_text_does_not_remove_tool_argument_guards(events):
    diagnostics = load(SOURCE/'app/iris_engine/llm/diagnostics.py','unlimited_diagnostics')
    def stream(**kwargs):
        assert 'max_response_bytes' not in kwargs
        yield events.TextDelta('x'*60000)
        yield events.MessageEnd('end_turn')
    provider=SimpleNamespace(name='test',stream_completion=stream)
    result=list(diagnostics.provider_events(provider,correlation_id='test',max_response_bytes=None))
    assert isinstance(result[-1],events.MessageEnd)
    def tool_stream(**kwargs):yield events.ToolUseDelta('id','x'*49000)
    provider.stream_completion=tool_stream
    result=list(diagnostics.provider_events(provider,correlation_id='test',max_response_bytes=None))
    assert result[-1].provider_code=='output_limit'


def test_output_limit_migration_preserves_rows_and_zero_quotas():
    from sqlalchemy import create_engine,text
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    migration=load(SOURCE/'app/alembic/versions/utmn_yuki_limits01_output_limit.py','unlimited_migration')
    engine=create_engine('sqlite://')
    with engine.begin() as connection:
        for table in ('server_settings','chatbot_policy'):
            connection.execute(text(f'CREATE TABLE {table} (id integer PRIMARY KEY, daily_budget integer)'))
            connection.execute(text(f'INSERT INTO {table} VALUES(1,0)'))
        with Operations.context(MigrationContext.configure(connection)):
            migration.upgrade();migration.upgrade()
            assert connection.execute(text('SELECT chatbot_max_output_tokens,daily_budget FROM server_settings')).one()==(2048,0)
            assert connection.execute(text('SELECT max_output_tokens,daily_budget FROM chatbot_policy')).one()==(2048,0)
            migration.downgrade()
        assert connection.execute(text('SELECT daily_budget FROM server_settings')).scalar_one()==0


def test_policy_patch_validates_before_mutating_and_persists_all_unlimited_fields():
    from datetime import datetime,timezone
    actual=ast.parse((SOURCE/'app/schema/marshables.py').read_text())
    cls=next(n for n in actual.body if isinstance(n,ast.ClassDef) and n.name=='ChatbotPolicySchema')
    definitions={}
    for name in LIMITS:
        node=next(n for n in cls.body if isinstance(n,ast.AnnAssign) and n.target.id==name)
        definitions[name]=eval(compile(ast.Expression(node.value),'<policy field>','eval'),
                              {'auto_field':lambda name,**kwargs:fields.Integer(**kwargs),'Range':Range})
    schema=Schema.from_dict(definitions)()
    policy=SimpleNamespace(name='test policy', **{key:8 for key in LIMITS})
    query=Mock();query.filter_by.return_value.first.return_value=policy
    request=SimpleNamespace(get_json=lambda **kwargs:{'max_output_tokens':-1})
    db=SimpleNamespace(session=Mock())
    scope=dict(ChatbotPolicy=SimpleNamespace(query=query),request=request,db=db,
        ChatbotPolicySchema=lambda **kwargs:schema,_policy_schema=SimpleNamespace(dump=lambda value:{}),
        response_api_error=lambda message:('error',message),response_api_success=lambda data:('ok',data),
        datetime=datetime,timezone=timezone,track_activity=Mock())
    patch=extract(SOURCE/'app/blueprints/rest/v2/manage_routes/case_chat.py','update_policy',scope)
    assert patch(1)[0]=='error' and policy.max_output_tokens==8
    db.session.commit.assert_not_called()
    request.get_json=lambda **kwargs:{key:0 for key in LIMITS}
    assert patch(1)[0]=='ok' and all(getattr(policy,key)==0 for key in LIMITS)
    db.session.commit.assert_called_once()
