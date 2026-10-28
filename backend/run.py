"""
Smart Router v5.3.0 启动入口
用法：uv run run.py  或  uv run uvicorn app.main:app --port 10002

FB-041 双栈监听：直接 uvicorn.run(host="::") 不可行 ——
Python 3.12 的 asyncio 在创建 IPv6 监听时会显式把 IPV6_V6ONLY 置 1，
结果只监听 IPv6，IPv4 客户端全部连不上（生产实测 10.10.0.2 返回 000）。
这里显式建一个 dualstack_ipv6=True 的 socket 再交给 uvicorn，
同端口同时接受 IPv4 与 IPv6。
"""

import socket

import uvicorn

if __name__ == "__main__":
    # 导入 app.main 触发配置加载（需先执行 seed.py 初始化数据库）
    from app.core.config import config

    sock = socket.create_server(
        ("::", config.listen_port),
        family=socket.AF_INET6,
        backlog=2048,
        dualstack_ipv6=True,
    )
    uvicorn.Server(uvicorn.Config("app.main:app")).run(sockets=[sock])
