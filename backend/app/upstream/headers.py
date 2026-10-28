"""
出站响应头安全化（CH-050）

HTTP 头值只能是 latin-1，Starlette 在构造 JSONResponse / StreamingResponse 时就会
按 latin-1 编码 header；上游源 ID 允许中文（历史数据里有「星-国模013」这类 id），
一旦被写进 `X-Served-By` 就会抛 UnicodeEncodeError，最终被全局兜底变成
500「中转站内部错误: UnicodeEncodeError」。

这里统一做 ASCII 安全化：
- 纯 ASCII 原样返回（行为零变化）
- 含非 ASCII 时按 RFC 3986 percent-encode（保留 `/` 便于阅读模型名）
"""

from urllib.parse import quote


def ascii_header_value(value) -> str:
    """把任意值转成可安全写入响应头的 ASCII 字符串。"""
    text = str(value)
    if text.isascii():
        return text
    return quote(text, safe="/")


def ascii_safe_headers(headers) -> dict:
    """复制一份响应头字典，值做 ASCII 安全化（用于透传上游/适配器响应头）。"""
    return {str(k): ascii_header_value(v) for k, v in (headers or {}).items()}
