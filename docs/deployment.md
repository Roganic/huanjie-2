# 部署说明

本文档描述当前推荐的公开部署方式：前端部署到 GitHub Pages，后端部署到 Render 或 Railway。

## 方案摘要

- 前端：Vite 构建静态资源，使用 `VITE_BACKEND_URL` 指向云后端
- 后端：FastAPI 容器部署，AI key 与 CORS 通过环境变量注入
- 本地开发：继续使用 Vite `/api` 代理到 `localhost:8000`

## 前端部署到 GitHub Pages

在 `app/frontend/` 下执行：

```bash
npm install
VITE_BACKEND_URL=https://your-backend.example.com \
VITE_APP_BASE=/your-repo/ \
npm run build:pages
```

说明：

- `VITE_BACKEND_URL` 必须是后端公开地址，不要带尾部 `/`
- `VITE_APP_BASE` 在 GitHub Pages 项目页通常为 `/<repo>/`
- 构建产物位于 `app/frontend/dist/`

发布方式：

1. 将 `dist/` 内容推送到 GitHub Pages 对应分支或通过 Actions 发布
2. 打开 `https://<user>.github.io/<repo>/`

## 后端部署到 Render 或 Railway

后端目录：`app/backend/`

本地验证建议使用 Python 3.10+，容器镜像默认使用 Python 3.11。

### Render

1. 选择从仓库创建 Web Service
2. Root Directory 设为 `app/backend`
3. 选择 Docker 部署
4. 配置环境变量：
   - `CORS_ALLOW_ORIGINS=https://<user>.github.io`
   - `KIMI_API_KEY=<your-key>` 或 `OPENAI_API_KEY=<your-key>`
   - 可选：`KIMI_MODEL`、`OPENAI_MODEL`

### Railway

1. 新建服务并指向仓库
2. 选择 `app/backend/Dockerfile`
3. 配置环境变量：
   - `CORS_ALLOW_ORIGINS=https://<user>.github.io`
   - `KIMI_API_KEY=<your-key>` 或 `OPENAI_API_KEY=<your-key>`

`PORT` 由平台注入，无需手动设置。

## 验证清单

部署后至少检查以下路径：

1. 打开前端公开 URL，确认页面能正常加载
2. 页面右上角健康状态显示“后端已连接”
3. 在左侧填写角色名并点击“开始冒险”
4. 输入一条行动，确认返回叙事文本与状态变化
5. 点击“重置”，确认角色与场景状态回到初始值

## 当前限制

- GitHub Pages / Render / Railway 的实际发布动作需要仓库和云平台权限，本仓库内仅提供部署配置与步骤
- 角色创建目前是轻量模板化选择，不是完整 5e 角色构建流程
