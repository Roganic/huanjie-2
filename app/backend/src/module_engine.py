"""Narrative compatibility entry point backed by current content and world state.

Event execution belongs to game.world; narration cannot advance a second story state.
"""


def build_module_context_for_prompt(session_id: str | None = None) -> str:
    from . import state
    from .content.store import for_session
    from .game.world import scene_view, quest_views
    with state._SESSION_LOCK:
        session = state._get_session(state._resolve_session_id(session_id), create_if_missing=True)
        if session.actor is None:
            return ""
        pack, scene = for_session(session), scene_view(session)
        quests = quest_views(session)
        lines = ["【模组剧情 / MODULE CONTEXT】", f"模组：{pack.name}（{pack.version}）",
                 f"当前位置：{scene.name}", scene.description,
                 "在场人物：" + "、".join(n.name for n in scene.npcs),
                 "已知线索：" + "；".join(session.discovered_clues.values())]
        lines.extend(f"任务：{q['name']}（{q['status_label']}）{q['objective']}" for q in quests)
        lines.append("叙事应依据上述内容与规则结算结果，不得虚构人物、出口、奖励或改写任务状态。")
        return "\n".join(lines)
