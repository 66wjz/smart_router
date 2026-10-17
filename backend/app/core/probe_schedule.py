"""
探测时间段（schedule）判定 - CH-021

支持的配置（存 agg_probe_config.schedule / sys_setting.latency_probe.schedule 的 JSON）：

    {"mode": "always"}                                  # 全天候（默认）
    {"mode": "window",
     "days": [1,2,3,4,5],                               # 1=周一 … 7=周日；空 = 每天
     "windows": [{"start": "08:00", "end": "23:00"}]}    # 空 = 全天；end < start 表示跨夜

设计要点：
- 纯函数，不依赖数据库/时间源，便于单测（now 可注入）
- 判定失败一律返回 True（宁可多探，也不要因配置写错导致完全不探）
"""

from datetime import datetime


def _parse_hhmm(text: str) -> int | None:
    """'08:30' → 510（分钟）；非法返回 None"""
    try:
        hh, _, mm = str(text).partition(":")
        h, m = int(hh), int(mm or 0)
    except (ValueError, TypeError):
        return None
    if not (0 <= h <= 23 and 0 <= m <= 59):
        return None
    return h * 60 + m


def normalize_schedule(raw) -> dict:
    """把外部输入规整为合法结构；无法识别时回退 always"""
    if not isinstance(raw, dict):
        return {"mode": "always"}
    mode = raw.get("mode")
    if mode not in ("always", "window"):
        mode = "always"
    if mode == "always":
        return {"mode": "always"}

    days = []
    for d in raw.get("days") or []:
        try:
            n = int(d)
        except (ValueError, TypeError):
            continue
        if 1 <= n <= 7 and n not in days:
            days.append(n)

    windows = []
    for w in raw.get("windows") or []:
        if not isinstance(w, dict):
            continue
        start = _parse_hhmm(w.get("start", ""))
        end = _parse_hhmm(w.get("end", ""))
        if start is None or end is None or start == end:
            continue
        windows.append({"start": w["start"], "end": w["end"]})

    return {"mode": "window", "days": sorted(days), "windows": windows}


def is_active(raw_schedule, now: datetime | None = None) -> bool:
    """当前时刻是否落在探测时间段内"""
    sched = normalize_schedule(raw_schedule)
    if sched["mode"] == "always":
        return True

    now = now or datetime.now()
    days = sched.get("days") or []
    if days and now.isoweekday() not in days:
        return False

    windows = sched.get("windows") or []
    if not windows:
        return True

    cur = now.hour * 60 + now.minute
    for w in windows:
        start = _parse_hhmm(w["start"])
        end = _parse_hhmm(w["end"])
        if start is None or end is None:
            continue
        if start < end:
            if start <= cur < end:
                return True
        else:  # 跨夜，如 23:00-07:00
            if cur >= start or cur < end:
                return True
    return False


def describe(raw_schedule) -> str:
    """给前端/日志用的一句话描述"""
    sched = normalize_schedule(raw_schedule)
    if sched["mode"] == "always":
        return "全天候"
    day_names = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
    days = sched.get("days") or []
    if not days:
        day_text = "每天"
    elif len(days) == 7:
        day_text = "每天"
    elif days == [1, 2, 3, 4, 5]:
        day_text = "工作日"
    elif days == [6, 7]:
        day_text = "周末"
    else:
        day_text = "、".join(day_names[d - 1] for d in days)
    windows = sched.get("windows") or []
    if not windows:
        return f"{day_text} 全天"
    win_text = "、".join(f"{w['start']}-{w['end']}" for w in windows)
    return f"{day_text} {win_text}"
