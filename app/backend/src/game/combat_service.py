"""Shared, model-independent combat commands. Session HP/resources are authoritative."""
from __future__ import annotations
import time
import uuid
from fastapi import HTTPException
from .. import state
from ..content.store import for_session
from ..models.state import AdventurePhase, Actor, DEFAULT_WEAPONS, InventoryItem
from ..engine.dice import roll_d20, roll_damage
from ..combat import resolve_attack_with_equipment
from ..spells.spell_registry import get_spell
from ..spells.spell_resolver import can_cast_spell, cast_spell

SPELL_IDS = ("magic_missile", "ray_of_frost", "burning_hands", "cure_wounds", "fireball_l3")


def enemies_for(session, combat):
    if combat.encounter_scene_id:
        return session.world_scenes[combat.encounter_scene_id].enemies
    # Old saves preserve their original single opponent and initiative.
    return {session.enemy.id: session.enemy}


def _sync(session, combat):
    enemies = enemies_for(session, combat)
    for p in combat.participants:
        a = session.actor if p.is_player else enemies[p.id]
        p.hp, p.hp_max, p.ac, p.conditions = a.hp, a.hp_max, a.ac, list(a.conditions)
    combat.scene = session.scene.model_copy(deep=True)


def available_actions(session_id, combat):
    actor = state._get_session(session_id, False).actor
    if actor is None:
        return []
    blocked = "战斗已结束" if combat.status != "active" else (
        "还不是你的回合" if combat.current_actor_id != actor.id else "角色无法行动" if actor.hp <= 0 else "")
    actions = []
    def add(id, name, target, cost, reason="", description=""):
        reason = blocked or reason
        if cost == "action" and combat.actions_remaining < 1:
            reason = reason or "本回合主动作已用完"
        if cost == "bonus_action" and not combat.bonus_action_available:
            reason = reason or "本回合附赠动作已用完"
        actions.append(dict(id=id, name=name, target=target, cost=cost, available=not reason,
                            disabled_reason=reason or None, description=description))
    add("attack", "普通攻击", "enemy", "action", description="使用当前装备的武器攻击")
    add("defend", "防御", "self", "action", description="直到下次轮到你，敌方攻击具有劣势")
    kind = actor.character_class.value if actor.character_class else ""
    if kind == "warrior":
        add("second_wind", "回气", "self", "bonus_action",
            "需要休息恢复" if actor.class_features.second_wind_used else "生命值已满" if actor.hp == actor.hp_max else "",
            "恢复 1d10 + 等级生命值，消耗附赠动作")
        add("action_surge", "动作如潮", "self", "free",
            "需要休息恢复" if actor.class_features.action_surge_used else "", "本回合增加一次主动作，每次休息间可用一次")
    if kind == "rogue":
        add("feint", "佯攻", "self", "bonus_action", "已经准备佯攻" if "hidden" in actor.conditions else "",
            "消耗附赠动作，下次攻击获得优势；不进行警戒或察觉检定，命中可触发偷袭")
    if kind == "mage":
        for id in SPELL_IDS:
            spell = get_spell(id)
            if not spell:
                continue
            _, reason = can_cast_spell(actor, spell)
            if spell.healing_dice and actor.hp >= actor.hp_max:
                reason = "生命值已满"
            add(spell.id, spell.name_cn, "self" if spell.healing_dice else "enemy", "action", reason,
                (f"消耗最低可用的 {spell.level} 环及以上法术位（高环代用不增强效果）" if spell.level else "戏法，不消耗法术位") + "；消耗主动作")
    potions = {i.id: i for i in actor.inventory if i.type == "consumable" and (i.effect_type in ("heal", "cure_poison") or i.id == "healing_potion")}
    if "healing_potion" not in potions:
        add("healing_potion", "治疗药水", "self", "action", "没有治疗药水")
    for id, potion in potions.items():
        add("healing_potion" if id == "healing_potion" else f"item:{id}", potion.name, "self", "action",
            ("当前没有中毒" if "poisoned" not in actor.conditions else "") if potion.effect_type == "cure_poison" else "生命值已满" if actor.hp == actor.hp_max else "", "消耗一件物品和主动作")
    add("end_turn", "结束回合", "none", "free")
    add("flee", "撤退", "none", "free", description="返回来时的地点；敌人伤势和敌对状态保留，不获得本场奖励")
    return actions


def combat_view(session_id, combat):
    _sync(state._get_session(session_id, False), combat)
    return {**combat.model_dump(mode="json"), "combatants": [p.model_dump() for p in combat.participants],
            "available_actions": available_actions(session_id, combat)}


def _event(actor, target, kind, delta, **details):
    return dict(actor_id=actor.id, target_id=target.id, type=kind, delta=delta, **details)


