# AI 跑团测试模型初选

核对日期：2026-09-07。按官方规格和价格筛选，尚未做真实模型跑团对比。建议先选 **Qwen3.7-Flash**，关闭思考模式；用 **Qwen3.8-Flash** 做质量对照。均复用本项目的 Function Calling 接口。

| 候选 | 北京区每百万输入 tokens | 每百万输出 tokens | 适用判断 |
| --- | ---: | ---: | --- |
| Qwen3.7-Flash（短上下文 ≤32K） | ¥0.2 | ¥0.8 | 首选低成本协议、玩法、对话测试；可固定 `qwen3.7-flash-2026-07-15` 快照 |
| Qwen3.8-Flash | ¥0.8 | ¥2.7 | 同服务商的效果对照；不能仅凭新版名称断言跑团更好 |

两款均列明支持 Function Calling。3.7 随单次输入长度分档，不能把 ≤32K 的价格用于更长请求。新加坡、其他地域、账号优惠与缓存价格不同。以上为模型专页原价，不计缓存优惠和免费额度。

来源：[Qwen3.7-Flash 模型规格与价格](https://help.aliyun.com/zh/model-studio/qwen3-7-flash)、[Qwen3.8-Flash 模型规格与价格](https://help.aliyun.com/zh/model-studio/qwen3-8-flash)。官方汇总页与模型专页的部分新型号价格存在差异，本表采用模型专页；充值/实际调用前仍以账号控制台计费为准。

## 大概需要多少钱

**估算假设**：一次玩家回合所有模型调用合计输入 6,000 tokens、输出 600 tokens；每个请求处于对应短上下文档位；不计缓存及赠送额度。这里已经把多次模型调用相加，不是单次调用成本。

- 3.7：每回合约 `6000×0.2/1000000 + 600×0.8/1000000 = ¥0.00168`，1,000 回合约 **¥1.68**。
- 3.8：同样假设每回合约 **¥0.00642**，1,000 回合约 **¥6.42**。

这不是实测账单，也不是系统保证的上限。历史长度、工具查询次数、返回长度和失败尝试都会改变消耗；实现已记录供应商返回的每次 usage，配置后按实际消耗修正。

## 其他候选与排除原因

- 角色扮演专用 `qwen-flash-character` 虽适合人物表现，但官方模型页注明不支持 Function Calling，暂不作为整个 GM 的默认模型。之后若拆独立叙事模型再评估。[官方规格](https://help.aliyun.com/zh/model-studio/qwen-flash-character)
- DeepSeek 支持兼容接口及工具调用，可作为后续替代服务。此次旧价格路径实时打开回到了入门页，搜索缓存与当前页面不一致，因此未把旧缓存价写进预算。[入门文档](https://api-docs.deepseek.com/)、[工具调用](https://api-docs.deepseek.com/guides/tool_calls/)
- Kimi 的定价页已指向 K3 等新版，当前可读取的详情没有完整价格表，未沿用旧 K2.5 价格冒充现价。[官方定价入口](https://platform.kimi.com/docs/pricing/chat)

## 接入注意

按账号业务空间和地域复制服务地址，不在程序中猜测地址。北京区当前官方 Function Calling 示例采用 `https://{WorkspaceId}.cn-beijing.maas.aliyuncs.com/compatible-mode/v1`，本项目配置需追加 `/chat/completions`；其他地域应使用相应控制台地址。[工具调用与非思考模式示例](https://help.aliyun.com/zh/model-studio/qwen-function-calling)

密钥放在后端 `.env.gm`，已实现的配置页面只更换服务配置，游戏规则和存档不需要随模型更换。选用“OpenAI 兼容”只表示采用兼容协议，并不表示请求发送到 OpenAI。

## 2026-09-08：切换免费 GLM

用户确认百炼免费额度已耗尽，当前本机配置切换为 `glm-4.7-flash`，接口为 `https://open.bigmodel.cn/api/paas/v4/chat/completions`，接口类型 `glm`。原百炼配置已在仓库外以 0600 权限备份；新密钥仅在忽略提交的后端配置中。

[官方定价](https://bigmodel.cn/pricing)当前将 GLM-4.7-Flash 标为免费；普通 GLM-4.7 与 FlashX 收费。免费不是永久可用性承诺。

按[官方工具调用说明](https://docs.bigmodel.cn/cn/guide/capabilities/function-calling)，GLM 使用 `tool_choice=auto`，关闭思考，省略并行工具参数；后端依然只接受单个结构化工具调用，拒绝纯文字冒充执行结果及多工具执行。模型设置页已增加智谱选项。

连通验收尚未通过：官方端点返回 HTTP 429 / 1305「该模型当前访问量过大，请您稍后再试」。终端代理曾超时，直连能取得该明确服务端错误；本地服务为该官方域名使用 NO_PROXY。31 项 GM 回归、前端构建与 lint 通过；未以模拟测试替代真实对话验收。


## 2026-09-09 实测补充

- 官方免费列表确认 GLM-4-Flash-250414 支持结构化输出：[模型说明](https://docs.bigmodel.cn/cn/guide/models/free/glm-4-flash-250414)。GLM-4.5-Flash 已声明下线后转到 4.7，不能当独立长期备用：[下线说明](https://docs.bigmodel.cn/cn/guide/models/free/glm-4.5-flash)。
- 4.7/4.6V 当前有 429/1305；legacy Flash 可用性较好，隔离浏览器两次成功调用分别约 2.24/2.34 秒，但人工复核发现一句 NPC 回复站在玩家视角，不算质量通过。
- 4.5 的简单工具问候成功，完整 NPC 上下文却返回普通文字并忽略工具，主机正确拒绝这种结果；没有通过普通文字伪造动作已执行。
- 模组解析多次出现超时/格式不符，结构化 JSON 方案取得真实草稿，但语义仍有提前完成任务、无条件结局等问题。需要编译边界改进与真实内容复验。
- 原始授权密钥仍仅保存在忽略的本地配置；未知备用密钥未向猜测的平台试投。
