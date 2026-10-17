-- Smart Router v5 建表脚本（SQLite）
-- 创建时间：2026-08-09
-- 执行方式：sqlite3 或 Python sqlite3 模块执行

-- ============================================================
-- 1. 客户端密钥表
-- ============================================================
CREATE TABLE IF NOT EXISTS api_api_key (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    key_value TEXT NOT NULL UNIQUE,
    groups TEXT NOT NULL DEFAULT '["free"]',
    enabled INTEGER NOT NULL DEFAULT 1,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_api_key_value ON api_api_key(key_value);

-- ============================================================
-- 2. 上游源表
-- ============================================================
CREATE TABLE IF NOT EXISTS up_upstream (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    upstream_id TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    base_url TEXT NOT NULL,
    api_key TEXT NOT NULL,
    format TEXT NOT NULL DEFAULT 'openai',
    group_name TEXT NOT NULL DEFAULT 'free',
    probe_enabled INTEGER NOT NULL DEFAULT 1,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_upstream_id ON up_upstream(upstream_id);

-- ============================================================
-- 3. 路由规则表
-- ============================================================
CREATE TABLE IF NOT EXISTS rule_rule (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    match_json TEXT NOT NULL DEFAULT '{}',
    sort_order INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================
-- 4. 候选模型表
-- ============================================================
CREATE TABLE IF NOT EXISTS rule_candidate (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    rule_id INTEGER NOT NULL,
    model TEXT NOT NULL,
    upstream_id TEXT NOT NULL,
    weight INTEGER NOT NULL DEFAULT 1,
    priority INTEGER NOT NULL DEFAULT 1,
    max_context INTEGER,
    max_output INTEGER,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_candidate_rule_id ON rule_candidate(rule_id);

-- ============================================================
-- 5. 模型别名（指针）表
-- ============================================================
CREATE TABLE IF NOT EXISTS pt_pointer (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    target_model TEXT NOT NULL,
    upstream_id TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_pointer_name ON pt_pointer(name);

-- ============================================================
-- 6. 聚合模型名表
-- ============================================================
CREATE TABLE IF NOT EXISTS agg_aggregated_name (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================
-- 7. 系统参数表（key-value，value 存 JSON 字符串）
-- ============================================================
CREATE TABLE IF NOT EXISTS sys_setting (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    key TEXT NOT NULL UNIQUE,
    value TEXT NOT NULL,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_setting_key ON sys_setting(key);

-- ============================================================
-- 8. 用量统计表（CH-019）
-- ============================================================
CREATE TABLE IF NOT EXISTS log_usage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,                  -- 请求完成时间 epoch
    api_key_id INTEGER,                -- 客户端 Key
    api_key_name TEXT,
    upstream_id TEXT,                  -- 实际命中的 upstream
    upstream_name TEXT,
    model TEXT,                        -- 客户端请求的模型名
    protocol TEXT DEFAULT 'chat',      -- chat / anthropic / responses
    stream INTEGER DEFAULT 0,
    status TEXT,                       -- success / error
    http_status INTEGER,
    prompt_tokens INTEGER DEFAULT 0,
    completion_tokens INTEGER DEFAULT 0,
    total_tokens INTEGER DEFAULT 0,
    estimated INTEGER DEFAULT 0,       -- 1=估算值
    duration_ms INTEGER,
    first_token_ms INTEGER,
    error_msg TEXT,
    created_at TEXT DEFAULT (datetime('now','localtime'))
);
CREATE INDEX IF NOT EXISTS idx_usage_ts ON log_usage(ts);
CREATE INDEX IF NOT EXISTS idx_usage_key_ts ON log_usage(api_key_id, ts);
CREATE INDEX IF NOT EXISTS idx_usage_model_ts ON log_usage(model, ts);

-- ============================================================
-- 9. 同名模型聚合组人工配置（CH-019 二期）
-- ============================================================
CREATE TABLE IF NOT EXISTS agg_model_group (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    model TEXT NOT NULL UNIQUE,
    upstreams TEXT NOT NULL DEFAULT '[]',  -- JSON: [{"upstream":"xxx","weight":1}]，顺序即候选优先级
    enabled INTEGER NOT NULL DEFAULT 1,     -- 0 = 关闭同名聚合，退化为单源直连
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_model_group_model ON agg_model_group(model);
