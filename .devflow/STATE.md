# 项目流程状态

> **当前版本：v5.2.0**（v5.1.0 于 2026-08-11 发布并打 tag；v5.2.0 为当前开发版本，待部署后打 tag；主仓库已迁 GitHub：https://github.com/66wjz/smart_router，原 Gitee 仓库转私有）

- 项目名称：Smart Router（AI 模型智能路由代理）
- 项目路径：E:\80-project_dev\04_smart-router(starting)
- 流程路径：full-route（正式开发，2026-08-09 启动 v5 重构管控）+ 维护迭代（CH-001~007 已实现部署）
- 技术栈：FastAPI + Vue3 + SQLite
- 项目规模：M
- 创建时间：2026-08-07（v4 追溯补建）；2026-08-09（v5 重构重启管控）
- 当前阶段：维护迭代（v5 六阶段已完成上线）
- 当前阶段状态：in_progress
- 上次更新：2026-10-18（CH-031）

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
| CH-031 | 仓库迁移 GitHub + 历史隐私清洗（B 线-小）：`git-filter-repo` 替换历史中 CH-016 硬编码的管理员密码与客户端 Key（已双备份）+ 移除内嵌明文密码的 Gitee remote + 全历史复扫 0 命中 + HEAD 树对象与清洗前一致（内容零变化） | ✅ 本地清洗完成（2026-10-18）；**未配置远端、未 push、未部署** | 本地 |

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
- 2026-10-18：**CH-031 仓库迁移与历史隐私清洗（本地完成，未 push）**：推送前隐私审查发现 git 历史中 `test/verify_prod_ch016.py` 在 CH-016 提交里硬编码管理员密码与客户端 Key（CH-018 已改环境变量但历史可查），`.git/config` 远端 URL 内嵌明文 Gitee 账号密码。处理：①双重备份（文件副本 + git bundle，均在项目目录外）；②`git filter-repo` 替换为占位符，27 提交重写；③移除凭据 remote；④全历史复扫 4 个敏感值 0 命中，HEAD 树对象与清洗前完全一致；⑤删除临时规则文件。用户决定迁 GitHub、Gitee 转私有、不轮换凭据（局域网部署）。**待用户提供 GitHub 仓库地址并授权后再推送**
- 2026-10-18：**CH-025 完成本地实现+验证并归档（已 push、未部署）**：用户反馈三类问题（新建聚合保存按钮卡「保存中」/ 复制 Key 弹确认框 / 请求频繁中断报 500）。①取证——连生产 10.10.0.2 取 journal（持久化完好、重启未丢），500 仅集中在 10-16（部署事故 + JSONDecodeError），拿到堆栈直指 `chat.py:23`，对照三入站发现仅 chat 缺 try；②A 线——`savingName` 与 `editName` 同为 `''` 导致按钮恒 disabled，改独立 `savingEdit`；③B 线——`showCopy()` 去 `ElMessageBox.confirm` 直接复制；④C1——三入站统一请求体校验（非 JSON / 非对象 / 缺 model / messages 非数组 → 400）；⑤C1b——`messages: null` 时 `get(k, [])` 返回 `None` → `for None` 崩，给 `estimate_tokens`/`extract_text`/`has_image` 补类型防御；⑥C2——`@app.exception_handler(Exception)` 按入站协议返回规范错误体；⑦C3——新增 `core/logging_setup.py`（ReqeustContextMiddleware 纯 ASGI 缓存请求体 + access 日志含 model/stream/messages/body 摘要 + `sk-` 脱敏 + RotatingFileHandler 10MB×5）+ `GET /admin/api/logs`、`/logs/info`。验证：畸形请求六种三入站全 400 零 500、503/401 规范错误体、日志脱敏生效、日志接口正常、浏览器实测保存按钮可点、CH-024 + CH-023 三套回归全通过、`npm run build` 通过；同步 9 份文档并归档。遗留：流式转发 `try_stream` 的 `send()` 无 `wait_for` 保护（生产 44 次 >60s、最长 219s），待用户确认后单独处理
