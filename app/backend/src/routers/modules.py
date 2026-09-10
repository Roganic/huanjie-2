"""Module documents, validation, import and isolated activation."""
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from typing import Literal
from ..content import store
from ..content.schema import ModulePack
from ..content import authoring
from ..content.runtime import active_view, catalog_view
from .. import state
from ..content.visuals import ThemePack, ModuleVisuals, ImageGenerationRequest, ImageJobRequest

router = APIRouter(tags=["modules"])


def session_for(request):
    sid = request.headers.get("X-Session-Id") or request.query_params.get("session_id") or state.DEFAULT_SESSION_ID
    try:
        return state._get_session(sid, False)
    except KeyError as exc:
        raise HTTPException(404, "会话不存在。") from exc


@router.get("/modules")
def list_modules(request: Request):
    session = session_for(request)
    with state._SESSION_LOCK:
        active = active_view(session)
        return {"modules": [catalog_view(pack, active["module_id"]) for pack in store.packs()], "active_module": active}


@router.get("/modules/schema")
def module_schema():
    return ModulePack.model_json_schema(by_alias=True)


@router.get('/modules/visuals')
def module_visuals(request: Request):
    with state._SESSION_LOCK:
        pack = store.for_session(session_for(request))
        visuals = pack.visuals
        # Presentation-only fallback for existing stock adventures; no save rewrite.
        if visuals is None and pack.id == store.builtin().id:
            visuals = store.builtin().visuals.model_copy(deep=True) if store.builtin().visuals else None
            if visuals:
                for group in ('scenes', 'characters', 'items', 'map', 'map_layout'):
                    known = getattr(pack, 'scenes' if group in ('map', 'map_layout') else group)
                    setattr(visuals, group, {k:v for k,v in getattr(visuals, group).items() if k in known})
        return (visuals or ModuleVisuals()).model_dump(mode='json')


@router.post('/themes/validate')
def validate_theme(theme: ThemePack):
    return theme.model_dump(mode='json')


@router.get('/images/capabilities')
def image_capabilities():
    return {'enabled': False, 'billing_unit': 'image', 'currency': 'CNY',
            'reason': 'AI 生图尚未开放；默认素材和上传免费可用。'}


@router.post('/images/quotes')
def image_quote(req: ImageGenerationRequest):
    raise HTTPException(503, 'AI 生图尚未开放，未创建订单或扣费。')


@router.post('/images/jobs')
def image_job(req: ImageJobRequest):
    raise HTTPException(503, 'AI 生图尚未开放，未创建订单或扣费。')


@router.get('/images/jobs/{job_id}')
def image_job_status(job_id: str):
    raise HTTPException(404, '生图任务不存在。')


@router.post("/modules/validate")
def validate_module(document: dict):
    return authoring.review(document)


class ParseRequest(BaseModel):
    source: str = Field(max_length=2_000_000)
    format: str = "json"


@router.post("/modules/parse")
async def parse_module(req: ParseRequest):
    if req.format == 'text':
        if not 20 <= len(req.source.strip()) <= 60000:
            return {'valid': False, 'draft': None, 'issues': [{'loc': ['source'], 'type': 'source_length', 'msg': '故事请写 20–60000 字，包含人物、地点、目标与结局。'}]}
        return await authoring.ModelStoryParser().parse(req.source)
    if req.format == 'story_graph':
        return authoring.review_pending({'format': req.format, 'source': req.source})
    if req.format != "json":
        return {"valid": False, "draft": None, "issues": [{"loc": ["source"], "type": "unsupported_format", "msg": "请选择故事文本或 JSON 格式。"}]}
    try:
        document = store.parse_json(req.source)
        if not isinstance(document, dict):
            raise ValueError("模组根节点必须是对象。")
        result = validate_module(document)
        return {**result, "draft": document}
    except ValueError as exc:
        return {"valid": False, "draft": None, "issues": [{"loc": ["source"], "type": "invalid_json", "msg": str(exc)}]}


