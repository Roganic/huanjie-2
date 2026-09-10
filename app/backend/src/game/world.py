"""Content-driven encounters, events and quests; session state owns all progress."""
from fastapi import HTTPException
from ..models.state import Actor, NPCType, AdventurePhase
from ..models.world import WorldSceneState
from ..scene import get_scene_by_id
from ..scene_map import get_scene_node
from ..content.store import for_session, builtin


def make_enemy(npc, pack=None):
    pack = pack or builtin()
    definition = pack.characters[npc.id]
    enemy = Actor(id=definition.id, name=definition.name, hp=definition.hp, hp_max=definition.hp,
        ac=definition.ac, abilities=definition.abilities.model_copy(deep=True), proficiency_bonus=0, description=definition.description)
    if definition.weapon_id:
        weapon = pack.items[definition.weapon_id].model_copy(deep=True)
        enemy.inventory = [weapon]
        enemy.equipped.weapon = weapon
    return enemy


def world_scene(session, scene_id=None):
    scene_id = scene_id or session.scene.id
    if scene_id not in session.world_scenes:
        pack = for_session(session)
        scene = get_scene_by_id(scene_id, pack)
        enemies = {n.id: make_enemy(n, pack) for n in (scene.npcs if scene else [])
                   if n.type == NPCType.HOSTILE and pack.characters[n.id].alive}
        session.world_scenes[scene_id] = WorldSceneState(enemies=enemies, dangerous=bool(enemies))
    return session.world_scenes[scene_id]


def scene_view(session):
    world = session.world_scenes.get(session.scene.id)
    if world is None:
        return session.scene.model_copy(deep=True)
    npcs = []
    for npc in session.scene.npcs:
        enemy = world.enemies.get(npc.id)
        if enemy is not None and enemy.hp <= 0:
            continue
        npcs.append(npc.model_copy(update={"type": NPCType.HOSTILE}) if enemy else npc.model_copy())
    description = session.scene.description
    if world.enemies and not any(e.hp > 0 for e in world.enemies.values()):
        description = "此处的敌人已被击败。你可以检查战利品，或从出口继续探索。"
    elif world.aggression:
        description = "你在这里攻击过当地人。场景已转为危险，敌对关系仍然保留。"
    return session.scene.model_copy(update={"npcs": npcs, "description": description})


def grant_items(session, grants):
    pack = for_session(session)
    for grant in grants:
        session.actor.inventory.extend(pack.items[grant.item_id].model_copy(deep=True) for _ in range(grant.quantity))


def fire_events(session, kind, target_id):
    from .events import trigger
    return trigger(session, kind, target_id)


def update_quest(session):
    for quest in for_session(session).quests.values():
        status = session.quest_states.get(quest.id, "available")
        if status in ("completed", "failed"):
            continue
        attacked = any(quest.giver_id in world.enemies for world in session.world_scenes.values())
        if attacked:
            session.quest_states[quest.id] = "failed"
        elif quest.giver_id in session.npc_dialogue_states or quest.giver_id in session.discovered_clues or status != "available":
            scene = world_scene(session, quest.target_scene_id)
            cleared = (bool(scene.enemies) and all(e.hp <= 0 for e in scene.enemies.values())) if quest.kind == 'clear_scene' else set(quest.required_flags) <= set(session.content_flags)
            alternative = bool(quest.alternative_flags) and set(quest.alternative_flags) <= set(session.content_flags)
            session.quest_states[quest.id] = "ready" if cleared or alternative else "active"


