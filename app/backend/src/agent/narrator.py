"""Narrative generation for game actions.

Provides immersive, GM-style narrative text for game actions.
Falls back to template narratives when API is unavailable.

Hard Constraint Principle:
- Rule engine results (success/failure, damage values, state changes) are INVIOLABLE facts
- AI narrative MUST respect these facts and cannot contradict them
- The prompt explicitly separates "ESTABLISHED FACTS" from "NARRATIVE SPACE"
"""

from __future__ import annotations

import json
import logging
import os
from typing import Optional

from pydantic import BaseModel

from ..models.action import (
    ActionRequest,
    Effect,
    Outcome,
)
from ..models.state import Actor, NarrativeHistoryEntry, Scene
from .providers import get_provider
from .resolution_constraints import (
    NarrationConstraintContext,
    ValidationResult,
    build_hard_constraints,
    build_narrative_prompt,
    detect_unauthorized_numeric_declarations,
    find_contradictions,
    validate_narrative_for_overreach,
)

# Backward-compatible export for existing scripts/tests.
KIMI_API_KEY = os.getenv("KIMI_API_KEY", "")
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Prompt Templates
# ---------------------------------------------------------------------------

NARRATIVE_SYSTEM_PROMPT = """你是一位经验丰富的奇幻桌游主持人（GM）。
你的任务是用**中文**为玩家的行动撰写沉浸式叙事描述，并主动推进场景发展。
所有输出必须使用中文，包括 action_result、scene_progression 和 gm_prompt 三个字段。

CRITICAL RULE - HARD CONSTRAINTS (绝对不可违反):
The "【硬约束区 / HARD CONSTRAINTS】" section in the prompt contains ESTABLISHED FACTS determined by the rule engine.
These are ABSOLUTE and CANNOT be changed, ignored, or contradicted in your narrative:
- If outcome is "失败" (failure), you CANNOT describe it as success or hitting
- If damage is "8", you MUST describe damage consistent with 8 HP loss
- If target HP changes to "5", you CANNOT say the target was defeated
- State changes (conditions, HP, resources) are FACTS, not suggestions

ABSOLUTE PROHIBITION - 数值权威禁止 (NUMERIC AUTHORITY RESTRICTION):
You are STRICTLY FORBIDDEN from announcing or modifying any numeric values in your narrative:
- NEVER say "HP becomes", "HP 变为", "生命值变为" or any HP modification
- NEVER say "You gain", "你获得", "你得到" followed by any numeric resource
- NEVER say "You lose", "你失去", "你损失" followed by any numeric resource
- NEVER announce specific damage numbers like "deals 5 damage" or "造成 5 点伤害"
- NEVER announce healing amounts like "restores 3 HP" or "恢复 3 点生命"
- NEVER state new HP totals like "now has 5 HP" or "现在剩下 5 点生命"

The rule engine ALONE has authority over all numeric values. Your job is ONLY to describe:
- Sensory details (what characters see, hear, feel)
- Emotional reactions and dramatic tension
- Environmental changes and atmospheric effects
- Strategic implications and narrative consequences

VIOLATION CONSEQUENCE: Any output containing unauthorized numeric declarations will be rejected.

叙事规则：
- 使用第二人称（"你"）或第三人称有限视角
- 语言生动、有氛围感，符合奇幻冒险风格
- 输出分为三个部分：
  1. action_result：描述行动、结果及直接后果
  2. scene_progression：描述行动后场景的即时反应或环境变化
  3. gm_prompt：主动向玩家抛出下一个节拍——具体的提示、压力或事件
- 每部分保持在1个简短段落内
- 结合近期会话历史，让场景持续演进而非重置
- 聚焦感官细节：角色看到、听到、感受到什么
- 战斗场景：描述紧张感、兵器碰撞、打击感
- 技能检定：描述努力、挣扎、结果
- 绝对不能违反硬约束——它们是事实
- 不要使用系统术语如"投骰"、"DC"、"修正值"、"检定"（直接描述结果）
- 不要出戏或提及游戏机制
- 只返回合法 JSON，包含 "action_result"、"scene_progression"、"gm_prompt" 三个键

语气：戏剧性但不夸张，扎实的奇幻冒险风格。"""


