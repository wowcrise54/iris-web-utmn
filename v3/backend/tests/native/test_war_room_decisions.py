from pathlib import Path
from runpy import run_path

import pytest
from pydantic import ValidationError


MODULE = Path(__file__).resolve().parents[2] / 'source/app/business/war_room_decisions.py'


def test_decision_requires_title_and_rationale_and_rejects_supplied_status():
    schema = run_path(str(MODULE))['DecisionCreate']
    assert schema.model_validate({'title': ' Isolate host ', 'rationale': ' Active lateral movement '}).model_dump() == {
        'title': 'Isolate host', 'rationale': 'Active lateral movement',
    }
    for values in [
        {'title': '   ', 'rationale': 'Rationale'},
        {'title': 'Decision', 'rationale': ''},
        {'title': 'Decision', 'rationale': 'Rationale', 'status': 'approved'},
    ]:
        with pytest.raises(ValidationError):
            schema.model_validate(values)


def test_decision_workflow_requires_approval_before_implementation():
    module = run_path(str(MODULE))
    transition = module['validate_decision_transition']
    transition('proposed', 'approved')
    transition('proposed', 'rejected')
    transition('approved', 'implemented')
    for before, after in [
        ('proposed', 'implemented'), ('rejected', 'approved'), ('approved', 'approved'),
        ('implemented', 'proposed'),
    ]:
        with pytest.raises(module['InvalidDecisionTransition']):
            transition(before, after)
