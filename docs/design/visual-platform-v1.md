# 默认外观、主题包与模组素材 V1

后续本地样板已补充预设专属图与可选地图版面坐标，见 [预设视觉样板](preset-showcase.md)。下文为 V1 发布时范围与历史验证，最新本地版本尚未发布 Sites。

已实现西方奇幻默认视觉、模组素材上传与预览、独立主题包导入导出；生图报价/任务接口保留但停用。此次交付不包含支付、充值、真实生图服务商调用和自动出图。

## 玩家看到什么

- 桌面主界面为角色档案、场景与地图、叙事与行动三栏。生命、属性、装备、目标、当前地点、可交谈人物和正在运行的事件时间可见。
- 默认插画覆盖酒馆、林地、水岸聚落、地下遗迹及通用冒险者形象；人物和物品提供协调的徽记。没有作者素材也能完整游玩。
- 场景画面由 Phaser 的独立场景镜头加载、按焦点裁切、渐显，并提供轻微环境光点；原地图和先攻继续使用 Phaser。中文叙事、输入与按钮保留语义 HTML。
- 平板隐藏侧栏，角色/背包入口仍可用；手机把场景放在阅读区上方，地图默认收起，可打开、浮动、拖动与调整大小。减少动态效果的系统偏好同时停用插画渐显与环境光点。
- 插画表达地点类型，不是剧情事实来源；不会据插画自动增加场景对象、人物、怪物或奖励。

## 编辑与复用

创作工坊 → **外观与素材**：选主题、条目、默认类别，上传图片或复用已有素材，调整自定义图片焦点。默认外观有西境旅行志、月下编年史和题材中立的通用星图三套。通用星图默认不展示西方奇幻场景。

替换位置：场景画面、NPC 肖像、玩家形象、装备物品、模组封面、地图相邻路线图标。地图节点布局、可达性和交互规则不由皮肤更改。声音、字体文件、复杂边框贴图和任意 CSS/脚本不在本版开放范围。

主题有独立 `id`、名称、预设配色、标题字体类别、装饰类别和通用素材表，可单独导出为 `.theme.json`，导入其他模组复用。本版按值保存主题快照，主题 ID 用于标识，尚无远程主题市场或自动更新依赖。

模组 `visuals` 包含主题快照、素材池，以及按现有条目 ID 索引的 `scenes` / `characters` / `items` / `map` 槽位，还有 `player` / `cover`。`map` 引用场景 ID；其他槽位校验相应条目存在。槽位存素材 ID、默认类别及焦点。一个素材可以复用在多个槽位，不重复存图。

显示优先级：模组槽位自定义素材 → 主题对应类别素材 → 平台默认图。缺失或无法解码的图片恢复默认显示。旧模组的 `visuals` 可省略，旧存档不需迁移。默认地点类别由地点名称做本地表现层匹配，作者可显式选择覆盖，匹配不参与规则裁定。

## 素材与存档边界

- 来源为平台默认、用户上传或生成素材。默认图属于平台静态资源，不写入每份存档。
- 上传支持 PNG/JPEG/WebP，输入上限 8 MB / 边长 8192。浏览器实际解码，缩到最长边 1200 后转 JPEG；透明区域铺浅纸色。本版不支持透明角色立绘。
- 便携模组只携带内嵌 PNG/JPEG；单图编码上限 240,000 字符，主题与模组素材合计 768,000 字符（750 KB），保存后随草稿、模组、冒险快照和云端存档恢复。导出文件不依赖设备上的临时图片地址。
- 服务端校验格式头、尺寸、大小、素材与条目引用；拒绝远程图片网址、SVG 和脚本。生成来源与 `generation_id` 仅为素材元信息，导入文件不能据此证明支付。
- 当前复用现有 JSON 存储，云端快照总限制仍为 24 MB。大量高分辨率美术与商业图库上线前，应把素材池迁移到内容寻址的对象存储，并加配额和导出打包；无需改变条目槽位或玩法接口。
- 游戏控制器按冒险加载视觉资料并缓存，行动刷新不会每轮重新请求整套图片；读档重新加载。跑团上下文不包含图片数据或皮肤信息，换皮不增加模型 token。

## 后续按图计费接口

`GET /images/capabilities` 明确返回停用状态。`POST /images/quotes`、`POST /images/jobs` 当前统一拒绝，任务查询不存在；不创建订单，不扣款，不调用任何生图提供商。