class NarrationBundle(BaseModel):
    """Structured narration result for action and proactive scene advancement."""

    action_result: str
    scene_progression: str
    gm_prompt: str


def _build_hard_constraints(
    outcome: Outcome,
    check_result: Optional[dict] = None,
    attack_result: Optional[dict] = None,
    saving_throw_result: Optional[dict] = None,
    effects: Optional[list[Effect]] = None,
    actor: Optional[Actor] = None,
    target: Optional[Actor] = None,
) -> list[str]:
    """Backward-compatible wrapper around centralized constraint mapping."""
    return build_hard_constraints(
        NarrationConstraintContext(
            outcome=outcome,
            check_result=check_result,
            attack_result=attack_result,
            saving_throw_result=saving_throw_result,
            effects=effects,
            actor=actor,
            target=target,
        )
    )


def _build_narrative_prompt(
    req: ActionRequest,
    actor: Actor,
    scene: Scene,
    outcome: Outcome,
    check_result: Optional[dict] = None,
    attack_result: Optional[dict] = None,
    saving_throw_result: Optional[dict] = None,
    effects: Optional[list[Effect]] = None,
    target: Optional[Actor] = None,
    narrative_history: Optional[list[NarrativeHistoryEntry]] = None,
) -> str:
    """Backward-compatible wrapper around centralized prompt building."""
    return build_narrative_prompt(
        req=req,
        actor=actor,
        scene=scene,
        context=NarrationConstraintContext(
            outcome=outcome,
            check_result=check_result,
            attack_result=attack_result,
            saving_throw_result=saving_throw_result,
            effects=effects,
            actor=actor,
            target=target,
        ),
        narrative_history=narrative_history,
    )


# ---------------------------------------------------------------------------
# Fallback Templates (when API is unavailable)
# ---------------------------------------------------------------------------

def _class_ability_flavor(actor: Actor) -> str:
    """Return a class-and-ability-aware narrative flavor snippet."""
    cls = actor.character_class.value if actor.character_class else "adventurer"
    if cls == "warrior":
        return f"作为战士，{actor.name}的蛮力与钢铁意志"
    if cls == "mage":
        return f"身为法师，{actor.name}的知识与专注"
    if cls == "rogue":
        return f"身为盗贼，{actor.name}的敏捷与机警"
    return f"{actor.name}"


def _fallback_action_result(
    req: ActionRequest,
    actor: Actor,
    scene: Scene,
    outcome: Outcome,
    attack_result: Optional[dict] = None,
    check_result: Optional[dict] = None,
) -> str:
    """Generate a template fallback narrative when API is unavailable."""

    if attack_result:
        # Combat fallback
        weapon = attack_result.get("weapon", "weapon")
        target = attack_result.get("target", "enemy")

        if outcome == Outcome.SUCCESS:
            damage = attack_result.get("damage")
            if damage:
                return (
                    f"{_class_ability_flavor(actor)}让{weapon}命中了{target}。"
                    f"冲击回荡在空气中，伤害切实落到了对方身上。"
                )
            else:
                return (
                    f"{actor.name}挥舞着{weapon}划过一道弧线命中了{target}，"
                    f"让对方措手不及。"
                )
        else:
            # Miss - include "miss" for test compatibility
            return (
                f"{actor.name} attacks {target} with the {weapon}, "
                f"but misses as the {target} dances aside at the last moment."
            )

    # Skill/ability check fallback with character flavor
    flavor = _class_ability_flavor(actor)
    if check_result and check_result.get("skill"):
        skill = check_result.get("skill", "")
        ability = check_result.get("ability", "")
        ability_flavor = {
            "str": "蛮力",
            "dex": "敏捷身手",
            "con": "坚韧体魄",
            "int": "渊博学识",
            "wis": "敏锐感知",
            "cha": "迷人魅力",
        }.get(ability, "能力")
        if outcome == Outcome.SUCCESS:
            return (
                f"{flavor}派上了用场。凭借{ability_flavor}，{actor.name}"
                f"顺利完成了{req.intent}，达成了预期的结果。"
            )
        else:
            return (
                f"尽管{flavor}不俗，{actor.name}在尝试{req.intent}时"
                f"还是差了一点运气，{ability_flavor}没能扭转局面。"
            )

    # General action fallback
    if outcome == Outcome.SUCCESS:
        return (
            f"{flavor}让{actor.name}顺利完成了{req.intent}，"
            f"努力得到了回报。"
        )
    else:
        return (
            f"{actor.name}尝试{req.intent}，但时运不济，"
            f"努力未能换来成功。"
        )


