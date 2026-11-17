import ast
from pathlib import Path
from runpy import run_path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from pydantic import ValidationError


MODULE = Path(__file__).resolve().parents[2] / 'source/app/business/war_room_task_fan_out.py'
ROUTES = MODULE.parents[1] / 'blueprints/rest/v2/war_rooms/tasks.py'


def test_fan_out_validates_target_ids_and_deduplicates_in_input_order():
    schema = run_path(str(MODULE))['FanOutRequest']
    payload = schema.model_validate({'case_ids': [5, 1, 5], 'assign_to_case_owner': False})
    assert payload.case_ids == [5, 1]
    assert payload.assign_to_case_owner is False
    for ids in ([], [True], ['123'], [0], [2**63], list(range(1, 52))):
        with pytest.raises(ValidationError):
            schema.model_validate({'case_ids': ids})


def test_default_status_prefers_to_do_and_tags_preserve_existing_spelling():
    module = run_path(str(MODULE))
    resolve = module['default_task_status_id']
    assert resolve([(1, 'Closed'), (3, ' To Do ')]) == 3
    assert resolve([(5, 'In progress'), (1, 'Open')]) == 1
    assert resolve([]) is None
    assert module['fan_out_tags']('SOC, soc, War-Room, isolation') == 'war-room,SOC,isolation'


def test_read_only_destination_prevents_the_entire_distribution():
    tree = ast.parse(ROUTES.read_text(encoding='utf-8'))
    handler = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'post_task_fan_out')
    handler.decorator_list = []
    persist = Mock()
    access = Mock(side_effect=[4, None])
    denied = Mock()
    module = run_path(str(MODULE))
    namespace = {
        'require_war_room_write': Mock(return_value=None),
        'FanOutRequest': module['FanOutRequest'],
        'request': SimpleNamespace(get_json=lambda: {'case_ids': [10, 11]}),
        'ac_fast_check_current_user_has_case_access': access,
        'CaseAccessLevel': SimpleNamespace(full_access=4),
        'ac_api_return_access_denied': denied,
        'fan_out_task': persist,
    }
    exec(compile(ast.Module(body=[handler], type_ignores=[]), str(ROUTES), 'exec'), namespace)
    assert namespace['post_task_fan_out'](1, 100) is denied.return_value
    denied.assert_called_once_with(caseid=11)
    persist.assert_not_called()
