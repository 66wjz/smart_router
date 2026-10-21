-- CH-041 请求过滤引擎（Pre-flight Filter）
-- 目的：在请求转发到上游之前，按规则判断「这个请求发过去注定会被上游拦截」，
--       从而直接跳过该上游，不产生任何上游请求（不消耗号池违规计数）。
--
-- 背景：WorkBuddy/buddy 渠道按 system 消息首行精确匹配维护非官方 agent 客户端黑名单，
--       命中后返回 HTTP 200 + error 包。CH-040 已能识别并切候选，但请求已经发出去了。

CREATE TABLE IF NOT EXISTS filter_rule (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT NOT NULL,              -- 规则名，如「DSH 身份声明」
    enabled       INTEGER NOT NULL DEFAULT 0, -- 1/0；默认不生效（安全默认）
    target        TEXT NOT NULL,              -- system_first_line / system_any / body_regex
    pattern       TEXT NOT NULL,              -- 匹配内容
    upstream_ids  TEXT,                       -- JSON 数组；空/NULL = 作用于全部上游源
    action        TEXT NOT NULL DEFAULT 'skip', -- skip=跳过该源 / reject=直接拒绝
    remark        TEXT DEFAULT '',
    created_at    TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at    TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_filter_rule_enabled ON filter_rule(enabled);

-- 全局开关：默认关闭，保证升级后行为与当前完全一致
INSERT INTO sys_setting (key, value)
VALUES ('filter_engine_enabled', 'false')
ON CONFLICT(key) DO NOTHING;

-- 预置两条已知规则（默认 enabled=0，需在界面手动开启）
-- 说明：pattern 用特征子串，不加引号/不加首尾锚点，避免因上游微调措辞而漏拦。
--
-- 作用源必须限定为 buddy / workbuddy，不能留空（留空 = 全部上游源）：
--   实测只有这两个渠道会按 system 首行匹配拦截非官方 agent 客户端，
--   trae / loomy / lobsterai 等渠道是放行的。规则不限源会把放行渠道也一起
--   拦掉，聚合候选被清空 → 客户端拿到 503，而不是设计中的「静默换成员」。
--   若发现新的拦截渠道，在「请求过滤」页把该源加进作用源即可。
INSERT INTO filter_rule (name, enabled, target, pattern, upstream_ids, action, remark)
SELECT 'DSH 身份声明', 0, 'system_first_line',
       'You are an AI agent powered by DeepSeek Harness',
       '["buddy","workbuddy"]', 'skip',
       'CH-040 实测：buddy / workbuddy 渠道按 system 首行精确匹配拦截 DSH 客户端；trae 等渠道放行，故作用源只限这两个。默认不启用，确认影响后手动开启。'
WHERE NOT EXISTS (SELECT 1 FROM filter_rule WHERE name = 'DSH 身份声明');

INSERT INTO filter_rule (name, enabled, target, pattern, upstream_ids, action, remark)
SELECT 'Claude Code 身份声明', 0, 'system_first_line',
       'You are Claude Code, Anthropic''s official CLI',
       '["buddy","workbuddy"]', 'skip',
       '同属非官方 agent 客户端黑名单，实测被同样渠道拦截，故作用源同上。默认不启用。'
WHERE NOT EXISTS (SELECT 1 FROM filter_rule WHERE name = 'Claude Code 身份声明');