class RepairRequest(BaseModel):
    source: str = Field(min_length=20, max_length=60000)
    outline: str = Field(max_length=2_000_000)
    assumptions: list[str] = Field(default_factory=list, max_length=30)
    questions: list[str] = Field(default_factory=list, max_length=30)


@router.post('/modules/repair')
async def repair_module(req: RepairRequest):
    try:
        outline = store.parse_json(req.outline)
        if not isinstance(outline, dict): raise ValueError('故事结构必须是对象。')
    except ValueError as exc:
        return {'valid': False, 'draft': None, 'issues': [{'loc': ['outline'], 'type': 'invalid_json', 'msg': str(exc)}]}
    return await authoring.ModelStoryParser().parse(req.source, previous={'outline': outline,
        'assumptions': req.assumptions, 'questions': req.questions})


class PendingDocument(BaseModel):
    format: Literal['json', 'story_graph']
    source: str = Field(max_length=2_000_000)


class DraftRequest(BaseModel):
    id: str | None = Field(default=None, pattern=r'^[0-9a-f]{32}$')
    source: str = Field(default='', max_length=60000)
    document: dict
    assumptions: list[str] = Field(default_factory=list, max_length=30)
    questions: list[str] = Field(default_factory=list, max_length=30)
    coverage: list[authoring.SourceMapping] = Field(default_factory=list, max_length=30)
    pending: PendingDocument | None = None


@router.get('/modules/drafts')
def drafts():
    return {'drafts': authoring.list_drafts()}


@router.post('/modules/drafts')
def save_draft(req: DraftRequest):
    if len(str(req.document)) > 2_000_000:
        raise HTTPException(413, '草稿过大。')
    return authoring.save_draft(req.document, req.source, req.id, req.assumptions, req.questions,
                               req.pending.model_dump() if req.pending else None,
                               [mapping.model_dump() for mapping in req.coverage])


@router.post("/modules/import")
def import_module(document: ModulePack):
    existing = store.get_pack(document.id)
    if existing is not None and existing.model_dump(mode='json') == document.model_dump(mode='json'):
        return {"success": True, "module": catalog_view(existing), "already_installed": True}
    try:
        store.install(document)
    except (ValueError, FileExistsError) as exc:
        raise HTTPException(409, str(exc)) from exc
    return {"success": True, "module": catalog_view(document)}


@router.get("/modules/active")
def active_module(request: Request):
    with state._SESSION_LOCK:
        return {"active": True, **active_view(session_for(request))}


class ActivateRequest(BaseModel):
    module_id: str


@router.post("/modules/activate")
def activate_module(req: ActivateRequest, request: Request):
    pack = store.get_pack(req.module_id)
    if pack is None:
        raise HTTPException(404, "模组不存在。")
    with state._SESSION_LOCK:
        source = session_for(request)
        if source.actor is None:
            raise HTTPException(409, "请先创建角色。")
        from ..game.lifecycle import play_status
        if not play_status(source)["can_restart"]:
            raise HTTPException(409, "请先结束当前战斗。")
        # A new adventure never overwrites the current character/world/save.
        fresh = state.create_session()
        target = state._get_session(fresh.session_id, False)
        target.content_pack = pack.model_copy(deep=True)
        from ..models.state import CharacterCreateRequest
        state.create_character(CharacterCreateRequest(name=source.actor.name, character_class=source.actor.character_class), target.session_id)
        return {"success": True, "session_id": target.session_id, "active_module": active_view(target)}


@router.post("/modules/{module_id}/activate")
def activate_by_id(module_id: str, request: Request):
    return activate_module(ActivateRequest(module_id=module_id), request)


@router.get("/modules/{module_id}")
def get_module(module_id: str):
    pack = store.get_pack(module_id)
    if pack is None:
        raise HTTPException(404, "模组不存在。")
    return pack.model_dump(mode="json", by_alias=True)