def _fallback_scene_progression(
    req: ActionRequest,
    actor: Actor,
    scene: Scene,
    outcome: Outcome,
    attack_result: Optional[dict] = None,
) -> str:
    """Return a deterministic scene progression when AI is unavailable."""
    if attack_result:
        target = attack_result.get("target", "enemy")
        if outcome == Outcome.SUCCESS:
            return (
                f"{target}在冲击下踉跄后退，{scene.name}中的空气因交锋而紧绷。"
                f"你可以趁势追击，也可以观察周围还有谁会加入战局。"
            )
        return (
            f"{target}稳住身形，战斗在瞬息间重新摆开架势，附近的动静变得紧张起来。"
            f"你可以调整位置、提防反击，或者出声控制下一步的交锋。"
        )

    if outcome == Outcome.SUCCESS:
        flags_hint = ""
        if scene.flags:
            latest_flag = scene.flags[-1]
            flag_desc = {
                "npc_persuaded": "周围的气氛因为刚刚的交涉而缓和了一些。",
                "door_opened": "敞开的门让新的路径成为可能。",
                "player_hidden": "你融入阴影中，周围环境似乎还没有察觉你的存在。",
                "secrets_found": "新发现的秘密改变了你对这里的认知。",
                "magic_identified": "被识别的魔法在空气中留下一丝异样的余韵。",
            }.get(latest_flag, "场景中的某些东西已经悄然改变。")
            flags_hint = f" {flag_desc}"
        return (
            f"{scene.name}中泛起一阵回应的涟漪，这一刻定格成了新的形状。"
            f"{flags_hint}你可以立即抓住机会、观察他人反应，或者探查环境的变化。"
        )

    return (
        f"挫折为世界留下了一个回应的空档；声音、目光和压力在{actor.name}周围悄然转移。"
        f"你可以重新评估房间、回应任何NPC的反应，或者在时机关闭前尝试新的角度。"
    )


def _build_history_callback(narrative_history: Optional[list[NarrativeHistoryEntry]]) -> str:
    if not narrative_history:
        return ""

    latest = narrative_history[-1]
    seed = latest.narration_summary or latest.action_summary
    compact = seed.replace("\n", " ").strip()
    if len(compact) > 120:
        compact = compact[:117].rstrip() + "..."

    if len(narrative_history) >= 3:
        return f" The scene is already carrying momentum from several exchanges, especially {compact}"
    return f" The room is still reacting to the last beat: {compact}"


