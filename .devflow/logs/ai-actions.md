# AI 操作留痕

> AI 每次关键操作（阶段切换、门禁检查、状态文件更新、批量修改）都记在这里。
> 用途：事后复盘"AI 是怎么走偏的"，识别 vibecoding 陷阱的早期信号。

## 操作记录（倒序，最新在最上）

### 2026-10-29 - CH-053 日志列表分页不刷新（A 线，已部署）
- 触发：用户反馈用量页「最近请求明细」切换页码/每页条数后内容不变
- 定位：全站唯一服务端分页列表；`ListPage` 转发事件名是 `page-change`，`Usage.vue` 写成 `@change` → 监听永不触发，`update:page` 只改状态不重新请求
- 修复：`Usage.vue` 一处 `@change="loadLogs"` → `@page-change="loadLogs"`
- 验证：`npm run build` 通过；构建产物 Usage chunk `onPageChange` 0→1；线上 dist 已替换（`Usage-CaNHGMm2.js`）；接口自证 page1/page2 不同、size 2/5 生效、total 1522
- 部署：dist 备份 `/opt/smart-router/backup/dist-fix-20261029/`，静态资源替换，未重启后端
- 文档：变更记录 / feedback-log（FB-048）/ STATE（CH-053）

### 2026-10-29 - 生产后台密码轮换 + 凭据本地留存
- 背景：中转站开公网 IPv6，GitHub 曾公开初始账号密码与 Key
- 实施：改密为 28 位强随机（旧密码立即 401、新密码 200）；凭据写入 `E:\80-project_dev\04_smart-router\.env`（.gitignore 已忽略，禁止提交，含 LAN/域名地址与管理员账号密码）
- 核查：当前启用 API Key 均为自定义 `sk-sr-*`，仅一把旧 `sk-CHANGE-ME-premium` 处于禁用，无泄露中的默认 Key
- 提醒：线上仍为 CH-049 之前版本，旧 JWT 最长 24h 后自然失效；如需立即踢出，部署 CH-049（JWT 带密码指纹）

### 2026-10-28 - CH-052 会话亲和：缓存优先路由（本地实现与验证）
- 触发：用户排查缓存命中（`test_demo` 命中≈99%，`deepseek-v4-1-flash` 新会话前几轮全 miss），确认不是显示错误；要求「彻底解决」而非临时调权重
- 用户决策：不依赖客户端改动 / 不依赖号池；新会话按负载/权重选一家后钉住；只有失败才换且换后不切回；权重与统计保留；短请求不钉；按聚合可单独开关，默认开；随后授权「按你的设计来，按 skill 流程」
- 分类：B 线-大 → 维护迭代迷你 5 阶段；变更文档 `docs/_changes/archived/FB-046-会话亲和缓存优先路由.md`
- 实施：①新增 `core/affinity.py`（`SessionAffinity` + 两个 contextvar：preferred/used key）；②`router_service._apply_affinity/_finish_affinity`（放置、命中、重钉、不切回、失败后改钉）+ `_UsageTracker.affinity_target`（非流式落库早于钉子完成，落库前按实际命中修正 `failover`）；③`key_pool.pick` 读 preferred key；④`agg_unified.affinity` + `log_usage` 三字段（`usage_repo` 列白名单 + 运行期幂等补列）；⑤前端编辑弹窗三选 + 卡片徽标
- 实施中修的三个坑：`bind()` 同源重绑重复累加 `active`（改为无条件先减）；`usage_repo.insert_many` 把所有附加列 `int()` 强转，`affinity_key/switch_reason` 是 TEXT → 整批落库失败（按列区分类型）；单候选时不必占表 → 新增 `single` 提前返回
- 验证：`test/verify_affinity_ch052.py` 38 项全过（指纹/TTL/LRU/active、1000 新会话 4:2:1=571/286/143、同会话 100 次同源同 Key、多轮不变、失败重钉不切回、Key 冷却换 Key、短请求不写表、关闭亲和恢复 40/20/10、测试端点不写表、日志三字段）；回归 ch051/ch038/ch039/ch040/ch041/ch024/ch036 全过；`py_compile` + `npm run build` 通过
- 版本：v5.3.0 → v5.4.0（main.py ×2 / run.py / pyproject.toml / frontend package.json / README / STATE）
- 文档：变更记录、feedback-log（FB-046）、需求规格（8.1 / 9.4.2）、功能清单（2.8.13）、API契约（4.28.1 / 4.28.2 / 4.30 / 落点表）、接口文档、系统核心流程（流程 1）、五列矩阵、README、_changes 索引
- 状态：未部署——生产 `10.10.0.2` / `192.168.31.10` 的 22 与 10002 均不可达（Ubuntu 侧故障），恢复后按 SQL 13 → 后端 → dist 上线，并核实各源 Key 数量与 8326 号池账号轮换
- 已知限制：跨提供商缓存物理上无法共享；号池内部账号轮换仍可能让缓存失效（本层不控制）

### 2026-10-28 - CH-051 聚合测试 + 成员加权分发（本地实现与验证）
- 触发：用户提两个需求（聚合测试按钮 / 聚合成员按权重均衡分发），要求「按 skill 流程」
- 分类：B 线-大 → 维护迭代迷你 5 阶段；变更文档 `docs/_changes/FB-045-聚合测试与加权分发.md`
- 用户拍板：所有固定成员聚合默认按权重轮流（权重全 1 = 平均轮询）；测试 = 逐个成员 + 走聚合一次；版本 v5.3.0
- 实施：①`core/weighted_rr.py`（SWRR）+ `router_service._apply_weighted_order`（冷却/探针 down 剔除、剩余权重重归一、全员不可用回退原顺序）+ 公开 `resolve_candidates`；②`api/admin/aggregations.py` 新增 `POST /admin/api/aggregations/test?name=`（成员逐个 + 走聚合一次，不写用量/不改健康）；③前端 `AggregationTestModal` + 聚合卡片「测试」按钮 + ChipFlow `renderMeta`（权重 ×N）+ 成员编辑文案
- 验证：`verify_aggregation_weight_ch051.py` 17 项全过；回归 ch040（9b 按新语义重置轮询）/ch039/ch041/ch024/ch034/ch036 全过；`py_compile` + `npm run build` 通过
- 版本：v5.2.5 → v5.3.0（main.py ×2 / run.py / pyproject.toml / frontend package.json / README / STATE）
- 文档：变更记录、feedback-log（FB-045）、需求规格（9.4 / 9.4.1）、功能清单（2.8.11 / 2.8.12）、API契约（4.28.5）、接口文档、系统核心流程、五列矩阵、README
- 状态：未部署（用户选择先本地验收）

### 2026-10-27 - CH-050 中文上游 ID 响应头打崩 /v1（修复 + 本地验证）
- 触发：用户截图报聚合 `test_demo` 调用 500「中转站内部错误: UnicodeEncodeError」，问「会是我们中转站的报错吗」，随后「直接改，弄到服务器上」
- 定位：报错体来自 `main.py` 全局兜底 → 异常在本系统内；`_RetryLoop.response_headers()` 把中文 `upstream_id` 写进 `X-Served-By`，Starlette 用 latin-1 编码响应头 → UnicodeEncodeError。管理端「测试」走 `test_non_stream` 不带该头，故单测正常、/v1（聚合/直连）才炸
- 复现：本地 starlette 1.6.0 直接构造 `JSONResponse(headers={'X-Served-By': '星-...'})` → 同一异常
- 实施：新增 `backend/app/upstream/headers.py`（`ascii_header_value` / `ascii_safe_headers`）；`response_headers()` + `router_service._wrap_stream_with_usage` + `v1/messages.py`(2处) + `v1/responses.py`(2处) 统一安全化；不改数据库/上游 ID
- 验证：`test/verify_header_ascii_ch050.py` 17 项全过；回归 `verify_wrapped_error_ch040.py`、`verify_usage_passthrough_ch039.py` 全过；`py_compile` 通过
- 版本：v5.2.4 → v5.2.5（main.py ×2 / run.py / pyproject.toml / frontend package.json / README / STATE）
- 部署：`test/deploy_ch050_hotfix.py` 已执行（2026-10-28 00:09）：备份 `backup/ch050-20261028-000910` → 上传 8 文件 → 清 pycache → 重启 → `openapi` 5.2.5 / health 200 / 远程头部自检 `raw_ascii=True`；生产 `配置已加载: 20 上游源, 3 规则, 6 密钥, 2 别名, 15 聚合`
- 线上复测：`test_demo` 不再 500（UnicodeEncodeError 已消失），当前返回 503「所有模型均不可用」——绕过中转站直连上游 `ai.88wk.org`（用其自己的 Key）同样 502/503（deepseek-flash 502、deepseek-v4-flash 502、deepseek-v4.1-flash 503、gpt-5.6-luna 404）→ **上游自身故障**，非本系统；另成员「星-国产模型」为禁用状态，聚合只有 2 个候选
- 文档：变更记录、feedback-log（FB-044）、STATE（CH-050）、API契约（变更记录）、README（X-Served-By 说明）

### 2026-10-22 - CH-049 收尾（归档 + 经验沉淀）
- 触发：用户「现在中转这个没事了，先按照 skill 流程收好尾」
- 前置状态核对：工作区干净、`8f5a527` 已推送、远端一致
- 归档：`_changes/CH-049` → `archived/`，README 索引状态改为「已实现（已归档）；未部署」；`_changes/` 活跃区恢复为 CH-034/036~041
- **L1 经验收敛（+5 条）**：
  - `BE-06` 同一个默认值写在两处 = 迟早不一致，必须抽常量（本轮真踩：`check_auth` 用 `""`、`login` 用 `smart-router-2026`，空库全量 401）
  - `BE-07` 改密后令牌失效用密码指纹而非版本号（版本号需人工递增，必然被忘记）
  - `PR-08` 回归失败先定性：`git stash` 跑基线区分「既有」与「本次引入」
  - `PR-09` 改鉴权契约要 grep 所有签发点，不只 `/login`（3 个测试夹具裸签 token 全失效）
  - `PR-10` 提交前脱敏要扫本次对话的真实值，不只密钥格式（新密码被写进 feedback-log / ai-actions）
- **L2 工作区归并（2 章）**：`03_BACKEND_DATABASE_EXPERIENCE.md` 新增第六章「缺省值必须单一来源」；`05_DEVFLOW_PROCESS_EXPERIENCE.md` 新增第五章「回归失败的定性与修复边界」
- L3 蒸馏：本轮 5 条 L1 经验均为项目实现细节（具体到本项目的 JWT/密码/测试脚本），**未达到普适标准**，不提请写入 skill 全局经验库
- STATE 收口：CH-049 行状态更新 + 「上次更新」改为已收尾
- 备注：本次「user_file_change」提示的文件删除为编辑器侧的显示事件，实测文件均存在，未做任何恢复或删除

### 2026-10-22 - CH-049 登录 401 提示纠正 + 改密后令牌失效
- 触发：用户「我登录进去点击右上角修改密码，改成（新密码），然后就登录不上去了，一直提示未登录或登录过期」；确认两个修复点后说「两个都修复，按照你的建议来，严格按照 skill 管控好开发流程」
- 分类（铁律 7）：①401 提示语义错误 → **A 线 bug**；②改密后旧 token 仍有效 → **B 线-小**。先写 `_changes/CH-049`
- 定位（只读取证，未改生产）：生产日志 `22:54:56 PUT /admin/api/admin-password → 401`、随后 6 次 `POST /login → 401`；库中 `admin.updated_at` 仍是 8 天前 → 改密请求在鉴权阶段就被挡，密码从未写入
- 实施：①`request.ts` 401 分支区分登录接口（用后端 detail，不清 token 不跳转）；②JWT 加 `pv` 密码指纹、`check_auth` 每次比对；③改密成功后前端主动 logout
- **回归逮到一处我自己引入的真 bug**：`check_auth` 默认密码写 `""`、`login` 写 `smart-router-2026`，空库（回归脚本建的空库）时两处指纹不等 → **所有管理接口 401**。`verify_filter_engine_ch041` 从「全部通过」变「10 项失败 ❌」。修法：抽 `DEFAULT_PASSWORD` 单一常量 + `current_password_version(admin_cfg)`，三处统一走它
- 连带适配：3 个测试脚本原本裸签 token（无 `pv`），改用新增的 `make_admin_token()`
- 验证：CH-049 本体 12 项 `CH049_ALL_PASS`；回归 ch038/ch041/ch042/ch024/ch034×2/ch036/ch037/ch039/ch040 **全过**；ch023 的 1 项失败经 stash 基线对比确认为**改动前既有**；`npm run build` + `compileall` 通过
- 文档同步：新增 `_changes/CH-049`；`_changes/README` 登记；`变更记录.md`；`需求规格`（1.1/1.2）；`API契约`（4.20 + 新增 4.20.1 401 语义表）；`接口文档`（3.9）；`STATE.md`；`feedback-log.md`（FB-043）
- 未部署（用户未要求）；上线后所有已登录会话会失效一次

