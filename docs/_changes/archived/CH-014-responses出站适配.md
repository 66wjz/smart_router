# 变更：Responses 出站适配器（协议矩阵 · 出站第三协议）

> 编号：CH-014
> 日期：2026-08-10
> 分类：B 线-大（新功能，走迷你 stage-1→5 流程）
> 状态：已实现（已部署生产 8.137.195.192:10002，待用户体验确认后归档）
> 规划：[.devflow/PLAN-多协议与分组管理.md](../../.devflow/PLAN-多协议与分组管理.md) P3 第二期
> 关联：[CH-011](CH-011-模型级协议覆盖.md)（模型级协议机制）、[CH-012](CH-012-智能重试.md)（_RetryLoop 复用）

---

## 一、变更背景

opencode go 清单（19 模型）中 17 个已被 CH-011 覆盖（openai×11 + anthropic×7），剩 gpt-5.6-luna 走 `POST /zen/go/v1/responses`（OpenAI Responses API 格式），当前无出站适配器。用户点名要用该模型。

同时用户确认目标为**完整 3×3 协议矩阵**（入站 openai/anthropic/responses × 出站 openai/anthropic/responses），本变更是出站第三块拼图；入站两块见 CH-009 / CH-010。

**内部中间语言 = OpenAI chat 格式**（不变）：所有入站请求归一化为 openai chat，所有出站从 openai chat 转换。

## 二、详细设计

### 2.1 新适配器 `upstream/responses_adapter.py`

复用既有骨架：Key 池、`_RetryLoop`（智能重试自动生效）、`_build_endpoint(base_url, "/v1/responses")`、健康记录、X-Served-By/X-Retry-Count 响应头。

导出：`try_non_stream_responses` / `try_stream_responses` / `test_non_stream_responses` + 三个转换器。

### 2.2 请求转换 openai chat → Responses

| openai 字段 | Responses 字段 |
|------------|----------------|
| `messages[role=system]` | 合并到顶层 `instructions` 字符串 |
| `messages[role=user]` | `input[]`：`{type:"message", role:"user", content:[{type:"input_text", text}]}` |
| `messages[role=assistant]` | `input[]`：`{type:"message", role:"assistant", content:[{type:"output_text", text}]}` |
| `messages[role=tool]` | `input[]`：`{type:"function_call_output", call_id, output}` |
| assistant 的 `tool_calls[]` | `input[]`：`{type:"function_call", call_id, name, arguments}` |
| `max_tokens` | `max_output_tokens` |
| `temperature` / `top_p` / `stream` | 同名透传 |
| `tools[{type:function,function:{...}}]` | `tools[{type:"function", name, description, parameters}]`（拍平 function 层） |

多模态/未识别 content 结构：降级为提取文本，无法提取则跳过该块（不报错）。

### 2.3 响应转换 Responses → openai chat（非流式）

- `output[{type:"message"}].content[{type:"output_text"}].text` 拼接 → `choices[0].message.content`
- `output[{type:"function_call"}]` → `choices[0].message.tool_calls[]`（openai 格式）
- `usage.input_tokens/output_tokens` → `prompt_tokens/completion_tokens/total_tokens`
- `finish_reason` 固定 `stop`（有 tool_calls 时 `tool_calls`）

### 2.4 流式转换 Responses SSE → openai SSE

Responses 事件是 `event: xxx` + `data: {...}` 两行对；转换器按 `data:` 行的 `type` 字段分发：

| Responses 事件 | openai chunk |
|----------------|--------------|
| `response.created` | 首个 chunk（role: assistant） |
| `response.output_text.delta`（`delta` 字段） | `choices[0].delta.content` |
| `response.output_item.done`（function_call 项） | `choices[0].delta.tool_calls` |
| `response.completed`（含 usage） | `finish_reason: stop` + usage + `data: [DONE]` |
| `response.failed` / `error` | error chunk + `[DONE]` |
| 其他事件 | 跳过 |

