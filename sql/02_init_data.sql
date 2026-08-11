-- Smart Router v5 初始数据脚本（种子数据，对应 v4 config.yaml）
-- 创建时间：2026-08-09
-- 执行方式：sqlite3 或由 backend/seed.py 执行
-- 注意：密钥/密码为占位默认值，部署前应修改

-- ============================================================
-- 1. 系统参数
-- ============================================================
INSERT OR REPLACE INTO sys_setting (key, value) VALUES
('admin', '{"username": "admin", "password": "smart-router-2026", "session_hours": 24}'),
('listen_port', '10002'),
('default_upstream', '"newapi"'),
('log_level', '"INFO"'),
('log_routing', 'true'),
('latency_probe', '{"enabled": true, "interval_seconds": 120, "timeout_seconds": 35, "request_text": "Hi", "max_tokens": 3, "base_latency": 0.5, "down_threshold_seconds": 30, "slow_threshold_seconds": 10, "error_as_down": true}'),
('retry', '{"max_attempts": 3, "response_timeout": 20, "first_chunk_timeout": 8}'),
('failover', '{"max_fails": 3, "cooldown_seconds": 120}');

-- ============================================================
-- 2. 客户端密钥
-- ============================================================
INSERT OR REPLACE INTO api_api_key (name, key_value, groups, enabled) VALUES
('默认 Key', 'sk-CHANGE-ME-default', '["free"]', 1),
('扣子平台', 'sk-CHANGE-ME-coze', '["free"]', 1),
('我的专属 Key', 'sk-CHANGE-ME-premium', '["free", "premium"]', 1);

-- ============================================================
-- 3. 上游源
-- ============================================================
INSERT OR REPLACE INTO up_upstream (upstream_id, name, base_url, api_key, format, group_name, probe_enabled) VALUES
('newapi', 'NewAPI 中转站 (NVIDIA 免费白嫖)', 'http://8.137.195.192:10000', 'sk-CHANGE-ME-newapi', 'openai', 'free', 1),
('xiaomi', '小米 MiMo', 'https://token-plan-cn.xiaomimimo.com', 'tp-CHANGE-ME-xiaomi', 'openai', 'free', 1);

-- ============================================================
-- 4. 路由规则 + 候选模型
-- ============================================================

-- 规则 1: 视觉理解 (sort_order=1)
INSERT INTO rule_rule (name, match_json, sort_order) VALUES
('视觉理解', '{"has_image": true}', 1);
INSERT INTO rule_candidate (rule_id, model, upstream_id, weight, priority, max_context, max_output) VALUES
(1, 'minimaxai/minimax-m3', 'newapi', 5, 1, 1000000, 32768),
(1, 'nvidia/nemotron-3-nano-omni-30b-a3b-reasoning', 'newapi', 4, 1, 262144, 65536);

-- 规则 2: 工具调用 (sort_order=2)
INSERT INTO rule_rule (name, match_json, sort_order) VALUES
('工具调用', '{"has_tools": true}', 2);
INSERT INTO rule_candidate (rule_id, model, upstream_id, weight, priority, max_context, max_output) VALUES
(2, 'openai/gpt-oss-20b', 'newapi', 5, 1, 128000, 16384),
(2, 'minimaxai/minimax-m3', 'newapi', 4, 1, 1000000, 32768),
(2, 'nvidia/nemotron-3-ultra-550b-a55b', 'newapi', 4, 1, 1000000, 32768),
(2, 'nvidia/nemotron-3-nano-30b-a3b', 'newapi', 3, 1, 262144, 16384),
(2, 'nvidia/nemotron-3-nano-omni-30b-a3b-reasoning', 'newapi', 2, 1, 262144, 65536),
(2, 'nvidia/nemotron-3-super-120b-a12b', 'newapi', 1, 1, 1000000, 32768);

-- 规则 3: 默认对话 (sort_order=3)
INSERT INTO rule_rule (name, match_json, sort_order) VALUES
('默认对话', '{"default": true}', 3);
INSERT INTO rule_candidate (rule_id, model, upstream_id, weight, priority, max_context, max_output) VALUES
(3, 'nvidia/nemotron-3-nano-30b-a3b', 'newapi', 5, 1, 262144, 16384),
(3, 'openai/gpt-oss-20b', 'newapi', 4, 1, 128000, 16384),
(3, 'minimaxai/minimax-m3', 'newapi', 4, 1, 1000000, 32768),
(3, 'nvidia/nemotron-3-nano-omni-30b-a3b-reasoning', 'newapi', 3, 1, 262144, 65536),
(3, 'nvidia/nemotron-3-ultra-550b-a55b', 'newapi', 3, 1, 1000000, 32768),
(3, 'nvidia/nemotron-3-super-120b-a12b', 'newapi', 1, 1, 1000000, 32768);

-- ============================================================
-- 5. 模型别名（指针）—— 无（原 my-model/code/fast 指向的模型已从上游下架，已删除）

-- ============================================================
-- 6. 聚合模型名
-- ============================================================
INSERT OR REPLACE INTO agg_aggregated_name (name) VALUES
('smart-latest'),
('smart-chat'),
('auto-chat');
