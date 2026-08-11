# 变更：Anthropic 入站（POST /v1/messages，协议矩阵 · 入站第一块）

> 编号：CH-009
> 日期：2026-08-10
> 分类：B 线-大（新功能，走迷你 stage-1→5 流程）
> 状态：已实现（已部署生产 8.137.195.192:10002）
> 规划：[.devflow/PLAN-多协议与分组管理.md](../../.devflow/PLAN-多协议与分组管理.md) P1
> 关联：[CH-014](CH-014-responses出站适配.md)（同批协议矩阵）

---

## 一、变更背景

目标 3×3 协议矩阵：客户端可以用 Anthropic SDK / Claude Code 等 Anthropic 协议客户端，拿 Smart Router 的 API Key 调任意上游模型（包括 openai 协议的 deepseek 等）。

当前入站只有 `POST /v1/chat/completions`（OpenAI 格式）。本变更新增 Anthropic 格式入站。

**内部中间语言 = OpenAI chat 格式**：anthropic 入站请求归一化为 openai chat → 走现有 RouterService 全链路（路由/分组/Key 池/智能重试/出站协议分发全部零改动）→ 响应从 openai chat 转回 anthropic。

## 二、详细设计

### 2.1 新端点

`POST /v1/messages`（新增 `api/v1/messages.py`，注册进 v1_router）。

### 2.2 鉴权兼容（中间件改动）

`main.py` 的 `require_api_key` 中间件：`/v1/` 路径下除 `Authorization: Bearer` 外，**兼容 `x-api-key` header**（Anthropic SDK 默认鉴权方式）。两种 header 任一命中即通过，分组注入逻辑不变。

### 2.3 请求转换 anthropic → openai chat

现有出站转换器 `convert_request_openai_to_anthropic` 的**逆运算**（新写 `convert_request_anthropic_to_openai`）：

| anthropic 字段 | openai chat 字段 |
|----------------|------------------|
| `system`（字符串或块数组） | `messages[0]` role=system |
| `messages[role=user/assistant]` 文本块 | 同 role message（文本拼接） |
| `tool_use` 块 | assistant `tool_calls[]` |
| `tool_result` 块 | role=tool message（`tool_call_id`） |
| `max_tokens`（anthropic 必填） | `max_tokens` |
| `tools[]` | openai `tools[{type:function,...}]` |
| `stream` | 同名 |

转换后交给 `RouterService.chat_completions`（内部统一入口，零改动）。

### 2.4 响应转换 openai chat → anthropic

现有 `convert_response_anthropic_to_openai` 的**逆运算**（新写 `convert_response_openai_to_anthropic`）：

- `choices[0].message.content` → `content:[{type:"text", text}]`
- `tool_calls` → `content:[{type:"tool_use", id, name, input}]`
- usage 字段映射（`prompt_tokens`→`input_tokens` 等）
- 包装为 anthropic messages 响应（`id: msg_xxx`、`type: "message"`、`role: "assistant"`、`stop_reason`）

### 2.5 流式转换 openai SSE → anthropic SSE

RouterService 返回的是 openai SSE 流；入站层包一层生成器，逐 chunk 转 anthropic 事件序列：

```
message_start → content_block_start → content_block_delta(逐 delta) → content_block_stop → message_delta(stop_reason+usage) → message_stop
```

现有 `convert_anthropic_sse_line_to_openai` 的逆方向，按 openai chunk 的 delta 内容驱动状态机（首 chunk 发 message_start+content_block_start，文本 delta 发 content_block_delta，finish 时发收尾事件）。

### 2.6 与现有能力的关系（全部复用，零改动）

路由引擎、分组权限（key_groups 注入后 _check_group/allowed_groups 照常）、Key 池、智能重试（CH-012）、出站协议分发（CH-011/CH-014）——因为入站转换发生在 RouterService 之前。

### 2.7 边界

- ✅ 文本对话 + 流式 + 工具调用双向映射
- ⚠️ anthropic 的 thinking/cache_control 等进阶字段降级忽略
- 模型测试/管理端不变（管理端测试仍走 openai 中间格式）

## 三、影响面

| 层 | 文件 | 改动 |
|----|------|------|
| 后端 | `api/v1/messages.py`（新） | /v1/messages 端点：请求逆转换 → RouterService → 响应逆转换 |
| 后端 | `upstream/anthropic_adapter.py` | 新增 3 个逆转换器（请求/响应/SSE） |
| 后端 | `main.py` | 中间件兼容 x-api-key |
| 后端 | `api/v1/router.py` | 注册 messages 路由 |

前端零改动。

## 四、验证

- 本地：模拟 Anthropic SDK 请求（x-api-key 鉴权 + anthropic 格式体）→ openai mock 上游 → 返回 anthropic 格式响应；流式事件序列合法
- 分组权限：无权限分组的 Key 调 /v1/messages 被 403
- 生产实接：用 Anthropic SDK（或 curl 模拟）经 /v1/messages 调 deepseek（openai 上游）与 minimax（anthropic 上游）
- compileall

## 五、实施记录（2026-08-11）

### 已实施

- `anthropic_adapter.py` 新增入站逆转换三件套：`convert_request_anthropic_to_openai`（system/tool_use/tool_result/tools 全映射）、`convert_response_openai_to_anthropic`（含 stop_reason 逆映射）、`OpenaiToAnthropicSSE` 流式状态机（message_start → content_block_* → message_delta → message_stop）
- 新增 `api/v1/messages.py`：POST /v1/messages；`main.py` 中间件兼容 x-api-key；v1/router.py 注册
- 插曲：插入逆转换器时残留一行孤儿 return（编译期发现即修）

### 验证（本地 mock 4 用例全过）

x-api-key 鉴权+非流式双向转换 ✅ / 无 Key 401 ✅ / 流式六类 anthropic 事件齐全 ✅ / 分组越权 403 ✅

### 部署

`test/deploy_ch009_incremental.py`（4 后端文件，无 DB/前端变更）；生产 POST /v1/messages 无 Key 返回 401（路由注册成功，非 404）。

## 六、变更记录

| 日期 | 变更 | 变更人 |
|------|------|--------|
| 2026-08-10 | 初始创建（设计确认，排在 CH-014 后实施） | AI+用户 |
| 2026-08-11 | 实施完成 + 本地 4 用例验证 + 部署生产 | AI+用户 |
