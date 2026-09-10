"""The shared output contract for editors and story parsers."""
import re
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator
from ..models.state import AbilityScores, InventoryItem
from ..models.events import EventSpec
from ..models.adjudication import ChallengeDefinition


class Definition(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ItemDefinition(InventoryItem):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    @model_validator(mode="after")
    def mechanics(self):
        def dice(expression):
            match = re.fullmatch(r"([1-9][0-9]?)d([1-9][0-9]?)([+-][0-9]{1,3})?", expression or "")
            return match is not None
        if self.type == "weapon" and (not dice(self.damage_dice) or self.attack_ability not in ("str", "dex")):
            raise ValueError("武器必须提供有效伤害骰（如 1d6）和攻击属性 str/dex")
        if self.type == "armor" and (self.base_ac is None or not 1 <= self.base_ac <= 40 or (self.max_dex_bonus is not None and self.max_dex_bonus < 0)):
            raise ValueError("护甲必须提供 1–40 的基础 AC，敏捷加值上限不能为负")
        if self.type == "consumable" and not (self.effect_type == "cure_poison" or self.effect_type == "heal" and dice(self.effect_dice)):
            raise ValueError("消耗品支持 heal（需恢复骰）或 cure_poison 效果")
        return self


class DropDefinition(Definition):
    item_id: str
    quantity: int = Field(default=1, ge=1, le=100)
    probability: float = Field(default=1, ge=0, le=1)


class KnowledgeDefinition(Definition):
    id: str = Field(min_length=1, max_length=128)
    text: str = Field(min_length=1, max_length=2000)
    required_flags: list[str] = Field(default_factory=list)


class CharacterDefinition(Definition):
    id: str
    name: str
    description: str = ""
    type: Literal["friendly", "neutral", "hostile"] = "neutral"
    race: str | None = None
    occupation: str | None = None
    role: str = "neutral"
    alive: bool = True
    hp: int = Field(default=8, ge=1, le=10000)
    ac: int = Field(default=10, ge=1, le=40)
    abilities: AbilityScores = Field(default_factory=lambda: AbilityScores(**dict.fromkeys(("str", "dex", "con", "int", "wis", "cha"), 10)))
    weapon_id: str | None = None
    dialogue: str = "我暂时没有更多消息。"
    clue: str | None = None
    personality: str = Field(default="", max_length=2000)
    knowledge: list[KnowledgeDefinition] = Field(default_factory=list)

    @model_validator(mode="after")
    def unique_knowledge(self):
        if len({k.id for k in self.knowledge}) != len(self.knowledge):
            raise ValueError("人物知识 ID 不能重复")
        return self
    xp_reward: int = Field(default=0, ge=0, le=100000)
    drops: list[DropDefinition] = Field(default_factory=list)


class ExitDefinition(Definition):
    direction: str
    target_scene_id: str


class InteractionDefinition(Definition):
    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    action_name: str = Field(min_length=1)
    time_cost: int = Field(default=1, ge=1, le=60)
    skill: Literal["acrobatics", "animal_handling", "arcana", "athletics", "deception", "history", "insight", "intimidation", "investigation", "medicine", "nature", "perception", "performance", "persuasion", "religion", "sleight_of_hand", "stealth", "survival"] | None = None
    aliases: list[str] = Field(default_factory=list)
    required_flags: list[str] = Field(default_factory=list)
    set_flags: list[str] = Field(default_factory=list)
    locked_reason: str = "请先寻找相关线索。"
    advantage_flags: list[str] = Field(default_factory=list)
    success_condition: Literal["poisoned", "inspired"] | None = None
    failure_condition: Literal["poisoned", "inspired"] | None = None
    dc: int = Field(default=10, ge=1, le=40)
    success_narrative: str = "你成功了。"
    failure_narrative: str = "这次尝试没有成功。"
    failure_damage: int = Field(default=0, ge=0, le=100)
    reward_item: str | None = None
    reward_info: str | None = None


class SceneDefinition(Definition):
    id: str
    name: str
    description: str
    aliases: list[str] = Field(default_factory=list)
    exits: list[ExitDefinition] = Field(default_factory=list)
    character_ids: list[str] = Field(default_factory=list)
    item_ids: list[str] = Field(default_factory=list)
    interactions: list[InteractionDefinition] = Field(default_factory=list)
    safe_rest: bool = False
    challenges: list[ChallengeDefinition] = Field(default_factory=list)


class ItemGrant(Definition):
    item_id: str
    quantity: int = Field(default=1, ge=1, le=100)


class ProgressHint(Definition):
    required_flags: list[str] = Field(default_factory=list)
    text: str = Field(min_length=1)


class QuestDefinition(Definition):
    id: str
    name: str
    kind: Literal["clear_scene", "flags"] = "clear_scene"
    giver_id: str
    target_scene_id: str
    objective: str = ""
    required_flags: list[str] = Field(default_factory=list)
    ready_text: str = ""
    rewards: list[ItemGrant] = Field(default_factory=list)
    alternative_flags: list[str] = Field(default_factory=list)
    alternative_objective: str = ""
    alternative_ready_text: str = ""
    progress_hints: list[ProgressHint] = Field(default_factory=list)
    xp_reward: int = Field(default=0, ge=0, le=100000)

    @model_validator(mode="after")
    def alternative_description(self):
        if self.kind == 'flags' and (not self.required_flags or not self.objective.strip() or not self.ready_text.strip()):
            raise ValueError("剧情任务必须说明目标、完成标记与完成后的实际结果")
        if self.alternative_flags and (not self.alternative_objective.strip() or not self.alternative_ready_text.strip()):
            raise ValueError("替代任务路线必须说明目标与完成后的实际结果")
        return self


class EventDefinition(EventSpec):
    id: str
    on: Literal["enter_scene", "talk", "scene_cleared", "interact"]
    target_id: str
    set_flags: list[str] = Field(default_factory=list)
    grants: list[ItemGrant] = Field(default_factory=list)


class EndingDefinition(Definition):
    id: str
    title: str
    description: str
    required_flags: list[str] = Field(default_factory=list)
    forbidden_flags: list[str] = Field(default_factory=list)
    completed_quests: list[str] = Field(default_factory=list)
    failed_quests: list[str] = Field(default_factory=list)


class SupplyPolicy(Definition):
    item_id: str
    starting_quantity: int = Field(default=2, ge=0, le=20)


from .visuals import ModuleVisuals


class ModulePack(Definition):
    schema_version: Literal[1] = 1
    id: str = Field(pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$")
    version: str = Field(min_length=1, max_length=32)
    name: str
    description: str
    starting_scene_id: str
    scenes: dict[str, SceneDefinition]
    characters: dict[str, CharacterDefinition]
    items: dict[str, ItemDefinition]
    quests: dict[str, QuestDefinition] = Field(default_factory=dict)
    events: dict[str, EventDefinition] = Field(default_factory=dict)
    endings: list[EndingDefinition] = Field(default_factory=list)
    supplies: SupplyPolicy | None = None
    visuals: ModuleVisuals | None = None

    @model_validator(mode="after")
    def references(self):
        errors = []
        def ref(value, collection, path):
            if value not in collection:
                errors.append(f"{path}: 未定义的引用 {value}")
        def validate_event(event, path):
            if event.scene_id:
                ref(event.scene_id, self.scenes, path + '.scene_id')
            collections = {'item': self.items, 'relationship': self.characters, 'encounter': self.scenes}
            for effect in event.effects:
                if effect.kind in collections:
                    ref(effect.target_id, collections[effect.kind], path + '.effects.' + effect.kind)
                if effect.kind == 'encounter' and event.scene_id != effect.target_id:
                    errors.append(path + ': 遭遇事件必须限定在对应场景')
        ref(self.starting_scene_id, self.scenes, "starting_scene_id")
        if self.visuals:
            for entity_id in self.visuals.map:
                ref(entity_id, self.scenes, 'visuals.map')
            for entity_id in self.visuals.map_layout:
                ref(entity_id, self.scenes, 'visuals.map_layout')
            for category in ('scenes', 'characters', 'items'):
                for entity_id in getattr(self.visuals, category):
                    ref(entity_id, getattr(self, category), 'visuals.' + category)
        if self.supplies:
            ref(self.supplies.item_id, self.items, "supplies.item_id")
        if len({e.id for e in self.endings}) != len(self.endings):
            errors.append("endings: 结局 ID 重复")
        for ending in self.endings:
            if set(ending.required_flags) & set(ending.forbidden_flags):
                errors.append('endings: 结局不能同时要求和排除同一标记')
            if not ending.completed_quests and not ending.failed_quests:
                errors.append("endings: 结局必须依赖已完成或失败的任务")
            for quest_id in [*ending.completed_quests, *ending.failed_quests]:
                ref(quest_id, self.quests, "endings.quests")
        for category in ("scenes", "characters", "items", "quests", "events"):
            for key, definition in getattr(self, category).items():
                if key != definition.id:
                    errors.append(f"{category}.{key}.id: 必须与索引一致")
        placements = {}
        aliases = {}
        for key, scene in self.scenes.items():
            for alias in [scene.id, scene.name, *scene.aliases]:
                normalized = alias.strip().lower()
                if not normalized or (normalized in aliases and aliases[normalized] != key):
                    errors.append(f"scenes.{key}.aliases: 地点名称或别名为空/歧义 {alias}")
                aliases[normalized] = key
            for id in scene.character_ids:
                if id in placements and placements[id] != key:
                    errors.append(f"scenes.{key}.character_ids: 同一人物不能放置在多个地点 {id}")
                placements[id] = key
            if len(scene.character_ids) != len(set(scene.character_ids)):
                errors.append(f"scenes.{key}.character_ids: 人物重复")
            if len(scene.item_ids) != len(set(scene.item_ids)):
                errors.append(f"scenes.{key}.item_ids: 物品重复")
            if len({e.direction for e in scene.exits}) != len(scene.exits):
                errors.append(f"scenes.{key}.exits: 出口方向重复")
            for e in scene.exits:
                ref(e.target_scene_id, self.scenes, f"scenes.{key}.exits")
            for id in scene.character_ids:
                ref(id, self.characters, f"scenes.{key}.character_ids")
            if len({i.id for i in scene.interactions}) != len(scene.interactions):
                errors.append(f"scenes.{key}.interactions: 互动 ID 重复")
            for interaction in scene.interactions:
                if any(not alias.strip() for alias in interaction.aliases):
                    errors.append(f"scenes.{key}.interactions.{interaction.id}.aliases: 别名不能为空")
                if interaction.reward_item:
                    ref(interaction.reward_item, self.items, f"scenes.{key}.interactions.{interaction.id}.reward_item")
            if len({c.id for c in scene.challenges}) != len(scene.challenges):
                errors.append(f"scenes.{key}.challenges: 挑战 ID 重复")
            goal_policies = {}
            for challenge in scene.challenges:
                if challenge.goal_id:
                    goal_key = (challenge.target_id, challenge.goal_id)
                    policy = (challenge.retry, challenge.retry_delay, challenge.retry_flags,
                              challenge.complete_on_success, challenge.completed_flags)
                    if goal_key in goal_policies and goal_policies[goal_key] != policy:
                        errors.append(f'scenes.{key}.challenges: 同一目标必须共用重试与完成条件')
                    goal_policies[goal_key] = policy
                ref(challenge.target_id, {scene.id, *scene.character_ids, *[i.id for i in scene.interactions]}, f"scenes.{key}.challenges.target_id")
                for event in [*challenge.on_success, *challenge.on_failure]:
                    validate_event(event, f'scenes.{key}.challenges.{challenge.id}.events')
                for option in challenge.consequences:
                    for event in [*option.on_success, *option.on_failure]:
                        validate_event(event, f'scenes.{key}.challenges.{challenge.id}.consequences.{option.id}')
            for id in scene.item_ids:
                ref(id, self.items, f"scenes.{key}.item_ids")
        for key, character in self.characters.items():
            for drop in character.drops:
                ref(drop.item_id, self.items, f"characters.{key}.drops")
            if character.weapon_id:
                ref(character.weapon_id, self.items, f"characters.{key}.weapon_id")
                if character.weapon_id in self.items and self.items[character.weapon_id].type != "weapon":
                    errors.append(f"characters.{key}.weapon_id: 必须引用武器")
        for key, quest in self.quests.items():
            ref(quest.giver_id, self.characters, f"quests.{key}.giver_id")
            ref(quest.target_scene_id, self.scenes, f"quests.{key}.target_scene_id")
            giver = self.characters.get(quest.giver_id)
            if giver and (not giver.alive or giver.type == "hostile" or giver.id not in placements):
                errors.append(f"quests.{key}.giver_id: 委托人必须是已放置的和平活人")
            target = self.scenes.get(quest.target_scene_id)
            if quest.kind == 'clear_scene' and target and not any(id in self.characters and self.characters[id].alive and self.characters[id].type == "hostile" for id in target.character_ids):
                errors.append(f"quests.{key}.target_scene_id: 清理委托的目标地点必须有敌人")
            for grant in quest.rewards:
                ref(grant.item_id, self.items, f"quests.{key}.rewards")
        for key, event in self.events.items():
            targets = ({f"{s.id}:{i.id}" for s in self.scenes.values() for i in s.interactions}
                       if event.on == "interact" else self.characters if event.on == "talk" else self.scenes)
            ref(event.target_id, targets, f"events.{key}.target_id")
            validate_event(event, f'events.{key}')
            for grant in event.grants:
                ref(grant.item_id, self.items, f"events.{key}.grants")
        if errors:
            raise ValueError("\n".join(errors))
        return self