### 2026-10-22 - v5.2.4 收尾（文档同步 + 脱敏 + 提交）
- 触发：用户「先加载 skill，然后按照流程对现在的这些改动进行收尾。然后脱敏，之后提交到仓库，这次先不部署了」
- 路径判定：STATE 全阶段 done + 维护迭代中 → **维护迭代模式**（无门禁，复用 A/B 线分类）
- 文档影响核对（10 项逐项过）：受影响 4 项 —— README（版本号 + 三行能力）、架构设计（CH-042~048 期间已同步）、API契约、接口文档；其余 6 项确认不受影响
- **本次抓到一处真实漏同步**：CH-042 新增的 `GET/POST /admin/api/export/{dataset}` + `GET /export/datasets` 三个端点与 10 个数据集，当时只改了架构设计，**API 契约与接口文档完全没登记**。已补齐（4.24 / 3.15），内容逐项对照 `export.py` 实际实现（数据集清单、筛选参数、错误码 404/400、响应头、两条设计理由）
- 脱敏（`rules/git-usage.md` 步骤 1）：275 个文件扫 `sk-*`/`nvapi-*`/`tp-*`/`ghp_*`/`AKIA*`/PEM 头 → 0 命中；`git ls-files` 查 `.db`/`.env`/`config.yaml`/`*_pass`/`.tmp_*` → 0 命中；用仓库外密码文件真实值反查全仓 → 未出现。结论：无需额外脱敏
- 收尾：STATE（版本 v5.2.4 + 最后更新 + v5.2.4 行）、feedback-log（FB-041 修正 + 新增 FB-042）、变更记录（收尾条目含 10 项核对表 + 脱敏结论）
- 提交：用户选择合并为一个 commit（含 CH-042~048 列表统一化 + v5.2.4 部署运维 + 双栈修正）
- 未部署（用户明确「这次先不部署了」）

### 2026-10-22 - v5.2.4 部署上线（先清用量日志再部署）
- 触发：用户「先别急提交，先更新服务器的版本」；首次全量部署因生产库 11G 备份过重被用户中断，指示「把用量日志先清空了部署」
- 定位：生产 `backend/smart_router.db` = 11GB（WAL 10MB），部署第 1 步整库在线备份要额外 11GB、耗时不可控
- 实施：①停服 → `DELETE FROM log_usage_detail`（502s）+ `DELETE FROM log_usage`（0.2s）→ `VACUUM`（10.14GB → 204KB）→ 启服；②删除中断部署留下的 8.7G 半截备份，磁盘 52G → 34G；③版本号统一 v5.2.4（main.py 2 处 / run.py / pyproject.toml / package.json / README），`npm run build` 重建 dist；④`deploy_v520_full.py` 9 步全过
- 清理后校验：`integrity_check=ok`、`freelist_count=0`；12 上游 / 6 Key / 3 规则 / 12 聚合 / 1 模板 / 2 过滤规则 / 16 设置全在，日志两表 0 行
- 部署结果：备份 `/opt/smart-router/backup/20261022-223013`（880K）；`Smart Router v5.2.4 启动`、配置已加载 12/3/6/1/12；`/`、`/health`、登录 200，无 Key 401；`openapi` version=5.2.4；监听 `0.0.0.0:10002`；`/admin/api/export/datasets` 200
- 冒烟：`SMOKE_FAIL` 唯一原因是脚本断言「过滤引擎必须默认关闭」，而生产引擎是用户主动开启 → 已把该断言改为「只校验表/端点/预置规则，开关值仅打印」
- **双栈修正（承接 FB-041）**：按用户选择先补 `host="::"`，上线后 IPv4 立刻全断（127.0.0.1 / 10.10.0.2 均 000，`ss` 只有 `[::]:10002`）→ 立即回滚为 0.0.0.0 恢复。取证：生产 Python 3.12 `asyncio.create_server("::")` 的 `IPV6_V6ONLY = 1`（系统 `net.ipv6.bindv6only=0` 无用），证明 FB-041 原「Linux 默认双栈」判断错误。改为显式双栈 socket（`socket.create_server(..., family=AF_INET6, dualstack_ipv6=True)` + `Server.run(sockets=[sock])`），本地最小 ASGI 离线验证 `v6only=0` 且 IPv4/IPv6 双 200 后才上线；结果 `ss` 显示 `*:10002`，三路健康检查全 200
- **纠错留痕**：部署前我把 `run.py` 的 `host="::"` 误判为「与本轮无关的改动」并建议还原，用户据此选择 0.0.0.0。事后发现它是 FB-041 已登记变更，服务器侧本就「随手册 A5b 部署」尚未上线；已向用户说明并按选择补回（含上述修正）
- 收尾：`docs/变更记录.md` 追加本次部署 + 日志清理记录，并更正 FB-041 的双栈判断
- 备注：停服清理期间网关不可用约 8.5 分钟（大表 DELETE 耗时），期间所有客户端请求会失败；双栈尝试导致的 IPv4 中断约 40 秒
- 未提交、未推送（用户明确「先别急提交」）

### 2026-10-22 - FB-041 中转站双栈监听改造（B 线-小，1 行，配 WireGuard 直连架构）
- 背景：用户提出 WireGuard IPv6 直连改造（云中继流量几天 100+G），并要求中转站支持公网 IPv6/域名访问
- 实测确认：10002 仅监听 0.0.0.0（IPv6 curl HTTP 000）→ 根因 run.py `host="0.0.0.0"`
- 实施：run.py `host="::"`（Linux 双栈）；配套 ufw 放行 10002/tcp + ddns-go AAAA 域名一箭双雕（同条记录服务 WG :51820 与 API :10002）都固化在《WireGuard直连改造-Ubuntu侧执行手册》（A5b/A6/阶段 C），服务器侧由 Ubuntu AI 随手册执行
- **2026-10-22 修正**：`host="::"` 并不是双栈（Python 3.12 asyncio 置 `IPV6_V6ONLY=1`，只监听 IPv6）→ 已改为显式双栈 socket 并上线，见本文件顶部 v5.2.4 部署记录
- 边界决策：团队 KPI(8000) 不开公网（默认弱口令 + 工作数据）；10002 公网暴露前置条件 = admin 强密码 + 换 sk-CHANGE-ME 系列 Key
- 涉及项目仓库改动仅 run.py 1 行，已记 feedback-log FB-041 / 变更记录

### 2026-10-22 - CH-048 分组管理改为弹窗编辑（B 线-小，纯前端）
- 触发：用户验收 CH-047 时说「这一版改的很完美了，稍微改一个地方」—— 分组管理要和上游源一样，条目是展示的、点右侧「修改」才弹窗，添加分组也弹窗填写
- 分类（铁律 7）：功能正常、只是形态不对 → **B 线（设计调整）**，先写 `docs/_changes/CH-048` 再改代码
- 用户拍板（AskUserQuestion）：**即时保存，去掉「保存分组」按钮**
- 定位（铁律 2）：CH-047 把分组管理换成 `ListPage` 后，两列仍是 `BaseInput`、新增是 push 空行、靠「保存分组」兜底 → 看着只读、实际可编辑，与上游源形态不一致
- 实施（只改 `Settings.vue`，后端零改动）：①列改纯文本 + 描述空值显示 `—`；②操作列改「修改 / 删除」；③右上「+ 添加分组」→ `openGroupAdd`；④新增/修改共用 `groupModal` + `BaseModal` + `BaseModalFooter`；⑤`commitGroups()` 统一提交（成功/失败都 `load()` 回真值）；⑥删掉 `groupsForm` / `savingGroups` / `handleSaveGroups` / `removeGroup` / `addGroup` 等死代码；⑦补空名与重名校验；⑧删掉 `commitGroups` 里的 `ElMessage.error`，避免与 `request.ts` 拦截器重复弹
- 中途失误：替换时把 `addGroup`/`removeGroupRow`/`handleSaveGroups` 复制成了三份，已用整段替换清理干净（教训：SearchReplace 的 `old_str` 取太短会定位到相邻重复块）
- 验证（浏览器逐项）：表格内 0 个输入框；新增弹窗「添加分组 / 分组名 / 描述 / 取消·确定添加」；重名「分组「free」已存在」且弹窗不关；新增/修改/删除均即时生效；删除被引用的 `free` 弹出后端 400 文案；空名提示；取消可关闭；测试数据 `ch048-test` 已清理，分页回到「共 2 条」；`npm run build` 通过（Settings 15.13 kB）
- 文档同步：新增 `_changes/CH-048`；`_changes/README` 登记；`变更记录.md`；`STATE.md`（CH-047 标注 + CH-048 新行）；`feedback-log.md`（FB-040）；`架构设计.md`（6.7 规范一取消「+ 添加分组在表格下方」的例外）；本日志
- 服务：全程保持运行（端口 10002）

### 2026-10-22 - CH-047 列表批量操作与筛选补齐（B 线-中，纯前端）
- 触发：用户验收 CH-046 后指出五点 —— ①模型别名批量操作不全 ②探测模板/探测单元明细没对齐 API Key ③用量统计除明细外其他没对齐 ④请求过滤批量操作不全 ⑤系统设置的分组管理没改好
- 分类（铁律 7）：补齐既有组件用法，无后端/DB 变更 → **B 线-中**
- 用户拍板（AskUserQuestion）：只读表只补「筛选 + 导出」；模型别名加批量删除、请求过滤加批量启停删、探测模板加批量删除+导出、分组管理改成标准列表
- 实施（按页一次只改一处）：
  - `Pointers.vue`：批量删除（逐条容错，删除后 `reloadConfig` + 重算页码 + 与最新列表求交集）
  - `FilterRules.vue`：批量启用/停用/删除（`updateFilterRule` 顺序执行，失败即中断并报后端 detail）
  - `TemplatePanel.vue`：补全选 + 批量删除（走父组件 `emit('remove')`，因单删已在父级处理）+ `dataset="probe-templates"` 导出
  - `ProbePlanPanel.vue`：接 `dataset="probe-units"` 导出
  - `Usage.vue`：三张汇总表各加关键字筛选（模型名 / 上游名+模型 / Key 名+ID），筛选后全选只作用于筛选结果
  - `Upstreams.vue`：补名称/ID/URL + 分组 + 状态三组筛选（原只有未接线的 `filters`）
  - `Aggregated.vue`：聚合模型补「聚合名 / 类型 / 状态」三组筛选 + `resetAggFilter`
  - `Settings.vue`：分组管理改标准列表（`ListPage` + `DataTable` + `ListToolbar` + 行内删除），**保留「保存分组」按钮**（后端 `updateGroups` 是全量替换语义，不能即时提交），旁加 `BaseHint` 说明
- 两项自查额外补齐（用户未点名但同属「没对齐」）：上游源筛选、聚合模型筛选
- 明确不做：探测单元明细的筛选 —— 数据随 plan 一次性返回（单次规模有限），加前端筛选属过度设计
- 验证：`npm run build` 通过（Settings 14.07 / Upstreams 30.56 / Usage 24.04 / Aggregated 60.32 / FilterRules 15.01 / Pointers 9.75 kB）；浏览器逐页实测 —— 模型别名「全选 共 0 条 批量删除 批量导出 导出」+ 空态仍有分页、请求过滤勾 1 行「已选 1 项 取消选择 批量启用 批量停用 批量删除 批量导出」、上游源搜 `xiaomi` → 共 1 条剩 1 张卡、聚合页 3 组筛选 + 模板工具条 + 单元「共 6 条 导出」、分组管理「共 2 条」列表化且保存按钮在
- 文档同步：新增 `_changes/CH-047`；`_changes/README` 登记；`变更记录.md`；`STATE.md`（CH-046 标注 + CH-047 新行）；`feedback-log.md`（FB-038 标注 + FB-039）；本日志
- 服务：全程保持运行（端口 10002，预览库 `.tmp_preview/preview.db`）

### 2026-10-22 - CH-046 全站列表统一收口（B 线-中，纯前端）
- 触发：用户「先查一下还有哪些列表显示没统一用组件，以 API Key 管理为标杆」，点名最近请求明细缺多选批量、模型别名空态无分页、用量三表没换组件
- 分类（铁律 7）：组件缺陷修复 + 六处迁移，无后端/DB 变更 → **B 线-中**
- 体检（先分析后动手）：15 处列表分四类 —— 已达标 6 / 功能不齐 4（用量四表）/ 形态不对 2（探测模板、探测单元）/ 口径不一 2（别名、过滤）+ 组件缺陷 1（`ListPage` 的 `total > 0`）
- 用户拍板：三批一起做；单条维护类「加多选但只给批量导出」
- 实施：①`ListPage` 去掉 `total > 0`；②`Usage.vue` 三张汇总表拆独立 `ListPage`（各自分页/全选/批量导出），明细独立成 `ListPage` 并加多选与批量导出；③`TemplatePanel.vue` / `ProbePlanPanel.vue` 改 `ListPage`+`DataTable`+`ListToolbar`+`RowActions`；④`Pointers.vue` / `FilterRules.vue` 加 `selectable`+全选+批量导出
- 明确不动：分组管理（行内编辑）、已配置模型（卡片内子表）、路由规则候选表（嵌套只读子表）
- 验证：`npm run build` 通过；浏览器逐页 —— 模型别名空态 0 条仍显示「共 0 条 20 条/页 1 前往 页」（原缺陷已修）、请求过滤勾 2 行「已选 2 项」、用量页 4 标题+4 工具条+4 独立分页、探测模板 0 条有分页、探测单元 6 条有分页
- 文档同步：新增 `_changes/CH-046`；`_changes/README`；`变更记录.md`；`STATE.md`；`feedback-log.md`（FB-038）；`架构设计.md`（6.6.1 补空态分页说明）
- 服务：全程保持运行（端口 10002）

