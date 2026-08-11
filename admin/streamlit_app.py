"""
Smart Router 管理后台 v2 - Streamlit 版
端口: 10003
功能: 上游源管理、路由规则编辑、延迟面板、系统设置
"""

import os
import sys

import requests
import streamlit as st
import yaml

# 确保项目根目录在 path 中
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

# ============================================================
# 配置
# ============================================================
ROUTER_URL = os.environ.get("ROUTER_URL", "http://127.0.0.1:10002")
CONFIG_PATH = os.path.join(ROOT_DIR, "config.yaml")

# ============================================================
# 自定义样式
# ============================================================
CUSTOM_CSS = """
<style>
/* 全局 */
.block-container {
    padding-top: 2rem;
    padding-bottom: 2rem;
    max-width: 1200px;
}

/* 侧边栏 */
section[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #1a1a2e 0%, #16213e 100%);
}
section[data-testid="stSidebar"] .stMarkdown, 
section[data-testid="stSidebar"] label,
section[data-testid="stSidebar"] p,
section[data-testid="stSidebar"] span {
    color: #e0e0e0 !important;
}
section[data-testid="stSidebar"] [data-testid="stSidebarNav"] {
    display: none;
}

/* 卡片容器 */
.metric-card {
    background: #ffffff;
    border: 1px solid #e8e8e8;
    border-radius: 12px;
    padding: 1.5rem;
    box-shadow: 0 2px 8px rgba(0,0,0,0.04);
    text-align: center;
    transition: box-shadow 0.2s;
}
.metric-card:hover {
    box-shadow: 0 4px 16px rgba(0,0,0,0.08);
}
.metric-card .label {
    font-size: 0.85rem;
    color: #888;
    margin-bottom: 0.3rem;
}
.metric-card .value {
    font-size: 2rem;
    font-weight: 700;
    color: #1a1a2e;
}
.metric-card .sub {
    font-size: 0.8rem;
    margin-top: 0.2rem;
}

/* 状态标签 */
.status-ok {
    display: inline-block;
    background: #e8f5e9;
    color: #2e7d32;
    padding: 2px 10px;
    border-radius: 12px;
    font-size: 0.82rem;
    font-weight: 500;
}
.status-down {
    display: inline-block;
    background: #ffebee;
    color: #c62828;
    padding: 2px 10px;
    border-radius: 12px;
    font-size: 0.82rem;
    font-weight: 500;
}
.status-unknown {
    display: inline-block;
    background: #f5f5f5;
    color: #757575;
    padding: 2px 10px;
    border-radius: 12px;
    font-size: 0.82rem;
    font-weight: 500;
}

/* 上游源卡片 */
.upstream-card {
    background: #fafbfc;
    border: 1px solid #e1e4e8;
    border-radius: 10px;
    padding: 1.2rem;
    margin-bottom: 1rem;
}
.upstream-card .header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 0.8rem;
}
.upstream-card .title {
    font-size: 1.1rem;
    font-weight: 600;
    color: #1a1a2e;
}
.upstream-card .badge {
    display: inline-block;
    background: #e3f2fd;
    color: #1565c0;
    padding: 2px 10px;
    border-radius: 12px;
    font-size: 0.78rem;
    font-weight: 500;
}

/* 规则卡片 */
.rule-card {
    background: #fafbfc;
    border: 1px solid #e1e4e8;
    border-radius: 10px;
    padding: 1.2rem;
    margin-bottom: 1rem;
}
.rule-card .rule-header {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    margin-bottom: 0.8rem;
}
.rule-card .rule-name {
    font-size: 1.05rem;
    font-weight: 600;
    color: #1a1a2e;
}
.rule-card .match-badge {
    display: inline-block;
    background: #fff3e0;
    color: #e65100;
    padding: 2px 10px;
    border-radius: 12px;
    font-size: 0.78rem;
    font-weight: 500;
}

/* 优先级标签 */
.priority-tag {
    display: inline-block;
    background: #e8eaf6;
    color: #283593;
    padding: 2px 8px;
    border-radius: 8px;
    font-size: 0.78rem;
    font-weight: 600;
    margin-bottom: 0.5rem;
}

/* 按钮 */
.stButton > button[kind="primary"] {
    border-radius: 8px;
}
.stButton > button {
    border-radius: 8px;
}

/* DataFrame 美化 */
.stDataFrame {
    border-radius: 8px;
    overflow: hidden;
}

/* 表单 */
.stForm {
    border: 1px solid #e8e8e8;
    border-radius: 12px;
    padding: 1.5rem;
    background: #fafbfc;
}
</style>
"""

# ============================================================
# 页面配置
# ============================================================
st.set_page_config(
    page_title="Smart Router 管理后台",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="expanded",
)
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

# ============================================================
# Session State 初始化
# ============================================================
_ss = st.session_state
if "logged_in" not in _ss:
    _ss.logged_in = False
if "jwt_token" not in _ss:
    _ss.jwt_token = ""
if "upstream_models" not in _ss:
    _ss.upstream_models = {}  # {upstream_id: [model_name, ...]}
if "selected_models" not in _ss:
    _ss.selected_models = {}  # {upstream_id: [selected_model, ...]}


# ============================================================
# API 调用封装
# ============================================================
def api_headers():
    return {"Authorization": f"Bearer {_ss.jwt_token}"}


def api_get(path, use_auth=True):
    headers = api_headers() if use_auth else {}
    try:
        return requests.get(f"{ROUTER_URL}{path}", headers=headers, timeout=10)
    except requests.RequestException:
        return None


