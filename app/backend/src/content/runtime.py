"""Runtime-facing content views; never a second progress store."""
from .store import for_session


def active_view(session):
    from ..game.world import quest_views
    pack = for_session(session)
    quests = quest_views(session) if session.actor else []
    return {"module_id": pack.id, "module_name": pack.name, "version": pack.version,
            "current_story_node": session.scene.name, "current_story_description": session.scene.description,
            "active_quests": [{"quest_id": q["id"], "quest_name": q["name"], "current_objective": q["objective"], "is_main": True}
                              for q in quests if q["status"] in ("active", "ready")],
            "completed_quests": [q["id"] for q in quests if q["status"] == "completed"]}


def catalog_view(pack, active_id=None):
    cover = None
    cover_builtin = None
    category, position = None, '50% 50%'
    if pack.visuals:
        v, slot = pack.visuals, pack.visuals.cover
        category = slot.fallback if slot else None
        inherited = v.theme.defaults.get(category or 'wilds')
        art = v.assets.get(slot.asset_id) if slot and slot.asset_id else v.theme.assets.get(inherited.asset_id) if inherited and inherited.asset_id else None
        cover_builtin = slot.builtin if slot and slot.builtin else inherited.builtin if inherited else None
        focus = slot if slot and (slot.asset_id or (slot.builtin and not art)) else inherited or slot
        if art:
            cover = art.data
        if focus:
            position = f'{focus.focal_x}% {focus.focal_y}%'
        category = inherited.fallback if inherited and inherited.fallback else category
    return {"id": pack.id, "name": pack.name, "description": pack.description, "version": pack.version,
            "cover_image": cover, "cover_builtin": cover_builtin,
            "cover_fallback": category, "cover_position": position,
            "illustrated": pack.visuals.theme.illustrated if pack.visuals else True,
            "status": "active" if pack.id == active_id else "inactive",
            "scenes": [{"id": s.id, "name": s.name, "description": s.description} for s in pack.scenes.values()],
            "npcs": [{"id": n.id, "name": n.name, "description": n.description, "type": n.type} for n in pack.characters.values()],
            "quests": [{"id": q.id, "name": q.name, "description": q.objective if q.kind == 'flags' else f"清理{pack.scenes[q.target_scene_id].name}",
                        "objectives": [q.objective if q.kind == 'flags' else f"击败全部敌人，向{pack.characters[q.giver_id].name}报告。"] + ([q.alternative_objective] if q.alternative_flags else []), "is_main": True} for q in pack.quests.values()]}