### 2026-10-22 - CH-045 列表工具条全选 + 上游源/聚合模型发现统一（B 线-中，纯前端）
- 触发：用户「缺了快捷全选的按钮，像 API Key 管理那样有个按一下全选的框；上游源列表、疑似同一模型（改名叫聚合模型发现）也照这个组件换上」
- 分类（铁律 7）：组件能力补齐 + 两处列表统一，无后端/DB 变更 → **B 线-中**
- 定位：卡片条目没有 `el-table` 表头 → 表头全选框丢失；上游源仍是 `BaseSection` + 裸 `v-for`，无统一工具条/分页/批量
- 方案取舍（铁律 6 设计前对齐）：`ListPage` 不知道条目结构、`EntityCard` 是被选对象 → 全选放 `ListToolbar` 左侧（本就持有 count/total）
- 实施：①`ListToolbar` 加 `selectable`/`allChecked`/`indeterminate` + `toggle-all`，只作用于当前页（并集/差集）、带半选态、竖线分隔；②`Upstreams.vue` 改 `ListPage` + 跨页选中 + 批量启用/禁用/删除（删除走 confirmDanger 提示路由候选失效）；③`UpstreamCard.vue` 加 `selectable`/`checked` 透传 `EntityCard`，内部 `ModelList` 原样保留；④`Aggregated.vue` 「疑似同一模型（建议合并）」→「聚合模型发现」+ 改 `ListPage`（`pagination=false`）+ 聚合列表接全选
- 未动：API Key 页是 `el-table`，已有表头全选，无需改
- 验证：`npm run build` 通过；上游源 10 卡 + 全选后「已选 10 项」10 张全勾 + 底部「共 12 条 10 条/页 1 2」；聚合页全选后「已选 5 项」；区块标题已改名；截图确认视觉
- 文档同步：新增 `_changes/CH-045`；`_changes/README`；`变更记录.md`；`STATE.md`（并修正行序为 CH-044→CH-045）；`feedback-log.md`（FB-037）；`架构设计.md`（6.6.1 工具条职责 + 6.6.2 关键取舍 5）
- 服务：全程保持运行（端口 10002）

### 2026-10-22 - CH-044 聚合模型列表化 + 卡片内分页修正（B 线-中，纯前端）
- 触发：用户验收 CH-043 时指出两处偏差 —— ①仪表盘右边高、左边应补到同高（否则露灰底）；②聚合模型本身就是一个列表，分页应在列表右下角而不是卡片内，批量操作在右上角；并补充「没有拖拽也行，你自己分析需不需要留」
- 分类（铁律 7）：结构调整 + 交互修正，无后端/DB 变更 → **B 线-中**
- 定位（铁律 3 先定位再改）：①`.two-col` 的 `align-items: start` 是 CH-043 我改反的；②分页被做进了 `ChipFlow` 内部；核查组件能力发现 `DataTable` 只能渲染表格行，但 `ListPage` 默认插槽本就支持卡片条目（源码注释已写明），**是没用对不是组件不行**
- 实施：①聚合组区块改 `ListPage`（标题+右上批量 / `ListToolbar` 常驻 / 卡片条目 / 底部 `TablePagination`）；②`ChipFlow` 加 `pager` 开关、默认 false 平铺；③`EntityCard` 加 `selectable`/`checked` + `update:checked`，勾选框挂标题行最左，`.ec-title` 加 `flex:1` 把操作区推到最右；④选中按聚合名存（不存行对象），跨页保持、批量启停后保留、批量移除逐条容错 + 与最新列表求交集；⑤**移除前端 Sortable 拖拽**（含 `.drag-handle` / `.drag-ghost` 样式与手柄节点、`reorderAggregations` 导入），保留后端 `PUT /aggregations/order`；⑥`.two-col` 改 `stretch`，`.trend-card` 纵向 flex、`.chart-wrap`/`.trend-svg` 撑满
- 拖拽取舍分析（用户让我自己判断）：去掉。理由 —— 纯展示顺序不参与路由决策、与分页冲突易误解为全局排序、展示型列表通用形态是筛选+表头排序
- 验证：`npm run build` 通过；浏览器实测 —— 卡片内 `.cf-pager` 0 个、列表底部「共 5 条 10 条/页」、造到 13 条时出现 `1 2` 页且跨页选中保持（第 1 页勾 1 项→翻第 2 页→仍「已选 1 项」→翻回勾选还在）、批量关闭后 2 项仍勾选、`.drag-handle` 0 个、仪表盘左右两栏均 372px 且图表实际 259px
- 数据修正：发现趋势图不渲染的根因是 `log_usage.ts` 存 unix 时间戳而验收数据写成了字符串，改正后 7 天趋势正常
- 清理：临时聚合 `ch044-demo-*` 8 个已删除；`ch043-big`/`ch043-small` 保留作验收样例
- 文档同步：新增 `_changes/CH-044`；`_changes/README` 登记 + 标注 CH-043 已被修正；`变更记录.md`；`STATE.md`；`feedback-log.md`（FB-036 + FB-035 补注）；`架构设计.md`（6.6.2 关键取舍 1 修正 + 新增取舍 4、6.7 规范六撤销拖拽）
- 服务：全程保持运行（端口 10002）

### 2026-10-22 - CH-043 卡片壳与成员流统一 + 批量选中保持（B 线-中，纯前端）
- 触发：用户三点反馈「①批量操作后选中状态丢了 ②仪表盘东西一多撑变形 ③聚合模型/疑似同一模型/上游源其实是同一种列表，却各维护一套组件」
- 分类（铁律 7）：抽二级组件 + 交互修正，无后端/DB 变更 → **B 线-中**
- 设计前对齐（铁律 6）：体检出卡片外壳 6 份、只读 chips 流 4 份、chip 样式 4 套；给出三档方案，用户拍板 **路线 A**（ChipFlow + EntityCard，不做 DataTable 展开行），并明确「成员超出做成和列表组件一样的分页」
- 实施（一次只改一处）：①新增 `base/ChipFlow.vue`（每页 10、序号跨页连续、首「首选」末「兜底」、≤pageSize 不渲染分页条）；②新增 `base/EntityCard.vue`（五插槽）；③`list/DataTable.vue` selection 列加 `reserve-selection` + 新增 `setSelection(keys)`；④`views/ApiKeys.vue` 批量启停保留选中、批量删除逐条容错 + 与最新列表求交集；⑤`AggregationCard`/`Aggregated`/`Dashboard`/`UpstreamCard` 换壳换流；⑥`dashboard.css` 改 `align-items:start` + `.share-list` 限高 320px
- 读代码确认（铁律 3/4）：先读 `ApiKeys.vue` 批量逻辑与 `DataTable.vue` expose，确认「父组件清空数组不同步表格勾选态」，因此必须显式调 `setSelection`
- 验证：`npm run build` 通过；浏览器逐项实测 —— 批量禁用后 3 行仍勾选、批量删除后复选框 `[false,false]` 无幽灵、12 成员聚合第 2 页序号 11/12 连续且末个「兜底」、12 上游时 `.share-list` 320/727 内部滚动且左栏仍 137px 未被拉长
- 清理：验证造的 12 个测试上游 / 36 条测试用量 / 临时聚合 `ch043-demo` / 两源临时模型全部删除
- 文档同步：`_changes/CH-043`（补 5.1 实测表）/ `_changes/README` / `变更记录.md` / `STATE.md` / `feedback-log.md`（FB-035）/ `架构设计.md`（新增 6.6.2 + 目录树 + 变更表）
- 遗留：第二档（探测模板 / 探测单元 / 分组管理）与第三档（上游源 / 聚合 / 规则卡片 / 仪表盘）待用户指示
- 服务：全程保持运行（端口 10002），未中途停止

### 2026-10-21 - CH-042 列表页二级组件（B 线-大，样例阶段）
- 触发：用户「前端整体乱糟糟，列表各做各的样式，缺列表这种二级组件；先做样例看效果，不要把我原来的东西直接干掉」
- 分类（铁律 7）：新增组件层 + 新页面，纯前端 → **B 线-大**
- 先分析后动手（用户要求「先分析，不要操作」）：体检 13 处列表，量化 7 个不一致维度 + 3 条根因（封装对象错 / 缺组合契约 / 约定靠文档不靠组件）
- 用户拍板三项：DataTable 走 **A（包 el-table）**、分页默认开、**先做样例页**
- 写变更文档 `docs/_changes/CH-042-列表页二级组件.md`（含 2.1 用户约束：不推翻现有设计）
- 实现 `components/list/` 七组件：ListPage / DataTable / FilterBar+FilterField / ListToolbar / TablePagination / StatCard / RowActions（+ types.ts / index.ts）
- 实现样例页 `views/DesignPreview.vue`，四形态：标准列表 / 批量操作 / 指标+列表 / 卡片列表
- 路由 `/design-preview` + 侧边栏入口（标注「验收后可移除」）
- 两处编译错误并修正：①`rateTone` 字符串字面量类型过宽 → 显式断言联合类型；②`avg_duration_ms` 列对象换行错位
- 验证：`npm run build` 通过（DesignPreview 21.2 kB）；本地起服务（临时库 `.tmp_preview`）浏览器实测四种形态全部正常，勾选后批量工具条正确出现（已选 12 项），控制台仅登录页遗留无障碍提示、无运行时报错
- **未动现有 13 处列表 / UpstreamCard / AggregationCard / Dashboard / BasePagination / 后端**（用户明确要求）
- 清理临时库；文档同步：架构设计 6.6.1 + 目录树 + 变更记录、docs/变更记录、_changes/README、feedback-log（FB-034）
- 未提交未部署，**待用户看效果确认**

### 2026-10-21 - CH-042 第二轮：工具条常驻 + 后端 xlsx 导出
- 用户反馈：只有「批量操作」符合想法；工具条要常驻、配色改灰不要蓝；加「导出」按钮（xlsx），无批量操作的列表也要能导出
- 用户确认三项规格：导出=全部、批量导出=选中项、格式 **xlsx**（后续要提取骨架做模板，要求做完善）
- **关键约束识别**：生产部署脚本 `deploy_v520_full.py` 只同步代码不装依赖 → **不能加 openpyxl**，改用标准库 `zipfile` 手写 xlsx
- 后端新增 `core/xlsx_writer.py`（6 个 part 最小 OOXML）+ `api/admin/export.py`（GET 全部 / POST 批量 / datasets 清单 / 10 个数据集）
- 踩坑：`styles.xml` 漏 `<cellStyles>` → openpyxl 警告「no default style」，部分 Excel 提示文件损坏；补上后 openpyxl 反向校验 13 项全过
- 路由顺序坑：`/export/datasets` 必须声明在 `/export/{dataset}` 之前，否则被通配吃掉
- 前端 `api/export.ts` 用**独立 axios 实例**（共享实例的响应拦截器 `return response.data` 会丢掉 `Content-Disposition`，拿不到中文文件名）
- `ListToolbar` 重做：常驻、灰底（`--bg-elevated`）、左侧未选中显示「共 N 条 · 已启用 X 个」、内建「导出」与「批量导出（N）」
- `DataTable` 暴露 `clearSelection()`（父组件清数组不会同步 el-table 内部勾选态）
- 验证：`verify_export_ch042.py` **31 项全通过**、`npm run build` 通过、浏览器实测点「导出」→ 200 + PK zip + `API Key_20261021-2058.xlsx`
- 文档同步：CH-042 变更文档（4.4 重做 / 4.5 导出 / 5.1 文件清单 / 六、验收）、docs/变更记录
- 仍未动现有 13 处列表；**待用户看效果后改「第一档 5 处」**

### 2026-10-21 - CH-042 第三轮：工具条定稿 + 第一档 5 处迁移
- 用户四条调整：①批量导出与导出交换位置 ②去掉两者间分割线 ③批量导出不显示条数 ④批量按钮常显、未选中置灰禁用
- `ListToolbar` 重构：新增 `actions: RowActionItem[]` 配置驱动（不再靠 `v-if`），未选中统一 `disabled`；按钮顺序 `批量操作 → 批量导出 → 导出`；删除 `.lt-divider`
- 迁移第一档 5 处：
  - `Pointers.vue`：筛选 + 常驻工具条 + DataTable + 分页 + RowActions
  - `FilterRules.vue`：新增三组筛选 + 工具条 + 分页；全局开关移到 `#notice`
  - `ApiKeys.vue`：筛选 + 多选 + 批量启停/删除 + 批量导出；操作列 4 项改 RowActions
  - `Usage.vue`：StatCard 指标卡 + 3 张汇总表各配工具条 + 明细换 FilterBar/TablePagination（保留行点击详情）
- 后端 `export.py` 补筛选参数支持（pointers/api-keys/filter-rules/usage-*），保证「导出 = 你看到的这批」
- 踩坑：`BaseInput` 不支持 `clearable` 属性，已移除
- 验证：`npm run build` 通过、`compileall` 通过、31 项导出测试全过、浏览器逐页实测（pointers/api-keys/usage/filter-rules）渲染正常且控制台无运行时报错、筛选后导出 200 + PK zip
- 文档同步：CH-042 变更文档（4.6 工具条定稿 / 4.7 迁移清单）、docs/变更记录
- **第二档 / 第三档未动**（用户尚未指示）

### 2026-10-21 - CH-041 请求过滤引擎（B 线-大，走 stage-1→5 迷你流程）
- 触发：用户提问「别人一直用 DSH 调 buddy，号池会不会封号？能不能配置过滤，命中就不发给 buddy，并回执提示」
- 分类（铁律 7）：新增模块 + 新数据链路 + 前端页 → **B 线-大**
- 分析：对比三方案（静默切 / 返回提示再路由 / 返回提示不路由）→ 用户选 **A 静默切**（聚合无感）+ 直连命中返回提示
- 关键认知：CH-040 是**事后兜底**（请求已发出、违规已计），本变更才是**事前防护**（违规计数 0）
- 迷你 stage-1/2：写 `docs/_changes/CH-041-请求过滤引擎.md`，含需求、三分支行为契约、表设计、API 契约、五列矩阵、验证方案
- 用户确认三项：预置两条规则默认关 / 直连返回 400 / **用量页也要能看到**（不能只埋日志）
- 实施顺序（铁律 3，一次只改一处）：增量 SQL 12 → repo → config 加载 → filter_engine 纯函数 → router_service 接入 → 管理端 API → 前端页 → 验证脚本
- **测试逼出两处真问题**：
  1. static 聚合原本返回 `direct`，导致命中过滤时返回 400 而非静默切换 → 改为返回 `static_agg`，过滤按 `aggregated/static_agg` 判定聚合语义。根因：我误把「同名模型分布在两源」当成聚合，实际只有 `agg_unified` 行才是门面（`auto_same_name_aggregate` 默认关）
  2. 初版过滤放在 tracker 创建之前，被拦请求不进用量表 → 与用户「用量页要可见」冲突 → 调整顺序为先建 tracker 再过滤
