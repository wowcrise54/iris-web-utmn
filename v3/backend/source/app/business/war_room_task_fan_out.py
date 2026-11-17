from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator


class FanOutRequest(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)

    case_ids: list[Annotated[int, Field(gt=0, le=2**63 - 1)]] = Field(min_length=1, max_length=50)
    status_id: int | None = Field(default=None, gt=0, le=2**31 - 1)
    assign_to_case_owner: bool = True

    @field_validator('case_ids')
    @classmethod
    def unique_case_ids(cls, values):
        return list(dict.fromkeys(values))


class InvalidFanOut(ValueError):
    pass


def default_task_status_id(statuses):
    preferred = [identifier for identifier, name in statuses if (name or '').strip().casefold() == 'to do']
    return min(preferred or [identifier for identifier, _ in statuses], default=None)


def fan_out_tags(tags):
    labels = {'war-room': 'war-room'}
    for value in (tags or '').split(','):
        label = value.strip()[:64]
        if label:
            labels.setdefault(label.casefold(), label)
    return ','.join(labels.values())
