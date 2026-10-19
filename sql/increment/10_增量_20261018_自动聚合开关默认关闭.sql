-- CH-036：同名模型自动聚合开关默认关闭 + CH-033 残留清理
-- 幂等：靠 sys_setting 标记键保证「只翻一次」，不覆盖用户之后的手动开关

-- 1) 开关缺行 → 插入 false
INSERT INTO sys_setting (key, value) SELECT 'auto_same_name_aggregate', 'false'
WHERE NOT EXISTS (SELECT 1 FROM sys_setting WHERE key = 'auto_same_name_aggregate');

-- 2) 存量 true → false（仅迁移一次；用标记键防止重启把用户手动打开的开关又关掉）
UPDATE sys_setting SET value = 'false', updated_at = CURRENT_TIMESTAMP
WHERE key = 'auto_same_name_aggregate'
  AND value = 'true'
  AND NOT EXISTS (SELECT 1 FROM sys_setting WHERE key = 'auto_same_name_migrated_v2');

INSERT INTO sys_setting (key, value) SELECT 'auto_same_name_migrated_v2', 'true'
WHERE NOT EXISTS (SELECT 1 FROM sys_setting WHERE key = 'auto_same_name_migrated_v2');

-- 3) 清理 CH-033 残留：为「移除自动发现聚合」落库的已关闭空壳行
--    条件极其精确，避免误删用户真实配置（必须有成员才算真实聚合）
DELETE FROM agg_unified
WHERE kind = 'static'
  AND enabled = 0
  AND remark = '已关闭（原自动发现聚合）'
  AND (members IS NULL OR members = '[]' OR members = '');
