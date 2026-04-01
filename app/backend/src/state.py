"""Session-scoped mutable state store for the V1 prototype."""

from __future__ import annotations

import json
import os
import tempfile
import threading
import time
import uuid
from contextvars import ContextVar, Token
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field

from .agent.narrator import generate_opening_narration
from .models.action import Effect
from .models.state import (
    AbilityScores,
    Actor,
    BootstrapState,
    CharacterClass,
    CharacterCreateRequest,
    GamePhase,
    NarrativeHistoryEntry,
    Scene,
    ScenarioId,
    ScenarioPreset,
)

_CHARACTER_CREATION_SCENE_INIT = dict(
    id="character-creation-01",
    name="命运启程",
    description=(
        "你站在冒险开始前的门槛上。先决定自己的姓名、道路与天赋，"
        "随后故事才会真正展开。"
    ),
    actors=[],
)

_ADVENTURE_SCENE_INIT = dict(
    id="scenario-entry-01",
    name="Adventure Start",
    description="Your chosen adventure is about to begin.",
    actors=[],
)

_SCENARIO_PRESETS: dict[ScenarioId, ScenarioPreset] = {
    ScenarioId.DUNGEON_DELVE: ScenarioPreset(
        id=ScenarioId.DUNGEON_DELVE,
        name="地下城探索",
        tagline="坍塌遗迹下的黑暗召唤着第一批火光。",
        summary="深入一处失落遗迹，寻找目标并决定是掠取、封印还是生还离开。",
        atmosphere="潮湿、压抑、回声重叠，任何火光都像在吞噬黑暗。",
        objective="找到遗迹深处被标记的封存室，确认里面的古物是否仍然存在。",
        threat="不稳定的地形、巡游怪物，以及可能先一步抵达的掠夺者。",
        opening_hook="你刚抵达遗迹入口，最后一支先遣队留下的绳索还在风里轻晃。",
        gm_style="强调压迫感、资源消耗、未知空间与步步深入的风险。",
    ),
    ScenarioId.TOWN_COMMISSION: ScenarioPreset(
        id=ScenarioId.TOWN_COMMISSION,
        name="城镇任务",
        tagline="秩序表面平静，真正的问题埋在交易与耳语里。",
        summary="在边境城镇接受一项公开委托，沿着线索接触人物、交换情报并做出立场选择。",
        atmosphere="喧闹与戒备并存，街头消息流动很快，每个人都像知道一点内情。",
        objective="查清委托背后的真实风险，并决定先保护谁、相信谁。",
        threat="谎言、时限压力、势力冲突，以及失控后可能波及整座街区的后果。",
        opening_hook="你踏入镇中心时，公告牌前已经围着争论不休的人群。",
        gm_style="强调人际张力、线索推进、立场抉择与不断升级的社会压力。",
    ),
    ScenarioId.WILDERNESS_SURVIVAL: ScenarioPreset(
        id=ScenarioId.WILDERNESS_SURVIVAL,
        name="荒野求生",
        tagline="路已经断了，接下来每一步都要靠判断与意志换来。",
        summary="在荒野中挣扎前行，维持方向、体力与士气，同时处理逼近的自然或猎食威胁。",
        atmosphere="空旷、寒冷、风声不断，远处的地平线没有任何安全承诺。",
        objective="在补给耗尽前找到安全落脚点，确认下一段旅程仍可继续。",
        threat="恶劣天气、地形阻隔、饥饿疲劳，以及暗处跟随的掠食者。",
        opening_hook="你回头时，来路已经被天气和地势彻底吞没。",
        gm_style="强调环境压迫、旅途节奏、消耗感与求生判断。",
    ),
}

_CLASS_TEMPLATES: dict[CharacterClass, dict[str, object]] = {
    CharacterClass.WARRIOR: {
        "description": "A disciplined frontline warrior who trusts steel and grit.",
        "abilities": AbilityScores(**{
            "str": 15,
            "dex": 13,
            "con": 14,
            "int": 8,
            "wis": 12,
            "cha": 10,
        }),
        "hp": 12,
        "ac": 16,
    },
    CharacterClass.MAGE: {
        "description": "A learned spellcaster who shapes danger with study and will.",
        "abilities": AbilityScores(**{
            "str": 8,
            "dex": 13,
            "con": 12,
            "int": 15,
            "wis": 14,
            "cha": 10,
        }),
        "hp": 8,
        "ac": 12,
    },
    CharacterClass.ROGUE: {
        "description": "A quick-footed opportunist who survives by timing and nerve.",
        "abilities": AbilityScores(**{
            "str": 10,
            "dex": 15,
            "con": 13,
            "int": 12,
            "wis": 14,
            "cha": 8,
        }),
        "hp": 10,
        "ac": 14,
    },
}