def quest_views(session):
    update_quest(session)
    pack = for_session(session)
    views = []
    labels = {"available": "待接取", "active": "进行中", "ready": "待交付", "completed": "已完成", "failed": "已中止"}
    for quest in pack.quests.values():
        status = session.quest_states.get(quest.id, "available")
        giver, target = pack.characters[quest.giver_id].name, pack.scenes[quest.target_scene_id].name
        reward = "、".join(f"{pack.items[g.item_id].name} ×{g.quantity}" for g in quest.rewards) or "无物品奖励"
        if quest.xp_reward:
            reward += f"、经验 {quest.xp_reward}"
        objectives = {"available": f"与{giver}交谈，接取委托。", "active": f"击败{target}的全部敌人，再向{giver}报告。",
            "ready": f"{target}已清理，与{giver}交谈领取奖励。", "completed": f"已向{giver}报告并领取奖励。", "failed": f"你攻击了委托人{giver}，委托已中止。"}
        if quest.kind == 'flags':
            objectives['active'] = quest.objective
            objectives['ready'] = quest.ready_text + f" 与{giver}交谈提交结果。"
            objectives['completed'] = quest.ready_text
        if quest.alternative_flags:
            objectives["active"] += " 也可以" + quest.alternative_objective
            for hint in quest.progress_hints:
                if set(hint.required_flags) <= set(session.content_flags):
                    objectives["active"] = hint.text
            scene = world_scene(session, quest.target_scene_id)
            if not (scene.enemies and all(e.hp <= 0 for e in scene.enemies.values())):
                objectives["ready"] = quest.alternative_ready_text + f" 与{giver}交谈领取奖励。"
                objectives["completed"] += " " + quest.alternative_ready_text
        views.append(dict(id=quest.id, name=quest.name, status=status, status_label=labels[status], objective=objectives[status], reward=reward))
    return views


def quest_view(session):
    views = quest_views(session)
    return next((v for v in views if v["status"] in ("active", "ready")), views[0] if views else None)


def quest_dialogue(session, npc_id):
    # A first conversation can start a quest even without an authored clue.
    for quest in for_session(session).quests.values():
        if quest.giver_id == npc_id and session.quest_states.get(quest.id, "available") == "available":
            session.quest_states[quest.id] = "active"
    update_quest(session)
    messages = []
    for view in quest_views(session):
        quest = for_session(session).quests[view["id"]]
        if quest.giver_id != npc_id:
            continue
        if view["status"] == "ready":
            grant_items(session, quest.rewards)
            from .progression import grant_experience
            growth = grant_experience(session, quest.xp_reward)
            session.quest_states[quest.id] = "completed"
            messages.append(f"收到你的报告了，谢谢你！收下{view['reward']}。委托已完成。")
            if growth.get("level_up"):
                messages.append(f"升至 {session.actor.level} 级，生命与职业资源已更新。")
        elif view["status"] == "active":
            messages.append(f"委托：{view['objective']} 奖励是{view['reward']}。")
        elif view["status"] == "completed":
            messages.append("委托已经完成，奖励也已交给你。")
    from .journey import settle_ending
    settle_ending(session)
    return " ".join(messages)


def move_to(session, target_id):
    from .. import state
    from .combat_service import begin_combat, combat_view
    from .lifecycle import require_exploration
    require_exploration(session)
    node = get_scene_node(session.scene.id, for_session(session))
    if not node or not any(e.target_scene_id == target_id for e in node.exits):
        raise HTTPException(400, "只能前往当前位置直接相连的地点。")
    previous = session.scene.id
    if not state.switch_scene(target_id, session.session_id):
        raise HTTPException(404, "目的地不存在。")
    session.previous_scene_id = previous
    from src.game.conditions import advance_time
    advance_time(session)
    event_text = fire_events(session, "enter_scene", target_id)
    world = world_scene(session)
    combat = begin_combat(session.session_id) if any(e.hp > 0 for e in world.enemies.values()) else None
    message = f"抵达{session.scene.name}。" + ("遭遇敌人，全体敌人进入先攻。" if combat else "")
    message += " ".join(event_text)
    state.append_action_history({"action": "移动", "result": "success", "narrative_summary": message}, session.session_id)
    return {"success": True, "message": message, "combat": combat_view(session.session_id, combat) if combat else None}
