# 基础组件库

> 完整约定与组件清单见 [docs/架构设计.md 第 6.6 节](../../../../docs/架构设计.md)。

## 为什么有些组件没人引用

这个目录是**刻意全量封装**的基础组件库：把后台常用的基础能力一次性备齐，**不要求每个组件当下都有引用**。

暂时没场景的组件（`BaseTable` / `BaseSelect` / `BaseAlert` / `BaseSpinner` / `BaseAvatar` / `BaseCalendarPicker`）**是有意保留**，供后续新页面直接取用，**不是待清理项**。仅在确认某个组件永远用不到时才删除，且删除需单独提一次变更。

## 使用约定

1. 新页面**优先**从这里取组件，不要照抄旧页面的原生 `el-*` 拼装。
2. 缺能力时**先在这里补封装**，再在页面里用；不要写一次性模板。
3. 与 `el-*` 语义不对等时（如 `BaseTable` 无固定列/展开行），按页面实际需求选，**不做机械替换**——功能退化比不统一更糟。
4. 新增/删除组件时同步更新架构设计 6.6 的清单。

## 清单

| 组件 | 用途 |
|------|------|
| `BaseSection` | 页面区块（标题 + actions 插槽 + card/plain 变体） |
| `BaseCard` | 卡片容器 |
| `BaseButton` | 按钮（primary/ghost/danger/icon + sm 尺寸） |
| `BaseInput` | 输入框（含 textarea / password） |
| `BaseBadge` | 状态徽标（多色变体） |
| `BaseCheckTag` | 可勾选标签 |
| `BaseModal` | 弹窗（size / layer 层级） |
| `BaseModalFooter` | 弹窗底部「取消 + 确定 + loading」 |
| `BaseFormGroup` | 表单字段（label / required / error / hint） |
| `BaseEmptyState` | 空态（默认大留白 / `compact` 区块内小块占位） |
| `BaseNotice` | 页面级说明条（info/warning/error/success + 可关闭） |
| `BaseHint` | 说明文字（段落 / block / inline 三版式） |
| `BasePagination` | 分页（显式 `show` 控制） |
| `BaseIcon` | 内联 SVG 图标集 |
| `BaseConfirm.ts` | 命令式确认（`confirmDanger` / `confirmAction`，返回 boolean 不抛异常） |
| `BaseTable` | 自研表格（列配置 / 排序 / 多选 / 密度）— 待启用 |
| `BaseSelect` | 自定义下拉（Teleport 定位，不受弹窗裁剪）— 待启用 |
| `BaseAlert` | 简洁提示条（`BaseNotice` 的轻量版）— 待启用 |
| `BaseSpinner` | 加载指示器（sm/md/lg + 文案）— 待启用 |
| `BaseAvatar` | 头像（首字母 + 多色）— 待启用 |
| `BaseCalendarPicker` | 自定义日历选择器 — 待启用 |

布局组件（`BaseSidebar`）在 `components/layout/`。
