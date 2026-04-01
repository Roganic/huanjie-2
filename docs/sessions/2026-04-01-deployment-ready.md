# 目标

在限定路径内补齐可公开部署的前后端分离配置，使前端可发布到 GitHub Pages，后端可部署到 Render 或 Railway，并保证游戏流程至少覆盖创建角色、行动、叙事和重置。

## 输入

- `app/frontend/package.json`
- `app/backend/src/`
- `docs/tech-choices.md`
- ForgeFlow 会话目标：`prompt-deployment-ready.md`

## 结论

- 前端新增 `VITE_BACKEND_URL` 与 `VITE_APP_BASE` 支持，构建产物可直接用于 GitHub Pages
- 后端通过 `Dockerfile` + `render.yaml` 支持云部署，CORS 与 AI provider key 均通过环境变量注入
- 新增后端 `env.example` 与完整流程烟测，覆盖“创建角色 → 行动 → 叙事 → 重置”
- `docs/deployment.md` 已整理为可执行的 GitHub Pages / Render / Railway 发布步骤

## 验证

- `python3 -m pytest app/backend/tests -q` 通过，结果为 `90 passed`
- `python3 -m pytest app/backend/tests/test_deployment_flow.py -q` 通过
- `cd app/frontend && VITE_BACKEND_URL=https://api.example.com VITE_APP_BASE=/demo/ npm run build:pages` 通过
- 前端默认 `npm run build:pages` 也通过，说明未破坏本地 `/api` 代理模式

## 未决问题

- 未在真实 GitHub Pages / Render / Railway 账号下完成最终发布，因此公开 URL 仍需人工补最后一步
- 如果后续要接入真正的角色构建流程，需要单独扩展角色模板和持久化设计
- 若要完全自动发布，还需要仓库根目录的 CI 工作流文件；本次会话受 path scope 限制未新增

## 下一步建议

1. 用仓库实际名称和后端域名执行一次正式部署
2. 在平台侧补齐环境变量后，按 `docs/deployment.md` 验证完整流程
3. 如果要持续部署，再新增 GitHub Actions 工作流
