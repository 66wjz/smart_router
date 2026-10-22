# Smart Router v5.2 - AI 模型智能路由代理 · 中转站

**当前版本：v5.2.4**（2026-10-22）· 仓库：https://github.com/66wjz/smart_router

基于 FastAPI + Vue3 + SQLite 的轻量级 AI 模型网关：既是**智能路由器**（按请求内容自动选模型），也是**中转站**（统一 Key/分组/协议，直连透传已配置模型）。提供 3×3 协议矩阵、延迟探测、故障转移、Key 池、多分组权限、智能重试等企业级能力。

## 架构概览

```
客户端 (Trae / Chatbox / 扣子 / codex CLI ...)
     │
     │  请求 + 路由层 API Key
     │  入站协议：openai / anthropic / responses 均可
     ▼
┌──────────────────────────────────────────┐
│       Smart Router (:10002)              │
│                                          │
│  1. API Key 白名单校验 + 分组注入          │
│  2. 分组过滤（Key 只访问其分组的上游源）    │
│  3. 识别聚合模型名 / 别名 / 直连模型       │
│  4. 内容感知路由（图片/工具/默认对话）      │
│  5. 上下文长度检查 + max_tokens 调整       │
│  6. 动态权重选模型（延迟平方衰减）          │
│  7. 模型级协议分发 → 出站适配器转换         │
│  8. Key 池轮询 + 智能重试（源级开关）       │
│  9. 失败自动换候选 / 换 Key / 退避重试      │
└──────────────┬───────────────────────────┘
               │  出站协议：openai / anthropic / responses（模型级可覆盖）
     ┌─────────┼──────────┐
     ▼         ▼          ▼
┌─────────┐ ┌────────┐ ┌────────────┐
│ NewAPI  │ │ 小米   │ │ opencode   │
│ (openai)│ │ (openai)│ │ (混合协议)  │
└─────────┘ └────────┘ └────────────┘
```

## 核心特性

