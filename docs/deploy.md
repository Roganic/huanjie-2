# 前后端分离部署指南

本项目的部署架构为：**GitHub Pages（静态前端）+ 云后端（Railway / Render）**。

## 部署架构

```
┌─────────────────┐         ┌─────────────────────────┐
│  GitHub Pages   │ ──────► │  Railway / Render       │
│  (Vite 构建产物) │   CORS  │  (FastAPI + Docker)     │
└─────────────────┘         └─────────────────────────┘
                                     │
                                     ▼
                            ┌─────────────────┐
                            │  Kimi / OpenAI  │
                            │  (LLM 叙事 API) │
                            └─────────────────┘
```

- 前端通过 `VITE_BACKEND_URL` 指向云后端地址
- 后端通过 `CORS_ALLOW_ORIGINS` 允许前端域名跨域
- AI API Key（`KIMI_API_KEY`、`OPENAI_API_KEY`）均通过平台环境变量注入，代码中无硬编码

---

## 环境变量清单

### 前端构建时（GitHub Actions / 本地生产构建）

| 变量名 | 说明 | 示例 |
|--------|------|------|
| `VITE_BACKEND_URL` | 后端 API 根地址 | `https://huanjie-backend.up.railway.app` |
| `VITE_APP_BASE` | GitHub Pages 子路径 | `/huanjie-2/` 或 `/` |

### 后端运行时（Railway / Render / 本地）

| 变量名 | 说明 | 示例 |
|--------|------|------|
| `PORT` | 服务监听端口（平台自动注入） | `8000` |
| `CORS_ALLOW_ORIGINS` | 允许跨域的前端 origin，逗号分隔 | `https://user.github.io` |
| `KIMI_API_KEY` | Kimi 叙事模型 API Key | `sk-...` |
| `KIMI_API_URL` | 可选，覆盖默认 Kimi endpoint | `https://api.moonshot.cn/v1/chat/completions` |
| `KIMI_MODEL` | 可选，覆盖默认 Kimi 模型 | `moonshot-v1-8k` |
| `OPENAI_API_KEY` | OpenAI 叙事模型 API Key | `sk-...` |
| `OPENAI_API_URL` | 可选，覆盖默认 OpenAI endpoint | `https://api.openai.com/v1/chat/completions` |
| `OPENAI_MODEL` | 可选，覆盖默认 OpenAI 模型 | `gpt-4o-mini` |

---

## 后端部署

后端目录 `app/backend/` 自带 `Dockerfile`，支持一键部署到 Railway 或 Render。

### Railway 部署

1. 登录 [Railway](https://railway.app)，新建 Project
2. 选择 "Deploy from GitHub repo"，选择本项目仓库
3. 在 Service Settings 中将 **Root Directory** 设为 `app/backend`
4. 在 Variables 中添加：
   - `CORS_ALLOW_ORIGINS` = `https://<你的 GitHub 用户名>.github.io`（如果使用自定义域名则填自定义域名）
   - `KIMI_API_KEY` = 你的 Kimi API Key（或 `OPENAI_API_KEY`）
5. 部署完成后，在 Service 的 Domains 中获取公开 URL，例如 `https://huanjie-backend.up.railway.app`

> 配置文件：`app/backend/railway.toml`

### Render 部署

1. 登录 [Render](https://render.com)
2. 点击 "New +" → "Blueprint"，选择本项目仓库
3. 在创建时指定 Blueprint 文件路径为 `app/backend/render.yaml`
4. 部署完成后，进入 Dashboard 为该 Web Service 添加环境变量：
   - `CORS_ALLOW_ORIGINS` = 你的 GitHub Pages 前端 origin
   - `KIMI_API_KEY` 和/或 `OPENAI_API_KEY`
5. 获取公开 URL（例如 `https://huanjie-backend.onrender.com`）

> 配置文件：`app/backend/render.yaml`
> 注意：`render.yaml` 中默认 `CORS_ALLOW_ORIGINS=*`，方便首次快速验证。生产环境请务必修改为具体前端 origin。

---

## 前端部署（GitHub Pages）

### 1. 配置 Repository Variables

进入 GitHub 仓库 **Settings → Secrets and variables → Actions → Variables**，添加：

- `BACKEND_URL`：你的后端公开 URL（例如 `https://huanjie-backend.up.railway.app`）
- `APP_BASE`（可选）：
  - 如果使用默认 GitHub Pages 域名（`https://<user>.github.io/<repo>/`），可不填，CI 会自动推断为 `/<repo>/`
  - 如果使用自定义域名（如 `https://huanjie.example.com/`），则设为 `/`

### 2. 启用 GitHub Pages

进入 **Settings → Pages**，Source 选择 "GitHub Actions"。

### 3. 触发部署

- 向 `main` 或 `master` 分支推送修改到 `app/frontend/**` 或 `.github/workflows/deploy-frontend.yml`
- 或手动在 Actions 页面触发 **Deploy Frontend to GitHub Pages**

部署完成后，访问 GitHub Pages 链接即可。

---

## 本地开发

本地开发时前端和后端完全独立，前端通过 Vite Dev Server 的代理直接转发 `/api` 到本地后端。

```bash
# 1. 启动后端
cd app/backend
source .venv/bin/activate
uvicorn src.main:app --reload

# 2. 启动前端（新终端）
cd app/frontend
npm install
npm run dev
```

- 前端地址：`http://localhost:5173`
- 后端地址：`http://localhost:8000`
- 前端 `vite.config.ts` 中已配置代理：`/api/*` → `http://localhost:8000/*`
- **本地开发无需设置 `VITE_BACKEND_URL`**；只有生产构建时才需要

---

## 部署验证

打开 GitHub Pages 公开地址后，按以下步骤验证完整游戏流程：

1. **创建角色**：输入角色名并选择模板，点击 "开始冒险"，确认角色状态和场景信息正确加载
2. **行动**：输入一个行动意图（如 "调查酒馆角落"），点击发送，确认 GM 返回叙事和检定结果
3. **叙事推进**：确认场景中时间、环境、角色状态有正常变化
4. **重置**：点击 "重置"，确认游戏回到初始状态
5. **后端连接**：页面右上角的健康指示灯应显示 "后端已连接"

如果任意步骤失败，请检查浏览器开发者工具中的 Network 请求和 Console 报错，优先排查：
- `VITE_BACKEND_URL` 是否指向了正确的后端地址
- 后端 `CORS_ALLOW_ORIGINS` 是否包含了前端 Pages 的 origin
- 后端环境变量中是否至少配置了一个 AI API Key（Kimi 或 OpenAI）
