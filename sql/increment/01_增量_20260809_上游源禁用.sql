-- Smart Router v5 增量脚本 01：上游源禁用功能
-- 创建时间：2026-08-09
-- 说明：up_upstream 增加 enabled 字段（1=启用 0=禁用），存量数据默认启用
-- 执行方式：sqlite3 或由 Python 执行

ALTER TABLE up_upstream ADD COLUMN enabled INTEGER NOT NULL DEFAULT 1;