| 特性 | 说明 |
|------|------|
| **智能路由** | 按请求内容（图片/工具/对话）匹配规则，动态权重（延迟平方衰减）选模型 |
| **多协议出站** | 上游模型级协议覆盖：openai / anthropic / responses，同站多协议源（如 opencode）一个源搞定 |
| **智能重试** | 源级开关（默认关）：5xx/超时/连接中断自动换 Key 或退避重试（指数退避 + jitter），客户端无感知 |
| **上游 Key 池** | 每个上游可配多个 Key 轮询分摊流量；单 Key 失败/限流自动换 Key + 冷却恢复 |
| **分组权限** | 可配置分组（free/premium/自定义）；API Key 与上游源均支持**多分组**，交集即放行；/v1/models 只返回 Key 有权访问的已配置模型 |
| **聚合独立分组** | 每个聚合有自己的「可用分组」，是独立权限门面：聚合配什么分组，就只有这些分组的 Key 能用它，**成员所属上游源的分组不参与判断**。典型用法是把某提供商所有模型放入「禁止单独使用」组，再建一个聚合开放给免费用户 |
| **请求级容错** | 候选转移 + Key 轮换 + 同渠道退避重试三层；流式首字节分界线（吐字前可重试，吐字后不重复） |
| **延迟探测** | 定期探测候选模型延迟，慢模型自动降权/剔除，付费源可关探测 |
| **上下文感知** | 估算请求 token，排除上下文不够的模型，max_tokens 自动调低 |
| **模型别名** | 别名指针直达指定模型，客户端无感知切换底层模型 |
| **同名模型跨源聚合** | 同一模型名分布在多个上游源时可互为候选（按源顺序兜底）；「聚合模型」页可视化展示 `源·真实模型 → 源·真实模型`，可勾选成员、拖拽调优先级、单组关闭或恢复自动。**同名自动聚合默认关闭**（跨源兜底不受影响），需聚合请手动创建；开关在系统设置 |
| **异名模型聚合** | 不同源里同一个模型名不一致时（`buddy/deepseek-v4.1-flash` vs `loomy/DeepSeek-V4.1-Flash`），系统按「去前缀+忽略大小写+忽略符号差异」自动识别并给出合并建议，一键合并为统一聚合名；也可手动任意组合 |
| **模型级管理** | 上游源内单个模型可启用/禁用（不影响同源其他模型）、可拖拽调整顺序（决定 direct 命中与聚合优先级） |
| **聚合模型统一** | 两类聚合同一页管理：**固定成员**（自己勾选源/真实模型，支持异名，按顺序跨源兜底）与**规则聚合**（候选由路由规则按请求内容运行时匹配）。统一存于 `agg_unified`（`kind` = static / rule） |
| **规则聚合可裁剪** | 一张路由规则表 + 每个聚合引用其子集：新建聚合时选「规则匹配」后可勾选**用哪几条规则**、**每条规则用哪几个候选**；规则全选 = 跟随（规则以后加模型自动纳入），取消任一候选 = 存显式子集。删除/改名规则自动清理引用它的聚合绑定（清空则回退全跟随），规则里移除已绑定候选时卡片显示失效黄标 |
| **请求可观测** | 每个 `/v1` 请求记一行访问日志（状态码/耗时/客户端 IP/模型/流式/消息数），出错时附请求体摘要（`sk-` 密钥自动打码）；日志落轮转文件 `logs/smart-router.log`（10MB×5），`GET /admin/api/logs?keyword=` 网页接口直接取现场，不用登服务器。三入站统一请求体校验（畸形请求返回 400 而非裸 500），未捕获异常按协议返回规范错误体。响应开始前客户端断开时记 `status=499 disconnected=true`（此前这类请求完全没有痕迹） |
| **请求详情（三栏对比）** | 用量明细点任意一行 → 抽屉三栏并列：**REQUEST（原始请求）/ FORWARDED（实际转发）/ RESPONSE（上游响应）** + 尝试链（每个候选的 HTTP 码/耗时/失败原因）。默认只对**失败请求**保存完整报文（成功只记结构化字段 + token），可在系统设置切 `off` / `error_only` / `all`；单报文上限 1 MB（超出保留头 3/4 + 尾 1/4 并标注），报文落库前脱敏 |
| **缓存 token 与重试可见** | 用量表按「输入 / 缓存读 / 输出」三段统计 token（兼容 OpenAI `cached_tokens`、Anthropic `cache_read_input_tokens`、中转站 `prompt_cache_hit_tokens`），并新增「尝试」列标出发生重试的请求 |
| **请求过滤（Pre-flight）** | 转发**之前**按规则过滤候选，命中就根本不发出去，从源头避免上游渠道因「非官方客户端」把号池里的号封掉。匹配对象支持 system 首行 / 全部 system 文本 / 请求体正则，动作分 `跳过`（换下一个成员）与 `拒绝`（返回 400）。**聚合模型无感切换**（命中成员被静默移除，客户端无感知），**直连模型直接 400** 并写明命中的规则。全局开关默认关（关闭时零开销），预置 DSH / Claude Code 两条身份规则（默认不启用），后台可粘请求体试跑 |
| **日志定期清理** | 主表与详情表共用保留期（默认 14 天，可设 7/14/30/90），后台每轮先删详情再删主表，不留孤儿行 |
| **聚合组独立探测** | 每个聚合可单独开关定时探测、设间隔/慢阈值/排序方式（稳定优先 / 速度优先）；探测对象按「上游源 × 真实模型」**全局去重**，多聚合共用同一模型只探一次 |
| **探测模板** | 一套可复用的探测节奏（间隔 / 慢阈值 / 排序 / 时段）。多个聚合挂同一模板即共用，改模板全组立即生效；模板值优先、不可被聚合覆盖；删模板自动回退自配 → 全局 |
| **探测排班表** | 按小时着色直观展示每个探测单元何时探测（探测中 / 时段外 / 已关闭），支持「合并视图 / 按星期」切换，行尾给出间隔、次/时、次/日与引用聚合，成本一目了然 |
| **探测时段** | 支持夜间不探测 / 周末不探测 / 只在工作时间探测：按「星期 + 时段窗口」配置（支持跨夜），三个快捷模板；时段外保留旧数据并标记「时段外 / 数据陈旧」 |
| **动态权重排序** | 规则聚合按「优先级 + 实时延迟动态权重（`base_weight × (base_latency/latency)²`）」排序；固定成员聚合按 stable / latency 两档分层排序，全不可用时回退配置顺序 |
| **三层用量统计** | 全局 / 模型级 / 客户端 Key 级用量与成功率，含逐条请求明细；流式自动注入 `include_usage` 取真实 tokens，上游不支持时按字符估算并标注 |
| **按单元用量（号池核算）** | 额外按「上游源 × 上游真实模型名」统计，聚合请求记账到实际命中的真实模型，可直接看出各家额度消耗 |
| **管理后台** | Vue3 SPA（同端口 10002）：仪表盘/上游源/规则/别名/Key/聚合模型（三标签）/用量统计/系统设置（全局容错 + 分组），JWT 鉴权，热重载 |
| **统一列表** | 全站 15 处列表共用一层组件（标题+右上主操作 / 筛选区 / 常驻工具条 / 条目 / 底部统一分页）；工具条内建快捷全选（只作用当前页、带半选态）与批量操作 |
| **xlsx 导出** | 每个列表都能「导出全部（按当前筛选）」与「批量导出选中项」，覆盖 10 个数据集；xlsx 由标准库手写 OOXML，**零依赖**（部署只同步代码、不装依赖） |
| **双栈监听** | 同一端口同时接受 IPv4 与 IPv6（显式 `dualstack_ipv6` socket；注意 Python 3.12 的 asyncio 会把 `host="::"` 变成 IPv6-only） |
| **接入说明** | 每个 API Key 内置接入弹窗：地址/可用模型/curl/Python SDK 预填示例一键复制 |

