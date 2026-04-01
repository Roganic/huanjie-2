# 技术选型

阅读顺序：先看“当前倾向”，需要拍板时再补充具体方案对比。

本文件用于记录技术方向和后续取舍，不在这里堆叠大而全的备选方案。

## 当前倾向

- 前端：Vite + React + TypeScript（本地 Web）
- 后端：Python + FastAPI，单体服务优先
- 目录：文档、研究、代码、归档分层
- 开发方式：先验证玩法和系统边界，再扩展工程复杂度

## 已决定

### 前端：Vite + React + TypeScript

- **Vite**：零配置开发服务器，HMR 快，构建输出小
- **React**：生态最大，AI 辅助编码支持最好，后续接流式响应、状态管理路径成熟
- **TypeScript**：类型安全，跨 session 接手时降低理解成本
- 暂不引入路由库、状态管理库或 UI 组件库，等复杂度需要时再加

### 后端：Python + FastAPI

- **后端语言**：Python（>=3.10）— AI/LLM 生态最成熟，适合快速原型
- **后端框架**：FastAPI — 轻量、异步、自带 OpenAPI 文档，便于调试
- **包管理**：pyproject.toml + pip，暂不引入 Poetry / PDM 等额外工具

### 部署：GitHub Pages + 容器化云后端

- **前端部署**：GitHub Pages，保留纯静态托管的低成本路径
- **后端部署**：Render 或 Railway，统一使用 `app/backend/Dockerfile`
- **环境注入**：前端使用 `VITE_BACKEND_URL`，后端使用平台环境变量注入 AI key 与 CORS

## 待决定

- 数据存储方案
- 向量检索方案
- 本地模型与云端模型的分工
