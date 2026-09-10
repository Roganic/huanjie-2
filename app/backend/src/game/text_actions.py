"""Transport-independent text adapter. Structured commands and legacy HTTP share the same game services."""
from __future__ import annotations
import re
from fastapi import HTTPException
from ..actions.scene_interaction import find_interactive_element, handle_scene_interaction
from ..models.action import ActionRequest, ActionResponse, Effect, Outcome, ResolutionType
from ..models.state import AdventurePhase
from ..state import append_action_history, get_actor, has_character, require_bootstrap_state, reset_current_session, set_current_session, update_combatant_hp, use_second_wind, _get_session, _resolve_session_id
from ..game.action_handler import is_spell_cast_intent, handle_spell_cast, is_rest_intent
_ITEM_USE_PREFIXES = ['使用', '用', 'use', 'consume', 'drink', '喝']

def _is_item_use_action(intent: str, approach: str) -> bool:
    """Check if an action is an item use action."""
    text = f'{intent} {approach}'.lower().strip()
    for prefix in _ITEM_USE_PREFIXES:
        if prefix.isascii():
            if text.startswith(prefix.lower() + ' ') or text == prefix.lower():
                return True
        elif text.startswith(prefix) or text.startswith(f'{prefix}'):
            return True
    return False

def _parse_item_name(intent: str, approach: str) -> str:
    """Parse item name from an item use action text."""
    text = intent.strip() or approach.strip()
    if text.startswith('使用'):
        return text[2:].strip()
    if text.startswith('用'):
        return text[1:].strip()
    if text.startswith('喝'):
        return text[1:].strip()
    lower = text.lower()
    for prefix in ('use ', 'consume ', 'drink '):
        if lower.startswith(prefix):
            return text[len(prefix):].strip()
    parts = text.split(None, 1)
    if len(parts) > 1:
        return parts[1].strip()
    return text

