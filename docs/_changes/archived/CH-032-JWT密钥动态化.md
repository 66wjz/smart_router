# CH-032 JWT 签名密钥改为动态获取

> 类型：B 线-小（安全加固，行为兼容）
> 状态：已实现（本地验证通过，未 push 未部署）
> 日期：2026-10-18

---

## 一、背景

CH-031 推送 GitHub 时发现 `backend/app/core/security.py:13` 把 `JWT_SECRET` 硬编码在源码里：

```python
JWT_SECRET = "smart-router-jwt-secret-2026"
```

代码公开后，任何人拿到源码即可用该密钥签发合法 JWT，伪造管理后台登录态（`verify_jwt` 只校验签名与 `exp`，不校验签发来源）。用户明确要求「这种肯定不行」，登记在 `docs/需求规格.md` 9.2，本次实现。

---

## 二、分类（铁律 7）

**B 线-小**：不改任何对外接口与业务行为，只换密钥来源。

---

## 三、现状分析

| 项 | 现状 |
|----|------|
| 密钥来源 | 源码常量，全仓唯一，无环境变量覆盖 |
| 使用点 | `create_jwt()` 签发、`verify_jwt()` 校验（`security.py` 内） |
| 外部引用 | `main.py:25` `from app.core.security import JWT_SECRET`——**导入后未使用**（死导入） |
| 数据库 | `sys_setting` 为 key-value 表，可存字符串，已有 `SettingRepository.get/set` |
| 影响面 | 管理后台登录态。更换密钥 = 所有已登录会话失效，需重新登录（可接受） |

---

## 四、方案

### 4.1 密钥优先级

```
SR_JWT_SECRET 环境变量  >  sys_setting.jwt_secret  >  首次启动自动生成并落库
```

- **环境变量优先**：多实例 / 容器化部署时可显式统一，也便于运维轮换。
- **自动生成并落库**：单机部署零配置即可；密钥不落在源码里，且重启后会话不失效（避免每次重启踢人）。
- **生成方式**：`secrets.token_urlsafe(48)`（约 64 字符，384 bit 熵）。

### 4.2 代码改动

`backend/app/core/security.py`：
- 删除模块级常量 `JWT_SECRET`
- 新增 `get_jwt_secret()`：三级取值 + 进程内缓存（`threading.Lock` 保护，避免并发首次调用重复生成）
- 数据库不可用时降级：回退到进程内随机密钥并 WARNING，服务仍可启动（重启后会话失效）
- `create_jwt()` / `verify_jwt()` 改为调用 `get_jwt_secret()`

`backend/app/main.py`：
- 删除未使用的 `from app.core.security import JWT_SECRET`

### 4.3 不做的事

- **不引入 `python-dotenv`**：项目当前无 `.env` 加载机制，为一行环境变量引依赖属过度设计；环境变量由 systemd / 启动脚本注入即可
- **不提供「查看密钥」接口**：密钥无展示必要，避免二次泄露
- **不做密钥轮换 UI**：轮换 = 改环境变量或删 `sys_setting.jwt_secret` 后重启，文档说明即可
- **不改密码哈希**：管理员密码仍为明文对比，属另一问题（本次不动，避免范围蔓延）

---

## 五、受影响文档（按 change-impact-checklist 逐项判定）

| # | 文档 | 受影响 | 理由 |
|---|------|--------|------|
| 1 | `README.md` | 是 | 部署章节补 `SR_JWT_SECRET` 说明 |
| 2 | `docs/需求规格.md` | 是 | 9.2 已实现，从「待完善事项」移除（原 9.3 顺延回 9.2） |
| 3 | `docs/架构设计.md` | 是 | `security.py` 职责说明补密钥来源 |
| 4 | `docs/数据库设计.md` | 是 | 3.9 新增 `jwt_secret` 键 |
| 5 | `docs/API契约.md` | 否 | 登录接口出入参不变 |
| 6 | `docs/接口文档.md` | 否 | 同上 |
| 7 | `docs/系统核心流程.md` | 否 | 登录流程步骤不变，仅密钥来源变 |
| 8 | `docs/面向客户的功能清单.md` | 否 | 无功能变化 |
| 9 | `docs/五列对应矩阵.md` | 否 | 无实体/表/API 变化 |
| 10 | `docs/变更记录.md` | 总是 | 追加 CH-032 |
| 11 | `.devflow/STATE.md` | 是 | 记录 CH-032 |

---

## 六、验收标准

1. **源码无密钥**：全仓 grep 不再有 `smart-router-jwt-secret-2026`
2. **零配置可用**：空库 `seed.py` → 启动 → 登录成功；`sys_setting.jwt_secret` 已写入随机值
3. **重启不踢人**：登录拿 token → 停服务 → 重启 → 旧 token 仍可访问管理接口
4. **环境变量优先**：设 `SR_JWT_SECRET` 启动，`sys_setting.jwt_secret` 不生成/不生效；用它签发的 token 可通过校验，旧 token 失效
5. **降级可用**：数据库不可用时服务仍能启动（记录 WARNING），不崩溃
6. **回归通过**：`verify_api_ch023` / `verify_rule_binding_ch024` / `verify_aggregation_ch023`
7. **编译通过**：后端 `compileall` 0 错误

---

## 七、风险与回退

| 风险 | 影响 | 缓解 |
|------|------|------|
| 首次升级后所有会话失效 | 用户需重新登录一次 | 属预期；文档注明 |
| `seed.py` 重建库会清掉 `jwt_secret` | 重跑 seed 后会话失效 | 属预期（seed 本身是破坏性操作） |
| 并发首次调用生成两个密钥 | 一个会话随机失效 | `threading.Lock` + 进程内缓存 |
| 多实例部署未设环境变量 | 各实例密钥不同，token 互不认 | 文档明确「多实例必须设 `SR_JWT_SECRET`」 |

回退：`git revert` 本次提交，行为恢复为固定常量密钥（不推荐，仅作应急）。

---

## 八、实际验证结果（2026-10-18）

| 验收标准 | 结果 | 证据 |
|---------|------|------|
| 1. 源码无密钥 | 通过 | `backend/` 全量 grep `smart-router-jwt-secret-2026` 0 命中（仅剩历史文档记载） |
| 2. 零配置可用 | 通过 | 临时库 `seed.py` → uvicorn → `POST /admin/api/login` 拿到 token → `GET /admin/api/upstreams` 200；`sys_setting.jwt_secret` 落库长度 64 |
| 3. 重启不踢人 | 通过 | 进程终止后重启，用重启前 token 访问 `GET /admin/api/upstreams` 仍 200 |
| 4. 环境变量优先 | 通过 | 设 `SR_JWT_SECRET=env-override-secret-for-test` 后 `get_jwt_secret()` 返回该值；此前签发的 token 立即失效，新 token 正常 |
| 5. 降级可用 | 通过 | `SMART_ROUTER_DB` 指向不存在目录，`get_jwt_secret()` 不抛异常，返回进程内随机密钥并打 WARNING |
| 6. 回归通过 | 通过 | `verify_api_ch023` / `verify_rule_binding_ch024` / `verify_aggregation_ch023` / `verify_migration_ch023` 全部「结果: 全部通过」 |
| 7. 编译通过 | 通过 | `compileall backend/app backend/seed.py backend/run.py` 退出码 0 |

补充验证：用旧硬编码密钥手工伪造的 token（`sub=admin`，未来过期）在 `verify_jwt()` 返回 `None`——**历史泄露的密钥已彻底失效**。