_ENEMY_INIT = dict(
    id="goblin-01",
    name="Goblin Scout",
    abilities=AbilityScores(**{
        "str": 8,
        "dex": 14,
        "con": 10,
        "int": 10,
        "wis": 8,
        "cha": 8,
    }),
    proficiency_bonus=2,
    hp=7,
    hp_max=7,
    ac=12,
    description="A small, wiry goblin with a rusty dagger.",
)

_COMBAT_SCENE_INIT = dict(
    id="combat-01",
    name="Forest Ambush",
    description="A narrow forest path. A goblin emerges from the underbrush.",
    scenario_id=ScenarioId.WILDERNESS_SURVIVAL,
    scenario_name="荒野求生",
    atmosphere="林间伏击，草木间潜伏着突如其来的危险。",
    objective="活过眼前的袭击并重新夺回行动节奏。",
    threat="潜伏在灌木与阴影中的袭击者。",
    actors=["goblin-01"],
)

MAX_STORED_NARRATIVE_HISTORY = 50
DEFAULT_PROMPT_HISTORY_ENTRIES = 5
DEFAULT_PROMPT_HISTORY_CHARS = 1800
DEFAULT_SESSION_ID = "default-session"
SESSION_TTL_SECONDS = max(60, int(os.getenv("SESSION_TTL_SECONDS", "43200")))
SESSION_STORE_DIR = Path(
    os.getenv("SESSION_STATE_DIR", Path(tempfile.gettempdir()) / "huanjie-2-sessions")
)
SESSION_STORE_DIR.mkdir(parents=True, exist_ok=True)

_CURRENT_SESSION_ID: ContextVar[str | None] = ContextVar("current_session_id", default=None)
_SESSION_LOCK = threading.RLock()


class SessionData(BaseModel):
    session_id: str
    phase: GamePhase = GamePhase.CHARACTER_CREATION
    actor: Actor | None = None
    enemy: Actor = Field(default_factory=lambda: Actor(**_ENEMY_INIT))
    scenario: ScenarioPreset = Field(
        default_factory=lambda: _SCENARIO_PRESETS[ScenarioId.DUNGEON_DELVE]
    )
    scene: Scene = Field(default_factory=lambda: Scene(**_CHARACTER_CREATION_SCENE_INIT))
    narrative_history: list[NarrativeHistoryEntry] = Field(default_factory=list)
    updated_at: float = Field(default_factory=time.time)


_sessions: dict[str, SessionData] = {}


def set_current_session(session_id: str) -> Token[str | None]:
    return _CURRENT_SESSION_ID.set(session_id)


def reset_current_session(token: Token[str | None]) -> None:
    _CURRENT_SESSION_ID.reset(token)


def list_scenarios() -> list[ScenarioPreset]:
    return [preset.model_copy(deep=True) for preset in _SCENARIO_PRESETS.values()]


def get_scenario(scenario_id: ScenarioId | str | None = None) -> ScenarioPreset:
    resolved = ScenarioId(scenario_id or ScenarioId.DUNGEON_DELVE)
    return _SCENARIO_PRESETS[resolved].model_copy(deep=True)


def create_session(scenario_id: ScenarioId | str | None = None) -> BootstrapState:
    session_id = uuid.uuid4().hex
    with _SESSION_LOCK:
        session = _create_fresh_session(session_id, scenario_id=scenario_id)
        _sessions[session_id] = session
        _persist_session(session)
    return _bootstrap_from_session(session)


def session_exists(session_id: str) -> bool:
    try:
        _get_session(session_id, create_if_missing=False)
    except KeyError:
        return False
    return True


def get_bootstrap_state(session_id: str | None = None) -> BootstrapState:
    session = _get_session(_resolve_session_id(session_id), create_if_missing=True)
    return _bootstrap_from_session(session)


def require_bootstrap_state(session_id: str) -> BootstrapState:
    session = _get_session(session_id, create_if_missing=False)
    return _bootstrap_from_session(session)


def get_actor(session_id: str | None = None) -> Actor | None:
    return _get_session(_resolve_session_id(session_id), create_if_missing=True).actor


def get_enemy(session_id: str | None = None) -> Actor:
    return _get_session(_resolve_session_id(session_id), create_if_missing=True).enemy


def get_actor_by_id_or_name(target: str, session_id: str | None = None) -> Optional[Actor]:
    session = _get_session(_resolve_session_id(session_id), create_if_missing=True)
    target_lower = target.lower()
    for actor in [session.actor, session.enemy]:
        if actor is None:
            continue
        if actor.id.lower() == target_lower or actor.name.lower() == target_lower:
            return actor
    return None


def get_scene(session_id: str | None = None) -> Scene:
    return _get_session(_resolve_session_id(session_id), create_if_missing=True).scene


