"""
CH-022：清空演示数据库（backend/demo.db）
用法：python test/clear_demo_ch022.py
"""

import os
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEMO_DB = os.path.join(BASE, "backend", "demo.db")

removed = 0
for suffix in ("", "-wal", "-shm"):
    path = DEMO_DB + suffix
    if os.path.exists(path):
        os.remove(path)
        removed += 1
        print(f"  已删除 {os.path.basename(path)}")

if not removed:
    print("演示库不存在，无需清理")
else:
    print(f"[demo] 清理完成，可重新运行 seed_demo_ch022.py 生成")

sys.exit(0)
