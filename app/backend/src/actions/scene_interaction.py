"""Resolve authored scene interactions; content defines targets, checks and consequences."""
import re
from ..content.store import for_session
from ..models.action import ActionResponse, Effect, Outcome, ResolutionType, CheckDetail, SkillCheckDetail
from ..scene import get_scene_by_id
from .. import state


def normalize_intent(intent):
    text = intent.strip().lower().rstrip("。！.!？?")
    return re.sub(r"^(?:我(?:要|想|想要)?|请|尝试)\s*", "", text).strip()


def interaction_terms(element):
    return {normalize_intent(t) for t in [element.action_name, element.name, *element.aliases,
            *[verb + element.name for verb in ("调查", "检查", "查看", "辨认", "观察")]]}


def find_interactive_element(intent, scene_id, pack=None):
    scene = get_scene_by_id(scene_id, pack)
    matches = [e for e in scene.interactive_elements if normalize_intent(intent) in interaction_terms(e)] if scene else []
    return matches[0] if len(matches) == 1 else None


def is_scene_interaction_action(intent, scene_id, pack=None):
    return find_interactive_element(intent, scene_id, pack) is not None


def interaction_status(session, element):
    from ..game.lifecycle import play_status
    if element.id in session.completed_interactions.get(session.scene.id, []):
        return "completed", "已经完成，不会重复结算。"
    if not play_status(session)["can_explore"]:
        return "locked", play_status(session)["reason"]
    if not set(element.required_flags) <= set(session.content_flags):
        return "locked", element.locked_reason
    return "available", ""


def handle_scene_interaction(req, element, session):
    """Caller holds the session lock; UI and text both use this handler."""
    from ..game.world import fire_events, update_quest, quest_view
    status, reason = interaction_status(session, element)
    if status != "available":
        return ActionResponse(action_status="blocked", action_summary=req.intent, resolution_type=ResolutionType.AUTO_SUCCESS,
                              outcome=Outcome.FAILURE, effects=[], narration=reason, scene_progression="", gm_prompt="")
    actor = session.actor
    check = skill_check = None
    success = True
    if element.skill:
        from ..game.checks import resolve_check
        check = resolve_check(actor, skill=element.skill, dc=element.dc,
            advantage=bool(element.advantage_flags) and set(element.advantage_flags) <= set(session.content_flags))
        success = check.total >= element.dc
        skill_check = SkillCheckDetail(skill=element.skill, roll=check.roll,
            modifier=check.modifier+check.proficiency_bonus, total=check.total, dc=element.dc, success=success)
    effects = [Effect(target=session.scene.id, field="time", delta=element.time_cost, description="场景互动")]
    narrative = element.success_narrative if success else element.failure_narrative
    if success:
        session.completed_interactions.setdefault(session.scene.id, []).append(element.id)
        session.content_flags = list(dict.fromkeys([*session.content_flags, *element.set_flags]))
        if element.reward_item:
            effects.append(Effect(target=actor.id, field="inventory_add", delta=element.reward_item, description="取得调查奖励"))
            narrative += f" 获得了{for_session(session).items[element.reward_item].name}。"
        if element.reward_info:
            session.discovered_clues[f"{session.scene.id}:{element.id}"] = element.reward_info
            narrative += " " + element.reward_info
        event_text = fire_events(session, "interact", f"{session.scene.id}:{element.id}")
        narrative += " " + " ".join(text for text in event_text if text.strip() != narrative.strip())
    elif element.failure_damage:
        effects.append(Effect(target=actor.id, field="hp", delta=-element.failure_damage, description="调查受伤"))
    state.apply_effects(effects, session.session_id)
    from ..game.conditions import add_condition
    condition = element.success_condition if success else element.failure_condition
    if condition and session.actor.hp > 0:
        add_condition(session.actor, condition)
        effects.append(Effect(target=session.actor.id, field="conditions_add", delta=condition, description="场景互动状态"))
    update_quest(session)
    quest = quest_view(session)
    progression = (quest["objective"] if quest else "可以继续探索。") if success else f"本次尝试消耗 {element.time_cost} 格场景时间；可以重试或选择另一条路线。"
    if session.actor.hp <= 0:
        progression = "生命值已耗尽，请读取存档或重新冒险。"
    response = ActionResponse(action_summary=req.intent,
        resolution_type=ResolutionType.CHECK if check else ResolutionType.AUTO_SUCCESS,
        check=check, skill_check=skill_check,
        outcome=Outcome.SUCCESS if success else Outcome.FAILURE, effects=effects, narration=narrative.strip(),
        scene_progression=progression, gm_prompt="")
    state.append_action_history({"action":req.intent,"result":response.outcome.value,"narrative_summary":response.narration,
        "resolution_summary": {"resolution_type": response.resolution_type.value, "check": check.model_dump() if check else None},
        "scene_progression": progression},session.session_id)
    return response
