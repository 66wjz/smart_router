"""最小化 xlsx 生成器（CH-042，零第三方依赖）

为什么不引入 openpyxl：
    生产部署脚本 `deploy_v520_full.py` 只同步代码与静态产物，**不会在服务器上装依赖**。
    一旦 pyproject 里加了 openpyxl，生产重启就会 ImportError → 服务起不来。
    而导出 xlsx 只需要「一个 sheet + 表头 + 若干行」，用标准库 zipfile 手写完全够用。

产出结构（Office Open XML 最小集）：
    [Content_Types].xml
    _rels/.rels
    xl/workbook.xml
    xl/_rels/workbook.xml.rels
    xl/styles.xml          表头加粗 + 列宽
    xl/worksheets/sheet1.xml
"""

import io
import re
import zipfile
from datetime import datetime
from xml.sax.saxutils import escape

# XML 1.0 不允许的控制字符（除 \t \n \r 外），出现会让 Excel 报文件损坏
_ILLEGAL_XML = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")

_CONTENT_TYPES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>
</Types>"""

_ROOT_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>"""

_WORKBOOK_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
</Relationships>"""

# 两种字体（常规 / 表头加粗）+ 两种单元格样式
# 注意：`cellStyles` 不能省 —— 缺它 openpyxl 会警告「Workbook contains no default style」，
# 部分 Excel 版本也会提示「文件已损坏，是否恢复」。这是手写 xlsx 最容易漏的一项。
_STYLES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
<fonts count="2">
<font><sz val="11"/><color theme="1"/><name val="Calibri"/></font>
<font><b/><sz val="11"/><color theme="1"/><name val="Calibri"/></font>
</fonts>
<fills count="3">
<fill><patternFill patternType="none"/></fill>
<fill><patternFill patternType="gray125"/></fill>
<fill><patternFill patternType="solid"><fgColor rgb="FFF2F3F5"/><bgColor indexed="64"/></patternFill></fill>
</fills>
<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>
<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
<cellXfs count="2">
<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>
<xf numFmtId="0" fontId="1" fillId="2" borderId="0" xfId="0" applyFont="1" applyFill="1"/>
</cellXfs>
<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>
</styleSheet>"""


def _col_letter(idx: int) -> str:
    """0 → A，25 → Z，26 → AA"""
    letters = ""
    idx += 1
    while idx > 0:
        idx, rem = divmod(idx - 1, 26)
        letters = chr(65 + rem) + letters
    return letters


def _clean(value) -> str:
    """转字符串并清掉 XML 非法字符"""
    return _ILLEGAL_XML.sub("", str(value))


def _cell(ref: str, value, style: int = 0) -> str:
    """生成一个单元格；数字走数值类型（Excel 可直接求和），其余走内联字符串。

    空值直接省略该 <c>，Excel 打开后是空单元格，视觉上一致且体积更小。
    """
    if value is None or value == "":
        return ""
    if isinstance(value, bool):
        value = "是" if value else "否"
    if isinstance(value, (int, float)):
        return f'<c r="{ref}" s="{style}"><v>{value}</v></c>'
    text = _clean(value)
    # inlineStr 省掉 sharedStrings.xml，代价是文件略大，对导出场景完全可接受
    return (
        f'<c r="{ref}" s="{style}" t="inlineStr">'
        f'<is><t xml:space="preserve">{escape(text)}</t></is></c>'
    )


def build_xlsx(
    sheet_name: str,
    headers: list[str],
    rows: list[list],
    col_widths: list[int] | None = None,
) -> bytes:
    """把表头 + 二维数据打成 xlsx 字节流。

    headers / 每一行 的列数必须一致；列宽单位为「字符数」，不传则按表头长度估一个。
    """
    ncol = len(headers)
    if ncol == 0:
        raise ValueError("headers 不能为空")

    if col_widths is None:
        col_widths = []
        for i, h in enumerate(headers):
            # 以表头为准估宽，再夹在 8~40 之间；数值列（如 tokens）太窄会显示 ####
            est = max(8, min(40, len(str(h)) * 2 + 4))
            for row in rows[:200]:
                if i < len(row) and row[i] is not None:
                    est = max(est, min(40, len(str(row[i])) + 4))
            col_widths.append(est)

    cols_xml = "".join(
        f'<col min="{i + 1}" max="{i + 1}" width="{w}" customWidth="1"/>'
        for i, w in enumerate(col_widths)
    )

    header_cells = "".join(
        _cell(f"{_col_letter(i)}1", h, style=1) for i, h in enumerate(headers)
    )
    body_xml = []
    for r_idx, row in enumerate(rows, start=2):
        cells = "".join(
            _cell(f"{_col_letter(c)}" + str(r_idx), row[c] if c < len(row) else None)
            for c in range(ncol)
        )
        body_xml.append(f'<row r="{r_idx}">{cells}</row>')

    last_col = _col_letter(ncol - 1)
    last_row = len(rows) + 1
    sheet = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        '<sheetViews><sheetView workbookViewId="0">'
        '<pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/>'
        "</sheetView></sheetViews>"
        f"<cols>{cols_xml}</cols>"
        f'<sheetData><row r="1">{header_cells}</row>{"".join(body_xml)}</sheetData>'
        f'<autoFilter ref="A1:{last_col}{last_row}"/>'
        "</worksheet>"
    )

    # sheet 名不能含 : \ / ? * [ ]，且不超过 31 字符
    safe_name = re.sub(r"[:\\/?*\[\]]", "_", sheet_name or "Sheet1")[:31] or "Sheet1"
    workbook = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        f'<sheets><sheet name="{escape(safe_name)}" sheetId="1" r:id="rId1"/></sheets>'
        "</workbook>"
    )

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", _CONTENT_TYPES)
        z.writestr("_rels/.rels", _ROOT_RELS)
        z.writestr("xl/workbook.xml", workbook)
        z.writestr("xl/_rels/workbook.xml.rels", _WORKBOOK_RELS)
        z.writestr("xl/styles.xml", _STYLES)
        z.writestr("xl/worksheets/sheet1.xml", sheet)
    return buf.getvalue()


def export_filename(prefix: str) -> str:
    """报表文件名：前缀 + 本地时间戳，如 `模型别名_20261021-2035.xlsx`"""
    return f"{prefix}_{datetime.now().strftime('%Y%m%d-%H%M')}.xlsx"
