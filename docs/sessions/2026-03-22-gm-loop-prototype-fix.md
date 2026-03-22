# 2026-03-22 GM Loop Prototype — Rework

## 目标

修复 `gm-loop-prototype` review 中指出的三个问题，使其达到可再次 review 的状态。

## 输入

- `coordination/reviews.md` 中 gm-loop-prototype 的 review 结论
- 三个必修项：auto-success 过宽、ability 未校验、缺少回归测试

## 修了哪些行为问题

### 1. 收紧 auto-success 规则

**问题**：原实现用单词级关键词（`open`, `talk`, `say` 等）做 `in` 匹配，导致 "open the locked chest"、"talk the guard into letting us pass"、"say a convincing lie" 都被误判为自动成功。

**修复**：
- 将关键词改为更具体的短语匹配（`look around`, `walk to`, `sit down` 等）
- 增加 disqualifier 机制：如果文本中出现 `locked`, `guard`, `convince`, `deceive`, `lie` 等词，即使匹配到了平凡短语也不自动成功
- `open` 和 `talk` 和 `say` 不再是独立的自动成功触发词

### 2. 收紧 ability 输入校验

**问题**：`ability` 字段接受任意字符串，非法值（如 `"athletics"`）会在 resolver 中静默得到 modifier `0`，不报错继续执行。

**修复**：
- 在 `ActionRequest` 模型上增加 Pydantic validator
- `ability` 必须为 `str/dex/con/int/wis/cha` 之一，否则返回 422

### 3. 补回归测试

新增 4 个测试：

| 测试 | 验证内容 |
|------|----------|
| `test_open_locked_chest_requires_check` | "open the locked chest" 不应自动成功 |
| `test_talk_guard_requires_check` | "talk the guard into letting us pass" 不应自动成功 |
| `test_say_convincing_lie_requires_check` | "say a convincing lie" 不应自动成功 |
| `test_invalid_ability_rejected` | `ability="athletics"` 应返回 422 |

## 验证结果

```
$ python3 -m pytest tests/ -v
9 passed in 0.58s
```

原有 5 个测试全部保留并通过，新增 4 个回归测试全部通过。

## 修改的文件

| 文件 | 改动 |
|------|------|
| `src/models/action.py` | 增加 ability validator |
| `src/engine/resolver.py` | 重写 auto-success 逻辑 |
| `tests/test_action.py` | 新增 4 个回归测试 |

## 刻意未做的内容

- 没有扩展 API 形态或新增端点
- 没有接入 LLM 或前端
- 没有引入数据库或会话状态
- 没有修改共享总纲文档
- auto-success 仍然是关键词规则，后续可能需要 LLM 判断替代

## 下一步建议

- 本版可再次提交 review
- 如需进一步提升 auto-success 准确性，应考虑让 GM agent（LLM）做分流判断
