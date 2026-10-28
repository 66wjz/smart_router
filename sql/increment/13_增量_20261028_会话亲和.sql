-- CH-052 会话亲和（缓存优先路由）
-- 1) 聚合级开关：NULL=跟随全局，0=关闭，1=开启
-- 2) 用量观测：会话指纹 / 是否命中钉子 / 切换原因
-- 注：运行期也会幂等补列（usage_repo / aggregation_repo），老库无需手工迁移

ALTER TABLE agg_unified ADD COLUMN affinity INTEGER DEFAULT NULL;
ALTER TABLE log_usage ADD COLUMN affinity_key TEXT;
ALTER TABLE log_usage ADD COLUMN affinity_hit INTEGER DEFAULT 0;
ALTER TABLE log_usage ADD COLUMN switch_reason TEXT;