## 快速开始

### 环境要求

- Python 3.14（uv 管理依赖，见 `backend/pyproject.toml`）
- 前端构建：Node.js（`frontend/`，Vue3 + Vite + Element Plus）

### 本地运行

```bash
# 首次：初始化数据库（一次性建全表 + 种子数据 + 全部增量结构）
cd backend
uv run python seed.py

# 后端（本地托管前端需指定 FRONTEND_DIST 指向构建产物）
$env:FRONTEND_DIST = "../frontend/dist"   # Windows PowerShell；Linux 用 export
uv run python run.py          # 监听 :10002

# 前端开发（可选，改前端时）
cd frontend
npm install
npm run dev                   # 开发服务器
npm run build                 # 产出 dist（后端生产模式直接托管）
```

> **数据库结构以 `seed.py` 的执行结果为准。**
>
> `sql/01_建表.sql` 只是 **v5 初版基线**，之后每轮迭代都通过 `sql/increment/*.sql` 增量补列补表。
> 因此**不要单独读 `01_建表.sql` 来判断当前表结构**——它缺 `up_upstream_key` 表、`up_upstream` 的
> `enabled/models/smart_retry/groups` 四列、`agg_unified` 及其 `rule_bindings/groups` 两列、
> `filter_rule` 表等。想看清完整结构，直接跑 `seed.py` 后 `PRAGMA table_info(...)`。
>
> `seed.py` 已按依赖顺序串起全部 15 个脚本，**一条命令即可得到与生产一致的最新结构**，
> 不必手动逐个执行；增量脚本按「老库升级路径」的价值保留，不删除。

### 演示环境（假数据，不碰正式配置）

想先看看聚合模型/探测配置长什么样，可以用独立演示库跑一套假数据：

```powershell
.\run_demo.ps1            # 生成 demo.db（若不存在）并启动 :10198
.\run_demo.ps1 -Reseed    # 强制重建演示数据后再启动
```

- 演示库 `backend/demo.db` 与正式库完全隔离（通过 `SMART_ROUTER_DB` 环境变量切换），已加入 `.gitignore`
- 内含 4 个上游源、3 个聚合组 + 2 个规则聚合、2 个探测模板（已挂到 3 个聚合）、3 把客户端 Key、2 条规则、14 天约 1400 条用量
- 特意留了一组未合并的异名模型，可在聚合页体验「一键合并」
- 聚合页三个标签都有数据可看：聚合组（含模板徽标）、探测模板（含引用统计）、探测计划（排班表 + 单元明细）
- 清理：`python test/clear_demo_ch022.py`

### 服务器部署（生产现状）

```
/opt/smart-router/backend/        # 后端代码 + smart_router.db（SQLite）
/opt/smart-router/frontend_dist/  # 前端构建产物（FRONTEND_DIST 环境变量指向）
systemd 服务：smart-router（:10002，Restart=always）
```

部署脚本：

| 脚本 | 用途 |
|------|------|
| `test/deploy_probe_prod.py` | **只读勘察**生产现状（目录/文件树/表结构/systemd 配置），部署前必跑 |
| `test/deploy_v520_full.py` | **全量部署**（整树同步）：备份 → 传 sql → 预迁移 → 传代码 → 替换 dist → chown → 语法预检 → 重启验证；每步失败即中止 |

