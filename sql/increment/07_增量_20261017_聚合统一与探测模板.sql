-- CH-023：聚合模型统一（static / rule 同一实体）+ 探测模板
-- 幂等：CREATE TABLE IF NOT EXISTS + INSERT OR IGNORE，可重复执行
-- 旧表 agg_aggregated_name / agg_model_group / agg_probe_config 保留不删（回滚兜底）

-- ============================================================
-- 1. 探测模板：多个聚合引用同一模板，改模板即全部生效
-- ============================================================
CREATE TABLE IF NOT EXISTS agg_probe_template (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,                    -- 模板名（如"高频-限时"）
    interval_seconds INTEGER NOT NULL,            -- 探测间隔（秒）
    slow_threshold_seconds REAL,                  -- NULL = 跟随全局
    sort_mode TEXT NOT NULL DEFAULT 'stable',     -- stable | latency（仅 static 聚合生效）
    schedule TEXT NOT NULL DEFAULT '{}',          -- JSON: {"mode":"always"} / {"mode":"window","days":[..],"windows":[..]}
    remark TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================
-- 2. 统一聚合实体
--    kind='static'：固定成员（原 agg_model_group，支持异名成员）
--    kind='rule'  ：手写聚合名（原 agg_aggregated_name，候选由路由规则运行时匹配）
-- ============================================================
CREATE TABLE IF NOT EXISTS agg_unified (
    name TEXT PRIMARY KEY,                        -- 客户端请求使用的聚合名
    kind TEXT NOT NULL,                           -- 'static' | 'rule'
    members TEXT NOT NULL DEFAULT '[]',           -- 仅 static：JSON [{"upstream","model","weight"}]
    enabled INTEGER NOT NULL DEFAULT 1,           -- 聚合本身是否启用
    probe_enabled INTEGER NOT NULL DEFAULT 0,     -- 是否对该聚合涉及的探测单元定时探测
    template_id INTEGER,                          -- 探测模板；非空时模板值优先，组自配字段不生效
    sort_mode TEXT NOT NULL DEFAULT 'stable',     -- stable | latency（仅 static 生效）
    interval_seconds INTEGER,                     -- NULL = 跟随全局（仅无模板时生效）
    slow_threshold_seconds REAL,                  -- NULL = 跟随全局
    schedule TEXT NOT NULL DEFAULT '{}',          -- 同模板的 schedule 结构
    remark TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_agg_unified_kind ON agg_unified(kind);
CREATE INDEX IF NOT EXISTS idx_agg_unified_template ON agg_unified(template_id);

-- ============================================================
-- 3. 数据迁移（只补缺，不覆盖新表已有内容）
-- ============================================================

-- 3.1 旧手写聚合名 → rule
INSERT OR IGNORE INTO agg_unified (name, kind, members, enabled)
SELECT name, 'rule', '[]', 1 FROM agg_aggregated_name;

-- 3.2 旧聚合组 → static（upstreams 结构与本表 members 一致）
INSERT OR IGNORE INTO agg_unified (name, kind, members, enabled)
SELECT model, 'static', COALESCE(NULLIF(upstreams, ''), '[]'), COALESCE(enabled, 1)
FROM agg_model_group;

-- 3.3 旧组探测配置 → 合并进对应行（含 enabled=0 的组：保留参数，只把开关记为关）
UPDATE agg_unified
SET probe_enabled = (SELECT p.enabled FROM agg_probe_config p WHERE p.model = agg_unified.name),
    interval_seconds = (SELECT p.interval_seconds FROM agg_probe_config p WHERE p.model = agg_unified.name),
    slow_threshold_seconds = (SELECT p.slow_threshold_seconds FROM agg_probe_config p WHERE p.model = agg_unified.name),
    sort_mode = COALESCE((SELECT p.sort_mode FROM agg_probe_config p WHERE p.model = agg_unified.name), sort_mode),
    schedule = COALESCE((SELECT p.schedule FROM agg_probe_config p WHERE p.model = agg_unified.name), schedule),
    updated_at = CURRENT_TIMESTAMP
WHERE EXISTS (SELECT 1 FROM agg_probe_config p WHERE p.model = agg_unified.name);
