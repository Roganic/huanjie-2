"""Narrative prompt builder with memory injection.

Builds LLM prompts that include action history and NPC dialogue context
to ensure narrative continuity and world responsiveness.
"""

from __future__ import annotations

from typing import Optional

from .memory import ActionHistoryEntry


def build_memory_context(
    action_history: list[ActionHistoryEntry],
    npc_dialogue_history: Optional[list[str]] = None,
    max_entries: int = 5,
) -> str:
    """Build a memory context block for narrative prompts.

    Args:
        action_history: Full list of action history entries
        npc_dialogue_history: Optional list of NPC dialogue summaries
        max_entries: Maximum recent actions to include

    Returns:
        Formatted memory context string
    """
    lines: list[str] = []
    recent = action_history[-max_entries:] if len(action_history) > max_entries else action_history

    lines.append("【会话记忆 / SESSION MEMORY】")
    lines.append("以下是你（GM）与玩家已经共同经历的近期事件。叙事时必须引用这些历史，让场景持续演进，")
    lines.append("绝对禁止重复描述同一事件，禁止出现与以下记录矛盾的状态描述。")
    lines.append("")

    if recent:
        lines.append(f"最近 {len(recent)} 次行动摘要：")
        for idx, entry in enumerate(recent, start=1):
            lines.append(f"{idx}. 行动: {entry.action}")
            lines.append(f"   结果: {entry.result}")
            if entry.narrative_summary:
                summary = entry.narrative_summary
                if len(summary) > 120:
                    summary = summary[:117].rstrip() + "..."
                lines.append(f"   叙事摘要: {summary}")
    else:
        lines.append("当前尚无行动历史。这是本次会话的第一次叙事。")

    if npc_dialogue_history:
        lines.append("")
        lines.append("【NPC 对话历史 / NPC DIALOGUE HISTORY】")
        recent_dialogues = npc_dialogue_history[-5:]
        for idx, dialogue in enumerate(recent_dialogues, start=1):
            lines.append(f"{idx}. {dialogue}")

    lines.append("")
    lines.append("【记忆使用规则 / MEMORY RULES】")
    lines.append("1. 必须引用上述历史事件，让当前叙事体现世界的连续性和对玩家行动的响应。")
    lines.append("2. 禁止用几乎相同的句子重复描述已经发生过的事情。")
    lines.append("3. 禁止描述与历史记录矛盾的场景状态（例如历史已说明门已打开，就不能再说门是关闭的）。")
    lines.append("4. 如果玩家正在与 NPC 互动，必须参考 NPC 对话历史来保持 NPC 态度和行为的一致性。")
    lines.append("")

    return "\n".join(lines)


def build_narrative_prompt(
    intent: str,
    approach: str,
    scene_name: str,
    scene_description: str,
    actor_name: str,
    action_history: list[ActionHistoryEntry],
    npc_dialogue_history: Optional[list[str]] = None,
    current_npc: Optional[str] = None,
    max_history_entries: int = 5,
) -> str:
    """Build a complete narrative prompt with injected memory context.

    Args:
        intent: Player's action intent
        approach: How the player attempts the action
        scene_name: Current scene name
        scene_description: Current scene description
        actor_name: Acting character name
        action_history: Recent action history
        npc_dialogue_history: Optional NPC dialogue summaries
        current_npc: Optional current NPC being interacted with
        max_history_entries: Maximum history entries to include

    Returns:
        Complete prompt string for the LLM
    """
    lines: list[str] = []

    lines.append(build_memory_context(
        action_history=action_history,
        npc_dialogue_history=npc_dialogue_history,
        max_entries=max_history_entries,
    ))

    lines.append("【当前场景 / CURRENT SCENE】")
    lines.append(f"场景: {scene_name}")
    lines.append(f"描述: {scene_description}")
    lines.append("")

    lines.append("【角色 / CHARACTER】")
    lines.append(f"名称: {actor_name}")
    lines.append("")

    if current_npc:
        lines.append(f"【互动对象 / INTERACTION TARGET】")
        lines.append(f"NPC: {current_npc}")
        lines.append("")

    lines.append("【当前行动 / CURRENT ACTION】")
    lines.append(f"意图: {intent}")
    lines.append(f"方式: {approach}")
    lines.append("")

    lines.append("基于以上记忆和场景信息，生成叙事内容。要求：")
    lines.append("- 中文输出")
    lines.append("- 必须体现对历史事件的引用和响应")
    lines.append("- 禁止重复描述同一历史事件")
    lines.append("- 禁止出现与已知状态矛盾的描述")
    lines.append("- 返回 JSON: {\"action_result\": \"...\", \"scene_progression\": \"...\", \"gm_prompt\": \"...\"}")

    return "\n".join(lines)
