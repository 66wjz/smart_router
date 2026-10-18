# CH-024：rule 聚合的真实路由绑定（规则子集 + 候选子集）

> 分类：B 线-大（新数据链路 + 运行时行为变化）
> 流程：维护迭代模式 · 迷你 stage-1→5
> 日期：2026-10-17
> 状态：设计已与用户确认，实施中
> 前序：CH-023（聚合统一 + 探测模板）

---

## 一、背景：CH-023 遗留的设计缺陷

CH-023 把「手写聚合名」统一成了 `kind=rule` 的聚合实体，但**只统一了名字，没有统一行为**。

### 1.1 问题证据

`core/router_engine.py` 的 `get_ordered_candidates()` 签名里**没有聚合名参数**：

```python
def get_ordered_candidates(messages, body, app_config, probe, health,
                           estimated_tokens=0, allowed_groups=None):
    for rule in app_config.rules:      # ← 遍历全局规则表
        if match_rule(rule, messages, body):
            candidates = rule.get("candidates", [])
            break
```

`router_service._resolve_candidates()` 虽然知道客户端请求的是 `smart-latest`，但只是用它做了"是不是聚合名"的判定，**没有把名字传下去**。

### 1.2 后果

| 现象 | 说明 |
|---|---|
| 多个 rule 聚合行为完全相同 | `smart-latest` 与 `smart-chat` 走的是同一套全局规则、同一份候选 |
| 无法表达"这个聚合只要一部分模型" | 规则表是全局的，无法按聚合裁剪 |
| 探测成本无法按聚合区分 | `rule_candidate_units()` 不带聚合名，所有 rule 聚合都显示"覆盖 N 个单元"（N 相同） |
| 前端无法新增 rule 聚合 | `saveEdit()` 里 `kind: 'static'` 写死，弹窗没有类型选择 |

### 1.3 用户提出的方案（已确认）

保留路由规则作为**候选库**（一张表、配好每条规则的候选），新增聚合时选择：

- 用哪几条规则
- 每条规则里用哪几个候选模型

即：**一张路由规则表，每个聚合名引用其一个子集**。

---

## 二、目标

1. 每个 rule 聚合有自己的路由行为（可只启用部分规则、部分候选）
2. 新增聚合时可选择类型（固定成员 / 规则匹配）
3. 探测计划按各聚合的实际绑定计算单元，成本可区分
4. 删除/改名规则时，同步清理引用它的聚合绑定，并提示影响范围
5. 老数据零迁移（无绑定 = 全跟随）

---

## 三、数据模型

### 3.1 新增字段（增量 SQL，不改原表文件）

```sql
ALTER TABLE agg_unified ADD COLUMN rule_bindings TEXT;
```

`rule_bindings` 仅对 `kind='rule'` 有意义，JSON 结构：

```json
[
  {"rule": "默认对话", "candidates": null},
  {"rule": "视觉理解", "candidates": [
      {"upstream": "buddy", "model": "gemini-2.5-pro"}
  ]}
]
```

| 值 | 语义 |
|---|---|
| `NULL` / `[]` | **全跟随**：使用所有规则、每条规则的全部候选（兼容 CH-023 老数据） |
| `[{rule, candidates: null}]` | 只使用列出的规则，但每条规则内全部候选都跟随（规则以后加模型会自动纳入） |
| `[{rule, candidates: [...]}]` | 显式候选子集；规则里新增的模型不会自动纳入 |

**为什么用 `{upstream, model}` 而不是 `"upstream:model"` 字符串**：模型名可能含冒号，拆分会歧义。

**为什么候选列表要允许 `null`**：区分"我全都要，以后规则加模型也跟着要"和"我只要当前这几个"。前者不会因为规则页新增模型而意外扩大探测成本。

### 3.2 校验规则

- `rule` 名称必须存在于当前规则表（保存时 400）
- `candidates` 里的项若已从规则中移除 → **不报错**，运行时静默跳过，接口返回 `stale` 标记供 UI 提示
- 绑定列表不能为空数组以外地"禁用全部规则"——若用户取消所有规则，前端阻止并提示"至少保留一条规则"

---

## 四、运行时改造

### 4.1 路由候选

`get_ordered_candidates()` 增加关键字参数 `aggregation: str | None = None`：

```
取规则列表：
  aggregation 为空 或 该聚合无绑定  → 全部规则（现有行为）
  有绑定                            → 只保留绑定里列出的规则，并按绑定裁剪候选

裁剪候选（bindings[i].candidates 非 null）：
  只保留 (upstream, model) 命中列表的候选

之后完全走原有逻辑：启用过滤 → 分组过滤 → priority + 动态权重排序
```