- 另一处为测试自身错误：试跑端点用 API Key 调用返回 401，管理端需 JWT —— 代码无误，改测试
- 验证：43 项全通过（含「引擎关闭零影响」「未命中零影响」两条回归保障）；回归 CH-039/040/038/037/034/036 六套全通过；`compileall` 0 错误；`npm run build` 通过
- 卫生：`seed.py` 与 `deploy_v520_full.py` 同步增量 12，`drop_all` 补 `filter_rule`；全新环境 seed 实测表/索引/2 条预置规则/全局开关全部就位
- 收尾：文档同步 10 份（需求规格 功能点 9.7 / 架构设计 / 数据库设计 3.11.2 / API契约 / 接口文档 / 系统核心流程 / 功能清单 2.10.6 + D045~D048 / 五列矩阵 / README 能力表与后台清单 / _changes 台账）；版本号统一 **v5.2.3**（README / main.py / pyproject / package.json / run.py）；`git checkout` 还原被 uv 重写的 `backend/uv.lock`（仅源地址噪音，无依赖变更）
- **部署上线**（用户指示「先部署，再提交代码」）：`deploy_v520_full.py` 9 步全过，备份 `/opt/smart-router/backup/20261021-105506`；增量 12 `APPLIED ok=5`（`filter_rule` 表 + 索引 + 全局开关 false + 2 条预置规则）；`COMPILE_OK`；重启后 `配置已加载: 12 上游源, 3 规则, 6 密钥, 1 别名, 12 聚合`、`Smart Router v5.2.3`；`SMOKE_OK`
- 顺带把冒烟脚本升级：新增 CH-041 校验（`filter_rule` 表存在、`GET /admin/api/filter-rules` 200、`enabled=false`、两条预置规则在列），失败即 `SMOKE_FAIL`
- **上线后自查发现配置错误并修正**（用户授权引擎后试跑）：
  - 试跑真实生产聚合，发现 **9 个启用中的聚合全部被拦空 → 客户端会拿 503**，与设计的「静默换成员」相反
  - 根因：拦截**按渠道**生效。实测仅 `buddy` / `workbuddy` 拦 DSH/Claude Code 身份声明，`trae` / `loomy` / `lobsterai` 放行；预置规则 `upstream_ids=NULL`（全部源），把放行渠道一起拦掉了
  - 取证：`log_usage` 里 buddy 5398 次全成功（本机已禁开场白，首行是 `You are a coding agent powered by ...`）、workbuddy 3 次全失败（`request illegal`）；运行日志无 DSH 黑名单记录，确认是「别人没禁用开场白才会踩」
  - 修正：生产走管理端 API 把两条规则作用源改为 `["buddy","workbuddy"]`，复验 7/9 聚合恢复切换、`hy3`/`hy4-preview` 本身只有这两个成员仍 503（真实情况）
  - 同步仓库：增量 12 默认值改为 `'["buddy","workbuddy"]'` + 注释说明为何不能留空；验证脚本用例 11 增加作用源断言（顺带修掉测试自身污染——用例 2/6 会改写同条规则，改为先抓快照）；43 项复跑全通过
- 用户 2026-10-21 决策：作用源**只配 buddy + workbuddy**，其他渠道等发现后再自行添加；数据库初始化选 **B 方案**（保持增量脚本，只在 README 写明「结构以 seed.py 为准」）

### 2026-10-21 - v5.2.2 全量部署上线 10.10.0.2（用户提供 SSH 凭据授权）
- 授权链：用户上次会话末「只提交推送」→ 本次直接给出 `root / <密码> / 22` 端口 → 判定为授权部署
- 部署前核对：工作区干净、HEAD = `9cb311f`；`--dry-run` 打包 backend 80 / sql 14 / dist 52（`.tmp_*` 未混入）；前端源码自 CH-038 未改，dist 无需重建
- 生产只读探查：服务自 2026-10-20 00:20 运行（CH-039 部署点），12 上游 / 12 聚合 / 9142 条用量，增量 11 的列与 `log_usage_detail` 均已在 → **本次纯代码部署，无新迁移**
- 执行：9 步全过，备份 `/opt/smart-router/backup/20261021-003244`；预迁移 7 个脚本全部 `APPLIED`（幂等）；`COMPILE_OK`；重启后 `active`、启动日志 `12 上游源, 3 规则, 6 密钥, 1 别名, 12 聚合`（配置未清空）、`Smart Router v5.2.2`；冒烟 `SMOKE_OK`
- **生产立即验证 CH-040**：部署后 1 分钟内自然流量即出现
  ```
  [WARNING] 模型 glm-5.3-flashx 返回 200 但响应体是错误包: 账号已被禁用 | UNKNOWN | 502，视为失败并重试
  [INFO] 重试(2/2): glm-5.3-flashx 失败 → 尝试 glm-5.3-flashx
  ```
  证明识别与切候选在真实流量上生效
- 部署后核对聚合链路：`deepseek-v4-1-flash` 5 成员、`retry.max_attempts=3`、`trae` 在第 3 位且放行 → 不依赖 DSH 侧改动也能自愈
- 凭据落位：`E:\80-project_dev\.sr_deploy_pass`（仓库外，不入库）；部署脚本按既有设计自动读取，未在命令行回显密码

### 2026-10-20 - DSH web profile 关闭身份开场白（配置改动，非本仓库）
- 文件：`C:\Users\wjz666123\.dsh\profiles\web\cordis.patch.yml`（备份 `.bak-20261020-ch040`）
- 追加 `- id: system-prompt` 覆盖层，置 `includeHarnessIdentity: false`，并原样保留 `personaPrefix` / `personaSuffix`（该文件开头警告「patch 按 id 替换整行 config」）
- 校验：YAML 解析通过，`system-prompt` 行 config 三字段齐全
- 生效后首行变为 `You are a coding agent powered by the {{model}} model.` —— 本机实测该行**不被拦截**
- 待用户重启 DSH 验证

### 2026-10-20 - CH-040 补充：用户带来第三方分析，本机实测修正首轮结论
- 触发：用户提供一份第三方 AI 分析（称腾讯 WorkBuddy 渠道维护了「非官方 agent 客户端」黑名单，按 system 消息首行精确匹配），并授权「用本机 127.0.0.1:8326 测」
- 本机对照实验（`buddy/deepseek-v4.1-flash`，只读探测，不改配置）：
  - `You are an AI agent powered by DeepSeek Harness.` → **拦截**
  - 前加空格 / 换行 / 无关一句 → 通过
  - `agent` → `assistant`、加逗号 → 通过
  - 仅 `.` → `?` → **仍拦截**
  - 无 system → 通过
- **首轮结论被推翻**：首轮说「号池侧偶发策略」，实为**内容精确匹配**。首轮错在取样维度——只按 UA/Key/upstream 分组，从未看 `request_body.messages[0]`
- **首轮推论也被修正**：首轮说「11 源同网关，聚合切换绕不过」，实测为**按渠道判定** —— `trae` 渠道放行、`buddy` 渠道拦截，跨渠道切换真实有效
- **状态码链路差异**（解释 CH-040 为何必须解析首行）：直连非流式 400、网关聚合非流式 502、**流式一律 200 + SSE 内塞 error**（生产库记的正是这一形态），因为 SSE 响应头已发出后无法改状态码
- **DSH 侧发现官方开关**：`@deepseek-ai/dsh-system-prompt` 的 `SystemPrompt.Config.includeHarnessIdentity`（默认 true），置 false 即不注入，比改字符串干净
- 文档同步：CH-040 文档新增第五节「真正触发条件」+ 第九节「职责边界」；需求规格 9.7 修正并新增条目；变更记录补章
- 只读原则：全程未改 DSH 配置、未改中转站请求内容、未伪装 UA；临时探测脚本已删除

### 2026-10-20 - CH-040 上游「200 + 错误包」误判为成功：修 A 线
- 授权链：用户反馈 DSH 报 `buddy: 请求被拦截... Illegal API invocation from an unapproved channel`，但中转站显示成功 → 我出定位与方案 → 用户「可以，按照你这个来，注意我是在 dsh 中用出现的这个问题…这个也一样考虑上」→ **用户纠正流程「不要直接改，先加载 skill，跟着流程来做，这也是一次 bug 修复了嘛」** → 我加载 skill、补写变更文档后重走 A 线
- 用户澄清语义：「我说的切换源是聚合模型，我们聚合模型有好几家的聚合到一起了，用户请求这个模型，路由到了第一个，第一个失败了，会不会在用这个聚合里面的别的发请求」→ 确认聚合 `deepseek-v4-1-flash` 有 3 成员、`max_attempts=3`，链路能力本就存在，只是被 200+错误包堵死
- 分类（铁律 7）：代码未按设计意图实现 → **A 线（bug）**
- 定位（铁律 2）：详情表取到 `log_id=8661` 原始响应体 —— **HTTP 200 + `choices: []` + `error{INVALID_REQUEST, status:400}`**；主表记 success、`completion=0`、`estimated=1`；UA 分组显示 DSH 2 成功 1 失败；同 Key 同源 `8660` 成功（84s/4952 tok）、`8661` 失败 → 偶发
- 推翻初版方案（**关键决策**）：原打算透传客户端 UA 给上游。取证发现 11 个上游源共用同一 Key 与同一 `base_url`（`127.0.0.1:8326`），失败与成功请求 UA 完全相同 → UA 不是区分变量。判定 `unapproved channel` 属号池侧策略，我们只做「正确识别 + 正确记账 + 正确重试」，不伪装 UA
- 改动（3 处）：`_extract_wrapped_error` / `_parse_sse_error_line` 两个判定函数；`try_stream` 首行判定（此时未向客户端发任何字节，可安全切候选）；`try_non_stream` 200 分支先解析再判定；`_UsageTracker.stream_error` 覆盖「首行之后才报错」
- 验证：`test/verify_wrapped_error_ch040.py` **36 项全通过**，含用户实际场景「agg_unified 2 成员首成员错误包 → 切到 src_good」（流式+非流式，断言 `attempt_count=2`、`upstream_id=src_good`）；离线回归 7 套通过
- **一个假失败（教训）**：首轮 [7][8] 失败看似 contextvar 串扰，插桩一度误导。真因是测试脚本自己把 `src_bad` 唯一 Key 打到 `max_fails=3` 触发 120s 冷却，`pick()` 返回 `None` 后直接 `break`，根本没发请求。**铁律 4 的价值在此体现：没有猜测式改代码，而是继续取证直到拿到 key_pool 状态**
- **另一处教训（结论层面）**：首轮把根因判为「号池侧偶发、无法定位」，实为**取样维度不足**（只看元数据没看请求内容）。后续本机实测推翻了该结论，详见上一条
- 未提交、未部署（用户要求攒批次）

### 2026-10-20 - CH-039 流式 usage 透传：修 A 线 + 部署上线 10.10.0.2
- 授权链：用户反馈「DSH 能正常对话，但显示 `1轮1步 · 0 tok/s`、上下文 `0%`」→ 我出定位报告与方案 → 用户「可以，就按照这个方案来」→ 我按 A 线改 + 验证 → 用户「先部署吧，不着急推送。等多更新一些功能，算一个小版本后一推送」
- 分类（铁律 7）：代码未按设计意图实现 → **A 线（bug）**，不写变更文档改设计
- 定位（铁律 2，先定位再改）：生产只读取证 `estimated=0/200`（服务端确实解析到真实 token）→ 近 3000 行日志 `1458 POST /v1/chat/completions`、`/v1/messages` 与 `/v1/responses` 各 0 条 → 缩小到 chat 流式路径 → `router_service.py` L395 把 `tracker.injected_usage` 当 `client_wants_usage` 传入（两者语义相反）
- 影响面尤点：客户端不传 → 注入 → `injected=True` → 剥离；客户端**传了** → 不注入 → `injected=False` → **同样剥离**。殊途同归，所有流式客户端一律收不到 usage
- 改动（单点，铁律 3）：注入分支之前先记录 `client_wants_usage`；`_forward()` 新增该参数并透传；`_wrap_stream_with_usage()` 改收真实意图；`injected_usage` 保留但改注释，明确不参与剥离决策
- 验证：`test/verify_usage_passthrough_ch039.py` 19 项全通过（两种客户端意图 + 记账 + 正文完整 + 非流式）；回归 7 套全通过；`compileall` 0 错误
- 同类勘察（本次不修、已登记需求规格 9.7）：Anthropic 入站 `message_start`/`message_delta` usage 写死 0；Responses 入站 `response.completed` 无 usage。依据是两者生产流量为 0
- 部署：9 步全过、`SMOKE_OK`，备份 `/opt/smart-router/backup/20261020-002036`
- **顺带修复部署卫生**：发现 `backend/.tmp_ch039/t.db` 被同步进生产（Windows 上 SQLite 文件锁使验证脚本的 rmtree 静默失败，而 `_skip_backend` 只按文件名挡 db）→ 改排除规则为「目录名 + 后缀」双重排除，并清理本地与远端临时目录
- **未提交、未推送**（用户要求攒够一批再作为一个版本推送）

