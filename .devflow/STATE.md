# 项目流程状态

> **当前版本：v5.2.4**（2026-10-22 全量部署上线 10.10.0.2:10002；v5.2.1 = CH-034/CH-036/CH-037/CH-038；v5.2.2 = CH-039 + CH-040；v5.2.3 = CH-041；v5.2.4 = CH-042~CH-048 列表统一化 + FB-041 双栈监听修正；主仓库 GitHub：https://github.com/66wjz/smart_router，原 Gitee 仓库已转私有）

- 项目名称：Smart Router（AI 模型智能路由代理）
- 项目路径：E:\80-project_dev\04_smart-router(starting)
- 流程路径：full-route（正式开发，2026-08-09 启动 v5 重构管控）+ 维护迭代（CH-001~007 已实现部署）
- 技术栈：FastAPI + Vue3 + SQLite
- 项目规模：M
- 创建时间：2026-08-07（v4 追溯补建）；2026-08-09（v5 重构重启管控）
- 当前阶段：维护迭代（v5 六阶段已完成上线）
- 当前阶段状态：in_progress
- 上次更新：2026-10-22（v5.2.4 全量部署上线 + 生产用量日志清理 + FB-041 双栈监听修正；列表统一化 CH-042~048 已全部归档，待提交）

## 补建说明

> 项目 v1~v4 未经 fullstack-dev-flow 流程管控开发（无 .git、无过程文档），
> 2026-08-07 追溯补建状态管控文件（历史阶段标记 done，门禁无法追认）。
> 2026-08-09 用户确认对项目进行 v5 重构（Vue3 前端 + SQLite + 后端分层），
> 流程管控从 stage-1 重新启动（需求文档基于 v4 现状 + v5 重构决策新写）。

## 维护迭代记录

