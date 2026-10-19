-- CH-034：聚合模型独立分组（聚合作为权限门面）
-- 语义：groups 为空 / NULL → 所有 Key 可用（兼容存量）；非空 → 只允许分组交集非空的 Key
-- 幂等：ALTER TABLE ADD COLUMN 重复执行会报 duplicate column，由启动时 sync_unified_tables 容错忽略
ALTER TABLE agg_unified ADD COLUMN groups TEXT;
