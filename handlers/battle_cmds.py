"""对抗线指令路由：对线与卷王大赛（均为玩家亲自出战）。"""

from ..core import social
from ..core.result import R
from .base import Route

GID_HINT = "该游戏只能在群聊中使用"


def _gid(event):
    return event.get_group_id() or ""


async def duel(ctx, event):
    gid = _gid(event)
    if not gid:
        return R(err=GID_HINT)
    me = str(event.get_sender_id())
    candidates = ctx.nums(event, ("对线",)) + ctx.ats(event)
    target = next((c for c in candidates if c != me), "")
    if not target:
        return R(err="格式：对线 @群友（或附QQ号）")
    return await social.duel(
        ctx.db, gid, me, target, ctx.config, ctx.nick(event, target), ctx.app_id
    )


async def rank_show(ctx, event):
    gid = _gid(event)
    if not gid:
        return R(err=GID_HINT)
    return await social.rank_show(ctx.db, gid, str(event.get_sender_id()))


async def rank_join(ctx, event):
    gid = _gid(event)
    if not gid:
        return R(err=GID_HINT)
    return await social.rank_join(
        ctx.db, gid, str(event.get_sender_id()), ctx.config, ctx.nick(event)
    )


ROUTES = [
    Route(r"^[#]?对线", "cmd_duel", "与群友来一场职场对线，赢奖金涨身价", duel),
    Route(
        r"^[#]?(卷王大赛|排位赛)$",
        "cmd_rank_show",
        "查看自己的卷王大赛段位与积分",
        rank_show,
    ),
    Route(
        r"^[#]?参加(卷王大赛|排位赛)",
        "cmd_rank_join",
        "亲自出战卷王大赛，冲击传奇卷王",
        rank_join,
    ),
]
