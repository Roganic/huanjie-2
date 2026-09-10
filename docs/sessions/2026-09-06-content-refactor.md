# 2026-09-06 内容与状态重构

目标：先解决重复定义、状态冲突和真实模组接入边界，再做编辑器和纯文本故事解析。没有引入新的前端引擎或模型调用。

完成内容、接口及限制统一记录于 [正式说明](../content-architecture.md)。本次继续使用已有工作目录，保留前几轮未提交改动与用户存档；重构前源码备份位于 `/tmp/huanjie-before-content-refactor-20260906.tar.gz`。

## 验证

- 相关回归命令：在 `app/backend` 中运行 `.venv/bin/python -m pytest tests/test_module_system_acceptance.py tests/test_modules.py tests/test_module_integration.py tests/test_world_encounters.py tests/test_combat_commands.py tests/test_exploration_guidance.py tests/test_core_gameplay.py tests/test_npc_interaction.py -q`。结果 105 通过。
- 所有运行均以临时 `SAVE_DIR`、`SESSION_STATE_DIR`、`MODULE_DIR` 隔离测试数据，未用测试重置用户实际会话。
- 全量：623 通过、113 失败，无收集错误，日志 `/tmp/hj-audit-final.txt`。保留失败以便继续定位，没有 skip/xfail 掩盖问题。
- 相比上轮全量失败集合，没有新增失败测试；本次涉及的模组 API、故事节点和重复地图相关用例已按真实世界规则迁移。
- 示例流程实际断言：独立激活不改变原角色；自定义装备生效；自定义治疗物品在探索/战斗中消耗一件；进入起点执行事件；双敌人先攻；自定义 XP/掉落；事件和任务奖励只发一次；删去目录中的模组后，存档仍能恢复其内容和进度；读档后对话次数继续累积；无任务的模组正常返回空列表。
- 前端 `npm run build`、`npm run lint` 通过；浏览器检查现有角色的任务状态、实际模组目录与 7 场景/17 人物/1 任务详情，没有修改该角色。
- `uv build --wheel` 成功，检查压缩包包含 `src/content/builtin.json` 和 `routes/combat.py`。修正 setuptools 配置，避免正式包遗漏内容和路由。

## 已知遗留

旧 `models/module.py`/`modules/manager.py` 与 `save_load/` 只保留独立旧格式兼容用途。通用动作、环境技能检定、叙事记忆和历史验收仍有工作；不能把全量 113 个失败都当成测试过时。下一轮按真实接口与已确认规则逐项分类，先补实际缺口，再退役剩余适配代码。

自然语言故事解析目前仅保留 `StoryParser` 输出协议，尚无具体实现。示例与 Schema 是可供后续编辑器采用的真实数据合同，不等于编辑器已经完成。