def _damage(actor, target, amount, events):
    before = target.hp
    target.hp = max(0, min(target.hp_max, target.hp - amount))
    events.append(_event(actor, target, "hp", target.hp-before, before=before, after=target.hp))
    if target.hp == 0 and "defeated" not in target.conditions:
        target.conditions.append("defeated")
        events.append(_event(actor, target, "condition_added", "defeated"))


def _status(session, combat):
    if session.actor.hp <= 0:
        combat.status = "defeat"
    elif all(e.hp <= 0 for e in enemies_for(session, combat).values()):
        combat.status = "victory"


def _log(combat, actor_id, action, target, narrative, hit=None, damage=0):
    from routes.combat import CombatLogEntry
    combat.log.append(CombatLogEntry(actor_id=actor_id, action_type=action, target_id=target,
                                    narrative=narrative, hit=hit, damage=damage, timestamp=int(time.time()*1000)))


def _enemy_turns(session, combat, events):
    from routes.combat import _advance_turn
    while combat.status == "active" and combat.current_actor_id != session.actor.id:
        enemy, player = enemies_for(session, combat)[combat.current_actor_id], session.actor
        if enemy.hp <= 0:
            _advance_turn(combat)
            continue
        result = resolve_attack_with_equipment(enemy, player.ac, advantage=False if "defending" in player.conditions else None)
        _damage(enemy, player, result["damage"], events)
        events.append(_event(enemy, player, "attack", result["damage"], **result))
        narrative = f"{enemy.name}攻击{player.name}，" + (f"造成 {result['damage']} 点伤害。" if result["hit"] else "未命中。")
        _log(combat, enemy.id, "attack", player.id, narrative, result["hit"], result["damage"])
        if player.hp <= 0:
            session.defeat_reason = f"{player.name}在{session.scene.name}被{enemy.name}击倒，生命值已耗尽。"
        _status(session, combat)
        if combat.status == "active":
            _advance_turn(combat)
    if combat.status == "active":
        combat.actions_remaining = 1
        combat.bonus_action_available = True
        session.actor.class_features.sneak_attack_available = True
        if "defending" in session.actor.conditions:
            session.actor.conditions.remove("defending")
            events.append(_event(session.actor, session.actor, "condition_removed", "defending"))


def _finish(session, combat):
    event_messages = []
    from routes.combat import _set_combat_state, _award_victory_rewards
    previous = session.combat_snapshot or {}
    old_round = previous.get('round_number', 1) if previous.get('combat_id') == combat.combat_id else 1
    from .events import advance_combat
    advance_combat(session, max(0, combat.round_number-old_round), combat.combat_id, combat.status != 'active')
    _status(session, combat)
    _sync(session, combat)
    if combat.status == "victory":
        _award_victory_rewards(session.session_id, combat, persist=False)
        _sync(session, combat)
    if combat.status != "active":
        session.game_phase = AdventurePhase.ENDED
    if combat.encounter_scene_id:
        from .world import update_quest
        world = session.world_scenes[combat.encounter_scene_id]
        world.dangerous = world.aggression or any(e.hp > 0 for e in world.enemies.values())
        update_quest(session)
        if combat.status == "victory":
            from .world import fire_events
            event_messages = fire_events(session, "scene_cleared", combat.encounter_scene_id)
            for message in event_messages:
                _log(combat, session.actor.id, "event", None, message)
    combat.log = combat.log[-100:]
    _set_combat_state(session.session_id, combat)
    return event_messages


def begin_combat(session_id, target_id=None):
    from routes.combat import CombatState, _get_combat_state, _actor_to_participant, _sort_initiative
    session = state._get_session(session_id, False)
    if session.actor is None:
        raise HTTPException(400, "No character found. 请先创建角色。")
    if session.actor.hp <= 0:
        raise HTTPException(409, "角色无法行动。")
    existing = _get_combat_state(session_id)
    if existing is not None:
        return existing
    if session.game_phase != AdventurePhase.EXPLORATION:
        raise HTTPException(409, "当前不能开始遭遇。")
    from .world import world_scene, make_enemy, update_quest
    world = world_scene(session)
    if target_id:
        npc = next((n for n in session.scene.npcs if n.id == target_id or n.name == target_id), None)
        if npc is None or not for_session(session).characters[npc.id].alive:
            raise HTTPException(400, "请选择当前场景中仍存活的人物。")
        from .targeting import attack_block_reason
        blocked = attack_block_reason(session, npc.id)
        if blocked:
            raise HTTPException(409, blocked)
        if npc.id in world.enemies and world.enemies[npc.id].hp <= 0:
            raise HTTPException(409, "这个目标已经被击败。")
        if npc.id not in world.enemies:
            world.enemies[npc.id] = make_enemy(npc, for_session(session))
            world.aggression = True
        world.dangerous = True
        update_quest(session)
    enemies = [e for e in world.enemies.values() if e.hp > 0]
    if not enemies:
        raise HTTPException(409, "此处没有敌人。和平人物暂不支持攻击。")
    session.enemy = enemies[0]  # Legacy reader compatibility; world state owns encounter enemies.
    player = session.actor
    participants = [_actor_to_participant(a, is_player=a.id == player.id,
                    initiative=roll_d20() + a.abilities.modifier("dex")) for a in [player, *enemies]]
    order = _sort_initiative(participants)
    combat = CombatState(combat_id="combat-" + uuid.uuid4().hex, round_number=1, turn_index=0,
                         participants=participants, initiative_order=order, current_actor_id=order[0],
                         scene=session.scene.model_copy(deep=True), status="active",
                         encounter_scene_id=session.scene.id, retreat_scene_id=session.previous_scene_id)
    session.game_phase = AdventurePhase.COMBAT
    _log(combat, player.id, "initiative", None,
         "全部敌人参战。先攻顺序：" + " → ".join(next(p.name for p in participants if p.id == id) for id in order))
    _enemy_turns(session, combat, [])
    _finish(session, combat)
    return combat


