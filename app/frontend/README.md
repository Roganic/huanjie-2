# 幻界 2.0 前端

React + TypeScript + Vite 单页应用。

## 本地开发

```bash
cd app/frontend
npm ci
npm run dev
```

开发服务器默认通过 Vite 代理把 `/api/*` 转发到 `http://localhost:8000`。

## 生产构建

生产环境通过 `VITE_API_BASE_URL` 注入后端地址，不再依赖同源 `/api`。

```bash
cd app/frontend
VITE_API_BASE_URL=https://your-backend.example.com npm run build
```

可选环境变量：

- `VITE_API_BASE_URL`：生产环境后端 HTTPS 根地址，例如 `https://your-backend.example.com`
- `VITE_BASE_PATH`：静态资源部署基础路径；GitHub Pages 场景通常为 `/<repo-name>/`

示例配置见 `app/frontend/.env.example`（开发环境）和 `env.production.example`（生产构建参考）。实际使用时请在本地创建 `.env` / `.env.production` 或直接通过 CI 环境变量注入。

## GitHub Pages 部署

### 公开访问入口（示例）

> 以下链接为占位示例，实际部署后请替换为真实地址。

- **前端（GitHub Pages）**：`https://<your-username>.github.io/<repo-name>/`
- **后端（健康检查）**：`https://<your-backend-domain>/health`
- **后端 API 文档**：`https://<your-backend-domain>/docs`

### 自动部署（GitHub Actions）

1. 在仓库 **Settings > Pages** 中启用 GitHub Pages（来源选 GitHub Actions）。
2. 在仓库 **Settings > Secrets and variables > Actions** 中添加 `VITE_API_BASE_URL`（你的云后端 HTTPS 地址）。
3. 推送 `main` 分支后，`.github/workflows/deploy-frontend-pages.yml` 会自动构建并发布。

### 手动本地构建

```bash
cd app/frontend
npm ci
VITE_API_BASE_URL=https://your-backend.example.com npm run build
```

构建产物在 `app/frontend/dist`，可直接上传到任意静态托管服务。

### 生产环境变量说明

| 变量 | 说明 | 示例 |
|------|------|------|
| `VITE_API_BASE_URL` | 前端构建时注入的后端根地址 | `https://huanjie-backend.fly.dev` |
| `VITE_BASE_PATH` | 前端静态资源基础路径（GitHub Pages 需设） | `/<repo-name>/` |
