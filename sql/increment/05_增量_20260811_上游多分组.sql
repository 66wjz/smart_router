-- CH-016：up_upstream 新增 groups 列（JSON 数组，多分组归属）
-- 幂等：重复执行 ALTER 会报 duplicate column，由执行脚本捕获忽略
-- group_name 列保留但逻辑废弃（兼容存量读取）

ALTER TABLE up_upstream ADD COLUMN groups TEXT NOT NULL DEFAULT '[]';

-- 存量回填：groups = [group_name]
UPDATE up_upstream SET groups = json_array(COALESCE(NULLIF(group_name, ''), 'free')) WHERE groups = '[]';
