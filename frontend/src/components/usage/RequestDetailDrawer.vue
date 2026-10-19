<template>
  <Teleport to="body">
    <div v-if="visible" class="drawer-overlay" @click.self="close">
      <aside class="drawer" role="dialog" aria-label="请求详情">
        <!-- 顶部：摘要 -->
        <header class="drawer-head">
          <div class="head-main">
            <BaseBadge :variant="statusVariant">{{ statusText }}</BaseBadge>
            <span class="head-title">请求 #{{ logId }}</span>
            <BaseBadge variant="gray">{{ summary.protocol }}{{ summary.stream ? ' ·流式' : '' }}</BaseBadge>
            <span v-if="isDisconnected" class="head-flag">客户端已断开</span>
          </div>
          <div class="head-actions">
            <BaseButton variant="ghost" size="sm" @click="layout = layout === 'columns' ? 'single' : 'columns'">
              {{ layout === 'columns' ? '单栏视图' : '三栏对比' }}
            </BaseButton>
            <BaseButton variant="ghost" size="sm" @click="refresh" :disabled="loading">刷新</BaseButton>
            <button class="close-btn" @click="close" aria-label="关闭">
              <BaseIcon name="x" :size="16" />
            </button>
          </div>
        </header>

        <div v-if="loading" class="drawer-empty">加载中…</div>
        <div v-else-if="loadError" class="drawer-empty">{{ loadError }}</div>

        <div v-else class="drawer-body">
          <!-- 摘要信息 -->
          <section class="summary-grid">
            <div class="kv">
              <span class="k">时间</span>
              <span class="v">{{ formatTime(summary.ts || summary.created_at) }}</span>
            </div>
            <div class="kv">
              <span class="k">模型</span>
              <span class="v mono">{{ summary.model || '—' }}</span>
            </div>
            <div class="kv">
              <span class="k">上游</span>
              <span class="v">{{ summary.upstream_name || summary.upstream_id || '—' }}</span>
            </div>
            <div class="kv">
              <span class="k">上游模型</span>
              <span class="v mono">{{ summary.upstream_model || '—' }}</span>
            </div>
            <div class="kv">
              <span class="k">Key</span>
              <span class="v">{{ summary.api_key_name || '—' }}</span>
            </div>
            <div class="kv">
              <span class="k">耗时</span>
              <span class="v">{{ summary.duration_ms != null ? summary.duration_ms + ' ms' : '—' }}<template v-if="summary.first_token_ms != null"> · 首包 {{ summary.first_token_ms }} ms</template></span>
            </div>
            <div class="kv">
              <span class="k">Tokens</span>
              <span class="v">
                输入 {{ summary.prompt_tokens ?? 0 }}
                · 缓存读 {{ summary.cache_read_tokens ?? 0 }}
                <template v-if="summary.cache_write_tokens"> · 缓存写 {{ summary.cache_write_tokens }}</template>
                · 输出 {{ summary.completion_tokens ?? 0 }}
                · 合计 {{ summary.total_tokens ?? 0 }}
                <BaseHint v-if="summary.estimated" inline text="（估算）" />
              </span>
            </div>
            <div class="kv">
              <span class="k">HTTP</span>
              <span class="v">{{ summary.http_status ?? '—' }}</span>
            </div>
          </section>

          <el-alert v-if="summary.error_msg" type="error" :closable="false" show-icon
            :title="summary.error_msg" style="margin-bottom: 12px" />

          <!-- 尝试链 -->
          <section v-if="attempts.length" class="attempts">
            <h4>尝试链路（{{ attempts.length }} 次）</h4>
            <div class="attempt-list">
              <div v-for="(a, i) in attempts" :key="i" class="attempt" :class="{ fail: !isOk(a.http_status) }">
                <span class="attempt-idx">{{ i + 1 }}</span>
                <span class="attempt-src">{{ a.upstream || '—' }}</span>
                <span class="attempt-model mono">{{ a.model || '—' }}</span>
                <span class="attempt-http">{{ a.http_status ?? '—' }}</span>
                <span class="attempt-ms">{{ a.ms != null ? a.ms + 'ms' : '—' }}</span>
                <span class="attempt-err" :title="a.error || ''">{{ a.error || '' }}</span>
              </div>
            </div>
          </section>

          <!-- 三栏报文 -->
          <el-alert v-if="!detail.available" type="info" :closable="false" show-icon
            :title="detail.reason || '该请求未采集详情报文'" />

          <div v-else class="panes" :class="`panes-${layout}`">
            <section class="pane">
              <header class="pane-head">
                <span class="pane-title">REQUEST<span class="pane-sub">原始请求</span></span>
                <span class="pane-actions">
                  <BaseButton v-if="canExpand('request_body')" variant="ghost" size="sm" @click="toggleExpand('request_body')">
                    {{ expanded.request_body ? '收起' : '展开全部' }}
                  </BaseButton>
                  <BaseButton variant="ghost" size="sm" @click="copy(paneTexts.request)">复制</BaseButton>
                </span>
              </header>
              <div class="pane-tabs">
                <button :class="{ active: requestTab === 'body' }" @click="requestTab = 'body'">请求体</button>
                <button :class="{ active: requestTab === 'headers' }" @click="requestTab = 'headers'">请求头</button>
              </div>
              <pre v-if="requestTab === 'body'" class="code">{{ paneTexts.request }}</pre>
              <pre v-else class="code">{{ headersText }}</pre>
            </section>

            <section class="pane">
              <header class="pane-head">
                <span class="pane-title">FORWARDED<span class="pane-sub">实际转发</span></span>
                <span class="pane-actions">
                  <BaseButton v-if="canExpand('forward_body')" variant="ghost" size="sm" @click="toggleExpand('forward_body')">
                    {{ expanded.forward_body ? '收起' : '展开全部' }}
                  </BaseButton>
                  <BaseButton variant="ghost" size="sm" @click="copy(paneTexts.forwarded)">复制</BaseButton>
                </span>
              </header>
              <pre class="code">{{ paneTexts.forwarded }}</pre>
            </section>

            <section class="pane">
              <header class="pane-head">
                <span class="pane-title">RESPONSE<span class="pane-sub">上游响应</span></span>
                <span class="pane-actions">
                  <BaseButton v-if="canExpand('response_body')" variant="ghost" size="sm" @click="toggleExpand('response_body')">
                    {{ expanded.response_body ? '收起' : '展开全部' }}
                  </BaseButton>
                  <BaseButton variant="ghost" size="sm" @click="copy(paneTexts.response)">复制</BaseButton>
                </span>
              </header>
              <pre class="code">{{ paneTexts.response }}</pre>
            </section>
          </div>
        </div>
      </aside>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import BaseBadge from '@/components/base/BaseBadge.vue'
