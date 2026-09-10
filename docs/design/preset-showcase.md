# 灯笼酒馆预设视觉样板

2026-09-09。本轮只在本地运行与验收，不更新 Sites。目标是让一篇真实可玩的预设形成完整的西方奇幻视觉体验，再把经验推广到其他模组。

2026-09-10 补充：文字版 / 美术版切换已本地实现，规则与验收见 [双游玩布局](play-views.md)。下文“本轮”指 09-09 的样板范围。

## 视觉与交互

以墨绿、旧金、暖羊皮纸为主色：左侧旅人档案，中间场景与区域地图，右侧旅行手记。使用有边距的独立画框、克制的细金线和纸页层次；中文正文使用书卷字体及较宽行距，动作和数值使用清晰的小号文字。

灯笼酒馆、村庄广场、地下城入口、地下通道、幽暗森林、古庙、宝库七个地点各有对应场景画面。酒馆三位 NPC 使用专属肖像并直接发起交谈，移除了行动区重复的交谈按钮。其他 NPC 暂用通用徽记，不把它们描述成已经拥有专属美术。

区域地图采用浅色绘图底纸、方格地点徽记、弯曲道路和金色立体当前位置指针。当前位置与相邻地点高亮，未到达且不相邻的地点隐藏名称。底纸没有道路、地点或任务信息，真正的路网由现有场景出口绘制。地点位置只是版面坐标，不代表战斗站位、距离或额外可达路线。

叙事区以“旅途手记”组织正文，按交谈、行旅、发现、战况等真实命令类型标记记录；规则明细继续折叠。战斗切换为相同配色的先攻队列，展示生命、先攻、当前行动者及可选目标。手机战斗采用双列队列、三列操作按钮，地图在探索时默认收起。

地图拖动、浮动、原位恢复、窗口拉伸、缩放、关闭、旋转指针继续可用；减少动态效果的系统设置继续生效。图标、名称、当前位置指针和点击区域共同随玩家的加减号/滚轮缩放；仅窗口自适应比例被抵消，避免浮窗尺寸改变时默认图标忽大忽小。名称绘制分辨率随放大倍率提高。

## 契约与兼容

- `ArtSlot.builtin` 引用受限的静态素材名，前后端均校验，不接受任意路径。素材按需加载，不随每份存档复制，不放入主持模型上下文。
- 自定义上传素材优先于预设图；主题素材可覆盖默认表现。关闭插画的中立主题不加载西方奇幻预设图。编辑器切换默认类别会清除该槽位的专属默认图，上传和焦点调节仍可用。
- `ModuleVisuals.map_layout` 为场景 ID → `{x,y,label}`，范围为 1000×620 设计画布内的安全区域。服务端验证坐标和场景引用，前端根据可用空间投影并预留指针、标签边距。尚无手工布局的模组继续自动排布。
- 旧灯笼酒馆存档如果没有任何视觉配置，仅在读取视觉接口时获得新默认外观，不替换场景、角色、规则、事件或进度。已有作者视觉快照优先保留。
- 地图坐标目前可通过 JSON 编写；本轮没有新增地图布局编辑器。地图底纸仍是平台默认资源，可替换路线图标接口保持原状。
- 两种游玩布局仍是后续方向：共享规则、存档、命令和进行中的请求，分别组织文字密集模式与场景模式。本轮交付场景模式样板，没有宣称已实现双模式切换。

## 原创资源

资源位于 `app/frontend/public/art/western/`。本轮新增九张，原始生成文件保留在 Codex 图片目录；工程内为副本。生成工具用于制作开发素材，未启用项目的付费生图接口。

| 文件 | 用途 |
|---|---|
| village-square.png | 村庄广场、古井与铁匠铺 |
| dungeon-gate.png | 藤蔓石门、破碎石像和补给箱 |
| dungeon-passage.png | 狭窄地下通道与发光苔藓 |
| ancient-temple.png | 坍塌屋顶的古庙和蓝色祭坛 |
| ancient-vault.png | 水晶照明的石室与带锁宝箱 |
| marcus.png | 白发、独眼、老兵酒保 |
| ayla.png | 银发、竖琴、吟游诗人 |
| hooded-merchant.png | 深色兜帽商人 |
| map-parchment.png | 中央留白、边缘山林纹理的地图底纸 |

场景提示词基调：`Original hand-painted Western medieval fantasy adventure background, wide 1536x1024. Fine tempera brushwork and etched stone details, muted teal shadows, warm ochre, aged ivory highlights, atmospheric painterly realism for an illustrated traveller journal. Full bleed, carefully composed environment, no people or creatures (interactive characters are rendered separately), no text, no readable runes, no UI, no logos, no watermark, no Asian architecture.`

在上述基调后分别加入本表场景的真实描述；入口指定 woodland exterior、shattered stone guardian、supply crate，通道指定 narrow low tunnel、glowing moss，古庙指定 roofless、broken statues、blue altar，宝库指定 single closed chest、rusty iron lock、glowing crystals、few scattered coins。没有把画出来的装饰增补为可操作对象。

肖像基调：`Original Western medieval fantasy character portrait, square 1024x1024, refined tempera painting with delicate etched lines, muted teal shadows, warm ochre and ivory, textured painterly realism, cohesive illustrated traveller journal style, full bleed.` 各人物按上表特征补充，要求 no text/UI/frame/logo/watermark/modern or Asian elements。

地图底纸要求：warm weathered cream parchment、faint contours、painted trees and mountain hatching around outer edges、central 75% mostly empty and low contrast、no buildings/roads/labels/compass/grid。村庄画面包含 stone well、half-timber cottages、blacksmith stall、market、cobblestone lane，禁止文字和人物。

## 本轮验证

详见 `../sessions/2026-09-09-preset-showcase.md`。这是已进行真实点击和截图检查的本地样板，审美满意度仍以用户体验反馈为准。其他预设专属整套美术、全员肖像、装备图库、双模式切换以及商业素材存储/计费不在本轮完成范围。
