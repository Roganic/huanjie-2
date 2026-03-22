"""Dice rolling utilities."""

from __future__ import annotations

import random
from typing import Optional


def roll_d20(advantage: Optional[bool] = None) -> int:
    """Roll 1d20, applying advantage/disadvantage if specified.

    advantage=True  -> roll twice, take higher
    advantage=False -> roll twice, take lower
    advantage=None  -> single roll
    """
    if advantage is None:
        return random.randint(1, 20)
    a, b = random.randint(1, 20), random.randint(1, 20)
    return max(a, b) if advantage else min(a, b)
