"""扩展生活指令路由：开会、带饭、回消息、抢会议室、吃饭、帮领导、峰会、宠物、考证、旅游。"""

import re

from ..core import life2
from ..core.result import R
from .base import GID_HINT, Route, gid_of


async def meeting(ctx, event):
    gid = gid_of(event)
    if not gid:
        return R(err=GID_HINT)
    return await life2.meeting(
        ctx.db, gid, event.get_sender_id(), await ctx.anick(event), ctx.config
    )


async def bring_food(ctx, event):
    gid = gid_of(event)
    if not gid:
        return R(err=GID_HINT)
    me = str(event.get_sender_id())
    target = next((c for c in ctx.ats(event) if c != me), "")
    if not target:
        return R(err="请@要帮带饭的同事")
    return await life2.bring_food(
        ctx.db, gid, me, target, await ctx.anick(event), ctx.config, await ctx.anick(event, target)
    )


async def reply_msg(ctx, event):
    gid = gid_of(event)
    if not gid:
        return R(err=GID_HINT)
    return await life2.reply_msg(
        ctx.db, gid, event.get_sender_id(), await ctx.anick(event), ctx.config
    )


async def meeting_room(ctx, event):
    gid = gid_of(event)
    if not gid:
        return R(err=GID_HINT)
    return await life2.meeting_room(
        ctx.db, gid, event.get_sender_id(), await ctx.anick(event), ctx.config
    )


async def eat_with(ctx, event):
    gid = gid_of(event)
    if not gid:
        return R(err=GID_HINT)
    me = str(event.get_sender_id())
    target = next((c for c in ctx.ats(event) if c != me), "")
    if not target:
        return R(err="请@要一起吃饭的同事")
    return await life2.eat_with(
        ctx.db, gid, me, target, await ctx.anick(event), ctx.config, await ctx.anick(event, target)
    )


async def boss_task(ctx, event):
    gid = gid_of(event)
    if not gid:
        return R(err=GID_HINT)
    return await life2.boss_task(
        ctx.db, gid, event.get_sender_id(), await ctx.anick(event), ctx.config
    )


async def summit(ctx, event):
    gid = gid_of(event)
    if not gid:
        return R(err=GID_HINT)
    return await life2.summit(
        ctx.db, gid, event.get_sender_id(), await ctx.anick(event), ctx.config
    )


async def adopt_pet(ctx, event):
    gid = gid_of(event)
    if not gid:
        return R(err=GID_HINT)

    m = re.search(r"(猫|狗)", event.message_str or "")
    return await life2.adopt_pet(
        ctx.db,
        gid,
        event.get_sender_id(),
        await ctx.anick(event),
        m.group(1) if m else "",
        ctx.config,
    )


async def pet_interact(ctx, event):
    gid = gid_of(event)
    if not gid:
        return R(err=GID_HINT)
    return await life2.pet_interact(
        ctx.db, gid, str(event.get_sender_id()), await ctx.anick(event)
    )


async def get_cert(ctx, event):
    gid = gid_of(event)
    if not gid:
        return R(err=GID_HINT)

    m = re.search(r"(?:考证书|考证)\s*(\S+)", event.message_str or "")
    return await life2.get_cert(
        ctx.db,
        gid,
        event.get_sender_id(),
        await ctx.anick(event),
        m.group(1) if m else "",
        ctx.config,
    )


async def travel(ctx, event):
    gid = gid_of(event)
    if not gid:
        return R(err=GID_HINT)
    return await life2.travel(
        ctx.db, gid, event.get_sender_id(), await ctx.anick(event), ctx.config
    )


ROUTES = [
    Route(r"^[#]?开会$", "cmd_meeting", "参加会议，随机事件", meeting),
    Route(r"^[#]?带饭(?:\s+@?\S+)?$", "cmd_bring_food", "帮同事带饭，+人脉", bring_food),
    Route(
        r"^[#]?(回消息|回工作消息)$",
        "cmd_reply_msg",
        "回复工作消息，+经验-精神",
        reply_msg,
    ),
    Route(r"^[#]?抢会议室$", "cmd_meeting_room", "抢会议室，随机结果", meeting_room),
    Route(
        r"^[#]?和同事吃饭(?:\s+@?\S+)?$", "cmd_eat_with", "和同事吃饭，+双方精神-钱", eat_with
    ),
    Route(
        r"^[#]?(帮领导做事|帮领导)$",
        "cmd_boss_task",
        "帮领导跑腿，有奖励有风险",
        boss_task,
    ),
    Route(r"^[#]?(行业峰会|峰会)$", "cmd_summit", "参加行业峰会，+经验+人脉", summit),
    Route(r"^[#]?(养猫|养狗)$", "cmd_adopt_pet", "领养宠物（猫或狗）", adopt_pet),
    Route(
        r"^[#]?(撸猫|遛狗|陪宠物)$",
        "cmd_pet_interact",
        "和宠物互动恢复精神",
        pet_interact,
    ),
    Route(
        r"^[#]?考证(?:书)?(?:\s+\S+)?$", "cmd_get_cert", "考行业证书（PMP/CPA/法考/CFA）", get_cert
    ),
    Route(r"^[#]?(旅游|出去旅游)$", "cmd_travel", "出去旅游，大幅恢复精神", travel),
]
