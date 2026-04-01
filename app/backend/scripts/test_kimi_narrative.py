#!/usr/bin/env python3
"""Manual test script for Kimi API narrative generation.

Usage:
    export KIMI_API_KEY="your-api-key"
    python scripts/test_kimi_narrative.py

Or without API key to test fallback mode:
    python scripts/test_kimi_narrative.py
"""

import json
import sys
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.agent.narrator import KIMI_API_KEY, generate_narration
from src.models.action import ActionRequest, Outcome
from src.models.state import AbilityScores, Actor, Scene


def create_test_actor() -> Actor:
    return Actor(
        id="test-01",
        name="Elara",
        abilities=AbilityScores(**{
            "str": 10,
            "dex": 16,
            "con": 12,
            "int": 14,
            "wis": 13,
            "cha": 15,
        }),
        proficiency_bonus=2,
        hp=20,
        hp_max=20,
        ac=14,
        description="A nimble elf rogue with a silver tongue and quick fingers.",
    )


def create_test_scene() -> Scene:
    return Scene(
        id="market-01",
        name="The Whispering Market",
        description=(
            "A crowded bazaar filled with exotic spices, colorful fabrics, "
            "and the constant murmur of merchants haggling. The scent of cinnamon "
            "and myrrh hangs heavy in the air."
        ),
        actors=["test-01"],
    )


def test_skill_check_narrative():
    """Test narrative generation for a skill check."""
    print("=" * 60)
    print("Test: Skill Check Narrative")
    print("=" * 60)
    
    actor = create_test_actor()
    scene = create_test_scene()
    req = ActionRequest(
        scene_id="market-01",
        actor="Elara",
        intent="pickpocket the merchant",
        approach="slip my hand into his pouch while distracting him with a question",
        ability="dex",
    )
    
    for outcome in [Outcome.SUCCESS, Outcome.FAILURE]:
        print(f"\n--- Outcome: {outcome.value} ---")
        check_result = {
            "ability": "dex",
            "modifier": 3,
            "dc": 15,
            "roll": 18 if outcome == Outcome.SUCCESS else 5,
            "total": 21 if outcome == Outcome.SUCCESS else 8,
        }
        
        narrative = generate_narration(
            req=req,
            actor=actor,
            scene=scene,
            outcome=outcome,
            check_result=check_result,
        )
        print(f"Narrative:\n{narrative}\n")


def test_combat_narrative():
    """Test narrative generation for combat."""
    print("=" * 60)
    print("Test: Combat Narrative")
    print("=" * 60)
    
    actor = Actor(
        id="warrior-01",
        name="Thorne",
        abilities=AbilityScores(**{
            "str": 18,
            "dex": 12,
            "con": 16,
            "int": 10,
            "wis": 12,
            "cha": 8,
        }),
        proficiency_bonus=2,
        hp=30,
        hp_max=30,
        ac=16,
        description="A hulking human warrior clad in battered plate armor.",
    )
    
    scene = Scene(
        id="dungeon-01",
        name="The Torchlit Corridor",
        description=(
            "A narrow stone passage lit by flickering torches. Water drips from "
            "the ceiling somewhere in the darkness ahead. The air smells of mold and rust."
        ),
        actors=["warrior-01"],
    )
    
    req = ActionRequest(
        scene_id="dungeon-01",
        actor="Thorne",
        intent="attack the goblin",
        approach="swing my greataxe in a deadly arc",
        weapon="greataxe",
        target="goblin-01",
    )
    
    for outcome in [Outcome.SUCCESS, Outcome.FAILURE]:
        print(f"\n--- Outcome: {outcome.value} ---")
        attack_result = {
            "weapon": "greataxe",
            "target": "Goblin Scout",
            "damage": {"total": 12, "rolls": [8, 4]} if outcome == Outcome.SUCCESS else None,
        }
        
        narrative = generate_narration(
            req=req,
            actor=actor,
            scene=scene,
            outcome=outcome,
            attack_result=attack_result,
        )
        print(f"Narrative:\n{narrative}\n")


def test_auto_success_narrative():
    """Test narrative generation for auto-success."""
    print("=" * 60)
    print("Test: Auto-Success Narrative")
    print("=" * 60)
    
    actor = create_test_actor()
    scene = create_test_scene()
    req = ActionRequest(
        scene_id="market-01",
        actor="Elara",
        intent="look around for exits",
        approach="casually scan the area",
    )
    
    print(f"\n--- Outcome: success (auto) ---")
    narrative = generate_narration(
        req=req,
        actor=actor,
        scene=scene,
        outcome=Outcome.SUCCESS,
    )
    print(f"Narrative:\n{narrative}\n")


def main():
    print("\n" + "=" * 60)
    print("Kimi API Narrative Generation Test")
    print("=" * 60)
    
    if KIMI_API_KEY:
        print(f"\n✓ KIMI_API_KEY is set (using AI generation)")
        # Mask the key for display
        masked_key = KIMI_API_KEY[:8] + "..." + KIMI_API_KEY[-4:] if len(KIMI_API_KEY) > 12 else "***"
        print(f"  Key: {masked_key}")
    else:
        print(f"\n⚠ KIMI_API_KEY is not set (using fallback narratives)")
        print(f"  To test with AI, set: export KIMI_API_KEY='your-key'")
    
    print()
    
    try:
        test_skill_check_narrative()
        print()
        test_combat_narrative()
        print()
        test_auto_success_narrative()
        
        print("\n" + "=" * 60)
        print("All tests completed successfully!")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n✗ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
