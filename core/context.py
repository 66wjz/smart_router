"""
上下文估算模块 - token 估算 + 上下文长度检查
"""

import logging

log = logging.getLogger("router")


def estimate_tokens(messages: list) -> int:
    """
    粗略估算请求的 token 数。
    规则：中文约 1.5 字/token，英文/代码约 4 字符/token，取混合平均值约 2 字符/token。
    图片按每张 768 tokens 估算（保守值）。
    """
    total_chars = 0
    image_count = 0
    for msg in messages:
        content = msg.get("content", "")
        if isinstance(content, str):
            total_chars += len(content)
        elif isinstance(content, list):
            for part in content:
                if isinstance(part, dict):
                    if part.get("type") == "text":
                        total_chars += len(part.get("text", ""))
                    elif part.get("type") == "image_url":
                        image_count += 1
    text_tokens = total_chars // 2
    image_tokens = image_count * 768
    return text_tokens + image_tokens


def extract_text(messages: list) -> str:
    """从 messages 中提取所有文本内容，用于关键词匹配"""
    texts = []
    for msg in messages:
        content = msg.get("content", "")
        if isinstance(content, str):
            texts.append(content)
        elif isinstance(content, list):
            for part in content:
                if isinstance(part, dict) and part.get("type") == "text":
                    texts.append(part.get("text", ""))
    return " ".join(texts).lower()


def has_image(messages: list) -> bool:
    """检测 messages 中是否包含图片"""
    for msg in messages:
        content = msg.get("content", "")
        if isinstance(content, list):
            for part in content:
                if isinstance(part, dict) and part.get("type") == "image_url":
                    return True
    return False


def has_new_image(messages: list) -> bool:
    """
    检测最后一条 user 消息中是否包含图片。
    用于视觉管道触发判断：只有用户新发送的图片才需要处理，
    历史上下文中的图片由管道缓存机制复用。
    """
    # 从后往前找最后一条 user 消息
    for msg in reversed(messages):
        if msg.get("role") == "user":
            content = msg.get("content", "")
            if isinstance(content, list):
                for part in content:
                    if isinstance(part, dict) and part.get("type") == "image_url":
                        return True
            return False
    return False


def extract_image_urls(messages: list) -> list[dict]:
    """
    从 messages 中提取所有图片信息，返回 [{msg_idx, part_idx, url}] 列表。
    url 字段可能是 http/https URL，也可能是 data:image base64 字符串。
    用于视觉管道遍历所有图片进行替换。
    """
    result = []
    for mi, msg in enumerate(messages):
        content = msg.get("content", "")
        if isinstance(content, list):
            for pi, part in enumerate(content):
                if isinstance(part, dict) and part.get("type") == "image_url":
                    url = part.get("image_url", {}).get("url", "") if isinstance(part.get("image_url"), dict) else part.get("url", "")
                    result.append({"msg_idx": mi, "part_idx": pi, "url": url})
    return result


def check_context_limit(estimated_tokens: int, max_context: int | None) -> bool:
    """
    检查请求 token 数是否超出模型上下文限制。
    返回 True 表示上下文足够，False 表示不够。
    预留 1024 tokens 作为最低输出空间。
    """
    if not max_context or estimated_tokens <= 0:
        return True
    min_output_reserve = 1024
    return estimated_tokens + min_output_reserve <= max_context


def adjust_max_tokens(requested_max_tokens: int | None, model_max_output: int | None) -> int | None:
    """
    如果请求的 max_tokens 超过模型上限，返回调整后的值。
    返回 None 表示不需要调整。
    """
    if requested_max_tokens is None:
        return None
    if model_max_output is None:
        return None
    if requested_max_tokens > model_max_output:
        return model_max_output
    return None
