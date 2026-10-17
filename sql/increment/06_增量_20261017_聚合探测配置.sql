-- CH-021：聚合模型独立探测配置 + 用量按「源 × 真实模型」记账（增量）
-- 幂等：CREATE TABLE IF NOT EXISTS 可重复执行；
--       ALTER TABLE 重复执行会报 duplicate column，由启动时 ensure_column 兜底忽略

-- 每个聚合组独立的探测策略（与 agg_model_group 解耦：自动发现的组也能配，且不会变成"已手动配置"）
CREATE TABLE IF NOT EXISTS agg_probe_config (
    model TEXT PRIMARY KEY,                       -- 聚合名（组标识）
    enabled INTEGER NOT NULL DEFAULT 0,           -- 该组是否启用定时探测
    interval_seconds INTEGER,                     -- NULL = 跟随全局
    slow_threshold_seconds REAL,                  -- NULL = 跟随全局
    sort_mode TEXT NOT NULL DEFAULT 'stable',     -- stable（稳定优先）| latency（速度优先）
    schedule TEXT NOT NULL DEFAULT '{}',          -- JSON: {"mode":"always|window","days":[1..7],"windows":[{"start":"08:00","end":"23:00"}]}
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- 用量记录补「上游真实模型名」：异名聚合时与客户端请求名不同，号池配额核算必须用真实名
ALTER TABLE log_usage ADD COLUMN upstream_model TEXT;

CREATE INDEX IF NOT EXISTS idx_usage_unit ON log_usage(upstream_id, upstream_model, ts);
