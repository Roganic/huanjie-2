# 2026-03-22 Backend State Bootstrap

## 目标

为后端添加一个只读的 `/state/bootstrap` 端点，返回当前固定角色和场景的初始状态，让前端可以从后端获取游戏初始数据，而不是依赖本地 mock。

同时将 action resolver 中的硬编码 ability modifier 桩替换为从 bootstrap actor 的真实属性值计算。

## 做了什么

### 新增文件

- `src/models/state.py` — Pydantic 模型：`AbilityScores`、`Actor`、`Scene`、`BootstrapState`
  - `AbilityScores` 使用 alias 处理 Python 保留字（`str` → `str_`，`int` → `int_`），JSON 序列化仍输出 `"str"` / `"int"`
  - `AbilityScores.modifier(ability)` 按 D&D 公式 `(score - 10) // 2` 计算
- `src/state.py` — 固定的 bootstrap 数据：一个 level-1 战士型角色 Aldric + 起始酒馆场景
- `src/routers/state.py` — `GET /state/bootstrap` 端点
- `tests/test_state.py` — 5 个测试覆盖端点形状、属性完整性、modifier 数学、resolver 集成

### 修改文件

- `src/main.py` — 注册 `state.router`
- `src/engine/resolver.py` — 移除硬编码 `DEFAULT_ABILITY_MODIFIERS` 和 `DEFAULT_PROFICIENCY_BONUS`，改为从 `get_bootstrap_state().actor` 查询

## 验证

```
python3 -m pytest tests/ -v
# 14 passed (9 existing + 5 new)
```

所有原有测试继续通过。注意 STR modifier 从旧的 `2`（桩值）变为 `3`（score 16 → (16-10)//2），但原有测试不硬断言 modifier 值，所以不受影响。

## 刻意没做的

- **没有引入数据库或持久化** — 当前只有一个硬编码的 actor/scene，足够原型阶段使用
- **没有 session 或多角色管理** — `get_bootstrap_state()` 目前直接返回固定数据，后续可扩展为按 session 查询
- **没有修改前端** — 前端消费 `/state/bootstrap` 属于独立任务
- **没有修改共享文档** — 遵守 worker 规则，只写 session 记录

## 下一步建议

- 前端对接 `/state/bootstrap`，用返回的 actor/scene 替换静态 mock
- 考虑 `/action` 端点是否也应该返回更新后的 actor 状态（如 HP 变化）
- 当引入多角色时，将 `BootstrapState` 扩展为 `actors: list[Actor]`
