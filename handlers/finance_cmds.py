"""理财线指令路由：银行、利息、转账、基金。"""

from ..core import finance
from ..core.result import R
from .base import GID_HINT, Route, gid_of


async def deposit(ctx, event):
    gid = gid_of(event)
    if not gid:
        return R(err=GID_HINT)
    nums = ctx.nums(event, ("存款",))
    return await finance.deposit(
        ctx.db,
        gid,
        event.get_sender_id(),
        nums[0] if nums else "0",
        ctx.config,
        await ctx.anick(event),
    )


async def deposit_all(ctx, event):
    gid = gid_of(event)
    if not gid:
        return R(err=GID_HINT)
    return await finance.deposit_all(
        ctx.db, gid, event.get_sender_id(), ctx.config, await ctx.anick(event)
    )


async def withdraw(ctx, event):
    gid = gid_of(event)
    if not gid:
        return R(err=GID_HINT)
    nums = ctx.nums(event, ("取款",))
    return await finance.withdraw(
        ctx.db,
        gid,
        event.get_sender_id(),
        nums[0] if nums else "0",
        ctx.config,
        await ctx.anick(event),
    )


async def upgrade_credit(ctx, event):
    gid = gid_of(event)
    if not gid:
        return R(err=GID_HINT)
    max_mode = "一键" in (event.message_str or "")
    return await finance.upgrade_credit(
        ctx.db, gid, event.get_sender_id(), max_mode, ctx.config, await ctx.anick(event)
    )


async def bank_info(ctx, event):
    gid = gid_of(event)
    if not gid:
        return R(err=GID_HINT)
    return await finance.bank_info(
        ctx.db, gid, event.get_sender_id(), ctx.config, await ctx.anick(event)
    )


async def collect_interest(ctx, event):
    gid = gid_of(event)
    if not gid:
        return R(err=GID_HINT)
    return await finance.collect_interest(
        ctx.db, gid, event.get_sender_id(), ctx.config, await ctx.anick(event)
    )


async def transfer(ctx, event):
    gid = gid_of(event)
    if not gid:
        return R(err=GID_HINT)
    ats = ctx.ats(event)
    if not ats:
        return R(err="请@收款人，如：转账 500 @群友")
    # 有 @ 时先剔除收款人 QQ，避免适配器把 @ 渲染成数字文本后金额误取为 QQ 号
    amount = ctx.amount_after(event, ("转账",), (ats[0],))
    return await finance.transfer(
        ctx.db,
        gid,
        str(event.get_sender_id()),
        ats[0],
        amount,
        ctx.config,
        await ctx.anick(event, ats[0]),
    )


async def fund_buy(ctx, event):
    gid = gid_of(event)
    if not gid:
        return R(err=GID_HINT)
    nums = ctx.nums(event, ("买基金",))
    return await finance.fund_buy(
        ctx.db,
        gid,
        event.get_sender_id(),
        nums[0] if nums else "0",
        ctx.config,
        await ctx.anick(event),
    )


async def fund_sell(ctx, event):
    gid = gid_of(event)
    if not gid:
        return R(err=GID_HINT)
    # 「卖出基金」= 全部赎回；「卖出基金 50」= 赎回 50%；
    # 「卖出基金 50%」= 同上。
    ratio = ""
    rest = (event.message_str or "").split("基金", 1)
    if len(rest) == 2:
        head = rest[1].strip()
        ratio = head.split()[0] if head else ""
    return await finance.fund_sell(
        ctx.db, gid, event.get_sender_id(), ratio, ctx.config, await ctx.anick(event)
    )


ROUTES = [
    Route(r"^[#]?存款(?:\s*\d+)?$", "cmd_deposit", "把钱存进银行吃利息", deposit),
    Route(
        r"^[#]?(一键存款|全部存款)$", "cmd_deposit_all", "全部现金存入银行", deposit_all
    ),
    Route(r"^[#]?取款(?:\s*\d+)?$", "cmd_withdraw", "从银行取款", withdraw),
    Route(
        r"^[#]?(一键升级信用|升级信用)$",
        "cmd_upgrade_credit",
        "升级信用等级提高存款上限",
        upgrade_credit,
    ),
    Route(
        r"^[#]?(银行信息|我的银行|账户信息)$",
        "cmd_bank_info",
        "查看银行账户与基金持仓",
        bank_info,
    ),
    Route(r"^[#]?领取利息$", "cmd_interest", "领取存款利息", collect_interest),
    Route(r"^[#]?转账(?:\s+@?\S+)?(?:\s+\d+)?$", "cmd_transfer", "向群友转账（收手续费）", transfer),
    Route(
        r"^[#]?买基金(?:\s*\d+)?$", "cmd_fund_buy", "申购基金（每日自动结算涨跌）", fund_buy
    ),
    Route(
        r"^[#]?卖出基金(?:\s*\S+)?$",
        "cmd_fund_sell",
        "赎回基金，可带比例如：卖出基金 50%",
        fund_sell,
    ),
]

