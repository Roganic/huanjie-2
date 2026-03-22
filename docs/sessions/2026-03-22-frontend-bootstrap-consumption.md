# Frontend Bootstrap Consumption

**日期**: 2026-03-22
**任务 ID**: `frontend-bootstrap-consumption`
**分支**: `wt/frontend-bootstrap-consumption`

## 目标

将前端侧栏和状态面板从静态 mock 数据切换为后端 `/state/bootstrap` 接口返回的实时数据。

## 做了什么

1. **新增 bootstrap 类型**: `AbilityScores`, `Actor`, `Scene`, `BootstrapState` — 与后端 Pydantic 模型一一对应。
2. **新增 bootstrap 请求**: 组件挂载时 fetch `/api/state/bootstrap`，结果存入 `bootstrap` state。
3. **替换侧栏**: 原先硬编码的三个场景和三个队伍成员，改为从 bootstrap 读取当前 scene 和 actor，加上场景描述。
4. **替换状态面板**: 移除 `MOCK_CHARACTER`（硬编码的艾拉·暮光），改为展示后端 actor 的 HP、熟练加值和六项属性值。
5. **替换 action 请求参数**: `scene_id` 和 `actor` 从旧的 `FIXED_SCENE_ID` / `FIXED_ACTOR` 改为 bootstrap 数据（fallback 到后端默认值）。
6. **移除废弃常量**: `MOCK_CHARACTER`, `FIXED_SCENE_ID`, `FIXED_ACTOR` 全部删除。
7. **CSS**: 新增 `.scene-desc` 和 `.sidebar-loading` 两个样式类。

## 验证

- `tsc -b` 类型检查通过
- `vite build` 生产构建通过
- `eslint src/` 无告警

## 未决问题

- 当 bootstrap 请求失败时，UI 停留在"加载中"状态，没有重试或错误提示。当前阶段可接受，后续可加错误处理。
- 状态面板不显示 class/level/AC，因为后端 bootstrap 尚未提供这些字段。等后端模型扩展后再补。
- action 后 HP 等状态不会自动刷新 — 这是下游任务 `frontend-state-refresh-after-action` 的职责。

## 下一步建议

- `frontend-state-refresh-after-action`: action 完成后重新 fetch bootstrap 或增量更新状态面板。
- 后端扩展 Actor 模型加入 class、level、AC 等字段后，前端可直接消费。
