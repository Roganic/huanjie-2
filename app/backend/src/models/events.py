"""Serializable event contracts shared by module authors, hosts and saved games."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator


class EventEffect(BaseModel):
    model_config = ConfigDict(extra='forbid')
    kind: Literal['relationship', 'damage', 'condition', 'flag', 'item', 'clue', 'encounter']
    target_id: str = Field(default='', max_length=128)
    value: str = Field(default='', max_length=2000)
    amount: int = Field(default=1, ge=-100, le=100)

    @model_validator(mode='after')
    def effect_contract(self):
        if self.kind == 'relationship' and (not self.target_id or not -2 <= self.amount <= 2 or self.amount == 0):
            raise ValueError('关系变化需要人物，单次范围为 -2 至 2，不能为 0')
        if self.kind in ('item', 'damage') and self.amount <= 0:
            raise ValueError('物品数量与伤害必须为正')
        if self.kind == 'condition' and self.value not in ('inspired', 'poisoned'):
            raise ValueError('未知状态')
        if self.kind in ('item', 'clue', 'encounter') and not self.target_id:
            raise ValueError('物品/线索必须有标识')
        if self.kind in ('flag', 'clue') and not self.value.strip():
            raise ValueError('标记/线索不能为空')
        if self.kind in ('damage', 'condition', 'flag') and self.target_id:
            raise ValueError('角色效果或世界标记不接受任意目标')
        if self.kind not in ('relationship', 'damage', 'item') and self.amount != 1:
            raise ValueError('这类效果不接受数量参数')
        if self.kind in ('relationship', 'damage', 'item', 'encounter') and self.value:
            raise ValueError('这类效果不接受额外文本参数')
        return self


class EventSpec(BaseModel):
    model_config = ConfigDict(extra='forbid')
    title: str = Field(default='后续事件', min_length=1, max_length=100)
    narration: str = Field(min_length=1, max_length=2000)
    category: Literal['social', 'environment', 'quest', 'combat'] = 'environment'
    scope: Literal['personal', 'scene', 'region', 'story'] = 'scene'
    priority: Literal['normal', 'urgent', 'critical'] = 'normal'
    clock: Literal['world', 'combat'] = 'world'
    delay: int = Field(default=0, ge=0, le=10000, description='world 为场景时间格，combat 为完整战斗轮')
    after_combat: Literal['continue', 'cancel'] = 'continue'
    required_flags: list[str] = Field(default_factory=list)
    wait_for_conditions: bool = False
    cancel_flags: list[str] = Field(default_factory=list)
    scene_id: str | None = None
    cancel_on_leave: bool = False
    visible: bool = True
    effects: list[EventEffect] = Field(default_factory=list, max_length=12)


    @model_validator(mode='after')
    def location_policy(self):
        if self.cancel_on_leave and not self.scene_id:
            raise ValueError('离开即取消的事件必须指定地点')
        return self


class ScheduledEvent(BaseModel):
    id: str
    source: str
    spec: EventSpec
    status: Literal['scheduled', 'fired', 'cancelled', 'expired'] = 'scheduled'
    due: int
    combat_id: str | None = None
    created_at: int
    resolved_at: int | None = None
    reason: str = ''


class EventClock(BaseModel):
    world_seconds: int = 0
    combat_rounds: int = 0
