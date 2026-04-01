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

## GitHub Pages

仓库包含 `.github/workflows/deploy-frontend-pages.yml`：

- `main` 分支推送后自动构建并发布到 GitHub Pages
- 构建前强制检查仓库 secret `VITE_API_BASE_URL`
- 默认将 `VITE_BASE_PATH` 设为 `/<repo-name>/`
- 构建后复制 `index.html` 为 `404.html`，兼容单页应用刷新
