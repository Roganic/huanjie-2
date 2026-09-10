"""Bounded document edits: the authoring reviewer can change a draft, never a game."""
import copy
import json
import re
from typing import Any, Literal
from pydantic import Field
from .schema import Definition


class DraftPatch(Definition):
    op: Literal['set', 'add', 'replace', 'remove'] = Field(description='修改或补充对象字段用 set；新增数组条目用 add；删除用 remove。replace 为旧兼容操作，仅限已存在字段。')
    path: str = Field(min_length=2, max_length=300, description='文档路径：数组条目必须用 @标识稳定定位，如 /quests/@letter/requires_any、/beats/@find/success。新增条目用 /beats/-。不要用会因删除而变化的数组数字下标。不含 document 前缀。')
    value: Any = None


class SourceMapping(Definition):
    source_excerpt: str = Field(min_length=1, max_length=300, description='从原稿逐字摘取的短句')
    references: list[str] = Field(max_length=15, description='实现这条原文的条目，格式 beats:标识、quests:标识、endings:标识、people:标识、items:标识或 locations:标识；无法表达时为空')
    note: str = Field(min_length=1, max_length=1000, description='说明如何落实该机制；不能表达时明确写出问题')


class DraftRevision(Definition):
    patches: list[DraftPatch] = Field(max_length=60)
    coverage: list[SourceMapping] = Field(min_length=1, max_length=30)
    assumptions: list[str] = Field(max_length=30)
    questions: list[str] = Field(max_length=30)


def apply_patches(document: dict, patches: list[DraftPatch]) -> dict:
    from .compiler import StoryGraph
    draft = copy.deepcopy(document)
    def array_index(values, key):
        if key.startswith('@'):
            found = [i for i, value in enumerate(values) if isinstance(value, dict) and value.get('id') == key[1:]]
            if len(found) != 1: raise ValueError(f'修订条目标识不存在或不唯一：{key}')
            return found[0]
        return int(key) if key.isdigit() else -1  # Compatibility with previously saved JSON Pointer patches.
    for patch in patches:
        if not patch.path.startswith('/') or re.search(r'~(?![01])', patch.path):
            raise ValueError('草稿修订路径不是有效 JSON Pointer')
        keys = [part.replace('~1', '/').replace('~0', '~') for part in patch.path[1:].split('/')]
        if keys[0] not in StoryGraph.model_fields or len(keys) > 12:
            raise ValueError('修订只能指向故事契约中的字段')
        parent = draft
        for key in keys[:-1]:
            if isinstance(parent, list) and 0 <= (index := array_index(parent, key)) < len(parent): parent = parent[index]
            elif isinstance(parent, dict) and key in parent: parent = parent[key]
            else: raise ValueError(f'修订路径不存在：{patch.path}')
        key = keys[-1]
        if isinstance(parent, list):
            index = len(parent) if key == '-' and patch.op == 'add' else array_index(parent, key)
            if not 0 <= index <= len(parent) or (patch.op != 'add' and index == len(parent)):
                raise ValueError(f'修订数组下标无效：{patch.path}')
            if patch.op == 'add': parent.insert(index, copy.deepcopy(patch.value))
            elif patch.op in ('set', 'replace'): parent[index] = copy.deepcopy(patch.value)
            else: parent.pop(index)
        elif isinstance(parent, dict):
            if patch.op not in ('set', 'add') and key not in parent: raise ValueError(f'修订字段不存在：{patch.path}')
            if patch.op == 'remove': del parent[key]
            else: parent[key] = copy.deepcopy(patch.value)
        else: raise ValueError(f'修订目标不是容器：{patch.path}')
        if len(json.dumps(draft, ensure_ascii=False)) > 2_000_000: raise ValueError('修订后的草稿过大')
    return draft


def coverage_issues(source: str, outline: dict, coverage: list[SourceMapping]) -> list[dict]:
    issues = []
    indexes = {group: {row.get('id') for row in (outline.get(group, []) if isinstance(outline.get(group, []), list) else []) if isinstance(row, dict)}
               for group in ('beats', 'quests', 'endings', 'people', 'items', 'locations')}
    for i, mapping in enumerate(coverage):
        if mapping.source_excerpt not in source:
            issues.append({'loc': ['coverage', i], 'type': 'source_mapping', 'msg': '机制摘录与原稿不完全一致，请对照原文确认。'})
        if not mapping.references:
            issues.append({'loc': ['coverage', i], 'type': 'unmapped_mechanism', 'msg': mapping.note})
        for ref in mapping.references:
            group, _, key = ref.partition(':')
            if key not in indexes.get(group, set()):
                issues.append({'loc': ['coverage', i], 'type': 'missing_mapping', 'msg': f'机制对应的条目不存在：{ref}'})
    return issues