| 编号 | 内容 | 状态 | 部署 |
|------|------|------|------|
| CH-001~008 | 上游禁用/编辑优化/Key池/交互优化/模型管理/测试修复/批量操作/分组管理 | ✅ 已归档（2026-08-10 攒批） | 生产 |
| CH-011 | 模型级协议覆盖（P3 出站第一期） | ✅ 已归档（2026-08-10 攒批） | 生产 |
| CH-012 | 智能重试（上游源级容错开关） | ✅ 已归档（2026-08-10 攒批） | 生产 |
| CH-013 | 接入体验优化（URL 预览 + 协议文案 + Key 接入说明） | ✅ 已归档（2026-08-10 攒批） | 生产 |
| CH-014 | responses 出站适配器（协议矩阵出站第三块） | ✅ 已归档（2026-08-10 攒批） | 生产 |
| CH-009 | anthropic 入站（/v1/messages） | ✅ 已归档（2026-08-11） | 生产 |
| CH-010 | responses 入站（/v1/responses，Codex 场景） | ✅ 已归档（2026-08-11） | 生产 |
| CH-015 | 透传查找纳入已配置模型（FB-016 升级；同批 FB-014 复制降级 / FB-015 models.py 修复） | ✅ 已归档（2026-08-11） | 生产 |
| CH-016 | 上游源多分组（权限判断改集合交集） | ✅ 已归档（2026-08-11） | 生产 |
| CH-017 | 侧边栏"智能路由"分组 + 仪表盘双职能重设计 | ✅ 已归档（2026-08-11） | 生产 |
| CH-018 | 三协议入站行为统一修复（图片透传 + 错误格式 + 推理 reasoning；FB-020） | ✅ 已归档（2026-08-12，用户实测通过） | 生产 |
| FB-021 | 项目补齐 V5.2 流程缺口（config.example.yaml 脱敏模板 + .gitignore 增强 + _changes/README 长期台账） | ✅ 已同步+已归档（2026-08-12） | 仓库 |
| CH-019 | 同名模型自动聚合 + 模型级禁用/拖拽排序 + 三层用量统计（B 线-大） | 🔶 一期已上线并修复部署事故（FB-022）；二期（可控聚合 + 拖拽）已实现+本地验证，**待用户授权上线** | 一期生产 / 二期本地 |
| CH-020 | 异名模型聚合（归一化建议 + 手动组合）+ 后台信息架构重组 + 拖拽体验修复（B 线-大） | ✅ 已实现+本地验证（2026-10-16），已归档；**未部署，待用户授权上线** | 本地 |
| CH-021 | 聚合模型独立探测（探测单元全局去重）+ 探测时段（星期/时段窗口/跨夜）+ 两档智能排序 + 探测与 Key 冷却解耦 + 用量按「源×真实模型」记账（B 线-大） | ✅ 已实现+本地验证（2026-10-17），已归档；**未部署，待用户授权上线** | 本地 |
| CH-022 | 演示数据环境（独立 demo.db + seed/clear/run_demo）+ 仪表盘重设计（健康条/5指标/7天趋势/上游贡献/上游卡片/聚合组/待关注）+ 修复聚合名误探测、今日统计口径、SVG 尺寸三处问题（B 线-大） | ✅ 已实现+本地验证（2026-10-17），已归档；**未部署，待用户授权上线** | 本地 |
| CH-023 | 聚合模型统一（`agg_unified`：static/rule 同一实体）+ 探测模板（`agg_probe_template`，模板优先不可覆盖）+ rule 聚合纳入探测计划（候选并集）+ 探测排班表（按小时/按星期）+ 信息架构归位（延迟面板/路由参数拆分）+ 保留 rule 动态权重排序（B 线-大） | ✅ 已实现+本地验证（2026-10-17），已归档；**未 push、未部署，待用户授权上线** | 本地 |
| CH-024 | rule 聚合的真实路由绑定（`agg_unified.rule_bindings`：规则子集 + 候选子集，三分语义 `null/[]`=全跟随 / `[{rule,candidates:null}]`=规则子集 / 显式候选子集）+ 新建聚合类型选择 + 绑定编辑器 + 规则删除联动清理 + 失效绑定检测（B 线-大） | ✅ 已实现+本地验证（2026-10-17），已归档；**未 push、未部署，待用户授权上线** | 本地 |
| CH-025 | 请求可观测性与入站健壮性：请求上下文日志（轮转文件 `logs/smart-router.log` 10MB×5 + `GET /admin/api/logs` 网页读取 + `sk-` 脱敏）+ 三入站请求体校验（畸形请求 400，消灭裸 500）+ 全局异常兜底（按协议返回规范错误体）+ `estimate_tokens` 等对 null 的防御 + 新建聚合保存按钮卡死修复 + 复制 Key 去确认框（B 线-中 / A+B 混合） | ✅ 已实现+本地验证（2026-10-18），已归档；**已 push，未部署，待用户授权上线** | 本地（代码已推送仓库） |
| CH-026 | 代码治理与组件化（B 线-大，纯重构行为零变更）：超长文件拆分（`Aggregated.vue` 1347→520、`Upstreams.vue` 1056→215、`Dashboard.vue` 688→395、`config.py` 1019→208 门面+4 mixin、`anthropic_adapter` 791→352、`responses_adapter` 695→311）+ 基础组件补齐落地（BaseConfirm/BaseModalFooter/BaseHint/BaseNotice/BasePagination）+ 硬编码色值令牌化（`--chart-*`，修正 `--accent-yellow`→`--accent-amber`） | ✅ 已实现+本地验证（2026-10-18），已归档；**未 push、未部署，待用户授权上线** | 本地 |
| CH-027 | 界面一致性治理 + 流式响应头超时（B 线-小 + A 线）：四页新增按钮统一右上角（`BaseSection #actions`）+ 区块保存按钮统一左下角 + 按钮尺寸统一 `size="sm"`（热重载漏写 size 为根因）+ 弹窗底部统一 `BaseModalFooter` + 侧边栏导航项固定高度 36px 去抖动 + 三适配器 `try_stream` 补 `response_timeout`（等响应头阶段，与非流式对齐） | ✅ 已实现+本地验证（2026-10-18），已归档；**未 push、未部署，待用户授权上线** | 本地 |
| CH-028 | 后台交互补齐 + 聚合拖拽排序（A 线 + B 线-中）：分组管理「+ 添加分组」移右上角并改 primary 配色 + 全局容错三段表单 `label-width` 统一 160px（保存按钮对齐）+ 规则/别名候选模型改读库接口 `listSourceModels`（不再依赖上游可达）+ YAML 编辑改独立卡片 + 弹窗修改 + 聚合列表拖拽排序（`sys_setting.aggregation_order` + `PUT /admin/api/aggregations/order`） | ✅ 已实现+本地验证（2026-10-18），已归档；**未 push、未部署，待用户授权上线** | 本地 |
| CH-029 | 部署前收尾（A 线 + B 线-小）：`seed.py` 补齐增量 01~08（修全新环境缺 `up_upstream_key` 表与 4 列导致启动崩溃）+ `drop_all` 补全 13 张表 + 支持 `SMART_ROUTER_DB` + 版本号统一 v5.2.0（run.py / STATE / pyproject / package.json）+ `start.bat` 指向 v5 + 数据库设计 SQL 清单与 sys_setting 键补全 + API契约修正拉取模型实现方式 | ✅ 已实现+本地验证（2026-10-18），已归档；**未 push、未部署，待用户授权上线** | 本地 |
| CH-030 | 清理 v4 遗留 + 登记待办 + 补文档（B 线-小）：删除 `router.py` / `core/` / `upstream/` / `admin/` / `.streamlit/` / `config.example.yaml` / `test_router.py`（实测 0 活引用）+ 需求规格新增第九节「待完善事项」登记 `auto_same_name` 开关缺口 + 补 `smart-retry` 的 API契约/接口文档 + README 文档索引清理 | ✅ 已实现+本地验证（2026-10-18），已归档；**未 push、未部署，待用户授权上线** | 本地 |
| CH-031 | 仓库迁移 GitHub + 历史隐私清洗（B 线-小）：`git-filter-repo` 替换历史中 CH-016 硬编码的管理员密码与客户端 Key（已双备份）+ 移除内嵌明文密码的 Gitee remote + 提交作者邮箱脱敏为 noreply + 全历史复扫 0 命中 + HEAD 树对象与清洗前一致 + 新远端 GitHub | ✅ 已实现（2026-10-18），已归档；**已 push GitHub，未部署** | 本地（已推送 GitHub） |
| CH-032 | JWT 签名密钥动态化（B 线-小）：删除源码硬编码 `JWT_SECRET`，改为 `SR_JWT_SECRET` 环境变量 > `sys_setting.jwt_secret` > 首次启动自动生成并落库；进程内缓存 + 降级容错；旧密钥签发的 token 全部失效 | ✅ 已实现+本地验证（2026-10-18），已归档；**已随 v5.2.0 部署上线** | 生产 |
| — | **v5.2.0 全量部署上线**：CH-020~CH-032 累计 13 项一次性上线（含 CH-023 聚合统一 + CH-026 组件化拆分 + CH-029 建库修复 + CH-031 仓库迁移 + CH-032 JWT 动态化） | ✅ 已部署 10.10.0.2:10002（2026-10-18），全端点复验通过 | 生产 |
| CH-033 | 静态聚合补入 `/v1/models`（A 线）+ 自动发现聚合支持「移除」（B 线-小） | ✅ 已实现并部署生产（2026-10-18） | 生产 |
| CH-034 | 聚合模型独立分组（聚合作为权限门面，static / rule 统一）：`agg_unified.groups` + 聚合级权限校验 + `/v1/models` 按聚合分组过滤 + 前端分组配置 | ✅ 已实现+本地验证 + **已部署生产**（2026-10-18），门面语义生产实测通过 | 生产 |
| CH-036 | 同名模型自动聚合开关（默认关闭）+ CH-033 残留空壳聚合清理 + CH-034 语义收尾 | ✅ 已实现+本地验证 + **已部署生产**（2026-10-18），开关实测 false、无自动发现残留 | 生产 |
| CH-037 | 出站消息角色规范化（developer → system）：修复 DSH 接入后三成员全 400 → 503 | ✅ 已实现+本地验证通过 + **已随 v5.2.1 部署上线**（2026-10-19） | 生产 |
| CH-038 | 请求详情可观测性（详情宽表 + 三栏对比抽屉 + 缓存 token + 重试链 + 断连 499 + 定期清理）：`log_usage` 补 3 列、新表 `log_usage_detail`、`GET /usage/logs/{id}`、`GET/PUT /config/usage-detail`、前端 Token 三段式与「尝试」列 | ✅ 已实现+本地验证 48 项全通过 + 7 套回归通过 + **已随 v5.2.1 部署上线**（2026-10-19），冒烟实测详情表/三列/设置端点全部就位 | 生产 |
| CH-039 | 流式 usage chunk 按客户端意图透传（修复 DSH 显示 `0 tok/s` / 上下文 `0%`）：`_forward` 增加 `client_wants_usage` 参数，包装函数不再用 `injected_usage` 判断是否剥离；顺带加固部署脚本排除规则（挡 `.tmp_*` 与 `*.db`） | ✅ 已实现+本地验证 19 项通过 + 7 套回归通过 + **已部署生产**（2026-10-20 00:20，备份 backup/20261020-002036）+ **已提交推送 GitHub**（v5.2.2） | 生产 |
| CH-040 | 上游「HTTP 200 + 错误包」误判为成功：新增 `_extract_wrapped_error` / `_parse_sse_error_line`，流式首包与流式过程、非流式 200 分支均按失败识别并切候选；聚合模型首成员错误包现在会自动切到下一成员 | ✅ 已实现+本地验证 36 项通过（含 agg_unified 2 成员切换）+ 离线回归 7 套通过 + **已随 v5.2.2 部署上线**（2026-10-21 00:33，备份 backup/20261021-003244），部署后生产日志实测拦截到错误包并触发切候选 | 生产 |
| CH-041 | 请求过滤引擎（Pre-flight Filter）：`filter_rule` 表 + 匹配引擎（system 首行/任一 system/正则）+ 规则 CRUD + 试跑端点 + 前端配置页；聚合命中静默换成员、直连命中返回 400、全局开关默认关 | ✅ 已实现+本地验证 43 项通过 + 离线回归 6 套通过 + `npm run build` 通过 + **已随 v5.2.3 部署上线**（2026-10-21 10:56，备份 backup/20261021-105506），冒烟实测 `filter_rule` 表就位、引擎 `false`、两条预置规则在列 | 生产 |
| CH-042 | 列表页二级组件层 + 第一档迁移（B 线-大）：`components/list/` 八组件 + 常驻灰底工具条内建 xlsx 导出（`core/xlsx_writer.py` 零依赖手写 OOXML + `api/admin/export.py` 10 个数据集）+ 样例页 `/design-preview`；**第一档 5 处已迁移**（模型别名 / 请求过滤 / API Key / 用量 3 表 / 用量明细）；第二档 4 处与第三档 4 处未动 | 🔶 第一档完成（2026-10-21）：build + compileall + 31 项导出测试 + 浏览器逐页实测全通过；**待用户验收** | 本地 |
| CH-043 | 卡片壳与成员流统一 + 批量选中保持（B 线-中，纯前端）：新增 `EntityCard`（替代 6 份卡片外壳）与 `ChipFlow`（替代 4 份只读 chips 流）+ `DataTable` 加 `reserve-selection` / `setSelection(keys)` + `ApiKeys` 批量启停保持选中、批量删除后按最新列表求交集防幽灵选中 + 仪表盘 `.share-list` 限高 320px | ✅ 已实现 + 浏览器逐项验证通过（2026-10-22）；**其中成员分页与仪表盘两栏方向已被 CH-044 修正** | 本地 |
| CH-044 | 聚合模型列表化 + 卡片内分页修正（B 线-中，纯前端）：聚合组区块改 `ListPage` 骨架（标题+右上批量 / 常驻工具条 / 卡片条目 / 底部统一分页）+ `ChipFlow.pager` 默认 false（卡片内平铺）+ `EntityCard` 加 `selectable`/`checked` 与跨页选中 + 批量启用/关闭/移除 + **移除前端拖拽排序**（保留后端 order 接口）+ 仪表盘两栏改 `stretch`、图表撑满剩余高度 | ✅ 已实现 + 浏览器逐项验证通过（2026-10-22）：卡片内分页 0 个、底部分页 13 条时出现 1/2 页且跨页选中保持、`.drag-handle` 0 个、左右两栏均 372px；**待用户验收** | 本地 |
| CH-045 | 列表工具条全选 + 三处列表统一（B 线-中，纯前端）：`ListToolbar` 新增快捷全选（`selectable` / `allChecked` / `indeterminate` + `toggle-all`，**只作用于当前页**、带半选态、位于工具条左侧）+ 上游源列表改 `ListPage`（统一分页 + 批量启用/禁用/删除）+ `UpstreamCard` 加 `selectable`/`checked` + 「疑似同一模型（建议合并）」改名**「聚合模型发现」**并补齐与聚合模型一致的骨架（右上刷新 / 工具条全选+批量合并 / 卡片条目 / 底部统一分页） | ✅ 已实现 + 浏览器逐项验证通过（2026-10-22）：上游源全选后「已选 10 项」10 张全勾、底部「共 12 条 10 条/页 1 2」；聚合页全选「已选 5 项」；聚合模型发现工具条「全选 共 2 条 批量合并」+ 底部页码 + 全选后「已选 2 项」；**待用户验收** | 本地 |
| CH-046 | 全站列表统一收口（B 线-中，纯前端）：`ListPage` 空态也渲染分页（去 `total > 0`）+ 用量页三张汇总表拆独立 `ListPage`（各自分页/全选/批量导出）+ 最近请求明细加多选与批量导出 + 探测模板/探测单元明细改 `ListPage` + 模型别名/请求过滤加多选（只给批量导出） | ✅ 已实现（2026-10-22）；**已归档**（用户验收「这一版改的很完美了」）；批量操作与筛选缺口由 CH-047 补齐 | 本地 |
| CH-047 | 列表批量操作与筛选补齐（B 线-中，纯前端）：模型别名加批量删除 + 请求过滤加批量启用/停用/删除 + 探测模板加全选/批量删除/导出 + 探测单元明细接导出 + 用量三表各加关键字筛选 + 上游源加筛选（关键字/分组/状态）+ 聚合模型加筛选（名称/类型/状态）+ 分组管理改标准列表（工具条/全选/批量删除/导出/分页，保留「保存分组」全量提交） | ✅ 已实现（2026-10-22）；**已归档**；分组管理的行内编辑形态已由 CH-048 修正 | 本地 |
| CH-048 | 分组管理改为展示型列表 + 弹窗编辑（B 线-小，纯前端）：对齐上游源 —— 条目只读（分组名/描述改纯文本）、行内「修改/删除」、右上「+ 添加分组」走弹窗、新增与修改共用 `BaseModal`、每次操作**即时提交**（后端 `updateGroups` 全量替换）、**移除「保存分组」按钮**与行内输入框、补空名/重名校验、失败由拦截器统一弹 `detail` 并重拉回真值；后端无改动 | ✅ 已实现 + 浏览器逐项验证通过（2026-10-22）；**已归档**；本轮列表统一化（CH-042~048）收口完成 | 本地 |
| v5.2.4 | 部署上线 + 生产库瘦身 + 双栈监听修正：①先清空 `log_usage`/`log_usage_detail` 并 `VACUUM`（10.14 GB → 204 KB），解决备份撑爆磁盘；②`deploy_v520_full.py` 9 步全过，含 CH-042~048 全部改动与后端导出端点；③FB-041 由 `host="::"` 改为显式双栈 socket（Python 3.12 asyncio 会置 `IPV6_V6ONLY=1`，原方案实际 IPv6-only）；④修部署冒烟「过滤引擎必须关闭」的过期断言 | ✅ 已部署生产（2026-10-22 22:30，备份 backup/20261022-223013 仅 880K）；`openapi` version=5.2.4、`ss` 显示 `*:10002`、IPv4/IPv6 双通、配置已加载 12/3/6/1/12 | 生产 |

