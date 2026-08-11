-- Smart Router v5 增量脚本 03：上游源已配置模型列表
-- 创建时间：2026-08-09
-- 说明：up_upstream 增加 models 字段（JSON 数组字符串），存量默认空列表
-- 执行方式：sqlite3 或由 Python 执行

ALTER TABLE up_upstream ADD COLUMN models TEXT NOT NULL DEFAULT '[]';