def get_narrative_history(session_id: str | None = None) -> list[NarrativeHistoryEntry]:
    session = _get_session(_resolve_session_id(session_id), create_if_missing=True)
    return list(session.narrative_history)


def append_narrative_history(
    entry: NarrativeHistoryEntry,
    session_id: str | None = None,
) -> None:
    resolved_session_id = _resolve_session_id(session_id)
    with _SESSION_LOCK:
        session = _get_session(resolved_session_id, create_if_missing=True)
        session.narrative_history = [
            *session.narrative_history,
            entry,
        ][-MAX_STORED_NARRATIVE_HISTORY:]
        _save_session(session)


def get_narrative_context(
    max_entries: int = DEFAULT_PROMPT_HISTORY_ENTRIES,
    max_chars: int = DEFAULT_PROMPT_HISTORY_CHARS,
    session_id: str | None = None,
) -> list[NarrativeHistoryEntry]:
    history = get_narrative_history(session_id=session_id)
    selected: list[NarrativeHistoryEntry] = []
    current_chars = 0

    for entry in reversed(history[-max_entries:]):
        entry_chars = len(entry.model_dump_json())
        if selected and current_chars + entry_chars > max_chars:
            break
        selected.append(entry)
        current_chars += entry_chars

    selected.reverse()
    return selected


def set_combat_scene(session_id: str | None = None) -> None:
    resolved_session_id = _resolve_session_id(session_id)
    with _SESSION_LOCK:
        session = _get_session(resolved_session_id, create_if_missing=True)
        actors = ["goblin-01"]
        if session.actor is not None:
            actors.insert(0, session.actor.id)
        session.scene = Scene(**{**_COMBAT_SCENE_INIT, "actors": actors})
        _save_session(session)


def has_character(session_id: str | None = None) -> bool:
    session = _get_session(_resolve_session_id(session_id), create_if_missing=True)
    return session.actor is not None and session.phase == GamePhase.ADVENTURE


def create_character(
    req: CharacterCreateRequest,
    session_id: str | None = None,
) -> BootstrapState:
    resolved_session_id = _resolve_session_id(session_id)
    with _SESSION_LOCK:
        session = _get_session(resolved_session_id, create_if_missing=True)
        template = _CLASS_TEMPLATES[req.character_class]
        hp = int(template["hp"])
        actor_id = f"{req.character_class.value}-{req.name.strip().lower().replace(' ', '-')}"

        session.actor = Actor(
            id=actor_id,
            name=req.name.strip(),
            character_class=req.character_class,
            abilities=template["abilities"],
            proficiency_bonus=2,
            hp=hp,
            hp_max=hp,
            ac=int(template["ac"]),
            description=str(template["description"]),
        )
        session.phase = GamePhase.ADVENTURE
        session.scenario = get_scenario(req.scenario_id)
        session.scene = _build_scenario_scene(session.scenario, actor_ids=[session.actor.id])
        session.enemy = Actor(**_ENEMY_INIT)
        session.narrative_history = _build_opening_history(
            actor=session.actor,
            scene=session.scene,
            scenario=session.scenario,
            provider=req.provider,
        )
        _save_session(session)
    return get_bootstrap_state(session_id=resolved_session_id)


def apply_effects(effects: list[Effect], session_id: str | None = None) -> None:
    resolved_session_id = _resolve_session_id(session_id)
    with _SESSION_LOCK:
        session = _get_session(resolved_session_id, create_if_missing=True)
        for effect in effects:
            _apply_one(session, effect)
        _save_session(session)


def reset_state(
    session_id: str | None = None,
    scenario_id: ScenarioId | str | None = None,
) -> BootstrapState:
    resolved_session_id = _resolve_session_id(session_id)
    with _SESSION_LOCK:
        session = _create_fresh_session(resolved_session_id, scenario_id=scenario_id)
        _sessions[resolved_session_id] = session
        _persist_session(session)
    return _bootstrap_from_session(session)


