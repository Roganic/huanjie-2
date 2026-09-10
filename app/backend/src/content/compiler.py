"""Compile a causal story graph into the existing ModulePack; never execute it.

The model names story beats and their prerequisites. This compiler owns progress
flags, one-shot settlement and quest/ending wiring, rather than asking a model to
invent those low-level conventions correctly on every request.
"""
import hashlib
from typing import Annotated, Literal
from pydantic import Field, model_validator
from .schema import Definition, CharacterDefinition, ItemDefinition, ItemGrant, ModulePack, SupplyPolicy
from ..models.adjudication import Skill, Ability


class Place(Definition):
    id: str = Field(min_length=1, max_length=80)
    name: str
    description: str
    exits: list[str] = Field(default_factory=list, description='明确可到达的相邻地点 ID；双向路在两端分别填写')
    safe_rest: bool = False
    item_ids: list[str] = Field(default_factory=list)


class Dependency(Definition):
    beat_id: str
    outcome: Literal['success', 'failure'] = 'success'


class RelationshipEffect(Definition):
    kind: Literal['relationship']
    target_id: str
    amount: Literal[-2, -1, 1, 2]


class DamageEffect(Definition):
    kind: Literal['damage']
    amount: int = Field(ge=1, le=100)


class ConditionEffect(Definition):
    kind: Literal['condition']
    value: Literal['inspired', 'poisoned']


class ItemEffect(Definition):
    kind: Literal['item']
    target_id: str = Field(description='items 中实际存在的物品 ID')
    amount: int = Field(default=1, ge=1, le=100)


class ClueEffect(Definition):
    kind: Literal['clue']
    target_id: str = Field(description='这条线索的稳定标识')
    value: str = Field(min_length=1, max_length=2000)


class EncounterEffect(Definition):
    kind: Literal['encounter']
    target_id: str = Field(description='存在敌人的地点 ID')


StoryEffect = Annotated[RelationshipEffect | DamageEffect | ConditionEffect | ItemEffect | ClueEffect | EncounterEffect,
                        Field(discriminator='kind')]


class Outcome(Definition):
    narration: str = Field(min_length=1, max_length=2000)
    effects: list[StoryEffect] = Field(default_factory=list, max_length=10)
    delay: int = Field(default=0, ge=0, le=10000, description='整个后果（包括叙述和物品）延后发生的时间格。需要立即对话和稍后危险时，写成两个独立 beat')
    priority: Literal['normal', 'urgent', 'critical'] = 'normal'
    category: Literal['social', 'environment', 'quest', 'combat'] = 'environment'
    scope: Literal['personal', 'scene', 'region', 'story'] = 'scene'
    cancel_after: list[Dependency] = Field(default_factory=list)

    @model_validator(mode='after')
    def meaningful_cancellation(self):
        if self.cancel_after and self.delay == 0:
            raise ValueError('cancel_after 必须写在等待发生的延迟后果上；把取消条件放到倒计时事件，而不是已立即完成的行动')
        return self


class Prerequisites(Definition):
    requires: list[Dependency] = Field(default_factory=list, description='以下事件结果必须全部发生（AND）')
    requires_any: list[Dependency] = Field(default_factory=list, description='以下事件结果至少发生一个（OR）；与 requires 同时满足')


class StoryKnowledge(Prerequisites):
    id: str = Field(min_length=1, max_length=128)
    text: str = Field(min_length=1, max_length=2000)
    required_flags: list[str] = Field(default_factory=list, json_schema_extra={'deprecated': True})


class Person(CharacterDefinition):
    scene_id: str
    knowledge: list[StoryKnowledge] = Field(default_factory=list, description='人物在满足事件前置后可透露的信息；用 requires/requires_any 引用剧情事件，不编造底层标记')


class BeatBase(Prerequisites):
    id: str = Field(min_length=1, max_length=80)
    name: str
    scene_id: str
    target_id: str | None = Field(default=None, description='talk 是该地点的人物；检定可对人物或地点')
    time_cost: int = Field(default=1, ge=1, le=60, description='玩家完成此次 interact/check 操作花费的时间格；花更多时间复原物品应增加此值，结果在操作完成时立即发生，不使用 success.delay')
    success: Outcome