### 2026-10-19 - v5.2.1 全量部署上线 10.10.0.2（用户授权「执行吧」）
- 授权链：用户先说「等你提交完，我换了模型再部署」→ 提交推送完成（67be8e3 / bc79aff / 51f47ae）→ 用户看到 README 版本号未同步，指出「不能只改号码，各文档都要对得上」→ 修正 6 处一致性缺陷并推送 → 用户「好的，执行吧」
- 前置问题 1（**会静默毁数据**）：部署脚本 `MIGRATE_FILES` 漏了 `increment/11`，重启后新代码写 `log_usage` 三列与 `log_usage_detail` 会全部失败。已在 51f47ae 补齐并加冒烟断言
- 前置问题 2（隐私）：脚本第 382 行硬编码管理员密码（明文），已改为从生产库读取且不打印。**该密码仍在 git 历史中**，是否清洗/轮换待用户决定
- 凭据路径：本机 `~/.ssh` 只有 known_hosts、无密钥，探测返回 `No authentication methods available` → 必须用密码；经确认后由用户提供，用 `$env:SR_SSH_PASS` 单次传入
- 执行前校验：`--dry-run` 通过（backend 80 / sql 14 / dist 52）；确认 sql 清单含 increment/11、dist 为最新构建且 Usage 分块含详情抽屉文案
- 部署结果：9 步全过，备份 `/opt/smart-router/backup/20261019-232936`；启动日志 `11 上游源, 3 规则, 6 密钥, 1 别名, 12 聚合`（配置未清空，预迁移策略生效）；`log_usage_detail`、三列、`/config/usage-detail` 全部就位；`SMOKE_OK`
- 未做：未提交部署脚本的隐私修改与本次台账更新（按规则不擅自提交，等用户指示）

### 2026-10-19 - CH-038 请求详情可观测性 + 断连记录（B 线-中 + A 线）
- 触发：用户反馈 Trae 21:54 报 `WebSocket ... (HTTP Status: 500)`，但中转站查不到；同时希望日志能记录请求体与上下文长度
- 定位（先定位再改）：四层日志（应用 / journalctl / uvicorn socket / 无 nginx）全无 500，`NRestarts=0` → 请求未到达应用层；`error sending request` 属发送阶段失败，TCP 阶段物理上无法记录（该边界写入文档 + UI 提示，避免再被误判成「网关丢日志」）
- 分类（铁律 7）：断连无痕迹 = A 线（可观测性缺陷）；详情/缓存 token/重试链 = B 线-中。同一条观测链路一起做
- 方案确认（用户拍板）：成功只存结构化字段 + token、失败存完整报文；不截断到 8KB（上限 1 MB）；新增定期清理（默认 14 天，可设 7/14/30/90）
- 实现：SQL 11（主表 3 列 + `log_usage_detail` + 3 个 sys_setting）；`usage_repo` 双表同事务写入与同周期清理；`logging_setup` 断连 499；`core/usage.py` 5 个 contextvar + `parse_cache_tokens` + 采集策略/截断；`openai_adapter` 转发体/响应体/尝试链采集；`api/admin/usage` 详情与设置端点；前端 Token 三段式 + 「尝试」列 + `RequestDetailDrawer.vue` 三栏 + 设置页新区块
- 关键细节：脱敏必须在截断**之前**（截断会切断 `sk-` 前缀使正则失效）；流式只留首尾各 20 条片段，不把整段流堆内存
- 验证：`test/verify_observability_ch038.py` 48 项全通过（含并发 contextvar 隔离、无孤儿详情行、先脱敏再截断）；CH-023/024/034/036/037 七套回归全通过；`compileall` 0 错误；`npm run build` 通过
- **未 push、未部署**：用户要求本版改完一起提交、避免重启中断会话
- 文档同步：README / 需求规格 / 架构设计 / 数据库设计 / API契约 / 接口文档 / 系统核心流程 / 功能清单 / 五列矩阵 / 变更记录 / _changes 索引 / STATE / 本日志

### 2026-10-19 - CH-037 出站消息角色规范化（A 线）
- **流程纠正**：本轮先定位后**直接改了代码**，用户指出「不能直接改，要先给结论/方案、跟 skill 流程走」。已 `git checkout` 回滚未批准的改动、删除 4 个临时诊断脚本，重新按流程执行
- 分类（铁律 7）：客户端发合法请求、网关因上游兼容性全链路失败 → **A 线（bug）**
- 定位链（先定位再改）：生产日志三成员全 400 + 失败请求 `body_snippet` 首条为 `role:"developer"` → 直连号池逐项对比，`developer` 单独触发 400 → 排除 `max_completion_tokens` / `parallel_tool_calls` / `tools=[]` / `reasoning_effort` / `stream_options` / 流式非流式（全 200）
- 方案 A（用户批准）：出站适配器把 `developer` 规范化成 `system`（语义等价）
- 实现：`_normalize_messages()` + 三处调用（`try_non_stream` / `try_stream` / `test_non_stream`，均在 deepcopy 副本上）；顺带补 400 响应体日志（此前只记状态码，导致排查被迫直连号池）
- 验证：`test/verify_role_normalize_ch037.py` 全通过（单元 11 项 + 集成 3 组，用本地 mock 上游断言「上游收到的 role 是 system」）；CH-023/024/034/036 五套回归全通过；`compileall` 0 错误
- **未部署**：用户明确要求，避免重启中断当前会话
- 文档同步：变更记录 / 架构设计 / 接口文档 / 系统核心流程 / 功能清单 / 五列矩阵 / _changes 索引 / STATE

### 2026-10-18 - 部署 CH-034 + CH-036 到生产 10.10.0.2（用户授权）
- 用户原话「部署，不然压根用不了」→ 视为明确授权，立即执行
- 工具复用：`test/deploy_v520_full.py` 整树同步；改动两处 —— `MIGRATE_FILES` 追加 `increment/09` + `increment/10`；新增**第 9 步业务冒烟**（远端自动登录 → 校验开关/聚合列表//v1/models）
- 9 步全过：备份（1.3M db + 644K 代码，`backup/20261018-233737`）→ 传 sql 13 个 → 预迁移 6 脚本全 APPLIED → 传后端 75 py → 换 dist 48 → 清缓存 chown → `COMPILE_OK` → 重启 active + 端点全 200 → 冒烟
- **关键安全点确认**：启动日志 `配置已加载: 11 上游源, 3 规则, 5 密钥, 1 别名, 12 聚合` —— 配置未被清空，证明「重启前预迁移」规避掉了导入期降级（否则全量 401）
- 冒烟初报 `SMOKE_FAIL`：3 个 rule 聚合不在 /v1/models。**先诊断再下结论**（写 `test/verify_prod_ch034_036.py` 只读查库）→ 确认生产上这 3 个聚合 `enabled=0`（用户早前关闭），`aggregated_names` 只收启用的 rule 名 → 断言写错，非缺陷；已修正部署脚本的断言语义
- **决定性验收**（写 `test/verify_prod_facade_ch034.py`）：自动筛查「成员只存在于无权源」的聚合 → 用 Key(`free,premium`) 实测：直连 `buddy/deepseek-v4-flash` → **403**（`无权访问分组 ['no_single_use']`），走聚合 `deepseek-v4-flash` → **200** 且命中 buddy。CH-034 门面语义在生产确认生效
- 顺带发现（如实登记、未擅自改动）：`dsh`(premium) 保留了与 `deepseek-v4-1-flash` 成员同名的 3 个模型 → 对有 premium 的 Key 而言该模型可经 dsh 直连，`no_single_use` 在此模型上数据层面失效；其余 8 个聚合锁定正常。是否清理 dsh 重复模型待用户决定
- 文档同步：变更记录（部署 + 验证 + 数据侧现象）、STATE 标记生产、_changes 状态更新

### 2026-10-18 - CH-036 同名模型自动聚合开关默认关闭（B 线-中 + A 线）
- 用户质疑「自动发现聚合是不是很早做的东西、没必要、还导致 bug」→ 核实：CH-019（2026-10-16）引入，当时前提是「多家真不同供应商都提供同一模型」
- 定位关键事实：`auto_same_name_enabled()` 在 CH-019 就写好了，但**全仓 0 调用点**，设置页无入口 → 开关形同虚设，自动聚合始终开启
- 用户拓扑变化：`dsh` 与 10 个分源共用同一 `base_url` + 同一 `api_key`（同号池）→ 同名跨源聚合零收益
- 方案 A（用户拍板）：保留代码路径 + 接上开关 + 默认关闭，而不是删除逻辑
- 实现要点：`auto_same_name_enabled()` 默认值 `True→False`；`collect_group_members()` / `is_model_group()` 加开关判断；新增 `GET/PUT /admin/api/config/auto-aggregate`；SQL 10 用 `auto_same_name_migrated_v2` 标记保证「只迁移一次」
- 同步收尾 CH-033：SQL 10 精确清理 `enabled=0` + 空成员 + 特定 remark 的空壳行（这些行会进 `_model_groups`，导致同名模型退化为单源直连、丢失跨源兜底）
- 同步收尾 CH-034：保留 `is_static_aggregation()` 的「自动发现不算门面」防御判断（开关打开时仍必要）
- 验证：`test/verify_auto_aggregate_ch036.py` 全通过（含「关闭后跨源兜底仍在：qwen3-coder-480b → ['buddy','trae']」这条关键断言）；CH-034 两套 + CH-023/024 三套回归全通过；`compileall` 0 错误；`npm run build` 通过
- 文档同步 7 份 + STATE/日志；未部署

### 2026-10-18 - CH-034 聚合模型独立分组（B 线-大）
- 分类（铁律 7）：用户反馈「聚合一用就 403 `API Key 无权访问分组 ['no_single_use']`」→ 定位为**设计缺陷**（`agg_unified` 无 `groups` 字段，权限继承自成员），归 **B 线-大**，先写 `docs/_changes/CH-034-聚合模型独立分组.md` 再改代码
- 用户明确补充：**rule 聚合与 static 聚合统一**按聚合自身分组
- 决策：`groups` 空 = 所有 Key 可用（存量 `NULL` 行为不变）；成员分组不参与聚合权限；上游禁用/模型禁用仍按原逻辑
- **实施中发现并修正一个设计边界**：初版把「自动发现聚合」也当门面（`collect_group_members()` 命中也放行），单测用例 4 立刻暴露出问题——同名模型横跨多源时会被隐式放宽为「任何 Key 可用」，绕过 `no_single_use` 保护。改回「只有显式配置（`agg_unified` / 旧 `_model_groups` 有行）的聚合才算门面」
- 验证：新增 `test/verify_group_scope_ch034.py`（19 项）+ `test/verify_models_scope_ch034.py`（TestClient 真实链路）全通过；CH-023/024 三套回归全通过；`compileall` 0 错误；`npm run build` 通过
- 文档同步 9 份：数据库设计 / 架构设计 / API契约 / 接口文档 / 系统核心流程 / 需求规格 9.2 / 功能清单 / 五列矩阵 / 变更记录；STATE 追加维护迭代记录
- 未部署：等用户授权后再上生产 10.10.0.2

### 2026-10-18 - 生产全量部署上线 v5.2.0（CH-020~CH-032 累计 13 项）
- 前置：用户授权部署（明确「原来怎么部署的就怎么部署」），并提供 SSH 凭据（root / 10.10.0.2:22）
- **只读勘察先行**（未改任何东西）：`test/deploy_probe_prod.py` 摸清生产现状 → 发现三处与预期不符的关键事实：①生产 python 是 `/opt/smart-router/backend/.venv/bin/python`（不是历史脚本里的 `/root/miniconda3`）；②`systemd` 以 `User=wjz666123` 运行（不是 root，上传后必须 chown）；③生产库只有 10 张表，**缺 `agg_model_group`/`agg_unified`/`agg_probe_config`/`agg_probe_template`**
- **推翻原部署方式**（铁律：先定位再改）：原脚本是「逐文件增量」，但 CH-026 新增了 4 个 config mixin、CH-023/024 含表结构与数据迁移 → 逐文件必漏。改为**整树同步**（backend + sql + dist 三个 tar）
- **定位部署阻断级风险**：新代码在**模块导入期**（`app.core.config` 的 `AppConfig.__init__` → `load()`）就会读全部表；生产库缺 4 张表 → 任一 repo 抛 `OperationalError` → `load()` 的 except 分支把 `_upstreams/_rules/_api_keys` **全部清空** → 网关全量 401。且 `main.py` 的 `startup()` 里 `config.load()` 与 `sync_unified_tables()` 同处一个 try，迁移失败会**跳过** `load()`
- **规避手段**：新增「预迁移」阶段——**重启前**先按 `sql/06 → increment/06 → 07 → 08` 顺序显式建表/迁移（顺序不可调换：06 建 `agg_model_group`/`agg_probe_config`，07 才引用它们）
- **红线确认**：全程**未执行 `seed.py`**（`drop_all()` 会清空生产数据）
- 部署 8 步，每步失败即中止，且中止点都在「已备份、未替换代码」之前 → 失败时生产仍跑旧版本：备份（sqlite3 **在线备份 API**，WAL 下安全）→ 传 sql → 预迁移 → 传 backend → 替换 dist → 清 pycache + chown → `compileall` 预检 → 重启 + 验证
- 结果：4 个迁移脚本全 `APPLIED ok`（8/3/7/2 条），表 10 → 14 张，`agg_unified` 3 行（由 `agg_aggregated_name` 迁移），`rule_bindings` 与 `log_usage.upstream_model` 列已补
- 验证：启动日志 `配置已加载: 1 上游源, 3 规则, 4 密钥, 0 别名, 3 聚合`（配置完整，非空）；`文件日志已启用`（CH-025）、`已自动生成 JWT 密钥`（CH-032）、`v5.2.0 启动`；10 个管理端点全 200；入口冒烟 `/` 200、`/health` 200、登录 200、无 Key 401（全程无 500）
- 备份：`/opt/smart-router/backup/20261018-210217`（DB 960K + 代码/前端 504K）
- 关键判断：**老库升级时，「表结构不完整」比「代码写错」更隐蔽** —— 代码错会报错，表缺失走的是 `except OperationalError → 置空` 的静默降级路径，表现为「服务启动正常但业务全废」。因此升级顺序必须是**先补结构、再上代码**
- 教训：`--dry-run` 与只读勘察都要先跑；若直接照搬历史脚本，会因 python 路径错误与属主问题踩坑

