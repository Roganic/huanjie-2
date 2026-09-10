"""Typed adjudication plans; goals are player intentions, never assertions of success."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator, field_validator
from .events import EventSpec

Skill = Literal['acrobatics', 'animal_handling', 'arcana', 'athletics', 'deception', 'history', 'insight', 'intimidation', 'investigation', 'medicine', 'nature', 'perception', 'performance', 'persuasion', 'religion', 'sleight_of_hand', 'stealth', 'survival']
Ability = Literal['str', 'dex', 'con', 'int', 'wis', 'cha']


class ApproachDefinition(BaseModel):
    """An author-approved method. The host selects its ID, never a difficulty."""
    model_config = ConfigDict(extra='forbid')
    id: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=100)
    description: str = Field(min_length=1, max_length=400)
    skill: Skill
    dc: int = Field(default=15, ge=5, le=30)
    required_flags: list[str] = Field(default_factory=list)


class ConsequenceOption(BaseModel):
    """A complete success/failure pair, chosen before the roll."""
    model_config = ConfigDict(extra='forbid')
    id: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=100)
    stakes: str = Field(min_length=1, max_length=500)
    required_flags: list[str] = Field(default_factory=list)
    on_success: list[EventSpec] = Field(min_length=1, max_length=4)
    on_failure: list[EventSpec] = Field(min_length=1, max_length=4)


class ChallengeChoice(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    approach_id: str | None = Field(default=None, max_length=80)
    consequence_id: str | None = Field(default=None, max_length=80)

    @field_validator('approach_id', 'consequence_id', mode='before')
    @classmethod
    def empty_is_default(cls, value):
        return None if value == '' else value


class ChallengeDefinition(BaseModel):
    model_config = ConfigDict(extra='forbid')
    id: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=100)
    description: str = Field(min_length=1, max_length=1000)
    target_id: str = Field(min_length=1, max_length=128)
    check_kind: Literal['automatic', 'ability', 'saving_throw'] = 'ability'
    skill: Skill | None = None
    ability: Ability | None = None
    dc: int = Field(default=15, ge=5, le=30)
    time_cost: int = Field(default=1, ge=1, le=60)
    risk: Literal['minor', 'moderate', 'major'] = 'minor'
    stakes: str = Field(min_length=1, max_length=500)
    retry: Literal['once', 'after_change', 'with_cost'] = 'after_change'
    retry_delay: int = Field(default=0, ge=0, le=60, description='大于 0 时，经过这些场景时间格也可重试')
    required_flags: list[str] = Field(default_factory=list)
    goal_id: str | None = Field(default=None, min_length=1, max_length=128)
    retry_flags: list[str] | None = None
    completed_flags: list[str] = Field(default_factory=list)
    complete_on_success: bool = False
    approaches: list[ApproachDefinition] = Field(default_factory=list, max_length=6)
    consequences: list[ConsequenceOption] = Field(default_factory=list, max_length=4)
    on_success: list[EventSpec] = Field(default_factory=list, max_length=4)
    on_failure: list[EventSpec] = Field(default_factory=list, max_length=4)

    @model_validator(mode='after')
    def meaningful(self):
        if self.approaches and self.check_kind != 'ability':
            raise ValueError('可选做法仅用于技能检定')
        for options in (self.approaches, self.consequences):
            if len({o.id for o in options}) != len(options):
                raise ValueError('做法或后果选项 ID 不能重复')
        if self.retry == 'once' and self.retry_delay:
            raise ValueError('仅限一次的挑战不能通过倒计时重开')
        if self.check_kind == 'ability' and not (self.skill or self.ability):
            raise ValueError('属性检定需要属性或技能')
        if self.check_kind == 'saving_throw' and (not self.ability or self.skill):
            raise ValueError('豁免必须指定属性，不使用技能熟练')
        if self.check_kind == 'automatic' and (self.skill or self.ability):
            raise ValueError('自动处理不掷骰')
        if self.check_kind != 'automatic' and not self.on_failure:
            raise ValueError('检定必须说明实际失败后果')
        return self


class AdjudicateArgs(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    kind: Literal['attack', 'challenge', 'expression', 'observe', 'unavailable']
    target_id: str = Field(min_length=1, max_length=128)
    goal: str = Field(min_length=1, max_length=300)
    approach: str = Field(min_length=1, max_length=300)
    challenge_id: str | None = None
    approach_id: str | None = Field(default=None, max_length=80)
    consequence_id: str | None = Field(default=None, max_length=80)


class ClarifyArgs(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    question: str = Field(min_length=1, max_length=300)
