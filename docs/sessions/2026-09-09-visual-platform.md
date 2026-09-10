# 视觉平台 V1 交付记录

## 目标与结果

按用户确认的方案实现西方奇幻默认外观、通用主题与可替换素材，保留未来按张收费的生图接口。本轮已发布到 https://huanjie-adventures.bigbiggod.chatgpt.site ，保持所有者私有访问。功能范围与素材提示词见 `../design/visual-platform-v1.md`。

## 发布证据

- Sites project：`appgprj_6aa0290ab8248191a0772a169e8bcc0a`
- 最终版本：9；`appgprj_6aa0290ab8248191a0772a169e8bcc0a~appgver_d3c0bd43ad708191b7b387a76d5f6149`
- 来源提交：`f5a5a8f36b59797e407700c293da9f6cd31ba7b5`
- 发布：`appgdep_6aa10200a258819192df22d467032419`；终态 `succeeded`；环境修订2。
- 第8版发布后发现隐藏/浮动地图样式优先级冲突，修复后重新构建、推送及发布第9版。没有把第8版当作最终交付。
- 独立发布目录：`/var/folders/32/7b2_5pds57701rzzwvtc6f6h0000gn/T/huanjie-site-source-OiwzAx`；主工作区前端源码与最终发布来源逐文件相同。
- 归档：`/tmp/huanjie-live-site-v9.tar.gz`；源码与原始生成图已落入工作区，发布归档不含密钥或本地存档。

## 验证与费用

后端完整796项通过，最后封面继承调整后的5项视觉边界复测通过；云端9项、最终网站构建及lint通过。记录：`/tmp/huanjie-visual-tests.log`、`/tmp/huanjie-visual-final-tests.log`、`/tmp/huanjie-visual-cloud-tests.log`、`/tmp/huanjie-visual-stage-build.log`、`/tmp/huanjie-visual-stage-lint.log`。

本轮未进行新的浏览器截图、点击或上传文件交互验收。界面由源码检查与编译检查覆盖，用户视觉验收仍待体验。不得把原第7版浏览器验收当作新界面的验收。

未调用项目付费模型进行新一轮试玩，也未配置实际生图提供商。默认素材由 Codex 内置图像生成工具创建，未来平台生图入口停用，不创建订单、不收费。

## 本地数据保留

备份目录：`/var/folders/32/7b2_5pds57701rzzwvtc6f6h0000gn/T/huanjie-before-phase2-_cs4rfqc`。

首次核对发现一个18.4小时未访问会话被原非持久模式12小时TTL移除；从备份原样恢复，未覆盖其他文件。以 `SESSION_DURABLE=true` 重启后再次比对，892份事实一致，只有默认会话更新时间变化。本地后端最终PID10986；后续重启仍需保留持久开关。启动/核对辅助脚本为 `/tmp/huanjie_phase2_deploy.py`。

## 接续

先收用户对新版实际界面的反馈。高分辨率图库/大量素材需先迁移为对象存储引用；商业生图在确认服务商、真实成本、按图报价、支付与失败退款后再启用。不因目前留了接口就自动开通付费调用。
