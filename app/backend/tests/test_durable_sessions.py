"""Hosted adventures survive time away; reading does not create cloud writes."""
import json
from src import state
from src.models.state import CharacterCreateRequest


def test_durable_progress_survives_inactivity_and_reads_do_not_touch_disk(monkeypatch):
    monkeypatch.setattr(state, 'SESSION_DURABLE', True)
    sid = state.create_session().session_id
    state.create_character(CharacterCreateRequest(name='归来的旅人',character_class='warrior'),sid)
    session = state._get_session(sid,False)
    session.updated_at = 1
    state._persist_session(session)
    path = state._session_file(sid)
    before = path.read_text()
    state._sessions.clear()
    assert state.require_bootstrap_state(sid).actor.name == '归来的旅人'
    assert state.session_exists(sid)
    assert path.read_text() == before
    restored = state._get_session(sid,False)
    restored.content_flags.append('returned')
    state._save_session(restored)
    assert 'returned' in json.loads(path.read_text())['content_flags']
    assert json.loads(path.read_text())['updated_at'] > 1