### 2026-10-18 - CH-032 JWT 签名密钥动态化
- 背景：CH-031 推送 GitHub 时发现 `security.py` 硬编码 `JWT_SECRET`，用户明确「这种肯定不行」，要求先改完再谈部署
- 先写变更文档再改代码（铁律 7：B 线必须先文档）：`docs/_changes/CH-032-JWT密钥动态化.md`
- 现状排查（铁律 2：先定位）：全仓 `JWT_SECRET` 只有 4 处——`security.py` 定义 + 2 处使用 + `main.py:25` 的死导入（导入后从未使用）
- 方案定级：`SR_JWT_SECRET` 环境变量 > `sys_setting.jwt_secret` > 首次启动 `secrets.token_urlsafe(48)` 自动生成并落库；**没有引入 python-dotenv**（项目无 .env 机制，为一行环境变量引依赖属过度设计）
- 实现：`security.py` 新增 `get_jwt_secret()`（进程内缓存 + `threading.Lock`，防并发首次调用生成两个密钥）+ `reset_cache()`（测试模拟重启）+ 数据库不可用时降级为进程内随机密钥并 WARNING（服务不崩）；`main.py` 删死导入，startup 在配置加载后预热密钥
- 验证（7 项单元 + 端到端）：自动生成落库长度 64 / 签发校验 / 模拟重启密钥不变且旧 token 有效 / **用旧硬编码密钥伪造的 token 返回 None** / 环境变量优先且旧 token 立即失效 / 数据库不可用降级 / 真实 uvicorn 重启后旧 token 仍 200
- 回归：`verify_api_ch023` / `verify_rule_binding_ch024` / `verify_aggregation_ch023` / `verify_migration_ch023` 全通过；`compileall` 退出码 0
- 文档同步：README 补环境变量表（含轮换说明）+ 需求规格移除 9.2 待完善项 + 架构设计 security.py 职责 + 数据库设计 3.9 新增 `jwt_secret` 键 + 变更记录 + STATE
- 临时验证脚本用后即删（`test/_tmp_*_ch032.py`），不留在仓库
- 关键判断：**「重启不踢人」是这次设计的核心约束**——如果每次重启随机生成新密钥，用户会频繁被登出，体验极差；落库持久化解决了这个矛盾
- 未做：未 push、未部署

