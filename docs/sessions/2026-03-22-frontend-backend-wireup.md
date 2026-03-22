# 2026-03-22 Frontend-Backend Wireup

## 目标

将现有前端壳子接到后端已有的 `/health` 与 `/action`，实现最小可交互的前后端联调。

## 输入

- `app/frontend/` 现有 React + Vite 前端壳子（纯 mock 数据）
- `app/backend/` 现有 FastAPI 后端（`/health` + `/action` 已实现）
- `docs/sessions/2026-03-21-frontend-shell.md` 前端壳子记录
- `docs/sessions/2026-03-22-gm-loop-prototype.md` 后端 GM loop 记录

## 做了什么

### 后端改动（最小）

| 文件 | 改动 |
|------|------|
| `src/main.py` | 新增 CORS 中间件，允许 `localhost:5173` 跨域请求 |

### 前端改动

| 文件 | 改动 |
|------|------|
| `vite.config.ts` | 新增 `/api` 代理，将前端请求转发到后端 `localhost:8000` |
| `src/App.tsx` | 全面重写：移除 mock GM 回复，接入真实 API |
| `src/App.css` | 新增健康指示灯、系统消息、裁定卡片等样式 |

### 前端新增交互

1. **健康状态指示灯**（Header 右侧）
   - 挂载时立即检测 `GET /api/health`
   - 每 15 秒自动刷新
   - 三态显示：黄色脉冲（连接中）→ 绿色（已连接）→ 红色（离线）

2. **行动发送**
   - 用户输入文本后通过 `POST /api/action` 发送到后端
   - 固定 `scene_id: "dungeon-01"` 和 `actor: "Aira"`
   - `intent` 和 `approach` 均使用用户输入文本
   - 发送期间输入框禁用，显示"裁定中…"

3. **结构化裁定结果展示** — `ResolutionCard` 组件
   - 顶部 badge 显示裁定类型（检定/自动成功）和结果（成功/失败）
   - 检定路径显示属性名称（中文）、d20 骰面值、调整值、熟练加值、总计、DC
   - 优势/劣势标签（如适用）
   - effects 列表（如有）
   - 叙事文本

4. **事件日志**（右侧面板）
   - 动态追加，不再是静态 mock
   - 检定结果自动记录为"属性检定 DC → 总计 成功/失败"
   - 自动成功记录为"自动成功: 行动摘要"

5. **错误处理**
   - HTTP 非 200 响应显示为系统消息
   - 网络异常显示为系统消息
   - 系统消息用虚线边框居中显示，与 GM/玩家消息区分

6. **其他改动**
   - 移除了静态 mock 消息，改为空白起始 + 提示文案
   - 新消息自动滚动到底部

## 验证结果

- `npm run build`（含 tsc + vite build）通过
- `npm run lint`（eslint）通过
- `python3 -m compileall src` 通过
- 后端仅新增 CORS 中间件，未改动 API 协议

## 本地验证步骤

```bash
# 终端 1：启动后端
cd app/backend
source .venv/bin/activate
pip install -e ".[dev]"
uvicorn src.main:app --reload

# 终端 2：启动前端
cd app/frontend
npm install
npm run dev

# 打开 http://localhost:5173
# 1. 观察 Header 右侧健康指示灯变绿
# 2. 输入 "look around the room" → 应得到自动成功
# 3. 输入 "pick the lock on the chest" → 应得到检定结果
# 4. 观察右侧事件日志自动更新
```

## 刻意未做的内容

- **没有做角色选择和场景切换**：actor 和 scene_id 硬编码
- **没有改后端 API 协议**：完全使用现有 `/health` 和 `/action` 形态
- **没有把规则逻辑复制到前端**：前端只做展示，裁定完全由后端完成
- **没有做 Markdown 渲染**：narration 直接显示为纯文本
- **没有做角色数据同步**：右侧面板仍为静态 mock 角色数据
- **没有做会话持久化**：刷新页面会丢失聊天记录
- **没有做流式响应**：等待完整响应后一次性显示

## 下一步建议

1. 角色数据从后端加载，替换右侧面板的静态 mock
2. 场景切换功能，让左侧场景列表可交互
3. 接入 LLM 生成 narration 后，考虑流式展示
4. 聊天记录持久化（本地存储或后端会话状态）
5. 骰子动画 / 投骰视觉反馈
