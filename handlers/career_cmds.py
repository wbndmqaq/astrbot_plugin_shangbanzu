"""职业线指令路由。"""

from ..core import career
from ..core.result import R
from .base import Route

GID_HINT = "该游戏只能在群聊中使用"


def _gid(event):
    return event.get_group_id() or ""


async def find_job(ctx, event):
    gid = _gid(event)
    if not gid:
        return R(err=GID_HINT)
    import re

    m = re.search(r"(?:找工作|求职)\s*([^\s#/]+)?", event.message_str or "")
    want = (m.group(1) if m and m.group(1) else "").strip()
    return await career.find_job(
        ctx.db, gid, event.get_sender_id(), ctx.nick(event), ctx.config, want
    )


async def my_company(ctx, event):
    gid = _gid(event)
    if not gid:
        return R(err=GID_HINT)
    return await career.my_company(
        ctx.db, gid, event.get_sender_id(), ctx.nick(event), ctx.config
    )


async def checkin(ctx, event):
    gid = _gid(event)
    if not gid:
        return R(err=GID_HINT)
    return await career.checkin(
        ctx.db, gid, event.get_sender_id(), ctx.nick(event), ctx.config
    )


async def slack(ctx, event):
    gid = _gid(event)
    if not gid:
        return R(err=GID_HINT)
    return await career.slack(
        ctx.db, gid, event.get_sender_id(), ctx.nick(event), ctx.config
    )


async def overtime(ctx, event):
    gid = _gid(event)
    if not gid:
        return R(err=GID_HINT)
    return await career.overtime(
        ctx.db, gid, event.get_sender_id(), ctx.nick(event), ctx.config
    )


async def take_leave(ctx, event):
    gid = _gid(event)
    if not gid:
        return R(err=GID_HINT)
    return await career.take_leave(
        ctx.db, gid, event.get_sender_id(), ctx.nick(event), ctx.config
    )


async def promote(ctx, event):
    gid = _gid(event)
    if not gid:
        return R(err=GID_HINT)
    return await career.promote(
        ctx.db, gid, event.get_sender_id(), ctx.nick(event), ctx.config
    )


async def resign_job(ctx, event):
    gid = _gid(event)
    if not gid:
        return R(err=GID_HINT)
    return await career.resign_job(
        ctx.db, gid, event.get_sender_id(), ctx.nick(event), ctx.config
    )


async def job_hop(ctx, event):
    gid = _gid(event)
    if not gid:
        return R(err=GID_HINT)
    return await career.job_hop(
        ctx.db, gid, event.get_sender_id(), ctx.nick(event), ctx.config
    )


async def write_report(ctx, event):
    gid = _gid(event)
    if not gid:
        return R(err=GID_HINT)
    return await career.write_report(
        ctx.db, gid, event.get_sender_id(), ctx.nick(event), ctx.config
    )


async def comp_leave(ctx, event):
    gid = _gid(event)
    if not gid:
        return R(err=GID_HINT)
    return await career.take_comp_leave(
        ctx.db, gid, event.get_sender_id(), ctx.nick(event), ctx.config
    )


ROUTES = [
    Route(
        r"^[#]?(找工作|求职)(\s*[^\s#/]+)?\s*$",
        "cmd_find_job",
        "投简历入职公司；可指定公司名，如：找工作 蓝色大厂",
        find_job,
    ),
    Route(
        r"^[#]?(我的公司|公司信息)$",
        "cmd_my_company",
        "查看当前雇主公司详情",
        my_company,
    ),
    Route(
        r"^[#]?(上班|打卡)$",
        "cmd_checkin",
        "每日打卡上班领日薪（含通勤与五险一金）",
        checkin,
    ),
    Route(r"^[#]?摸鱼$", "cmd_slack", "摸鱼恢复精神，小心被抓", slack),
    Route(r"^[#]?加班$", "cmd_overtime", "加班赚钱涨经验，可能获得调休券", overtime),
    Route(r"^[#]?请个?假$", "cmd_leave", "请假回血（每周限2次）", take_leave),
    Route(
        r"^[#]?(请调休|调休)$", "cmd_comp_leave", "使用调休券带薪休息一天", comp_leave
    ),
    Route(
        r"^[#]?(写周报|周报)$",
        "cmd_write_report",
        "每周提交一次周报，评级S/A/B拿绩效奖",
        write_report,
    ),
    Route(r"^[#]?(晋升|升职)$", "cmd_promote", "晋升职级", promote),
    Route(r"^[#](辞职|离职)$", "cmd_resign", "辞掉公司工作", resign_job),
    Route(r"^[#]?跳槽$", "cmd_hop", "跳槽换公司", job_hop),
]
