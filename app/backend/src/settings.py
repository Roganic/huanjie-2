"""Environment-backed application settings."""

from __future__ import annotations

import os
from functools import lru_cache

from pydantic import BaseModel, Field


# 本地开发默认允许的 CORS 源
DEFAULT_CORS_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:4173",
    "http://127.0.0.1:4173",
]


def _parse_origins(raw_value: str | None) -> list[str]:
    """Parse CORS origins from environment variable.
    
    支持多种格式:
    - 未设置: 使用默认本地开发源
    - 空字符串: 使用默认本地开发源
    - "*": 允许所有源 (仅用于快速测试)
    - 逗号分隔的 URL 列表: 如 "https://user.github.io,https://app.example.com"
    """
    if raw_value is None:
        return DEFAULT_CORS_ORIGINS

    value = raw_value.strip()
    if not value:
        return DEFAULT_CORS_ORIGINS

    if value == "*":
        return ["*"]

    return [origin.strip() for origin in value.split(",") if origin.strip()]


class Settings(BaseModel):
    app_name: str = "幻界 2.0"
    app_version: str = "0.1.0"
    port: int = Field(default=8000, ge=1, le=65535)
    cors_origins: list[str] = Field(default_factory=lambda: list(DEFAULT_CORS_ORIGINS))


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Load process settings once per interpreter.
    
    环境变量:
    - PORT: 服务端口 (Railway/Render 自动注入)
    - CORS_ALLOW_ORIGINS: 允许的跨域来源，逗号分隔
      示例: "https://username.github.io" 或 "https://app.example.com,https://app2.example.com"
    """
    return Settings(
        port=int(os.getenv("PORT", "8000")),
        cors_origins=_parse_origins(os.getenv("CORS_ALLOW_ORIGINS")),
    )
