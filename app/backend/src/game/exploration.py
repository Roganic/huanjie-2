"""Deterministic exploration guidance and ordinary NPC conversations."""

import re

from .. import state
from ..models.action import ActionResponse, Outcome, ResolutionType
from ..models.state import AdventurePhase
from ..scene_map import get_scene_node
from .world import scene_view, world_scene, quest_view, quest_dialogue

DIRECTIONS = {"north": "向北", "south": "向南", "east": "向东", "west": "向西",
              "up": "向上", "down": "向下", "northeast": "向东北", "northwest": "向西北"}
from ..content.store import builtin, for_session
from .world import quest_views, fire_events

# Compatibility views; the content pack is the only authored source.
CLUES = {id: n.clue for id, n in builtin().characters.items() if n.clue}
REPLIES = {id: n.dialogue for id, n in builtin().characters.items()}


def is_dialogue(intent: str) -> bool:
    return bool(re.search(r"说(?:句|几句|两句|点)?话|交谈|对话|聊天|聊聊|打招呼|询问|打听|问问|搭话|问候|告诉|\b(talk|speak|chat|ask|hello|hi)\b", intent, re.I))


def talk(session, intent: str, npc_id: str | None = None) -> ActionResponse:
    """Caller holds the session lock. Never rolls dice or changes combat state."""
    pack = for_session(session)
    present = scene_view(session).npcs
    npc = next((n for n in present if n.id == npc_id), None) if npc_id else next(
        (n for n in present if n.name in intent or n.id in intent), None)
    success = False
    from .lifecycle import play_status
    if not play_status(session)["can_explore"]:
        message = "当前无法交谈，请先结束战斗并确保角色可以行动。"
    elif npc is None:
        names = "、".join(n.name for n in present if pack.characters[n.id].alive and n.type != "hostile")
        message = f"你现在位于{session.scene.name}。请指定在场的交谈对象" + (f"：{names}。" if names else "；这里暂时没有可交谈的人。")
    elif npc.type == "hostile" or not pack.characters[npc.id].alive:
        message = f"{npc.name}目前无法与你交谈。"
    elif npc_id is None and any(word in intent for word in ("威胁", "威吓", "说服", "欺骗", "恐吓", "攻击", "杀", "偷")):
        message = "目前支持普通交谈和打听线索；这类特殊社交行动尚未实现，请先选择普通交谈。"
    else:
        success = True
        dialogue = session.npc_dialogue_states.setdefault(npc.id, state.NPCDialogueState(npc_id=npc.id, npc_name=npc.name))
        repeat = "他再次提醒你：" if npc.id in session.discovered_clues else ""
        message = f"{npc.name}：{repeat}“{pack.characters[npc.id].dialogue}”"
        if pack.characters[npc.id].clue:
            session.discovered_clues[npc.id] = pack.characters[npc.id].clue
        events = " ".join(fire_events(session, "talk", npc.id))
        quest_reply = quest_dialogue(session, npc.id)
        if repeat and (quest_reply or events):
            message = f"{npc.name}：{quest_reply}{events}"
        else:
            message += quest_reply + events
        dialogue.add_entry("player", intent)
        dialogue.add_entry(npc.name, message)
    response = ActionResponse(action_status="executed" if success else "blocked", action_summary=intent, resolution_type=ResolutionType.AUTO_SUCCESS,
                              outcome=Outcome.SUCCESS if success else Outcome.FAILURE, effects=[],
                              narration=message, scene_progression="", gm_prompt="")
    state.append_action_history({"action": intent, "result": response.outcome.value,
                                 "narrative_summary": message}, session.session_id)
    return response


