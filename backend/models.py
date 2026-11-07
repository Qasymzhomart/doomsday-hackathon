from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator
import math


class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)


class Criterion(StrictModel):
    criterion_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    weight: float = Field(ge=0)
    answer_type: Literal['boolean', 'scale'] = 'boolean'
    min_score: float = 0
    max_score: float = Field(default=1, gt=0)
    allowed_scores: list[float] | None = None
    allow_na: bool = False
    critical_rule: bool = False
    section: str = ''

    @model_validator(mode='after')
    def valid_scale(self):
        if self.min_score < 0 or self.min_score >= self.max_score:
            raise ValueError('Invalid score range')
        if self.answer_type == 'boolean' and (self.min_score, self.max_score) != (0, 1):
            raise ValueError('Boolean scale must be 0..1')
        if self.allowed_scores is not None and (not self.allowed_scores or any(
            not math.isfinite(s) or not self.min_score <= s <= self.max_score for s in self.allowed_scores
        )):
            raise ValueError('Invalid allowed_scores')
        return self


class Checklist(StrictModel):
    name: str = Field(min_length=1)
    criteria: list[Criterion] = Field(min_length=1)
    rounding_decimals: int = Field(default=2, ge=0, le=6)

    @model_validator(mode='after')
    def unique_ids(self):
        ids = [c.criterion_id for c in self.criteria]
        if len(ids) != len(set(ids)):
            raise ValueError('Duplicate criterion_id')
        return self


class Message(StrictModel):
    timestamp: str
    speaker: Literal['client', 'operator', 'bot', 'system']
    text: str


class Conversation(StrictModel):
    conversation_id: str = Field(min_length=1)
    channel: Literal['agent chat', 'voice call']
    language: Literal['RU', 'KZ', 'EN']
    transcript: list[Message]
    audio_url: str | None = None


class AIResult(StrictModel):
    criterion_id: str
    applicable: bool = Field(strict=True)
    answer: str
    score: float | None = Field(default=None, strict=True)
    reason: str = Field(min_length=1)
    evidence_ids: list[str]
    critical_error: bool = Field(strict=True)


class AIEvaluation(StrictModel):
    criteria: list[AIResult]


class EvaluateRequest(StrictModel):
    checklist_id: int | None = None


class ImportRequest(StrictModel):
    group_id: str = Field(min_length=1)


class AppealRequest(StrictModel):
    conversation_id: str
    evaluation_id: int
    criterion_id: str
    comment: str = Field(min_length=1)


class ReviewRequest(StrictModel):
    decision: Literal['confirmed', 'changed']
    new_score: float | None = None
    applicable: bool | None = None
    critical_error: bool | None = None
    reason: str = Field(min_length=1)
