"""
平滑加权轮询（SWRR，nginx 同款算法）

为什么不用「随机加权」：用户要的是「100 次里 A 约 50 次、B/C 各 25 次」这种可预期的
比例，随机算法在小样本上抖动大；SWRR 在一个周期（权重和）内严格按比例，且请求
分布是均匀穿插的（A B A C 而不是 A A B C 连发）。

状态在进程内存里按「作用域」（聚合名）保存；成员的集合或权重变化时自动重置，
所以「C 挂了 → 只剩 A=2/B=1」会从 (0,0) 重新开始，比例自然变成 2/3 : 1/3。
重启后从头开始，长时间看比例仍然收敛。
"""


class WeightedRoundRobin:
    """按 scope 维护 current 权重表的 SWRR 选择器。"""

    def __init__(self):
        # scope -> {"sig": 成员+权重签名, "current": {key: 累计值}}
        self._scopes: dict[str, dict] = {}

    def pick(self, scope: str, items: list[tuple[str, int]]) -> str | None:
        """从 [(key, weight)] 中选一个；items 为空返回 None，只有一个直接返回该 key。"""
        if not items:
            return None
        if len(items) == 1:
            return items[0][0]

        normalized = [(str(k), max(1, int(w or 1))) for k, w in items]
        sig = tuple(sorted(normalized))
        state = self._scopes.get(scope)
        if state is None or state["sig"] != sig:
            # 成员或权重变了：从零开始，避免旧累计值把新成员压死
            state = {"sig": sig, "current": {k: 0.0 for k, _ in normalized}}
            self._scopes[scope] = state

        current: dict[str, float] = state["current"]
        total = sum(w for _, w in normalized)
        best_key = None
        best_val = None
        for key, weight in normalized:
            value = current.get(key, 0.0) + weight
            current[key] = value
            if best_val is None or value > best_val:
                best_val, best_key = value, key
        current[best_key] = best_val - total
        return best_key

    def reset(self, scope: str | None = None) -> None:
        """清掉某个聚合（或全部）的轮询状态。"""
        if scope is None:
            self._scopes.clear()
        else:
            self._scopes.pop(scope, None)
