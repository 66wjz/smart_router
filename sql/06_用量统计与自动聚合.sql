-- CH-019：用量统计表 + 同名自动聚合开关（增量）
-- 幂等：可重复执行

CREATE TABLE IF NOT EXISTS log_usage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,                  -- 请求完成时间 epoch
    api_key_id INTEGER,                -- 客户端 Key（未认证失败不记）
    api_key_name TEXT,
    upstream_id TEXT,                  -- 实际命中的 upstream（重试取最终成功者；全败记最后尝试者）
    upstream_name TEXT,
    model TEXT,                        -- 客户端请求的模型名
    protocol TEXT DEFAULT 'chat',      -- chat / anthropic / responses
    stream INTEGER DEFAULT 0,
    status TEXT,                       -- success / error
    http_status INTEGER,
    prompt_tokens INTEGER DEFAULT 0,
    completion_tokens INTEGER DEFAULT 0,
    total_tokens INTEGER DEFAULT 0,
    estimated INTEGER DEFAULT 0,       -- 1=上游未返回 usage，按字符估算
    duration_ms INTEGER,
    first_token_ms INTEGER,            -- 流式首包耗时（可空）
    error_msg TEXT,                    -- 失败摘要（截断 500 字）
    created_at TEXT DEFAULT (datetime('now','localtime'))
);

CREATE INDEX IF NOT EXISTS idx_usage_ts ON log_usage(ts);
CREATE INDEX IF NOT EXISTS idx_usage_key_ts ON log_usage(api_key_id, ts);
CREATE INDEX IF NOT EXISTS idx_usage_model_ts ON log_usage(model, ts);

-- 同名模型聚合组的人工配置（CH-019 二期）
-- 一行 = 一个模型名的聚合配置；无行则走自动发现
CREATE TABLE IF NOT EXISTS agg_model_group (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    model TEXT NOT NULL UNIQUE,
    upstreams TEXT NOT NULL DEFAULT '[]',  -- JSON: [{"upstream":"xxx","weight":1}] 顺序即候选优先级
    enabled INTEGER NOT NULL DEFAULT 1,     -- 0 = 关闭同名聚合，退化为单源直连
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_model_group_model ON agg_model_group(model);

-- 同名模型自动聚合开关（默认开启；缺行时插入，已有值不覆盖）
INSERT INTO sys_setting (key, value) SELECT 'auto_same_name_aggregate', 'true'
WHERE NOT EXISTS (SELECT 1 FROM sys_setting WHERE key = 'auto_same_name_aggregate');

-- 用量保留天数
INSERT INTO sys_setting (key, value) SELECT 'usage_retention_days', '30'
WHERE NOT EXISTS (SELECT 1 FROM sys_setting WHERE key = 'usage_retention_days');