def _fallback_gm_prompt(
    req: ActionRequest,
    actor: Actor,
    scene: Scene,
    outcome: Outcome,
    attack_result: Optional[dict] = None,
    check_result: Optional[dict] = None,
    narrative_history: Optional[list[NarrativeHistoryEntry]] = None,
) -> str:
    history_callback = _build_history_callback(narrative_history)
    time_pressure = (
        f" {scene.name}的时间已经推进到第{scene.time}拍。"
        if scene.time
        else ""
    )

    if attack_result:
        target = attack_result.get("target", "enemy")
        if outcome == Outcome.SUCCESS:
            return (
                f"{target}踉跄着但没有离开战场；混战中的某个东西即将回应你的优势。"
                f"{history_callback}{time_pressure} 你要追击受伤的敌人、撤退 reposition，还是应对其他动向？"
            )
        return (
            f"{target}已经看穿了你的路线，战斗似乎要反噬你了。"
            f"{history_callback}{time_pressure} 在反击到来之前，你打算怎么做？"
        )

    # Build contextual prompt based on check result and scene state
    check_hint = ""
    if check_result:
        skill = check_result.get("skill")
        ability = check_result.get("ability", "")
        total = check_result.get("total", 0)
        dc = check_result.get("dc", 0)
        if skill == "persuasion" and outcome == Outcome.SUCCESS:
            check_hint = " NPC的态度已经软化，现在可能是进一步交涉或提出请求的好时机。"
        elif skill == "stealth" and outcome == Outcome.SUCCESS:
            check_hint = " 你目前处于隐匿状态，可以趁机移动、偷袭，或者保持隐蔽观察。"
        elif skill == "perception" and outcome == Outcome.SUCCESS:
            check_hint = " 你的察觉让你注意到了常人忽略的细节，不妨去调查那个发现。"
        elif skill == "arcana" and outcome == Outcome.SUCCESS:
            check_hint = " 魔法的本质已经向你揭示，你可以决定如何利用这一知识。"
        elif ability == "str" and outcome == Outcome.SUCCESS:
            check_hint = " 你的力量突破了一道障碍，接下来要利用这条新路做什么？"
        elif outcome == Outcome.FAILURE:
            margin = dc - total
            if margin >= 5:
                check_hint = " 这次失败相当明显，周围的反应可能不会对你有利。"
            else:
                check_hint = " 你几乎就要成功了，也许再尝试一次，或者换一个方法？"

    if outcome == Outcome.SUCCESS:
        return (
            f"{scene.name}中出现了一个新的机会窗口，但它不会一直敞开。"
            f"{check_hint}{history_callback}{time_pressure} 你要立即利用这个机会、向做出反应的人发问，还是检查刚刚发生了什么变化？"
        )

    return (
        f"失败的尝试让场景获得了反推的许可。"
        f"{check_hint}{history_callback}{time_pressure} 什么最先引起你的注意：一个NPC的反应、环境的变化，还是一个新的策略？"
    )


def _fallback_narration_bundle(
    req: ActionRequest,
    actor: Actor,
    scene: Scene,
    outcome: Outcome,
    attack_result: Optional[dict] = None,
    check_result: Optional[dict] = None,
    narrative_history: Optional[list[NarrativeHistoryEntry]] = None,
) -> NarrationBundle:
    return NarrationBundle(
        action_result=_fallback_action_result(req, actor, scene, outcome, attack_result, check_result),
        scene_progression=_fallback_scene_progression(req, actor, scene, outcome, attack_result),
        gm_prompt=_fallback_gm_prompt(req, actor, scene, outcome, attack_result, check_result, narrative_history),
    )


# ---------------------------------------------------------------------------
# API Client
# ---------------------------------------------------------------------------

def _parse_narration_bundle(content: str) -> Optional[NarrationBundle]:
    """Parse the model response into the required narration bundle."""
    raw = content.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1] if "\n" in raw else raw
        raw = raw.rsplit("```", 1)[0].strip()

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None

    action_result = str(data.get("action_result", "")).strip()
    scene_progression = str(data.get("scene_progression", "")).strip()
    gm_prompt = str(data.get("gm_prompt", "")).strip()
    if not action_result or not scene_progression or not gm_prompt:
        return None

    return NarrationBundle(
        action_result=action_result,
        scene_progression=scene_progression,
        gm_prompt=gm_prompt,
    )


def _narration_respects_constraints(
    narration: NarrationBundle,
    outcome: Outcome,
    attack_result: Optional[dict] = None,
    check_result: Optional[dict] = None,
    saving_throw_result: Optional[dict] = None,
    effects: Optional[list[Effect]] = None,
    actor: Optional[Actor] = None,
    target: Optional[Actor] = None,
) -> bool:
    """Backward-compatible boolean helper for contradiction validation."""
    reasons = find_contradictions(
        action_result=narration.action_result,
        scene_progression=narration.scene_progression,
        context=NarrationConstraintContext(
            outcome=outcome,
            check_result=check_result,
            attack_result=attack_result,
            saving_throw_result=saving_throw_result,
            effects=effects,
            actor=actor,
            target=target,
        ),
    )
    return not reasons


async def _call_kimi_api(prompt: str) -> Optional[NarrationBundle]:
    provider = get_provider("kimi")
    if provider is None:
        return None
    generated = await provider.generate(NARRATIVE_SYSTEM_PROMPT, prompt)
    return _parse_narration_bundle(generated) if generated else None


