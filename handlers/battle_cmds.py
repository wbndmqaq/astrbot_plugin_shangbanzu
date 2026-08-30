"""对抗线指令路由：对线与卷王大赛（均为玩家亲自出战）。"""

from ..core import social
from ..core.result import R
from .base import GID_HINT, Route, gid_of


async def duel(ctx, event):
    gid = gid_of(event)
    if not gid:
        return R(err=GID_HINT)
    me = str(event.get_sender_id())
    # @ 目标优先于裸数字，避免「对线 12345 @B」时数字 12345 抢占目标
    ats = ctx.ats(event)
    candidates = list(ats) + [c for c in ctx.nums(event, ("对线",)) if c not in ats]
    target = next((c for c in candidates if c != me), "")
    if not target:
        return R(err="格式：对线 @群友（或附QQ号）")
    return await social.duel(
        ctx.db, gid, me, target, ctx.config, await ctx.anick(event, target), ctx.app_id
    )


async def rank_show(ctx, event):
    gid = gid_of(event)
    if not gid:
        return R(err=GID_HINT)
    return await social.rank_show(ctx.db, gid, str(event.get_sender_id()))


async def rank_join(ctx, event):
    gid = gid_of(event)
    if not gid:
        return R(err=GID_HINT)
    return await social.rank_join(
        ctx.db, gid, str(event.get_sender_id()), ctx.config, await ctx.anick(event)
    )


ROUTES = [
    Route(
        r"^[#]?对线(?:\s+@?\S+)?$",
        "cmd_duel",
        "与群友来一场职场对线，赢奖金涨身价",
        duel,
    ),
    Route(
        r"^[#]?(卷王大赛|排位赛)$",
        "cmd_rank_show",
        "查看自己的卷王大赛段位与积分",
        rank_show,
    ),
    Route(
        r"^[#]?参加(卷王大赛|排位赛)$",
        "cmd_rank_join",
        "亲自出战卷王大赛，冲击传奇卷王",
        rank_join,
    ),
]