import BaseButton from '@/components/base/BaseButton.vue'
import BaseHint from '@/components/base/BaseHint.vue'
import BaseIcon from '@/components/base/BaseIcon.vue'
import { copyToClipboard } from '@/utils/clipboard'
import { getUsageLogDetail } from '@/api/usage'

const props = defineProps<{
  visible: boolean
  logId: number | null
}>()

const emit = defineEmits<{ 'update:visible': [value: boolean] }>()

const loading = ref(false)
const loadError = ref('')
const summary = ref<any>({})
const attempts = ref<any[]>([])
const detail = ref<any>({ available: false, reason: '' })
const requestTab = ref<'body' | 'headers'>('body')
const layout = ref<'columns' | 'single'>('columns')

/** 大报文分块渲染：默认只渲染前 64KB，避免一次性插入几 MB 文本卡死 */
const RENDER_LIMIT = 64 * 1024
const expanded = ref<Record<string, boolean>>({})

const isDisconnected = computed(() => Number(summary.value.http_status) === 499)
const statusVariant = computed(() => {
  if (summary.value.status === 'success') return 'green'
  if (isDisconnected.value) return 'amber'
  return 'red'
})
const statusText = computed(() => {
  if (summary.value.status === 'success') return '成功'
  if (isDisconnected.value) return '断开'
  return '失败'
})

const headersText = computed(() => {
  const h = detail.value.request_headers
  if (!h || !Object.keys(h).length) return '（无）'
  return Object.entries(h).map(([k, v]) => `${k}: ${v}`).join('\n')
})

function pretty(raw: any): string {
  if (raw === null || raw === undefined) return '（未采集）'
  let text = String(raw)
  if (typeof raw === 'string') {
    const s = raw.trim()
    if ((s.startsWith('{') && s.endsWith('}')) || (s.startsWith('[') && s.endsWith(']'))) {
      try {
        text = JSON.stringify(JSON.parse(s), null, 2)
      } catch {
        // 非法 JSON 原样展示
      }
    }
  } else {
    try {
      text = JSON.stringify(raw, null, 2)
    } catch {
      text = String(raw)
    }
  }
  return text
}

function paneText(key: string): string {
  const full = pretty(detail.value[key])
  if (expanded.value[key] || full.length <= RENDER_LIMIT) return full
  return `${full.slice(0, RENDER_LIMIT)}\n\n…[已省略 ${full.length - RENDER_LIMIT} 字符，点击「展开全部」查看]`
}

const paneTexts = computed(() => ({
  request: paneText('request_body'),
  forwarded: paneText('forward_body'),
  response: paneText('response_body'),
}))

function canExpand(key: string): boolean {
  return pretty(detail.value[key]).length > RENDER_LIMIT
}

function toggleExpand(key: string) {
  expanded.value = { ...expanded.value, [key]: !expanded.value[key] }
}

function isOk(http: any): boolean {
  const n = Number(http)
  return Number.isFinite(n) && n >= 200 && n < 300
}

function formatTime(s?: string): string {
  if (!s) return '—'
  return String(s).replace('T', ' ').slice(0, 19)
}

async function copy(text: string) {
  const ok = await copyToClipboard(text)
  ok ? ElMessage.success('已复制') : ElMessage.error('复制失败')
}

function close() {
  emit('update:visible', false)
}

