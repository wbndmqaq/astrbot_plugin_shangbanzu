"""扩展玩法第二批指令路由。"""

from ..core import extra2
from ..core.result import R
from .base import Route

GID = "该功能只能在群聊中使用"


async def party(ctx, event):
    gid = event.get_group_id() or ""
    if not gid:
        return R(err=GID)
    return await extra2.party_lottery(
        ctx.db, gid, event.get_sender_id(), ctx.nick(event), ctx.config
    )


async def lend(ctx, event):
    gid = event.get_group_id() or ""
    if not gid:
        return R(err=GID)
    me = str(event.get_sender_id())
    ats = ctx.ats(event)
    nums = ctx.nums(event, ("借钱", "借"))
    target = (ats[0] if ats else None) or (
        nums[0] if nums and nums[0].isdigit() and len(nums[0]) >= 5 else ""
    )
    amount = nums[-1] if nums else "0"
    if not target:
        return R(err="请@要借钱的群友，如：借钱 @群友 500")
    return await extra2.lend_money(
        ctx.db, gid, me, target, amount, ctx.config, ctx.nick(event, target)
    )


async def advice(ctx, event):
    return await extra2.career_advice()


async def workstation(ctx, event):
    gid = event.get_group_id() or ""
    if not gid:
        return R(err=GID)
    return await extra2.upgrade_workstation(
        ctx.db, gid, event.get_sender_id(), ctx.nick(event), ctx.config
    )


async def ot_meal(ctx, event):
    gid = event.get_group_id() or ""
    if not gid:
        return R(err=GID)
    return await extra2.overtime_meal(
        ctx.db, gid, event.get_sender_id(), ctx.nick(event), ctx.config
    )


async def checkup(ctx, event):
    gid = event.get_group_id() or ""
    if not gid:
        return R(err=GID)
    return await extra2.health_checkup(
        ctx.db, gid, event.get_sender_id(), ctx.nick(event), ctx.config
    )


ROUTES = [
    Route(r"^[#]?(年会抽奖|年会)$", "cmd_party", "年会抽奖（每年限一次）", party),
    Route(r"^[#]?借钱\s+\S+", "cmd_lend", "借钱 @群友 N（可能收不回来）", lend),
    Route(r"^[#/]?(职场建议|建议)$", "cmd_advice", "随机职场生存建议", advice),
    Route(
        r"^[#/]?(工位升级|升级工位)$",
        "cmd_workstation",
        "升级工位提高摸鱼舒适度",
        workstation,
    ),
    Route(r"^[#/]?(加班餐|加班饭)$", "cmd_ot_meal", "加班餐补贴（一天一次）", ot_meal),
    Route(r"^[#/]?(年度体检|体检)$", "cmd_checkup", "年度体检，可能查出问题", checkup),
]
