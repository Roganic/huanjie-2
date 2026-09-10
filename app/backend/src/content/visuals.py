"""Portable presentation-only contract. No mechanics or executable theme code."""
import base64
import binascii
import struct
from typing import Literal, Protocol
from pydantic import BaseModel, ConfigDict, Field, model_validator


class VisualDefinition(BaseModel):
    model_config = ConfigDict(extra='forbid')


def image_dimensions(raw: bytes, mime: str) -> tuple[int, int]:
    if mime == 'image/png' and raw[:8] == b'\x89PNG\r\n\x1a\n' and raw[12:16] == b'IHDR' and len(raw) >= 33:
        return struct.unpack('>II', raw[16:24])
    if mime == 'image/jpeg' and raw[:2] == b'\xff\xd8':
        i = 2
        while i + 4 <= len(raw):
            if raw[i] != 255:
                break
            marker = raw[i + 1]
            if marker == 255:
                i += 1
                continue
            if marker in (0xD8, 0xD9) or 0xD0 <= marker <= 0xD7:
                i += 2
                continue
            length = int.from_bytes(raw[i + 2:i + 4], 'big')
            if length < 2 or i + 2 + length > len(raw):
                break
            if marker in (0xC0, 0xC1, 0xC2) and length >= 8:
                h, w = struct.unpack('>HH', raw[i + 5:i + 9])
                return w, h
            i += 2 + length
    raise ValueError('图片内容与格式不符，支持静态 PNG / JPEG。')


class VisualAsset(VisualDefinition):
    name: str = Field(max_length=120)
    source: Literal['upload', 'generated'] = 'upload'
    data: str = Field(max_length=240_000)
    generation_id: str | None = Field(default=None, max_length=100)

    @model_validator(mode='after')
    def raster(self):
        prefix, sep, encoded = self.data.partition(',')
        mime = prefix.removeprefix('data:').removesuffix(';base64')
        if not sep or prefix not in ('data:image/png;base64', 'data:image/jpeg;base64'):
            raise ValueError('素材须为内嵌 PNG / JPEG，不接受网址、SVG 或脚本。')
        try:
            raw = base64.b64decode(encoded, validate=True)
            w, h = image_dimensions(raw, mime)
        except (ValueError, binascii.Error, struct.error) as exc:
            raise ValueError('图片格式无效或内容损坏。') from exc
        if not (0 < w <= 2048 and 0 < h <= 2048):
            raise ValueError('图片边长不能超过 2048 像素。')
        return self


Category = Literal['tavern', 'wilds', 'harbor', 'ruins', 'abstract', 'portrait', 'traveller', 'weapon', 'armor', 'potion', 'item']


class ArtSlot(VisualDefinition):
    builtin: Literal['tavern', 'wilds', 'harbor', 'ruins', 'traveller', 'village-square', 'marcus', 'ayla', 'hooded-merchant', 'dungeon-gate', 'dungeon-passage', 'ancient-temple', 'ancient-vault'] | None = None
    asset_id: str | None = Field(default=None, max_length=80)
    fallback: Category | None = None
    focal_x: int = Field(default=50, ge=0, le=100)
    focal_y: int = Field(default=50, ge=0, le=100)


class ThemePack(VisualDefinition):
    schema_version: Literal[1] = 1
    id: str = Field(default='western-journal', pattern=r'^[a-zA-Z0-9_-]{1,64}$')
    name: str = Field(default='西境旅行志', min_length=1, max_length=80)
    preset: Literal['parchment', 'midnight', 'neutral'] = 'parchment'
    heading_font: Literal['serif', 'sans'] = 'serif'
    frame: Literal['ornate', 'simple'] = 'ornate'
    illustrated: bool = True
    assets: dict[str, VisualAsset] = Field(default_factory=dict, max_length=30)
    defaults: dict[str, ArtSlot] = Field(default_factory=dict, max_length=11)

    @model_validator(mode='after')
    def references(self):
        allowed = {'tavern', 'wilds', 'harbor', 'ruins', 'abstract', 'portrait', 'traveller', 'weapon', 'armor', 'potion', 'item'}
        for key, slot in self.defaults.items():
            if key not in allowed or (slot.asset_id and slot.asset_id not in self.assets):
                raise ValueError('主题默认素材分类或引用无效。')
        if sum(len(a.data) for a in self.assets.values()) > 768_000:
            raise ValueError('主题素材总量请控制在 750 KB 以内。')
        return self


class MapPoint(VisualDefinition):
    x: int = Field(ge=80, le=920)
    y: int = Field(ge=80, le=540)
    label: str | None = Field(default=None, max_length=12)


class ModuleVisuals(VisualDefinition):
    schema_version: Literal[1] = 1
    theme: ThemePack = Field(default_factory=ThemePack)
    assets: dict[str, VisualAsset] = Field(default_factory=dict, max_length=60)
    scenes: dict[str, ArtSlot] = Field(default_factory=dict)
    characters: dict[str, ArtSlot] = Field(default_factory=dict)
    items: dict[str, ArtSlot] = Field(default_factory=dict)
    map: dict[str, ArtSlot] = Field(default_factory=dict)
    map_layout: dict[str, MapPoint] = Field(default_factory=dict)
    player: ArtSlot | None = None
    cover: ArtSlot | None = None

    @model_validator(mode='after')
    def references(self):
        slots = [*self.scenes.values(), *self.characters.values(), *self.items.values(), *self.map.values(), self.player, self.cover]
        for slot in slots:
            if slot and slot.asset_id and slot.asset_id not in self.assets:
                raise ValueError(f'模组素材引用不存在：{slot.asset_id}')
        if sum(len(a.data) for a in [*self.assets.values(), *self.theme.assets.values()]) > 768_000:
            raise ValueError('模组与主题素材合计请控制在 750 KB 以内。')
        return self


# Future provider integration: server-issued quotes, explicit acceptance, then
# an idempotent job. A generation_id in an imported asset is not a paid receipt.
class ImageGenerationRequest(VisualDefinition):
    prompt: str = Field(min_length=1, max_length=4000)
    slot: Category
    theme_id: str = Field(max_length=64)
    count: int = Field(default=1, ge=1, le=4)


class ImageQuote(VisualDefinition):
    id: str
    currency: Literal['CNY'] = 'CNY'
    unit_price_fen: int = Field(ge=0)
    count: int = Field(ge=1, le=4)
    expires_at: str


class ImageJobRequest(VisualDefinition):
    quote_id: str = Field(min_length=1, max_length=100)
    idempotency_key: str = Field(min_length=16, max_length=100)


class ImageJob(VisualDefinition):
    id: str
    status: Literal['queued', 'running', 'succeeded', 'failed']
    assets: list[VisualAsset] = Field(default_factory=list)
    charged_fen: int = Field(default=0, ge=0)


class ImageProvider(Protocol):
    async def quote(self, request: ImageGenerationRequest) -> ImageQuote: ...
    async def submit(self, request: ImageJobRequest) -> ImageJob: ...
    async def status(self, job_id: str) -> ImageJob: ...
