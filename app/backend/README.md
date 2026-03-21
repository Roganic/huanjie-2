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
│   └── routers/
│       └── health.py        # 健康检查
```

## 后续扩展方向

按需新增，不提前建目录：

- `src/engine/` — 规则引擎
- `src/agent/` — GM agent 编排
- `src/memory/` — 会话状态与记忆/RAG
- `src/models/` — 数据模型
