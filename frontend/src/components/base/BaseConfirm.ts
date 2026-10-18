import { ElMessageBox } from 'element-plus'

/**
 * 危险操作确认（统一封装 ElMessageBox.confirm）
 *
 * 用法：
 *   if (!await confirmDanger('确定删除规则「X」吗？')) return
 *
 * 返回 true = 用户确认；false = 取消（不抛异常，调用方无需 try/catch）
 */
export async function confirmDanger(
  message: string,
  title = '删除确认',
  confirmText = '确定',
): Promise<boolean> {
  try {
    await ElMessageBox.confirm(message, title, {
      type: 'warning',
      confirmButtonText: confirmText,
      cancelButtonText: '取消',
    })
    return true
  } catch {
    return false
  }
}

/**
 * 普通确认（无 warning 图标，用于「恢复自动」等中性操作）
 */
export async function confirmAction(
  message: string,
  title: string,
  confirmText = '确定',
): Promise<boolean> {
  try {
    await ElMessageBox.confirm(message, title, {
      confirmButtonText: confirmText,
      cancelButtonText: '取消',
    })
    return true
  } catch {
    return false
  }
}
