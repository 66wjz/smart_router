-- Smart Router v5 增量脚本 02：上游源 Key 池
-- 创建时间：2026-08-09
-- 说明：新增 up_upstream_key 表（一个上游源挂多个 API Key），存量 api_key 迁移为 Key 池第一条
-- 执行方式：sqlite3 或由 Python 执行

CREATE TABLE IF NOT EXISTS up_upstream_key (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    upstream_id TEXT NOT NULL,
    api_key TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_upstream_key_upstream ON up_upstream_key(upstream_id);

-- 存量迁移：现有单 Key 写入 Key 池（幂等）
INSERT OR IGNORE INTO up_upstream_key (upstream_id, api_key)
SELECT upstream_id, api_key FROM up_upstream WHERE api_key IS NOT NULL AND trim(api_key) != '';