## 历史经验参考

> 初始化时从历史项目复盘中提取的经验，供本阶段参考
- （暂无其他项目复盘可供参考，后续阶段复盘后将回流）

## 阶段状态总览

| 阶段 | 状态 | 开始时间 | 完成时间 | 门禁通过 |
|------|------|---------|---------|---------|
| stage-1 需求 | done | 2026-08-09 | 2026-08-09 | ✅（用户确认） |
| stage-2 设计 | done | 2026-08-09 | 2026-08-09 | ✅（v5 上线后追认） |
| stage-3 后端开发 | done | 2026-08-09 | 2026-08-09 | ✅（v5 上线后追认） |
| stage-4 前端开发 | done | 2026-08-09 | 2026-08-09 | ✅（v5 上线后追认） |
| stage-5 联调 | done | 2026-08-09 | 2026-08-09 | ✅（v5 上线后追认） |
| stage-6 测试部署 | done | 2026-08-09 | 2026-08-09 | ✅（生产运行中） |

> 状态枚举：pending / in_progress / done / blocked

## 当前阻塞

（无）

## 阶段变更记录

- 2026-08-07：补建流程管控文件（历史阶段追溯为 done）
- 2026-08-09：v5 重构启动，流程重新从 stage-1 管控；需求确认通过，进入 stage-2 设计
- 2026-08-09：v5 六阶段完成并部署生产（10002 端口），进入维护迭代
- 2026-08-09：CH-001~007 实现部署；用户确认多协议+分组规划，固化为 PLAN 文档，CH-008（分组管理）开工
- 2026-08-10：CH-008/011/012/013/014 实现部署；FB-008~013 记录；协议矩阵三文档建档（CH-014 出站已完成，CH-009/010 入站设计确认待实施）；攒批待用户确认后统一归档
- 2026-08-10：用户确认整体初步完成 → 攒批统一收尾：README 重写对齐 v5；CH-001~008/011~014 归档至 docs/_changes/archived/；_changes/README 分活跃/归档两表；feedback-log / PLAN 状态收口。剩余活跃仅 CH-009/CH-010（入站协议，设计就绪）
- 2026-08-10：文档同步闭环（用户质询 README/设计文档未同步后补齐六份原始文档，修正多处虚假声明与 README 死链）
- 2026-08-11：CH-009（anthropic 入站）+ CH-010（responses 入站）实施验证部署完成并归档——**3×3 协议矩阵收齐，第一版（V1）完成**
- 2026-08-11：FB-014/015/016 三连修（复制按钮 HTTP 降级 / models.py 只回已配置模型 / 透传查找纳入已配置模型 CH-015），本地+生产验证通过，CH-015 归档
- 2026-08-11：项目纳入 git 管控（gitee.com/wang-jianzhou-66/smart_router，main 分支首提交 fd0722f）；敏感信息脱敏（SSH 密码/Key 走环境变量；DB/config.yaml/test_router.py 入 .gitignore）
- 2026-08-12：FB-020/CH-018 两期完成并归档（入站图片映射 + 三协议错误格式统一 + 推理模型 reasoning 映射）；文档同步闭环（API契约/接口文档/功能清单/五列矩阵/README/变更记录 6 份）；用户实测确认通过
- 2026-10-16：CH-019 实施并部署 Ubuntu 生产（另一 AI 承接，非完整流程：部署漏传 3 适配器致 chat 全 500、SQL 06 未执行、前端目录错位）；FB-022 部署修复收口（md5 比对补齐 + venv 补跑 SQL 06 + unit 指向修正 + usage_repo `with int` bug 修复 + retry 超时 20→60/8→30 热调整）；chat/流式/messages/usage 端到端全通
- 2026-10-16：**流程违规记录**——AI 未经用户授权直接部署生产，导致中转站中断，由用户另寻 AI 修复。此后确立规则：任何上线动作必须先获用户明确同意，本地验证为主。
- 2026-10-16：CH-019 二期完成本地实现与验证（**未部署**）：同名聚合可控化（agg_model_group + 3 API + Aggregated.vue 可视化/勾选源/拖拽优先级/启停/恢复自动）、模型排序改 sortablejs 拖拽；后端 `test/verify_group_ch019.py` 18/18，浏览器实测拖拽落库通过（含修复「UI 变但库没变」的 Vue 数组切片同步 bug）；同步 6 份原始文档，CH-019 归档
- 2026-10-16：**CH-020 完成本地实现+验证并归档（未部署）**：①异名模型聚合——`agg_model_group.upstreams` 成员新增 `model` 字段，新增归一化建议（去前缀/小写/符号归一）与 source-models 端点，前端支持一键合并、手动组合异名成员；`resolve_group_candidates` 使候选携带各源真实模型名；②后台信息架构重组——侧边栏四组（无分组/智能路由/统计/系统），新增「路由参数」页（延迟探测/请求重试/智能重试/故障转移/手动重载），仪表盘收敛为中转视角，延迟面板吸收路由视角，移除顶栏全局热重载；③拖拽体验修复——补插入位置指示线，加 `group` 隔离与 `evt.from/to` uid 比对，根治跨源拖拽 404「上游源不存在」。验证：后端 `test/verify_alias_ch019.py` 13/13、前端构建通过、浏览器实测跨源拖拽不再发请求
- 2026-10-17：**CH-021 完成本地实现+验证并归档（未部署）**：①探测单元全局去重——`collect_probe_plan()` 取「规则候选 ∪ 别名目标 ∪ 聚合组成员」，按 `(upstream, 真实模型)` 唯一，多组引用时间隔取最小；②聚合组独立探测——新表 `agg_probe_config`（与 `agg_model_group` 解耦，自动发现组也能配）+ 4 个管理端点；③探测时段——新增 `core/probe_schedule.py`，支持 `always` / `window`（星期 1~7 + 多时段窗口 + 跨夜），快捷模板三个；④调度改造——按单元到期 + `asyncio.gather` + 信号量限流，探测失败默认不计 Key 冷却（`count_key_failures=false`）；⑤两档排序——`stable`（保序、超慢沉底）/ `latency`（延迟升序），T0/T1/T2 分层，全 down 回退配置顺序；⑥用量按单元——`log_usage.upstream_model` + `by-unit` 端点。验证：`verify_probe_ch021.py` 24/24、`verify_probe_ch021_db.py` 19/19、`verify_probe_ch021_api.py` 32/32、`verify_usage_unit_ch021.py` 8/8、`npm run build` 通过、浏览器实测探测保存与计划联动通过；同步 9 份文档
- 2026-10-17：**CH-022 完成本地实现+验证并归档（未部署）**：①演示环境——`core/database.py` 支持 `SMART_ROUTER_DB`，`test/seed_demo_ch022.py` 生成独立 `backend/demo.db`（4 上游 / 3 聚合组覆盖探测开·速度优先·限时段、开·稳定优先、关三态 / 3 客户端 Key / 2 规则 / 14 天 1392 条用量 / 一组未合并异名模型用于体验一键合并），`run_demo.ps1` 启动到 10198；②仪表盘重设计——健康条 + 5 指标卡（今日请求含「今日至今 vs 昨日同期」环比）+ 7 天双指标 SVG 趋势 + 上游贡献占比 + 上游源卡片 + 聚合组概览 + 需要关注；`GET /admin/api/dashboard` 扩展 `usage_today/usage_7d/trend/upstream_usage/groups/attention/probe_summary`；③修复三处问题——探测计划把聚合名当模型名（单元 11→7）、今日统计误用 `created_at`（1392→56）、全局 `svg{width:1em!important}` 压扁趋势图。验证：浏览器实测全模块正常、CH-021 回归 24/24 + 8/8、`npm run build` 通过；同步 8 份文档
- 2026-10-17：**CH-023 完成本地实现+验证并归档（未 push、未部署）**：①聚合实体统一——新表 `agg_unified`（`kind` = static / rule），旧 `agg_model_group` / `agg_aggregated_name` 幂等迁移搬入，旧表保留；`_sync_legacy_views()` 把统一表投射回旧内存视图，既有路由链路零改动；②探测模板——新表 `agg_probe_template`，聚合挂模板后模板值完全覆盖自配（不可被组覆盖），改模板全组同步，删模板回退自配→全局；③rule 聚合纳入探测计划——探测对象 = 全部规则候选并集，单元记录 `groups` / `group_kinds`；④探测排班表——按小时着色（探测中/时段外/关闭）+ 合并/按星期视图 + 间隔/次时/次日/引用聚合，支持跨夜；⑤保留原有排序语义——rule 走 `get_ordered_candidates`（priority + 动态权重 `base_w × (base_latency/latency)²`），static 走 `sort_group_candidates`（stable/latency 分层，全 down 回退）；⑥信息架构归位——侧边栏移除延迟面板/路由参数，聚合页三标签，容错参数搬入系统设置，`/latency`→`/aggregated?tab=plan`、`/route-params`→`/settings` 重定向；⑦修复三处问题——增量 SQL 路径少折一层目录、`PUT /aggregations` 无法用 null 清空字段（改 `model_fields_set`）、自动发现聚合从列表消失。验证：`verify_migration_ch023.py` 全通过、`verify_aggregation_ch023.py` 30 项全通过、`verify_api_ch023.py` 40 项全通过、`npm run build` 通过、demo 库浏览器实测三标签/模板挂载/排班表/重定向全正常
- 2026-10-17：**CH-024 完成本地实现+验证并归档（未 push、未部署）**：用户指出 CH-023 只统一了「rule 聚合」的名字、没统一行为（所有 rule 聚合共用全局规则与同一份候选、无法裁剪、无法新建 rule 类型）。按用户方案实施「一张路由规则表 + 每个聚合引用其子集」：①数据层——`agg_unified` 加 `rule_bindings` TEXT 列（增量 SQL 08），三分语义 `NULL`/`[]` = 全跟随、`[{rule, candidates: null}]` = 规则子集且候选全跟随、显式候选子集；②路由——`get_ordered_candidates(..., aggregation=聚合名)` 先按绑定裁剪规则与候选，之后排序逻辑一行未改；③探测——`rule_candidate_units(aggregation)` 按绑定算单元，各聚合探测成本可区分；④规则变更联动——`set_rules()` 后 `prune_rule_bindings()` 清理已删/改名规则引用（清空回退全跟随），响应带 `affected_aggregations`；⑤失效检测——`rule_binding_issues()` 检出 `rule_missing`/`candidate_missing`，列表返回 `stale_bindings` 供卡片黄标；⑥前端——新建/编辑弹窗加「聚合类型」单选 + 绑定编辑器（规则卡片：使用勾选/候选复选框/跟随徽标/全选）+ 卡片绑定摘要 + 失效黄标。修复：前端 rule 类型保存被后端拒（`saveEdit()` 无条件发 `members: []`，改 rule 类型不发该字段）。验证：`verify_rule_binding_ch024.py` 8 组全通过、CH-023 三套回归全通过、`npm run build` 通过、demo 库浏览器实测通过；同步 10 份文档并归档
- 2026-10-18：**CH-031 仓库迁移与历史隐私清洗（已 push GitHub，未部署）**：推送前隐私审查发现 git 历史中 `test/verify_prod_ch016.py` 在 CH-016 提交里硬编码管理员密码与客户端 Key（CH-018 已改环境变量但历史可查），`.git/config` 远端 URL 内嵌明文 Gitee 账号密码。处理：①双重备份（文件副本 + git bundle，均在项目目录外）；②`git filter-repo` 替换为占位符，27 提交重写；③移除凭据 remote；④提交作者邮箱（手机号@qq.com）脱敏为 GitHub noreply；⑤全历史复扫密码/Key/账号/手机号 0 命中，HEAD 树对象与清洗前完全一致；⑥新远端 `https://github.com/66wjz/smart_router.git` 并推送 main。用户决定 Gitee 转私有、不轮换凭据（局域网部署），JWT 密钥硬编码问题登记到需求规格 9.2 待改
- 2026-10-18：**CH-025 完成本地实现+验证并归档（已 push、未部署）**：用户反馈三类问题（新建聚合保存按钮卡「保存中」/ 复制 Key 弹确认框 / 请求频繁中断报 500）。①取证——连生产 10.10.0.2 取 journal（持久化完好、重启未丢），500 仅集中在 10-16（部署事故 + JSONDecodeError），拿到堆栈直指 `chat.py:23`，对照三入站发现仅 chat 缺 try；②A 线——`savingName` 与 `editName` 同为 `''` 导致按钮恒 disabled，改独立 `savingEdit`；③B 线——`showCopy()` 去 `ElMessageBox.confirm` 直接复制；④C1——三入站统一请求体校验（非 JSON / 非对象 / 缺 model / messages 非数组 → 400）；⑤C1b——`messages: null` 时 `get(k, [])` 返回 `None` → `for None` 崩，给 `estimate_tokens`/`extract_text`/`has_image` 补类型防御；⑥C2——`@app.exception_handler(Exception)` 按入站协议返回规范错误体；⑦C3——新增 `core/logging_setup.py`（ReqeustContextMiddleware 纯 ASGI 缓存请求体 + access 日志含 model/stream/messages/body 摘要 + `sk-` 脱敏 + RotatingFileHandler 10MB×5）+ `GET /admin/api/logs`、`/logs/info`。验证：畸形请求六种三入站全 400 零 500、503/401 规范错误体、日志脱敏生效、日志接口正常、浏览器实测保存按钮可点、CH-024 + CH-023 三套回归全通过、`npm run build` 通过；同步 9 份文档并归档。遗留：流式转发 `try_stream` 的 `send()` 无 `wait_for` 保护（生产 44 次 >60s、最长 219s），待用户确认后单独处理
- 2026-10-18：**CH-032 JWT 签名密钥动态化（已实现，随 v5.2.0 上线）**：删除 `security.py` 硬编码 `JWT_SECRET`，改为三级取值 `SR_JWT_SECRET` 环境变量 > `sys_setting.jwt_secret` > 首次启动 `secrets.token_urlsafe(48)` 自动生成并落库；进程内缓存 + `threading.Lock` 防并发重复生成；数据库不可用时降级为进程内随机密钥并 WARNING（服务不崩）；`main.py` 删死导入并在 startup 预热。核心约束是「不硬编码」与「重启不踢人」同时满足。验证：7 项单元（含旧硬编码密钥伪造的 token 失效）+ 真实 uvicorn 重启后旧 token 仍有效 + 四套回归全通过 + `compileall` 0 错误
- 2026-10-18：**v5.2.0 全量部署上线（用户授权）**：生产停在 CH-019 一期，累计 13 项变更一次性上线。①推翻原「逐文件增量」方式——CH-026 新增 4 个 config mixin、CH-023/024 含表结构与数据迁移，逐文件必漏，改**整树同步**；②明确红线——**绝不在生产跑 `seed.py`**（`drop_all()` 会清空生产数据）；③**排查出高危点并规避**——生产库缺 `agg_model_group`/`agg_unified`/`agg_probe_config`/`agg_probe_template` 四表，而新代码在**模块导入期**即调用 `config.load()`，任一 repo 抛 `OperationalError` 会让 load() 把上游源/规则/API Key 全部清空 → 网关全量 401；且 `startup()` 中 `config.load()` 与 `sync_unified_tables()` 同处一个 try，迁移失败会跳过 load()。故改为**重启前显式预迁移**（sql/06 → increment/06 → 07 → 08）；④部署 8 步：备份（sqlite3 在线备份 API）→ 传 sql → 预迁移 → 传代码 → 替换 dist → 清 pycache + chown → compileall 预检 → 重启验证，每步失败即中止且中止点均在替换代码之前；⑤新增 `test/deploy_v520_full.py`（全量）与 `test/deploy_probe_prod.py`（只读勘察）。验证：4 个迁移脚本全 `APPLIED`，表增至 14 张，`agg_unified` 3 行；启动日志 `配置已加载: 1 上游源, 3 规则, 4 密钥, 0 别名, 3 聚合`（配置完整）；10 个管理端点全 200；入口冒烟 `GET /` 200、`/health` 200、登录 200、无 Key 401（无 500）。备份 `/opt/smart-router/backup/20261018-210217`
- 2026-10-19：**CH-038 完成本地实现+验证（未 push、未部署）**：用户反馈 Trae 21:54 报 500 但中转站查不到日志，同时希望日志能记录请求体与上下文。①定位——四层日志（应用 / journalctl / uvicorn socket / 无 nginx）全无 500、`NRestarts=0`，判定请求未到达应用层（`error sending request` 属发送阶段失败，TCP 阶段物理上无法记录，该边界已写入文档与 UI 提示）；②A 线——`RequestContextMiddleware` 包装 `receive` 捕获 `http.disconnect` + `response_started` 标志，未发响应即断连时补记 `status=499 disconnected=true`；③数据层——`log_usage` 补 `cache_read_tokens`/`cache_write_tokens`/`attempt_count`，新表 `log_usage_detail`（与主表 1:1 可缺行）；④采集层——5 个 contextvar 贯穿请求体/白名单请求头/实际转发体/上游响应/尝试链，适配器两个转发循环逐候选 `_note_attempt`，流式只留首尾各 20 条片段；⑤策略——默认 `error_only`（成功只记结构化字段 + token，失败存完整报文），单报文上限 1 MB（头 3/4 + 尾 1/4 + 标注），保留期 30 → 14 天（可设 7/14/30/90），主表与详情表同周期清理且先删详情；⑥脱敏——**先脱敏再截断**（截断会切断 `sk-` 前缀导致正则失效）；⑦前端——`Usage.vue` Token 三段式 + 「尝试」列 + 行点击，新增 `RequestDetailDrawer.vue`（三栏 + 尝试链 + 复制 + 窄屏单栏 + 超 64KB 分块渲染），`Settings.vue` 新增「用量与日志」；⑧验证——`verify_observability_ch038.py` 48 项全通过、7 套回归全通过、`compileall` 0 错误、`npm run build` 通过；同步 10 份文档
