---
AIGC:
  ContentProducer: '001191110102MAD55U9H0F10002'
  ContentPropagator: '001191110102MAD55U9H0F10002'
  Label: '1'
  ProduceID: 'b5447a5f-797d-4488-9dac-c1dab866aaad'
  PropagateID: 'b5447a5f-797d-4488-9dac-c1dab866aaad'
  ReservedCode1: '781ab911-14f4-4caf-a47c-82d9964c825b'
  ReservedCode2: '781ab911-14f4-4caf-a47c-82d9964c825b'
---

# Smart Router 上游容错增强方案

## 一、背景

当前 Smart Router 已实现：延迟探测 + 平方衰减 + 聚合模型 + 故障转移。

但现有的"故障转移"只在**渠道级别**（某个 channel 整体不可用时切走），缺少**单次请求级别**的容错能力：当上游返回 500、连接超时、TLS 握手中断（unexpected EOF）时，当前是直接把错误透传给客户端，客户端看到掉线。

典型场景：opencode.ai zen 免费 API 在工作日高峰期频繁返 500 和 TLS 握手中断，但过几秒可能就恢复，需要中转层自动重试 + 切备用渠道，让客户端无感知。

---

## 二、目标

对不稳定上游实现 **自动重试 → 故障转移 → 熔断保护** 三级容错，客户端只感知最终结果，不感知中间的重试和切换。

---

## 三、核心模块设计

### 3.1 单渠道自动重试

**触发条件**（以下情况才重试，4xx 不重试）：
- HTTP 5xx（500/502/503/504）
- 连接级错误：连接超时、连接重置（connection reset）、TLS 握手失败（unexpected EOF during handshake）
- 读取超时（等首字节超时）

**重试策略**：
- 最大重试次数：默认 3 次（可配）
- 退避间隔：指数退避，默认 `[500ms, 1000ms, 2000ms]`
- 加 jitter（±20%），防止多个客户端同步重试

**流式请求（SSE）的关键区分**——这是最容易出 bug 的地方：

```
转发请求到上游
 ├─ 阶段A：连接阶段（已发出请求，等待第一个 byte）
 │   ├─ 收到首字节 → 进入阶段B
 │   └─ 失败（5xx / 超时 / 连接断） → ✅ 可以重试（客户端还没收到任何数据）
 │
 └─ 阶段B：传输阶段（已经开始向客户端透传 SSE chunk）
     ├─ 中途断开 → ❌ 不重试！直接向客户端发 SSE error event 并关闭流
     │              （重试会导致内容重复，客户端无法处理）
     └─ 正常 [DONE] → 正常结束
```

> 核心原则：**只要还没往客户端写过任何字节，就可以重试；一旦写了第一个字节，就不能重试。**

### 3.2 跨渠道故障转移

单个渠道重试耗尽后，**自动切到 fallback 渠道**重试。

同一个逻辑模型可映射到多个上游渠道，按优先级排序：

```
客户端请求 model: "deepseek-v4-flash"

渠道列表（按优先级）:
  1. opencode-zen（免费，但不稳定）
  2. deepseek-official（付费，稳定）

执行流程:
  → opencode-zen 重试 3 次全失败
  → 自动切到 deepseek-official
  → 成功，结果返回给客户端
  → 客户端完全不知道中间切过渠道
```

### 3.3 熔断器（Circuit Breaker）

防止一个已经挂掉的上游持续拖慢所有请求。

**状态机**：

```
                  失败率超阈值
  ┌──────────┐ ──────────────→ ┌──────────┐
  │  CLOSED  │                 │   OPEN   │
  │ (正常)   │ ←────────────── │ (熔断中)  │
  └──────────┘   半开探测成功   └──────────┘
                                   │
                                   │ 冷却时间到(60s)
                                   ▼
                               ┌──────────┐
                               │HALF-OPEN │
                               │ (半开探测)│
                               └──────────┘
                                   │
                          ┌────────┴────────┐
                       探测成功            探测失败
                          │                   │
                     → CLOSED             → OPEN(再等60s)
```

**参数**：
- 统计窗口：最近 60 秒的请求
- 熔断触发：失败率 > 50% **且** 窗口内请求数 ≥ 10
- 熔断后：直接跳过该渠道，走 fallback（不再往该渠道发请求）
- 冷却时间：60 秒后进入半开状态，放行 1 个探测请求
- 探测成功 → 恢复（CLOSED）；探测失败 → 继续熔断（再等 60s）

### 3.4 主动健康检查（可选，加分项）

除了被动的熔断统计，可以加一个**后台定时探测**：

- 每 30 秒对所有渠道发一个轻量请求（如 `GET /v1/models` 或发一个 `max_tokens=1` 的最小请求）
- 探测结果用于给熔断器提供初始状态和加速恢复判断
- 不影响正常请求的延迟

---

## 四、配置格式

```jsonc
{
  "uptreams": {
    "opencode-zen": {
      "base_url": "https://opencode.ai/zen/go/v1",
      "api_key": "sk-xxx",
      "timeout_seconds": 30,
      "retry": {
        "max_attempts": 3,
        "backoff_ms": [500, 1000, 2000],
        "jitter": 0.2,
        "retry_on": ["http_5xx", "connect_error", "read_timeout", "tls_handshake_error"]
      },
      "circuit_breaker": {
        "enabled": true,
        "window_seconds": 60,
        "failure_rate_threshold": 0.5,
        "min_requests": 10,
        "cooldown_seconds": 60
      }
    },
    "deepseek-official": {
      "base_url": "https://api.deepseek.com/v1",
      "api_key": "sk-yyy",
      "timeout_seconds": 30
    }
  },

  // 模型 → 渠道路由表（按优先级，前面的渠道挂了自动切后面的）
  "model_routing": {
    "deepseek-v4-flash": {
      "channels": ["opencode-zen", "deepseek-official"],
      "model_map": {
        "opencode-zen": "deepseek-v4-flash",
        "deepseek-official": "deepseek-chat"
      }
    },
    "kimi-k3": {
      "channels": ["opencode-zen", "kimi-official"],
      "model_map": {
        "opencode-zen": "kimi-k3",
        "kimi-official": "moonshot-v1-auto"
      }
    }
  }
}
```

