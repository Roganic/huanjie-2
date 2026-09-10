"""Art stays portable and cannot change rules or create paid work."""
import base64
import json
import struct
import pytest
from pydantic import ValidationError
from src.content.schema import ModulePack
from src.content.store import builtin
from src.content.visuals import VisualAsset, ModuleVisuals, ThemePack
from tests.conftest import create_session_and_character


PNG = 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jB1sAAAAASUVORK5CYII='


def asset(data=PNG):
    return {'name': 'test.png', 'source': 'upload', 'data': data}


def illustrated_pack():
    document = builtin().model_dump(mode='json')
    scene = document['starting_scene_id']
    document['id'] = 'visual-test'
    document['visuals'] = {'theme': {'id': 'test-theme', 'name': '独立主题', 'preset': 'midnight'},
        'assets': {'test': asset()}, 'scenes': {scene: {'asset_id': 'test'}}, 'cover': {'asset_id': 'test'}}
    return document


def test_legacy_pack_and_art_cannot_mutate_rules():
    legacy = builtin().model_dump(mode='json'); legacy.pop('visuals')
    assert ModulePack.model_validate(legacy).visuals is None
    edited = illustrated_pack()
    for field in ('scenes', 'characters', 'items', 'quests', 'events'):
        assert ModulePack.model_validate(edited).model_dump(mode='json')[field] == legacy[field]
    edited['visuals']['attack_bonus'] = 999
    with pytest.raises(ValidationError):
        ModulePack.model_validate(edited)


def test_portable_theme_and_asset_references():
    theme = ThemePack(assets={'portrait': asset()}, defaults={'portrait': {'asset_id': 'portrait'}})
    assert ThemePack.model_validate_json(theme.model_dump_json()) == theme
    with pytest.raises(ValidationError):
        ModuleVisuals(assets={'one': asset()}, player={'asset_id': 'missing'})
    document = illustrated_pack(); document['visuals']['scenes']['missing-place'] = {}
    with pytest.raises(ValidationError):
        ModulePack.model_validate(document)


def test_reject_executable_external_oversized_and_mismatched_images():
    for bad in ('https://example.com/a.png', 'data:image/svg+xml,<svg/>', PNG.replace('png', 'jpeg'), 'data:image/png;base64,bad!'):
        with pytest.raises(ValidationError):
            VisualAsset(**asset(bad))
    raw = bytearray(base64.b64decode(PNG.split(',')[1])); raw[16:20] = struct.pack('>I', 99999)
    with pytest.raises(ValidationError):
        VisualAsset(**asset('data:image/png;base64,' + base64.b64encode(raw).decode()))
    # Individually bounded files still cannot make an unbounded portable pack.
    padded = PNG.split(',')[0] + ',' + base64.b64encode(base64.b64decode(PNG.split(',')[1]) + b'\0' * 160000).decode()
    with pytest.raises(ValidationError):
        ModuleVisuals(assets={str(i): asset(padded) for i in range(4)})


@pytest.mark.asyncio
async def test_import_activation_save_and_restore_keep_art_out_of_model_context(client):
    from src import state
    from src.gm.context import public_context, catalogue
    original = await create_session_and_character(client)
    headers = {'X-Session-Id': original}
    before = (await client.get('/state', headers=headers)).json()
    document = illustrated_pack()
    assert (await client.post('/modules/import', json=document)).status_code == 200
    exported = (await client.get('/modules/visual-test')).json()
    assert exported['visuals']['assets']['test']['data'] == PNG
    activated = await client.post('/modules/activate', headers=headers, json={'module_id': 'visual-test'})
    sid = activated.json()['session_id']; active_headers = {'X-Session-Id': sid}
    response = await client.get('/modules/visuals', headers=active_headers)
    assert response.status_code == 200 and response.json()['theme']['preset'] == 'midnight'
    save = await client.post('/save', headers=active_headers, json={})
    assert save.status_code == 200
    saved = (await client.get('/saves', headers=active_headers)).json()['saves'][0]
    loaded = await client.post('/load', headers=active_headers, json={'save_id': saved['save_id']})
    assert loaded.status_code == 200
    restored = await client.get('/modules/visuals', headers={'X-Session-Id': loaded.json()['session_id']})
    assert restored.json()['assets']['test']['data'] == PNG
    session = state._get_session(sid, False)
    context = json.dumps(public_context(session, catalogue(session)))
    assert 'base64' not in context and 'test-theme' not in context
    after = (await client.get('/state', headers=headers)).json()
    assert before['actor'] == after['actor'] and before['scene'] == after['scene']


@pytest.mark.asyncio
async def test_image_service_is_disabled_without_order_or_charge(client):
    assert (await client.get('/images/capabilities')).json()['enabled'] is False
    assert (await client.post('/images/quotes', json={'prompt': 'a tavern', 'slot': 'tavern', 'theme_id': 'western-journal'})).status_code == 503
    assert (await client.post('/images/jobs', json={'quote_id': 'made-up', 'idempotency_key': 'fake-acceptance-key'})).status_code == 503
    assert (await client.get('/images/jobs/made-up')).status_code == 404


def test_preset_layout_and_builtin_art_are_bounded_presentation():
    from src.content.visuals import ArtSlot
    document = builtin().model_dump(mode='json')
    document['visuals']['map_layout']['not-a-scene'] = {'x': 200, 'y': 200}
    with pytest.raises(ValidationError):
        ModulePack.model_validate(document)
    with pytest.raises(ValidationError):
        ArtSlot(builtin='../../private')
    document = builtin().model_dump(mode='json')
    document['visuals']['map_layout']['tavern-01']['x'] = 100000
    with pytest.raises(ValidationError):
        ModulePack.model_validate(document)


@pytest.mark.asyncio
async def test_old_stock_save_gets_art_without_replacing_content_or_custom_theme(client):
    from src import state
    sid = await create_session_and_character(client)
    headers = {'X-Session-Id': sid}
    session = state._get_session(sid, False)
    session.content_pack = builtin().model_copy(deep=True)
    session.content_pack.visuals = None
    session.content_pack.scenes['tavern-01'].description = '旧存档的独立场景内容'
    snapshot = session.content_pack.model_dump(mode='json')
    result = (await client.get('/modules/visuals', headers=headers)).json()
    assert result['characters']['tavern-keeper-01']['builtin'] == 'marcus'
    assert result['scenes']['vault-01']['builtin'] == 'ancient-vault'
    assert session.content_pack.model_dump(mode='json') == snapshot
    session.content_pack.visuals = ModuleVisuals(theme=ThemePack(id='custom', preset='neutral', illustrated=False))
    result = (await client.get('/modules/visuals', headers=headers)).json()
    assert result['theme']['id'] == 'custom' and result['scenes'] == {}
