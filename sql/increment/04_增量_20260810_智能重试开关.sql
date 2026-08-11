-- 04_增量_20260810_智能重试开关.sql
-- CH-012：up_upstream 新增 smart_retry 列（0/1，默认 0=关闭）
-- 执行方式：sqlite3 smart_router.db < 本文件（或在 DB 工具中执行）

ALTER TABLE up_upstream ADD COLUMN smart_retry INTEGER NOT NULL DEFAULT 0;
