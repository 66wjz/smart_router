# 变更：上游源 Key 池（批量 Key + 自动路由）

> 编号：CH-003
> 日期：2026-08-09
> 分类：B 线（新功能，M 规模）
> 状态：已实现（已部署生产 8.137.195.192:10002）
> 关联文档：[docs/数据库设计.md](../../数据库设计.md)、[docs/API契约.md](../../API契约.md)、[docs/接口文档.md](../../接口文档.md)

---

## 一、变更背景

当前架构：Smart Router → newapi 中转站（8.137.195.192:10000，sub2api）→ NVIDIA 官方免费端点。一个上游源只能配置**一个** API Key，依赖单点中转，限流不可控。

用户目标：Smart Router 直接对接 NVIDIA 官方（`integrate.api.nvidia.com`），上游源支持**批量配置多个 API Key**，请求自动路由到其中一个 Key（Key 池轮询 + 失败跳过），用多 Key 分摊单 Key 限流，替代 newapi 中转层。

## 二、功能语义

1. **一个上游源挂载 N 个 Key**（N≥1），Key 为同提供商（同 base_url）的不同凭据；
2. **转发自动选 Key**：轮询选择 + 跳过失败/冷却中的 Key；被上游拒绝（401/403/429）的 Key 立即标记失败并换下一个 Key 重试同一模型；**全部 Key 失败才返回失败**（触发现有候选模型重试）；
3. **Key 级健康**：连续失败达到阈值进入短暂冷却，成功清零，冷却后自动恢复；
4. **探测**：探测请求同样从 Key 池选 Key，坏 Key 不误判整个模型 down；
5. **存量迁移**：现有 `up_upstream.api_key` 迁移为 Key 池第一条，行为完全兼容；
6. 原有 `api_key` 字段保留（单 Key 快捷写法），新增 `api_keys` 数组（批量写法，优先级更高）。

## 三、影响面

| 层 | 改动 | 说明 |
|----|------|------|
| 数据库 | 新增表 `up_upstream_key` + 数据迁移 | 增量 SQL，不改原建表文件 |
| 配置层 | `get_upstream_keys()`、Key 池加载/同步 | AppConfig 读 Key 列表，写操作同步 |
| 新增模块 | `KeyPool`（内存 Key 健康 + 轮询选择） | 独立于 DB 的运行时状态 |
| 转发 | openai/anthropic 适配器改用 Key 池选 Key + 失败换 Key | 改动集中在 adapter |
| 探测 | probe 用 Key 池选 Key | 避免坏 Key 误判 |
| API | UpstreamCreate/Update 支持 `api_keys`；list 返回 `key_count` | 兼容 `api_key` |
| 前端 | 上游源新增/编辑改为多 Key 输入（每行一个）；列表显示 Key 数量 | Upstreams.vue |

## 四、详细设计

### 4.1 数据库（增量 SQL `sql/increment/02_增量_20260809_上游Key池.sql`）

```sql
CREATE TABLE IF NOT EXISTS up_upstream_key (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    upstream_id TEXT NOT NULL,
    api_key TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_upstream_key_upstream ON up_upstream_key(upstream_id);

-- 存量迁移：现有单 Key 写入 Key 池
INSERT OR IGNORE INTO up_upstream_key (upstream_id, api_key)
SELECT upstream_id, api_key FROM up_upstream WHERE api_key IS NOT NULL AND trim(api_key) != '';
```

### 4.2 新增 KeyPool 模块（`backend/app/core/key_pool.py`）

内存运行时状态（不落库）：

```python
class KeyPool:
    def __init__(self, max_fails=3, cooldown_seconds=120)
    def pick(self, upstream_id, keys: list[str]) -> str | None
        # 轮询索引 + 跳过冷却中/禁用的 Key
    def record_fail(self, upstream_id, key)   # 失败计数+1，达阈值进入冷却
    def record_success(self, upstream_id, key) # 清零
    def reset(self, upstream_id)               # 热重载/Key 变更时重置
```

- `pick` 返回当前轮询下标的下一个**可用** Key；无可用返回 None；
- 阈值/冷却复用 failover 配置（max_fails / cooldown_seconds）。

### 4.3 配置层（AppConfig）

- 加载时按上游分组读取 `up_upstream_key`；
- 新增 `get_upstream_keys(upstream_id) -> list[str]`（仅 enabled 的 key）；
- `add_upstream`：`api_keys` 优先，其次 `api_key`；
- `update_upstream`：若传入 `api_keys` 则整体替换 Key 池（删旧插新）；
- `delete_upstream`：级联删除该上游的 Key；
- Key 池变化时调用 `key_pool.reset(upstream_id)`。

### 4.4 转发适配器（openai_adapter.py / anthropic_adapter.py）

伪代码（非流式为例）：

