# 部署说明

本文档描述当前推荐的公开部署方式：前端部署到 GitHub Pages，后端部署到 Render 或 Railway。

## 方案摘要

- 前端：Vite 静态构建，运行时通过 `VITE_BACKEND_URL` 指向云后端
- 后端：FastAPI + Docker，AI key 和 CORS 全部走环境变量
- 验证方式：本地先跑构建与烟测，再做公开发布
- 当前仓库已提供：
- `app/frontend/.env.example`
- `app/backend/env.example`
  - `app/backend/Dockerfile`
  - `app/backend/render.yaml`
  - `app/backend/tests/test_deployment_flow.py`

## 前端部署到 GitHub Pages

在 `app/frontend/` 下执行：

```bash
npm install
VITE_BACKEND_URL=https://your-backend.example.com \
VITE_APP_BASE=/your-repo/ \
npm run build:pages
```

说明：

- `VITE_BACKEND_URL` 必须填写后端公开地址，不要带尾部 `/`
- `VITE_APP_BASE` 在 GitHub Pages 项目页通常为 `/<repo>/`
- 如果你使用用户主页根路径，可将 `VITE_APP_BASE=/`
- 构建产物位于 `app/frontend/dist/`

发布方式：

1. 将 `dist/` 内容发布到 GitHub Pages 对应分支，或由 GitHub Actions 发布
2. 打开 `https://<user>.github.io/<repo>/`
3. 首次打开后确认前端健康状态能连到云后端

## 后端部署到 Render

后端目录：`app/backend/`

本地验证建议使用 Python 3.10+，容器镜像默认使用 Python 3.11。

推荐使用仓库内的 Blueprint：

1. 在 Render 里创建 Blueprint
2. 将 Blueprint 文件路径指定为 `app/backend/render.yaml`
3. 同步后设置环境变量：
   - `CORS_ALLOW_ORIGINS=https://<user>.github.io`
   - `KIMI_API_KEY=<your-key>` 或 `OPENAI_API_KEY=<your-key>`
   - 可选：`KIMI_MODEL`、`OPENAI_MODEL`
4. 部署完成后访问 `https://<your-render-service>/health`

说明：

- `render.yaml` 已把 `rootDir` 固定到 `app/backend`
- Docker 启动命令沿用 `Dockerfile` 里的 `uvicorn`
- `PORT` 由平台注入，无需手动设置

## 后端部署到 Railway

如果使用 Railway，直接复用 `app/backend/Dockerfile`：

1. 新建服务并连接仓库
2. 将服务根目录设置为 `app/backend`，或在服务变量里指定 Dockerfile 路径
3. 配置环境变量：
   - `CORS_ALLOW_ORIGINS=https://<user>.github.io`
   - `KIMI_API_KEY=<your-key>` 或 `OPENAI_API_KEY=<your-key>`
4. 部署后访问 `https://<your-railway-service>/health`

## 发布前本地验证

### 后端烟测

```bash
cd app/backend
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
python -m pytest tests/test_deployment_flow.py -v
```

这条烟测覆盖：

1. 创建角色
2. 提交行动
3. 返回叙事与场景推进
4. 重置状态

### 前端生产构建

```bash
cd app/frontend
npm install
VITE_BACKEND_URL=https://example.com \
VITE_APP_BASE=/demo/ \
npm run build:pages
```

## 公开部署后的验收清单

1. 打开前端公开 URL，确认页面能正常加载
2. 页面右上角健康状态显示“后端已连接”
3. 创建一个新角色并进入场景
4. 输入一条行动，确认返回叙事文本、裁定结果和场景推进
5. 点击“重置”，确认角色与场景状态回到初始值

## 当前限制

- 仓库内已补齐部署配置，但实际发布仍需要 GitHub Pages / Render / Railway 账号权限
- 本次会话无法直接替你创建真实线上服务，因此公开 URL 需要你按上面的步骤完成最后发布
