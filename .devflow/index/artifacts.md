# 项目产出物索引

> 所有阶段的产出物都在这里登记。门禁检查时，AI 会核对这个清单。
> 注：本项目 v4 产出物为追溯补建登记；v5 重构产出物为正式流程登记。

## v4（历史，追溯登记）

| 阶段 | 产出物 | 路径 | 状态 | 创建时间 |
|------|--------|------|------|---------|
| stage-3 | 路由引擎 | core/router_engine.py | ✅ 存在（v5 将迁移） | -（追溯） |
| stage-3 | 配置加载 | core/config.py | ✅ 存在（v5 将重写） | -（追溯） |
| stage-3 | 健康检查/探测 | core/health.py + core/probe.py | ✅ 存在（v5 将迁移） | -（追溯） |
| stage-3 | 上下文/响应处理 | core/context.py | ✅ 存在（v5 将迁移） | -（追溯） |
| stage-3 | 管理 API | admin/api.py | ✅ 存在（v5 将拆分） | -（追溯） |
| stage-3 | 主服务 | router.py | ✅ 存在（v5 将重组） | -（追溯） |
| stage-3 | 上游适配器 | upstream/ | ✅ 存在（v5 将迁移） | -（追溯） |
| stage-4 | Streamlit 管理后台 | admin/streamlit_app.py | 🔄 将被 Vue3 替换 | -（追溯） |

## v5（正式流程，当前）

| 阶段 | 产出物 | 路径 | 状态 | 创建时间 |
|------|--------|------|------|---------|
| stage-1 | 需求规格 | docs/需求规格.md | ✅ approved（用户确认） | 2026-08-09 |
| stage-1 | 面向客户的功能清单（含演示验证清单） | docs/面向客户的功能清单.md | ✅ approved（用户确认） | 2026-08-09 |
| stage-2 | 架构设计（含流程图/时序图） | docs/架构设计.md | ✅ created（待确认） | 2026-08-09 |
| stage-2 | 数据库设计 | docs/数据库设计.md | ✅ created（待确认） | 2026-08-09 |
| stage-2 | API 契约 | docs/API契约.md | ✅ created（待确认） | 2026-08-09 |
| stage-2 | 五列对应矩阵 | docs/五列对应矩阵.md | ✅ created（待确认） | 2026-08-09 |
| stage-2 | 系统核心流程 | docs/系统核心流程.md | ✅ created（待确认） | 2026-08-09 |
| stage-2 | 建表 SQL | sql/01_建表.sql | ✅ created | 2026-08-09 |
| stage-2 | 初始数据 SQL | sql/02_init_data.sql | ✅ created | 2026-08-09 |

> 状态枚举：空（未创建）/ pending / created / reviewed / approved
