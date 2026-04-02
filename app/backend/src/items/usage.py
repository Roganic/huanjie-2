"""Item usage resolution logic."""

from __future__ import annotations

from dataclasses import dataclass

from ..engine.dice import roll_damage
from ..models.action import Effect, ItemUseDetail
from ..models.state import Actor, InventoryItem, ItemType


# Names that match the healing potion
HEALING_POTION_NAMES = {"治疗药水", "healing potion", "药水", "potion"}


@dataclass
class ItemUseResult:
    """Result of resolving an item use action."""

    success: bool
    action_summary: str = ""
    narration: str = ""
    scene_progression: str = ""
    gm_prompt: str = ""
    effects: list[Effect] | None = None
    item_use: ItemUseDetail | None = None
    error_message: str = ""


def _find_item_in_inventory(actor: Actor, item_name: str) -> tuple[int, InventoryItem] | None:
    """Find an item in the actor's inventory by name (case-insensitive).

    Returns (index, item) if found, None otherwise.
    """
    item_name_lower = item_name.lower().strip()
    for idx, item in enumerate(actor.inventory):
        if item.name.lower() == item_name_lower:
            return idx, item
    return None


def _match_healing_potion(item_name: str) -> bool:
    """Check if the item name refers to a healing potion."""
    name_lower = item_name.lower().strip()
    # Direct match
    if name_lower in {n.lower() for n in HEALING_POTION_NAMES}:
        return True
    # Fuzzy match: contains "治疗" and "药水"
    if "治疗" in name_lower and "药水" in name_lower:
        return True
    if "healing" in name_lower and "potion" in name_lower:
        return True
    return False


def resolve_item_use(actor: Actor, item_name: str) -> ItemUseResult:
    """Resolve using an item from the actor's inventory.

    Args:
        actor: The actor using the item.
        item_name: Name of the item to use.

    Returns:
        ItemUseResult with success/failure, effects, and narration.
    """
    effects: list[Effect] = []

    # Try to find the item in inventory
    found = _find_item_in_inventory(actor, item_name)

    # Special handling: if the name looks like a healing potion but exact name
    # wasn't found, try to find any consumable that is a healing potion
    if found is None and _match_healing_potion(item_name):
        for idx, item in enumerate(actor.inventory):
            if item.type == ItemType.CONSUMABLE and _match_healing_potion(item.name):
                found = (idx, item)
                break

    if found is None:
        return ItemUseResult(
            success=False,
            error_message=f"背包中没有 '{item_name}'。",
        )

    idx, item = found

    # Resolve based on item type and identity
    if _match_healing_potion(item.name):
        # Healing potion: restore 2d4+2 HP, capped at hp_max
        total, rolls = roll_damage("2d4+2")
        hp_before = actor.hp
        hp_after = min(actor.hp_max, actor.hp + total)
        hp_change = hp_after - hp_before

        effects.append(
            Effect(
                target=actor.id,
                field="hp",
                delta=hp_change,
                description=f"{actor.name} 饮用 {item.name}，恢复 {hp_change} 点生命值。",
            )
        )

        # Also apply inventory removal effect (handled by state.py)
        effects.append(
            Effect(
                target=actor.id,
                field="inventory_remove",
                delta=item.name,
                description=f"{item.name} 已从背包中移除。",
            )
        )

        return ItemUseResult(
            success=True,
            action_summary=f"{actor.name} 使用 {item.name}",
            narration=f"{actor.name} 拔开瓶塞，将鲜红的药水一饮而尽。温暖的能量流过全身，恢复了 {hp_change} 点生命值。",
            scene_progression="生命值得到恢复，你可以继续行动。",
            gm_prompt="询问玩家下一步想要做什么，或描述周围环境的细微变化。",
            effects=effects,
            item_use=ItemUseDetail(
                item_name=item.name,
                effect_type="heal",
                roll_result=total,
                hp_change=hp_change,
            ),
        )

    # Unknown consumable / not implemented
    return ItemUseResult(
        success=False,
        error_message=f"'{item.name}' 暂无法使用。",
    )
