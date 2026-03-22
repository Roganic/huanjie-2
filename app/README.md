# App Workspace

这里放所有可运行代码。

## 目录约定

- `frontend/`：本地 Web 前端
- `backend/`：API、规则引擎、agent 编排
- ForgeFlow 的控制脚本已迁移到平级目录 `ForgeFlow/scripts/`

## 约束

- 在没有明确必要前，不拆多服务
- 优先建立最小可运行原型
- 代码实现要和 `docs/` 中的正式结论保持同步

## 前端启动

```bash
cd frontend
npm install
npm run dev
```

默认地址 http://localhost:5173。

技术栈：Vite + React + TypeScript。详见 `docs/tech-choices.md`。
