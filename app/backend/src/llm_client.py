"""Unified OpenAI-compatible LLM client for narrative generation."""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

import httpx

from .config import LLMConfig

logger = logging.getLogger(__name__)


class OpenAICompatibleClient:
    """OpenAI-compatible chat completions client.

    Supports any API that follows the OpenAI chat completions format,
    including Kimi (Moonshot), OpenAI, and compatible proxies.
    """

    def __init__(self, config: LLMConfig) -> None:
        self.config = config

    async def generate(self, system_prompt: str, user_prompt: str) -> Optional[str]:
        """Call the chat completions endpoint and return generated text.

        Logs the full user prompt and raw response for observability.
        """
        logger.info("LLM call started. Prompt length: %d chars", len(user_prompt))
        logger.info("LLM prompt:\n%s", user_prompt)

        headers = {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.config.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.8,
            "max_tokens": 500,
        }

        try:
            async with httpx.AsyncClient(timeout=self.config.timeout) as client:
                response = await client.post(
                    self.config.base_url,
                    headers=headers,
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()
                if "choices" in data and len(data["choices"]) > 0:
                    content = data["choices"][0].get("message", {}).get("content", "")
                    raw = content.strip() if content else None
                    if raw:
                        logger.info("LLM raw response:\n%s", raw)
                    return raw
                return None
        except asyncio.TimeoutError:
            logger.warning(
                "LLM call timed out after %s seconds", self.config.timeout
            )
            return None
        except httpx.HTTPStatusError as exc:
            logger.warning(
                "LLM call failed with HTTP %s: %s",
                exc.response.status_code,
                exc.response.text,
            )
            return None
        except httpx.HTTPError as exc:
            logger.warning("LLM call failed with HTTP error: %s", exc)
            return None
        except Exception as exc:
            logger.warning("LLM call failed with unexpected error: %s", exc)
            return None