首字节分界线不变：拿到首行才提交 StreamingResponse，之前失败可重试（_RetryLoop）；吐字后中断只关流。

### 2.5 分发与配置

| 位置 | 改动 |
|------|------|
| `services/router_service.py` `_forward` | `fmt == "responses"` 走新适配器 |
| `api/admin/upstreams.py` `test_upstream` | 同上（`test_non_stream_responses`） |
| `schemas/upstream.py` | `ALLOWED_MODEL_PROTOCOLS` 加 `"responses"` |
| `upstream/__init__.py` | 导出新函数 |
| 前端 `views/Upstreams.vue` | 模型协议下拉加 `responses` 选项；`api/upstreams.ts` ModelEntry 类型加 `'responses'` |

鉴权：Responses 端点用 `Authorization: Bearer`（与 openai 相同）。

### 2.6 边界

- ✅ 文本对话 + 流式 + 基础工具调用映射
- ⚠️ reasoning 块 / input_image 等多模态与进阶字段不做完整映射，降级忽略
- ❌ 入站 responses（客户端用 responses 调我们）→ CH-010，不在本变更

## 三、影响面

新增 1 文件（responses_adapter.py）；改动 5 处（router_service / admin upstreams / schemas / upstream `__init__` / 前端下拉）。对既有 openai/anthropic 路径零影响。

## 四、验证

- 本地 mock（扩展 `test/mock_flaky_upstream.py` 加 `/v1/responses` 非流式+流式 + 记录收到的请求体）：
  - 非流式：mock 断言收到的是 Responses 格式（有 `input`、无 `messages`）；返回 Responses 格式 → 客户端收到合法 openai chat 响应
  - 流式：mock 发 Responses SSE 事件序列 → 客户端收到合法 openai SSE（delta 文本 + [DONE]）
  - 智能重试联动：500×1 后成功，X-Retry-Count=1
  - 错误透传：400 不重试直接失败
- 生产实接：opencode 源 gpt-5.6-luna 标 responses，实测对话 + 流式
- compileall / vue-tsc / 构建

## 五、实施记录（2026-08-10）

### 已实施

- 新增 `upstream/responses_adapter.py`（约 520 行）：请求/响应/SSE 三个转换器 + 非流式/流式/管理端测试三个转发函数；复用 `_RetryLoop`（智能重试）与 Key 池
- 接入：router_service `_forward` 与 admin test 增加 `responses` 分发；`ALLOWED_MODEL_PROTOCOLS` 加 responses；包导出；前端模型协议下拉加第三项

### 验证结果（本地 mock /v1/responses 端到端）

| 用例 | 结果 |
|------|------|
| 非流式：mock 收到 Responses 格式（input/instructions/max_output_tokens），客户端收到合法 openai 响应（content+usage） | ✅ |
| 流式：Responses SSE → openai SSE（role chunk + delta 文本 + usage + [DONE]） | ✅ |
| 智能重试联动：500×1 → 200 + X-Retry-Count:1 + X-Served-By:smoke-resp/gpt-5.6-luna | ✅ |
| 管理端模型测试走 responses 分发 | ✅ |
| 400 不重试直接失败 | ✅ |
| compileall / vue-tsc / 构建 | ✅ |

插曲：首轮测试 PowerShell 剥引号导致请求体非法 JSON（500 在 request.json() 解析层，未到适配器），按铁律 2 看日志定位后改文件传参重跑通过——测试工具问题，非功能问题。

### 部署

`test/deploy_ch014_incremental.py`（新增适配器 + 4 个改动文件 + dist，无 DB 变更），active / GET 200 / 生产探测流量正常。

## 六、变更记录

| 日期 | 变更 | 变更人 |
|------|------|--------|
| 2026-08-10 | 初始创建（用户确认完整 3×3 矩阵目标，出站先行） | AI+用户 |
| 2026-08-10 | 实施完成 + 本地 5 用例验证通过 + 部署生产，待用户体验确认 | AI+用户 |
