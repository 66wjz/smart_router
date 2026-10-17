# 测试反馈日志

> 记录 6.3a / 维护迭代的每条反馈，分类（A 线 bug / B 线设计调整）必填。
> 编号规则：FB-{n} 递增。

| 编号 | 日期 | 反馈 | 分类 | 状态 | 处理 |
|------|------|------|------|------|------|
| FB-001 | 2026-08-09 | 上游源支持批量 API Key，自动轮询分摊流量（Key 池方案 A） | B 线-大（新功能） | 已实现+已部署 | CH-003：Key 池模块 + 适配器改造 + 探测 + API + 前端，已验证并部署生产 |
| FB-002 | 2026-08-09 | NVIDIA 上游单个 Key 请求会长时间挂起不返回 | A 线（设计缺陷升级 B 线） | 已修复 | 超时/错误语义改为 Key 级失败换 Key；超时收紧 12s/6s；修复 httpx 脏连接复用问题 |
| FB-003 | 2026-08-09 | 上游源页面要能选择模型做测试 | B 线（新功能） | 已实现+已部署 | CH-004：新增 test 接口 + 前端「测试选中模型」按钮 |
| FB-004 | 2026-08-09 | 生成随机 Key 会刷新页面；应自动生成并提供重新生成按钮 | A 线 bug + B 线交互 | 已修复 | BaseButton 加 type="button"（根因）；新增弹窗自动生成 Key +「重新生成」按钮 |
| FB-005 | 2026-08-09 | API Key 操作列按钮（修改/禁用/复制/删除）粘连 | B 线-小 | 已修复 | 操作列 flex + gap 8px |
| FB-006 | 2026-08-09 | 全系统按钮/输入框/下拉框高度不统一 | B 线-小 | 已修复 | --control-height 36→32px 对齐 Element Plus 默认 |
| FB-007 | 2026-08-10 | opencode 类上游同站不同模型绑定不同协议/端点，按协议拆多源太麻烦 | B 线-大（新功能） | 已实现（待部署+体验确认） | CH-011：models 条目升级为 {name, protocol?}，转发/测试按模型级协议分发；第一期仅 openai/anthropic 出站 |
| FB-008 | 2026-08-10 | opencode go 频繁掉线（500/TLS 中断抖动），直连单模型时无请求级容错 | B 线-大（新功能） | 已实现+已部署（待体验确认） | CH-012：智能重试开关（源级默认关）；预算制重试（Key 数+2）、同 Key 退避+jitter、5xx 可重试、X-Served-By/X-Retry-Count |
| FB-009 | 2026-08-10 | Base URL 拼接黑盒；API Key 拿到手不知如何接入 | B 线-小 | 已实现+已部署（待体验确认） | CH-013：URL 实时预览 + 格式改"默认协议" + Key 接入说明弹窗（地址/Key/可用模型/curl/SDK 示例） |
| FB-010 | 2026-08-10 | 生产添加上游源报 500（NOT NULL constraint failed: up_upstream.api_key） | A 线 bug | 已修复+已部署 | 根因：pydantic model_dump 显式带 api_key=None，repo `data.get("api_key", "")` 对显式 None 不生效 → INSERT NULL 违例；修为 `or ""`；本地复现→修复→验证（添加成功+Key 池加载 2 Key）后部署 |
| FB-011 | 2026-08-10 | 接入说明弹窗「复制示例」按钮位置不好看 | B 线-小 | 已修复+已部署 | 复制按钮移到对应示例标题行右侧（usage-label-row 布局） |
| FB-012 | 2026-08-10 | 模型协议下拉默认态显示"请选择"而不是"继承（源协议）" | A 线 bug（CH-011 实现缺陷） | 已修复+已部署 | 根因：el-select 把空串 '' 视为空值显示占位符；改为 'inherit' 哨兵值，保存时映射回无 protocol |
| FB-013 | 2026-08-10 | 要用 gpt-5.6-luna（responses 协议）+ 出入站完整协议矩阵（Codex 场景） | B 线-大（新功能） | ✅ 全部实现+已部署（2026-08-11 归档） | CH-014 responses 出站 + CH-009 anthropic 入站 + CH-010 responses 入站；3×3 矩阵收齐（注：gpt-5.6-luna 受 opencode 区域限制，与本系统无关） |
| FB-014 | 2026-08-11 | API Key 管理及接入说明的复制按钮全部复制不成功 | A 线 bug | 已修复+已部署 | 根因：navigator.clipboard 仅在安全上下文（HTTPS/localhost）可用，生产纯 HTTP 下 undefined 静默失败；新增 utils/clipboard.ts（execCommand 降级）替换全部 6 处调用 |
| FB-015 | 2026-08-11 | /v1/models 返回上游全量目录而非已配置的 10 个模型 | A 线 bug | 已修复+已部署 | 根因：生产（及本地）models.py 为旧版实时代理拉取；重写为只返回已配置模型（分组+启用过滤）；生产验证 13 个（10 配置+3 聚合） |
| FB-016 | 2026-08-11 | 直连 opencode/kimi 已配置模型 503"所有模型均不可用" | B 线-小（A 升级，设计缺口） | 已实现+已部署（CH-015） | find_model_upstream 只查路由规则候选；补第二层"上游已配置模型"查找；生产验证 mimo-v2.5/kimi-for-coding 直连 200、free Key 越权 403 |
| FB-017 | 2026-08-11 | 上游源不能多选分组（Key 侧经查已支持多选） | B 线-大 | ✅ 已实现+已部署（CH-016，2026-08-11 归档） | groups JSON 数组 + 集合交集权限；本地 4 用例 + 生产临时双分组实测通过 |
| FB-018 | 2026-08-11 | 侧边栏平铺误导：路由规则/聚合模型名/延迟面板是聚合路由职能，不应与中转站职能并列 | B 线-小 | ✅ 已实现+已部署（CH-017，2026-08-11 归档） | 侧边栏加"智能路由"分组；仪表盘双职能重设计（设计稿确认后实施，含一轮等高修复）；生产视觉验证通过 |
| FB-019 | 2026-08-11 | 智能路由应为可折叠一级菜单（点击展开二级），而非分组标题 | B 线-小（CH-017 交互迭代） | 已实现+已部署 | BaseSidebar 新增可折叠分组能力（icon+chevron+缩进二级项，默认展开）；生产视觉验证通过 |
| FB-020 | 2026-08-12 | messages/responses 入站丢图片 + 三协议行为不统一：Claude 模式发图看不到图，Responses 模式发图空回复，deepseek 不支持图时 messages/responses 报错格式客户端无法解析（表现为超时无反馈），推理模型（mimo-v2.5）reasoning 内容在 messages/responses 入站被丢弃 | A 线 bug | ✅ 已修复+已部署+已归档（CH-018，2026-08-12；用户实测确认通过） | 一期：入站转换器补图片块映射（anthropic image / responses input_image → image_url）。二期：① 三入站错误统一为各自协议标准格式（openai `{"error":{...}}` / anthropic `{"type":"error","error":{...}}` / responses `{"error":{...}}`）治"超时无反馈"；② anthropic 非流式补 reasoning→thinking 块、流式补 thinking_delta；③ responses 非流式补 reasoning item、流式补 reasoning_summary_text.delta；兼容上游两种推理字段（reasoning_content / reasoning）。 |
| FB-021 | 2026-08-12 | 按 skill V5.2 新规则补齐项目流程缺口：无脱敏配置模板、.gitignore 未覆盖密钥/日志/缓存、_changes/README 缺长期台账 | B 线-小（流程补齐） | ✅ 已同步+已归档（FB-021，2026-08-12） | 新增 config.example.yaml（脱敏模板）；.gitignore 对照 skill 模板增强；_changes/README 补长期台账区；README/变更记录同步 |
| FB-022 | 2026-10-16 | CH-019 部署后中转站上线即故障：/v1/chat/completions 全 500（另一 AI 未完成实施验证即部署） | A 线 bug（部署不一致 + 新代码缺陷） | 已修复+已部署 | 根因三处：①部署清单漏传 app/upstream/ 三适配器（新 ModelHealth 双参签名 vs 旧调用必炸）；②迁移脚本写死旧机 /root/miniconda3 路径致 SQL 06 静默未执行；③前端传 frontend_dist 而 unit 指向 frontend/dist 且未 daemon-reload。修复：md5 全量比对补齐 3 文件（先备份 backup_app_20261016_195621+DB）、venv python 补跑 SQL 06（幂等）、unit 改指+reload；另修新代码 usage_repo.py `with int` 落库假错（本地+服务器同步改）；retry 超时热调整 response 20→60 / first_chunk 8→30（dsh 聚合入口实测 20~40s）。验证：chat 非流式×3/流式/messages/usage 落库/新前端全通 |
| FB-023 | 2026-10-17 | 聚合模型需要像上游源一样「每组自己管探测」，且探测单元不能重复：多个聚合组共用的模型只探一次；另需支持夜间/周末不探测；探测失败不应把唯一 Key 打进冷却；希望记录各家额度消耗 | B 线-大（新功能） | ✅ 已同步+已归档（CH-021，2026-10-17） | 聚合组独立探测（新表 agg_probe_config，4 端点）+ 探测单元全局去重（规则∪别名∪聚合成员）+ 探测时段（星期/时段窗口/跨夜 + 快捷模板）+ 两档排序（stable/latency，全 down 兜底）+ 探测失败默认不计 Key 冷却 + 用量按「源×真实模型」记账（`log_usage.upstream_model` + by-unit）。验证 24+19+32+8 全通过，前端构建通过，浏览器实测通过。受影响文档：数据库设计 / API契约 / 接口文档 / 架构设计 / 系统核心流程 / 功能清单 / 五列矩阵 / README / 变更记录 |
| FB-024 | 2026-10-17 | 想用假数据实际感受聚合模型与探测配置；仪表盘页面需要重新设计（信息密度太低） | B 线-大（新功能 + 设计调整） | ✅ 已同步+已归档（CH-022，2026-10-17） | 演示环境（`SMART_ROUTER_DB` 独立 demo.db + seed/clear/run_demo 三脚本，4 上游/3 聚合组三态/1392 条用量/未合并异名模型）+ 仪表盘重设计（健康条/5指标/7天SVG趋势/上游贡献占比/上游卡片/聚合组概览/待关注）；顺带修复聚合名误入探测计划、今日统计用错时间字段、全局 SVG 尺寸压扁图表三处问题。受影响文档：API契约 / 接口文档 / 需求规格 / 系统核心流程 / 功能清单 / 五列矩阵 / README / 变更记录 |
