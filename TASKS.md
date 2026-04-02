# TASKS

使用方式：

- 每个任务尽量标注负责范围，方便多 agent 并行
- 如果某个共享文件正在被集中修改，可在任务后标记 `occupied`
- 任务描述保持短句，细节写入对应 `docs/sessions/`
- 如果一个任务将进入独立 worktree，建议在任务后加 `wt`

## Now (AI 实时叙事阶段)

- 接入 Kimi API 实现 AI 叙事生成 `backend`
- 设计叙事提示词模板与上下文管理 `backend`
- 前端展示 AI 生成的叙事文本 `frontend`

## Next

- 记忆/RAG 初步探索 `backend`
- 增加结构化规则数据格式
- 增加试玩流程和样例战役

## Completed (里程碑二功能完整性)

- ✅ 战斗系统完整闭环 `backend`
- ✅ 角色系统数据持久化 `backend`
- ✅ 装备系统：装备武器/护甲后战斗和 AC 正确更新
- ✅ 物品使用：治疗药水消耗和 HP 恢复
- ✅ 角色成长：战斗获得 XP、达到阈值后升级
- ✅ 职业特性：战士 second_wind/action_surge、盗贼偷袭
- ✅ 战斗先攻：initiative_order 正确排序，current_turn 正确推进
- ✅ 地图系统：场景切换后 current_node 和 explored_nodes 正确同步
- ✅ 法师施法：法术槽消耗、伤害/治疗效果

## Later

- 增加提示词实验和模型对比
- 扩展更多职业和法术

## Blocked

- 暂无