def execute_turn(session_id, combat, req):
    from routes.combat import CombatActionResponse, _advance_turn
    session = state._get_session(session_id, False)
    player = session.actor
    enemies = enemies_for(session, combat)
    living = [e for e in enemies.values() if e.hp > 0]
    enemy = next((e for e in enemies.values() if req.target_id in (e.id, e.name)), living[0] if living else next(iter(enemies.values())))
    action = req.ability_id or (req.skill if req.action_type == "skill" else req.action_type)
    if action == "hide":
        action = "feint"  # Old clients/saves map to the new non-spatial rogue ability.
    option = next((a for a in available_actions(session_id, combat) if a["id"] == action), None)
    if option is None:
        raise HTTPException(400, "未知战斗行动或当前职业不具备此能力。")
    if not option["available"]:
        raise HTTPException(409, option["disabled_reason"])
    target = enemy if option["target"] == "enemy" else player
    if req.target_id and option["target"] != "none" and req.target_id not in (target.id, target.name):
        raise HTTPException(400, "该能力不能作用于这个目标。")
    if option["target"] == "enemy" and enemy.hp <= 0:
        raise HTTPException(409, "目标已被击败。")
    if action == "attack" and req.weapon:
        weapon = player.equipped.weapon
        if weapon is None or req.weapon not in (weapon.id, weapon.name):
            raise HTTPException(400, "只能使用当前装备的武器。")
    events, costs = [], []
    hit, damage, sneak = None, 0, 0
    previous_logs = len(combat.log)
    if action == "attack":
        hidden = "hidden" in player.conditions
        from .conditions import advantage_for, consume_inspiration
        advantage_state = advantage_for(player, advantage=hidden)
        consume_inspiration(player)
        result = resolve_attack_with_equipment(player, enemy.ac, advantage=advantage_state)
        hit, damage = result["hit"], result["damage"]
        if hidden:
            player.conditions.remove("hidden")
            events.append(_event(player, player, "condition_removed", "hidden"))
        if hit and advantage_state is True and player.character_class.value == "rogue" and player.class_features.sneak_attack_available:
            sneak, rolls = roll_damage(f"{max(1, (player.level+1)//2)}d6")
            player.class_features.sneak_attack_available = False
            damage += sneak
            events.append(_event(player, enemy, "sneak_attack", sneak, rolls=rolls))
        _damage(player, enemy, damage, events)
        events.append(_event(player, enemy, "attack", damage, **result))
        narrative = f"{player.name}使用{result.get('weapon_used', '武器')}攻击{enemy.name}，" + (f"造成 {damage} 点伤害" + (f"（含偷袭 {sneak} 点）" if sneak else "") + "。" if hit else "未命中。")
    elif action == "second_wind":
        healing, _ = roll_damage(f"1d10+{player.level}")
        before = player.hp
        _damage(player, player, -healing, events)
        player.class_features.second_wind_used = True
        costs.append(dict(resource="second_wind", amount=1))
        narrative = f"回气恢复了 {player.hp-before} 点生命值。"
    elif action == "action_surge":
        player.class_features.action_surge_used = True
        combat.actions_remaining += 1
        costs.append(dict(resource="action_surge", amount=1))
        narrative = "动作如潮：本回合增加一次主动作。"
    elif action == "feint":
        player.conditions.append("hidden")
        events.append(_event(player, player, "condition_added", "hidden"))
        narrative = "你以佯攻制造破绽，下次攻击获得优势；没有进行察觉或距离检定。"
    elif action == "defend":
        if "defending" not in player.conditions:
            player.conditions.append("defending")
        events.append(_event(player, player, "condition_added", "defending"))
        narrative = "你采取防御姿态，敌人对你的攻击具有劣势，持续到下次轮到你。"
    elif action == "healing_potion" or action.startswith("item:"):
        from ..items.usage import resolve_item_use
        item_id = "healing_potion" if action == "healing_potion" else action.removeprefix("item:")
        result = resolve_item_use(player, item_id)
        if not result.success:
            raise HTTPException(409, result.error_message)
        before = player.hp
        for effect in result.effects:
            state._apply_one(session, effect)
        player = session.actor
        events.append(_event(player, player, "hp", player.hp-before, before=before, after=player.hp))
        costs.append(dict(resource=item_id, amount=1))
        narrative = result.narration
    elif action == "flee":
        combat.status = "escaped"
        narrative = "你撤离了遭遇，没有获得战利品。"
    elif action == "end_turn":
        combat.actions_remaining = 0
        narrative = "你结束了本回合。"
    else:
        spell = get_spell(action)
        result = cast_spell(player, spell.id, target)
        if not result.success:
            raise HTTPException(409, result.error_message)
        amount = result.damage or 0
        if spell.healing_dice:
            amount = min(0, amount)
        _damage(player, target, amount, events)
        damage = max(0, amount)
        hit = result.hit if result.hit is not None else True
        if spell.level:
            costs.append(dict(resource="spell_slot", level=result.slot_level, amount=1))
        events.append(_event(player, target, "spell", amount, spell_id=spell.id, resolution=result.model_dump(mode="json")))
        narrative = result.narrative
    if option["cost"] == "action":
        combat.actions_remaining -= 1
        costs.append(dict(resource="action", amount=1))
    elif option["cost"] == "bonus_action":
        combat.bonus_action_available = False
        costs.append(dict(resource="bonus_action", amount=1))
    _log(combat, player.id, action, target.id, narrative, hit, damage)
    from src.game.conditions import advance_time
    advance_time(session)
    _status(session, combat)
    if combat.status == "active" and combat.actions_remaining == 0:
        _advance_turn(combat)
        _enemy_turns(session, combat, events)
    # Capture this turn before trimming the persistent log.
    narrative = "\n".join(entry.narrative for entry in combat.log[previous_logs:]) or narrative
    event_messages = _finish(session, combat)
    narrative = "\n".join([narrative, *event_messages])
    state.append_action_history(dict(action=option["name"], result="success", narrative_summary=narrative), session_id)
    from ..models.action import Effect
    effects = [Effect(target=e["target_id"], field="hp", delta=e["delta"], description="生命值变化") for e in events if e["type"] == "hp"]
    rewards = combat.rewards or {}
    return CombatActionResponse(action_type=action, actor_id=player.id, target_id=target.id, hit=hit,
        damage=damage, sneak_attack_damage=sneak or None, effects=effects, narrative=narrative, combat_state=combat,
        events=events, costs=costs, outcome="failure" if hit is False else "success",
        available_actions=available_actions(session_id, combat), xp_gained=rewards.get("xp_gained",0),
        loot_gained=rewards.get("loot_gained",[]), level_up=rewards.get("level_up"), combat_ended=combat.status!="active", victory=combat.status=="victory")


