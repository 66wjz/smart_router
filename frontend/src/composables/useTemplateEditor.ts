/**
 * 探测模板的编辑与保存（CH-026 从 Aggregated.vue 抽出）
 *
 * 状态（弹窗开关/表单/保存中）由调用方持有，本 composable 只封装
 * 「打开表单 → 回填 → 校验 → 提交 → 刷新」这套动作。
 */
import { ElMessage } from 'element-plus'
import { confirmDanger } from '@/components/base/BaseConfirm'
import { normalizeSchedule, validateSchedule } from '@/components/aggregation/schedule'
import {
  createProbeTemplate,
  deleteProbeTemplate,
  updateProbeTemplate,
  type ProbeTemplate,
} from '@/api/aggregations'
import { reloadConfig } from '@/api/common'
import type { ProbeFormModel } from '@/components/probe/ProbeSettingsForm.vue'

export interface TemplateFormState {
  name: string
  remark: string
}

export interface TemplateEditorOptions {
  /** 复用的空探测表单工厂（避免循环依赖） */
  emptyProbeForm: () => ProbeFormModel
  /** 保存成功后刷新数据 */
  onSaved: () => Promise<void> | void
}

export function useTemplateEditor(
  form: TemplateFormState,
  probeForm: { value: ProbeFormModel },
  opts: TemplateEditorOptions,
) {
  const openCreate = (open: () => void) => {
    form.name = ''
    form.remark = ''
    probeForm.value = { ...opts.emptyProbeForm(), enabled: true, interval_seconds: 300, sort_mode: 'stable' }
    open()
  }

  const openEdit = (t: ProbeTemplate, open: () => void) => {
    form.name = t.name
    form.remark = t.remark || ''
    probeForm.value = {
      enabled: true,
      template_id: null,
      interval_seconds: t.interval_seconds,
      slow_threshold_seconds: t.slow_threshold_seconds,
      sort_mode: t.sort_mode,
      schedule: {
        mode: t.schedule?.mode === 'window' ? 'window' : 'always',
        days: [...(t.schedule?.days || [])],
        windows: (t.schedule?.windows || []).map((w: any) => ({ start: w.start, end: w.end })),
      },
    }
    open()
  }

  /** 校验并保存；返回 true=成功（调用方据此关闭弹窗） */
  async function save(templateId: number | null): Promise<boolean> {
    const name = form.name.trim()
    if (!name) {
      ElMessage.warning('模板名不能为空')
      return false
    }
    const interval = Number(probeForm.value.interval_seconds) || 0
    if (interval < 10) {
      ElMessage.warning('探测间隔不能小于 10 秒')
      return false
    }
    const err = validateSchedule(probeForm.value.schedule)
    if (err) {
      ElMessage.warning(err)
      return false
    }

    const payload = {
      name,
      interval_seconds: interval,
      slow_threshold_seconds: probeForm.value.slow_threshold_seconds,
      sort_mode: probeForm.value.sort_mode,
      schedule: normalizeSchedule(probeForm.value.schedule),
      remark: form.remark,
    }
    try {
      if (templateId) await updateProbeTemplate(templateId, payload as any)
      else await createProbeTemplate(payload as any)
      ElMessage.success('模板已保存')
      await reloadConfig()
      await opts.onSaved()
      return true
    } catch (e: any) {
      ElMessage.error(e?.response?.data?.detail || '保存失败')
      return false
    }
  }

  /** 删除模板（含引用提示）；返回 true=已删除 */
  async function remove(t: ProbeTemplate): Promise<boolean> {
    const refs = t.ref_names || []
    const message = refs.length
      ? `模板「${t.name}」正被 ${refs.length} 个聚合使用（${refs.join('、')}）。删除后这些聚合将回退到自配参数。确认删除？`
      : `确定删除模板「${t.name}」吗？`
    if (!await confirmDanger(message, '删除模板')) return false
    try {
      await deleteProbeTemplate(t.id)
      ElMessage.success('模板已删除')
      await reloadConfig()
      await opts.onSaved()
      return true
    } catch (e: any) {
      ElMessage.error(e?.response?.data?.detail || '删除失败')
      return false
    }
  }

  return { openCreate, openEdit, save, remove }
}
