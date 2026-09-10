import pytest
from src import state
from src.content.store import get_pack
from src.content.authoring import review
from src.models.state import CharacterCreateRequest
from src.game.commands import execute_command, GameCommand, facts


def start(module):
    sid = state.create_session().session_id
    session = state._get_session(sid, False)
    session.content_pack = get_pack(module)
    state.create_character(CharacterCreateRequest(name='试玩',character_class='warrior',ability_generation='standard_array'),sid)
    def act(kind, target=None):
        command = GameCommand(kind=kind,target_id=target,request_id=f'test-{len(session.command_receipts)}')
        result = execute_command(sid,command)
        stable = facts(session)
        assert execute_command(sid,command)['replayed'] and facts(session) == stable
        return result['result']
    return session, act


@pytest.mark.parametrize('module', ['last-ferry-light','city-beneath-the-tide'])
def test_authored_maps_and_flag_sources_are_complete(module):
    result=review(get_pack(module).model_dump())
    assert result['valid'] and result['warnings']==[]


@pytest.mark.parametrize(('choice','ending'), [('publish','names'),('seal','sealed'),('stop','still')])
def test_medium_adventure_three_final_choices_and_growth(monkeypatch,choice,ending):
    monkeypatch.setattr('src.engine.dice.roll_d20',lambda:20)
    s,act=start('city-beneath-the-tide')
    act('talk','lu');act('move','archive');act('talk','song');act('challenge','read-ledger')
    act('move','water-hall');act('talk','lu');act('move','market');act('talk','wen')
    act('move','cistern');act('challenge','repair-filter');act('move','market');act('talk','wen')
    act('move','cistern');act('move','glassworks');act('challenge','ask-engineer')
    act('move','sluice');act('challenge','trace-valve');act('move','tide-heart')
    act('challenge',choice)
    other=next(c for c in ['publish','seal','stop'] if c != choice)
    assert act('challenge',other)['action_status']=='blocked'
    act('move','sluice');act('move','glassworks');act('move','archive');act('talk','song')
    assert s.adventure_outcome['id']==ending
    assert s.actor.level==2 and s.actor.experience_points==360
    assert all(status=='completed' for status in s.quest_states.values())


def test_medium_all_failed_checks_still_finish(monkeypatch):
    monkeypatch.setattr('src.engine.dice.roll_d20',lambda:1)
    s,act=start('city-beneath-the-tide')
    act('talk','lu');act('move','archive');act('talk','song')
    assert act('challenge','read-ledger')['outcome']=='failure'
    act('challenge','recover-ledger');act('move','water-hall');act('talk','lu')
    act('move','market');act('talk','wen');act('move','cistern')
    assert act('challenge','repair-filter')['outcome']=='failure'
    act('challenge','clean-spare');act('move','market');act('talk','wen');act('move','cistern')
    act('move','glassworks');assert act('challenge','ask-engineer')['outcome']=='failure'
    act('challenge','copy-map');act('move','sluice');assert act('challenge','trace-valve')['outcome']=='failure'
    act('challenge','reset-valve')
    # Deliberately spend additional travel time to exercise the flood deadline.
    for _ in range(3): act('move','glassworks');act('move','sluice')
    act('move','tide-heart');act('challenge','publish')
    act('move','sluice');act('move','glassworks');act('move','archive');act('talk','song')
    assert s.adventure_outcome['id']=='after-flood'


def test_medium_optional_encounter_settles_both_enemies_and_does_not_respawn(monkeypatch):
    from src.game import combat_service
    from routes.combat import _get_combat_state
    import random
    rng = random.Random(1)
    monkeypatch.setattr(random, 'randint', lambda low, high: 20 if high == 20 else rng.randint(low, high))
    initiative = iter([20, 1, 1])
    monkeypatch.setattr(combat_service, 'roll_d20', lambda: next(initiative))
    s, act = start('city-beneath-the-tide')
    act('move', 'market'); act('move', 'underpass'); act('attack', 'crab-a')
    battle = _get_combat_state(s.session_id)
    assert {p.id for p in battle.participants if not p.is_player} == {'crab-a', 'crab-b'}
    assert battle.initiative_order[0] == s.actor.id
    for _ in range(12):
        battle = _get_combat_state(s.session_id)
        if battle.status != 'active': break
        target = next(p.id for p in battle.participants if not p.is_player and p.hp > 0)
        result = execute_command(s.session_id, GameCommand(kind='combat', action='attack', target_id=target,
            request_id=f'fight-{len(s.command_receipts)}'))
        stable = facts(s)
        assert execute_command(s.session_id, GameCommand(kind='combat', action='attack', target_id=target,
            request_id=result['request_id']))['replayed'] and facts(s) == stable
    battle = _get_combat_state(s.session_id)
    assert battle.status == 'victory' and s.actor.experience_points == 120
    assert {'tide-knife', 'water-tonic'} <= {i.id for i in s.actor.inventory}
    execute_command(s.session_id, GameCommand(kind='leave', action='victory'))
    act('move', 'market'); act('move', 'underpass')
    assert s.game_phase.value == 'exploration' and s.actor.experience_points == 120