def leave_combat(session_id, reason):
    from routes.combat import _get_combat_state, _clear_combat_state
    session = state._get_session(session_id, False)
    combat = _get_combat_state(session_id)
    if combat is None:
        raise HTTPException(404, "没有战斗记录。")
    if reason in ("victory", "defeat") and reason != combat.status:
        raise HTTPException(409, "战斗结果由系统判定，不能手动指定。")
    if combat.status == "active":
        combat.status = "escaped" if reason == "flee" else "defeat"
    message = '本次冒险已经结束，请读取存档或重新冒险。' if combat.status == 'defeat' else '已完成胜利结算并返回探索。' if combat.status == 'victory' else '已撤退并返回探索。'
    result = dict(message=message, combat_id=combat.combat_id, status=combat.status, final_round=combat.round_number,
                  participants=[p.model_dump() for p in combat.participants])
    if combat.status == "defeat":
        if reason == "surrender" and session.actor.hp > 0:
            session.actor.hp = 0
            session.defeat_reason = "你放弃了这场战斗，本次冒险已经结束。"
            if "defeated" not in session.actor.conditions:
                session.actor.conditions.append("defeated")
        _finish(session, combat)
        return result
    from .events import advance_combat
    advance_combat(session, 0, combat.combat_id, ended=True)
    session.game_phase = AdventurePhase.EXPLORATION
    session.actor.conditions = [c for c in session.actor.conditions if c not in ("hidden", "defending")]
    _clear_combat_state(session_id)
    if combat.status == "escaped" and combat.retreat_scene_id:
        # Some world links are one-way; returning along the entry route is always allowed.
        state.switch_scene(combat.retreat_scene_id, session_id)
        session.previous_scene_id = combat.encounter_scene_id
    state._save_session(session)
    return result
