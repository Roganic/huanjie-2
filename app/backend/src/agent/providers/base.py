"""Base provider interface for narration generation."""

from __future__ import annotations

from typing import Optional, Protocol


class NarrationProvider(Protocol):
    """Protocol for AI narration providers.

    Implementations handle API-specific authentication, request formatting,
    and response parsing. All configuration must come from environment
    variables — no hard-coded keys or model names.
    """

    @property
    def name(self) -> str:
        """Human-readable provider name."""
        ...

    def is_available(self) -> bool:
        """Return True when the provider has required configuration."""
        ...

    async def generate(self, system_prompt: str, user_prompt: str) -> Optional[str]:
        """Call the provider API and return the generated text, or None on failure."""
        ...
