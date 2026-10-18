-- CH-024：rule 聚合的路由绑定（规则子集 + 候选子集）
-- 幂等：ALTER TABLE ADD COLUMN 重复执行会报 duplicate column，由启动时 ensure_column 兜底忽略

-- rule_bindings 仅对 kind='rule' 有意义，JSON 结构：
--   NULL / '[]'                                  → 全跟随（使用全部规则、全部候选）
--   [{"rule":"默认对话","candidates":null}]       → 只用该规则，候选全跟随（规则以后加模型自动纳入）
--   [{"rule":"视觉理解","candidates":[{"upstream":"buddy","model":"gemini-2.5-pro"}]}]
--                                                → 显式候选子集
ALTER TABLE agg_unified ADD COLUMN rule_bindings TEXT;

CREATE INDEX IF NOT EXISTS idx_agg_unified_kind ON agg_unified(kind);
