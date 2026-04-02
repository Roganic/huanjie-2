"""Module trigger engine for story node progression.

This module evaluates whether player actions satisfy story triggers
and advances the active module's current_story_node accordingly.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .models.module import ModuleDefinition, StoryNode, StoryTrigger, TriggerType, get_module
from .state import get_active_module, get_scene, set_active_module_story_node


@dataclass
class TriggerResult:
    """Result of evaluating a story trigger."""

    triggered: bool
    previous_node_id: Optional[str] = None
    triggered_node_id: Optional[str] = None
    description: Optional[str] = None


def get_current_story_node(session_id: str | None = None) -> tuple[Optional[StoryNode], Optional[ModuleDefinition]]:
    """Get the current story node and its module definition for a session.
    
    Returns:
        Tuple of (StoryNode or None, ModuleDefinition or None)
    """
    active = get_active_module(session_id)
    if active is None:
        return None, None
    module = get_module(active.module_id)
    if module is None:
        return None, None
    node = module.nodes.get(active.current_story_node)
    return node, module


def evaluate_triggers(
    action_type: str,
    target: str,
    intent: str = "",
    session_id: str | None = None,
) -> TriggerResult:
    """Evaluate whether the current action triggers a story node advancement.
    
    Args:
        action_type: Broad action category (e.g., "move", "interact", "combat", "explore")
        target: The primary target of the action (scene_id, npc_id, or keyword)
        intent: The player's raw intent text (for keyword matching)
        session_id: The session ID
        
    Returns:
        TriggerResult indicating whether a trigger fired and what changed
    """
    active = get_active_module(session_id)
    if active is None:
        return TriggerResult(triggered=False)
    
    node, module = get_current_story_node(session_id)
    if node is None or module is None:
        return TriggerResult(triggered=False)
    
    previous_node_id = node.id
    intent_lower = intent.lower()
    
    for trigger in node.triggers:
        matched = False
        if trigger.type == TriggerType.ENTER_SCENE:
            matched = target == trigger.target
        elif trigger.type == TriggerType.INTERACT_NPC:
            matched = target == trigger.target
        elif trigger.type == TriggerType.ACTION_KEYWORD:
            matched = trigger.target.lower() in intent_lower
        
        if matched:
            next_node = module.nodes.get(trigger.next_node_id)
            if next_node is None:
                continue
            
            # Update session state
            set_active_module_story_node(trigger.next_node_id, session_id)
            
            return TriggerResult(
                triggered=True,
                previous_node_id=previous_node_id,
                triggered_node_id=trigger.next_node_id,
                description=next_node.description,
            )
    
    return TriggerResult(triggered=False)


def check_scene_entry_triggers(session_id: str | None = None) -> TriggerResult:
    """Check triggers when the player enters a new scene.
    
    This should be called after scene switching (e.g., movement).
    
    Returns:
        TriggerResult if a trigger fired, otherwise triggered=False
    """
    scene = get_scene(session_id)
    return evaluate_triggers(
        action_type="move",
        target=scene.id,
        intent="",
        session_id=session_id,
    )


def check_action_triggers(
    intent: str,
    approach: str = "",
    session_id: str | None = None,
) -> TriggerResult:
    """Check triggers for a generic player action.
    
    Evaluates enter_scene triggers based on current scene, interact_npc
    triggers based on NPC mentions in intent, and action_keyword triggers.
    
    Args:
        intent: Player's action intent
        approach: Player's action approach
        session_id: The session ID
        
    Returns:
        TriggerResult if a trigger fired
    """
    full_text = f"{intent} {approach}".lower()
    scene = get_scene(session_id)
    
    # First check scene entry (in case we are already in that scene)
    result = evaluate_triggers(
        action_type="explore",
        target=scene.id,
        intent=intent,
        session_id=session_id,
    )
    if result.triggered:
        return result
    
    # Check NPC interactions by looking for NPC names in intent
    node, _ = get_current_story_node(session_id)
    if node is not None:
        for trigger in node.triggers:
            if trigger.type == TriggerType.INTERACT_NPC:
                # Simple heuristic: NPC id or a fragment of it appears in text
                if trigger.target.lower() in full_text:
                    return evaluate_triggers(
                        action_type="interact",
                        target=trigger.target,
                        intent=intent,
                        session_id=session_id,
                    )
    
    # Check action keywords
    return evaluate_triggers(
        action_type="action",
        target="",
        intent=intent,
        session_id=session_id,
    )


def build_module_context_for_prompt(session_id: str | None = None) -> str:
    """Build module context string for injection into narrative prompts.
    
    Returns:
        Formatted module context string, or empty string if no active module
    """
    node, module = get_current_story_node(session_id)
    if node is None or module is None:
        return ""
    
    lines: list[str] = []
    lines.append(f"【模组剧情 / MODULE CONTEXT】")
    lines.append(f"当前剧情节点 / Current Story Node: {node.name}")
    lines.append(f"节点描述 / Node Description: {node.description}")
    
    if node.visible_npcs:
        lines.append(f"剧情相关NPC / Relevant NPCs: {', '.join(node.visible_npcs)}")
    
    if node.quests:
        lines.append("")
        lines.append("活跃任务 / Active Quests:")
        for quest in node.quests:
            lines.append(f"  - {quest.name}: {quest.description}")
            for obj in quest.objectives:
                status = "[已完成]" if obj.completed else "[未完成]"
                lines.append(f"      {status} {obj.description}")
    
    lines.append("")
    lines.append("叙事约束 / NARRATIVE CONSTRAINT:")
    lines.append("- 你必须严格基于当前剧情节点和场景描述进行叙事")
    lines.append("- 不要引入当前场景和剧情节点中未定义的NPC或地点")
    lines.append("- 主动引导玩家推进当前节点的任务目标")
    
    return "\n".join(lines)
