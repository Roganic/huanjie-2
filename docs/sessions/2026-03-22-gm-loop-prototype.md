# 2026-03-22 GM Loop Prototype

## 目标

基于现有 backend skeleton 和 V1 规则总纲，实现最小的 "玩家行动 → 结构化裁定 → 叙事占位" 后端闭环。

## 输入

- `app/backend/` 现有 FastAPI 骨架（main.py + health router）
- `docs/rules-core.md` V1 规则内核（统一检定、优势/劣势、DC 档位、结构化裁定结果）
- `docs/ai-architecture.md` 后端模块规划（engine / models / routers 目录约定）

## 做了什么

### 新增文件

| 文件 | 职责 |
|------|------|
| `src/models/__init__.py` | models 包入口 |
| `src/models/action.py` | ActionRequest / ActionResponse Pydantic 模型 |
| `src/engine/__init__.py` | engine 包入口 |
| `src/engine/dice.py` | d20 投骰，支持优势/劣势 |
| `src/engine/resolver.py` | 行动裁定引擎：自动成功分流 + 统一检定 + 结构化结果 |
| `src/routers/action.py` | POST /action 路由 |
| `tests/__init__.py` | 测试包入口 |
| `tests/test_action.py` | 5 个测试：health、auto_success、check、ability override、advantage |

### 修改文件

| 文件 | 改动 |
|------|------|
| `src/main.py` | 注册 action router |

### 实现细节

1. **数据模型** (`models/action.py`)
   - 请求：scene_id, actor, intent, approach, ability(可选), dc(可选), advantage(可选)
   - 响应：action_summary, resolution_type, check, outcome, effects, narration

2. **裁定引擎** (`engine/resolver.py`)
   - 自动成功分流：基于关键词（look, walk, talk 等）判断是否跳过检定
   - 统一检定：`1d20 + 属性调整值 + 熟练加值` vs DC
   - DC 档位：10 / 15 / 20（对应 easy / medium / hard）
   - 属性推断：从 approach 文本中的关键词推断使用哪个属性
   - 结果包含 outcome（success/failure）、effects 列表、narration stub

3. **骰子** (`engine/dice.py`)
   - 标准 d20，支持优势（取高）和劣势（取低）

4. **API 路由** (`routers/action.py`)
   - `POST /action`，接收 ActionRequest，返回 ActionResponse

## 验证结果

```
$ python3 -m pytest tests/ -v
5 passed in 0.40s
```

覆盖场景：
- 健康检查仍可用
- 自动成功路径（intent 包含 "look"）
- 检定路径（pick lock，验证 ability=dex, dc=15 等结构化字段）
- 显式指定 ability 覆盖自动推断
- 优势标记正确传递

## 刻意没有做的内容

- **没有真实角色数据**：使用硬编码的默认属性调整值和熟练加值
- **没有 GM agent / LLM 调用**：narration 是简单模板字符串，不涉及模型调用
- **没有会话状态**：每次请求独立，不追踪 HP、物品、场景进度
- **没有战斗系统**：没有先攻、AC 命中、伤害结算
- **没有状态效果系统**：effects 字段仅做占位，不实际修改角色状态
- **没有复杂规则**：没有职业、法术、反应链
- **没有持久化**：纯内存，无数据库

## 未决问题

- 角色数据从哪里来？需要一个最小的角色定义结构
- 自动成功 vs 需要检定的分流，后续是否由 LLM 判断而非关键词匹配？
- narration 何时接入 LLM？需要定义 GM agent 的输入输出协议
- effects 是否需要实际回写到角色/场景状态？需要会话状态模块

## 下一步建议

1. 定义最小角色数据结构，替换硬编码属性
2. 前后端联调（`frontend-backend-wireup` 任务）
3. 接入 LLM 生成 narration（需要 `src/agent/` 模块）
4. 引入会话状态，让 effects 实际影响后续检定
