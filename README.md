# Smart Router v5 - AI 模型智能路由代理

基于 FastAPI + Vue3 + SQLite 的轻量级 AI 模型智能路由代理。部署在中转站前方，根据请求内容自动选择最佳模型，提供延迟探测、故障转移、Key 池、分组权限、智能重试、多协议适配等企业级能力。

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
| **分组权限** | 可配置分组（free/premium/自定义），API Key 与上游源按分组隔离，/v1/models 按 Key 过滤 |
| **请求级容错** | 候选转移 + Key 轮换 + 同渠道退避重试三层；流式首字节分界线（吐字前可重试，吐字后不重复） |
| **延迟探测** | 定期探测候选模型延迟，慢模型自动降权/剔除，付费源可关探测 |
| **上下文感知** | 估算请求 token，排除上下文不够的模型，max_tokens 自动调低 |
| **模型别名** | 别名指针直达指定模型，客户端无感知切换底层模型 |
| **管理后台** | Vue3 SPA（同端口 10002）：仪表盘/上游源/规则/别名/Key/分组/探测与重试参数，JWT 鉴权，热重载 |
| **接入说明** | 每个 API Key 内置接入弹窗：地址/可用模型/curl/Python SDK 预填示例一键复制 |

## 快速开始

### 环境要求

- Python 3.14（uv 管理依赖，见 `backend/pyproject.toml`）
- 前端构建：Node.js（`frontend/`，Vue3 + Vite + Element Plus）

### 本地运行

```bash
# 后端（含前端静态托管，frontend/dist 存在时自动挂载）
cd backend
uv run python run.py          # 监听 :10002

# 前端开发（可选，改前端时）
cd frontend
npm install
npm run dev                   # 开发服务器
npm run build                 # 产出 dist（后端生产模式直接托管）
```

### 服务器部署（生产现状）

```
/opt/smart-router/backend/        # 后端代码 + smart_router.db（SQLite）
/opt/smart-router/frontend_dist/  # 前端构建产物（FRONTEND_DIST 环境变量指向）
systemd 服务：smart-router（:10002，Restart=always）
```

增量部署脚本见 `test/deploy_*_incremental.py`（paramiko SFTP 上传 + 服务器侧 py_compile 预检 + systemctl 重启 + 健康验证）。

## 使用方式

### 管理后台

浏览器访问 `http://your-server:10002`，登录后：

1. **仪表盘** — 上游源数、模型可用率、Key 数、故障状态
2. **上游源** — 添加/编辑/禁用源；Base URL 实时拼接预览；多 Key 池；智能重试开关；模型列表（拉取/手动添加/单测/全测/批量），**每个模型可单独覆盖协议**
3. **路由规则** — 可视化编辑候选模型（权重/优先级/上下文上限）
4. **模型别名** — 别名指针管理
5. **API Key** — 增删改、随机生成、分组指派、「接入说明」弹窗
6. **设置** — 探测/重试/故障转移/智能重试全局参数、分组管理、密码修改、热重载

### 客户端接入

```bash
# OpenAI 兼容格式（当前唯一入站协议）
curl http://your-server:10002/v1/chat/completions \
  -H "Authorization: Bearer YOUR_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"smart-latest","messages":[{"role":"user","content":"你好"}]}'
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

## 技术栈与结构

- **后端**：FastAPI + httpx + SQLite（配置库存储 + 内存缓存 + 热重载），uv 管理
- **前端**：Vue3 + Vite + Element Plus + Pinia，构建产物由后端静态托管
- **结构**：

```
backend/app/
├── main.py               # 组装：中间件鉴权 + 服务注册 + SPA 托管
├── api/                  # admin/*（管理接口）+ v1/*（客户端接口）
├── core/                 # config（SQLite+缓存）/ router_engine / probe / health / key_pool
├── services/             # router_service（调度核心）/ config_service / ...
├── repositories/         # 七表 Repository（upstream/key/rule/pointer/...）
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