def _apply_one(session: SessionData, eff: Effect) -> None:
    actor = session.actor
    enemy = session.enemy
    scene = session.scene

    if actor is not None and eff.target in (actor.id, actor.name):
        if eff.field == "hp" and isinstance(eff.delta, int):
            session.actor = actor.model_copy(
                update={"hp": max(0, min(actor.hp_max, actor.hp + eff.delta))}
            )
        elif eff.field == "conditions_add" and isinstance(eff.delta, str):
            if eff.delta not in actor.conditions:
                session.actor = actor.model_copy(
                    update={"conditions": [*actor.conditions, eff.delta]}
                )
        elif eff.field == "conditions_remove" and isinstance(eff.delta, str):
            session.actor = actor.model_copy(
                update={"conditions": [c for c in actor.conditions if c != eff.delta]}
            )
        return

    if eff.target in (enemy.id, enemy.name):
        if eff.field == "hp" and isinstance(eff.delta, int):
            session.enemy = enemy.model_copy(
                update={"hp": max(0, min(enemy.hp_max, enemy.hp + eff.delta))}
            )
        elif eff.field == "conditions_add" and isinstance(eff.delta, str):
            if eff.delta not in enemy.conditions:
                session.enemy = enemy.model_copy(
                    update={"conditions": [*enemy.conditions, eff.delta]}
                )
        elif eff.field == "conditions_remove" and isinstance(eff.delta, str):
            session.enemy = enemy.model_copy(
                update={"conditions": [c for c in enemy.conditions if c != eff.delta]}
            )
        return

    if eff.target == scene.id and eff.field == "time" and isinstance(eff.delta, int):
        session.scene = scene.model_copy(update={"time": scene.time + eff.delta})


def _bootstrap_from_session(session: SessionData) -> BootstrapState:
    return BootstrapState(
        session_id=session.session_id,
        phase=session.phase,
        actor=session.actor,
        scenario=session.scenario,
        scene=session.scene,
        narrative_history=list(session.narrative_history),
    )


def _resolve_session_id(session_id: str | None) -> str:
    return session_id or _CURRENT_SESSION_ID.get() or DEFAULT_SESSION_ID


def _session_file(session_id: str) -> Path:
    return SESSION_STORE_DIR / f"{session_id}.json"


def _create_fresh_session(
    session_id: str,
    scenario_id: ScenarioId | str | None = None,
) -> SessionData:
    scenario = get_scenario(scenario_id)
    return SessionData(
        session_id=session_id,
        scenario=scenario,
        scene=Scene(**_CHARACTER_CREATION_SCENE_INIT),
    )


def _build_scenario_scene(scenario: ScenarioPreset, actor_ids: list[str]) -> Scene:
    return Scene(
        **{
            **_ADVENTURE_SCENE_INIT,
            "id": f"{scenario.id.value}-entry",
            "name": scenario.name,
            "description": scenario.opening_hook,
            "scenario_id": scenario.id,
            "scenario_name": scenario.name,
            "atmosphere": scenario.atmosphere,
            "objective": scenario.objective,
            "threat": scenario.threat,
            "actors": actor_ids,
        }
    )


def _build_opening_history(
    actor: Actor,
    scene: Scene,
    scenario: ScenarioPreset,
    provider: str = "",
) -> list[NarrativeHistoryEntry]:
    opening = generate_opening_narration(
        actor=actor,
        scene=scene,
        scenario=scenario,
        provider=provider,
    )
    return [
        NarrativeHistoryEntry(
            action_summary="开场叙事",
            resolution_summary={
                "resolution_type": "auto_success",
                "outcome": "success",
                "event_type": "opening",
            },
            narration_summary=" ".join(
                [opening.action_result, opening.scene_progression, opening.gm_prompt]
            )[:400],
            narration=opening.action_result,
            scene_progression=opening.scene_progression,
            gm_prompt=opening.gm_prompt,
            created_at=int(time.time() * 1000),
        )
    ]


def _get_session(session_id: str, create_if_missing: bool) -> SessionData:
    with _SESSION_LOCK:
        session = _sessions.get(session_id)
        if session is None:
            session = _load_session(session_id)
            if session is not None:
                _sessions[session_id] = session

        if session is None:
            if not create_if_missing:
                raise KeyError(session_id)
            session = _create_fresh_session(session_id)
            _sessions[session_id] = session
            _persist_session(session)
            return session

        if _is_expired(session):
            _delete_session(session_id)
            if not create_if_missing:
                raise KeyError(session_id)
            session = _create_fresh_session(session_id)
            _sessions[session_id] = session
            _persist_session(session)
            return session

        session.updated_at = time.time()
        _persist_session(session)
        return session


def _load_session(session_id: str) -> SessionData | None:
    session_file = _session_file(session_id)
    if not session_file.exists():
        return None

    data = json.loads(session_file.read_text(encoding="utf-8"))
    session = SessionData.model_validate(data)
    if _is_expired(session):
        session_file.unlink(missing_ok=True)
        return None
    return session


def _save_session(session: SessionData) -> None:
    session.updated_at = time.time()
    _persist_session(session)


def _persist_session(session: SessionData) -> None:
    _session_file(session.session_id).write_text(
        json.dumps(
            session.model_dump(mode="json", by_alias=True),
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def _delete_session(session_id: str) -> None:
    _sessions.pop(session_id, None)
    _session_file(session_id).unlink(missing_ok=True)


def _is_expired(session: SessionData) -> bool:
    return (time.time() - session.updated_at) > SESSION_TTL_SECONDS
