"""指令路由聚合。

新增一个指令的步骤：
1. 在对应业务模块（core/xxx.py）实现服务函数，返回 result.R；
2. 在本包对应域文件写一个 async run(ctx, event) -> R；
3. 向 ROUTES 追加一条 Route(pattern, name, doc, run)。
"""

from . import (
    backup_cmds,
    battle_cmds,
    career_cmds,
    company_cmds,
    extra2_cmds,
    extra_cmds,
    finance_cmds,
    life2_cmds,
    life_cmds,
    market_cmds,
    push_cmds,
    review_cmds,
    stock_cmds,
    system_cmds,
)
from .base import Route, install

ALL_ROUTES: list[Route] = [
    *system_cmds.ROUTES,
    *career_cmds.ROUTES,
    *company_cmds.ROUTES,
    *battle_cmds.ROUTES,
    *extra2_cmds.ROUTES,
    *extra_cmds.ROUTES,
    *life2_cmds.ROUTES,
    *life_cmds.ROUTES,
    *market_cmds.ROUTES,
    *finance_cmds.ROUTES,
    *push_cmds.ROUTES,
    *review_cmds.ROUTES,
    *stock_cmds.ROUTES,
    *backup_cmds.ROUTES,
]

__all__ = ["ALL_ROUTES", "Route", "install"]
