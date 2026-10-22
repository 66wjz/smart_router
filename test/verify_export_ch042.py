"""CH-042 导出能力验证：xlsx 结构合法性 + 端点行为

覆盖：
  [1] xlsx 字节流是合法 zip，包含必需的 6 个 part
  [2] 表头/单元格内容正确，中文不乱码，数字是数值类型
  [3] 空值不写 <c>，bool 转中文
  [4] 列宽与冻结首行存在
  [5] GET /admin/api/export/{dataset} 返回 xlsx 且带文件名字头
  [6] POST 批量导出只含选中的 id
  [7] datas 未知 → 404；批量传空 ids → 400
  [8] 数据集清单包含全部 10 个
"""

import io
import os
import sys
import zipfile

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend"))

from app.core.xlsx_writer import build_xlsx, export_filename  # noqa: E402

failures = []


def check(cond, msg):
    if cond:
        print(f"  OK   {msg}")
    else:
        print(f"  FAIL {msg}")
        failures.append(msg)


# ---------------------------------------------------------------- [1] 结构
print("\n[1] xlsx 字节流是合法 zip，part 齐全")
data = build_xlsx("测试表", ["名称", "数量"], [["甲", 1], ["乙", 2]])
check(data[:2] == b"PK", "zip 魔数正确（PK）")

z = zipfile.ZipFile(io.BytesIO(data))
names = set(z.namelist())
required = {
    "[Content_Types].xml", "_rels/.rels", "xl/workbook.xml",
    "xl/_rels/workbook.xml.rels", "xl/styles.xml", "xl/worksheets/sheet1.xml",
}
check(required <= names, f"必需 part 齐全（实际 {sorted(names)}）")

# XML 能被解析（用标准库 xml，不引入额外依赖）
import xml.etree.ElementTree as ET  # noqa: E402

for n in required:
    try:
        ET.fromstring(z.read(n))
    except Exception as e:
        check(False, f"{n} XML 解析失败：{e}")
        break
else:
    check(True, "6 个 part 全部可被 XML 解析器读取")

# ---------------------------------------------------------------- [2] 内容
print("\n[2] 表头与单元格内容正确")
sheet = z.read("xl/worksheets/sheet1.xml").decode()
check("名称" in sheet and "数量" in sheet, "表头写入")
check("甲" in sheet and "乙" in sheet, "中文单元格写入")
check('<c r="B2" s="0"><v>1</v></c>' in sheet, "数字写成数值类型（Excel 可直接求和）")
check('t="inlineStr"' in sheet, "字符串用 inlineStr")
check('s="1"' in sheet, "表头用加粗样式（style 1）")

print("\n[3] 空值与布尔处理")
data2 = build_xlsx("t", ["A", "B", "C"], [[None, "", True]])
sheet2 = zipfile.ZipFile(io.BytesIO(data2)).read("xl/worksheets/sheet1.xml").decode()
check('<c r="A2"' not in sheet2, "null 不生成单元格")
check('<c r="B2"' not in sheet2, "空字符串不生成单元格")
check("是" in sheet2, "布尔 True 转「是」")

print("\n[4] 列宽与冻结首行")
check("<cols>" in sheet and 'customWidth="1"' in sheet, "写了列宽")
check('state="frozen"' in sheet, "首行冻结")
check("<autoFilter" in sheet, "自动筛选")

print("\n[5] 非法字符清理 + 文件名")
data3 = build_xlsx("t", ["A"], [["bad\x00char\x07here"]])
s3 = zipfile.ZipFile(io.BytesIO(data3)).read("xl/worksheets/sheet1.xml").decode()
check("badcharhere" in s3 or "bad" in s3, "XML 非法控制字符被清掉")
try:
    ET.fromstring(s3)
    check(True, "清掉控制字符后仍是合法 XML")
except Exception as e:
    check(False, f"清理后 XML 仍非法：{e}")

fn = export_filename("模型别名")
check(fn.startswith("模型别名_") and fn.endswith(".xlsx"), f"文件名格式（{fn}）")

# ---------------------------------------------------------------- 端点验证
print("\n[6] 导出端点（真实起服务）")
import json  # noqa: E402
import shutil  # noqa: E402
import tempfile  # noqa: E402
import threading  # noqa: E402
import time  # noqa: E402
import urllib.error  # noqa: E402
import urllib.request  # noqa: E402

tmpdir = tempfile.mkdtemp(prefix="ch042_")
os.environ["SMART_ROUTER_DB"] = os.path.join(tmpdir, "t.db")

import uvicorn  # noqa: E402

from app.main import app  # noqa: E402

