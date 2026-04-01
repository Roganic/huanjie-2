"""AI narration provider registry.

New providers are registered here; the rest of the codebase only talks to
``get_provider`` and the ``NarrationProvider`` protocol.
"""

from __future__ import annotations

from typing import Optional

from .base import NarrationProvider
from .kimi import KimiProvider
from .openai import OpenAIProvider

# Registry of supported providers.
_REGISTRY: dict[str, type[NarrationProvider]] = {
    "kimi": KimiProvider,
    "openai": OpenAIProvider,
}


def list_providers() -> list[str]:
    """Return the names of all registered providers."""
    return list(_REGISTRY.keys())


def get_provider(name: Optional[str] = None) -> Optional[NarrationProvider]:
    """Instantiate a provider by name.

    If *name* is omitted or empty, the first available provider is chosen
    based on environment configuration (Kimi first, then OpenAI).
    Returns ``None`` when the requested provider is unknown or unavailable.
    """
    if not name:
        # Default: first available provider in priority order
        for cls in (KimiProvider, OpenAIProvider):
            inst = cls()
            if inst.is_available():
                return inst
        return None

    cls = _REGISTRY.get(name.lower())
    if cls is None:
        return None
    inst = cls()
    return inst if inst.is_available() else None
