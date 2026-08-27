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
        ctx.db, gid, me, target, ctx.nick(event), ctx.config, ctx.nick(event, target)
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


async def my_achievements_cmd(ctx, event):
    gid = event.get_group_id() or ""
    if not gid:
        return R(err=GID)
    return await extra.my_achievements(
        ctx.db, gid, event.get_sender_id(), ctx.nick(event), ctx.config
    )


async def set_title_cmd(ctx, event):
    gid = event.get_group_id() or ""
    if not gid:
        return R(err=GID)
    import re
    m = re.search(r"^[#]?(?:佩戴称号|佩戴头衔|设置称号)\s*(\S+)", event.message_str or "")
    title_name = (m.group(1) if m else "").strip()
    return await extra.set_title(
        ctx.db, gid, event.get_sender_id(), ctx.nick(event), title_name, ctx.config
    )


async def unset_title_cmd(ctx, event):
    gid = event.get_group_id() or ""
    if not gid:
        return R(err=GID)
    return await extra.unset_title(
        ctx.db, gid, event.get_sender_id(), ctx.nick(event), ctx.config
    )


async def send_redpacket_cmd(ctx, event):
    gid = event.get_group_id() or ""
    if not gid:
        return R(err=GID)
    import re
    m = re.search(r"^[#]?(?:发红包|发群红包|塞红包)\s+(\d+(?:\.\d+)?)\s+(\d+)", event.message_str or "")
    if not m:
        return R(err="格式错误！请发送：「发红包 <总金额> <个数>」，例如：「发红包 1000 5」")
    return await extra.send_redpacket(
        ctx.db, gid, event.get_sender_id(), ctx.nick(event), m.group(1), m.group(2), ctx.config
    )


async def claim_redpacket_cmd(ctx, event):
    gid = event.get_group_id() or ""
    if not gid:
        return R(err=GID)
    return await extra.claim_redpacket(
        ctx.db, gid, event.get_sender_id(), ctx.nick(event), ctx.config
    )


async def scratch_lottery_cmd(ctx, event):
    gid = event.get_group_id() or ""
    if not gid:
        return R(err=GID)
    return await extra.scratch_lottery(
        ctx.db, gid, event.get_sender_id(), ctx.nick(event), ctx.config
    )


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
    Route(r"^[#]?(我的成就|成就|成就列表)$", "cmd_my_achievements", "查看个人职场成就与解锁进度", my_achievements_cmd),
    Route(r"^[#]?(佩戴称号|佩戴头衔|设置称号)\s*\S+", "cmd_set_title", "佩戴已解锁的成就称号", set_title_cmd),
    Route(r"^[#]?(卸下称号|卸下头衔|隐藏称号)$", "cmd_unset_title", "卸下当前佩戴的头衔", unset_title_cmd),
    Route(r"^[#]?(发红包|发群红包|塞红包)\s+\S+\s+\S+", "cmd_send_packet", "在群内塞拼手气红包给群友", send_redpacket_cmd),
    Route(r"^[#]?(抢红包|领红包|开红包)$", "cmd_claim_packet", "开抢群内最新拼手气红包", claim_redpacket_cmd),
    Route(r"^[#]?(刮刮乐|彩票|下班刮刮乐)$", "cmd_scratch", "购买职场刮刮乐（小赌怡情）", scratch_lottery_cmd),
]
