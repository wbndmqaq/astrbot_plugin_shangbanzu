"""双色球彩票指令路由：买彩票（机选/自选）、我的彩票、开奖结果、奖池。"""

import re

from ..core import lottery
from ..core.result import R
from .base import GID_HINT, Route, gid_of


async def buy_lottery(ctx, event):
    gid = gid_of(event)
    if not gid:
        return R(err=GID_HINT)
    # 「买彩票」= 机选 1 注；「买彩票 3」= 机选 3 注；「买彩票 3 7 12 5」= 自选一注

    m = re.search(r"买彩票\s*([\d\s，,]+)", event.message_str or "")
    args = (m.group(1).strip() if m and m.group(1) else "")
    return await lottery.buy_ticket(
        ctx.db, gid, event.get_sender_id(), args, ctx.config, await ctx.anick(event)
    )


async def my_lottery(ctx, event):
    gid = gid_of(event)
    if not gid:
        return R(err=GID_HINT)
    return await lottery.my_tickets(
        ctx.db, gid, str(event.get_sender_id()), ctx.config
    )


async def lottery_draw_result(ctx, event):
    return await lottery.lottery_result(ctx.db)


async def lottery_pool(ctx, event):
    return await lottery.lottery_pool_view(ctx.db, ctx.config)


ROUTES = [
    Route(
        r"^[#]?买彩票(?:\s+[\d\s,，]*)?$",
        "cmd_buy_lottery",
        "双色球购票：机选「买彩票 3」/ 自选「买彩票 3 7 12 5」（红1~16选3+蓝1~8选1）",
        buy_lottery,
    ),
    Route(
        r"^[#]?(我的彩票|彩票号码)$",
        "cmd_my_lottery",
        "查看本期持有的彩票号码",
        my_lottery,
    ),
    Route(
        r"^[#]?(彩票结果|开奖结果)$",
        "cmd_lottery_result",
        "查看最近一期双色球开奖结果与中奖名单",
        lottery_draw_result,
    ),
    Route(
        r"^[#]?(彩票奖池|奖池)$",
        "cmd_lottery_pool",
        "查看本期双色球累积奖池与开奖时间",
        lottery_pool,
    ),
]