**排序语义一行不改**：仍然是 `priority` 升序 + 动态权重 `base_weight × (base_latency/latency)²` 降序，`dw=0` 过滤，全 0 回退原顺序。

### 4.2 探测计划

`rule_candidate_units(aggregation: str | None = None)`：

- 传聚合名：只展开该聚合绑定的规则与候选
- 不传：全部规则（供 `GET /aggregations/rule-units` 与旧逻辑复用）

`collect_probe_plan()` 中 rule 聚合那段改为 `self.rule_candidate_units(name)`。

### 4.3 规则变更联动

`AppConfig.set_rules()` 保存后执行 `prune_rule_bindings(valid_names)`：

- 遍历 `kind=rule` 且绑定非空的聚合
- 删除绑定中已不存在的规则名
- 若清理后为空 → 置为 `NULL`（回退全跟随），并记录 warning
- 返回受影响聚合名，通过 `PUT /admin/api/rules` 响应告知前端

---

## 五、API 变更

| 方法 | 路径 | 变更 |
|---|---|---|
| GET | `/admin/api/aggregations` | 每项新增 `rule_bindings`、`rule_binding_summary`（规则数 / 候选数）、`stale_bindings`（失效项） |
| PUT | `/admin/api/aggregations?name=` | 新增 `rule_bindings` 入参；`kind=rule` 时生效；`null`/`[]` = 全跟随 |
| PUT | `/admin/api/rules` | 响应新增 `affected_aggregations`（因规则删除/改名而被清理的聚合名） |
| GET | `/admin/api/aggregations/rule-units?name=` | 新增可选 `name`，传则返回该聚合的绑定展开结果 |

---

## 六、前端变更

### 6.1 新建/编辑聚合弹窗

顶部新增类型选择：

```
聚合类型  ( ) 固定成员   ( ) 规则匹配
```

选「规则匹配」后，主体从"成员拖拽列表"切换为"规则绑定"：

```
┌ 默认对话 ────────────────────────────── [✓ 使用] ┐
│ 候选（勾选即纳入本聚合，全选 = 跟随规则）           │
│  ☑ buddy · deepseek-v4.1-flash   P1 权重5          │
│  ☑ buddy · qwen3-coder-480b      P1 权重3          │
└────────────────────────────────────────────────────┘
┌ 视觉理解 ────────────────────────────── [✓ 使用] ┐
│  ☑ buddy · gemini-2.5-pro        P1 权重2          │
│  ☐ loomy · glm-4.6               P2 权重1          │
└────────────────────────────────────────────────────┘
```

- 规则全选 → 存 `candidates: null`
- 取消任一候选 → 存显式列表
- 取消「使用」→ 该规则不进绑定；全部取消时阻止保存
- 规则页无候选时提示"请先去路由规则页配置候选"

### 6.2 聚合卡片

rule 聚合卡片在原有"覆盖 N 个探测单元"之外，增加：

```
3 条规则 · 5 个候选
默认对话(2) · 视觉理解(1) · 工具调用(2)
```

有失效绑定（`stale_bindings` 非空）时显示黄色徽标「2 个候选已失效」。

### 6.3 路由规则页

删除规则时，若被 rule 聚合引用，确认框追加："该规则被 N 个聚合使用（a、b），删除后这些聚合会同步移除该规则绑定。"

---

## 七、改动文件

### 后端

| 文件 | 改动 |
|---|---|
| `sql/increment/08_增量_20261017_聚合规则绑定.sql`（新） | `agg_unified` 加 `rule_bindings` 列 |
| `repositories/aggregation_repo.py` | 解析/序列化 `rule_bindings` |
| `core/config.py` | 载入绑定；`rule_bindings_of()` / `rule_candidate_units(name)` / `prune_rule_bindings()`；启动执行 08 |
| `core/router_engine.py` | `get_ordered_candidates(..., aggregation=None)` + 绑定裁剪 |
| `services/router_service.py` | 传入聚合名 |
| `services/config_service.py` | `list_aggregations` 带绑定摘要与失效项；`set_rules` 返回受影响聚合 |
| `api/admin/aggregations.py` | `rule_bindings` 入参校验（`model_fields_set` 区分 null/未提供）；`rule-units` 支持 `name` |
| `api/admin/rules.py` | 响应带 `affected_aggregations` |

### 前端

| 文件 | 改动 |
|---|---|
| `api/aggregations.ts` | 类型补 `rule_bindings` / `rule_binding_summary` / `stale_bindings` |
| `views/Aggregated.vue` | 新建弹窗加类型选择 + 规则绑定编辑器；卡片显示规则摘要 |
| `views/Rules.vue` | 删除规则时提示影响聚合 |

