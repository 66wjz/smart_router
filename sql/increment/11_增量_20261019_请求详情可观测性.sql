-- CH-038：请求详情可观测性
-- 1) 主表补缓存 token 与尝试次数（幂等：重复执行报 duplicate column，由调用方容错忽略）
ALTER TABLE log_usage ADD COLUMN cache_read_tokens INTEGER DEFAULT 0;
ALTER TABLE log_usage ADD COLUMN cache_write_tokens INTEGER DEFAULT 0;
ALTER TABLE log_usage ADD COLUMN attempt_count INTEGER DEFAULT 1;

-- 2) 请求详情表（与 log_usage 1:1，可缺行；仅按策略采集）
CREATE TABLE IF NOT EXISTS log_usage_detail (
    log_id          INTEGER PRIMARY KEY,   -- 对应 log_usage.id
    request_headers TEXT,                  -- 入站请求头（已脱敏）
    request_body    TEXT,                  -- 客户端原始请求体
    forward_body    TEXT,                  -- 实际发给上游的请求体
    response_body   TEXT,                  -- 上游响应体（流式存首尾摘要）
    attempts        TEXT,                  -- JSON: [{upstream,model,status,http,ms,error}]
    created_at      TEXT DEFAULT (datetime('now','localtime'))
);
CREATE INDEX IF NOT EXISTS idx_usage_detail_created ON log_usage_detail(created_at);

-- 3) 详情采集策略（默认仅失败请求；单报文上限 1MB）
INSERT INTO sys_setting (key, value) SELECT 'usage_detail_mode', '"error_only"'
WHERE NOT EXISTS (SELECT 1 FROM sys_setting WHERE key = 'usage_detail_mode');
INSERT INTO sys_setting (key, value) SELECT 'usage_detail_max_bytes', '1048576'
WHERE NOT EXISTS (SELECT 1 FROM sys_setting WHERE key = 'usage_detail_max_bytes');

-- 4) 保留期默认 14 天
--    旧库由 06 建表脚本写入 30，此前没有 UI 可改，故仅当值仍为默认 30 时改为 14；
--    其它值视为用户显式设置，保留不动。
INSERT INTO sys_setting (key, value) SELECT 'usage_retention_days', '14'
WHERE NOT EXISTS (SELECT 1 FROM sys_setting WHERE key = 'usage_retention_days');
UPDATE sys_setting SET value = '14' WHERE key = 'usage_retention_days' AND value = '30';