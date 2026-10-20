# CH-039 流式 usage chunk 按客户端意图透传

> 类型：A 线（bug —— 代码未按设计意图实现）
> 状态：已实现 + **已部署生产**（2026-10-20 00:20）；未提交、未推送（用户要求攒批次）
> 日期：2026-10-19
> 来源：用户反馈「接入 DSH（OpenAI 兼容）后能聊，但显示 `1轮1步 · 0 tok/s`、上下文 `0%`」

---

## 一、现象与定位

### 1.1 现象

DSH 通过本中转站使用 OpenAI 兼容协议，对话正常，但界面显示：

```
1 轮 1 步 · 0 tok/s      上下文 0%
```

换用其他模型（不经本中转站）时能正常显示速度与上下文。

### 1.2 定位（铁律 2：先定位再改）

**生产侧取证**（只读）：

| 检查 | 结果 |
|---|---|
| `log_usage` 最近 200 条 `estimated` | 0/200 —— 服务端**确实解析到了真实 usage** |
| 最近 8 条 token 数值 | 如 `473675 prompt / 271 completion`，非 0、非估算 |
| 近 3000 行日志的入站路径 | `1458 POST /v1/chat/completions`，`/v1/messages` 与 `/v1/responses` 各 0 条 |

→ 说明**不是上游没给 usage，也不是记账失败**，而是 usage chunk 没发给客户端。

**代码定位**（`backend/app/services/router_service.py`）：

```
L491-493  客户端没传 include_usage → 注入 → tracker.injected_usage = True
L395      _wrap_stream_with_usage(result, tracker, tracker.injected_usage)
L442      if not client_wants_usage: continue   ← 在这里被剥离
```

**根因**：第 395 行把「中转站注入过」当成「客户端要求」，两者语义正好相反。

### 1.3 为什么两种客户端都拿不到

| 客户端行为 | `injected_usage` | 传给 `client_wants_usage` | 结果 |
|---|---|---|---|
| 不传 `include_usage` | `True`（我们注入了） | `True` | 剥离 → 收不到 |
| **传 `include_usage`** | `False`（无需注入） | `False` | 剥离 → **收不到** |

第二行是 DSH 的情况：它自己要求了 usage，反而因为「没被注入」而被判定为「不需要」。**两条路径都剥离**，所以所有流式客户端一律收不到 usage。

### 1.4 最小复现（改前实测）

```
[A] 客户端【不传】include_usage  → 收到 usage = True    ← 与预期相反
[B] 客户端【传】include_usage    → 收到 usage = False   ← 客户端正当要求被吞
```

---

## 二、修复

### 2.1 改动（单点，铁律 3）

`backend/app/services/router_service.py`：

1. 进入注入分支**之前**，先记录客户端原始意图：

```python
client_wants_usage = bool((body.get("stream_options") or {}).get("include_usage"))
```

2. 注入判断复用该变量（语义不变，仅避免重复取值）：

```python
if final_fmt == "openai" and not client_wants_usage:
    body["stream_options"] = {"include_usage": True}
    tracker.injected_usage = True
```

3. `_forward()` 新增 `client_wants_usage: bool = False` 参数，并在包装流式响应时传真实意图：

```python
result = self._wrap_stream_with_usage(result, tracker, client_wants_usage)
```

4. `injected_usage` 的注释改写，明确它**不再参与**剥离决策：

```python
# True=中转站主动替客户端注入了 stream_options.include_usage。
# 注意：仅用于说明该 usage chunk 是「我们要求才有的」，**不参与**是否剥离的
# 决策——剥离与否只看客户端的原始意图（CH-039）。
self.injected_usage = False
```

### 2.2 为什么保留 `injected_usage` 而不删

它仍表达「这个 usage chunk 是我们主动要求上游才有的」这一事实，对后续排查有价值（例如区分「上游本来就会给」与「我们开的」）。删除会丢失该信息。改为只写不读、注释澄清语义即可。

### 2.3 行为变化

| 场景 | 改前 | 改后 |
|---|---|---|
| 客户端要求 `include_usage` | 收不到 usage | **收到 usage**（含 `cached_tokens`） |
| 客户端不要求 | 收不到 usage | 收不到（保持旧行为，不影响其他客户端） |
| 服务端记账 | 正常 | 正常（`feed_chunk` 在剥离前已执行） |
| 非流式 | 正常 | 正常 |

---

## 三、验证

### 3.1 新增脚本

`test/verify_usage_passthrough_ch039.py`（19 项，全通过）：

- **[1] 不传 include_usage**：不返回 usage chunk（兼容）、正文两个 delta 都在、服务端记账正确（`prompt=1234`、`estimated=0`、`cache_read_tokens=800`）
- **[2] 传 include_usage（DSH 场景）**：**收到 usage chunk**、`prompt_tokens` / `completion_tokens` / `total_tokens` 全部正确、`prompt_tokens_details.cached_tokens` 透传、正文未被破坏、记账不受影响
- **[3] 非流式**：usage 原样透传、`stream=0`、缓存 token 已记录

### 3.2 回归

CH-023（aggregation / api）、CH-024（rule-binding）、CH-034（group-scope）、CH-036、CH-037、CH-038 —— 7 套全通过；`compileall` 0 错误。

---

## 四、同类问题勘察（本次不修，已登记）

生产近 3000 行日志里 `/v1/messages` 与 `/v1/responses` **各 0 条**，故以下两处只登记不修：

| 位置 | 问题 |
|---|---|
| `anthropic_convert_in.py` L217 / L279 | `message_start.usage` 与 `message_delta.usage` 都写死 0（非流式路径是对的） |
| `responses_convert.py` L435-437 | `response.completed` 里完全没有 `usage` 字段 |

已登记到 `docs/需求规格.md` 9.7，附修法。

---

## 五、验收标准

1. 客户端传 `stream_options.include_usage=true` → SSE 末段出现带 `usage` 的 chunk
2. 客户端不传 → 行为与改前完全一致（不出现 usage chunk）
3. 两种情况服务端 `log_usage` 都正确记录真实 token（`estimated=0`）
4. 正文内容（delta 序列）不受影响
5. 非流式响应不变
6. CH-023/024/034/036/037/038 回归全通过

---

## 六、明确不做

- 不改 Anthropic / Responses 入站的流式 usage（0 流量，已登记 9.7）
- 不改变「客户端不要求时剥离」的既有兼容行为
- 不动上游适配器的转发逻辑
