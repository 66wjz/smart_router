/**
 * 列表页二级组件 —— 公共类型（CH-042）
 *
 * 这里只定义「页面里怎么描述一个列表」，不涉及数据获取。
 */

/** 表格列定义：对齐 el-table-column 的常用能力，够用即可 */
export interface DataColumn {
  /** 取值字段名，同时作为默认插槽名 cell-{key} */
  key: string
  label: string
  width?: number | string
  minWidth?: number | string
  /** 固定列：右侧操作列常用 'right' */
  fixed?: boolean | 'left' | 'right'
  align?: 'left' | 'center' | 'right'
  sortable?: boolean
  /** 超长省略 + 悬浮提示，默认 true */
  ellipsis?: boolean
  /** 自定义单元格插槽名，默认 cell-{key} */
  slot?: string
  /** 自定义表头插槽名，默认 header-{key} */
  headerSlot?: string
  /** 纯展示用的列（不参与排序、无插槽） */
  formatter?: (row: any) => string
}

/** 列表页密度：compact 对齐现有 size="small" 的观感 */
export type ListDensity = 'compact' | 'default'

/** 指标卡语义色 */
export type StatTone = 'default' | 'primary' | 'success' | 'warning' | 'danger'

/** 行内操作项：配合 RowActions 使用 */
export interface RowActionItem {
  label: string
  onClick?: () => void
  variant?: 'primary' | 'ghost' | 'danger' | 'secondary'
  disabled?: boolean
  /** 在这一项之前插一条竖线分隔 */
  divider?: boolean
}
