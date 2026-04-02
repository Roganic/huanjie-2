"""Centralized configuration for LLM narration."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class LLMConfig:
    api_key: str
    model: str
    base_url: str
    timeout: float


def get_llm_config(provider: Optional[str] = None) -> Optional[LLMConfig]:
    """Load LLM configuration from environment variables.

    Args:
        provider: Optional provider name ('kimi' or 'openai').
                 Defaults to Kimi if KIMI_API_KEY is set, otherwise OpenAI.

    Returns:
        LLMConfig if API key is available, otherwise None.
    """
    if provider == "openai":
        api_key = os.getenv("OPENAI_API_KEY", "")
        if not api_key:
            return None
        return LLMConfig(
            api_key=api_key,
            model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            base_url=os.getenv(
                "OPENAI_API_URL", "https://api.openai.com/v1/chat/completions"
            ),
            timeout=float(os.getenv("OPENAI_TIMEOUT_SECONDS", "5")),
        )

    # Default: Kimi
    api_key = os.getenv("KIMI_API_KEY", "")
    if not api_key:
        return None

    return LLMConfig(
        api_key=api_key,
        model=os.getenv("KIMI_MODEL", "moonshot-v1-8k"),
        base_url=os.getenv(
            "KIMI_API_URL", "https://api.moonshot.cn/v1/chat/completions"
        ),
        timeout=float(os.getenv("KIMI_TIMEOUT_SECONDS", "5")),
    )