class AutomaticBeat(BeatBase):
    trigger: Literal['arrive', 'talk', 'interact', 'clear_scene'] = Field(description='arrive 只在玩家实际进入地点时检查，不会在其他事件成功后自动触发；talk 只在和 target_id 交谈时检查；interact 是玩家点击的操作。一个动作成功即产生该 beat 的事实，不再添加 arrive 成功事件。')

    @property
    def failure(self):
        return None


class CheckBeat(BeatBase):
    trigger: Literal['check']
    skill: Skill | None = None
    ability: Ability | None = None
    saving_throw: bool = False
    dc: int = Field(default=10, ge=5, le=30)
    stakes: str = Field(min_length=1)
    failure: Outcome

    @model_validator(mode='after')
    def check_contract(self):
        if not (self.skill or self.ability):
            raise ValueError('检定需要属性或技能')
        if self.saving_throw and (self.skill or not self.ability):
            raise ValueError('豁免只能使用属性')
        return self


Beat = Annotated[AutomaticBeat | CheckBeat, Field(discriminator='trigger')]


class StoryQuest(Prerequisites):
    model_config = {'json_schema_extra': {'anyOf': [
        {'required': ['requires'], 'properties': {'requires': {'minItems': 1}}},
        {'required': ['requires_any'], 'properties': {'requires_any': {'minItems': 1}}},
    ]}}
    id: str
    name: str
    giver_id: str
    objective: str
    ready_text: str
    # Retain old editable outlines; new generation uses the common AND/OR contract.
    alternative: list[Dependency] = Field(default_factory=list, json_schema_extra={'deprecated': True})
    alternative_objective: str = Field(default='', json_schema_extra={'deprecated': True})
    alternative_ready_text: str = Field(default='', json_schema_extra={'deprecated': True})
    xp_reward: int = Field(default=0, ge=0, le=100000)
    rewards: list[ItemGrant] = Field(default_factory=list)


class Conclusion(Prerequisites):
    id: str
    title: str
    description: str
    completed_quests: list[str] = Field(min_length=1)
    excludes: list[Dependency] = Field(default_factory=list, description='这些事件结果中任意一个发生，就不能进入这个结局；用于及时/延误等互斥结局')


