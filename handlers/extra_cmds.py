"""扩展玩法指令路由。"""

from ..core import extra
from ..core.result import R
from .base import Route

GID = "该功能只能在群聊中使用"


async def year_bonus(ctx, event):
    gid = event.get_group_id() or ""
    if not gid:
        return R(err=GID)
    return await extra.year_bonus(
        ctx.db, gid, event.get_sender_id(), ctx.nick(event), ctx.config
    )


async def learn_skill(ctx, event):
    gid = event.get_group_id() or ""
    if not gid:
        return R(err=GID)
    import re

    m = re.search(r"学技能\s+(\S+)", event.message_str or "")
    return await extra.learn_skill(
        ctx.db,
        gid,
        event.get_sender_id(),
        ctx.nick(event),
        ctx.config,
        m.group(1) if m else "",
    )


async def my_skills(ctx, event):
    gid = event.get_group_id() or ""
    if not gid:
        return R(err=GID)
    return await extra.my_skills(
        ctx.db, gid, str(event.get_sender_id()), ctx.nick(event)
    )


async def social(ctx, event):
    gid = event.get_group_id() or ""
    if not gid:
        return R(err=GID)
    me = str(event.get_sender_id())
    target = next((c for c in ctx.ats(event) if c != me), "")
    if not target:
        return R(err="请@要社交的群友")
    return await extra.social_network(
        ctx.db, gid, me, target, ctx.config, ctx.nick(event, target)
    )


async def side_up(ctx, event):
    gid = event.get_group_id() or ""
    if not gid:
        return R(err=GID)
    return await extra.side_hustle_upgrade(
        ctx.db, gid, event.get_sender_id(), ctx.nick(event), ctx.config
    )


async def annual_leave(ctx, event):
    gid = event.get_group_id() or ""
    if not gid:
        return R(err=GID)
    return await extra.annual_leave(
        ctx.db, gid, event.get_sender_id(), ctx.nick(event), ctx.config
    )


async def gossip(ctx, event):
    gid = event.get_group_id() or ""
    if not gid:
        return R(err=GID)
    return await extra.gossip(ctx.db, gid, str(event.get_sender_id()), ctx.nick(event))


ROUTES = [
    Route(
        r"^[#]?(年终奖|年度奖金)$",
        "cmd_year_bonus",
        "领取年终奖（每年限一次）",
        year_bonus,
    ),
    Route(
        r"^[#]?学技能\s+\S+",
        "cmd_learn_skill",
        "学习技能：编程/设计/管理/演讲/外语",
        learn_skill,
    ),
    Route(r"^[#]?(我的技能|技能列表)$", "cmd_my_skills", "查看已掌握的技能", my_skills),
    Route(r"^[#]?(职场社交|社交)\s+\S+", "cmd_social", "请群友喝奶茶建立人脉", social),
    Route(
        r"^[#]?(副业升级|副业进阶)$", "cmd_side_up", "升级副业等级提高摆摊收益", side_up
    ),
    Route(
        r"^[#]?(请年假|休年假|年假)$",
        "cmd_annual_leave",
        "休年假（不扣钱但断全勤）",
        annual_leave,
    ),
    Route(r"^[#]?(职场八卦|八卦)$", "cmd_gossip", "随机生成一条群内职场八卦", gossip),
]
