# 幻界 2.0 后端

Python 3.10+ + FastAPI 单体服务。

## 本地启动

```bash
cd app/backend
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
uvicorn src.main:app --reload
```

服务启动后访问：

- 根路径：`http://localhost:8000/`
- 健康检查：`http://localhost:8000/health`
- API 文档：`http://localhost:8000/docs`

## 关键环境变量

- `PORT`：服务监听端口，云平台通常自动注入
- `CORS_ALLOW_ORIGINS`：允许跨域的前端 origin，使用逗号分隔
- `KIMI_API_KEY`：Kimi 叙事模型 key
- `KIMI_API_URL` / `KIMI_MODEL` / `KIMI_TIMEOUT_SECONDS`：Kimi 可选覆盖项
- `OPENAI_API_KEY`：OpenAI 叙事模型 key
- `OPENAI_API_URL` / `OPENAI_MODEL` / `OPENAI_TIMEOUT_SECONDS`：OpenAI 可选覆盖项

本地开发默认允许：

- `http://localhost:5173`
- `http://127.0.0.1:5173`

部署到 GitHub Pages 时，需要把 `CORS_ALLOW_ORIGINS` 设置为实际前端 origin，例如：

```bash
CORS_ALLOW_ORIGINS=https://your-user.github.io
```

## 容器部署

后端目录自带 `Dockerfile`，可直接用于 Railway 或 Render。

本地构建与运行：

```bash
cd app/backend
docker build -t huanjie-backend .
docker run --rm -p 8000:8000 \
  -e CORS_ALLOW_ORIGINS=http://localhost:5173 \
  -e KIMI_API_KEY=your-key \
  huanjie-backend
```

## API

- `GET /health`：健康检查
- `GET /state/bootstrap`：获取当前角色、场景和叙事上下文
- `POST /state/character`：创建新角色并重置场景
- `POST /state/reset`：重置到初始状态
- `POST /action`：提交玩家行动并获取裁定与叙事

## 测试

```bash
cd app/backend
source .venv/bin/activate
python -m pytest tests -v
```
