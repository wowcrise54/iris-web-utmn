from pathlib import Path
from runpy import run_path
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock
import sys


def test_graph_presence_requires_case_access_and_leaves_on_session_revocation(monkeypatch):
    def stub(name, **attrs):
        module = ModuleType(name)
        vars(module).update(attrs)
        monkeypatch.setitem(sys.modules, name, module)

    socket = Mock()
    socket.on.side_effect = lambda *args, **kwargs: lambda handler: handler
    access = Mock(return_value=False)
    session_live = Mock(return_value=True)
    join = Mock()
    leave = Mock()
    token = Mock(return_value={'user_id': 7, 'user_name': 'Analyst', 'session_id': 'session'})
    stub('app', socket_io=socket)
    stub('app.blueprints.access_controls', is_user_authenticated=lambda request: False)
    stub('app.blueprints.iris_user', iris_current_user=None)
    stub('app.business.access_controls', ac_fast_check_user_has_case_access=access)
    stub('app.business.auth', validate_auth_token=token, auth_session_is_live=session_live)
    stub('app.models.authorization', CaseAccessLevel=SimpleNamespace(read_only=1, full_access=2))
    stub('app.socket_transport', join_room=join, leave_room=leave)
    stub('app.web', request=SimpleNamespace(sid='graph-test'))
    source = (Path(__file__).resolve().parents[2] / 'source/app/blueprints'
              / 'socket_io_event_handlers/graph_event_handlers.py')
    handlers = run_path(str(source))

    assert handlers['connect']({'case_id': True, 'token': 'test'}) is False
    assert handlers['connect']({'case_id': 12, 'token': 'test'}) is False
    join.assert_not_called()

    access.return_value = True
    assert handlers['connect']({'case_id': 12, 'token': 'test'}) is True
    join.assert_called_once_with('case-graph:12')
    handlers['heartbeat']()
    event, viewer = socket.emit.call_args.args
    assert event == 'graph-viewer'
    assert viewer['name'] == 'Analyst'
    assert socket.emit.call_args.kwargs == {'to': 'case-graph:12', 'namespace': '/case-graph'}

    handlers['publish_graph_change'](12, 'Editor')
    assert socket.emit.call_args.args == ('graph-changed', {'updated_by': 'Editor'})

    session_live.return_value = False
    handlers['heartbeat']()
    leave.assert_called_once_with('case-graph:12')
    assert socket.emit.call_args.args == ('graph-viewer-left', {'peer': viewer['peer']})
    assert not handlers['_members']