async function load() {
  if (!props.logId) return
  loading.value = true
  loadError.value = ''
  try {
    const res: any = await getUsageLogDetail(props.logId)
    summary.value = res.summary || {}
    attempts.value = res.attempts || []
    detail.value = res.detail || { available: false, reason: '' }
  } catch (e: any) {
    loadError.value = e?.response?.data?.detail || '加载请求详情失败'
  } finally {
    loading.value = false
  }
}

function refresh() {
  expanded.value = {}
  load()
}

watch(
  () => [props.visible, props.logId],
  ([v]) => {
    if (v) {
      requestTab.value = 'body'
      expanded.value = {}
      load()
    }
  },
)
</script>

<style scoped>
.drawer-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.35);
  z-index: var(--z-modal);
  display: flex;
  justify-content: flex-end;
  animation: drawerFade 0.15s ease;
}
.drawer {
  width: min(1280px, 92vw);
  height: 100%;
  background: var(--bg-base);
  border-left: 1px solid var(--border-subtle);
  box-shadow: var(--shadow-lg);
  display: flex;
  flex-direction: column;
  animation: drawerIn 0.2s var(--ease-out);
}
@keyframes drawerFade { from { opacity: 0; } to { opacity: 1; } }
@keyframes drawerIn { from { transform: translateX(24px); opacity: 0; } to { transform: none; opacity: 1; } }

.drawer-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 14px 18px;
  border-bottom: 1px solid var(--border-subtle);
  flex-wrap: wrap;
}
.head-main { display: flex; align-items: center; gap: 8px; min-width: 0; }
.head-title { font-weight: 600; font-size: 15px; }
.head-flag { font-size: 12px; color: var(--accent-amber); }
.head-actions { display: flex; align-items: center; gap: 8px; }
.close-btn {
  background: none;
  border: none;
  color: var(--text-tertiary);
  cursor: pointer;
  width: 28px;
  height: 28px;
  border-radius: var(--radius-sm);
  display: flex;
  align-items: center;
  justify-content: center;
}
.close-btn:hover { background: var(--bg-hover); color: var(--text-primary); }

.drawer-body { flex: 1; overflow: auto; padding: 16px 18px 28px; }
.drawer-empty { padding: 40px; text-align: center; color: var(--text-tertiary); }

.summary-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: 8px 16px;
  padding: 12px 14px;
  background: var(--bg-elevated);
  border-radius: var(--radius-md);
  margin-bottom: 14px;
}
.kv { display: flex; gap: 8px; font-size: 12px; min-width: 0; }
.kv .k { color: var(--text-tertiary); flex: 0 0 62px; }
.kv .v { color: var(--text-primary); word-break: break-all; }
.mono { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; }

.attempts { margin-bottom: 14px; }
.attempts h4 { margin: 0 0 8px; font-size: 13px; }
.attempt-list { display: flex; flex-direction: column; gap: 4px; }
.attempt {
  display: grid;
  grid-template-columns: 28px 90px minmax(160px, 1.4fr) 70px 80px minmax(120px, 2fr);
  align-items: center;
  gap: 8px;
  padding: 5px 10px;
  font-size: 12px;
  background: var(--bg-elevated);
  border-radius: var(--radius-sm);
}
.attempt.fail { background: var(--accent-red-muted); }
.attempt-idx { color: var(--text-tertiary); }
.attempt-err { color: var(--text-tertiary); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.attempt.fail .attempt-err { color: var(--accent-red); }

.panes { display: grid; gap: 12px; align-items: start; }
.panes-columns { grid-template-columns: repeat(3, minmax(0, 1fr)); }
.panes-single { grid-template-columns: minmax(0, 1fr); }

.pane {
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-md);
  overflow: hidden;
  background: var(--bg-surface);
  min-width: 0;
}
.pane-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 10px;
  background: var(--bg-elevated);
  border-bottom: 1px solid var(--border-subtle);
}
.pane-title { font-size: 12px; font-weight: 700; letter-spacing: 0.04em; }
.pane-sub { font-weight: 400; color: var(--text-tertiary); margin-left: 6px; letter-spacing: 0; }
.pane-actions { display: flex; align-items: center; gap: 6px; }
.pane-tabs { display: flex; gap: 4px; padding: 6px 10px 0; }
.pane-tabs button {
  background: none;
  border: 1px solid transparent;
  border-radius: var(--radius-sm) var(--radius-sm) 0 0;
  padding: 3px 10px;
  font-size: 12px;
  color: var(--text-tertiary);
  cursor: pointer;
}
.pane-tabs button.active {
  color: var(--text-primary);
  border-color: var(--border-subtle);
  border-bottom-color: transparent;
  background: var(--bg-hover);
}
.code {
  margin: 0;
  padding: 10px 12px;
  max-height: 52vh;
  overflow: auto;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 11.5px;
  line-height: 1.55;
  color: var(--text-primary);
  white-space: pre-wrap;
  word-break: break-word;
}

@media (max-width: 1280px) {
  .panes-columns { grid-template-columns: minmax(0, 1fr); }
}
</style>
