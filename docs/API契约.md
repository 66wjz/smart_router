# Smart Router API 契约

> 创建时间：2026-08-09
> 状态：待确认
> 关联流程：fullstack-dev-flow stage-2
> 关联数据库设计：[docs/数据库设计.md](数据库设计.md)
> 版本：v5（保持 v4 管理 API 路径不变，兼容前端迁移）

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

```json
{
  "object": "list",
  "data": [
    { "id": "smart-latest", "object": "model", "owned_by": "smart-router", "context_length": 128000, "max_output": 65536 },
    { "id": "my-model", "object": "model", "owned_by": "smart-router", "type": "pointer", "target_model": "deepseek-ai/deepseek-v4-pro" },
    { "id": "mistralai/mistral-large-...", "object": "model" }
  ]
}
```

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
  "upstream_count": 2,
  "model_count": 12,
  "model_ok": 10,
  "model_down": 2,
  "rule_count": 3,
  "pointer_count": 3,
  "api_key_count": 3,
  "health": { "fails": {}, "cooldown": {} }
}
```

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

### 4.26.6 全局探测计划（CH-021）

- **路径**: `GET /admin/api/model-groups/probe-plan`
- **鉴权**: JWT
- **出参**:

```json
{ "summary": { "unit_count": 12, "member_refs": 16, "dedup_saved": 4,
               "daily_requests": 17280, "global_interval": 360 },
  "units": [
    { "key": "buddy:deepseek-v4.1-flash", "upstream": "buddy", "upstream_name": "Buddy",
      "model": "deepseek-v4.1-flash", "groups": ["deepseek-v4-1-flash"], "sources": ["group"],
      "interval": 60, "latency": 1.2, "status": "ok", "last_check": 1792228899,
      "stale": false, "active_now": true } ] }
```

- **说明**:
  - 探测单元 = `(上游源, 该源真实模型名)`，**全局唯一**；聚合组只引用不拥有
  - 多组引用同一单元时 `interval` 取最小值；`daily_requests = Σ(86400/interval)`
  - `active_now=false` 表示当前处于该单元探测时段之外
  - `stale=true` 表示 `last_check` 超过 `3 × interval` 未更新

### 4.27 用量汇总（CH-019）

- **路径**: `GET /admin/api/usage/summary?range=today|7d|30d`
- **鉴权**: JWT
- **出参**:

```json
{ "total": 128, "success_count": 125, "success_rate": 0.9766, "total_tokens": 456789, "active_keys": 3,
  "top_errors": [{ "target": "dsh/deepseek-v4-flash", "count": 2 }] }
```

- **说明**: `success_rate` 在无请求时为 `null`；`top_errors` 取错误数 Top5

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

### 4.30 用量明细（CH-019）

- **路径**: `GET /admin/api/usage/logs?range=today|7d|30d&page=1&size=50&key_id=&model=&status=success|error`
- **出参**: `{ "total": 128, "page": 1, "size": 50, "items": [ ...log_usage 行... ] }`（按 id 倒序）

### 4.31 手动落库用量缓冲（CH-019，调试用）

- **路径**: `POST /admin/api/usage/flush`
- **出参**: `{ "ok": true }`

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

### 4.8 聚合模型名

- **路径**: `GET /admin/api/aggregated-names`
- **鉴权**: JWT
- **出参**: `{ "names": ["smart-latest", "smart-chat", "auto-chat"] }`

- **路径**: `PUT /admin/api/aggregated-names`
- **鉴权**: JWT
- **入参**: `{ "names": ["smart-latest", "auto-chat"] }`

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

### 4.19 配置项 - 故障转移

- **路径**: `GET /admin/api/config/failover`
- **路径**: `PUT /admin/api/config/failover`
- **鉴权**: JWT
- **配置字段**: max_fails/cooldown_seconds

### 4.20 修改管理员密码

- **路径**: `PUT /admin/api/admin-password`
- **鉴权**: JWT
- **入参**:

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| old_password | string | 是 | 当前密码 |
| new_password | string | 是 | 新密码（至少 6 位） |

- **错误码**: 400 当前密码错误

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
| 拉取模型列表 | 前端直连上游 | up_upstream |
| 规则可视化编辑 | GET/PUT /admin/api/rules | rule_rule, rule_candidate |
| 规则 YAML 编辑 | GET/PUT /admin/api/rules | rule_rule, rule_candidate |
| 别名增删改查 | /admin/api/model-pointers | pt_pointer |
| 延迟与健康状态 | GET /status | （内存状态） |
| 聚合名管理 | GET/PUT /admin/api/aggregated-names | agg_aggregated_name |
| 同名模型跨源聚合 | POST /v1/chat/completions（direct 多候选） | up_upstream(models) |
| 异名模型聚合 | POST /v1/chat/completions（聚合名 → 各源真实模型名） | agg_model_group |
| 聚合配置与建议 | GET/PUT/DELETE /admin/api/model-groups；GET .../suggestions；GET .../source-models | agg_model_group |
| 聚合组独立探测 | GET/PUT/DELETE /admin/api/model-groups/probe*；GET .../probe-plan | agg_probe_config |
| 单模型启用/禁用 | PATCH /admin/api/upstreams/{id}/models | up_upstream(models) |
| 模型顺序重排 | PUT /admin/api/upstreams/{id}/models/order | up_upstream(models) |
| 用量三层统计 | GET /admin/api/usage/summary\|by-model\|by-key\|logs | log_usage |
| 用量按单元（号池核算） | GET /admin/api/usage/by-unit | log_usage(upstream_model) |
| 延迟探测参数配置 | GET/PUT /admin/api/config/probe | sys_setting |
| 重试参数配置 | GET/PUT /admin/api/config/retry | sys_setting |
| 故障转移参数配置 | GET/PUT /admin/api/config/failover | sys_setting |
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
