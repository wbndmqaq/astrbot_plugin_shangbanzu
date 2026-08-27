"""年终考评指令路由。"""

from ..core.result import R
from .base import Route


async def annual_review(ctx, event):
    gid = event.get_group_id() or ""
    if not gid:
        return R(err="该功能只能在群聊中使用")
    from ..core.review import annual_review as _ar

    return await _ar(ctx.db, gid, event.get_sender_id(), ctx.nick(event), ctx.config)


ROUTES = [
    Route(
        r"^[#]?(年终考评|年度考评|考评|年终总结)$",
        "cmd_annual_review",
        "年度绩效考评，S/A/B/C/D五档影响年终奖和调薪",
        annual_review,
    ),
]
