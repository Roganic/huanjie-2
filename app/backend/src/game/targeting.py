"""Target permission boundary; future NPC aggression/story rules plug in here."""
from ..content.store import for_session


def attack_block_reason(session, npc_id):
    world = session.world_scenes.get(session.scene.id)
    # Existing hostile encounters in older saves remain playable.
    if world and npc_id in world.enemies:
        return ""
    npc = for_session(session).characters.get(npc_id)
    if npc and npc.type == "hostile":
        return ""
    return "暂不支持攻击友方或中立人物。请选择交谈，或继续探索其他地点。"