# 建一个可用库：直接跑 seed 的 SQL 清单
import sqlite3  # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SQL_FILES = [
    "01_建表.sql", "02_init_data.sql",
    "increment/01_增量_20260809_上游源禁用.sql",
    "increment/02_增量_20260809_上游Key池.sql",
    "increment/03_增量_20260809_上游模型列表.sql",
    "increment/04_增量_20260810_智能重试开关.sql",
    "increment/05_增量_20260811_上游多分组.sql",
    "06_用量统计与自动聚合.sql",
    "increment/06_增量_20261017_聚合探测配置.sql",
    "increment/07_增量_20261017_聚合统一与探测模板.sql",
    "increment/08_增量_20261017_聚合规则绑定.sql",
    "increment/09_增量_20261018_聚合分组.sql",
    "increment/10_增量_20261018_自动聚合开关默认关闭.sql",
    "increment/11_增量_20261019_请求详情可观测性.sql",
    "increment/12_增量_20261021_请求过滤引擎.sql",
]
con = sqlite3.connect(os.environ["SMART_ROUTER_DB"])
for f in SQL_FILES:
    path = os.path.join(REPO, "sql", f.replace("/", os.sep))
    if os.path.exists(path):
        con.executescript(open(path, encoding="utf-8").read())
con.commit()
con.close()

config = app.state.config
config.load()

PORT = 18099
server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=PORT, log_level="error"))
threading.Thread(target=server.run, daemon=True).start()
for _ in range(60):
    try:
        urllib.request.urlopen(f"http://127.0.0.1:{PORT}/health", timeout=1)
        break
    except Exception:
        time.sleep(0.2)

BASE = f"http://127.0.0.1:{PORT}"


def http(method, path, body=None, token=None, raw=False):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(BASE + path, data=data, method=method)
    if data is not None:
        r.add_header("Content-Type", "application/json")
    if token:
        r.add_header("Authorization", "Bearer " + token)
    try:
        with urllib.request.urlopen(r, timeout=30) as resp:
            return resp.status, resp.read(), {k.lower(): v for k, v in resp.headers.items()}
    except urllib.error.HTTPError as e:
        return e.code, e.read(), {k.lower(): v for k, v in e.headers.items()}


# 登录取 JWT
con = sqlite3.connect(os.environ["SMART_ROUTER_DB"])
cfg = json.loads(con.execute("SELECT value FROM sys_setting WHERE key='admin'").fetchone()[0])
con.close()
st, body, _ = http("POST", "/admin/api/login",
                   {"username": cfg.get("username", "admin"), "password": cfg.get("password", "")})
token = json.loads(body).get("token", "") if st == 200 else ""
check(st == 200 and token, f"登录成功（{st}）")

# 数据集清单
st, body, _ = http("GET", "/admin/api/export/datasets", token=token)
ds = json.loads(body).get("datasets", []) if st == 200 else []
check(st == 200 and len(ds) == 10, f"数据集清单 10 个（实际 {len(ds)}: {ds}）")

# 导出全部：模型别名
st, body, headers = http("GET", "/admin/api/export/pointers", token=token)
check(st == 200, f"GET 导出返回 200（实际 {st}）")
check(body[:2] == b"PK", "返回体是 zip/xlsx")
disp = headers.get("content-disposition", "")
check("filename*=UTF-8''" in disp, f"带 RFC5987 文件名字头（{disp[:70]}）")
check("spreadsheetml" in headers.get("content-type", ""), "Content-Type 是 xlsx")
if st == 200:
    zz = zipfile.ZipFile(io.BytesIO(body))
    check("xl/worksheets/sheet1.xml" in zz.namelist(), "导出的 xlsx 结构完整")

# 批量导出：filter-rules（admin 账号可读）
st, body2, _ = http("POST", "/admin/api/export/filter-rules",
                    {"ids": ["1"]}, token=token)
check(st == 200 and body2[:2] == b"PK", f"批量导出返回 xlsx（{st}）")
if st == 200:
    s = zipfile.ZipFile(io.BytesIO(body2)).read("xl/worksheets/sheet1.xml").decode()
    check(s.count("<row ") == 2, f"批量导出只含表头 + 1 行（实际 {s.count('<row ')} 行）")
    check("DSH 身份声明" in s, "导出的正是选中的那条规则")

# 未知数据集
st, _, _ = http("GET", "/admin/api/export/not-exist", token=token)
check(st == 404, f"未知数据集返回 404（实际 {st}）")

# 批量空 ids
st, _, _ = http("POST", "/admin/api/export/pointers", {"ids": []}, token=token)
check(st == 400, f"批量导出空 ids 返回 400（实际 {st}）")

# 未登录
st, _, _ = http("GET", "/admin/api/export/pointers")
check(st == 401, f"未登录返回 401（实际 {st}）")

server.should_exit = True
time.sleep(0.5)
shutil.rmtree(tmpdir, ignore_errors=True)

print("\n" + ("全部通过 ✅" if not failures else f"{len(failures)} 项失败 ❌"))
for f in failures:
    print("  -", f)
sys.exit(1 if failures else 0)
