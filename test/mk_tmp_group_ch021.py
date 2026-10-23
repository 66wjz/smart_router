"""CH-021 浏览器实测辅助：造一个临时聚合组（验证探测弹窗用）

用法：python test/mk_tmp_group_ch021.py [port] [create|delete]
"""

import json
import os
import sys
import time
import urllib.error
import urllib.request

PORT = sys.argv[1] if len(sys.argv) > 1 else "10199"
ACTION = sys.argv[2] if len(sys.argv) > 2 else "create"
BASE = f"http://127.0.0.1:{PORT}"
GROUP = "ch021-ui-demo"

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend"))
from app.services.auth_service import make_admin_token  # noqa: E402
from app.core.config import config  # noqa: E402

# CH-049 起 token 必须带密码指纹 pv，裸签会被 check_auth 拒绝
TOKEN = make_admin_token(config.admin_config)


def call(method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    req.add_header("Authorization", f"Bearer {TOKEN}")
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()


if ACTION == "delete":
    print(call("DELETE", f"/admin/api/model-groups?model={GROUP}"))
    print(call("DELETE", f"/admin/api/model-groups/probe?model={GROUP}"))
else:
    status, ups = call("GET", "/admin/api/upstreams")
    ids = [u["id"] for u in ups["upstreams"]] if status == 200 else []
    if len(ids) < 2:
        print("上游源不足 2 个，无法构造多成员聚合组")
        sys.exit(1)
    print(call("PUT", f"/admin/api/model-groups?model={GROUP}", {
        "upstreams": [
            {"upstream": ids[0], "model": "ch021-model-a", "weight": 1},
            {"upstream": ids[1], "model": "ch021-model-b", "weight": 1},
        ],
        "enabled": True,
    }))
