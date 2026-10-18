/**
 * 上游源「已配置模型」的状态与操作（CH-026 从 Upstreams.vue 抽出）
 *
 * 抽成 composable 后，主容器与 ModelList / FetchModelsPanel 共享同一份状态，
 * 避免多层 props 透传。用 Symbol key provide/inject。
 */
import { nextTick, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import Sortable from 'sortablejs'
import {
  deleteUpstreamModel,
  reorderUpstreamModels,
  testUpstreamModel,
  toggleUpstreamModel,
  updateUpstreamModels,
  type ModelEntry,
} from '@/api/upstreams'
import { fetchUpstreamModels } from '@/api/aggregated'
import { reloadConfig } from '@/api/common'

export interface ModelTestState {
  status: string
  detail?: string
  latency?: number
}

/** 超过该数量时默认折叠列表 */
export const COLLAPSE_THRESHOLD = 5

export const UPSTREAM_MODELS_KEY = Symbol('upstream-models')

export function useUpstreamModels(loadAll: () => Promise<void> | void) {
  // 已配置模型（持久化，来自上游 models 字段，条目带可选协议覆盖）
  const modelsByUpstream = reactive<Record<string, ModelEntry[]>>({})
  // 拉取结果与勾选
  const remoteModelsByUpstream = reactive<Record<string, string[]>>({})
  const remoteChecked = reactive<Record<string, Record<string, boolean>>>({})
  const fetchSearch = reactive<Record<string, string>>({})
  const fetchPanelOpen = reactive<Record<string, boolean>>({})
  const fetchingIds = ref<string[]>([])
  // 单模型测试状态: idle | testing | ok | fail
  const modelStatesByUpstream = reactive<Record<string, Record<string, ModelTestState>>>({})
  const testingModels = reactive<Record<string, string[]>>({})
  // 折叠 + 全量测试
  const modelExpanded = reactive<Record<string, boolean>>({})
  const testingAll = reactive<Record<string, boolean>>({})
  const testProgress = reactive<Record<string, string>>({})
  // 批量选择
  const modelSelected = reactive<Record<string, Record<string, boolean>>>({})
  const togglingModels = reactive<Record<string, boolean>>({})

  /** 切换上游后重建列表时初始化各分片 */
  function initUpstream(id: string) {
    modelStatesByUpstream[id] = modelStatesByUpstream[id] || {}
    testingModels[id] = testingModels[id] || []
    modelExpanded[id] = modelExpanded[id] ?? false
    testingAll[id] = false
    modelSelected[id] = modelSelected[id] || {}
  }

  function setModels(id: string, models: ModelEntry[]) {
    modelsByUpstream[id] = models
  }

  // ---------- 拉取远端模型 ----------
  async function openFetchPanel(u: { id: string }) {
    if (fetchPanelOpen[u.id]) {
      fetchPanelOpen[u.id] = false
      return
    }
    if (!remoteModelsByUpstream[u.id]) await fetchRemoteModels(u)
    fetchPanelOpen[u.id] = true
  }

  async function fetchRemoteModels(u: { id: string }) {
    if (fetchingIds.value.includes(u.id)) return
    fetchingIds.value.push(u.id)
    try {
      const res: any = await fetchUpstreamModels(u.id)
      const models = res.models || []
      remoteModelsByUpstream[u.id] = models
      remoteChecked[u.id] = Object.fromEntries(models.map((m: string) => [m, false]))
      fetchSearch[u.id] = fetchSearch[u.id] || ''
      if (!models.length) {
        ElMessage.warning('未拉取到模型列表（检查 Base URL / API Key 或服务商不支持 /v1/models）')
      } else {
        ElMessage.success(`获取到 ${models.length} 个模型`)
      }
    } catch {
      ElMessage.error('获取模型列表失败')
    } finally {
      fetchingIds.value = fetchingIds.value.filter((id) => id !== u.id)
    }
  }

  function filteredRemoteModels(u: { id: string }): string[] {
    const q = (fetchSearch[u.id] || '').trim().toLowerCase()
    const list = remoteModelsByUpstream[u.id] || []
    if (!q) return list
    return list.filter((m) => m.toLowerCase().includes(q))
  }

  function selectedRemoteCount(u: { id: string }): number {
    return Object.values(remoteChecked[u.id] || {}).filter(Boolean).length
  }

  function toggleSelectAll(u: { id: string }) {
    const visible = filteredRemoteModels(u)
    if (!visible.length) return
    const checked = remoteChecked[u.id] || {}
    const allOn = visible.every((m) => checked[m])
    visible.forEach((m) => { checked[m] = !allOn })
  }

  async function handleJoin(u: { id: string }) {
    const checked = remoteChecked[u.id] || {}
    const picked = Object.keys(checked).filter((m) => checked[m])
    if (!picked.length) return
    const merged = mergeModels(modelsByUpstream[u.id], picked)
    if (merged.length === (modelsByUpstream[u.id] || []).length) {
      ElMessage.info('所选模型均已存在')
      return
    }
    try {
      await updateUpstreamModels(u.id, merged)
      modelsByUpstream[u.id] = merged
      ElMessage.success(`已加入 ${picked.length} 个模型`)
      fetchPanelOpen[u.id] = false
      remoteChecked[u.id] = {}
    } catch (e: any) {
      ElMessage.error(e?.response?.data?.detail || '保存模型列表失败')
    }
  }

  /** 手动添加：把输入的模型名并入现有列表（去重 + 按名排序） */
  async function addModels(id: string, names: string[]): Promise<boolean> {
    const merged = mergeModels(modelsByUpstream[id], names)
    try {
      await updateUpstreamModels(id, merged)
      modelsByUpstream[id] = merged
      return true
    } catch (e: any) {
      ElMessage.error(e?.response?.data?.detail || '添加失败')
      return false
    }
  }

  function mergeModels(base: ModelEntry[] | undefined, added: string[]): ModelEntry[] {
    const map = new Map((base || []).map((e) => [e.name, e]))
    added.forEach((name) => {
      if (!map.has(name)) map.set(name, { name })
    })
    return [...map.values()].sort((a, b) => a.name.localeCompare(b.name))
  }

  // ---------- 协议覆盖 / 启停 ----------
  async function setModelProtocol(u: { id: string }, modelName: string, protocol: string) {
    const effective = protocol === 'inherit' ? '' : protocol
    const list = modelsByUpstream[u.id] || []
    const newList = list.map((e) =>
      e.name === modelName
        ? (effective ? { name: e.name, protocol: effective as ModelEntry['protocol'] } : { name: e.name })
        : e,
    )
    try {
      await updateUpstreamModels(u.id, newList)
      modelsByUpstream[u.id] = newList
      ElMessage.success(effective
        ? `模型「${modelName}」协议已设为 ${effective}`
        : `模型「${modelName}」已恢复继承源协议`)
    } catch (e: any) {
      ElMessage.error(e?.response?.data?.detail || '保存协议失败')
    }
  }

  async function handleToggleModel(u: { id: string }, modelName: string, enabled: boolean) {
    const k = `${u.id}:${modelName}`
    togglingModels[k] = true
    try {
      await toggleUpstreamModel(u.id, modelName, enabled)
      const list = modelsByUpstream[u.id] || []
      const idx = list.findIndex((e) => e.name === modelName)
      if (idx >= 0) modelsByUpstream[u.id][idx] = { ...list[idx], enabled }
      ElMessage.success(enabled
        ? `模型「${modelName}」已启用`
        : `模型「${modelName}」已禁用（不出现在 /v1/models，不参与路由与探测）`)
      await reloadConfig()
    } catch (e: any) {
      ElMessage.error(e?.response?.data?.detail || '操作失败')
    } finally {
      togglingModels[k] = false
    }
  }

  // ---------- 拖拽排序 ----------
  const sortables: Record<string, Sortable> = {}

  function initModelSortable(u: { id: string }) {
    const el = document.querySelector(`[data-sortable-upstream="${u.id}"]`) as HTMLElement | null
    if (!el) return
    sortables[u.id]?.destroy()
    sortables[u.id] = Sortable.create(el, {
      handle: '.drag-handle',
      animation: 150,
      ghostClass: 'drag-ghost',
      fallbackTolerance: 3,
      // 只允许在本列内排序，禁止拖到其他上游源的列表（避免 id 串台导致 404）
      group: { name: `models-${u.id}`, pull: false, put: false },
      // 折叠状态下只显示前 N 行，拖拽会打乱全量顺序 → 折叠时禁用
      disabled: (modelsByUpstream[u.id] || []).length > COLLAPSE_THRESHOLD && !modelExpanded[u.id],
      onEnd: async (evt) => {
        const fromEl = evt.from as HTMLElement
        const toEl = evt.to as HTMLElement
        const fromUid = fromEl.dataset.sortableUpstream || ''
        const toUid = toEl.dataset.sortableUpstream || ''
        // 跨源拖拽：Sortable 已把节点挪出原列（即使目标列不接受），重新加载数据复原
        if (fromUid !== toUid || toUid !== u.id) {
          await loadAll()
          return
        }
        if ((evt.oldIndex ?? -1) === (evt.newIndex ?? -1)) return
        const domOrder = Array.from(toEl.querySelectorAll('.model-row'))
          .map((n) => (n as HTMLElement).dataset.model || '')
          .filter(Boolean)
        const all = [...(modelsByUpstream[u.id] || [])]
        if (domOrder.length !== all.length) {
          // 折叠态下可见行少于全量行 → 不落库，交给下次展开后再拖
          await loadAll()
          return
        }
        const byName = new Map(all.map((e) => [e.name, e]))
        const finalList = domOrder.map((n) => byName.get(n)).filter(Boolean) as ModelEntry[]
        // 先同步本地数据，避免 Vue 用旧数组回写 DOM
        modelsByUpstream[u.id] = finalList
        try {
          await reorderUpstreamModels(u.id, finalList.map((e) => e.name))
          await reloadConfig()
          ElMessage.success('模型顺序已保存')
        } catch (e: any) {
          ElMessage.error(e?.response?.data?.detail || '排序失败')
          await loadAll()
        }
      },
    })
  }

  function initAllSortables(upstreamIds: string[]) {
    nextTick(() => {
      upstreamIds.forEach((id) => initModelSortable({ id }))
    })
  }

  // ---------- 折叠 ----------
  function visibleModels(u: { id: string }): ModelEntry[] {
    const all = modelsByUpstream[u.id] || []
    if (all.length > COLLAPSE_THRESHOLD && !modelExpanded[u.id]) {
      return all.slice(0, COLLAPSE_THRESHOLD)
    }
    return all
  }

  function toggleExpand(u: { id: string }) {
    modelExpanded[u.id] = !modelExpanded[u.id]
    // 折叠/展开会改变渲染行数，重建 Sortable 以刷新 disabled 状态
    nextTick(() => initModelSortable(u))
  }

  // ---------- 批量选择 ----------
  function allSelected(u: { id: string }): boolean {
    const all = modelsByUpstream[u.id] || []
    if (!all.length) return false
    const sel = modelSelected[u.id] || {}
    return all.every((e) => sel[e.name])
  }

  function toggleSelectAllModels(u: { id: string }) {
    const all = modelsByUpstream[u.id] || []
    const target = !allSelected(u)
    for (const e of all) modelSelected[u.id][e.name] = target
  }

  function selectedModelCount(u: { id: string }): number {
    return Object.values(modelSelected[u.id] || {}).filter(Boolean).length
  }

  function selectedModels(u: { id: string }): string[] {
    const all = modelsByUpstream[u.id] || []
    const sel = modelSelected[u.id] || {}
    return all.filter((e) => sel[e.name]).map((e) => e.name)
  }

  async function batchDelete(u: { id: string }) {
    const sel = selectedModels(u)
    if (!sel.length) return
    try {
      await ElMessageBox.confirm(`确定删除选中的 ${sel.length} 个模型吗？`, '批量删除确认', {
        type: 'warning', confirmButtonText: '确定', cancelButtonText: '取消',
      })
    } catch {
      return
    }
    const newList = (modelsByUpstream[u.id] || []).filter((e) => !sel.includes(e.name))
    try {
      await updateUpstreamModels(u.id, newList)
      modelsByUpstream[u.id] = newList
      modelSelected[u.id] = {}
      ElMessage.success(`已删除 ${sel.length} 个模型`)
    } catch (e: any) {
      ElMessage.error(e?.response?.data?.detail || '批量删除失败')
    }
  }

  // ---------- 测试 ----------
  function isTesting(u: { id: string }, m: string): boolean {
    return (testingModels[u.id] || []).includes(m)
  }

  function modelState(u: { id: string }, m: string): ModelTestState | undefined {
    return modelStatesByUpstream[u.id]?.[m]
  }

  function modelStateBadge(u: { id: string }, m: string): 'default' | 'blue' | 'green' | 'red' | 'gray' {
    const s = modelState(u, m)?.status
    if (s === 'ok') return 'green'
    if (s === 'fail') return 'red'
    if (s === 'testing') return 'blue'
    return 'gray'
  }

  function modelStateText(u: { id: string }, m: string): string {
    const s = modelState(u, m)
    if (!s || s.status === 'idle') return '未测试'
    if (s.status === 'testing') return '测试中'
    if (s.status === 'ok') return `通过 ${s.latency ?? ''}ms`
    return '失败'
  }

  function modelStateDetail(u: { id: string }, m: string): string {
    return modelState(u, m)?.detail || ''
  }

  async function testModel(u: { id: string; name: string }, m: string) {
    if (isTesting(u, m)) return
    testingModels[u.id].push(m)
    modelStatesByUpstream[u.id][m] = { status: 'testing' }
    const start = Date.now()
    try {
      const res: any = await testUpstreamModel(u.id, { model: m })
      const latency = Date.now() - start
      if (res.ok) {
        modelStatesByUpstream[u.id][m] = { status: 'ok', latency, detail: res.content || '（无文本回复）' }
        ElMessageBox.alert(`模型: ${m}\n耗时: ${latency} ms\n\n回复: ${res.content}`, `模型测试成功（${u.name}）`, {
          confirmButtonText: '知道了',
        })
      } else {
        modelStatesByUpstream[u.id][m] = { status: 'fail', detail: res.error || '测试失败' }
        ElMessage.error(res.error || '测试失败')
      }
    } catch (e: any) {
      const msg = e?.response?.data?.error || e?.response?.data?.detail || '测试请求失败'
      modelStatesByUpstream[u.id][m] = { status: 'fail', detail: msg }
      ElMessage.error(msg)
    } finally {
      testingModels[u.id] = testingModels[u.id].filter((x) => x !== m)
    }
  }

  async function testModels(u: { id: string; name: string }, models: string[]) {
    if (!models.length) {
      ElMessage.warning('暂无可测试的模型')
      return
    }
    if (testingAll[u.id]) return
    testingAll[u.id] = true
    modelExpanded[u.id] = true
    let okCount = 0
    let failCount = 0
    for (let i = 0; i < models.length; i++) {
      const m = models[i]
      testProgress[u.id] = `${i + 1}/${models.length}`
      testingModels[u.id].push(m)
      modelStatesByUpstream[u.id][m] = { status: 'testing' }
      const start = Date.now()
      try {
        const res: any = await testUpstreamModel(u.id, { model: m })
        if (res.ok) {
          okCount++
          modelStatesByUpstream[u.id][m] = {
            status: 'ok', latency: Date.now() - start, detail: res.content || '（无文本回复）',
          }
        } else {
          failCount++
          modelStatesByUpstream[u.id][m] = { status: 'fail', detail: res.error || '测试失败' }
        }
      } catch (e: any) {
        failCount++
        modelStatesByUpstream[u.id][m] = {
          status: 'fail',
          detail: e?.response?.data?.error || e?.response?.data?.detail || '测试请求失败',
        }
      } finally {
        testingModels[u.id] = testingModels[u.id].filter((x) => x !== m)
      }
    }
    delete testProgress[u.id]
    testingAll[u.id] = false
    ElMessageBox.alert(
      `上游「${u.name}」共 ${models.length} 个模型\n通过: ${okCount} 个\n失败: ${failCount} 个`,
      '测试完成',
      { confirmButtonText: '知道了' },
    )
  }

  const testAllModels = (u: { id: string; name: string }) =>
    testModels(u, (modelsByUpstream[u.id] || []).map((e) => e.name))

  const batchTest = (u: { id: string; name: string }) => testModels(u, selectedModels(u))

  async function removeModel(u: { id: string; name: string }, m: string) {
    try {
      await ElMessageBox.confirm(`确定从上游「${u.name}」移除模型「${m}」吗？`, '移除确认', {
        type: 'warning', confirmButtonText: '确定', cancelButtonText: '取消',
      })
    } catch {
      return
    }
    try {
      await deleteUpstreamModel(u.id, m)
      modelsByUpstream[u.id] = (modelsByUpstream[u.id] || []).filter((x) => x.name !== m)
      delete modelStatesByUpstream[u.id][m]
      ElMessage.success(`已移除模型「${m}」`)
    } catch (e: any) {
      ElMessage.error(e?.response?.data?.detail || '移除失败')
    }
  }

  return {
    // state
    modelsByUpstream, remoteModelsByUpstream, remoteChecked, fetchSearch, fetchPanelOpen,
    fetchingIds, modelStatesByUpstream, testingModels, modelExpanded, testingAll, testProgress,
    modelSelected, togglingModels,
    // actions
    initUpstream, setModels, openFetchPanel, fetchRemoteModels, filteredRemoteModels,
    selectedRemoteCount, toggleSelectAll, handleJoin, addModels, mergeModels,
    setModelProtocol, handleToggleModel, initModelSortable, initAllSortables,
    visibleModels, toggleExpand, allSelected, toggleSelectAllModels, selectedModelCount,
    selectedModels, batchDelete, isTesting, modelState, modelStateBadge, modelStateText,
    modelStateDetail, testModel, testModels, testAllModels, batchTest, removeModel,
  }
}

export type UpstreamModels = ReturnType<typeof useUpstreamModels>