def api_post(path, data=None, use_auth=True):
    headers = api_headers() if use_auth else {}
    headers["Content-Type"] = "application/json"
    try:
        return requests.post(f"{ROUTER_URL}{path}", json=data, headers=headers, timeout=10)
    except requests.RequestException:
        return None


def api_put(path, data=None):
    headers = api_headers()
    headers["Content-Type"] = "application/json"
    try:
        return requests.put(f"{ROUTER_URL}{path}", json=data, headers=headers, timeout=10)
    except requests.RequestException:
        return None


def api_delete(path):
    try:
        return requests.delete(f"{ROUTER_URL}{path}", headers=api_headers(), timeout=10)
    except requests.RequestException:
        return None


def read_config_yaml():
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return {}


def save_config_yaml(data):
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
        return True
    except Exception:
        return False


def do_reload():
    r = api_post("/admin/api/reload")
    return r and r.status_code == 200


def get_upstreams_list():
    """获取上游源列表"""
    r = api_get("/admin/api/upstreams")
    if r and r.status_code == 200:
        return r.json().get("upstreams", [])
    return []


def get_real_api_key(upstream_id):
    """从 config.yaml 获取真实 API Key"""
    cfg = read_config_yaml()
    for u in cfg.get("upstreams", []):
        if u.get("id") == upstream_id:
            return u.get("api_key", "")
    return ""


def fetch_upstream_models(upstream_id, base_url, api_key):
    """从上游源拉取模型列表"""
    try:
        url = f"{base_url.rstrip('/')}/v1/models"
        resp = requests.get(
            url,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=30,
            verify=False,  # 部分上游源 SSL 证书可能不受信任
        )
        if resp.status_code == 200:
            models_data = resp.json().get("data", [])
            return sorted([m.get("id", "") for m in models_data])
    except Exception as e:
        import traceback
        traceback.print_exc()
    return None


# ============================================================
# 登录页面
# ============================================================
def login_page():
    _, col_center, _ = st.columns([1, 1.2, 1])
    with col_center:
        st.markdown("""
        <div style="text-align:center; padding-top: 60px; padding-bottom: 24px;">
            <div style="font-size: 3rem; margin-bottom: 8px;">🧠</div>
            <h1 style="margin:0; color:#1a1a2e;">Smart Router</h1>
            <p style="color:#888; font-size: 1rem; margin-top:4px;">AI 模型智能路由代理 · v4</p>
        </div>
        """, unsafe_allow_html=True)

        with st.form("login_form", border=True):
            username = st.text_input("用户名", placeholder="请输入用户名")
            password = st.text_input("密码", type="password", placeholder="请输入密码")
            submitted = st.form_submit_button("登 录", use_container_width=True)

            if submitted:
                if not username or not password:
                    st.warning("请输入用户名和密码")
                    return
                r = api_post("/admin/api/login", {"username": username, "password": password}, use_auth=False)
                if r and r.status_code == 200:
                    token = r.json().get("token", "")
                    _ss.logged_in = True
                    _ss.jwt_token = token
                    st.rerun()
                else:
                    detail = r.json().get("detail", "登录失败") if r else "无法连接路由服务"
                    st.error(f"登录失败: {detail}")


