# Smart Router API 契约

> 创建时间：2026-08-09
> 状态：已上线（生产运行中，v5.2.3）
> 关联流程：fullstack-dev-flow stage-2
> 关联数据库设计：[docs/数据库设计.md](数据库设计.md)
> 版本：v5.2.3（保持 v4 管理 API 路径不变，兼容前端迁移；变更见第六节变更记录）

---

## 一、通用约定

### 1.1 基础路径

- 路由代理基础路径: `http://<server>:10002`
- 对外客户端接口前缀: `/v1/`
- 管理后台接口前缀: `/admin/api/`
- 健康状态接口: `/health`、`/status`

### 1.2 鉴权方式

| 接口组 | 方式 | 说明 |
|--------|------|------|
| 客户端接口 /v1/* | Bearer Token（路由层 API Key） | 白名单校验，无效返回 401 |
| 管理接口 /admin/api/* | Bearer Token（JWT） | 登录后获取，除 login 外全部需要 |
| /health /status | 无 | 公开 |

Header: `Authorization: Bearer <token>`

### 1.3 通用响应结构

管理接口统一响应结构：

```json
{
  "ok": true,
  "data": { ... }
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| ok | boolean | true=成功, false=失败 |
| data | object/array/null | 业务数据（成功时） |

错误响应（HTTP 非 2xx）由 FastAPI 统一返回：

```json
{
  "detail": "错误描述"
}
```

| HTTP 状态码 | 含义 |
|------------|------|
| 200 | 成功 |
| 400 | 参数错误 / 业务冲突 |
| 401 | 未登录 / 密钥无效 |
| 403 | 无权限（分组无权访问） |
| 404 | 资源不存在 |
| 503 | 无可用模型 |

### 1.4 客户端接口响应

客户端接口（/v1/chat/completions 等）返回 OpenAI 兼容格式（choices/usage/stream SSE），错误返回 OpenAI 格式：

```json
{
  "error": { "message": "Invalid API key.", "type": "auth_error", "code": 401 }
}
```

各协议入站的错误均按对应协议标准格式返回（CH-018）：

| 入站 | 错误格式 |
|------|---------|
| OpenAI（/v1/chat/completions） | `{"error": {"message", "type", "code"}}` |
| Anthropic（/v1/messages） | `{"type": "error", "error": {"type", "message"}}` |
| Responses（/v1/responses） | `{"error": {"message", "type", "code"}}` |

> 无可用模型返回 503 + 上述各协议格式错误；客户端 SDK 可直接解析，不再出现"超时无反馈"。

**请求体校验（CH-025）**：三个入站现在都对请求体做统一校验，畸形请求返回 **400**（此前 `/v1/chat/completions` 缺校验，非 JSON body 会变成无错误体的裸 500）：

| 情况 | 返回 |
|------|------|
| body 不是合法 JSON | 400 各协议格式 `请求体不是合法 JSON` |
| body 不是 JSON 对象（数组 / null / 字符串） | 400 `请求体必须是 JSON 对象` |
| `model` 缺失 | 400 `model 参数缺失` |
| `messages` 缺失或不是数组（仅 chat） | 400 `messages 参数缺失或不是数组` |

**未捕获异常兜底（CH-025）**：服务端注册了全局异常处理器，任何未被业务捕获的异常按入站协议返回规范化错误体（HTTP 500），不再返回 FastAPI 默认的纯文本 `Internal Server Error`：

| 入站 | 兜底错误格式 |
|------|-------------|
| OpenAI（/v1/chat/completions） | `{"error": {"message": "中转站内部错误: <异常类型>", "type": "api_error", "code": 500}}` |
| Anthropic（/v1/messages） | `{"type": "error", "error": {"type": "api_error", "message": "中转站内部错误: <异常类型>"}}` |
| Responses（/v1/responses） | `{"error": {"message": "中转站内部错误: <异常类型>", "type": "api_error"}}` |

---

## 二、客户端接口（/v1/）

### 2.1 聊天补全

- **路径**: `POST /v1/chat/completions`
- **鉴权**: 路由层 API Key
- **入参**: OpenAI chat/completions 格式（model/messages/stream/tools/max_tokens 等）
  - model 取值：聚合模型名（智能路由）/ 模型别名（直接转发）/ 具体模型名（透传）
- **出参**: OpenAI chat.completion 格式 或 SSE 流
- **状态码**: 200 / 401 / 403 / 503
- **错误码**:
  - 401: 缺失或无效 API Key
  - 403: Key 无权访问目标分组
  - 503: 无可用模型

### 2.2 Anthropic Messages

- **路径**: `POST /v1/messages`
- **鉴权**: 路由层 API Key（兼容 `x-api-key` 头）
- **说明**: Anthropic 格式请求，内部转 OpenAI 格式路由，响应转回 Anthropic 格式
- **入参**: Anthropic messages 格式（model/messages/max_tokens/system/tools/stream 等）；`content` 支持 text/image 块（base64 或 url，CH-018）
- **出参**: Anthropic messages 格式 或 SSE 流
- **推理模型**: 上游 `reasoning` 内容映射为 anthropic `thinking` 块（非流式）/ `thinking_delta` 事件（流式），正文为空时仍返回推理内容（CH-018）
- **错误**: Anthropic 标准错误格式 `{"type":"error","error":{"type","message"}}`（CH-018）

### 2.3 Responses

- **路径**: `POST /v1/responses`
- **鉴权**: 路由层 API Key（Bearer）
- **说明**: Responses 格式请求（Codex 等），内部转 OpenAI 格式路由，响应转回 Responses 格式
- **入参**: Responses 格式（model/input/instructions/max_output_tokens/tools/stream 等）；`input[].content` 支持 input_text/input_image 块（CH-018）
- **出参**: Responses 格式 或 SSE 流
- **推理模型**: 上游 `reasoning` 内容映射为 Responses `reasoning` output item（非流式）/ `response.reasoning_summary_text.delta` 事件（流式）（CH-018）
- **错误**: Responses 标准错误格式 `{"error":{"message","type","code"}}`（CH-018）

### 2.4 模型列表

- **路径**: `GET /v1/models`
- **鉴权**: 路由层 API Key
- **分组过滤**: 仅返回该 Key 有权访问分组的上游模型（无 Key 返回 401）
- **出参**: OpenAI models 列表 + 聚合模型条目 + 别名条目
- **CH-033**: 聚合条目覆盖 **rule 与 static 两类**；static 聚合（含异名聚合）此前被遗漏，导致「聚合名可调用但在模型列表看不到」。聚合条目标记 `type: "aggregation"`，并用 `aggregation_kind` 区分 `rule` / `static`；`enabled=false` 的聚合不输出；与真实模型或另一聚合重名时只输出一次
- **CH-034**: 聚合条目**按聚合自身 `groups` 过滤**（空 = 所有 Key 可见），不再按成员所属上游源分组过滤；真实模型条目仍按上游源分组过滤。聚合条目额外输出 `groups` 字段

```json
{
  "object": "list",
  "data": [
    { "id": "deepseek-v4-1-flash", "object": "model", "owned_by": "smart-router", "type": "aggregation", "aggregation_kind": "static", "member_count": 3, "groups": ["premium"] },
    { "id": "smart-latest", "object": "model", "owned_by": "smart-router", "type": "aggregation", "aggregation_kind": "rule", "context_length": 128000, "max_output": 65536, "groups": [] },
    { "id": "my-model", "object": "model", "owned_by": "smart-router", "type": "pointer", "target_model": "deepseek-ai/deepseek-v4-pro" },
    { "id": "mistralai/mistral-large-...", "object": "model" }
  ]
}
```

> **403 文案差异（CH-034）**：请求被拒时，聚合命中报 `API Key 无权访问聚合 xxx（该聚合分组 [...]）`；真实模型命中报 `API Key 无权访问分组 [...]（模型 xxx）`——可用于快速区分是聚合门面拒绝还是成员级拒绝。

---

## 三、公开状态接口

### 3.1 健康检查

- **路径**: `GET /health`
- **鉴权**: 无
- **出参**: `{"status": "ok", "version": "5.0"}`

### 3.2 路由状态面板

- **路径**: `GET /status`
- **鉴权**: 无
- **出参**:

```json
{
  "version": "5.0",
  "aggregated_models": ["smart-latest", "smart-chat", "auto-chat"],
  "latency_panel": { "模型名": { "latency": "1.2s", "status": "ok", "error": null } },
  "rules": [
    { "name": "视觉理解", "candidates": [ { "model": "...", "upstream": "newapi", "base_weight": 5, "dynamic_weight": 3.2, "latency": 1.2, "status": "ok", "max_context": 1000000, "max_output": 32768 } ] }
  ],
  "health": { "fails": {}, "cooldown": {} }
}
```

---

## 四、管理接口（/admin/api/）

### 4.1 登录

- **路径**: `POST /admin/api/login`
- **鉴权**: 不需要
- **入参**:

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| username | string | 是 | 管理员用户名 |
| password | string | 是 | 管理员密码 |

- **出参**:

```json
{ "ok": true, "token": "eyJhbGciOi..." }
```

- **错误码**: 401 用户名或密码错误

### 4.2 仪表盘

- **路径**: `GET /admin/api/dashboard`
- **鉴权**: JWT
- **出参**:

```json
{
  "upstream_count": 4,
  "model_count": 12,
  "probe_unit_count": 7,
  "model_ok": 5,
  "model_down": 2,
  "rule_count": 3,
  "pointer_count": 3,
  "api_key_count": 3,
  "health": { "fails": {}, "cooldown": {}, "probe_down": {} },

  "usage_today": { "requests": 56, "success_rate": 0.946, "total_tokens": 63800,
                   "active_keys": 3, "requests_delta": -0.45 },
  "usage_7d": { "requests": 724, "total_tokens": 771800, "success_rate": 0.981 },
  "trend": [ { "date": "10-11", "requests": 82, "success_count": 81, "total_tokens": 91600 } ],

  "upstream_usage": [ { "upstream_id": "buddy", "upstream_name": "Buddy 积分池",
                        "requests": 327, "success_count": 320, "error_count": 7,
                        "total_tokens": 376600, "share": 0.488,
                        "probe_ok": 3, "probe_total": 3,
                        "enabled": true, "smart_retry": true } ],

  "groups": [ { "model": "deepseek-v4-1-flash", "member_count": 3,
                "members": [ { "upstream": "buddy", "model": "deepseek-v4.1-flash" } ],
                "configured": true, "probe_enabled": true, "probe_interval": 60,
                "probe_schedule": "工作日 08:00-23:00", "probe_schedule_mode": "window",
                "sort_mode": "latency", "requests_7d": 297, "tokens_7d": 268700 } ],

  "attention": [ { "kind": "probe_down", "target": "gemini-2.5-pro@buddy",
                   "detail": "探测不可用：..." } ],

  "probe_summary": { "enabled": true, "unit_count": 7, "ok": 5, "down": 1, "unknown": 1,
                     "global_interval": 300, "global_schedule": "全天候", "scheduled_off": 3 }
}
```

**字段说明（CH-022 扩展）**：

| 字段 | 说明 |
|---|---|
| `usage_today` / `usage_7d` | 按请求时间 `ts` 聚合（today 以本地自然日 0 点起） |
| `requests_delta` | 今日 0 点至今 vs 昨日同期 的请求数环比；昨日同期为 0 时返回 `null` |
| `trend` | 最近 7 个自然日，缺失日期补 0；`date` 格式 `MM-DD` |
| `upstream_usage` | 按上游源聚合近 7 天，`share` 按 tokens 占比；附探测可用率与实际启用/智能重试状态 |
| `groups` | 聚合组概览：成员链路 + 探测配置 + 近 7 天用量；`configured=false` 表示自动发现 |
| `attention` | 待关注项，`kind ∈ {cooldown, probe_down, no_key, stale, disabled_upstream}` |
| `probe_summary` | 去重探测计划的健康摘要；`scheduled_off` 为当前处于探测时段外的单元数 |

> `usage_*` / `trend` 在 `log_usage` 尚未建立时返回零值，不影响其余字段。

### 4.3 上游源列表

- **路径**: `GET /admin/api/upstreams`
- **鉴权**: JWT
- **出参**:

```json
{ "upstreams": [ { "id": "newapi", "name": "NewAPI 中转站", "base_url": "http://...", "api_key": "sk-XW***gow", "key_count": 3, "keys": ["sk-xxx", "sk-yyy"], "format": "openai", "group": "free", "groups": ["free"], "probe_enabled": true } ] }

> `groups` 为归属分组数组（CH-016 多分组）；`group` 为其首元素冗余（向后兼容）。权限判定：Key 分组集合与源 groups 集合有交集即放行。
```

> api_key 字段脱敏显示；key_count 为 Key 池数量；keys 为完整 Key 数组（管理端编辑回显用）

### 4.4 添加上游源

- **路径**: `POST /admin/api/upstreams`
- **鉴权**: JWT
- **入参**:

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| id | string | 是 | 上游源 ID（唯一） |
| name | string | 是 | 显示名称 |
| base_url | string | 是 | 地址 |
| api_key | string | 否 | 单 Key 快捷写法（api_keys 为空时兜底） |
| api_keys | array\<string\> | 否 | Key 池（批量 Key，优先于 api_key） |
| format | string | 否 | openai/anthropic/responses，默认 openai（源级；模型级 protocol 可覆盖） |
| group | string | 否 | 单分组（旧字段，与 groups 二选一） |
| groups | array | 否 | 归属分组数组（CH-016 多分组），默认 ["free"] |

> api_key / api_keys 至少提供一个

### 4.5 更新上游源

- **路径**: `PUT /admin/api/upstreams/{upstream_id}`
- **鉴权**: JWT
- **入参**: 同 4.4 的字段（除 id 外均可选）；传 `api_keys` 则整体替换 Key 池，不传则保持原 Key 池
- **错误码**: 404 上游源不存在

### 4.6 删除上游源

- **路径**: `DELETE /admin/api/upstreams/{upstream_id}`
- **鉴权**: JWT
- **说明**: 级联删除该上游的 Key 池（up_upstream_key）
- **错误码**: 404 上游源不存在

### 4.7 测试上游源模型

- **路径**: `POST /admin/api/upstreams/{upstream_id}/test`
- **鉴权**: JWT
- **入参**:

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| model | string | 是 | 要测试的模型名 |
| prompt | string | 否 | 测试提示词，默认「你好，请回复一句话」 |

- **出参**: `{ "ok": true, "content": "模型回复文本" }`
- **说明**: 走 Key 池选 Key 转发；失败时 502 返回 `{ok: false, error}`，error 含具体原因（HTTP 状态码+响应体错误信息/连接超时/响应超时/连接异常）
- **错误码**: 400 上游源已禁用；404 上游源不存在；502 测试失败（含具体原因）

### 4.7.1 写入上游源已配置模型列表

- **路径**: `PUT /admin/api/upstreams/{upstream_id}/models`
- **鉴权**: JWT
- **入参**: `{ "models": [{"name": "deepseek-chat"}, {"name": "qwen3.7-max", "protocol": "anthropic"}] }`（整体覆盖；批量加入时前端合并去重后提交）
- **模型条目**: `name` 必填；`protocol` 可选（CH-011 模型级协议覆盖），取值 `openai` / `anthropic` / `responses`（CH-014），缺省继承源级 `format`；非法值 422
- **出参**: `{ "ok": true, "models": [...] }`
- **错误码**: 404 上游源不存在；422 protocol 非法
- **兼容**: 存量纯字符串数组（`["m1"]`）读取时自动归一化为 `[{"name": "m1"}]`

### 4.7.2 删除上游源单个模型

- **路径**: `DELETE /admin/api/upstreams/{upstream_id}/models?model={model_name}`
- **鉴权**: JWT
- **入参**: `model`（query 参数，模型名可能含 `/`，必须走 query 避免路径匹配失败）
- **出参**: `{ "ok": true }`
- **错误码**: 400 model 参数缺失；404 上游源不存在

### 4.7.3 单模型启用/禁用（CH-019）

- **路径**: `PATCH /admin/api/upstreams/{upstream_id}/models?model={model_name}`
- **鉴权**: JWT
- **入参**: `{ "enabled": false }`
- **行为**: 仅改该模型条目的 `enabled` 标记，保留 `protocol` 等其余字段；禁用后不出现在 `GET /v1/models`、不参与路由与延迟探测
- **出参**: `{ "ok": true, "model": "...", "enabled": false }`
- **错误码**: 400 model 参数缺失；404 上游源不存在 / 模型不在该源已配置列表

### 4.7.4 模型顺序重排（CH-019）

- **路径**: `PUT /admin/api/upstreams/{upstream_id}/models/order`
- **鉴权**: JWT
- **入参**: `{ "names": ["model-b", "model-a"] }`（重排后的完整有序名单；未出现的模型按原相对顺序追加尾部）
- **出参**: `{ "ok": true, "models": ["model-b", "model-a"] }`
- **错误码**: 404 上游源不存在

### 4.24 聚合组列表（CH-019 / CH-020）

- **路径**: `GET /admin/api/model-groups`（可选 `?model=xxx` 过滤单个）
- **鉴权**: JWT
- **出参**:

```json
{
  "groups": [
    {
      "model": "deepseek-v4-1-flash",
      "sources": ["dsh", "trae"],
      "members": [
        {"upstream": "dsh",  "model": "deepseek/deepseek-v4.1-flash"},
        {"upstream": "trae", "model": "trae/deepseek-v4.1-flash"}
      ],
      "enabled": true,
      "configured": false,
      "auto_sources": ["dsh", "trae"]
    }
  ]
}
```

- **字段说明**: `model` 为**聚合名**（客户端请求用）；`sources` 为生效源顺序（兼容旧前端）；`members` 为 `{upstream, model}`，其中 `model` 是该源里的**真实模型名**（支持异名）；`configured=false` 表示走自动发现；`auto_sources` 为自动发现的同名源
- **说明**: 自动发现只返回严格同名且分布在 ≥2 个源的模型；人工配置过的聚合组始终返回（含异名成员），即使只剩 1 个源

### 4.25 保存聚合配置（CH-019 / CH-020）

- **路径**: `PUT /admin/api/model-groups?model={model_name}`
- **鉴权**: JWT
- **入参**:

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| upstreams | array | 是 | `[{upstream, model?, weight}]`，**顺序即候选优先级**，不可为空 |
| upstreams[].model | string | 否 | 该源里的真实模型名；**不填表示与聚合名同名**（纯同名聚合） |
| enabled | bool | 否 | 默认 true；false = 关闭聚合，退化为取第一个可用成员直连 |

- **出参**: `{ "ok": true, "model": "..." }`
- **错误码**: 400 model 缺失；404 上游源不存在；422 upstreams 为空

### 4.26 删除聚合配置（CH-019）

- **路径**: `DELETE /admin/api/model-groups?model={model_name}`
- **鉴权**: JWT
- **行为**: 删除人工配置，该聚合名回到自动发现
- **出参**: `{ "ok": true, "model": "..." }`

### 4.26.1 异名聚合建议（CH-020）

- **路径**: `GET /admin/api/model-groups/suggestions`
- **鉴权**: JWT
- **行为**: 按「去 `provider/` 前缀 → 转小写 → `.` `_` 视为 `-` → 压缩重复分隔符」归一化模型名，聚类出**疑似同一模型**
- **过滤条件**: 分布在 ≥2 个源、成员名不完全相同、尚未人工配置
- **出参**:

```json
{
  "suggestions": [
    {
      "suggested_name": "deepseek-v4-1-flash",
      "normalized": "deepseek-v4-1-flash",
      "members": [
        {"upstream": "buddy", "upstream_name": "Buddy 池", "model": "buddy/deepseek-v4.1-flash"},
        {"upstream": "loomy", "upstream_name": "Loomy 池", "model": "loomy/DeepSeek-V4.1-Flash"},
        {"upstream": "trae",  "upstream_name": "Trae 池",  "model": "trae/deepseek-v4.1-flash"}
      ]
    }
  ]
}
```

- **用法**: 前端「一键合并」直接调 `PUT /admin/api/model-groups?model={suggested_name}`，把 `members` 原样作为 `upstreams` 提交

### 4.26.2 某源已配置模型（CH-020）

- **路径**: `GET /admin/api/model-groups/source-models?upstream={upstream_id}`
- **鉴权**: JWT
- **出参**: `{ "upstream": "buddy", "models": [{"name": "buddy/deepseek-v4.1-flash", "enabled": true}] }`
- **用途**: 「添加异名成员」时下拉选择该源的真实模型名
- **错误码**: 404 上游源不存在

### 4.26.3 聚合组探测配置列表（CH-021）

- **路径**: `GET /admin/api/model-groups/probe-configs`
- **鉴权**: JWT
- **出参**:

```json
{ "configs": {
    "deepseek-v4-1-flash": {
      "model": "deepseek-v4-1-flash", "configured": true, "enabled": true,
      "interval_seconds": 30, "slow_threshold_seconds": 4, "sort_mode": "latency",
      "schedule": {"mode": "window", "days": [1,2,3,4,5], "windows": [{"start":"08:00","end":"23:00"}]},
      "member_count": 3,
      "raw": {"enabled": true, "interval_seconds": 30, "slow_threshold_seconds": 4,
              "sort_mode": "latency", "schedule": {"..."}}
    }
} }
```

- **说明**: `configured=false` 表示该组无人工探测配置（各字段为全局继承值）；`raw` 为落库原值（用于编辑回显，区分"显式设置"与"继承"）

### 4.26.4 保存聚合组探测配置（CH-021）

- **路径**: `PUT /admin/api/model-groups/probe?model={model_name}`
- **鉴权**: JWT
- **入参**:

```json
{ "enabled": true, "interval_seconds": 30, "slow_threshold_seconds": 4,
  "sort_mode": "stable|latency",
  "schedule": {"mode": "always|window", "days": [1,2,3,4,5],
               "windows": [{"start": "08:00", "end": "23:00"}]} }
```

- **校验**:
  - `interval_seconds`：`null` 或 `0` 表示跟随全局；否则 ≥ 10
  - `slow_threshold_seconds`：`null` 或 `0` 表示跟随全局；否则 ≥ 1
  - `sort_mode`：`stable` / `latency`
  - `schedule.mode`：`always` / `window`；窗口 `start` 与 `end` 必须同时存在且不相同（支持跨夜）
- **出参**: `{ "ok": true, "model": "deepseek-v4-1-flash" }`
- **错误码**: 400 model 缺失 / 404 聚合组不存在 / 422 参数非法

### 4.26.5 删除聚合组探测配置（CH-021）

- **路径**: `DELETE /admin/api/model-groups/probe?model={model_name}`
- **鉴权**: JWT
- **说明**: 删除后该组回到"不探测"，全局探测不受影响
- **出参**: `{ "ok": true, "model": "..." }`

### 4.26.6 全局探测计划（CH-021 / CH-023）

- **路径**: `GET /admin/api/model-groups/probe-plan`（兼容保留） / `GET /admin/api/probe-plan`（推荐）
- **鉴权**: JWT
- **出参**:

```json
{ "summary": { "unit_count": 12, "member_refs": 16, "dedup_saved": 4,
               "daily_requests": 17280, "global_interval": 360, "aggregation_count": 8 },
  "units": [
    { "key": "buddy:deepseek-v4.1-flash", "upstream": "buddy", "upstream_name": "Buddy",
      "model": "deepseek-v4.1-flash",
      "groups": ["deepseek-v4-1-flash", "smart-latest"],
      "group_kinds": {"deepseek-v4-1-flash": "static", "smart-latest": "rule"},
      "sources": ["group"],
      "interval": 60,
      "schedule": {"mode": "window", "days": [1,2,3,4,5], "windows": [{"start":"08:00","end":"23:00"}]},
      "schedules": [{"mode": "window", "..."}],
      "latency": 1.2, "status": "ok", "last_check": 1792228899,
      "stale": false, "active_now": true } ] }
```

- **说明**:
  - 探测单元 = `(上游源, 该源真实模型名)`，**全局唯一**；聚合只引用不拥有
  - 多聚合引用同一单元时 `interval` 取最小值；`daily_requests = Σ(86400/interval)`
  - `groups` 含 **rule 聚合**（其探测对象 = 所有规则候选并集），`group_kinds` 区分 `static` / `rule`
  - `schedules` 为各引用聚合的生效时段；仅一个时 `schedule` 与其相同，多个时 `schedule` 回退 `{"mode":"always"}`（实际判定按并集，见 `active_now`）
  - `active_now=false` 表示当前处于该单元探测时段之外
  - `stale=true` 表示 `last_check` 超过 `3 × interval` 未更新

### 4.28 统一聚合（CH-023）

#### 4.28.1 聚合列表

- **路径**: `GET /admin/api/aggregations`
- **鉴权**: JWT
- **出参**:

```json
{ "aggregations": [
  { "name": "deepseek-v4-1-flash", "kind": "static", "enabled": true, "configured": true,
    "members": [{"upstream":"buddy","model":"deepseek-v4.1-flash","weight":3}],
    "groups": ["premium"],
    "member_count": 3, "template_id": 1, "template_name": "高频-交易时段",
    "probe": { "enabled": true, "interval_seconds": 60, "slow_threshold_seconds": 5,
               "sort_mode": "latency", "schedule": {"mode":"window","..."},
               "template_id": 1, "template_name": "高频-交易时段" },
    "self_config": { "probe_enabled": true, "interval_seconds": 60,
                     "slow_threshold_seconds": 5.0, "sort_mode": "latency", "schedule": {"..."} },
    "remark": "" },
  { "name": "smart-latest", "kind": "rule", "members": [], "member_count": 7,
    "rule_names": ["默认对话", "视觉理解"],
    "rule_bindings": [{"rule": "默认对话", "candidates": null},
                      {"rule": "视觉理解", "candidates": [{"upstream":"buddy","model":"gemini-2.5-pro"}]}],
    "rule_binding_summary": {"rule_count": 2, "candidate_count": 3,
      "items": [{"rule":"默认对话","count":2,"follow_all":true},
                {"rule":"视觉理解","count":1,"follow_all":false}]},
    "stale_bindings": [] } ] }
```

- **说明**:
  - `kind=static`：固定成员，`members` 为候选链路
  - `kind=rule`：候选由路由规则运行时匹配，`members` 恒空，`member_count` 为**按绑定裁剪后**的候选展开单元数
  - `configured=false`：未人工配置、由同名模型自动发现
  - `groups`（CH-034）：聚合自身可用分组，空数组 = 所有 Key 可用。**static 与 rule 同一语义**，成员所属上游源的分组不参与聚合权限判断
  - `probe` 为**生效值**（模板优先 → 自配 → 全局）；`self_config` 为落库原值（编辑回显用）
  - `rule_bindings`（CH-024，仅 rule）：`null`/`[]` = 全跟随（所有规则、全部候选）；`[{"rule","candidates"}]` 中 `candidates=null` 表示该规则候选全跟随，数组表示显式候选子集
  - `rule_binding_summary`：卡片摘要（规则数 / 候选数 / 每条规则明细）
  - `stale_bindings`：失效项（规则已删除 `rule_missing` / 候选已移出规则 `candidate_missing`），供 UI 提示

#### 4.28.2 新建 / 更新聚合

- **路径**: `PUT /admin/api/aggregations?name={聚合名}`
- **鉴权**: JWT
- **入参**（均可选，未提供则保持原值）:

```json
{ "kind": "static|rule", "members": [{"upstream":"buddy","model":"deepseek-v4.1-flash","weight":3}],
  "rule_bindings": [{"rule":"默认对话","candidates":null},
                    {"rule":"视觉理解","candidates":[{"upstream":"buddy","model":"gemini-2.5-pro"}]}],
  "groups": ["premium"],
  "enabled": true,
  "probe_enabled": true, "template_id": 1,
  "sort_mode": "stable|latency", "interval_seconds": 60, "slow_threshold_seconds": 5,
  "schedule": {"mode":"always|window","days":[1,2,3,4,5],"windows":[{"start":"08:00","end":"23:00"}]},
  "remark": "" }
```

- **语义**:
  - `template_id` / `interval_seconds` / `slow_threshold_seconds` 支持**显式 `null` 清空**（后端用 `model_fields_set` 区分「未提供」与「传 null」）
  - `kind=rule` 不允许传 `members`
  - `rule_bindings`（CH-024，仅 `kind=rule`）：同样支持显式 `null`/`[]` 清空（= 全跟随）
  - `rule_bindings[].rule` 必须存在于当前规则表（否则 404）；`candidates` 里的 `{upstream, model}` 必须属于该规则的候选（否则 400）；规则候选列表为空时不允许绑定（400）
  - `template_id` 非空时必须存在
  - `groups`（CH-034）：聚合可用分组数组；空数组 / 未提供 = 所有 Key 可用。传入的分组名必须存在于分组表（否则 404）。**static 与 rule 均适用**
- **错误码**: 400 name/kind 缺失或 rule 传成员 / 404 上游源、模板或分组不存在

#### 4.28.3 删除聚合

- **路径**: `DELETE /admin/api/aggregations?name={聚合名}`
- **出参**: `{ "ok": true, "name": "..." }`
- **错误码**: 404 聚合不存在
- **CH-033 语义扩展**：
  - 人工配置的聚合（`agg_unified` 有行）→ 直接删行，恢复为「自动发现」状态（若同名模型仍分布在 ≥2 个源）
  - **自动发现的聚合**（无库行，由 `collect_group_members()` 即时推导）→ 落库一条 `enabled=false` 且成员为空的 static 行，语义为「关闭该聚合」；该聚合随后从列表、路由候选、探测计划中消失
  - 该操作**可逆**：对关闭后的聚合调用 `PUT /admin/api/aggregations?name=xxx` 传 `enabled=true` 与成员即可恢复
  - 重复删除同一自动发现聚合仍返回 200（幂等）

#### 4.28.3.1 保存聚合列表顺序（CH-028）

- **路径**: `PUT /admin/api/aggregations/order`
- **鉴权**: JWT
- **入参**:

```json
{ "names": ["deepseek-v4-1-flash", "smart-chat", "glm-4.6"] }
```

- **出参**: `{ "ok": true, "count": 3 }`
- **语义**:
  - 顺序存 `sys_setting.aggregation_order`（JSON 数组），**不改 `agg_unified` 表结构**
  - 数组中不存在的聚合名会被过滤（防止删除后残留脏数据）
  - 未列入数组的聚合（新增 / 自动发现）在列表末尾按 `kind + name` 排序
  - 传空数组 = 恢复默认顺序（`kind + name`）
  - 自动发现的聚合（`configured=false`，不在 `agg_unified` 中）也可参与排序
- **错误码**: 401 未鉴权

#### 4.28.4 rule 聚合的探测对象（CH-024）

- **路径**: `GET /admin/api/aggregations/rule-units?name={聚合名}`（`name` 可选，CH-024）
- **鉴权**: JWT
- **出参**: `{ "units": [{"upstream":"buddy","model":"deepseek-v4-1-flash","upstream_name":"Buddy"}], "aggregation": "smart-latest" }`
- **说明**:
  - 传 `name`：返回**该聚合按 `rule_bindings` 裁剪后**的候选展开并集
  - 不传 `name`：返回所有路由规则候选展开后的并集（旧行为，聚合名形式的候选已展开为各源真实模型名）

### 4.29 探测模板（CH-023）

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/admin/api/probe-templates` | 列表，含 `ref_count` / `ref_names` |
| POST | `/admin/api/probe-templates` | 新建 |
| PUT | `/admin/api/probe-templates/{id}` | 更新 |
| DELETE | `/admin/api/probe-templates/{id}` | 删除，返回 `affected`（受影响聚合名） |

**入参**:

```json
{ "name": "高频-交易时段", "interval_seconds": 60, "slow_threshold_seconds": 5,
  "sort_mode": "latency",
  "schedule": {"mode":"window","days":[1,2,3,4,5],"windows":[{"start":"08:00","end":"23:00"}]},
  "remark": "" }
```

- **校验**: `name` 非空且唯一；`interval_seconds ≥ 10`；`slow_threshold_seconds` 为 `null`/`0` 表示跟随全局，否则 ≥ 1；`sort_mode ∈ {stable, latency}`
- **删除语义**: 引用方 `template_id` 置空，回退到自配 → 全局；聚合本身不删
- **错误码**: 400 重名 / 404 模板不存在

### 4.27 用量汇总（CH-019）

- **路径**: `GET /admin/api/usage/summary?range=today|7d|30d`
- **鉴权**: JWT
- **出参**:

```json
{ "total": 128, "success_count": 125, "success_rate": 0.9766, "total_tokens": 456789, "active_keys": 3,
  "filtered_count": 4,
  "top_errors": [{ "target": "dsh/deepseek-v4-flash", "count": 2 }] }
```

- **说明**: `success_rate` 在无请求时为 `null`；`top_errors` 取错误数 Top5；`filtered_count` 为被请求过滤引擎拦截的请求数（CH-041，这些请求未发往任何上游）

### 4.28 用量按模型聚合（CH-019）

- **路径**: `GET /admin/api/usage/by-model?range=today|7d|30d`
- **出参**: `{ "models": [{ "model", "requests", "success_count", "error_count", "prompt_tokens", "completion_tokens", "total_tokens", "avg_duration_ms", "upstream_count" }] }`（按 total_tokens 降序，最多 200 条）

### 4.28.1 用量按单元聚合（CH-021）

- **路径**: `GET /admin/api/usage/by-unit?range=today|7d|30d`
- **鉴权**: JWT
- **出参**:

```json
{ "units": [
   { "upstream_id": "buddy", "upstream_name": "Buddy",
     "upstream_model": "deepseek-v4.1-flash",
     "requests": 320, "success_count": 318, "error_count": 2, "request_models": 3,
     "prompt_tokens": 900000, "completion_tokens": 350000, "total_tokens": 1250000,
     "avg_duration_ms": 2100, "last_ts": 1792228899 } ] }
```

- **说明**:
  - 维度是「上游源 × 上游真实模型名」，用于号池/积分消耗核算
  - `upstream_model` 取 `COALESCE(upstream_model, model)`：CH-021 之前的老数据没有真实模型名，回退用请求名，避免整行丢失
  - `request_models` = 该单元被多少个不同的客户端请求名命中（异名聚合的关联度指标）
  - 按 total_tokens 降序，最多 500 条

### 4.29 用量按 Key 聚合（CH-019）

- **路径**: `GET /admin/api/usage/by-key?range=today|7d|30d`
- **出参**: `{ "keys": [{ "api_key_id", "api_key_name", "requests", "success_count", "error_count", "total_tokens", "avg_duration_ms" }] }`

### 4.30 用量明细（CH-019 / CH-038）

- **路径**: `GET /admin/api/usage/logs?range=today|7d|30d&page=1&size=50&key_id=&model=&status=success|error|filtered`
- **出参**: `{ "total": 128, "page": 1, "size": 50, "items": [ ...log_usage 行... ] }`（按 id 倒序）
- **CH-038 增量**: 每行补 `cache_read_tokens` / `cache_write_tokens` / `attempt_count`（旧库缺列时给 0 / 0 / 1）。**只增不改**，原有字段全部保留。
- **CH-041 增量**: `status=filtered` 筛选被请求过滤引擎拦截的记录（`error_msg LIKE '【已过滤】%'`）

### 4.30.1 单条请求详情（CH-038）

- **路径**: `GET /admin/api/usage/logs/{log_id}`
- **鉴权**: JWT
- **出参**:

```json
{
  "id": 12345,
  "summary": {
    "ts": 1792419416.5, "status": "success", "http_status": 200,
    "protocol": "chat", "stream": 1,
    "model": "deepseek-v4-1-flash", "upstream_model": "deepseek-v4.1-flash",
    "upstream_id": "buddy", "upstream_name": "Buddy", "api_key_name": "trae",
    "prompt_tokens": 60531, "cache_read_tokens": 50845, "cache_write_tokens": 0,
    "completion_tokens": 379, "total_tokens": 60910, "estimated": 0,
    "duration_ms": 352, "first_token_ms": 180, "attempt_count": 1,
    "error_msg": null
  },
  "attempts": [
    { "upstream": "buddy", "model": "deepseek-v4.1-flash",
      "http_status": 200, "ms": 352, "error": null }
  ],
  "detail": {
    "available": true,
    "request_headers": { "user-agent": "...", "content-type": "application/json" },
    "request_body": "{...}",
    "forward_body": "{...}",
    "response_body": "{...}",
    "truncated": { "request_body": false, "forward_body": false, "response_body": true }
  }
}
```

- **说明**:
  - 三栏语义：`request_body` = 客户端原始请求；`forward_body` = 实际发给上游的报文（含模型替换、`developer→system` 等改写）；`response_body` = 上游响应（流式只存首尾各 20 条片段）
  - `detail.available=false` 时带 `reason`：未采集（成功请求 + `error_only` 模式）或早于功能上线
  - `truncated` 标记哪一栏发生过截断（超过 `usage_detail_max_bytes`，保留头 3/4 + 尾 1/4）
  - 报文已脱敏（`sk-xxxx` → `sk-xxxx****`），请求头只保留白名单字段
  - `attempts` 为尝试链，长度与 `summary.attempt_count` 一致
  - 400：`log_id` 不存在；401：无有效 JWT

### 4.30.2 详情采集策略（CH-038）

- **路径**: `GET /admin/api/config/usage-detail`
- **出参**: `{ "mode": "error_only", "max_bytes": 1048576, "retention_days": 14 }`

- **路径**: `PUT /admin/api/config/usage-detail`
- **入参**: `{ "mode": "off|error_only|all", "max_bytes": 1048576, "retention_days": 14 }`
  - `max_bytes` 可选，范围 1024 ~ 1048576
  - `retention_days` 可选，范围 1 ~ 3650（UI 提供 7/14/30/90）
- **出参**: `{ "ok": true }`
- **错误**: 非法枚举或越界值 → 422

### 4.31 手动落库用量缓冲（CH-019，调试用）

- **路径**: `POST /admin/api/usage/flush`
- **出参**: `{ "ok": true }`

### 4.32 运行日志读取（CH-025）

- **路径**: `GET /admin/api/logs?lines={N}&keyword={关键词}`
- **鉴权**: JWT
- **说明**: 读取轮转日志文件（`logs/smart-router.log`）尾部，供不登录服务器也能拿到出错现场
- **参数**:
  - `lines`：返回行数，默认 200，上限 5000
  - `keyword`：非空时只返回含该子串的行（如 `INVALID`、`status=500`、`ERROR`）
- **出参**:

```json
{ "ok": true, "file": "/opt/smart-router/backend/logs/smart-router.log",
  "size_bytes": 33819, "returned": 3, "keyword": "",
  "content": "2026-10-18 12:48:51 [WARNING] access: POST /v1/chat/completions status=400 ..." }
```

- **日志内容说明**（CH-025 新增的请求上下文）:

| 字段 | 含义 |
|------|------|
| `status` / `elapsed` | HTTP 状态码 / 耗时（秒） |
| `client` | 客户端 IP |
| `model` / `stream` | 请求的模型名 / 是否流式 |
| `messages` | 消息条数（非数组时不输出） |
| `body=INVALID(reason)` | 请求体无法解析，`reason` ∈ `empty` / `bad_json` / `not_object` |
| `body_snippet` | 请求体摘要（截断 300 字符，`sk-xxx` 已脱敏） |

- **文件策略**: `RotatingFileHandler`，单文件 10MB × 保留 5 份；可用环境变量 `SMART_ROUTER_LOG_DIR` 改目录

### 4.33 日志文件信息（CH-025）

- **路径**: `GET /admin/api/logs/info`
- **鉴权**: JWT
- **出参**: `{ "ok": true, "file": "...", "exists": true, "size_bytes": 33819 }`

### 4.34 请求过滤规则（CH-041）

转发前拦截：命中规则的候选**不会发往上游**，避免触发上游渠道按请求内容维护的客户端黑名单。

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/admin/api/filter-rules` | 规则列表 + 全局开关状态 |
| POST | `/admin/api/filter-rules` | 新建规则 |
| PUT | `/admin/api/filter-rules/{id}` | 更新规则 |
| DELETE | `/admin/api/filter-rules/{id}` | 删除规则 |
| PUT | `/admin/api/filter-rules/engine` | 切换全局开关 |
| POST | `/admin/api/filter-rules/test` | **试跑**：传入请求体，返回会命中哪些规则 |

**GET 出参**:

```json
{
  "enabled": false,
  "rules": [{
    "id": 1, "name": "DSH 身份声明", "enabled": false,
    "target": "system_first_line", "pattern": "You are an AI agent powered by DeepSeek Harness",
    "upstream_ids": [], "action": "skip", "remark": ""
  }],
  "targets": ["system_first_line", "system_any", "body_regex"],
  "actions": ["skip", "reject"]
}
```

**新建/更新入参**:

```json
{ "name": "DSH 身份声明", "enabled": true, "target": "system_first_line",
  "pattern": "powered by DeepSeek Harness", "upstream_ids": ["buddy"],
  "action": "skip", "remark": "" }
```

- **校验**: `name` 非空且唯一；`pattern` 非空；`target ∈ {system_first_line, system_any, body_regex}`；`action ∈ {skip, reject}`
- **`upstream_ids`**: 空数组 = 作用于**全部上游源**
- **`engine`**: `{ "enabled": true|false }`，默认 `false`
- **`test` 入参/出参**:

```json
// 请求
{ "body": { "model": "x", "messages": [...] }, "upstream_ids": ["buddy", "trae"] }

// 响应
{ "engine_enabled": true, "matched": true,
  "results": [{ "upstream": "buddy", "rules": [{ "id": 1, "name": "DSH 身份声明", "action": "skip" }] }],
  "enabled_rule_count": 1 }
```

- **错误码**: 400 重名 / 404 规则不存在
- **运行时行为**（上游转发层的可观察结果）：

| 场景 | HTTP | 说明 |
|---|---|---|
| 聚合候选命中，仍有剩余候选 | 200（正常转发） | 静默跳过命中的成员，客户端无感 |
| 聚合候选全部命中 | 503 | 消息列明规则名与被过滤的源 |
| 单模型直连命中 | **400** | 不偷偷换源，消息说明命中规则 |
| 引擎关闭 / 规则空 / 未命中 | 不变 | 与未启用该功能时完全一致 |

### 4.6 路由规则列表

- **路径**: `GET /admin/api/rules`
- **鉴权**: JWT
- **出参**:

```json
{ "rules": [ { "name": "视觉理解", "match": { "has_image": true }, "candidates": [ { "model": "...", "upstream": "newapi", "weight": 5, "priority": 1, "max_context": 1000000, "max_output": 32768 } ] } ] }
```

### 4.7 保存路由规则

- **路径**: `PUT /admin/api/rules`
- **鉴权**: JWT
- **入参**: `{ "rules": [...] }`（同上格式）
- **出参**（CH-024）: `{ "ok": true, "affected_aggregations": ["smart-latest"] }`
- **说明**: 保存后自动清理引用已删除/改名规则的聚合绑定（`prune_rule_bindings`）；清理后绑定为空则回退全跟随。`affected_aggregations` 为被清理的聚合名，供前端提示

### 4.8 聚合模型名（CH-023 起为兼容入口）

- **路径**: `GET /admin/api/aggregated-names`
- **鉴权**: JWT
- **出参**: `{ "names": ["smart-latest", "smart-chat", "auto-chat"] }`
- **说明**: 返回 `agg_unified` 中 `kind=rule` 且启用的聚合名；等价于 `GET /admin/api/aggregations` 按 `kind` 过滤

- **路径**: `PUT /admin/api/aggregated-names`
- **鉴权**: JWT
- **入参**: `{ "names": ["smart-latest", "auto-chat"] }`
- **说明**: 整体替换 rule 聚合集合（新增的建行、移除的删行），保留已有探测配置

### 4.9 模型别名列表

- **路径**: `GET /admin/api/model-pointers`
- **鉴权**: JWT
- **出参**: `{ "pointers": [ { "name": "my-model", "target_model": "deepseek-ai/deepseek-v4-pro", "upstream": "newapi" } ] }`

### 4.10 添加模型别名

- **路径**: `POST /admin/api/model-pointers`
- **鉴权**: JWT
- **入参**:

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| name | string | 是 | 别名名称（唯一） |
| target_model | string | 是 | 目标模型 |
| upstream | string | 否 | 上游源 ID，默认 default_upstream |

- **错误码**: 400 别名已存在

### 4.11 修改别名指向

- **路径**: `PUT /admin/api/model-pointers/{name}`
- **鉴权**: JWT
- **入参**: `{ "target_model": "...", "upstream": "..." }`
- **错误码**: 404 别名不存在

### 4.12 删除别名

- **路径**: `DELETE /admin/api/model-pointers/{name}`
- **鉴权**: JWT
- **错误码**: 404 别名不存在

### 4.13 API Key 列表

- **路径**: `GET /admin/api/api-keys`
- **鉴权**: JWT
- **出参**:

```json
{ "api_keys": [ { "name": "默认 Key", "key": "sk-your-key", "key_masked": "sk-y***_key", "enabled": true, "groups": ["free"] } ] }
```

> key 为完整值（管理后台显示用），key_masked 为脱敏值

### 4.14 添加 API Key

- **路径**: `POST /admin/api/api-keys`
- **鉴权**: JWT
- **入参**:

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| name | string | 是 | 名称 |
| key | string | 是 | 密钥值 |
| groups | array | 否 | 可访问分组，默认 ["free"] |
| enabled | boolean | 否 | 是否启用，默认 true |

- **错误码**: 400 密钥已存在

### 4.15 更新 API Key

- **路径**: `PUT /admin/api/api-keys/{key_value}`
- **鉴权**: JWT
- **入参**: `{ "enabled": false, "groups": ["free", "premium"] }`
- **错误码**: 404 密钥不存在

### 4.16 删除 API Key

- **路径**: `DELETE /admin/api/api-keys/{key_value}`
- **鉴权**: JWT
- **错误码**: 404 密钥不存在

### 4.17 配置项 - 延迟探测

- **路径**: `GET /admin/api/config/probe`
- **路径**: `PUT /admin/api/config/probe`
- **鉴权**: JWT
- **配置字段**: enabled/interval_seconds/timeout_seconds/request_text/max_tokens/base_latency/down_threshold_seconds/slow_threshold_seconds/error_as_down

### 4.18 配置项 - 重试

- **路径**: `GET /admin/api/config/retry`
- **路径**: `PUT /admin/api/config/retry`
- **鉴权**: JWT
- **配置字段**: max_attempts/response_timeout/first_chunk_timeout

### 4.18.1 配置项 - 智能重试（CH-012）

- **路径**: `GET /admin/api/config/smart-retry`
- **路径**: `PUT /admin/api/config/smart-retry`
- **鉴权**: JWT
- **出参**（GET）:

```json
{ "extra_attempts": 2, "backoff_ms": [500, 1500], "jitter": 0.2 }
```

- **入参**（PUT）: 同上结构，字段均可选，未提供的字段沿用缺省值（后端与默认值合并返回）
- **字段说明**:

| 字段 | 类型 | 默认 | 说明 |
|------|------|------|------|
| extra_attempts | int | 2 | 在 Key 数之外追加的尝试次数（总预算 = Key 数 + 该值） |
| backoff_ms | int[] | [500, 1500] | 同一 Key 重试前的退避毫秒序列，超出长度取最后一项 |
| jitter | float | 0.2 | 退避抖动比例（±20%），0 表示不抖动 |

- **语义**:
  - 该组参数是**全局默认**，但只对「上游源开启 `smart_retry`」的源生效（源级开关见 4.x 上游源 CRUD 的 `smart_retry` 字段）
  - 开关关闭时：行为退化为基础换 Key 逻辑（仅 401/403/429/超时/连接异常换 Key）
  - 开关开启时：额外把 500/502/503/504 纳入可重试；同一 Key 重试前按 `backoff_ms` + `jitter` 退避
- **出参**（PUT）: `{"ok": true}`
- **存储**: `sys_setting` 键 `smart_retry`
- **错误码**: 401 未鉴权；422 参数类型非法

### 4.19 配置项 - 故障转移

- **路径**: `GET /admin/api/config/failover`
- **路径**: `PUT /admin/api/config/failover`
- **鉴权**: JWT
- **配置字段**: max_fails/cooldown_seconds

### 4.19b 配置项 - 同名模型自动聚合（CH-036）

- **路径**: `GET /admin/api/config/auto-aggregate`
- **路径**: `PUT /admin/api/config/auto-aggregate`
- **鉴权**: JWT
- **出参**: `{ "enabled": false }`
- **入参**: `{ "enabled": true }`
- **语义**: 控制「多个上游源都有同名模型时，是否自动当成一个聚合组」。
  - `false`（默认）：同名模型只做跨源兜底（`collect_model_upstreams()` 仍返回多候选），不出现在聚合列表、不作为聚合参与权限判断
  - `true`：恢复 CH-019 旧行为，同名分布 ≥2 个启用源时自动成为聚合组
- **存储**: `sys_setting.auto_same_name_aggregate`

### 4.20 修改管理员密码

- **路径**: `PUT /admin/api/admin-password`
- **鉴权**: JWT
- **入参**:

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| old_password | string | 是 | 当前密码 |
| new_password | string | 是 | 新密码（至少 6 位） |

- **错误码**: 400 当前密码错误
- **CH-049 起**：改密成功后，**所有已签发的旧 token 立即失效**（服务端比对 JWT 内的密码指纹 `pv` 与当前密码指纹），后续请求返回 401「密码已变更，请重新登录」。客户端应在改密成功后主动退出并重新登录。

### 4.20.1 JWT 鉴权语义（CH-049）

管理端接口统一要求 `Authorization: Bearer <token>`，401 有四种语义，客户端需按 `detail` 区分：

| detail | 含义 | 客户端应做 |
|--------|------|-----------|
| `Missing token` | 请求头没带 token | 清 token → 跳登录页 |
| `Invalid or expired token` | 签名不对或已过期 | 清 token → 跳登录页 |
| `密码已变更，请重新登录` | token 内的密码指纹与当前密码不符 | 清 token → 跳登录页 |
| `用户名或密码错误` | **仅登录接口**：账号或密码不对 | 提示原文，**不清 token、不跳转**（本来就在登录页） |


### 4.21 热重载配置

- **路径**: `POST /admin/api/reload`
- **鉴权**: JWT
- **出参**: `{ "ok": true, "message": "配置已重新加载" }`

### 4.22 分组列表

- **路径**: `GET /admin/api/groups`
- **鉴权**: JWT
- **出参**:

```json
{ "groups": [ { "name": "free", "description": "免费分组（默认）" }, { "name": "premium", "description": "付费分组" } ] }
```

### 4.23 保存分组列表

- **路径**: `PUT /admin/api/groups`
- **鉴权**: JWT
- **入参**:

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| groups | array | 是 | `[{name, description}]`，整体覆盖保存 |

- **错误码**: 400 被上游源或 API Key 引用的分组不可删除

### 4.24 数据导出（CH-042）

- **路径**: `GET /admin/api/export/{dataset}`（导出全部，受 query 筛选约束） / `POST /admin/api/export/{dataset}`（批量导出选中项）
- **鉴权**: JWT
- **响应**: 二进制 xlsx（`Content-Type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`），带 `Content-Disposition`（`filename*` 按 RFC 5987 编码，中文名不乱码）与 `Access-Control-Expose-Headers: Content-Disposition`
- **数据集清单**: `GET /admin/api/export/datasets`（返回 `{datasets: [...]}`，须声明在 `/export/{dataset}` 之前，否则被通配吃掉）

| dataset | 内容 | 支持的 query 筛选 |
|---|---|---|
| `pointers` | 模型别名 | `keyword` / `upstream` |
| `api-keys` | API Key（导出保留完整 Key） | `keyword` / `group` / `enabled` |
| `filter-rules` | 请求过滤规则 | `keyword` / `upstream` / `enabled` |
| `usage-by-model` | 用量-按模型 | `range` |
| `usage-by-unit` | 用量-按单元 | `range` |
| `usage-by-key` | 用量-按 Key | `range` |
| `usage-logs` | 请求明细（分页循环拉取，硬上限 20 万条） | `range` / `model` / `status` |
| `groups` | 分组 | — |
| `probe-templates` | 探测模板 | — |
| `probe-units` | 探测单元 | — |

- **批量导出入参**: `{ "ids": ["..."] }`，ids 为各数据集的主键字符串（`pointers` 用别名、`api-keys` 用名称、`usage-by-unit` 用 `upstream_id|upstream_model` 等）
- **错误码**: 404 未知数据集 / 400 批量导出未选任何记录
- **为何用 POST 传 ids**: 批量可能选中上百条，拼 URL 会超长
- **为何后端生成 xlsx**: 「导出 = 导出全部」，前端只能拿到当前页；且 xlsx 由标准库 `zipfile` 手写 OOXML（`core/xlsx_writer.py`），**不引入 openpyxl**，因为部署脚本只同步代码、不在服务器装依赖

---

## 五、需求 → API → 表 对应矩阵

| 需求功能点 | 涉及 API | 涉及表 |
|----------|---------|--------|
| 统一模型名智能路由 | POST /v1/chat/completions | rule_rule, rule_candidate, up_upstream |
| 上下文感知路由 | POST /v1/chat/completions | rule_candidate |
| 故障转移与自动重试 | POST /v1/chat/completions | （内存状态） |
| 别名固定转发 | POST /v1/chat/completions | pt_pointer |
| 指定模型直连 | POST /v1/chat/completions | up_upstream, rule_candidate |
| 多协议格式支持 | POST /v1/messages | up_upstream |
| 两层 Key 鉴权 | /v1/* | api_api_key |
| 后台登录认证 | POST /admin/api/login | sys_setting(admin) |
| 修改后台密码 | PUT /admin/api/admin-password | sys_setting(admin) |
| 系统概览 | GET /admin/api/dashboard | 多表聚合 |
| 密钥增删改查 | /admin/api/api-keys | api_api_key |
| 分组列表管理 | GET/PUT /admin/api/groups | sys_setting(groups) |
| 模型列表按 Key 过滤 | GET /v1/models | up_upstream(groups), api_api_key(groups) |
| 上游源增删查 | /admin/api/upstreams | up_upstream |
| 拉取模型列表 | GET /admin/api/upstreams/{id}/models（后端代理请求上游 `/v1/models`，非前端直连） | up_upstream |
| 规则可视化编辑 | GET/PUT /admin/api/rules | rule_rule, rule_candidate |
| 规则 YAML 编辑 | GET/PUT /admin/api/rules | rule_rule, rule_candidate |
| 别名增删改查 | /admin/api/model-pointers | pt_pointer |
| 延迟与健康状态 | GET /status | （内存状态） |
| 聚合名管理 | GET/PUT /admin/api/aggregated-names（兼容）；GET/PUT/DELETE /admin/api/aggregations | agg_unified（kind=rule） |
| rule 聚合规则绑定 | PUT /admin/api/aggregations（`rule_bindings`）；GET /admin/api/aggregations（`rule_bindings` / `rule_binding_summary` / `stale_bindings`） | agg_unified(rule_bindings) |
| 同名模型跨源聚合 | POST /v1/chat/completions（direct 多候选） | up_upstream(models) |
| 异名模型聚合 | POST /v1/chat/completions（聚合名 → 各源真实模型名） | agg_unified（kind=static, members） |
| 聚合配置与建议 | GET/PUT/DELETE /admin/api/model-groups（兼容）；GET/PUT/DELETE /admin/api/aggregations；GET .../suggestions；GET .../source-models | agg_unified |
| 聚合独立分组（门面权限） | PUT /admin/api/aggregations（`groups`）；GET /admin/api/aggregations（`groups`）；GET /v1/models 按聚合分组过滤 | agg_unified(groups), sys_setting(groups) |
| 聚合探测与排序配置 | PUT /admin/api/aggregations（probe_* / sort_mode / schedule / template_id）；GET /admin/api/model-groups/probe-configs（兼容） | agg_unified |
| 探测模板 | GET/POST /admin/api/probe-templates；PUT/DELETE /admin/api/probe-templates/{id} | agg_probe_template |
| 请求过滤规则 | GET/POST /admin/api/filter-rules；PUT/DELETE /admin/api/filter-rules/{id}；PUT /admin/api/filter-rules/engine；POST /admin/api/filter-rules/test | filter_rule |
| 探测计划与排班表 | GET /admin/api/probe-plan（兼容 .../model-groups/probe-plan）；GET /admin/api/aggregations/rule-units | agg_unified, agg_probe_template, sys_setting(latency_probe) |
| 单模型启用/禁用 | PATCH /admin/api/upstreams/{id}/models | up_upstream(models) |
| 模型顺序重排 | PUT /admin/api/upstreams/{id}/models/order | up_upstream(models) |
| 用量三层统计 | GET /admin/api/usage/summary\|by-model\|by-key\|logs | log_usage |
| 用量按单元（号池核算） | GET /admin/api/usage/by-unit | log_usage(upstream_model) |
| 请求详情（三栏报文 + 尝试链） | GET /admin/api/usage/logs/{log_id} | log_usage, log_usage_detail |
| 详情采集与保留策略 | GET/PUT /admin/api/config/usage-detail | sys_setting(usage_detail_mode/max_bytes/retention_days) |
| 延迟探测参数配置 | GET/PUT /admin/api/config/probe | sys_setting |
| 重试参数配置 | GET/PUT /admin/api/config/retry | sys_setting |
| 智能重试全局参数 | GET/PUT /admin/api/config/smart-retry | sys_setting(smart_retry) |
| 故障转移参数配置 | GET/PUT /admin/api/config/failover | sys_setting |
| 同名模型自动聚合开关 | GET/PUT /admin/api/config/auto-aggregate | sys_setting(auto_same_name_aggregate) |
| 配置热重载 | POST /admin/api/reload | 全表 |

## 六、变更记录

| 日期 | 变更内容 | 变更人 |
|------|---------|--------|
| 2026-08-09 | 初始创建（基于 v4 现有接口梳理，管理接口路径不变） | AI+用户 |
| 2026-08-10 | CH-008：新增 4.22/4.23 分组管理接口；/v1/models 增加按 Key 分组过滤说明 | AI+用户 |
| 2026-08-10 | CH-012：上游源新增 smart_retry 开关字段；新增 GET/PUT /admin/api/config/smart-retry 全局参数；成功响应新增 X-Served-By / X-Retry-Count 响应头 | AI+用户 |
| 2026-08-11 | CH-009/010：新增入站端点 POST /v1/messages（Anthropic 格式，兼容 x-api-key 鉴权）与 POST /v1/responses（Responses 格式，Codex 可用）；内部统一 openai chat 中间格式，双向自动转换（含流式），3×3 协议矩阵收齐 | AI+用户 |
| 2026-08-12 | CH-018：三入站错误统一为各协议标准格式；messages/responses 入站补图片块映射（image/input_image → image_url）；推理模型 reasoning 映射（anthropic thinking / responses reasoning item）；新增 2.3 Responses 契约章节 | AI+用户 |
| 2026-10-16 | CH-019：新增 4.7.3 单模型启停、4.7.4 模型重排、4.24~4.26 同名聚合组三端点、4.27~4.31 用量四端点+flush；/v1/models 过滤模型级禁用；503 错误信息带 `model@upstream` | AI+用户 |
| 2026-10-16 | CH-020：聚合组成员支持异名（`upstreams[].model`）；新增 4.26.1 归一化建议、4.26.2 某源已配置模型两端点；4.24/4.25 补充 `members` 字段说明 | AI |
| 2026-10-19 | CH-038：新增 4.30.1 单条请求详情（三栏报文 + 尝试链）、4.30.2 详情采集策略 GET/PUT；4.30 列表出参补 `cache_read_tokens` / `cache_write_tokens` / `attempt_count`（只增不改） | AI |
| 2026-10-21 | CH-041：新增 4.34 请求过滤规则（CRUD + 全局开关 + 试跑）；4.27 汇总补 `filtered_count`；4.30 明细支持 `status=filtered` 筛选；五列矩阵补「请求过滤规则」行 | AI |
| 2026-10-22 | CH-042：新增 4.24 数据导出 `GET/POST /admin/api/export/{dataset}` + `GET /admin/api/export/datasets`（10 个数据集，xlsx 由标准库手写 OOXML，零依赖） | AI |