class StoryGraph(Definition):
    name: str
    description: str
    starting_scene_id: str
    locations: list[Place] = Field(min_length=1, max_length=100)
    people: list[Person] = Field(default_factory=list, max_length=200)
    items: list[ItemDefinition] = Field(default_factory=list, max_length=300)
    beats: list[Beat] = Field(default_factory=list, max_length=300)
    quests: list[StoryQuest] = Field(default_factory=list, max_length=100)
    endings: list[Conclusion] = Field(default_factory=list, max_length=50)
    supplies: SupplyPolicy | None = None

    @model_validator(mode='after')
    def graph_contract(self):
        def keyed(values, category):
            result = {v.id: v for v in values}
            if len(result) != len(values): raise ValueError(f'{category}标识不能重复')
            return result
        places=keyed(self.locations,'地点'); people=keyed(self.people,'人物'); keyed(self.items,'物品')
        beats=keyed(self.beats,'事件'); quests=keyed(self.quests,'任务'); keyed(self.endings,'结局')
        if self.starting_scene_id not in places: raise ValueError('起始地点不存在')
        for place in self.locations:
            if any(p not in places for p in place.exits): raise ValueError(f'地点 {place.id} 的出口不存在')
        for person in self.people:
            if person.scene_id not in places: raise ValueError(f'人物 {person.id} 的地点不存在')
        def dependencies(values):
            for d in values:
                if d.beat_id not in beats: raise ValueError(f'前置事件 {d.beat_id} 不存在')
                if d.outcome=='failure' and beats[d.beat_id].trigger!='check': raise ValueError(f'事件 {d.beat_id} 没有失败分支')
        for beat in self.beats:
            if beat.scene_id not in places: raise ValueError(f'事件 {beat.id} 的地点不存在')
            if beat.trigger=='talk' and beat.target_id not in people: raise ValueError('交谈事件必须指定人物')
            if beat.target_id and beat.target_id != beat.scene_id and (beat.target_id not in people or people[beat.target_id].scene_id!=beat.scene_id):
                raise ValueError(f'事件 {beat.id} 的对象不在该场景')
            dependencies([*beat.requires, *beat.requires_any])
            for outcome in (beat.success,beat.failure):
                if outcome: dependencies(outcome.cancel_after)
        # Reachability understands OR joins: one valid incoming route suffices.
        reachable = set()
        for _ in beats:
            before = len(reachable)
            for beat in self.beats:
                if all(d.beat_id in reachable for d in beat.requires) and (not beat.requires_any or any(d.beat_id in reachable for d in beat.requires_any)):
                    reachable.add(beat.id)
            if len(reachable) == before: break
        if set(beats) - reachable:
            raise ValueError('事件前置条件形成循环或无法开始：' + '、'.join(sorted(set(beats) - reachable)))
        def compatible(values, excluded=()):
            # A one-shot check cannot both succeed and fail, including through
            # prerequisites of later beats. All entries in a requires list are AND.
            outcomes = {}
            def collect(d):
                if d.beat_id in outcomes:
                    if outcomes[d.beat_id] != d.outcome:
                        raise ValueError(f'前置条件同时要求事件 {d.beat_id} 成功与失败，无法达成')
                    return
                outcomes[d.beat_id] = d.outcome
                for parent in beats[d.beat_id].requires: collect(parent)
            for d in values: collect(d)
            if any(outcomes.get(d.beat_id) == d.outcome for d in excluded):
                raise ValueError('结局前置路线包含被排除的事件结果，无法达成')
        def compatible_join(value, excluded=()):
            compatible(value.requires, excluded)
            if value.requires_any:
                for dependency in value.requires_any:
                    try:
                        compatible([*value.requires, dependency], excluded)
                        break
                    except ValueError:
                        continue
                else: raise ValueError('所有备选前置分支均与必要条件冲突')
        for beat in self.beats: compatible_join(beat)
        for person in self.people:
            for knowledge in person.knowledge:
                dependencies([*knowledge.requires, *knowledge.requires_any])
                compatible_join(knowledge)
        for quest in self.quests:
            if quest.giver_id not in people: raise ValueError('任务委托人不存在')
            if not (quest.requires or quest.requires_any): raise ValueError('任务必须依赖实际事件')
            dependencies([*quest.requires,*quest.requires_any,*quest.alternative])
            compatible_join(quest)
            compatible(quest.alternative)
        for ending in self.endings:
            if any(q not in quests for q in ending.completed_quests): raise ValueError('结局引用了不存在的任务')
            dependencies([*ending.requires,*ending.requires_any,*ending.excludes])
            if any(d in ending.excludes for d in ending.requires):
                raise ValueError('结局不能同时要求和排除同一事件结果')
            compatible_join(ending, ending.excludes)
        reached, queue = set(), [self.starting_scene_id]
        while queue:
            place = queue.pop()
            if place in reached: continue
            reached.add(place); queue.extend(places[place].exits)
        if set(places) - reached:
            raise ValueError('这些地点从起点不可达，请补齐出口：' + '、'.join(sorted(set(places) - reached)))
        return self


def flag(id, outcome='success'):
    return 'beat-' + hashlib.sha256(id.encode()).hexdigest()[:24] + '-' + outcome