### 2026-10-18 - CH-031 仓库迁移 GitHub + Git 历史隐私清洗
- 背景：用户推送前要求先做隐私审查。审查发现 git 历史里 `test/verify_prod_ch016.py` 在 CH-016 提交（`e2df186`）硬编码管理员密码与客户端 Key，CH-018（`521ac20`）虽已改环境变量但历史仍可翻阅；`.git/config` 的 remote URL 内嵌明文 Gitee 账号密码
- 用户决策：①迁 GitHub、Gitee 仓库转私有；②推前先清干净；③不轮换凭据（局域网部署，外部不可达）
- 备份（铁律：破坏性操作先备份）：工作区文件副本 `E:\80-project_dev\04_smart-router-backup-20261018`（1.8 MB，排除 node_modules/.venv/dist/logs/__pycache__/*.db）+ `git bundle` 全 refs `E:\80-project_dev\04_smart-router-20261018.bundle`（0.9 MB）；两者都在项目目录外，**不会被误推**
- 工具：`uv tool install git-filter-repo` → v2.47.0（venv 内无 pip，改用 uv tool）
- 清洗：规则文件写在 `.git/replace-rules.txt`（不受 git 跟踪，避免自己泄露），`git filter-repo --replace-text` 把真实密码/Key 替换为 `CHANGE-ME-ADMIN-PASSWORD` / `sk-CHANGE-ME-CLIENT-KEY`；27 个提交 0.41s 重写完成；`origin` 按设计被移除
- 验证：4 个敏感值（管理员密码 / 客户端 Key / Gitee 账号 / Gitee 密码）全历史 `git grep --fixed-strings` 扫描 **0 命中**；清洗前后 HEAD 树对象完全一致（`3957e9f3…`）→ 内容零变化；提交数 27 不变、`v5.1.0` 标签保留；`git status` 干净（294 文件）
- 收尾：临时规则文件已删除；`.git/config` 只剩 core/user/branch，无任何 URL 与密码；失效的 `backup-before-clean` 分支删除（旧 hash 已随重写消失）
- 第二轮：提交作者邮箱是「手机号@qq.com」，用 `--mailmap` 全量改为 `wangjianzhou <66wjz@users.noreply.github.com>`；又因为变更文档里自己写了手机号，追加一次 `--replace-text` 扫尾（**教训：写脱敏记录时不能把真值再抄一遍**）
- 远端：`git remote add origin https://github.com/66wjz/smart_router.git`（URL 无凭据），`git push -u origin main` 成功；本地 `user.email` 也改为 noreply（仓库级，未动全局）
- 推送后复扫：4 个敏感值 + 提交元数据全部 0 命中；提交 31、跟踪文件 295、`v5.1.0` 标签保留
- 推送时新发现：`backend/app/core/security.py:13` 的 `JWT_SECRET` 硬编码，任何人拿到源码可伪造管理台 token → 登记到 `docs/需求规格.md` 9.2，列入后续 B 线-小（用户明确「这种肯定不行，后面要改」）
- 关键判断：**历史清洗必须在 push 之前做**——一旦旧历史推到远端，force push 也难保干净（平台缓存 / 他人克隆 / fork）。本次恰好从未成功推送过含凭据的提交，成本最低
- 未做：未部署（部署需用户另行授权）

### 2026-10-18 - CH-030 清理 v4 遗留 + 登记待办 + 补文档
- 背景：CH-029 收尾列了 4 项遗留，用户逐项决策（部署脚本待部署时重写 / v4 代码删掉 / `auto_same_name` 登记待办 / 补 `smart-retry` 文档）
- 删前依赖排查（铁律 2）：`backend/app/**` 与 `test/` 对根目录 `core`/`upstream`/`admin` 的 import 实测 0 处；`start.bat` 已在 CH-029 改指 `backend/run.py`；`config.example.yaml` 仅被 README 索引引用
- 删除：11 个 git 跟踪文件（`router.py` / `core/` 6 py / `upstream/` 3 py / `admin/` 3 py / `.streamlit/config.toml` / `config.example.yaml`）+ 1 个未跟踪 `test_router.py`；**保留本地 `config.yaml`**（含真实配置、已 gitignore）
- 删后验证：根目录 7 项全部不存在；空库 `seed.py` + `uvicorn` 启动成功；`npm run build` + `compileall` 通过；三套回归全通过；残留 grep 仅剩注释与 v5 自身 `app/api/v1/router.py` 路径
- 待办登记：`docs/需求规格.md` 新增第九节「待完善事项」，9.1 详列 `auto_same_name` 的现状/实际行为/原承诺/影响/后续做法（避免以后误当已实现）
- 文档补齐：`API契约.md` 4.18.1 `smart-retry`（字段表 + 默认值 + 开关语义 + 存储键 + 错误码）、`接口文档.md` 同步、API 总表补行；实测接口返回与文档一致
- 关键判断：**删除 git 跟踪文件是安全可回退操作**（`git revert` 可完整恢复），但**未跟踪的本地 `config.yaml` 不能删**——它可能就是用户唯一的真实配置备份

### 2026-10-18 - CH-025 取证（问题 3 日志排查）
- 背景：用户报「WebSocket error: Network IO error: error sending request for url (http://10.10.0.2:10002/v1/chat/completions) (HTTP Status: 500)」，要求先分析
- 连接生产 10.10.0.2 取 journal 日志（paramiko/py3.12，SSH root）：journald 持久化（`/var/log/journal` 存在、Storage=auto），覆盖 9/21 至今；服务今早 09:57 重启，boot -1 日志完整保留 → **重启未冲掉日志**
- 全量状态码统计：500 仅集中在 10-16（19:48~19:54 共 34 个 = CH-019 部署事故的 `TypeError: ModelHealth.record_success()`，FB-022 已修；20:03:48/49/51 共 3 个 = `json.decoder.JSONDecodeError`）。10-15/10-17 的 502/503 是上游不可用后的正常容错返回
- 拿到 JSONDecodeError 完整堆栈，直指 `app/api/v1/chat.py:23  body = await request.json()`；对照三入站：messages.py / responses.py 都包了 try 返回规范 400，**仅 chat.py 裸调用** → 非 JSON body 必成裸 500（无错误体，客户端只能报 Network IO error）
- 今日（10-18）复查：311×200 + 31×304，**0 个 500 / 0 个 Traceback / 0 个 WARNING**；服务 NRestarts=0；上游 8326 = `node dsh web`（即 dsh 自身）
- 结论：日志本身够用（能定位到行），但**缺请求上下文**（无 body / headers / 协议），无法得知客户端发了什么才触发 → 需补结构化请求日志；`chat.py` 裸 500 为已证实缺陷
- 产出：CH-025 = A（新建聚合保存按钮卡「保存中」）+ B（复制 Key 去确认弹窗）+ C1（chat.py 补 try）+ C2（全局异常兜底）+ C3（请求上下文日志落文件）

### 2026-10-16 - CH-019 部署事故修复（FB-022，A 线）+ CH-019 收口待办登记
- 背景：另一 AI 会话承接 CH-019（B 线-大），在未完成实施验证的情况下执行了增量部署（test/deploy_ch019_incremental.py）至 Ubuntu 生产，上线即 /v1/chat 全 500
- 三处部署缺口定位（journalctl traceback + ss + unit 对读）：①上传清单漏 app/upstream/ 三个适配器 → 新 ModelHealth.record_success(upstream_id, model) 签名 vs 旧调用 record_success(model) → 每请求必炸；②迁移步骤写死阿里云旧机 /root/miniconda3/bin/python（Ubuntu 无）→ SQL 06 静默未执行；③前端传至 frontend_dist/ 而 systemd FRONTEND_DIST 指向 frontend/dist 且未 daemon-reload → 生产一直跑旧前端
- 修复（先备份 /opt/smart-router/backup_app_20261016_195621 + DB 再动手）：本地↔远程 58 个 .py 逐文件 md5 比对精确补传 3 适配器；venv python 绝对路径补跑 SQL 06（幂等通过）；unit 改指 frontend_dist + daemon-reload + 重启
- 顺手修新代码 bug（铁律 2 定位→铁律 3 单点改）：repositories/usage_repo.py insert_many `with self._lock_cursor_batch(...)` 把 int 当上下文管理器每批必抛 TypeError 假错（数据实际已落库）→ 改 1 行直接 return；本地同步修改（先本地后上传）
- 运行参数热调整：PUT /admin/api/config/retry → response_timeout 20→60、first_chunk_timeout 8→30（dsh 网关 aggregate/* 聚合入口实测 20~40s，原超时一碰即 503；CH-019 决策点 4 的落地，值按实测取）
- 验证：chat 非流式×3、流式、/v1/messages（anthropic）、/admin/api/usage/summary、新 dist 前端页面全通；log_usage 正常落库（success 与 error 均记）
- 遗留待办（CH-019 收尾，用户实测确认后执行）：文档同步（数据库设计 log_usage / API契约+接口文档 4 个 usage 端点与 PATCH/PUT models / 功能清单 / README / 五列矩阵）→ 变更文档归档 → 版本号决策（启动日志已显示 v5.2.0，建议收尾统一）→ git commit（本地 18 改+11 新增未提交）；test/deploy_ch019_incremental.py 内 miniconda 旧路径未修，复用前必改

### 2026-08-12 - FB-021 项目补齐 V5.2 流程缺口（B 线-小，已归档）
- 按 skill V5.2 新规则对项目做缺口盘点：无脱敏配置模板、.gitignore 未覆盖密钥/日志/缓存、_changes/README 缺长期台账
- 补齐：新增 config.example.yaml（脱敏模板，真实 config.yaml 不入库）；.gitignore 对照 skill templates/gitignore.md 增强；_changes/README 补长期台账区
- 同步：README（文档索引加 config.example.yaml）、变更记录、feedback-log（FB-021）、STATE.md（维护迭代记录）
- 验证：config.example.yaml 无真实凭据；git 跟踪文件敏感扫描全绿；无功能/接口/行为变化；变更文档归档至 _changes/archived/
- 状态：已同步+已归档；待 commit/push

### 2026-08-12 - FB-020 归档（CH-018）+ 文档同步闭环
- 用户实测确认通过 → 归档：变更文档 CH-018 移入 docs/_changes/archived/；_changes/README 登记同步去向
- 同步回原始文档（6 份）：API契约（1.4 错误格式表 + 2.2 messages + 新增 2.3 Responses + 变更记录）、接口文档（通用错误约定 + 入站协议矩阵 + 变更记录）、面向客户的功能清单（D018c 新增）、五列对应矩阵（CH-018 行 + 变更记录）、README（三协议入站能力对齐段）、docs/变更记录.md（2026-08-12 CH-018 段）
- feedback-log FB-020 状态更新为已归档；STATE.md 维护迭代记录追加

### 2026-08-12 - FB-020 二期：三协议错误格式统一 + 推理模型 reasoning 映射（已部署生产验证）
- 用户实测发现：deepseek 不支持图时 messages/responses 表现为"超时无反馈"（实为错误格式客户端解析不了）；mimo-v2.5（推理模型）在 messages/responses 有空内容/无结果
- 二期修复（5 文件）：chat.py/messages.py/responses.py 三入站错误统一为各协议标准格式（openai/anthropic/responses）；anthropic_adapter 非流式 reasoning→thinking 块 + 流式 thinking_delta；responses_adapter 非流式 reasoning item + 流式 reasoning_summary_text.delta
- 关键发现：opencode go 上游流式推理字段是 `delta.reasoning`（非 deepseek 官方 `reasoning_content`），抓上游原始 SSE 确认后兼容两个字段名
- 验证：本地 16 用例全过（含真实字段格式）+ 生产 11 项全过（三协议错误格式 / mimo 非流式与流式 thinking / responses reasoning）；部署 deploy_fb020_r2.py
- 状态：待用户实测确认后归档

### 2026-08-12 - FB-020 一期：入站丢图片修复（A 线 bug）：anthropic/responses 入站补图片块映射
- 用户反馈：Chatbox Claude 兼容模式发图 AI 回复但看不到图；Responses 模式发图空回复；OpenAI 兼容正常（报"所有模型均不可用"= 图片真实透传后被不支持图片的模型拒绝）
- 根因定位：CH-009 入站 `_anthropic_content_to_openai` 只处理 text/tool_use/tool_result，漏 image 块；CH-010 入站 `convert_request_responses_to_openai` 只处理 input_text/output_text/text，漏 input_image 块
- 修复（2 文件）：anthropic_adapter 新增 `_anthropic_image_block_to_openai`（base64→data URI / url 直传）；responses_adapter message 分支补 input_image→image_url；content 纯文本保持 str 不回归、混合时转块列表
- 验证：compileall + 5 用例全过（anthropic 混合/纯文本/仅图片 + responses 混合/纯文本/仅图片 + 闭环 image 无损）
- 状态：待部署云服务器 + 用户实测

### 2026-08-11 - v5.1.0 版本收口：文档对齐 + 版本号 + tag
- 文档缺口盘点（marker 扫描）：数据库设计补 up_upstream.groups 列 + format 三协议 + 3.8 交集语义；API契约/接口文档补 upstream.groups 字段与 responses 协议；系统核心流程表速览补 groups；功能清单补 1.3.2 智能重试/1.5.2 多分组/2.2.1 仪表盘双视角；README 修订（版本头/双定位/多分组/三协议接入示例/FRONTEND_DIST 本地托管说明/八表/智能路由折叠菜单；修正"当前唯一入站协议"过期表述）
- 版本号：FastAPI version=5.1.0、启动日志、Login/顶栏 v5.1
- 部署：deploy_v510_release.py（main.py+run.py+dist）；生产 openapi.json 验证 version=5.1.0
- git tag v5.1.0 随提交推送

### 2026-08-11 - FB-019 智能路由改可折叠一级菜单（CH-017 交互迭代）
- 用户反馈：分组标题不符合预期，要"一级菜单点击展开二级"
- 实施：BaseSidebar 新增 collapsible 分组（network 图标 + chevron 旋转 + 二级项缩进，默认展开）；AdminLayout 智能路由组启用
- 验证：本地实机截图（展开态/点击收起态均正确）→ dist 部署 → 生产截图复核通过
- 顺带确认：用户已自行用 CH-016 多分组能力（opencode go 源配双分组 premium+opencode go，新建分组生效）

### 2026-08-11 - CH-017 侧边栏分组 + 仪表盘重设计：实施+视觉验证+部署+归档
- 用户确认修订版方案（只加"智能路由"分组）+ 设计稿（提出卡片不等高问题）
- 实施：AdminLayout 三组结构（复用 BaseSidebar 多分组）；Dashboard 按设计稿重写（双职能指标卡/源状态表/路由概览/等高 fill-card）；Latency 探测范围说明
- 视觉验证（Chrome DevTools MCP 实机截图）：本地首轮发现第二行不等高——:deep(.base-section) 未命中（类在根元素上），改 fill-card 直接作用根元素后两行等高；生产截图复核通过（数据与真实配置一致）
- 归档 CH-017；活跃变更清零

### 2026-08-11 - CH-016 上游源多分组：实施+验证+部署+归档
- 实施：增量 SQL 05（groups 列+存量回填）；repo/config 解析；5 处权限判断改集合交集（isdisjoint）；schema/前端多选
- 验证：本地 4 用例全过（双分组命中/可见性/收紧 403/存量无回归）；生产临时给 opencode go 加 free 组实测 free Key 直调 mimo-v2.5 → 200，还原后 403
- 插曲：Upstreams.vue 部分编辑疑似被外部编辑器缓冲区覆盖回退（tsc 抓出补改）；验证脚本 URL 空格未编码（工具问题）
- CH-017 修订版方案 + 仪表盘设计稿（docs/designs/CH-017-仪表盘设计稿.html）待用户确认

### 2026-08-11 - 推送后隐私复查 → 发现泄露 → 重写历史修复
- 用户确认"没有隐私数据上传吧"→ 全库扫描发现 **sql/02_init_data.sql 含真实上游 Key（newapi sk-vJgy… / xiaomi tp-cujb…）+ 三个生产路由层 Key**，首轮脱敏只覆盖了 test/ 脚本，漏了种子 SQL 和文档示例
- 修复：种子 SQL 全部改占位符（sk-CHANGE-ME-*）；API契约/数据库设计示例 Key 改 sk-your-key；verify_edit_flows.py 改环境变量
- 历史处理：git commit --amend 重写首提交 + force push（fd0722f → ddf33c8），HEAD 复扫 8 类敏感串全部干净，远端已校验
- 教训（经验沉淀）：脱敏范围必须覆盖 sql/种子文件/文档示例，不只脚本；今后推送前固定跑敏感串扫描清单
- 残留说明：seed 中默认管理密码 smart-router-2026 为公开默认值（生产已改密），属可接受
- 已建议用户：公开窗口约 5 分钟，如需绝对安全可在 opencode/小米/管理后台轮换相关 Key，或将仓库设为私有

### 2026-08-11 - 纳入 git 管控（gitee）
- 用户建仓库 https://gitee.com/wang-jianzhou-66/smart_router，要求推送管理
- 安全前置：test/ 24 个脚本硬编码服务器 root 密码 + 生产 Key → 一次性脱敏脚本批量改环境变量（SR_SSH_PASS/SR_FREE_KEY/SR_PREMIUM_KEY/SR_COZE_KEY），脱敏脚本自身含模式串已删除；config.yaml（v4 真实 Key）、smart_router.db、test_router.py（v4 真实 Key）入 .gitignore
- git init（main）+ 首提交 fd0722f（206 文件）+ push 成功（ls-remote 校验一致）
- 注意：远程 URL 含账密存于本地 .git/config（不入库）；后续改代码 → commit → push 即可

### 2026-08-11 - FB-014/015/016 三连修 + CH-015 归档
- FB-014（复制失效）：根因 navigator.clipboard 需安全上下文，生产纯 HTTP 静默失败；新增 utils/clipboard.ts（execCommand 降级）替换 ApiKeys.vue 6 处调用
- FB-015（/v1/models 全量目录）：根因生产+本地 models.py 均为旧版实时代理拉取（与既往记录不符，无 git 不可追溯，已留痕）；重写为只回已配置模型（分组+启用过滤，不代理拉取）
- FB-016 → CH-015（透传 503）：根因 find_model_upstream 只查规则候选；补第二层"上游已配置模型"查找（B 线-小变更文档已建并归档）
- 验证：本地（403 分组拦截/200 命中 X-Served-By/models 只含配置项）+ 生产真实上游（models 13 个无垃圾模型/mimo-v2.5 200/kimi-for-coding 200/free 越权 403）
- 部署：test/deploy_ch015_incremental.py（config.py + models.py + dist）
- 待用户浏览器复验：复制按钮（HTTP 降级逻辑无法无头验证）

### 2026-08-11 - 生产真实链路验证（test/verify_prod_matrix.py，无 mock）
- 结果 4/4 通过 + 1 跳过：
  - openai 入站→openai 出站（newapi minimax-m3 直连）：200，X-Served-By=newapi/...，content="好" ✅
  - anthropic 入站（x-api-key）→openai 出站：200，anthropic 外壳（type=message/stop_reason=end_turn）✅
  - responses 入站（Codex 风格 instructions+input）→openai 出站：200，object=response/status=completed ✅
  - responses 入站流式：response.created/output_text.delta/response.completed 事件全在 ✅
  - anthropic→anthropic 双转换链（opencode minimax-m2.7）：跳过——生产管理员密码已被用户修改（非默认），无法创建临时别名；该组合为两条已验证链路的复合，用户可在管理端点 minimax-m2.7「测试」补验
- 注：脚本汇总计数用了 `is True` 严格判断导致显示 1/4，各用例实际均 PASS（真值判定），仅为脚本显示瑕疵

### 2026-08-11 - CH-009/CH-010 入站双协议：实施+验证+部署+归档（V1 收官）
- CH-009：anthropic_adapter 加入站逆转换三件套（请求/响应/SSE 状态机 OpenaiToAnthropicSSE）；新增 api/v1/messages.py；main.py 中间件兼容 x-api-key；本地 4 用例全过（x-api-key 鉴权+非流式双向转换/401/流式六事件/分组 403）；deploy_ch009_incremental 部署（生产 /v1/messages 401≠404 注册成功）
- CH-010：responses_adapter 加逆转换三件套（OpenaiToResponsesSSE）；新增 api/v1/responses.py；本地 4 用例全过（Codex 风格 instructions+input 字符串/input 数组/流式五事件/401）；deploy_ch010_incremental 部署（双入站路由均 401）
- 插曲：CH-009 插入转换器时残留孤儿 return（编译期发现即修）；CH-009 流式首测输出空——定位为 mock 不支持 stream 非功能问题，补 mock 后通过
- 收官：两份变更文档补实施记录并归档 archived/；README/需求规格/功能清单/系统核心流程/五列矩阵的协议矩阵全部翻转为已实现；PLAN P1/P2 已上线；STATE/feedback-log/变更记录收口
- **CH-001~014 全部归档，3×3 协议矩阵收齐，第一版（V1）完成**

### 2026-08-10 - 文档同步闭环（用户确认补齐）
- 背景：用户质询"README 没跟着更新？设计文档随规范更新了吗"——核实 skill 原文（铁律7 自检/6.7 强制/反模式表）确认 README 必须更新；审计发现需求规格/功能清单/五列矩阵 0 引用（未同步），架构设计/数据库设计部分同步
- 补齐：需求规格（协议矩阵修订+迭代需求第八节+端口闭环）、功能清单（1.4.1 修订+三章节+D021~026）、五列矩阵（补 9 行+一致性回溯+入站一致性检查项）、架构设计（第十一节演进：三适配器/Key 池/_RetryLoop/分组/部署形态）、系统核心流程（接口清单+表速览）、数据库设计（3.8/3.9+列说明+增量 SQL 表）
- 纠错：同步过程中发现 README 文档索引含死链（测试手册/部署手册 v5 未建）已修；grp_group 表系我误写——实际分组存 sys_setting.groups，三处文档已按代码事实修正
- 变更记录.md 补"攒批收尾：文档同步闭环"条目

### 2026-08-10 - 攒批统一收尾归档（用户确认整体初步完成）
- README 对齐：发现主 README 还是 v4 残留（Streamlit/config.yaml/未实施的入站端点），已全文重写为 v5 现状（FastAPI+Vue3+SQLite、Key 池/分组/智能重试/协议矩阵/部署现状/文档索引）
- 归档：CH-001~008、CH-011~014 共 12 份变更文档移入 docs/_changes/archived/；_changes/README 重构为"进行中（CH-009/010）+ 已归档"两表
- 收口：STATE.md 维护记录合并归档行 + 阶段变更记录；PLAN P0/P3 标已上线；feedback-log 维持台账
- 文档同步确认：API契约/接口文档（分组接口、models 对象条目、responses 协议、smart-retry 配置、X-Served-By 头）、数据库设计（增量 SQL 04）、变更记录均已在此前各变更实施时同步
- 剩余活跃：CH-009（anthropic 入站）、CH-010（responses 入站）设计就绪待用户发令

### 2026-08-10 - 生产诊断：gpt-5.6-luna 403 + 测试延迟 3s+（无代码改动）
- 方法：`test/diagnose_opencode.py` 从生产服务器本机直连 opencode（绕过中转），原始响应 + curl 分层计时
- 结论1（403）：直连同样返回 `403 This model is not available in your region`（Console Go 区域限制，按服务器出口 IP 判定）——与中转代码无关，我们的适配器如实透传
- 结论2（延迟）：直连计时 DNS 0.003s / TCP 0.21s / TLS 0.44s / 首字节 0.44s / 总 2.65~3.11s——网络 0.45s + opencode 自身生成 2.2~2.6s（免费档+推理模型+海外线路）；中转层开销可忽略，管理端测试 3s+ 是上游真实速度
- 观察项（未改）：区域类 403 会进 Key 池轮换计数（换 Key 无意义但无害），如需优化再立项

### 2026-08-10 - CH-014 responses 出站适配器：实施+验证+部署
- 实施：新增 responses_adapter.py（请求/响应/SSE 转换 + 3 个转发函数，复用 _RetryLoop/Key 池）；router_service + admin test 分发；协议白名单 + 前端下拉加 responses
- 验证：本地 mock /v1/responses 5 用例全过（非流式双向转换、流式 SSE 转换、智能重试联动 X-Retry-Count=1、管理端测试分发、400 不重试）
- 插曲：首轮测试 PowerShell 剥引号致请求体非法 JSON（500 在解析层），第二轮 Invoke-WebRequest NRE——均为测试工具问题，改 curl -d @文件后全过
- 部署：`test/deploy_ch014_incremental.py`（5 后端文件 + dist，无 DB 变更），active/200/生产探测正常
- 待办：用户生产实测 gpt-5.6-luna（标 responses 协议）；CH-009 anthropic 入站待开工

### 2026-08-10 - 协议矩阵三份设计文档建档（CH-014/009/010）
- 背景：用户确认目标为完整 3×3 协议矩阵（入站识别 anthropic/responses + 出站连接三种上游）；动机——Codex 等客户端发 responses 格式
- 分析：opencode go 19 模型清单中 17 个已被 CH-011 覆盖，仅 gpt-5.6-luna 需 responses 出站；google 私有映射正式排除（清单中不存在）
- 产出：CH-014（responses 出站，实施中）、CH-009（anthropic 入站，含中间件 x-api-key 兼容设计）、CH-010（responses 入站）三份变更文档；PLAN P1/P2/P3 状态更新；_changes/README 登记
- 架构决策：内部中间语言 = openai chat 格式不变；入站转换发生在 RouterService 之前，出站转换在适配器内；CH-009/010 转换器为已有出站转换器的逆运算
- 实施顺序：CH-014 → CH-009 → CH-010

### 2026-08-10 - 修复：模型协议下拉默认态显示占位符（FB-012 A 线小）
- 定位：用户截图显示默认态为"请选择"而非"继承（源协议）"；根因——el-select 将空串 '' 视为空值显示 placeholder，即使存在 value="" 的选项也不选中
- 修复：'inherit' 哨兵值替代空串（显示继承项），setModelProtocol 保存时映射回无 protocol；下拉加宽 150→160px
- 验证：vue-tsc + 构建 ✅；`test/deploy_dist_only.py` 纯前端推送（40 文件，GET / 200）
- 用户同问"只有 openai/anthropic 两种协议"：核实为 CH-011 第一期设计内范围（非目标明确 responses/google 留第二期），非遗漏；CH-014（responses 出站）待用户排期

### 2026-08-10 - 热修：添加上游源 500（FB-010 A 线）+ 接入说明按钮右移（FB-011 B 线-小）
- 定位：生产 journalctl 拿到堆栈 `sqlite3.IntegrityError: NOT NULL constraint failed: up_upstream.api_key`；根因——pydantic model_dump 显式携带 api_key=None，`data.get("api_key", "")` 的默认值仅在键缺失时生效，显式 None 穿透 → INSERT NULL 违例（前端添加只发 api_keys 数组）
- 复现：本地 POST 仅 api_keys → HTTP 500 复现成功
- 修复：repo create 改 `data.get("api_key") or ""`（单点最小改动）；验证：添加成功 + Key 池加载 2 Key + 清理
- UI：ApiKeys 接入说明弹窗「复制示例」移到标题行右侧
- 部署：`test/deploy_hotfix_add_upstream.py`（repo 文件 + dist），COMPILE_OK/active/200
- 待办：用户重新体验添加 opencode 源 + 模型测试；攒批收尾归档不变

### 2026-08-10 - CH-012 智能重试 + CH-013 接入体验：实施+验证+部署
- 操作：用户确认方案（智能重试默认关）后按 B 线流程建 CH-012/CH-013 变更文档 → 实施 → 验证 → 部署
- CH-012：up_upstream 加 smart_retry 列（本地+生产幂等执行）；适配器 `_RetryLoop` 预算制（Key 数+extra_attempts，同 Key 退避 ±jitter，开关内 5xx 可重试）；成功响应 X-Served-By/X-Retry-Count；GET/PUT /admin/api/config/smart-retry；前端开关+徽标+Settings 全局参数
- CH-013：Upstreams URL 实时拼接预览 + "格式"改"默认协议"；ApiKeys 接入说明弹窗（地址/Key/按分组可用模型/curl+SDK 示例）
- 验证：本地 mock 可编程上游 5 用例全过（关→不重试；开→500 退避成功带响应头；超预算 503 恰好 3 次；400 不重试；500×2 第 3 次成功）；compileall/vue-tsc/构建 ✅
- 部署：`test/deploy_ch012_incremental.py`（7 后端文件 + dist + 生产加列），active/200/生产探测流量正常
- 插曲：测试脚本误用 /admin/api/pointers（实际为 /model-pointers）导致首轮用例全 FAIL——按铁律 2 定位后修正重跑通过
- 待办：用户生产体验（opencode 源开智能重试观察掉线率）→ 攒批统一收尾归档 CH-003~008/011/012/013

### 2026-08-10 - CH-011 部署生产（增量）
- 操作：用户确认推送，执行 `test/deploy_ch011_incremental.py`（增量脚本，不触碰生产 DB）
- 内容：5 个后端变更文件 + 前端 dist 整体替换（40 文件）→ 服务器侧 py_compile 预检 → systemctl restart
- 验证：服务 active ✅、10002 监听 ✅、GET / 200 ✅、启动日志正常 ✅
- 注意：admin 默认密码在生产登录 401（生产密码已被改过），管理接口验证留给用户实际体验
- 待办：用户生产体验（分组管理 + 模型协议下拉 + opencode 实接）→ 统一收尾归档 CH-003~008/011

### 2026-08-10 - CH-011 实施完成：模型级协议覆盖（迷你 stage-3/4/5）
- 操作：用户确认设计后实施，一次完成后端 5 文件 + 前端 2 文件改动
- 后端：repo `_parse_models`/`_dump_models` 双向归一化（string→object，脏数据丢弃）；config 新增 `get_model_protocol`；router_service `_forward` + admin test 按模型级协议分发；schemas 新增 ModelEntry（protocol 白名单校验 422）；models 删除按 .name
- 前端：ModelEntry 类型；Upstreams.vue 模型行协议下拉（继承/openai/anthropic 即改即存）；全链路按 .name
- 验证：后端 compileall ✅、vue-tsc ✅、构建 ✅；单元级归一化+四分支解析 ✅；接口冒烟 5 项（创建/回读持久化/非法 422/PUT+DELETE/清理）✅
- 待办：opencode 实接验证（需真实 Key，部署后用户验证）；与 CH-003~008 攒批统一推送生产 + 统一收尾归档

### 2026-08-10 - CH-011 变更文档创建：模型级协议覆盖（方案 B 拍板）
- 操作：用户拍板方案 B（模型级协议覆盖），按 B 线流程先建变更文档，未动代码
- 产出：`docs/_changes/CH-011-模型级协议覆盖.md`（设计待确认）；_changes/README 登记；PLAN 新增 P3（出站方向，区别于 P1/P2 入站）
- 设计要点：up_upstream.models 元素 string→object（{name, protocol?}），repo 归一化兼容存量；分发 2 处改按模型级协议；第一期仅 openai/anthropic 出站；探测不改
- 待办：用户确认 CH-011 设计 → 迷你 stage-3/4 实施 → 本地验证 → 攒批统一收尾推送生产

### 2026-08-10 - 收尾策略确认：CH-003~008 攒批统一收尾
- 操作：用户确认——所有待确认变更（CH-003~008）不再逐个单独收尾，攒在一起等用户最终确认后统一归档 + 统一推送服务器
- 影响：STATE.md 维护迭代记录、_changes/archived/ 归档、_changes/README 登记、feedback-log 状态更新均延后到用户统一确认时一次完成
- 代码现状核查：CH-008 后端（groups.py/config.py/models.py）+ 前端（Settings/Upstreams/ApiKeys）均完整，后端编译通过，前端 dist 已构建
- 新议题：用户提出"一源多协议端点"建模问题（opencode 类上游，同站不同模型走不同协议/路径），分析见对话，方案待用户拍板后建 CH 文档

### 2026-08-09 - 规划固化：分组管理 + 多协议统一输出
- 操作：用户确认方案，固化规划文档并纳入流程管控（B 线-规划）
- 产出：`.devflow/PLAN-多协议与分组管理.md`（P0 分组管理 / P1 Anthropic 兼容 / P2 Responses 兼容 分期）
- 核查：分组隔离核心逻辑已实现（中间件 key_groups + _check_group/allowed_groups），CH-008 聚焦管理补强
- 流程：STATE.md 更新（v5 六阶段 done + 维护迭代登记）、CH-008 变更文档创建、_changes/README 待登记
- 待办：CH-008（分组管理）实施 → 部署 → 文档同步；P1/P2 待用户排期

### 2026-08-09 - 维护迭代：模型删除修复 + 批量操作（CH-007）
- 操作：实施并部署删除修复与批量操作（B 线-小）
- 排查：单删失败根因——NVIDIA 模型名含 `/`（01-ai/yi-large），路径参数 {model_name} 无法匹配斜杠 → 404
- 修复：删除接口改 query 参数 `DELETE /upstreams/{id}/models?model=xxx`（前后端同步）
- 新增：模型行多选 checkbox + 批量操作条（全选/已选 n/批量删除/批量测试）；批量删除走 PUT models 覆盖，批量测试复用全量测试逻辑
- 验证：本地含斜杠模型删除成功；生产临时模型增删成功且用户数据完好；vue-tsc 通过
- 部署：服务器 8.137.195.192:10002（代码 + 前端 dist + 重启）
- 文档：CH-007 + 变更记录/API契约/接口文档 + _changes/README 登记
- 待办：用户实际体验确认后归档 CH-003~007；STATE.md 阶段推进待用户确认

### 2026-08-09 - 维护迭代：模型测试修复 + 折叠 + 全量测试（CH-006）
- 操作：实施并部署测试链路修复与交互优化（B 线-小）
- 排查：生产日志定位测试全失败根因——newapi base_url 被配成完整 URL（/v1/chat/completions），适配器重复拼接 → 全部 404
- 修复：openai/anthropic 适配器新增 _build_endpoint URL 容错 + test_non_stream 测试函数（错误具体透传 HTTP 状态码+响应体/超时/连接异常）；生产 base_url 修正为根地址
- 体验：模型列表 >5 个默认折叠可展开；新增「全量测试」按钮（串行 + 进度 + 汇总弹窗）；失败原因行内完整展示
- 验证：生产真实模型测试 200、不存在模型返回具体 HTTP 404 错误、模型拉取 100 个、vue-tsc 通过
- 部署：服务器 8.137.195.192:10002（变更文件 + 前端 dist + base_url 修正 + 重启）
- 文档：CH-006 + 变更记录/API契约/接口文档 + _changes/README 登记
- 待办：用户实际体验确认后归档 CH-003~006；STATE.md 阶段推进待用户确认

### 2026-08-09 - 维护迭代：上游源模型管理（CH-005）
- 操作：实施并部署上游模型管理（B 线-小），设计稿经用户 2 轮确认（拉取勾选加入 + 手动添加弹窗 + 单模型测试）
- 新增：up_upstream 加 models 列（JSON），PUT/DELETE /upstreams/{id}/models 接口，list 返回 models
- 重构：Upstreams.vue 模型区块（持久化列表 + 拉取面板搜索/全选/勾选 + 手动添加弹窗 + 行内单模型测试/删除）
- 验证：本地接口冒烟（写入→回读→单删）+ vue-tsc + 后端编译通过；生产登录/models 增删/页面 200
- 部署：服务器 8.137.195.192:10002（变更文件 + 前端 dist + DB 增量 + systemctl restart）
- 文档：CH-005 + 变更记录/接口文档/API契约 + _changes/README 登记
- 待办：用户实际体验确认后归档 CH-003/004/005；STATE.md 阶段推进待用户确认

### 2026-08-09 - 维护迭代：管理后台交互优化（CH-004）
- 操作：实施并部署 4 项交互改进（B 线-小）
- 新增：上游源模型在线测试接口 + 前端「测试选中模型」按钮
- 修复：BaseButton 加 type="button"，解决生成随机 Key 时误触发表单提交刷新页面
- 体验：API Key 弹窗打开自动生成随机 Key + 「重新生成」按钮；操作列按钮间距 8px
- 统一：--control-height 36→32px，Base 组件与 Element Plus 默认控件高度对齐
- 部署：服务器 8.137.195.192:10002（代码 + 前端构建 + 重启），生产验证测试接口返回 ok
- 文档：CH-004 变更文档 + API契约 4.7 + 接口文档 3.3 + 变更记录，登记 _changes/README，feedback-log 记录 FB-003~006
- 待办：用户实际体验确认后归档 CH-003/CH-004；STATE.md 阶段推进待用户确认

### 2026-08-09 - 维护迭代：上游源 Key 池（CH-003）
- 操作：实施并部署 Key 池方案（B 线-大）
- 新增：`core/key_pool.py`、`repositories/upstream_key_repo.py`、增量 SQL（up_upstream_key）
- 改造：openai/anthropic 适配器 4 个转发函数 + probe 走 Key 池；schema/API/前端多 Key
- 关键修复：非流式改 send(stream=True)+aread()+显式 aclose，解决超时取消脏连接阻塞后续 Key
- 配置：retry 超时 20→12s / 8→6s（本地 + 生产）
- 验证：本地 mock 端到端（401/超时换 Key + 冷却 + 轮询）+ 生产公网验证（登录/upstreams/模型/聊天 200）
- 部署：服务器 8.137.195.192:10002（DB 增量 + 代码 + 前端构建 + systemctl restart）
- 文档：CH-003 补充实施记录，同步回数据库设计/API契约/接口文档/架构设计，登记 _changes/README
- 待办：用户实际体验确认后归档 CH-003；STATE.md 阶段推进待用户确认

### 2026-08-09 - v5 重构：需求确认 + 设计产出
- 操作：v5 重构流程重启，stage-1 需求文档 + 功能清单产出并确认通过
- 操作：stage-2 设计产出（架构设计/数据库设计/API契约/五列矩阵/系统核心流程/建表SQL）
- 流程路径：full-route（重新从 stage-1 管控）
- 决策：前端 Streamlit → Vue3；配置 YAML → SQLite；后端分层重组；Responses/视觉管道暂不实现
- 待办：stage-2 设计待用户确认后进入 stage-3

### 2026-08-07 - 补建流程管控
- 操作：执行 bootstrap/init-structure.md（追溯补建）
- 流程路径：full-route
- 当前阶段：stage-6（追溯）
- 备注：项目历史上未经流程管控（无 .git、无过程文档），本次按现状补建 STATE.md、index/artifacts.md；历史阶段门禁无法追认
