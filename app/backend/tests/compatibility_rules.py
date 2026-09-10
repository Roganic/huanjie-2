"""Direct checks for the retained legacy rule orchestrator, not the live /action API.

These tests preserve formula/tool/narrator coverage. Actual player input must use
an authored target and is covered by scene, story and encounter API tests.
"""
from src import state
from src.models.action import ActionRequest
from src.models.state import CharacterCreateRequest
from src.agent.orchestrator import resolve_action_with_agent


def resolve_compatibility_action(*, json, headers=None):
    sid = (headers or {}).get('X-Session-Id', state.DEFAULT_SESSION_ID)
    token = state.set_current_session(sid)
    try:
        if not state.has_character(sid):
            state.create_character(CharacterCreateRequest(name='Aldric',character_class='warrior'),sid)
        session = state._get_session(sid,False)
        req = ActionRequest.model_validate(json).model_copy(update={'actor':session.actor.name,'scene_id':session.scene.id})
        return resolve_action_with_agent(req)
    finally:
        state.reset_current_session(token)
