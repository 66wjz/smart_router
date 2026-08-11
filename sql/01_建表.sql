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