---

## 八、验证方案

1. **`test/verify_rule_binding_ch024.py`（新）**
   - 无绑定 → 行为与改造前一致（回归）
   - 绑定规则子集 → 只走列出的规则
   - 绑定候选子集 → 只出现勾选的候选
   - `candidates: null` → 规则新增模型后自动纳入
   - 规则删除 → 绑定被清理、受影响聚合返回
   - 探测单元数按绑定计算且各聚合理不同
   - 空绑定清理后回退全跟随

2. **回归**：`verify_aggregation_ch023.py`、`verify_api_ch023.py`、`verify_probe_ch021.py`

3. **前端**：`npm run build` + demo 库浏览器实测（新建规则聚合、绑定裁剪、卡片摘要）

---

## 九、受影响文档（收尾时按清单核对）

| # | 文档 | 何时受影响 |
|---|---|---|
| 1 | README.md | 能力清单需补"rule 聚合可裁剪规则/候选" |
| 2 | docs/需求规格.md | 功能点 8.1 补充绑定语义 |
| 3 | docs/架构设计.md | 路由决策流程增加绑定裁剪分支 |
| 4 | docs/数据库设计.md | `agg_unified` 补 `rule_bindings` 字段 + 增量 SQL 08 |
| 5 | docs/API契约.md | 3 个端点字段变更 |
| 6 | docs/接口文档.md | 同上 |
| 7 | docs/系统核心流程.md | 流程 1/2 与能力清单更新 |
| 8 | docs/面向客户的功能清单.md | 2.8.1 与演示验证清单补项 |
| 9 | docs/五列对应矩阵.md | 补行 |
| 10 | docs/变更记录.md | 总是追加 |

---

## 十、不做

- 不做"按聚合覆盖权重/优先级"（统一用规则表的配置，避免两处打架）
- 不做"规则内候选单独设优先级"（沿用规则表）
- 不删除 `agg_aggregated_name` 等旧表（继续保留兜底）
- 不部署、不 push（等用户明确授权）

---

## 十一、实施结果（2026-10-17，本地完成，未部署）

### 11.1 与设计的偏差

| 项 | 设计 | 实际 | 原因 |
|---|---|---|---|
| 规则页提示影响聚合 | 删除规则时前端弹框提示 | 后端 `PUT /rules` 返回 `affected_aggregations`，前端暂未加提示文案 | 后端已具备数据，前端提示待后续补（不阻塞主链路） |
| 空绑定语义 | `null` / `[]` 均表示全跟随 | 前端保存全跟随时传 `[]`，后端 `_validate_bindings` 归一化为 `None` | 保持存储统一，两种入参等价 |
| 失效绑定 | 仅 UI 提示 | 额外提供 `rule_binding_issues()` 供接口返回 `stale_bindings` | 规则删候选后能立即在卡片上看到黄标 |

### 11.2 修复的问题

- **前端提交 `members: []` 被后端拒绝**：rule 类型聚合保存时报 400「不能配置成员」。根因是 `saveEdit()` 无条件带上 `members` 字段，而后端用 `req.members is not None` 判断是否配置成员。改为 rule 类型不发送该字段。

### 11.3 验证结果

| 项目 | 结果 |
|---|---|
| `test/verify_rule_binding_ch024.py` | 全部通过（8 组：全跟随回归 / 规则子集 / 候选子集 / 覆盖自动扩展 / 探测单元按绑定 / 规则删除清理 / 失效检测 / API 校验） |
| CH-023 回归 | `verify_migration_ch023.py` 通过、`verify_aggregation_ch023.py` 通过、`verify_api_ch023.py` 通过 |
| `npm run build` | 通过 |
| 浏览器实测（demo.db / 10198） | 新建弹窗出现类型选择；选「规则匹配」后列出规则与候选；取消勾选候选后「跟随」徽标消失、计数变 1/2；保存成功；卡片显示「默认对话(2 · 跟随) 视觉理解(1) · 2 条规则 · 3 个候选 · 覆盖 6 个探测单元」；`rule-units?name=` 返回裁剪后的单元 |

### 11.4 已知限制

- 路由规则页删除规则时，后端会返回受影响聚合，但前端暂未弹出提示（后端行为已生效且安全：绑定被自动清理并回退全跟随）
- 绑定的候选只做"是否属于该规则"的校验，不做上游源启用状态校验（运行时统一按启用状态过滤）
- **未 push、未部署**，等用户明确授权
