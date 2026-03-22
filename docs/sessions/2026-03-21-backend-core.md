# 2026-03-21 后端最小骨架

## 目标

在 `app/backend/` 建立可启动的最小后端服务，为后续规则引擎、GM agent 编排和会话状态预留结构。

## 做了什么

1. **技术选型**：确定 Python + FastAPI 作为后端栈
   - Python：AI/LLM 生态最成熟，原型阶段优先
   - FastAPI：轻量异步、自带 OpenAPI 文档、便于调试
2. **项目结构**：
   ```
   app/backend/
   ├── pyproject.toml      # 依赖管理
   ├── README.md           # 启动说明
   ├── .gitignore          # 排除 .venv / __pycache__
   └── src/
       ├── main.py         # FastAPI 入口
       └── routers/
           └── health.py   # GET /health
   ```
3. **验证**：本地 `uvicorn src.main:app --reload` 启动成功
   - `GET /` → `{"name": "幻界 2.0", "status": "running"}`
   - `GET /health` → `{"status": "ok"}`
4. **文档更新**：
   - `docs/tech-choices.md` — 记录 Python + FastAPI 决策
   - `docs/ai-architecture.md` — 补充后端模块与核心模块的对应关系

## 结论

- 后端骨架已就位，可作为后续开发的基础
- 当前结构足够极简，符合"不提前拆分"原则
- 后续模块（engine / agent / memory / models）按需在 `src/` 下新建

## 未决问题

- 前后端通信协议尚未定义（REST？WebSocket？混合？）
- 会话状态结构和持久化方案未定
- GM agent 的提示词编排模式未定
- 是否需要引入 CORS 中间件取决于前端技术栈选型

## 下一步建议

1. 前端骨架就绪后，定义前后端通信的第一个接口（建议从"发送玩家行动 → 返回 GM 叙述"开始）
2. 规则内核收敛后，在 `src/engine/` 实现第一个检定函数
3. 选定 LLM 调用方式后，在 `src/agent/` 搭建 GM agent 最小原型
