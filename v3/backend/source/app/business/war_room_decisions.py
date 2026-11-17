from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, StringConstraints


class DecisionCreate(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)

    title: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=256)]
    rationale: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=20000)]


class DecisionStatus(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)

    status: Literal['approved', 'rejected', 'implemented']
    comment: Annotated[str, StringConstraints(strip_whitespace=True, max_length=4000)] = ''


class InvalidDecisionTransition(ValueError):
    pass


_TRANSITIONS = {
    'proposed': {'approved', 'rejected'},
    'approved': {'implemented'},
}


def validate_decision_transition(current, requested):
    if requested not in _TRANSITIONS.get(current, ()):
        raise InvalidDecisionTransition('This action is unavailable for the current decision status.')
