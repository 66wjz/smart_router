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
INSERT INTO filter_rule (name, enabled, target, pattern, upstream_ids, action, remark)
SELECT 'DSH 身份声明', 0, 'system_first_line',
       'You are an AI agent powered by DeepSeek Harness',
       NULL, 'skip',
       'CH-040 实测：buddy 渠道按 system 首行精确匹配拦截 DSH 客户端。默认不启用，确认影响后手动开启。'
WHERE NOT EXISTS (SELECT 1 FROM filter_rule WHERE name = 'DSH 身份声明');

INSERT INTO filter_rule (name, enabled, target, pattern, upstream_ids, action, remark)
SELECT 'Claude Code 身份声明', 0, 'system_first_line',
       'You are Claude Code, Anthropic''s official CLI',
       NULL, 'skip',
       '同属非官方 agent 客户端黑名单，实测被同样渠道拦截。默认不启用。'
WHERE NOT EXISTS (SELECT 1 FROM filter_rule WHERE name = 'Claude Code 身份声明');
