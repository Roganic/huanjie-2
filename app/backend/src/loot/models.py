"""Loot system models for enemy drop tables and loot generation."""

from __future__ import annotations

from pydantic import BaseModel, Field


class LootItem(BaseModel):
    """An item entry in a loot table."""
    
    item_id: str
    name: str
    quantity: int = 1
    probability: float = Field(ge=0.0, le=1.0, default=1.0)
    description: str = ""


class LootTable(BaseModel):
    """A loot table defining possible drops for an enemy type."""
    
    enemy_type: str
    enemy_name: str
    drops: list[LootItem]


class LootGained(BaseModel):
    """Represents loot gained from defeating an enemy."""
    
    enemy_id: str
    enemy_name: str
    items: list[LootItem]


class GeneratedLoot(BaseModel):
    """Result of loot generation for a combat encounter."""
    
    loot_entries: list[LootGained] = Field(default_factory=list)
    
    def get_all_items(self) -> list[LootItem]:
        """Get all loot items from all entries."""
        items = []
        for entry in self.loot_entries:
            items.extend(entry.items)
        return items
    
    def is_empty(self) -> bool:
        """Check if no loot was generated."""
        return len(self.loot_entries) == 0 or all(
            len(entry.items) == 0 for entry in self.loot_entries
        )