async def _call_openai_api(prompt: str) -> Optional[NarrationBundle]:
    provider = get_provider("openai")
    if provider is None:
        return None
    generated = await provider.generate(NARRATIVE_SYSTEM_PROMPT, prompt)
    return _parse_narration_bundle(generated) if generated else None


def generate_narration(
    req: ActionRequest,
    actor: Actor,
    scene: Scene,
    outcome: Outcome,
    check_result: Optional[dict] = None,
    attack_result: Optional[dict] = None,
    saving_throw_result: Optional[dict] = None,
    effects: Optional[list[Effect]] = None,
    target: Optional[Actor] = None,
    narrative_history: Optional[list[NarrativeHistoryEntry]] = None,
) -> NarrationBundle:
    """Generate structured narrative text for an action resolution.
    
    This is a synchronous wrapper around the async API call.
    Falls back to template narrative if API is unavailable.
    
    Hard constraints (outcome, damage, state changes) are injected into the prompt
    to ensure AI narrative respects rule engine results.
    
    Args:
        req: The action request
        actor: The acting character
        scene: The current scene
        outcome: Success or failure
        check_result: Optional check details
        attack_result: Optional attack details
        effects: Optional list of state change effects
        target: Optional target actor (for combat context)
        
    Returns:
        Narration bundle for action result and scene progression
    """
    context = NarrationConstraintContext(
        outcome=outcome,
        check_result=check_result,
        attack_result=attack_result,
        saving_throw_result=saving_throw_result,
        effects=effects,
        actor=actor,
        target=target,
    )
    prompt = _build_narrative_prompt(
        req=req,
        actor=actor,
        scene=scene,
        outcome=outcome,
        check_result=check_result,
        attack_result=attack_result,
        saving_throw_result=saving_throw_result,
        effects=effects,
        target=target,
        narrative_history=narrative_history,
    )

    def _run_provider(current_prompt: str) -> Optional[NarrationBundle]:
        try:
            import asyncio

            if req.provider == "openai":
                return asyncio.run(_call_openai_api(current_prompt))
            if req.provider == "kimi" or KIMI_API_KEY:
                return asyncio.run(_call_kimi_api(current_prompt))

            provider = get_provider(req.provider)
            if provider is None:
                return None

            generated = asyncio.run(provider.generate(NARRATIVE_SYSTEM_PROMPT, current_prompt))
            return _parse_narration_bundle(generated) if generated else None
        except Exception:
            return None

    narrative = _run_provider(prompt)
    if narrative:
        # Use comprehensive validation including numeric authority checks
        validation = validate_narrative_for_overreach(
            action_result=narrative.action_result,
            scene_progression=narrative.scene_progression,
            gm_prompt=narrative.gm_prompt,
            context=context,
        )
        
        if validation.is_valid:
            return narrative

        logger.warning(
            "Narration failed validation with %d violations; retrying once",
            len(validation.violations),
            extra={
                "outcome": outcome.value,
                "action_intent": req.intent,
                "violations": validation.violations,
            },
        )
        retry_prompt = (
            f"{prompt}\n\n"
            "【修正要求 / CORRECTION REQUIRED】\n"
            "你上一版叙事违反以下约束规则。请严格修正，不得重复以下问题：\n"
            f"{json.dumps(validation.violations, ensure_ascii=False)}\n\n"
            "特别提醒：你作为叙事AI，绝对不得自行宣布或修改任何数值（如HP、伤害值等）。"
            "数值相关描述只能通过感官细节体现，不得直接陈述数值变化。"
        )
        retry_narrative = _run_provider(retry_prompt)
        if retry_narrative:
            retry_validation = validate_narrative_for_overreach(
                action_result=retry_narrative.action_result,
                scene_progression=retry_narrative.scene_progression,
                gm_prompt=retry_narrative.gm_prompt,
                context=context,
            )
            if retry_validation.is_valid:
                return retry_narrative

            logger.warning(
                "Narration retry still failed validation; using fallback",
                extra={
                    "outcome": outcome.value,
                    "action_intent": req.intent,
                    "violations": retry_validation.violations,
                },
            )

    return _fallback_narration_bundle(
        req,
        actor,
        scene,
        outcome,
        attack_result,
        check_result,
        narrative_history,
    )