```python
keys = app_config.get_upstream_keys(upstream_id)
for _ in range(len(keys)):                # 最多尝试 keys 数量次
    api_key = key_pool.pick(upstream_id, keys)
    if not api_key: break                 # 无可用 Key
    resp = await post(url, headers=Bearer(api_key))
    if resp.status_code == 200:
        key_pool.record_success(...); health.record_success(model); return ...
    if resp.status_code in (401, 403, 429):
        key_pool.record_fail(...); log; continue      # 换下一个 Key
    else:
        health.record_fail(model); return None        # 其他错误，换候选模型
return None
```

- adapter 增加 `key_pool` 参数（由 `main.py` 创建单例注入 RouterService → adapter）；
- 流式同逻辑。

### 4.5 探测（probe.py）

- `probe_one` 用 `key_pool.pick` 选 Key；401/403/429 时 `record_fail` 并换下一个 Key 重试；
- 全部 Key 失败才判定模型 down。

### 4.6 API 契约

```
UpstreamCreate:  + api_keys?: list[str]      （优先于 api_key）
UpstreamUpdate:  + api_keys?: list[str]      （传则整体替换 Key 池）
GET /admin/api/upstreams: 每条 + key_count: int
```

### 4.7 前端（Upstreams.vue）

- 新增/修改弹窗的「API Key」输入改为多行文本（每行一个 Key）；
- 修改弹窗回显现有 Key（每行一个）；提交 `api_keys: string[]`；
- 列表卡片显示 `N 个 Key`。

## 五、验收标准

1. 上游源可配置多个 Key（批量粘贴），列表显示 Key 数量；
2. 转发轮询使用 Key；单个 Key 401/429 立即换下一个 Key，同一模型成功；全部 Key 失败才换候选模型；
3. 失败 Key 达阈值进入冷却，冷却后自动恢复；成功清零；
4. 探测使用 Key 池，坏 Key 不误判模型 down；
5. 存量单 Key 上游迁移后行为不变；
6. 前后端 vue-tsc 通过、接口验证通过。

## 六、变更记录

| 日期 | 变更 | 变更人 |
|------|------|--------|
| 2026-08-09 | 初始创建 | AI+用户 |

## 七、实施补充（2026-08-09 实施后追加）

### 7.1 已落地改动

- 数据库：增量 SQL `sql/increment/02_增量_20260809_上游Key池.sql`（建 `up_upstream_key` + 存量迁移），本地与生产均已执行
- 新增模块：`app/core/key_pool.py`（轮询 + Key 级失败冷却）、`app/repositories/upstream_key_repo.py`
- 配置层：`AppConfig` 加载/写入 Key 池、`get_upstream_keys()`、`get_key_count()`、`get_upstream_all_keys()`（编辑回显）、写操作同步 `key_pool.reset()`
- 转发：openai/anthropic 适配器 4 个转发函数全部改走 Key 池（401/403/429/连接超时/响应超时/空响应/连接异常 → 记 Key 失败 → 换下一个 Key；全部 Key 失败才判模型失败）
- 探测：`probe_one` 用 Key 池选 Key，坏 Key 不误判模型 down
- API：`UpstreamCreate/Update` 增加 `api_keys`；list 返回 `key_count` + `keys`
- 前端：Upstreams.vue 新增/编辑改多 Key 文本域（每行一个），列表显示 `N 个 Key`

### 7.2 NVIDIA 卡住问题的解决（实施中发现并修复）

> 现象：NVIDIA 上游单个 Key 请求会长时间挂起（不返回错误也不返回结果）。

1. **超时/错误语义升级**：原实现超时直接判模型失败换候选；现改为超时/401/403/429/连接异常都只判**该 Key 失败**，换下一个 Key 重试同一模型（`app/upstream/openai_adapter.py`、`anthropic_adapter.py`）
2. **超时配置收紧**：`retry.response_timeout` 20→12s、`first_chunk_timeout` 8→6s（本地 + 生产 DB 同步，管理后台可调）
3. **脏连接修复（关键）**：非流式原用 `asyncio.wait_for(httpx.post())`，超时取消后 httpx 底层连接清理不可靠，**复用该连接的后续 Key 请求被上游挂起的旧请求阻塞**（端到端测试实测：坏 Key 挂起后好 Key 也超时）。修复：改用 `send(stream=True)` + `aread()` + 全路径显式 `await resp.aclose()`，确保超时/失败连接被主动关闭

### 7.3 验证记录

- 本地端到端（mock 上游 127.0.0.1:9999，3 Key：sk-bad/sk-slow/sk-test）：
  - 401 秒级换 Key ✅；挂起 Key 12s 超时换 Key ✅；sk-test 兜底成功 200 ✅
  - 连续失败 3 次进入冷却 120s，冷却后跳过 ✅
  - 修复脏连接后，3 连发均成功 ✅
- 生产验证（8.137.195.192:10002）：
  - 登录 / upstreams（key_count、keys）/ 模型拉取 / 前端页面 / 真实聊天（`openai/gpt-oss-20b` → newapi）均 200 ✅
  - DB 迁移：`up_upstream_key` 表已建，3 上游 Key 迁移完成，retry 配置已更新 ✅
