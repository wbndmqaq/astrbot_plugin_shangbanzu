"""年终考评指令路由。"""

from ..core import review
from ..core.result import R
from .base import GID_HINT, Route, gid_of


async def annual_review(ctx, event):
    gid = gid_of(event)
    if not gid:
        return R(err=GID_HINT)
    return await review.annual_review(
        ctx.db, gid, event.get_sender_id(), await ctx.anick(event), ctx.config
    )


ROUTES = [
    Route(
        r"^[#]?(年终考评|年度考评|考评|年终总结)$",
        "cmd_annual_review",
        "年度绩效考评，S/A/B/C/D五档影响年终奖和调薪",
        annual_review,
    ),
]