def execute_text(req, session_id):
    from ..state import DEFAULT_SESSION_ID, create_character
    from ..models.state import CharacterCreateRequest
    explicit_session_id = session_id != DEFAULT_SESSION_ID
    if explicit_session_id:
        try:
            require_bootstrap_state(session_id)
        except KeyError as exc:
            raise HTTPException(404, '会话不存在或已失效。') from exc
    token = set_current_session(session_id)
    try:
        if not has_character(session_id=session_id):
            if explicit_session_id:
                raise HTTPException(status_code=400, detail='No character found. Please create a character before taking actions.')
            create_character(CharacterCreateRequest(name='Aldric', character_class='warrior'), session_id=session_id)
        actor = get_actor(session_id)
        if actor.hp <= 0:
            raise HTTPException(409, '角色已倒下，请读取存档或重新开始冒险。')
        session = _get_session(session_id, False)
        req = req.model_copy(update={'actor': actor.name, 'scene_id': session.scene.id})
        from routes.combat import CombatActionRequest, _get_combat_state, _resolve_combat_action
        from ..state import _SESSION_LOCK
        text = req.intent.strip().lower()
        aliases = {'回气': 'second_wind', '动作如潮': 'action_surge', '隐匿': 'feint', '佯攻': 'feint', '防御': 'defend', '撤退': 'flee', '结束回合': 'end_turn'}
        ability = aliases.get(text, text)
        spell = None
        if is_spell_cast_intent(req.intent):
            from ..game.action_handler import _parse_spell_name, _SPELL_NAME_TO_ID
            from ..spells.spell_registry import get_spell
            name = _parse_spell_name(req.intent)
            spell = get_spell(_SPELL_NAME_TO_ID.get(name, name)) if name else None
            ability = spell.id if spell else ability
        with _SESSION_LOCK:
            encounter = _get_combat_state(session_id)
            if encounter is not None:
                if encounter.status != 'active':
                    raise HTTPException(409, '战斗已结束，请先返回探索。')
                attack_text = bool(re.search('^(?:我(?:要|想)?|尝试)?(?:攻击|砍|刺杀|杀死|殴打|attack\\b)', text))
                if req.action_type.value == 'attack' or req.weapon or attack_text:
                    ability = 'attack'
                named_target = next((p.id for p in encounter.participants if not p.is_player and (p.name in req.intent or p.id in req.intent)), None)
                used_item = None
                if _is_item_use_action(req.intent, req.approach):
                    from ..items.usage import _find_item_in_inventory, _match_healing_potion
                    item_name = _parse_item_name(req.intent, req.approach)
                    found = _find_item_in_inventory(actor, item_name)
                    if not found and _match_healing_potion(item_name):
                        found = _find_item_in_inventory(actor, 'healing_potion')
                    if found:
                        used_item = found[1]
                        ability = 'healing_potion' if used_item.id == 'healing_potion' else f'item:{used_item.id}'
                try:
                    result = _resolve_combat_action(session_id, encounter, CombatActionRequest(action_type=ability, target_id=named_target or req.target, weapon=req.weapon))
                except HTTPException as exc:
                    if exc.status_code not in (400, 409):
                        raise
                    failure = ActionResponse(action_summary=req.intent, resolution_type=ResolutionType.AUTO_SUCCESS, outcome=Outcome.FAILURE, effects=[], narration=str(exc.detail), scene_progression='', gm_prompt='')
                    return failure
                raw = result.model_dump(mode='json')
                spell_event = next((e for e in result.events if e['type'] == 'spell'), None)
                if spell_event:
                    from ..spells.spell_registry import get_spell
                    raw['outcome'] = 'success'
                    info = spell_event['resolution']
                    amount = info.get('damage') or 0
                    raw['spell_cast'] = {**info, 'spell_level': get_spell(spell_event['spell_id']).level, 'slot_used': info['slot_level'], 'effect_type': 'heal' if amount < 0 else 'damage' if amount > 0 else 'none', 'damage_total': max(0, amount), 'damage_roll': info['damage_rolls'], 'heal': max(0, -amount), 'narration': info['narrative']}
                if used_item is not None and (ability == 'healing_potion' or ability.startswith('item:')):
                    hp = next((e for e in result.events if e['type'] == 'hp' and e['actor_id'] == result.actor_id))
                    raw['item_use'] = {'item_name': used_item.name, 'effect_type': 'heal', 'roll_result': hp['delta'], 'hp_change': hp['delta']}
                raw.update(action_summary=req.intent, resolution_type='check' if result.hit is not None else 'auto_success', narration=result.narrative, scene_progression='', gm_prompt='')
                return raw
        from ..game.lifecycle import require_exploration
        require_exploration(session)
        from ..actions.scene_interaction import normalize_intent
        if not req.interaction_id and (re.match('^(?:不|不要|别|取消|我不)', normalize_intent(req.intent)) or re.search('然后|并且|接着|同时|[;；]', req.intent)):
            from ..game.exploration import describe_or_guide
            with _SESSION_LOCK:
                result = describe_or_guide(session, req.intent)
            return result
        from ..content.store import for_session
        with _SESSION_LOCK:
            pack = for_session(session)
            element = next((i for i in pack.scenes[session.scene.id].interactions if i.id == req.interaction_id), None) if req.interaction_id else find_interactive_element(req.intent, session.scene.id, pack)
            if req.interaction_id and element is None:
                raise HTTPException(400, '当前位置没有这个互动对象，请刷新场景。')
            if element is not None:
                result = handle_scene_interaction(req.model_copy(update={'intent': element.action_name}), element, session)
        if element is not None:
            return result
        from ..game.combat_service import begin_combat
        from ..game.world import move_to
        attack_text = bool(re.search('^(?:我(?:要|想)?|尝试)?(?:攻击|砍|刺杀|杀死|殴打|attack\\b)', text))
        if req.action_type.value == 'attack' or req.weapon or attack_text or (spell is not None and (not spell.healing_dice)) or (text in ('战斗', '迎战', '开战')):
            with _SESSION_LOCK:
                session = _get_session(session_id, False)
                target = req.target or next((n.id for n in session.scene.npcs if n.name in req.intent or n.id in req.intent), None)
                if target is None and text not in ('攻击', 'attack', '战斗', '迎战', '开战'):
                    raise HTTPException(400, '请明确选择当前场景中的攻击目标。')
                combat = begin_combat(session_id, target_id=target)
                message = '战斗开始。' + '\n'.join((entry.narrative for entry in combat.log))
                append_action_history({'action': req.intent, 'result': 'success', 'narrative_summary': message}, session_id)
            result = ActionResponse(action_summary=req.intent, resolution_type=ResolutionType.AUTO_SUCCESS, outcome=Outcome.SUCCESS, effects=[], narration=message, scene_progression='', gm_prompt='')
            return result
        from ..game.exploration import is_dialogue, talk
        if is_dialogue(req.intent):
            with _SESSION_LOCK:
                session = _get_session(session_id, create_if_missing=False)
                result = talk(session, req.intent)
            return result
        if re.search('^(?:我(?:要|想)?|尝试)?(?:前往|走向|进入|返回|离开|去|回到|向[东南西北上下]|go\\b|move\\b|enter\\b)', text):
            from ..scene_map import parse_movement_intent, get_connected_scene
            with _SESSION_LOCK:
                session = _get_session(session_id, False)
                from ..content.store import for_session
                pack = for_session(session)
                target, direction = parse_movement_intent(req.intent, pack)
                target = target or get_connected_scene(session.scene.id, direction or '', pack)
                if not target:
                    raise HTTPException(400, '无法确定目的地，请点击当前场景的出口。')
                moved = move_to(session, target)
            result = ActionResponse(action_summary=req.intent, resolution_type=ResolutionType.AUTO_SUCCESS, outcome=Outcome.SUCCESS, effects=[], narration=moved['message'], scene_progression='', gm_prompt='')
            return result
        intent_lower = req.intent.strip().lower()
        if intent_lower in ('second_wind', '回气'):
            if actor.hp >= actor.hp_max:
                raise HTTPException(409, '生命值已满，无需使用回气。')
            sw_result = use_second_wind(session_id=session_id)
            if not sw_result['success']:
                raise HTTPException(status_code=400, detail=sw_result['error'])
            actor = get_actor(session_id=session_id) or actor
            effects = []
            if actor is not None:
                effects.append(Effect(target=actor.id, field='hp', delta=sw_result['hp_healed'], description=f"Second Wind 恢复 {sw_result['hp_healed']} 点生命值"))
                session = _get_session(_resolve_session_id(session_id), create_if_missing=True)
                if session.game_phase == AdventurePhase.COMBAT:
                    update_combatant_hp(actor.id, actor.hp)
            from ..game.conditions import advance_time
            advance_time(session)
            result = ActionResponse(action_summary='使用 Second Wind', resolution_type=ResolutionType.AUTO_SUCCESS, outcome=Outcome.SUCCESS, effects=effects, narration=f"你集中精神，调动体内的战斗本能，恢复了 {sw_result['hp_healed']} 点生命值。", scene_progression='', gm_prompt='')
            append_action_history({'action': result.action_summary, 'result': result.outcome.value, 'narrative_summary': result.narration}, session_id=session_id)
            return result
        if ability in ('action_surge', 'feint', 'hide', 'defend', 'end_turn', 'flee'):
            raise HTTPException(409, '这项能力仅在战斗中使用；探索时请交谈、移动或整理行囊。')
        inventory_command = re.match('^(拾取|捡起|拿起|装备|卸下|pick up\\s+|equip\\s+|unequip\\s+)(.+)$', req.intent.strip(), re.I)
        if inventory_command or _is_item_use_action(req.intent, req.approach):
            from ..game.inventory import pickup_item, equip_item, unequip_item, use_item
            from ..content.store import for_session
            from ..items.usage import _find_item_in_inventory, _match_healing_potion
            with _SESSION_LOCK:
                session = _get_session(session_id, False)
                verb = inventory_command[1].strip().lower() if inventory_command else 'use'
                name = inventory_command[2].strip() if inventory_command else _parse_item_name(req.intent, req.approach)
                if verb in ('卸下', 'unequip'):
                    slot = {'武器': 'weapon', '护甲': 'armor', 'weapon': 'weapon', 'armor': 'armor'}.get(name)
                    if slot is None:
                        raise HTTPException(400, '请指定卸下武器或护甲。')
                    changed = unequip_item(session, slot)
                elif verb in ('拾取', '捡起', '拿起', 'pick up'):
                    pack = for_session(session)
                    candidates = [pack.items[id] for id in pack.scenes[session.scene.id].item_ids]
                    item = next((i for i in candidates if i.id == name or i.name.lower() == name.lower()), None)
                    if item is None:
                        raise HTTPException(404, '当前位置没有这件物品。')
                    changed = pickup_item(session, item.id)
                else:
                    found = _find_item_in_inventory(session.actor, name)
                    item = found[1] if found else next((i for i in session.actor.inventory if verb == 'use' and _match_healing_potion(name) and (i.id == 'healing_potion')), None)
                    if item is None:
                        raise HTTPException(400, '背包中没有这件物品。')
                    changed = equip_item(session, item.id) if verb in ('装备', 'equip') else use_item(session, item.id)
                result = ActionResponse(action_summary=req.intent, resolution_type=ResolutionType.AUTO_SUCCESS, outcome=Outcome.SUCCESS, effects=changed.get('effects', []), narration=changed['message'], inventory_update=changed.get('inventory_update'), item_use=changed.get('item_use'), scene_progression='', gm_prompt='')
            return result
        is_rest, rest_type = is_rest_intent(req.intent)
        if is_rest:
            from ..game.lifecycle import rest as rest_command
            with _SESSION_LOCK:
                changed = rest_command(session, rest_type)
            result = ActionResponse(action_summary=req.intent, resolution_type=ResolutionType.AUTO_SUCCESS, outcome=Outcome.SUCCESS, effects=changed['effects'], narration=changed['message'], scene_progression='', gm_prompt='')
            return result
        if spell is not None and spell.healing_dice and (actor.hp >= actor.hp_max):
            raise HTTPException(409, '生命值已满，无需消耗法术位。')
        if is_spell_cast_intent(req.intent):
            actor = get_actor(session_id=session_id)
            if actor is None:
                raise HTTPException(status_code=400, detail='No character found.')
            spell_result = handle_spell_cast(req.intent, actor, session_id=session_id)
            if spell_result is not None:
                if spell_result['success']:
                    from ..game.conditions import advance_time
                    advance_time(session)
                actor = get_actor(session_id=session_id) or actor
                _spell_session = _get_session(_resolve_session_id(session_id), create_if_missing=True)
                if _spell_session.game_phase == AdventurePhase.COMBAT:
                    update_combatant_hp(actor.id, actor.hp)
                spell_effects = [Effect(**e) for e in spell_result.get('effects', [])]
                if not spell_result['success']:
                    spell_response = ActionResponse(action_summary=f"施放 {spell_result['spell_name']}", resolution_type=ResolutionType.AUTO_SUCCESS, outcome=Outcome.FAILURE, effects=[], narration=spell_result.get('narration', spell_result.get('error_message', '')), scene_progression='', gm_prompt='')
                else:
                    spell_response = ActionResponse(action_summary=f"施放 {spell_result['spell_name']}", resolution_type=ResolutionType.AUTO_SUCCESS, outcome=Outcome.SUCCESS, effects=spell_effects, narration=spell_result.get('narration', ''), scene_progression='', gm_prompt='')
                append_action_history({'action': spell_response.action_summary, 'result': spell_response.outcome.value, 'narrative_summary': (spell_response.narration or '')[:400]}, session_id=session_id)
                raw = spell_response.model_dump(mode='json')
                raw['spell_cast'] = spell_result
                return raw
        from ..game.exploration import describe_or_guide
        with _SESSION_LOCK:
            result = describe_or_guide(session, req.intent)
        return result
    finally:
        reset_current_session(token)
