"""Derived journey views and durable, content-authored adventure outcomes."""
from ..content.store import for_session
from .conditions import condition_views


def settle_ending(session):
    if session.adventure_outcome is not None or session.actor is None: return
    for ending in for_session(session).endings:
        if (set(ending.required_flags) <= set(session.content_flags)
            and not set(ending.forbidden_flags) & set(session.content_flags)
            and all(session.quest_states.get(q)=='completed' for q in ending.completed_quests)
            and all(session.quest_states.get(q)=='failed' for q in ending.failed_quests)):
            session.adventure_outcome=dict(id=ending.id,title=ending.title,description=ending.description,
                level=session.actor.level,xp=session.actor.experience_points,scene_time=session.scene.time,
                locations=len(session.explored_nodes),clues=len(session.discovered_clues))
            return


def journey_view(session):
    if session.actor is None: return None
    from .lifecycle import rest_resources
    pack=for_session(session)
    return dict(content_version=pack.version,ending=session.adventure_outcome,
                conditions=condition_views(session.actor),rest=rest_resources(session),
                locations=len(session.explored_nodes),total_locations=len(pack.scenes))