def guidance(session):
    from ..actions.scene_interaction import interaction_status
    from .targeting import attack_block_reason
    world = world_scene(session)
    pack = for_session(session)
    present = scene_view(session).npcs
    quest = quest_view(session)
    node = get_scene_node(session.scene.id, pack)
    exits = node.exits if node else session.scene.exits
    moves = []
    for exit in exits:
        target = get_scene_node(exit.target_scene_id, pack)
        if target:
            destination = world_scene(session, target.scene_id)
            count = sum(e.hp > 0 for e in destination.enemies.values())
            label = f"{DIRECTIONS.get(exit.direction, '前往')} · {target.name}"
            moves.append({"target_scene_id": target.scene_id, "label": label + (f" · 遭遇 {count} 名敌人" if count else "")})
    friendly = [n for n in present if n.type != "hostile" and pack.characters[n.id].alive]
    objective = f"先与{friendly[0].name}交谈，了解这里的消息。" if friendly else "选择出口继续探索。"
    if quest and (quest["status"] != "available" or session.discovered_clues):
        objective = quest["objective"]
    objects = []
    for element in pack.scenes[session.scene.id].interactions:
        status, reason = interaction_status(session, element)
        from .conditions import advantage_for, RULES
        advantage = advantage_for(session.actor, advantage=bool(element.advantage_flags) and set(element.advantage_flags) <= set(session.content_flags)) if session.actor else None
        hints = []
        if element.skill:
            hints.append("优势：掷两次取较高" if advantage is True else "劣势：掷两次取较低" if advantage is False else "正常检定")
        if element.failure_condition: hints.append("失败后" + RULES[element.failure_condition][0])
        if element.success_condition: hints.append("成功后获得" + RULES[element.success_condition][0])
        objects.append({"rule_hint": " · ".join(hints),"id": element.id, "name": element.name, "intent": element.action_name,
                        "status": status, "reason": reason, "skill": element.skill,
                        "dc": element.dc if element.skill else None, "time_cost": 1})
    from .events import event_view
    from .adjudication import challenge_view
    return {"pending_events": event_view(session), "event_facts": [e for e in session.event_facts if e.get('visible', True)][-5:],
            "challenges": challenge_view(session),
            "relationships": [{"name": pack.characters[id].name, "value": value} for id, value in session.relationships.items() if id in {n.id for n in present}],
            "location": session.scene.name, "objective": objective, "objects": objects,
            "danger": "危险" if world.dangerous else "已清理" if world.enemies else "和平",
            "enemy_count": sum(e.hp > 0 for e in world.enemies.values()),
            "quest": quest, "quests": quest_views(session),
            "targets": [{"id": n.id, "name": n.name, "hostile": n.type == "hostile", "attackable": not attack_block_reason(session, n.id)}
                        for n in present if pack.characters[n.id].alive],
            "npcs": [{"id": n.id, "name": n.name, "intent": f"和{n.name}说话"}
                     for n in present if n.type != "hostile" and pack.characters[n.id].alive],
            "interactions": [{"id": i.id, "name": i.name, "intent": i.action_name}
                             for i in pack.scenes[session.scene.id].interactions
                             if interaction_status(session, i)[0] == "available"],
            "moves": moves, "clues": list(session.discovered_clues.values())}


def describe_or_guide(session, intent):
    """Unknown input never invents targets or delegates a default ability check."""
    from ..actions.scene_interaction import normalize_intent
    text = normalize_intent(intent)
    looking = text in ("观察", "观察周围", "环顾四周", "查看场景", "我在哪", "这里有什么", "该做什么", "下一步", "look", "look around", "look around the tavern", "examine the room")
    view = guidance(session)
    actions = [o["intent"] for o in view["objects"] if o["status"] == "available"]
    actions += [n["intent"] for n in view["npcs"]]
    message = (f"{session.actor.name}，你在{view['location']}。{scene_view(session).description}" if looking else
               "没有找到这项行动对应的场景对象或处理方式。请一次描述一个行动，或选择下方的可用操作。")
    message += " 可用行动：" + "、".join(actions + [m["label"] for m in view["moves"]]) + "。"
    result = ActionResponse(action_status="read_only" if looking else "blocked", action_summary=intent, resolution_type=ResolutionType.AUTO_SUCCESS,
        outcome=Outcome.SUCCESS if looking else Outcome.FAILURE, effects=[], narration=message,
        scene_progression=view["objective"], gm_prompt="")
    state.append_action_history({"action": intent, "result": result.outcome.value, "narrative_summary": message},session.session_id)
    return result
