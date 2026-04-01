# 幻界 2.0 前端

## 本地开发

```bash
cd app/frontend
npm install
npm run dev
```

默认情况下，Vite 会将 `/api/*` 请求代理到 `http://localhost:8000`，因此本地开发不需要填写 `VITE_BACKEND_URL`。

## 环境变量

- `VITE_BACKEND_URL`：生产环境后端地址，例如 `https://huanjie-api.onrender.com`
- `VITE_APP_BASE`：静态资源基础路径。GitHub Pages 项目页通常为 `/<repo>/`

可用示例：

```bash
cp .env.example .env.local
```

## 生产构建

普通构建：

```bash
npm run build
```

GitHub Pages 构建：

```bash
VITE_BACKEND_URL=https://your-backend.example.com \
VITE_APP_BASE=/your-repo/ \
npm run build:pages
```

构建产物位于 `dist/`，可直接发布到 GitHub Pages。