> **两条硬约束**：
> 1. **绝不在有数据的库上执行 `seed.py`** —— `drop_all()` 会先删全部表再重建，生产数据全丢。
> 2. **老库升级必须先补表结构再上代码** —— 新代码在模块导入期就会读全部表，表缺失会让配置加载走静默降级分支（`except OperationalError → 置空`），表现为「服务启动正常但业务全废」。缺失结构由 `sql/06` 与 `sql/increment/06~11` 的幂等脚本补齐。

#### 环境变量

| 变量 | 默认 | 说明 |
|------|------|------|
| `SMART_ROUTER_DB` | `backend/smart_router.db` | 数据库文件路径（演示环境指向 `demo.db`） |
| `FRONTEND_DIST` | `frontend_dist` | 前端构建产物目录 |
| `SR_JWT_SECRET` | 自动生成 | 管理后台 JWT 签名密钥。**不设时首次启动自动生成并写入 `sys_setting.jwt_secret`**，重启后会话不失效；多实例部署必须显式设置同一值，否则 token 互不认可 |

> 轮换 JWT 密钥：改 `SR_JWT_SECRET` 或更新 `sys_setting.jwt_secret` 后重启，所有已登录会话立即失效（需重新登录）。

## 使用方式

### 管理后台

浏览器访问 `http://your-server:10002`，登录后（侧边栏按职能分组，智能路由与统计可折叠）：

1. **仪表盘** — 运营首页：健康条（探测/单元/时段/成功率/待关注）+ 5 指标卡 + 7 天双指标趋势 + 上游贡献占比 + 上游源卡片 + 聚合组概览 + 需要关注
2. **上游源** — 添加/编辑/禁用源；**多分组归属**；Base URL 实时拼接预览；多 Key 池；智能重试开关；模型列表（拉取/手动添加/单测/全测/批量），**每个模型可单独覆盖协议、单独启停、拖拽排序**
3. **模型别名** — 别名指针管理
4. **API Key** — 增删改、随机生成、多分组指派、「接入说明」弹窗
5. **智能路由**（折叠）
   - 路由规则 — 权重/优先级/上下文上限
   - **聚合模型**（三标签）
     - 聚合组 — 固定成员（可跨源/异名，可视化编辑 + 拖拽优先级 + 一键合并建议）与规则聚合（候选由路由规则运行时匹配，可裁剪用哪几条规则/每条的哪几个候选）统一管理；**每个聚合有自己的「可用分组」，权限只看聚合自身，成员分组不参与**；各自可配探测与排序
     - 探测模板 — 一套可复用探测节奏，多个聚合共用，改模板即全组生效
     - 探测计划 — 探测排班表（0~23 点色块 / 按星期视图 / 成本汇总）+ 单元明细 + 全局探测默认值
6. **统计**（折叠）— 用量统计：全局/模型级/Key 级三层 + 按单元（源×真实模型）+ 请求明细（今日 / 7 天 / 30 天）；明细行可点开**三栏详情**（原始请求 / 实际转发 / 上游响应）；顶部含「已过滤」卡片与状态筛选
7. **请求过滤** — 全局引擎开关 + 规则表格（匹配对象 / 动作 / 作用域 / 启停）+ 新建编辑 + **试跑面板**（粘请求体看哪些候选会被拦）
8. **系统设置** — 全局容错（请求重试 / 智能重试 / 故障转移）、同名模型聚合开关、用量与日志（详情采集模式 / 单报文上限 / 保留期）、分组管理、配置操作

> 旧地址 `/latency` 自动跳到「聚合模型 → 探测计划」，`/route-params` 自动跳到系统设置。

### 客户端接入

```bash
# OpenAI 格式
curl http://your-server:10002/v1/chat/completions \
  -H "Authorization: Bearer YOUR_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"smart-latest","messages":[{"role":"user","content":"你好"}]}'

# Anthropic 格式（Claude Code 等，x-api-key 或 Bearer 均可）
curl http://your-server:10002/v1/messages \
  -H "x-api-key: YOUR_KEY" -H "anthropic-version: 2023-06-01" \
  -H "Content-Type: application/json" \
  -d '{"model":"smart-latest","max_tokens":1024,"messages":[{"role":"user","content":"你好"}]}'

# Responses 格式（Codex CLI 等）
curl http://your-server:10002/v1/responses \
  -H "Authorization: Bearer YOUR_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"smart-latest","input":"你好"}'
```

