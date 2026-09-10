"""Validated content repository; running sessions keep their own content snapshot."""
import json
import os
import sys
import tempfile
from functools import lru_cache
from pathlib import Path
from typing import Protocol
from .schema import ModulePack

MODULE_DIR = Path(os.getenv("MODULE_DIR", Path(__file__).parent.parent.parent / "modules"))


@lru_cache(maxsize=1)
def builtin():
    return ModulePack.model_validate_json(Path(__file__).with_name("builtin.json").read_text())


@lru_cache(maxsize=1)
def bundled():
    return {p.stem: ModulePack.model_validate_json(p.read_text())
            for p in sorted(Path(__file__).with_name('adventures').glob('*.json'))}


def for_session(session):
    return session.content_pack or builtin()


def get_pack(module_id):
    if module_id in ("default", builtin().id):
        return builtin().model_copy(deep=True)
    if module_id in bundled():
        return bundled()[module_id].model_copy(deep=True)
    # Validate IDs before using them as filenames.
    import re
    if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}", module_id):
        return None
    path = MODULE_DIR / f"{module_id}.json"
    try:
        pack = ModulePack.model_validate_json(path.read_text())
        return pack if pack.id == module_id else None
    except (ValueError, OSError):
        return None


def install(pack):
    if pack.id in ("default", builtin().id) or pack.id in bundled():
        raise ValueError("内置模组不可覆盖，请使用新的模组 ID。")
    MODULE_DIR.mkdir(parents=True, exist_ok=True)
    path = MODULE_DIR / f"{pack.id}.json"
    if path.exists():
        raise ValueError("模组 ID 已存在，请使用新 ID 导入新版本。")
    # Publish a fully written file without overwriting an existing module.
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=MODULE_DIR, suffix=".tmp", delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(pack.model_dump_json(by_alias=True, indent=2))
            stream.flush()
            os.fsync(stream.fileno())
        if sys.platform == 'emscripten':
            # Browser requests are serialized in one Worker. No other writer can
            # intervene between the existence check and this atomic rename.
            temporary.rename(path)
        else:
            os.link(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def packs():
    result = [builtin().model_copy(deep=True), *[p.model_copy(deep=True) for p in bundled().values()]]
    for path in sorted(MODULE_DIR.glob("*.json")):
        try:
            pack = ModulePack.model_validate_json(path.read_text())
            if pack.id not in ("default", builtin().id) and pack.id not in bundled() and path.stem == pack.id:
                result.append(pack)
        except (ValueError, OSError):
            continue
    return result


class StoryParser(Protocol):
    """Text parsers produce a reviewed draft, never directly mutate game state."""
    async def parse(self, source: str) -> dict: ...


def parse_json(source: str):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"重复的 JSON 键：{key}")
            result[key] = value
        return result
    return json.loads(source, object_pairs_hook=unique)
