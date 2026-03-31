# 2026-03-22 Frontend State Panel Polish

## 目标

在前端状态面板中展示后端权威数据中的 conditions 与 scene time，并让最近的效果变化更易于扫描。

## 输入

- 基于 `frontend-ui-enhancement` worktree 的最新前端代码
- 后端 API `/api/state/bootstrap` 已返回 `actor.conditions` 与 `scene.time`
- 后端 `apply_effects` 已支持 `conditions_add`、`conditions_remove`、`time` 字段的变更

## 改动范围

仅修改以下路径：
- `app/frontend/src/App.tsx`
- `app/frontend/src/App.css`
- `docs/sessions/2026-03-22-frontend-state-panel-polish.md`

## 实现内容

### 1. 类型扩展

在 `Scene` 接口中新增可选字段：

```ts
interface Scene {
  // ...existing fields...
  time?: number;
}
```

### 2. 场景时间展示

- **Sidebar 场景卡片**：新增 `scene.time` 展示行，时间变化时触发绿色闪烁动画。
- **Status Panel 场景时间区块**：独立展示当前 `scene.time`（单位 ticks），变化时同样触发闪烁动画，与 HP、属性值并列呈现。

### 3. 最近变化扫描（Recent Changes）

新增 `computeStateDiff` 纯 diff 逻辑，对比 `previousBootstrap` 与当前 `bootstrap`：

- **HP 变化**：显示 `+/- N HP`
- **新增条件**：显示 `+ 条件名`（绿色高亮）
- **移除条件**：显示 `- 条件名`（灰色删除线）
- **时间变化**：显示 `+/- N 时间`（蓝色高亮）

该组件仅在存在差异时渲染，无需理解后端规则语义，仅做数组/数值对比。

### 4. 条件高亮

`StatusEffect` 组件新增 `isNew` 属性：
- 新获得的条件会带有脉冲发光边框（`pulse-glow` 动画），持续约 1.2s，便于一眼识别最新生效的状态。

### 5. API 契约

未修改任何 API 路径、请求体或响应体结构。前端仅消费后端已提供的字段。

## 验证

```bash
cd app/frontend
npm run build   # tsc + vite build 通过，无类型错误
```

构建产物已更新至 `app/frontend/dist/`。

## 未决问题

- 当前 `previousBootstrap` 在每次行动后更新，因此 "最新变化" 仅展示最近一次行动带来的差异。若后续需要聚合多次变化，可改为保留一个变化历史队列。

## 下一步建议

1. 若后端增加更多可变更字段（如 `scene.environment`、`actor.ac`），只需在 `computeStateDiff` 中追加对比逻辑即可。
2. 考虑为 `RecentChanges` 增加自动淡出（如 5 秒后隐藏），减少面板常驻信息量。