```python
from openai import OpenAI

client = OpenAI(base_url="http://your-server:10002/v1", api_key="YOUR_KEY")
resp = client.chat.completions.create(
    model="smart-latest",
    messages=[{"role": "user", "content": "你好"}],
)
print(resp.choices[0].message.content)
```

模型名三种用法：
- **聚合模型名**（如 `smart-latest`）→ 智能路由
- **别名**（管理后台配置的指针）→ 直达指定模型
- **具体模型名**（如 `deepseek-v4-flash`）→ 直接透传到对应上游

成功响应带 `X-Served-By: {上游}/{模型}` 与 `X-Retry-Count` 头，便于调试。

## 协议矩阵

| 方向 | OpenAI chat | Anthropic | Responses |
|------|------------|-----------|-----------|
| 入站（客户端 → 本服务） | ✅ `/v1/chat/completions` | ✅ `/v1/messages`（x-api-key 兼容） | ✅ `/v1/responses`（Codex 可用） |
| 出站（本服务 → 上游） | ✅ | ✅（模型级覆盖） | ✅（模型级覆盖） |

内部统一以 OpenAI chat 格式为中间语言：入站归一化 → 路由 → 出站按模型协议转换。任意协议客户端可调用任意协议上游的模型。

三协议入站能力对齐（v5.1.0+）：
- **错误格式**：各协议错误按各自标准格式返回（OpenAI `{"error":{...}}` / Anthropic `{"type":"error","error":{...}}` / Responses `{"error":{...}}`），客户端 SDK 可直接解析
- **图片**：messages/responses 入站支持图片块（base64 或 URL），真实透传（不支持图片的模型由上游拒绝报错）
- **推理模型**：reasoning 内容映射（Anthropic `thinking` 块 / Responses `reasoning` item），正文为空时推理内容不丢失

## 技术栈与结构

- **后端**：FastAPI + httpx + SQLite（配置库存储 + 内存缓存 + 热重载），uv 管理
- **前端**：Vue3 + Vite + Element Plus + Pinia，构建产物由后端静态托管
- **结构**：

```
backend/app/
├── main.py               # 组装：中间件鉴权 + 服务注册 + SPA 托管
├── api/                  # admin/*（管理接口）+ v1/*（客户端接口）
├── core/                 # config（SQLite+缓存）/ router_engine / probe / health / key_pool / filter_engine
├── services/             # router_service（调度核心）/ config_service / ...
├── repositories/         # 13 个业务 Repository（upstream/key/rule/pointer/group/aggregation/usage/filter_rule/...）
└── upstream/             # openai / anthropic / responses 三个出站适配器
frontend/src/views/       # Dashboard / Upstreams / Rules / Pointers / ApiKeys / Settings ...
```

## 文档索引

| 文档 | 说明 |
|------|------|
| [docs/需求规格.md](docs/需求规格.md) | 功能需求与核心实体（含迭代新增需求第八节） |
| [docs/架构设计.md](docs/架构设计.md) | 分层架构与模块划分（含维护迭代架构演进第十一节） |
| [docs/系统核心流程.md](docs/系统核心流程.md) | 核心流程图与对外能力清单 |
| [docs/数据库设计.md](docs/数据库设计.md) | SQLite 表结构（sql/ 含全量与增量脚本） |
| [docs/API契约.md](docs/API契约.md) | 端点契约（入参/出参/错误码） |
| [docs/接口文档.md](docs/接口文档.md) | 接口说明与示例 |
| [docs/五列对应矩阵.md](docs/五列对应矩阵.md) | 需求→实体→表→API→模块 全链路追溯 |
| [docs/变更记录.md](docs/变更记录.md) | 全部业务变更记录 |
| [docs/_changes/](docs/_changes/) | 变更文档（已归档批次在 archived/） |
| [.devflow/PLAN-多协议与分组管理.md](.devflow/PLAN-多协议与分组管理.md) | 协议矩阵规划（P0~P3） |

## 流程管控

本项目使用 fullstack-dev-flow 技能管控（6 阶段门禁 + 维护迭代 A/B/C 三线 + 9 条铁律），管控文件位于 `.devflow/`：

| 文件 | 说明 |
|------|------|
| .devflow/STATE.md | 流程状态 + 维护迭代记录 |
| .devflow/feedback-log.md | 用户反馈台账（FB 编号） |
| .devflow/logs/ai-actions.md | AI 操作留痕（倒序） |
| docs/_changes/ | B 线变更文档 + archived/ 归档 |
