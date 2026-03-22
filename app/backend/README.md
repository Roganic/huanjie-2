# 幻界 2.0 后端

Python + FastAPI 单体服务。

## 快速启动

```bash
cd app/backend
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
uvicorn src.main:app --reload
```

服务启动后访问：

- 根路径：http://localhost:8000/
- 健康检查：http://localhost:8000/health
- API 文档：http://localhost:8000/docs

## 目录结构

```text
app/backend/
├── pyproject.toml
├── README.md
├── src/
│   ├── main.py              # FastAPI 入口
│   ├── routers/
│   │   ├── health.py        # GET /health
│   │   └── action.py        # POST /action
│   ├── engine/
│   │   ├── dice.py          # d20 投骰（优势/劣势）
│   │   └── resolver.py      # 行动裁定引擎
│   └── models/
│       └── action.py        # 请求/响应数据模型
└── tests/
    └── test_action.py       # 行动 API 测试
```

## API

### GET /health

健康检查。返回 `{"status": "ok"}`。

### POST /action

提交玩家行动，返回结构化裁定结果。

请求体示例：

```json
{
  "scene_id": "dungeon-03",
  "actor": "Bree",
  "intent": "pick the lock on the chest",
  "approach": "carefully pick the lock with thieves tools",
  "dc": 15
}
```

可选字段：`ability`（str/dex/con/int/wis/cha）、`dc`、`advantage`（true/false）。

响应体示例：

```json
{
  "action_summary": "Bree attempts to pick the lock on the chest by carefully pick the lock with thieves tools",
  "resolution_type": "check",
  "check": {
    "ability": "dex",
    "modifier": 1,
    "proficiency_bonus": 2,
    "advantage": null,
    "roll": 14,
    "total": 17,
    "dc": 15
  },
  "outcome": "success",
  "effects": [],
  "narration": "Bree attempts to pick the lock on the chest by carefully pick the lock with thieves tools — and it works."
}
```

## 测试

```bash
cd app/backend
source .venv/bin/activate
python3 -m pytest tests/ -v
```

## 后续扩展方向

按需新增，不提前建目录：

- `src/agent/` — GM agent 编排（LLM 调用）
- `src/memory/` — 会话状态与记忆/RAG