# ============================================================
# 仪表盘页面
# ============================================================
def dashboard_page():
    r = api_get("/admin/api/dashboard")
    if not r or r.status_code != 200:
        st.error("无法获取仪表盘数据")
        return

    data = r.json()
    ok = data.get("model_ok", 0)
    down = data.get("model_down", 0)
    total = ok + down
    rate = f"{ok / total * 100:.0f}%" if total > 0 else "N/A"
    rate_color = "#2e7d32" if total > 0 and ok / total >= 0.7 else "#e65100" if total > 0 else "#888"

    # 指标卡片
    c1, c2, c3, c4, c5 = st.columns(5)
    with c1:
        st.markdown(f"""
        <div class="metric-card">
            <div class="label">上游源数</div>
            <div class="value">{data.get('upstream_count', 0)}</div>
        </div>
        """, unsafe_allow_html=True)
    with c2:
        st.markdown(f"""
        <div class="metric-card">
            <div class="label">候选模型数</div>
            <div class="value">{data.get('model_count', 0)}</div>
        </div>
        """, unsafe_allow_html=True)
    with c3:
        st.markdown(f"""
        <div class="metric-card">
            <div class="label">模型可用率</div>
            <div class="value" style="color:{rate_color}">{rate}</div>
            <div class="sub">{ok} 可用 / {down} 不可用</div>
        </div>
        """, unsafe_allow_html=True)
    with c4:
        st.markdown(f"""
        <div class="metric-card">
            <div class="label">路由规则数</div>
            <div class="value">{data.get('rule_count', 0)}</div>
        </div>
        """, unsafe_allow_html=True)
    with c5:
        key_count = len(data.get('api_keys', [])) if 'api_keys' in data else data.get('api_key_count', 0)
        st.markdown(f"""
        <div class="metric-card">
            <div class="label">API Key 数</div>
            <div class="value">{key_count}</div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("---")

    # 健康状态 + 快速操作
    col_left, col_right = st.columns([2, 1])

    with col_left:
        st.markdown("#### 模型故障状态")
        health = data.get("health", {})
        fails = health.get("fails", {})
        cooldown = health.get("cooldown", {})

        if fails:
            for model, count in fails.items():
                remaining = cooldown.get(model, 0)
                if remaining > 0:
                    st.markdown(f"""
                    <div style="display:flex; align-items:center; gap:8px; padding:6px 0;">
                        <span class="status-down">故障</span>
                        <strong>{model}</strong>
                        <span style="color:#888;">— 连续失败 {count} 次，冷却剩余 {remaining}s</span>
                    </div>
                    """, unsafe_allow_html=True)
                else:
                    st.markdown(f"""
                    <div style="display:flex; align-items:center; gap:8px; padding:6px 0;">
                        <span class="status-ok">已恢复</span>
                        <strong>{model}</strong>
                        <span style="color:#888;">— 失败 {count} 次</span>
                    </div>
                    """, unsafe_allow_html=True)
        else:
            st.markdown("""
            <div style="display:flex; align-items:center; gap:8px; padding:6px 0;">
                <span class="status-ok">正常</span>
                <span>所有模型正常运行，无故障记录</span>
            </div>
            """, unsafe_allow_html=True)

    with col_right:
        st.markdown("#### 快速操作")
        if st.button("热重载配置", use_container_width=True, type="primary"):
            if do_reload():
                st.success("配置热重载成功")
                st.rerun()
            else:
                st.error("热重载失败")
        if st.button("刷新延迟数据", use_container_width=True):
            st.rerun()


# ============================================================
# API Key 管理页面
# ============================================================
def api_keys_page():
    st.markdown("#### 路由层 API Key 管理")
    st.caption("这些 Key 是客户端访问 Smart Router 的入场券。校验通过后，路由器会用各 upstream 自己的 Key 去访问模型提供商。")

    r = api_get("/admin/api/api-keys")
    if not r or r.status_code != 200:
        st.error("无法获取 API Key 列表")
        return

    api_keys = r.json().get("api_keys", [])

    # 当前 Key 列表
    if api_keys:
        st.markdown("**已有 Key**")
        for ak in api_keys:
            col_name, col_key, col_status, col_act = st.columns([2, 3, 1, 1])
            with col_name:
                st.markdown(f'<span style="font-weight:600;">{ak.get("name", "")}</span>', unsafe_allow_html=True)
            with col_key:
                st.code(ak.get("key_masked", ak.get("key", "")), language=None)
            with col_status:
                enabled = ak.get("enabled", True)
                if enabled:
                    st.markdown('<span class="status-ok">启用</span>', unsafe_allow_html=True)
                else:
                    st.markdown('<span class="status-down">禁用</span>', unsafe_allow_html=True)
            with col_act:
                full_key = ak.get("key", "")
                # 启用/禁用切换
                if enabled:
                    if st.button("禁用", key=f"disable_{full_key}"):
                        r2 = api_put(f"/admin/api/api-keys/{full_key}", {"enabled": False})
                        if r2 and r2.status_code == 200:
                            st.success("已禁用")
                            do_reload()
                            st.rerun()
                        else:
                            st.error("操作失败")
                else:
                    if st.button("启用", key=f"enable_{full_key}"):
                        r2 = api_put(f"/admin/api/api-keys/{full_key}", {"enabled": True})
                        if r2 and r2.status_code == 200:
                            st.success("已启用")
                            do_reload()
                            st.rerun()
                        else:
                            st.error("操作失败")

            # 第二行：复制完整 Key + 删除
            col_copy, col_del = st.columns([4, 1])
            with col_copy:
                st.caption(f"完整 Key: `{full_key}`")
            with col_del:
                if st.button("删除", key=f"del_key_{full_key}"):
                    r2 = api_delete(f"/admin/api/api-keys/{full_key}")
                    if r2 and r2.status_code == 200:
                        st.success("已删除")
                        do_reload()
                        st.rerun()
                    else:
                        st.error("删除失败")

            st.markdown("---")
    else:
        st.info("暂无 API Key，请在下方添加。")

    # 添加新 Key
    st.markdown("#### 添加新 Key")
    with st.form("add_api_key_form", border=True):
        c1, c2, c3 = st.columns([2, 3, 1])
        with c1:
            new_key_name = st.text_input("名称", placeholder="例: 扣子平台、开发测试")
        with c2:
            new_key_value = st.text_input("Key 值", type="password", placeholder="例: sk-my-key-123")
        with c3:
            new_key_enabled = st.checkbox("启用", value=True)

        # 自动生成建议
        if st.form_submit_button("生成随机 Key"):
            import secrets, string
            generated = "sk-sr-" + "".join(secrets.choice(string.ascii_lowercase + string.digits) for _ in range(28))
            st.info(f"建议 Key: `{generated}`（请复制后粘贴到上方）")

        submitted = st.form_submit_button("添加 Key", type="primary", use_container_width=True)
        if submitted:
            if not new_key_value:
                st.warning("Key 值为必填")
            else:
                result = api_post("/admin/api/api-keys", {
                    "name": new_key_name or "未命名",
                    "key": new_key_value,
                    "enabled": new_key_enabled,
                })
                if result and result.status_code == 200:
                    st.success(f"API Key 添加成功")
                    do_reload()
                    st.rerun()
                else:
                    detail = result.json().get("detail", "添加失败") if result else "请求失败"
                    st.error(f"添加失败: {detail}")


# ============================================================
# 上游源管理页面
# ============================================================
def upstreams_page():
    st.markdown("#### 上游源列表")
    upstreams = get_upstreams_list()

    if not upstreams:
        st.info("暂无上游源，请在下方添加。")
    else:
        for u in upstreams:
            uid = u.get("id", "")
            uname = u.get("name", "")
            fmt = u.get("format", "")
            base_url = u.get("base_url", "")
            masked_key = u.get("api_key", "")

            st.markdown(f"""
            <div class="upstream-card">
                <div class="header">
                    <div>
                        <span class="title">{uname}</span>
                        <span class="badge">{fmt}</span>
                    </div>
                </div>
                <div style="color:#666; font-size:0.85rem;">
                    ID: <code>{uid}</code> &nbsp;&middot;&nbsp;
                    Base URL: <code>{base_url}</code> &nbsp;&middot;&nbsp;
                    API Key: <code>{masked_key}</code>
                </div>
            </div>
            """, unsafe_allow_html=True)

            # 操作按钮区
            col_fetch, col_del = st.columns([3, 1])
            with col_fetch:
                if st.button(f"拉取模型列表", key=f"fetch_{uid}"):
                    real_key = get_real_api_key(uid)
                    with st.spinner("正在获取..."):
                        models = fetch_upstream_models(uid, base_url, real_key)
                    if models is not None:
                        _ss.upstream_models[uid] = models
                        st.success(f"获取到 {len(models)} 个模型")
                        st.rerun()
                    else:
                        st.error("获取模型列表失败")

            with col_del:
                if st.button(f"删除", key=f"del_{uid}"):
                    r2 = api_delete(f"/admin/api/upstreams/{uid}")
                    if r2 and r2.status_code == 200:
                        st.success(f"已删除上游源 {uid}")
                        do_reload()
                        st.rerun()
                    else:
                        st.error("删除失败")

            # 模型列表展示 + 选择
            if uid in _ss.upstream_models:
                model_list = _ss.upstream_models[uid]
                st.markdown(f"**{uname} 可用模型**（共 {len(model_list)} 个）")

                # 已选中的模型
                if uid not in _ss.selected_models:
                    _ss.selected_models[uid] = []

                selected = st.multiselect(
                    f"选择要加入路由的模型",
                    options=model_list,
                    default=_ss.selected_models.get(uid, []),
                    key=f"sel_{uid}",
                )
                _ss.selected_models[uid] = selected

                if selected:
                    st.caption(f"已选择 {len(selected)} 个模型，可在「路由规则」页面将它们加入候选")

            # 手动输入模型名（fallback）
            with st.expander("手动输入模型名", expanded=False):
                manual_models = st.text_input(
                    "输入模型名（逗号分隔）",
                    placeholder="例: mimo-v2.5-pro, mimo-v2.5",
                    key=f"manual_{uid}",
                )
                if st.button("添加", key=f"add_manual_{uid}"):
                    if manual_models.strip():
                        names = [n.strip() for n in manual_models.split(",") if n.strip()]
                        if uid not in _ss.upstream_models:
                            _ss.upstream_models[uid] = []
                        existing = set(_ss.upstream_models[uid])
                        for n in names:
                            if n not in existing:
                                _ss.upstream_models[uid].append(n)
                                existing.add(n)
                        _ss.upstream_models[uid].sort()
                        st.success(f"已添加 {len(names)} 个模型")
                        st.rerun()

            st.markdown("---")

    # 添加新上游源
    st.markdown("#### 添加上游源")
    with st.form("add_upstream_form", border=True):
        c1, c2 = st.columns(2)
        with c1:
            new_id = st.text_input("ID（唯一标识）", placeholder="例: newapi、xiaomi")
            new_base_url = st.text_input("Base URL", placeholder="例: http://124.222.235.3:10001")
        with c2:
            new_name = st.text_input("显示名称", placeholder="例: NewAPI 中转站")
            new_api_key = st.text_input("API Key", type="password", placeholder="sk-xxx...")
        new_format = st.selectbox("格式", ["openai", "anthropic"], index=0)

        submitted = st.form_submit_button("添加上游源", use_container_width=True, type="primary")
        if submitted:
            if not all([new_id, new_name, new_base_url, new_api_key]):
                st.warning("所有字段均为必填")
            else:
                result = api_post("/admin/api/upstreams", {
                    "id": new_id,
                    "name": new_name,
                    "base_url": new_base_url,
                    "api_key": new_api_key,
                    "format": new_format,
                })
                if result and result.status_code == 200:
                    st.success(f"上游源 {new_id} 添加成功")
                    do_reload()
                    st.rerun()
                else:
                    detail = result.json().get("detail", "添加失败") if result else "请求失败"
                    st.error(f"添加失败: {detail}")


# ============================================================
# 路由规则管理页面（核心交互升级）
# ============================================================
def rules_page():
    st.markdown("#### 路由规则管理")

    r = api_get("/admin/api/rules")
    if not r or r.status_code != 200:
        st.error("无法获取路由规则")
        return
    rules = r.json().get("rules", [])

    upstreams = get_upstreams_list()
    upstream_ids = [u["id"] for u in upstreams]

    # 当前规则展示
    for i, rule in enumerate(rules):
        match_desc = []
        m = rule.get("match", {})
        if m.get("has_image"):
            match_desc.append("含图片")
        if m.get("has_tools"):
            match_desc.append("含工具调用")
        if m.get("default"):
            match_desc.append("默认")
        match_str = " + ".join(match_desc) if match_desc else "无条件"
        candidates = rule.get("candidates", [])

        st.markdown(f"""
        <div class="rule-card">
            <div class="rule-header">
                <span class="rule-name">{rule.get('name', '')}</span>
                <span class="match-badge">{match_str}</span>
            </div>
        </div>
        """, unsafe_allow_html=True)

        # 按优先级分组
        priorities = {}
        for c in candidates:
            p = c.get("priority", 1)
            priorities.setdefault(p, []).append(c)

        for p in sorted(priorities.keys()):
            st.markdown(f'<span class="priority-tag">优先级 {p}</span>', unsafe_allow_html=True)
            p_cands = priorities[p]
            rows = []
            for c in p_cands:
                rows.append({
                    "模型": c.get("model", ""),
                    "上游源": c.get("upstream", ""),
                    "权重": c.get("weight", 1),
                    "最大上下文": c.get("max_context", "N/A"),
                    "最大输出": c.get("max_output", "N/A"),
                })
            st.dataframe(rows, use_container_width=True, hide_index=True)

    st.markdown("---")

    # ===================== 可视化规则编辑器 =====================
    st.markdown("#### 编辑路由规则")

    tab_visual, tab_yaml = st.tabs(["可视化编辑", "YAML 编辑"])

    with tab_visual:
        # 深拷贝 rules 供编辑
        if "editing_rules" not in _ss:
            _ss.editing_rules = rules

        rules_copy = _ss.editing_rules

        for i, rule in enumerate(rules_copy):
            m = rule.get("match", {})
            match_desc = []
            if m.get("has_image"):
                match_desc.append("含图片")
            if m.get("has_tools"):
                match_desc.append("含工具调用")
            if m.get("default"):
                match_desc.append("默认")
            match_str = " + ".join(match_desc) if match_desc else "无条件"

            with st.expander(f"规则 {i + 1}: {rule.get('name', '')} ({match_str})", expanded=False):
                # 规则名称
                new_name = st.text_input("规则名称", value=rule.get("name", ""), key=f"rname_{i}")
                rules_copy[i]["name"] = new_name

                # 候选模型列表
                cands = rule.get("candidates", [])

                # 展示现有候选 + 删除
                if cands:
                    st.markdown("**当前候选模型**")
                    for j, c in enumerate(cands):
                        cols = st.columns([4, 2, 1, 1, 1, 1])
                        with cols[0]:
                            st.text(c.get("model", ""))
                        with cols[1]:
                            st.text(f"上游: {c.get('upstream', '')}")
                        with cols[2]:
                            st.text(f"权重: {c.get('weight', 1)}")
                        with cols[3]:
                            st.text(f"P{c.get('priority', 1)}")
                        with cols[4]:
                            ctx = c.get("max_context", "N/A")
                            st.text(f"ctx:{ctx}")
                        with cols[5]:
                            if st.button("删除", key=f"del_cand_{i}_{j}"):
                                rules_copy[i]["candidates"].pop(j)
                                _ss.editing_rules = rules_copy
                                st.rerun()

                # 添加新候选模型
                st.markdown("**添加候选模型**")
                ac1, ac2, ac3, ac4, ac5, ac6 = st.columns([3, 2, 1, 1, 2, 2])

                with ac1:
                    # 选上游源，再选模型
                    new_upstream = st.selectbox("上游源", options=upstream_ids, key=f"new_up_{i}")

                    # 根据选中的上游源，展示可用模型
                    available_models = _ss.upstream_models.get(new_upstream, [])
                    # 同时包含当前规则已有的候选模型名（来自其他上游源）
                    if not available_models:
                        st.caption("请先在上游源管理中拉取模型列表")

                with ac2:
                    if available_models:
                        new_model = st.selectbox("模型", options=available_models, key=f"new_model_{i}")
                    else:
                        new_model = st.text_input("模型名（手动输入）", key=f"new_model_manual_{i}")

                with ac3:
                    new_weight = st.number_input("权重", value=3, min_value=1, max_value=10, key=f"new_w_{i}")

                with ac4:
                    new_priority = st.number_input("优先级", value=1, min_value=1, max_value=5, key=f"new_p_{i}")

                with ac5:
                    new_ctx = st.number_input("最大上下文", value=1000000, min_value=0, step=1000, key=f"new_ctx_{i}")

                with ac6:
                    new_out = st.number_input("最大输出", value=32768, min_value=0, step=1000, key=f"new_out_{i}")

                if st.button(f"+ 添加到候选", key=f"add_cand_{i}"):
                    if new_model:
                        rules_copy[i].setdefault("candidates", []).append({
                            "model": new_model,
                            "upstream": new_upstream,
                            "weight": new_weight,
                            "priority": new_priority,
                            "max_context": new_ctx,
                            "max_output": new_out,
                        })
                        _ss.editing_rules = rules_copy
                        st.success(f"已添加 {new_model}")
                        st.rerun()
                    else:
                        st.warning("请选择或输入模型名")

        # 保存按钮
        col_save, col_reset = st.columns(2)
        with col_save:
            if st.button("保存所有规则", type="primary", use_container_width=True):
                r2 = api_put("/admin/api/rules", {"rules": rules_copy})
                if r2 and r2.status_code == 200:
                    st.success("规则已保存并热重载")
                    do_reload()
                    if "editing_rules" in _ss:
                        del _ss.editing_rules
                    st.rerun()
                else:
                    st.error("保存失败")
        with col_reset:
            if st.button("重置编辑", use_container_width=True):
                if "editing_rules" in _ss:
                    del _ss.editing_rules
                st.rerun()

    with tab_yaml:
        st.caption("直接编辑 YAML 格式的路由规则。修改后将自动保存并热重载。")
        rules_yaml = yaml.dump(rules, default_flow_style=False, allow_unicode=True, sort_keys=False)
        edited_yaml = st.text_area("路由规则 (YAML)", value=rules_yaml, height=400, key="rules_yaml_editor")

        c1, c2 = st.columns(2)
        with c1:
            if st.button("保存 YAML 规则", type="primary", use_container_width=True):
                try:
                    parsed = yaml.safe_load(edited_yaml)
                    if not isinstance(parsed, list):
                        st.error("规则必须是列表格式")
                    else:
                        r2 = api_put("/admin/api/rules", {"rules": parsed})
                        if r2 and r2.status_code == 200:
                            st.success("规则已保存")
                            do_reload()
                        else:
                            st.error("保存失败")
                except yaml.YAMLError as e:
                    st.error(f"YAML 解析错误: {e}")
        with c2:
            if st.button("重新加载", use_container_width=True):
                st.rerun()


# ============================================================
# 模型别名（指针）管理页面
# ============================================================
def model_pointers_page():
    st.markdown("#### 模型别名管理")
    st.caption("模型别名是指针：客户端请求别名时，直接转发到指定的真实模型，不走路由规则。可在后台随时切换指向。")

    r = api_get("/admin/api/model-pointers")
    if not r or r.status_code != 200:
        st.error("无法获取模型别名")
        return

    pointers = r.json().get("pointers", [])
    upstreams = get_upstreams_list()
    upstream_ids = [u["id"] for u in upstreams]

    # 获取所有可用模型列表（从上游源拉取的缓存 + 路由规则中的候选）
    all_models = set()
    for uid, models in _ss.upstream_models.items():
        all_models.update(models)
    rules_r = api_get("/admin/api/rules")
    if rules_r and rules_r.status_code == 200:
        for rule in rules_r.json().get("rules", []):
            for c in rule.get("candidates", []):
                all_models.add(c.get("model", ""))
    all_models = sorted(all_models)

    # 当前别名列表
    if pointers:
        st.markdown("**当前别名**")
        for p in pointers:
            col_name, col_target, col_upstream, col_act = st.columns([2, 4, 2, 1])
            with col_name:
                st.markdown(f'<span style="font-weight:600; color:#1565c0;">{p.get("name", "")}</span>', unsafe_allow_html=True)
            with col_target:
                st.text(p.get("target_model", ""))
            with col_upstream:
                st.text(p.get("upstream", ""))
            with col_act:
                if st.button("删除", key=f"del_ptr_{p.get('name', '')}"):
                    r2 = api_delete(f"/admin/api/model-pointers/{p.get('name', '')}")
                    if r2 and r2.status_code == 200:
                        st.success(f"已删除别名 {p.get('name', '')}")
                        do_reload()
                        st.rerun()
                    else:
                        st.error("删除失败")
        st.markdown("---")
    else:
        st.info("暂无模型别名，在下方添加。")

    # 修改现有别名指向
    if pointers:
        st.markdown("#### 修改别名指向")
        pointer_names = [p.get("name", "") for p in pointers]
        sel_pointer = st.selectbox("选择别名", options=pointer_names, key="sel_pointer_edit")
        if sel_pointer:
            current = next((p for p in pointers if p.get("name") == sel_pointer), {})
            c1, c2 = st.columns(2)
            with c1:
                new_upstream = st.selectbox(
                    "上游源",
                    options=upstream_ids,
                    index=upstream_ids.index(current.get("upstream", "")) if current.get("upstream", "") in upstream_ids else 0,
                    key="ptr_edit_upstream",
                )
                available = _ss.upstream_models.get(new_upstream, [m for m in all_models])
            with c2:
                if available:
                    new_target = st.selectbox(
                        "目标模型",
                        options=available,
                        index=available.index(current.get("target_model", "")) if current.get("target_model", "") in available else 0,
                        key="ptr_edit_model",
                    )
                else:
                    new_target = st.text_input(
                        "目标模型（手动输入）",
                        value=current.get("target_model", ""),
                        key="ptr_edit_model_manual",
                    )
            if st.button("修改指向", type="primary", key="ptr_edit_btn"):
                r2 = api_put(f"/admin/api/model-pointers/{sel_pointer}", {
                    "target_model": new_target,
                    "upstream": new_upstream,
                })
                if r2 and r2.status_code == 200:
                    st.success(f"别名 {sel_pointer} 已指向 {new_target}")
                    do_reload()
                    st.rerun()
                else:
                    st.error("修改失败")
        st.markdown("---")

    # 添加新别名
    st.markdown("#### 添加新别名")
    with st.form("add_pointer_form", border=True):
        c1, c2, c3 = st.columns([2, 3, 2])
        with c1:
            new_name = st.text_input("别名名称", placeholder="例: my-model, gpt4")
        with c2:
            add_upstream = st.selectbox("上游源", options=upstream_ids, key="ptr_add_upstream")
            add_available = _ss.upstream_models.get(add_upstream, [m for m in all_models])
        with c3:
            if add_available:
                add_target = st.selectbox("目标模型", options=add_available, key="ptr_add_model")
            else:
                add_target = st.text_input("目标模型（手动输入）", placeholder="例: mistralai/mistral-large", key="ptr_add_model_manual")

        submitted = st.form_submit_button("添加别名", type="primary", use_container_width=True)
        if submitted:
            if not new_name or not add_target:
                st.warning("别名名称和目标模型为必填")
            else:
                result = api_post("/admin/api/model-pointers", {
                    "name": new_name,
                    "target_model": add_target,
                    "upstream": add_upstream,
                })
                if result and result.status_code == 200:
                    st.success(f"别名 {new_name} 添加成功")
                    do_reload()
                    st.rerun()
                else:
                    detail = result.json().get("detail", "添加失败") if result else "请求失败"
                    st.error(f"添加失败: {detail}")


# ============================================================
# 延迟面板页面
# ============================================================
def latency_page():
    r = api_get("/status", use_auth=False)
    if not r or r.status_code != 200:
        st.error("无法获取状态数据")
        return

    data = r.json()
    latency_panel = data.get("latency_panel", {})

    st.markdown("#### 模型延迟状态")

    if latency_panel:
        rows = []
        for model, info in sorted(latency_panel.items()):
            status = info.get("status", "unknown")
            latency = info.get("latency", "N/A")
            error = info.get("error", "")

            status_html = {
                "ok": '<span class="status-ok">可用</span>',
                "down": '<span class="status-down">不可用</span>',
                "unknown": '<span class="status-unknown">未知</span>',
            }.get(status, '<span class="status-unknown">未知</span>')

            latency_str = f"{latency}s" if latency != "N/A" and latency is not None else "N/A"
            rows.append({
                "状态": status,
                "模型": model,
                "延迟": latency_str,
                "错误": error or "-",
            })

        # 状态汇总
        ok_count = sum(1 for r in rows if r["状态"] == "ok")
        down_count = sum(1 for r in rows if r["状态"] == "down")
        total = len(rows)
        st.markdown(f"""
        <div style="display:flex; gap:16px; margin-bottom:1rem;">
            <div class="metric-card" style="flex:1; padding:1rem;">
                <div class="label">总模型</div>
                <div class="value" style="font-size:1.5rem;">{total}</div>
            </div>
            <div class="metric-card" style="flex:1; padding:1rem;">
                <div class="label">可用</div>
                <div class="value" style="font-size:1.5rem; color:#2e7d32;">{ok_count}</div>
            </div>
            <div class="metric-card" style="flex:1; padding:1rem;">
                <div class="label">不可用</div>
                <div class="value" style="font-size:1.5rem; color:#c62828;">{down_count}</div>
            </div>
        </div>
        """, unsafe_allow_html=True)

        st.dataframe(rows, use_container_width=True, hide_index=True)
    else:
        st.info("暂无延迟数据")

    st.markdown("---")

    # 路由规则详细状态
    rules_status = data.get("rules", [])
    for rule in rules_status:
        st.markdown(f"#### 规则: {rule.get('name', '')}")
        candidates = rule.get("candidates", [])
        rows = []
        for c in candidates:
            rows.append({
                "模型": c.get("model", ""),
                "上游源": c.get("upstream", ""),
                "基础权重": c.get("base_weight", 0),
                "动态权重": c.get("dynamic_weight", 0),
                "延迟": c.get("latency", "N/A"),
                "状态": c.get("status", "unknown"),
                "最大上下文": c.get("max_context", "N/A"),
                "最大输出": c.get("max_output", "N/A"),
            })
        st.dataframe(rows, use_container_width=True, hide_index=True)


# ============================================================
# 聚合模型名管理
# ============================================================
def aggregated_names_page():
    r = api_get("/admin/api/aggregated-names")
    if not r or r.status_code != 200:
        st.error("无法获取聚合模型名")
        return

    names = r.json().get("names", [])

    st.info("聚合模型名是客户端请求时使用的统一模型名，路由代理会根据请求内容自动选择最佳模型。")

    # 展示当前聚合名
    if names:
        tags_html = " ".join(
            f'<span style="display:inline-block; background:#e3f2fd; color:#1565c0; '
            f'padding:4px 14px; border-radius:16px; margin:4px; font-size:0.9rem;">{n}</span>'
            for n in names
        )
        st.markdown(f"<div>{tags_html}</div>", unsafe_allow_html=True)

    current_text = ", ".join(names)
    edited = st.text_input("聚合模型名（逗号分隔）", value=current_text, key="agg_names_input")

    if st.button("保存", type="primary"):
        new_names = [n.strip() for n in edited.split(",") if n.strip()]
        r2 = api_put("/admin/api/aggregated-names", {"names": new_names})
        if r2 and r2.status_code == 200:
            st.success("聚合模型名已更新")
            do_reload()
        else:
            st.error("更新失败")


# ============================================================
# 系统设置页面
# ============================================================
def settings_page():
    # 延迟探测
    st.markdown("#### 延迟探测")
    r = api_get("/admin/api/config/probe")
    if r and r.status_code == 200:
        probe = r.json()
        with st.form("probe_form"):
            c1, c2, c3 = st.columns(3)
            with c1:
                enabled = st.checkbox("启用延迟探测", value=probe.get("enabled", True))
                interval = st.number_input("探测间隔（秒）", value=probe.get("interval_seconds", 120), min_value=10)
            with c2:
                timeout = st.number_input("探测超时（秒）", value=probe.get("timeout_seconds", 35), min_value=5)
                max_tokens = st.number_input("探测 max_tokens", value=probe.get("max_tokens", 3), min_value=1, max_value=10)
            with c3:
                down_threshold = st.number_input("不可用阈值（秒）", value=probe.get("down_threshold_seconds", 30), min_value=5)
                base_latency = st.number_input("基准延迟（秒）", value=probe.get("base_latency", 0.5), min_value=0.1, step=0.1, format="%.1f")

            if st.form_submit_button("保存探测设置", type="primary"):
                new_probe = {
                    "enabled": enabled, "interval_seconds": interval,
                    "timeout_seconds": timeout, "request_text": probe.get("request_text", "Hi"),
                    "max_tokens": max_tokens, "down_threshold_seconds": down_threshold,
                    "base_latency": base_latency, "error_as_down": probe.get("error_as_down", True),
                }
                r2 = api_put("/admin/api/config/probe", new_probe)
                if r2 and r2.status_code == 200:
                    st.success("探测设置已保存")
                    do_reload()
                else:
                    st.error("保存失败")

    st.markdown("---")

    # 重试设置
    st.markdown("#### 请求重试")
    r = api_get("/admin/api/config/retry")
    if r and r.status_code == 200:
        retry = r.json()
        with st.form("retry_form"):
            c1, c2, c3 = st.columns(3)
            with c1:
                max_attempts = st.number_input("最大重试次数", value=retry.get("max_attempts", 3), min_value=1, max_value=10)
            with c2:
                response_timeout = st.number_input("响应超时（秒）", value=retry.get("response_timeout", 60), min_value=10)
            with c3:
                first_chunk_timeout = st.number_input("首包超时（秒）", value=retry.get("first_chunk_timeout", 30), min_value=5)

            if st.form_submit_button("保存重试设置", type="primary"):
                r2 = api_put("/admin/api/config/retry", {
                    "max_attempts": max_attempts, "response_timeout": response_timeout,
                    "first_chunk_timeout": first_chunk_timeout,
                })
                if r2 and r2.status_code == 200:
                    st.success("重试设置已保存")
                    do_reload()
                else:
                    st.error("保存失败")

    st.markdown("---")

    # 故障转移
    st.markdown("#### 故障转移")
    r = api_get("/admin/api/config/failover")
    if r and r.status_code == 200:
        failover = r.json()
        with st.form("failover_form"):
            c1, c2 = st.columns(2)
            with c1:
                max_fails = st.number_input("最大连续失败次数", value=failover.get("max_fails", 3), min_value=1, max_value=20)
            with c2:
                cooldown = st.number_input("冷却时间（秒）", value=failover.get("cooldown_seconds", 120), min_value=10)

            if st.form_submit_button("保存故障转移设置", type="primary"):
                r2 = api_put("/admin/api/config/failover", {"max_fails": max_fails, "cooldown_seconds": cooldown})
                if r2 and r2.status_code == 200:
                    st.success("故障转移设置已保存")
                    do_reload()
                else:
                    st.error("保存失败")

    st.markdown("---")

    # 密码修改
    st.markdown("#### 修改管理后台密码")
    with st.form("password_form"):
        c1, c2, c3 = st.columns(3)
        with c1:
            old_pass = st.text_input("当前密码", type="password")
        with c2:
            new_pass = st.text_input("新密码", type="password")
        with c3:
            confirm_pass = st.text_input("确认新密码", type="password")

        if st.form_submit_button("修改密码", type="primary"):
            if not old_pass or not new_pass:
                st.warning("请输入当前密码和新密码")
            elif new_pass != confirm_pass:
                st.warning("两次输入的新密码不一致")
            elif len(new_pass) < 6:
                st.warning("新密码至少6位")
            else:
                r2 = api_put("/admin/api/admin-password", {"old_password": old_pass, "new_password": new_pass})
                if r2 and r2.status_code == 200:
                    st.success("密码已修改")
                else:
                    detail = r2.json().get("detail", "修改失败") if r2 else "请求失败"
                    st.error(f"修改失败: {detail}")

    st.markdown("---")

    # 热重载
    st.markdown("#### 配置操作")
    if st.button("热重载配置", type="primary", use_container_width=True):
        if do_reload():
            st.success("配置已热重载")
        else:
            st.error("热重载失败")


# ============================================================
# 主界面
# ============================================================
def main_app():
    with st.sidebar:
        st.markdown("""
        <div style="text-align:center; padding: 12px 0 8px;">
            <div style="font-size:1.6rem;">🧠</div>
            <div style="font-size:1.1rem; font-weight:700; color:#fff;">Smart Router</div>
            <div style="font-size:0.75rem; color:#aaa;">v4 · 管理后台</div>
        </div>
        """, unsafe_allow_html=True)

        st.markdown("---")

        page = st.radio(
            "导航",
            ["仪表盘", "API Key 管理", "上游源管理", "路由规则", "模型别名", "延迟面板", "聚合模型名", "系统设置"],
            label_visibility="collapsed",
        )

        st.markdown("---")

        if st.button("退出登录", use_container_width=True):
            _ss.logged_in = False
            _ss.jwt_token = ""
            st.rerun()

    if page == "仪表盘":
        dashboard_page()
    elif page == "API Key 管理":
        api_keys_page()
    elif page == "上游源管理":
        upstreams_page()
    elif page == "路由规则":
        rules_page()
    elif page == "模型别名":
        model_pointers_page()
    elif page == "延迟面板":
        latency_page()
    elif page == "聚合模型名":
        aggregated_names_page()
    elif page == "系统设置":
        settings_page()


# ============================================================
# 入口
# ============================================================
if _ss.logged_in:
    main_app()
else:
    login_page()
