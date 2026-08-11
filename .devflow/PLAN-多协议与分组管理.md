# 规划：分组管理 + 多协议统一输出

> 创建：2026-08-09（用户确认方案后固化，防止遗忘）
> 状态：已确认，分期实施中（P0 已开工，P1/P2 待排期）
> 流程：每个分期对应一个 CH 变更文档（docs/_changes/），走 B 线管控
> 关联：docs/_changes/CH-008-分组管理.md（P0）

---

## 一、背景

维护迭代阶段用户提出两项能力诉求：

1. **分组权限隔离**：上游源接入时归属某个分组；创建 API Key 时可选分组（多选）；该 Key 只能访问所属组的上游源。
   - 现状核实：核心隔离逻辑**已实现**（中间件注入 key_groups + 路由时 `_check_group` 403 / `allowed_groups` 过滤）。缺管理体验补强。
2. **多协议统一输出**：无论上游源是 openai / anthropic 哪种格式，客户端用 Smart Router 创建的 API Key，都能以 **OpenAI 兼容 / Anthropic 兼容 / Responses 兼容** 三种协议之一调用同一模型（如 deepseek-v4-flash）。

## 二、目标

- P0：分组可配置 + 模型列表按 Key 分组过滤 + 未分组默认行为明确
- P1：Anthropic 兼容入口 `POST /v1/messages`（非流式 + 流式）
- P2：Responses 兼容入口 `POST /v1/responses`（先非流式，后流式）

## 三、分期方案

### P0：分组管理（CH-008，小）

| 项 | 内容 |
|----|------|
| 分组数据源 | 新增"分组列表"配置（setting 表，JSON：`[{name, description}]`），取代写死的 free/premium |
| 管理接口 | `GET/PUT /admin/api/groups`（列表/整体保存）；上游源、API Key 的分组选项从分组管理动态加载 |
| 模型列表过滤 | `GET /v1/models` 按 `request.state.key_groups` 过滤上游模型（只展示有权访问组的上游） |
| 默认行为 | 未选分组的 API Key 默认 `["free"]`；管理端可选"不限制"（groups 含 `*`） |
| 迁移 | 存量数据（free/premium）自动纳入分组列表 |
| 验收 | 建 A 组上游 + 仅 A 组 Key → 能访问 A、不能访问 B；/v1/models 只显示 A 组模型 |

### P1：Anthropic 兼容（CH-009，中）

| 项 | 内容 |
|----|------|
| 入口 | `POST /v1/messages`（Anthropic 格式请求/响应） |
| 鉴权 | 中间件兼容 `x-api-key` header（Anthropic SDK 默认）与 `Authorization: Bearer` |
| 请求转换 | anthropic messages 格式 → 统一 openai chat 格式（逆写现有 `convert_request_openai_to_anthropic`） |
| 响应转换 | openai chat → anthropic messages 格式（逆写现有 `convert_response_anthropic_to_openai`） |
| 流式 | anthropic SSE 事件 ↔ openai SSE 互转（逆写 `convert_anthropic_sse_line_to_openai`） |
| 工具调用 | anthropic tool_use/tool_result ↔ openai tools 映射 |
| 复用 | 路由引擎 / 分组校验 / 重试 / Key 池 全部复用，零改动 |
| 验收 | Anthropic SDK 用 API Key 调 `/v1/messages`，deepseek-v4-flash（openai 上游）与 claude 类（anthropic 上游）均可用，流式/非流式、工具调用正常 |

### P2：Responses 兼容（CH-010，中高）

| 项 | 内容 |
|----|------|
| 入口 | `POST /v1/responses`（OpenAI Responses API 格式） |
| 请求转换 | `{model, input: [...]}` → openai chat 格式（input 文本/tool 消息映射） |
| 响应转换 | openai chat → Responses `{output: [{type: "message", content: [{type: "output_text", text}]}]}` |
| 流式 | Responses SSE 事件（response.created / response.output_text.delta / response.completed）从 openai SSE 转换 |
| 工具调用 | Responses function_call / function_call_output ↔ openai tools 映射 |
| 验收 | OpenAI SDK Responses 调用可用，非流式先行，流式后补 |

## 四、依赖与顺序

```
P0（分组管理） ── 独立，先行
P1（Anthropic） ── 依赖协议适配层骨架（请求归一化 + 响应序列化抽象）
P2（Responses） ── 复用 P1 的协议适配层骨架，新增第二套转换
```

> P1/P2 共用的"协议适配层"建议在 P1 落地时顺手抽象，P2 只加转换器不重改骨架。

## 五、风险

- P1/P2 流式事件映射复杂（事件边界、增量文本合并、结束事件），需专项测试
- Responses API 规范仍在演进（字段/事件可能变化）
- 测试矩阵：3 协议 × 流式/非流式 × openai/anthropic 上游 × 分组权限

## 六、流程管控要求

1. 每个分期先建 `docs/_changes/CH-XXX.md`，再动代码（B 线）
2. 实施后本地验证 + 前端 vue-tsc + 后端编译，再部署生产
3. 部署后生产实测关键链路，同步 `docs/变更记录.md` / `API契约.md` / `接口文档.md` / `_changes/README.md` / `.devflow/logs/ai-actions.md`
4. 用户体验确认后归档对应 CH，更新 STATE.md

## 七、分期状态

| 分期 | CH | 状态 | 备注 |
|------|----|------|------|
| P0 分组管理 | CH-008 | ✅ 已上线（2026-08-10 归档） | 生产运行中 |
| P1 Anthropic 兼容（入站） | CH-009 | ✅ 已上线（2026-08-11 归档） | /v1/messages + x-api-key 兼容 + 逆转换三件套 |
| P2 Responses 兼容（入站） | CH-010 | ✅ 已上线（2026-08-11 归档） | /v1/responses（Codex 场景）+ 逆转换三件套 |
| P3 模型级协议覆盖（出站） | CH-011 + CH-014 | ✅ 已上线（2026-08-10 归档） | CH-011 openai/anthropic 出站 + CH-014 responses 出站，出站三协议齐 |

> **P3 说明（2026-08-10 新增）**：P1/P2 是"入站"方向（客户端用什么协议调我们）；P3 是"出站"方向（我们用什么协议调上游）。动因：opencode 同站不同模型绑定不同协议/端点。设计见 [CH-011](../docs/_changes/archived/CH-011-模型级协议覆盖.md)（已归档）。