> `model_map` 解决不同上游模型名不一致的问题（比如 DeepSeek 官方叫 `deepseek-chat`，opencode zen 叫 `deepseek-v4-flash`）。

---

## 五、核心流程伪代码

```python
def handle_request(client_req):
    model = client_req["model"]
    stream = client_req.get("stream", False)

    # 1. 获取该模型的渠道列表（已按优先级排序）
    channels = model_routing[model]["channels"]
    model_map = model_routing[model].get("model_map", {})

    last_error = None

    for channel_id in channels:
        channel = upstreams[channel_id]

        # 2. 熔断检查 — 熔断中的渠道直接跳过
        if circuit_breaker.is_open(channel_id):
            log(f"[skip] {channel_id} 熔断中")
            continue

        # 3. 单渠道内重试
        for attempt in range(channel.retry.max_attempts):
            try:
                # 把逻辑模型名映射为该渠道的实际模型名
                actual_model = model_map.get(channel_id, model)
                upstream_req = replace_model(client_req, actual_model)

                if stream:
                    # —— 流式请求 ——
                    return handle_stream_request(
                        channel, upstream_req, channel_id
                    )
                else:
                    # —— 非流式请求 ——
                    resp = send_request(channel, upstream_req)
                    circuit_breaker.record_success(channel_id)
                    return resp

            except (ConnectError, TLSError, ReadTimeout, HTTP5xxError) as e:
                last_error = e
                circuit_breaker.record_failure(channel_id)
                log(f"[retry] {channel_id} attempt {attempt+1} failed: {e}")

                if attempt < channel.retry.max_attempts - 1:
                    backoff = calc_backoff(channel.retry, attempt)
                    sleep(backoff)
                    continue
                else:
                    break  # 该渠道重试耗尽，跳出，切下一个渠道

    # 4. 所有渠道都失败
    return error_response(503, f"all channels exhausted, last_error: {last_error}")


def handle_stream_request(channel, req, channel_id):
    """
    流式请求处理 — 区分「连接阶段」和「传输阶段」
    """
    try:
        resp = connect_to_upstream(channel, req)  # 建立连接
    except (ConnectError, TLSError, ReadTimeout, HTTP5xxError) as e:
        # 阶段A：连接阶段失败 — 客户端还没收到任何数据，可以重试
        raise e  # 抛回上层，触发重试/故障转移

    # 成功建立连接，开始透传
    try:
        client_stream = start_client_sse_stream()
        first_chunk_sent = False

        for chunk in resp.iter_chunks():
            client_stream.write(chunk)
            first_chunk_sent = True

        client_stream.close()

    except (ConnectError, ReadTimeout, ConnectionReset) as e:
        if not first_chunk_sent:
            # 还是阶段A，可以重试
            raise e
        else:
            # 阶段B：已经开始向客户端传数据了，不能重试
            # 直接向客户端发送 SSE error event
            client_stream.write(b'data: {"error":"upstream stream interrupted"}\n\n')
            client_stream.write(b'data: [DONE]\n\n')
            client_stream.close()
            circuit_breaker.record_failure(channel_id)
            return  # 正常返回，上层不会触发重试

    circuit_breaker.record_success(channel_id)
```

---

## 六、实现要点清单

| # | 要点 | 说明 |
|---|------|------|
| 1 | 重试只针对 5xx 和连接错误 | 4xx（如 401/403/429）不重试，直接返回 |
| 2 | 429（限流）特殊处理 | 可重试但要用更长的退避间隔（如 5s 起） |
| 3 | 流式请求的「首字节分界线」 | 一旦往客户端写了第一个字节，就不允许重试 |
| 4 | 熔断器的并发安全 | 用原子操作或锁保护计数器，避免并发请求竞态 |
| 5 | 渠道切换时保留客户端原始请求 | 不要在重试中丢失客户端的 headers/参数 |
| 6 | 日志记录 | 记录每次重试和切换，方便排查：`[channel=opencode-zen attempt=2] 500 Internal Server Error → fallback to deepseek-official` |
| 7 | 响应头标记 | 可在响应头加 `X-Served-By: deepseek-official`，方便调试确认走了哪个渠道 |
| 8 | model_map 映射 | 不同上游模型名可能不一样，需要配置映射 |

---

## 七、与现有 Smart Router 功能的关系

| 现有功能 | 本方案关系 |
|---------|-----------|
| 延迟探测+平方衰减 | 不冲突。本方案在「选好渠道后、请求执行阶段」做容错，延迟探测在「选渠道阶段」 |
| 聚合模型 | 不冲突。聚合模型选出的渠道列表可以直接作为本方案的 fallback 链 |
| 故障转移（渠道级） | 本方案是其超集：从「渠道级硬切」升级为「请求级重试+软切」 |

简单说：现有的故障转移是「渠道死了才切」，本方案是「单次请求失败了也重试，重试不行再切」，粒度更细。

---

## 八、预期效果

```
之前：客户端 → Smart Router → opencode-zen 500 → ❌ 客户端收到报错掉线
之后：客户端 → Smart Router → opencode-zen 500 → 重试 → 还500 → 切 deepseek-official → ✅ 客户端正常收到结果
```

客户端零感知，只看到请求成功。

> AI生成