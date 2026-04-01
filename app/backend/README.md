# 幻界 2.0 后端

Python + FastAPI 单体服务。

## 运行要求

- Python `>=3.10`
- 推荐 Python `3.11`

项目代码使用了 Python 3.10+ 的类型语法，Python 3.9 不能正常启动。

## 本地启动

```bash
cd app/backend
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install ".[dev]"
python -m src.main
```

服务启动后访问：

- 根路径：http://localhost:8000/
- 健康检查：http://localhost:8000/health
- API 文档：http://localhost:8000/docs

## 生产部署

后端支持直接通过环境变量启动：

```bash
cd app/backend
python -m src.main
```

关键环境变量：

- `PORT`：监听端口，默认 `8000`
- `HOST`：监听地址，默认 `0.0.0.0`
- `CORS_ALLOW_ORIGINS`：逗号分隔的允许来源列表
- `KIMI_API_KEY`：Kimi API Key
- `OPENAI_API_KEY`：OpenAI API Key
- `KIMI_API_URL` / `OPENAI_API_URL`：可选自定义 API 地址
- `KIMI_MODEL` / `OPENAI_MODEL`：可选模型名

应用默认允许 `http://localhost:5173`，并额外放行 `https://*.github.io`，便于与 GitHub Pages 前端联调。

## 容器部署

目录内提供 `app/backend/Dockerfile`，可直接用于 Railway / Render / Fly.io 等支持 Docker 的平台。

```bash
cd app/backend
docker build -t huanjie-backend .
docker run -p 8000:8000 \
  -e PORT=8000 \
  -e KIMI_API_KEY=... \
  huanjie-backend
```

`runtime.txt` 固定了 Python 3.11，便于使用支持该约定的平台。

## 一键部署到云平台

### Railway

```bash
cd app/backend
./scripts/deploy-railway.sh
```

前置条件：安装 [Railway CLI](https://docs.railway.app/develop/cli) 并已登录。部署后请在 Railway Dashboard 设置环境变量（`KIMI_API_KEY`、`CORS_ALLOW_ORIGINS` 等）。

### Fly.io

```bash
cd app/backend
flyctl apps create huanjie-backend   # 首次部署需创建应用
./scripts/deploy-fly.sh
```

前置条件：安装 [flyctl](https://fly.io/docs/flyctl/install/) 并已登录。首次创建应用后，后续可直接运行 `./scripts/deploy-fly.sh`。 secrets 请通过 `flyctl secrets set` 配置。