已定义 `ImageGenerationRequest`、`ImageQuote`、`ImageJobRequest`、`ImageJob`、`ImageProvider` 接口。后续实现必须由服务端保存报价与原请求绑定、价格及有效期，用户明确接受报价后按幂等键创建任务。不得依据客户端的金额或素材来源标记扣款。

商业接入顺序：测真实服务成本与质量 → 设置按张价格/张数并展示 → 接支付与余额预留 → 成功交付结算 → 失败释放预留 → 图像永久入库复用。再次生成算新任务，重复请求与刷新读取不算新图；技术失败不收图费。未确定价格前不显示虚构售价。

## 验证

- 后端全量 796 项通过，新增只覆盖视觉/规则隔离、旧包兼容、恶意/超限素材拒绝、主题引用、导入/独立激活/存读档、停用生图服务等实际边界。
- 云端现有 9 项通过；网站构建与静态检查通过。最后封面继承/焦点调整后重跑相关视觉检查。
- 本轮未运行新的浏览器截图或点击验收；视觉体验是否满意仍待用户体验，不把构建通过写成视觉验收通过。
- 本地 892 份原始会话/存档事实比对一致。发现一个 18.4 小时旧会话触发原有非持久模式 12 小时过期，已从本轮备份恢复，并以 `SESSION_DURABLE=true` 重启本地服务。以后本地启动也应保留此配置，云端本来已启用。

## 默认原创美术

使用 Codex 内置图像生成工具生成，未调用项目已充值的生图 API。资产位于 `app/frontend/public/art/western/`：[tavern.png](/Users/roganic/Desktop/exercise/huanjie-2/app/frontend/public/art/western/tavern.png)、[wilds.png](/Users/roganic/Desktop/exercise/huanjie-2/app/frontend/public/art/western/wilds.png)、[harbor.png](/Users/roganic/Desktop/exercise/huanjie-2/app/frontend/public/art/western/harbor.png)、[ruins.png](/Users/roganic/Desktop/exercise/huanjie-2/app/frontend/public/art/western/ruins.png)、[traveller.png](/Users/roganic/Desktop/exercise/huanjie-2/app/frontend/public/art/western/traveller.png)。`public/art/atlas.svg` 和徽记为代码图形。

共同提示词：

> Use case: stylized-concept. Production background illustration for a Western fantasy narrative RPG. Original hand-painted tempera and etched storybook illustration on subtly aged parchment, refined European medieval fantasy, muted deep teal shadows, warm amber light, antique gold, moss, ivory; detailed yet calm composition, dramatic depth. Wide landscape 1536x1024. Full bleed, NO panels, NO text, NO interface, NO logo, NO watermark, no Asian architecture, no modern objects.

分别追加：

- Tavern: Interior of a quiet medieval roadside tavern, massive dark oak beams, stone fireplace glowing warmly, leaded arched window with blue evening sky, simple wooden counter and empty stools, a pewter tankard and travel journal on foreground table. Unoccupied; no people.
- Wilds: Ancient mossy woodland path winding toward a small ruined stone arch, mountain crags beyond pines, luminous late afternoon mist, a tiny amber wayside lantern. No people.
- Harbor: Medieval European riverside harbor at twilight, timber framed stone houses with steep slate roofs, small stone bell tower, wooden ferry jetty, one warm lantern beside calm teal water, distant misty hills. No people.
- Ruins: Forgotten subterranean medieval vaulted stone crypt and broken archway, worn stone steps descending past columns, very subtle amber braziers illuminating cool teal shadows, moss and stone reliefs, no visible monsters or treasure, no people.

玩家形象提示词：

> Use case: stylized-concept. Production generic adventurer portrait for a Western fantasy RPG, vertical 1024x1536. Hand-painted tempera and finely etched storybook illustration on aged parchment, deep teal and antique gold, subdued ivory highlights, matching medieval illustrated travel journal aesthetic. A lone cloaked traveller seen from behind in three-quarter view with face fully obscured by hood, a travel pack and rolled blanket, rough linen and worn leather, gazing toward far mountain ruins. Gender and ethnicity unspecified, no weapon or class insignia, no text or border, not an identifiable story character. Full bleed image, subject occupies most foreground, a subtle golden circular halo-like cartographic compass motif behind the hood. Elegant atmospheric painterly detail, no cartoon, no modern objects, no Asian elements.
