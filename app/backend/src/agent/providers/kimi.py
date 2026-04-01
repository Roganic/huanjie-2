"""Kimi (Moonshot) narration provider."""

from __future__ import annotations

import asyncio
import os
from typing import Optional

import httpx

from .base import NarrationProvider


class KimiProvider(NarrationProvider):
    """Narration provider using Moonshot's Kimi API."""

    def __init__(self) -> None:
        self._api_key = os.getenv("KIMI_API_KEY", "")
        self._api_url = os.getenv("KIMI_API_URL", "https://api.moonshot.cn/v1/chat/completions")
        self._model = os.getenv("KIMI_MODEL", "moonshot-v1-8k")
        self._timeout = float(os.getenv("KIMI_TIMEOUT_SECONDS", "5"))

    @property
    def name(self) -> str:
        return "kimi"

    def is_available(self) -> bool:
        return bool(self._api_key)

    async def generate(self, system_prompt: str, user_prompt: str) -> Optional[str]:
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.8,
            "max_tokens": 500,
        }
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(
                    self._api_url,
                    headers=headers,
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()
                if "choices" in data and len(data["choices"]) > 0:
                    content = data["choices"][0].get("message", {}).get("content", "")
                    return content.strip() if content else None
                return None
        except asyncio.TimeoutError:
            return None
        except httpx.HTTPError:
            return None
        except Exception:
            return None
