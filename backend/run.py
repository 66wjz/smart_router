"""
Smart Router v5.1.0 启动入口
用法：uv run run.py  或  uv run uvicorn app.main:app --port 10002
"""

import uvicorn

if __name__ == "__main__":
    # 导入 app.main 触发配置加载（需先执行 seed.py 初始化数据库）
    from app.core.config import config
    uvicorn.run("app.main:app", host="0.0.0.0", port=config.listen_port)