def compile_story(graph: StoryGraph | dict) -> dict:
    graph = StoryGraph.model_validate(graph)
    places={p.id:p for p in graph.locations};beats={b.id:b for b in graph.beats}
    doc={'schema_version':1,'id':'story-'+hashlib.sha256(graph.name.encode()).hexdigest()[:16], 'version':'1.0.0',
         'name':graph.name,'description':graph.description,'starting_scene_id':graph.starting_scene_id,
         'scenes':{},'characters':{},'items':{i.id:i.model_dump(mode='json',by_alias=True) for i in graph.items},
         'quests':{},'events':{},'endings':[],'supplies':graph.supplies.model_dump() if graph.supplies else None}
    flags=lambda ds:[flag(d.beat_id,d.outcome) for d in ds]
    # OR joins compile into a shared monotonic flag on each contributing result.
    # The rules engine never needs to infer narrative equivalence or run scripts.
    joins = {}
    def requirements(value):
        result = flags(value.requires)
        if value.requires_any:
            members = sorted(set(flags(value.requires_any)))
            joined = 'join-' + hashlib.sha256('|'.join(members).encode()).hexdigest()[:24]
            for member in members: joins.setdefault(member, set()).add(joined)
            result.append(joined)
        return result
    prerequisites = {('beat', b.id): requirements(b) for b in graph.beats}
    prerequisites.update({('quest', q.id): requirements(q) for q in graph.quests})
    prerequisites.update({('ending', e.id): requirements(e) for e in graph.endings})
    prerequisites.update({('knowledge', p.id, k.id): requirements(k) for p in graph.people for k in p.knowledge})
    for p in graph.locations:
        doc['scenes'][p.id]={'id':p.id,'name':p.name,'description':p.description,'safe_rest':p.safe_rest,'item_ids':p.item_ids,
            'character_ids':[],'interactions':[],'challenges':[],
            'exits':[{'direction':places[target].name,'target_scene_id':target} for target in p.exits]}
    for p in graph.people:
        doc['characters'][p.id]=p.model_dump(mode='json',exclude={'scene_id', 'knowledge'})
        doc['characters'][p.id]['knowledge']=[{'id':k.id,'text':k.text,
            'required_flags':list(dict.fromkeys([*k.required_flags, *prerequisites[('knowledge', p.id, k.id)]]))} for k in p.knowledge]
        doc['scenes'][p.scene_id]['character_ids'].append(p.id)
    def outcome(beat, value, state):
        return {'title':beat.name,'narration':value.narration,'scene_id':beat.scene_id if value.scope == 'scene' else None,'delay':value.delay,
            'priority':value.priority,'category':value.category,'scope':value.scope,'cancel_flags':flags(value.cancel_after),
            'effects':[e.model_dump() for e in value.effects]+[{'kind':'flag','value':f} for f in [flag(beat.id,state), *sorted(joins.get(flag(beat.id,state), set()))]]}
    for b in graph.beats:
        target=b.target_id or b.scene_id
        if b.trigger=='check':
            doc['scenes'][b.scene_id]['challenges'].append({'id':b.id,'name':b.name,'description':b.stakes,
                'target_id':target,'check_kind':'saving_throw' if b.saving_throw else 'ability','skill':b.skill,'ability':b.ability,
                'dc':b.dc,'time_cost':b.time_cost,'stakes':b.stakes,'retry':'once','required_flags':prerequisites[('beat', b.id)],
                'completed_flags':[flag(b.id)],'complete_on_success':True,
                'on_success':[outcome(b,b.success,'success')],'on_failure':[outcome(b,b.failure,'failure')]})
        else:
            if b.trigger=='interact':
                doc['scenes'][b.scene_id]['interactions'].append({'id':b.id,'name':b.name,'action_name':b.name,
                    'required_flags':prerequisites[('beat', b.id)],'set_flags':[], 'time_cost':b.time_cost,
                    'success_narrative':f'你已完成「{b.name}」，后续结果仍需等待。' if b.success.delay else b.success.narration})
            event=outcome(b,b.success,'success')
            event.update(id=b.id,on={'arrive':'enter_scene','talk':'talk','interact':'interact','clear_scene':'scene_cleared'}[b.trigger],
                target_id=f'{b.scene_id}:{b.id}' if b.trigger=='interact' else target if b.trigger=='talk' else b.scene_id,
                required_flags=prerequisites[('beat', b.id)])
            doc['events'][b.id]=event
    for q in graph.quests:
        doc['quests'][q.id]={'id':q.id,'name':q.name,'kind':'flags','giver_id':q.giver_id,
            'target_scene_id':beats[([*q.requires, *q.requires_any])[-1].beat_id].scene_id,'objective':q.objective,'ready_text':q.ready_text,
            'required_flags':prerequisites[('quest', q.id)],'alternative_flags':flags(q.alternative),'alternative_objective':q.alternative_objective,
            'alternative_ready_text':q.alternative_ready_text,'xp_reward':q.xp_reward,'rewards':[g.model_dump() for g in q.rewards]}
    for e in graph.endings:
        doc['endings'].append({'id':e.id,'title':e.title,'description':e.description,
            'completed_quests':e.completed_quests,'required_flags':prerequisites[('ending', e.id)],
            'forbidden_flags':flags(e.excludes)})
    # Same final contract as manual editing/import. Compilation never installs or plays.
    return ModulePack.model_validate(doc).model_dump(mode='json',by_alias=True)
