"""Model outages cannot hold typed gameplay controls hostage."""
import pytest
from src import state
from src.gm import host
from src.game.commands import facts
from tests.conftest import create_session_and_character
from tests.test_gm_host import model

@pytest.mark.asyncio
async def test_direct_controls_work_without_initializing_provider(client, monkeypatch, predictable_combat):
    sid = await create_session_and_character(client)
    h = {'X-Session-Id': sid}
    def forbidden():
        raise AssertionError('Typed rule actions must not initialize a model provider')
    monkeypatch.setattr(host, 'ToolProvider', forbidden)
    async def direct(**cmd):
        body = {**cmd, 'request_id': str(len(state._get_session(sid, False).command_receipts))}
        r = await client.post('/commands', headers=h, json=body)
        assert r.status_code == 200, r.text
        assert r.json()['result']['gm']['calls'] == 0
        before = facts(state._get_session(sid, False))
        replay = await client.post('/commands', headers=h, json=body)
        assert replay.json()['replayed']
        assert facts(state._get_session(sid, False)) == before
        return r.json()
    weapon = state._get_session(sid, False).actor.equipped.weapon
    await direct(kind='unequip', target_id='weapon')
    await direct(kind='equip', target_id=weapon.id)
    await direct(kind='interact', target_id='veteran-advice', expected_scene_id='tavern-01')
    await direct(kind='challenge', target_id='social:tavern-keeper-01:persuasion')
    blocked = await direct(kind='challenge', target_id='social:tavern-keeper-01:persuasion')
    assert blocked['result']['feedback']['detail']
    assert '换一种说法' not in blocked['result']['feedback']['summary']
    await direct(kind='move', target_id='dungeon-entrance-01')
    await direct(kind='move', target_id='combat-encounter-01')
    await direct(kind='combat', action='defend')
    assert state._get_session(sid, False).combat_snapshot['round_number'] == 2

@pytest.mark.asyncio
async def test_talk_button_skips_planning_preserves_dialogue_and_reply(client, monkeypatch):
    sid = await create_session_and_character(client)
    p = model(monkeypatch, ('respond', {'message': '老马库斯放下酒杯：“有什么想打听的？”'}))
    command = {'kind': 'talk', 'target_id': 'tavern-keeper-01', 'expected_scene_id': 'tavern-01', 'request_id': 'talk-button',
               'text': {'scene_id': 'tavern-01', 'actor': 'hero', 'intent': '与老马库斯交谈', 'approach': ''}}
    r = await client.post('/commands', headers={'X-Session-Id': sid}, json=command)
    assert r.status_code == 200, r.text
    assert r.json()['result']['gm']['calls'] == 1 and len(p.messages) == 1
    s = state._get_session(sid, False)
    assert s.discovered_clues and s.discourse['speaker_id'] == 'tavern-keeper-01'
    assert s.narrative_history[-1].gm_narration == r.json()['result']['gm_narration']
    stale = await client.post('/commands', headers={'X-Session-Id': sid}, json={**command, 'expected_scene_id': 'elsewhere', 'request_id': 'stale'})
    assert stale.status_code == 409 and len(p.messages) == 1
