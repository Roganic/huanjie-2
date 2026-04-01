# 部署指南

本文档说明如何将幻界 2.0 部署到公开环境，采用前后端分离架构：

- **前端**: GitHub Pages (静态站点)
- **后端**: Railway 或 Render (云服务)

## 架构概览

```
┌─────────────────┐         ┌─────────────────┐
│   GitHub Pages  │ ◄─────► │  Railway/Render │
│   (静态前端)     │  HTTPS  │  (FastAPI后端)  │
└─────────────────┘         └─────────────────┘
        │                            │
        └─────── VITE_BACKEND_URL ───┘
                   (环境变量注入)
```

## 后端部署

### 方式一: Railway (推荐)

1. **Fork 本仓库** 到你的 GitHub 账号

2. **登录 Railway**: https://railway.app

3. **创建项目**:
   - 点击 "New Project" → "Deploy from GitHub repo"
   - 选择 fork 的仓库
   - 选择 `app/backend` 作为根目录

4. **配置环境变量**:
   在 Railway 项目 Settings → Variables 中添加:

   ```
   KIMI_API_KEY=your_kimi_api_key_here
   # 或
   OPENAI_API_KEY=your_openai_api_key_here
   
   # 可选配置
   CORS_ALLOW_ORIGINS=https://yourusername.github.io
   ```

5. **部署**:
   - Railway 会自动检测 `railway.toml` 并部署
   - 部署完成后，记下分配的域名 (如 `https://huanjie-api.up.railway.app`)

### 方式二: Render

1. **登录 Render**: https://render.com

2. **创建 Web Service**:
   - 点击 "New +" → "Web Service"
   - 选择 GitHub 仓库
   - 选择 `app/backend` 作为根目录

3. **配置**:
   - Runtime: Python 3
   - Build Command: `pip install -e .`
   - Start Command: `uvicorn src.main:app --host 0.0.0.0 --port $PORT`

4. **环境变量**:
   在 Render 的 Environment 标签页添加:

   ```
   KIMI_API_KEY=your_kimi_api_key_here
   # 或
   OPENAI_API_KEY=your_openai_api_key_here
   ```

5. **部署**:
   - Render 会自动部署
   - 记下分配的域名 (如 `https://huanjie-api.onrender.com`)

## 前端部署 (GitHub Pages)

### 1. 配置环境变量

在前端目录创建生产环境配置:

```bash
cd app/frontend
cp .env.example .env.production
```

编辑 `.env.production`:

```
VITE_BACKEND_URL=https://your-backend-url.railway.app
# GitHub Pages 子路径格式: /repo-name/
VITE_APP_BASE=/huanjie-2/
```

### 2. 本地构建测试

```bash
cd app/frontend
npm ci
VITE_BACKEND_URL=https://your-backend-url.railway.app npm run build:pages
```

构建产物在 `dist/` 目录，可直接部署。

### 3. 推送到 GitHub Pages

#### 使用 GitHub Actions (推荐)

在项目根目录创建 `.github/workflows/deploy-frontend.yml`:

```yaml
name: Deploy Frontend to GitHub Pages

on:
  push:
    branches: [main]
  workflow_dispatch:

permissions:
  contents: read
  pages: write
  id-token: write

concurrency:
  group: pages
  cancel-in-progress: false

jobs:
  deploy:
    environment:
      name: github-pages
      url: ${{ steps.deployment.outputs.page_url }}
    runs-on: ubuntu-latest
    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Setup Node
        uses: actions/setup-node@v4
        with:
          node-version: 20
          cache: npm
          cache-dependency-path: app/frontend/package-lock.json

      - name: Install dependencies
        run: |
          cd app/frontend
          npm ci

      - name: Build
        run: |
          cd app/frontend
          VITE_BACKEND_URL=${{ vars.BACKEND_URL }} npm run build:pages

      - name: Setup Pages
        uses: actions/configure-pages@v4

      - name: Upload artifact
        uses: actions/upload-pages-artifact@v3
        with:
          path: app/frontend/dist

      - name: Deploy to GitHub Pages
        id: deployment
        uses: actions/deploy-pages@v4
```

然后在 GitHub 仓库设置中:
- Settings → Pages → Source: GitHub Actions
- Settings → Secrets and variables → Variables → Repository variables
- 添加 `BACKEND_URL` = `https://your-backend-url.railway.app`

### 4. 验证部署

访问 GitHub Pages URL，检查:
- [ ] 页面正常加载
- [ ] 健康检查指示器显示 "后端已连接"
- [ ] 可以创建角色
- [ ] 可以发送行动指令
- [ ] 可以重置游戏

## 环境变量参考

### 前端 (构建时)

| 变量名 | 说明 | 示例 |
|--------|------|------|
| `VITE_BACKEND_URL` | 后端 API 地址 | `https://api.example.com` |
| `VITE_APP_BASE` | 应用基础路径 | `/huanjie-2/` |

### 后端 (运行时)

| 变量名 | 说明 | 必填 |
|--------|------|------|
| `KIMI_API_KEY` | Kimi API 密钥 | 二选一 |
| `OPENAI_API_KEY` | OpenAI API 密钥 | 二选一 |
| `PORT` | 服务端口 (由平台提供) | 自动 |
| `CORS_ALLOW_ORIGINS` | 允许的跨域来源 | 可选 |

## 本地开发

本地开发不受部署配置影响，使用默认配置:

```bash
# 后端
cd app/backend
source .venv/bin/activate
uvicorn src.main:app --reload

# 前端 (新终端)
cd app/frontend
npm run dev
```

前端 dev server 会自动代理 `/api` 请求到 `http://localhost:8000`。

## 故障排查

### 前端显示 "后端离线"

1. 检查后端健康端点: `https://your-backend.com/health`
2. 检查 CORS 配置: 后端日志中查看是否有 CORS 错误
3. 检查网络: 浏览器 DevTools → Network 查看请求状态

### AI 叙事不生效

1. 检查后端环境变量是否设置了 `KIMI_API_KEY` 或 `OPENAI_API_KEY`
2. 检查后端日志中的 API 调用错误

### 构建失败

1. 确保 `VITE_BACKEND_URL` 不为空且格式正确
2. 检查 `package.json` 中的 `build:pages` 脚本是否存在
