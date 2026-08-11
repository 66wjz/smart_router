# 变更：Responses 入站（POST /v1/responses，协议矩阵 · 入站第二块）

> 编号：CH-010
> 日期：2026-08-10
> 分类：B 线-大（新功能，走迷你 stage-1→5 流程）
> 状态：已实现（已部署生产 8.137.195.192:10002）
> 规划：[.devflow/PLAN-多协议与分组管理.md](../../.devflow/PLAN-多协议与分组管理.md) P2
> 关联：[CH-014](CH-014-responses出站适配.md)（出站转换器，本变更逆用）、[CH-009](CH-009-anthropic入站.md)（入站模式样板）

---

## 一、变更背景

3×3 协议矩阵最后一块：客户端（如 Codex 等使用 OpenAI Responses API 的工具）拿 Smart Router 的 API Key，以 Responses 格式调任意上游模型。

用户原话："最后我可能用 codex，这样发的请求就是 responses"——本变更覆盖该场景。

**内部中间语言 = OpenAI chat 格式**（与 CH-009 同模式）：responses 入站请求归一化为 openai chat → RouterService 全链路零改动 → 响应转回 Responses 格式。

## 二、详细设计

### 2.1 新端点

`POST /v1/responses`（新增 `api/v1/responses.py`，注册进 v1_router）。鉴权：`Authorization: Bearer`（Responses 客户端默认），中间件无需再改。

### 2.2 请求转换 Responses → openai chat

CH-014 出站转换器 `convert_request_openai_to_responses` 的**逆运算**（新写 `convert_request_responses_to_openai`）：

| Responses 字段 | openai chat 字段 |
|----------------|------------------|
| `instructions` | `messages[0]` role=system |
| `input[{type:"message", role}]` | 同 role message（input_text/output_text 块提取文本） |
| `input[{type:"function_call"}]` | assistant `tool_calls[]` |
| `input[{type:"function_call_output"}]` | role=tool message |
| `input` 为纯字符串 | 单条 user message |
| `max_output_tokens` | `max_tokens` |
| `tools[{type:"function",...}]` | openai `tools`（包回 function 层） |
| `temperature` / `top_p` / `stream` | 同名透传 |

### 2.3 响应转换 openai chat → Responses（非流式）

CH-014 `convert_response_responses_to_openai` 的逆运算：

- `choices[0].message.content` → `output:[{type:"message", role:"assistant", content:[{type:"output_text", text}]}]`
- `tool_calls` → `output:[{type:"function_call", call_id, name, arguments}]`
- usage 逆映射
- 包装 Responses 响应外壳（`id: resp_xxx`、`object: "response"`、`status: "completed"`、`created_at`）

### 2.4 流式转换 openai SSE → Responses SSE

按 CH-014 的映射表逆向，openai chunk 驱动事件序列：

```
response.created → response.output_item.added → response.output_text.delta(逐 delta)
→ response.output_item.done → response.completed(含 usage)
```

每个事件按 Responses SSE 规范输出 `event: xxx\r\ndata: {...}\r\n\r\n` 两行对。

### 2.5 边界

- ✅ 文本对话 + 流式 + 基础工具调用
- ⚠️ Responses API 规范仍在演进：reasoning 块、store/previous_response_id 等有状态字段不做（无状态透传），遇到降级忽略
- Codex 兼容性作为验收重点（用户的真实目标客户端）

## 三、影响面

| 层 | 文件 | 改动 |
|----|------|------|
| 后端 | `api/v1/responses.py`（新） | /v1/responses 端点 |
| 后端 | `upstream/responses_adapter.py` | 新增 3 个逆转换器（CH-014 文件上追加） |
| 后端 | `api/v1/router.py` | 注册路由 |

前端零改动。

## 四、验证

- 本地：Responses 格式请求 → openai mock 上游 → Responses 格式响应；流式事件序列合法（event/data 两行对）
- 生产实接：curl 模拟 Codex 请求 /v1/responses 调 deepseek（openai 上游）与 gpt-5.6-luna（responses 上游，同协议直通场景）
- compileall

## 五、实施记录（2026-08-11）

### 已实施

- `responses_adapter.py` 新增入站逆转换三件套：`convert_request_responses_to_openai`（instructions/input 字符串与数组两种形态/function_call 全映射）、`convert_response_openai_to_responses`、`OpenaiToResponsesSSE` 流式状态机（response.created → output_item.added → output_text.delta → output_item.done → response.completed）
- 新增 `api/v1/responses.py`：POST /v1/responses；v1/router.py 注册；鉴权复用 Bearer

### 验证（本地 mock 4 用例全过）

Codex 风格（instructions + input 字符串）非流式双向转换 ✅ / input 数组形态 ✅ / 流式五类 responses 事件齐全 ✅ / 无 Key 401 ✅

### 部署

`test/deploy_ch010_incremental.py`（3 后端文件）；生产 POST /v1/responses 与 /v1/messages 无 Key 均 401（路由注册成功）。**3×3 协议矩阵就此收齐**。

## 六、变更记录

| 日期 | 变更 | 变更人 |
|------|------|--------|
| 2026-08-10 | 初始创建（设计确认，排在 CH-009 后实施） | AI+用户 |
| 2026-08-11 | 实施完成 + 本地 4 用例验证 + 部署生产 | AI+用户 |
