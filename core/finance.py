"""金融系统服务：银行存取、信用升级、利息、转账、基金。"""

import asyncio
import math
import time

from . import logic
from .career import _load
from .result import R


def _fmt(x):
    return logic.fmt_money(x)


def _settle_fund(p):
    today = logic.today_str()
    if p["fund_day"] == today or float(p["fund"]) <= 0:
        return None
    change = logic.fund_daily_change()
    old = float(p["fund"])
    p["fund"] = round(old * (1 + change / 100.0), 2)
    if abs(p["fund"]) < 0.01:
        p["fund"] = 0.0
    p["fund_day"] = today
    return {"change": change, "old": round(old, 2), "new": float(p["fund"])}


async def deposit(db, gid, uid, amount, cfg, nickname=""):
    p = await _load(db, gid, uid, nickname, cfg)
    amt = int(amount) if str(amount).lstrip("-").isdigit() else 0
    if amt <= 0:
        return R(err="请输入正确的存款金额，例如「存款 500」")
    if amt > float(p["cash"]):
        return R(err=f"现金余额不足（当前 {_fmt(p['cash'])} 元）")
    space = float(p["bank_limit"]) - float(p["deposit"])
    if amt > space:
        return R(
            err=f"超过存储上限！当前上限 {logic.fmt_money(p['bank_limit'])} 元，还可存入 {_fmt(space)} 元，「升级信用」可提升额度"
        )
    p["cash"] = round(float(p["cash"]) - amt, 2)
    p["deposit"] = round(float(p["deposit"]) + amt, 2)
    await asyncio.to_thread(db.save_player, p)
    return R(
        tmpl="panel",
        data={
            "icon": "🏦",
            "title": "存款成功",
            "accent": "#6fe08c",
            "blocks": [
                {"label": "存入", "value": f"{_fmt(amt)} 元"},
                {"label": "存款余额", "value": f"{_fmt(p['deposit'])} 元"},
                {"label": "现金余额", "value": f"{_fmt(p['cash'])} 元"},
                {
                    "label": "利率说明",
                    "value": f"每小时 {float(logic.cfg_get(cfg, 'bank_interest_rate_hourly', 0.01)) * 100:.0f}%，最多计息 {int(logic.cfg_get(cfg, 'bank_max_interest_hours', 24))} 小时/天",
                },
            ],
            "foot": "记得每天「领取利息」",
        },
        text=f"存款成功！存入 {_fmt(amt)} 元，存款余额 {_fmt(p['deposit'])} 元",
    )


async def deposit_all(db, gid, uid, cfg, nickname=""):
    p = await _load(db, gid, uid, nickname, cfg)
    amt = round(float(p["cash"]), 2)
    if amt <= 0:
        return R(err="你的现金是 0 元，让我存个寂寞")
    space = float(p["bank_limit"]) - float(p["deposit"])
    if amt > space:
        return R(
            err=f"超过存储上限！当前上限 {_fmt(p['bank_limit'])} 元，还可存入 {_fmt(space)} 元"
        )
    p["cash"] = 0.0
    p["deposit"] = round(float(p["deposit"]) + amt, 2)
    await asyncio.to_thread(db.save_player, p)
    return R(
        tmpl="panel",
        data={
            "icon": "🏦",
            "title": "一键存款成功",
            "accent": "#6fe08c",
            "blocks": [
                {"label": "存入", "value": f"{_fmt(amt)} 元"},
                {"label": "存款余额", "value": f"{_fmt(p['deposit'])} 元"},
                {"label": "现金余额", "value": "0 元（月光族实锤）"},
            ],
        },
        text=f"全部存入成功！存款余额 {_fmt(p['deposit'])} 元",
    )


async def withdraw(db, gid, uid, amount, cfg, nickname=""):
    p = await _load(db, gid, uid, nickname, cfg)
    amt = int(amount) if str(amount).isdigit() else 0
    if amt <= 0:
        return R(err="请输入正确的取款金额，例如「取款 500」")
    if amt > float(p["deposit"]):
        return R(err=f"存款余额不足（当前存款 {_fmt(p['deposit'])} 元）")
    p["cash"] = round(float(p["cash"]) + amt, 2)
    p["deposit"] = round(float(p["deposit"]) - amt, 2)
    await asyncio.to_thread(db.save_player, p)
    return R(
        tmpl="panel",
        data={
            "icon": "💵",
            "title": "取款成功",
            "accent": "#ffd86f",
            "blocks": [
                {"label": "取出", "value": f"{_fmt(amt)} 元"},
                {"label": "存款余额", "value": f"{_fmt(p['deposit'])} 元"},
                {"label": "现金余额", "value": f"{_fmt(p['cash'])} 元"},
            ],
        },
        text=f"取款成功！取出 {_fmt(amt)} 元",
    )


async def upgrade_credit(db, gid, uid, max_mode, cfg, nickname=""):
    p = await _load(db, gid, uid, nickname, cfg)
    multi = float(logic.cfg_get(cfg, "bank_upgrade_price_multi", 1.2))
    limit_multi = float(logic.cfg_get(cfg, "bank_limit_increase_multi", 1.25))
    max_times = 99 if max_mode else 1
    spent = 0.0
    upgrades = 0
    while upgrades < max_times and float(p["cash"]) >= float(p["bank_upgrade_price"]):
        price = float(p["bank_upgrade_price"])
        p["cash"] = round(float(p["cash"]) - price, 2)
        spent = round(spent + price, 2)
        upgrades += 1
        p["bank_level"] = int(p["bank_level"]) + 1
        p["bank_limit"] = round(float(p["bank_limit"]) * limit_multi, 0)
        p["bank_upgrade_price"] = float(int(price * multi))
    if upgrades == 0:
        return R(
            err=f"升级需要 {_fmt(p['bank_upgrade_price'])} 元，当前现金 {_fmt(p['cash'])} 元不足"
        )
    await asyncio.to_thread(db.save_player, p)
    title = "一键升级信用成功" if max_mode else "升级信用成功"
    blocks = [
        {"label": "信用等级", "value": f"Lv.{p['bank_level']}"},
        {"label": "存储上限", "value": f"{_fmt(p['bank_limit'])} 元"},
        {"label": "下次升级费", "value": f"{_fmt(p['bank_upgrade_price'])} 元"},
        {"label": "现金余额", "value": f"{_fmt(p['cash'])} 元"},
    ]
    extra = (
        [{"label": "本次统计", "value": f"升级 {upgrades} 次，共花 {_fmt(spent)} 元"}]
        if max_mode
        else []
    )
    return R(
        tmpl="panel",
        data={
            "icon": "📈",
            "title": title,
            "accent": "#6fe08c",
            "blocks": blocks + extra,
        },
        text=f"{title}！Lv.{p['bank_level']}，上限 {_fmt(p['bank_limit'])} 元",
    )


async def bank_info(db, gid, uid, cfg, nickname=""):
    p = await _load(db, gid, uid, nickname, cfg)
    interest = logic.interest_of(
        float(p["deposit"]),
        int(p["last_interest"]),
        float(logic.cfg_get(cfg, "bank_interest_rate_hourly", 0.01)),
        int(logic.cfg_get(cfg, "bank_max_interest_hours", 24)),
    )
    fund_note = ""
    settle = _settle_fund(p)
    if settle and float(p["fund"]) > 0:
        emoji = "📈" if settle["change"] >= 0 else "📉"
        fund_note = f"今日基金{emoji} {settle['change']:+.2f}%"
        await asyncio.to_thread(db.save_player, p)
    return R(
        tmpl="panel",
        data={
            "icon": "🏦",
            "title": "上班族银行 · 账户信息",
            "accent": "#7fd1ff",
            "subtitle": fund_note,
            "blocks": [
                {"label": "现金", "value": f"{_fmt(p['cash'])} 元"},
                {"label": "存款", "value": f"{_fmt(p['deposit'])} 元"},
                {"label": "基金持仓", "value": f"{_fmt(p['fund'])} 元"},
                {
                    "label": "总资产",
                    "value": f"{_fmt(round(float(p['cash']) + float(p['deposit']) + float(p['fund']), 2))} 元",
                },
                {
                    "label": "信用等级",
                    "value": f"Lv.{p['bank_level']}（上限 {_fmt(p['bank_limit'])} 元）",
                },
                {"label": "下次升级费", "value": f"{_fmt(p['bank_upgrade_price'])} 元"},
                {"label": "可领利息", "value": f"{_fmt(interest)} 元"},
            ],
        },
        text=f"银行信息：现金{_fmt(p['cash'])} 存款{_fmt(p['deposit'])} 基金{_fmt(p['fund'])} 可领利息{_fmt(interest)}",
    )


async def collect_interest(db, gid, uid, cfg, nickname=""):
    p = await _load(db, gid, uid, nickname, cfg)
    rate = float(logic.cfg_get(cfg, "bank_interest_rate_hourly", 0.01))
    max_h = int(logic.cfg_get(cfg, "bank_max_interest_hours", 24))
    interest = logic.interest_of(
        float(p["deposit"]), int(p["last_interest"]), rate, max_h
    )
    if interest <= 0:
        return R(err="当前没有可领取的利息（每小时结算一次，存款才有利息哦）")
    p["cash"] = round(float(p["cash"]) + interest, 2)
    p["last_interest"] = int(time.time())
    await asyncio.to_thread(db.save_player, p)
    return R(
        tmpl="panel",
        data={
            "icon": "🪙",
            "title": "利息到账",
            "accent": "#6fe08c",
            "blocks": [
                {"label": "本次利息", "value": f"+{_fmt(interest)} 元"},
                {"label": "存款", "value": f"{_fmt(p['deposit'])} 元"},
                {"label": "现金", "value": f"{_fmt(p['cash'])} 元"},
            ],
        },
        text=f"领取利息 +{_fmt(interest)} 元",
    )


async def transfer(db, gid, me, target, amount, cfg, target_name=""):
    p = await _load(db, gid, me, "", cfg)
    td = await _load(db, gid, target, target_name, cfg)
    amt = int(amount) if str(amount).isdigit() else 0
    min_amt = int(logic.cfg_get(cfg, "transfer_min_amount", 100))
    if amt < min_amt:
        return R(err=f"转账金额不能低于 {min_amt} 元")
    if str(target) == str(me):
        return R(err="不能给自己转账，左手倒右手没有意义")
    fee = math.ceil(amt * float(logic.cfg_get(cfg, "transfer_fee_rate", 0.1)))
    total = amt + fee
    if float(p["cash"]) < total:
        return R(err=f"余额不足：需要 {total} 元（本金 {amt} + 手续费 {fee}）")
    p["cash"] = round(float(p["cash"]) - total, 2)
    td["cash"] = round(float(td["cash"]) + amt, 2)
    tname = td.get("card") or td["nickname"] or target_name or f"用户{target}"
    await asyncio.to_thread(db.save_player, p)
    await asyncio.to_thread(db.save_player, td)
    return R(
        tmpl="panel",
        data={
            "icon": "💸",
            "title": "转账成功",
            "accent": "#6fe08c",
            "blocks": [
                {"label": "收款人", "value": tname},
                {"label": "金额", "value": f"+{_fmt(amt)} 元"},
                {"label": "手续费", "value": f"-{_fmt(fee)} 元"},
                {"label": "剩余现金", "value": f"{_fmt(p['cash'])} 元"},
            ],
        },
        text=f"已向 {tname} 转账 {_fmt(amt)} 元（手续费 {_fmt(fee)}），剩余 {_fmt(p['cash'])} 元",
    )


async def fund_buy(db, gid, uid, amount, cfg, nickname=""):
    p = await _load(db, gid, uid, nickname, cfg)
    settle = _settle_fund(p)
    amt = int(amount) if str(amount).isdigit() else 0
    if amt <= 0:
        return R(err="请输入正确的买入金额，例如「买基金 1000」")
    fee = math.ceil(amt * float(logic.cfg_get(cfg, "fund_fee_rate", 0.005)))
    total = amt + fee
    if float(p["cash"]) < total:
        return R(
            err=f"买入需要 {total} 元（含手续费 {fee}），现金不足。温馨提示：基金有风险，梭哈需谨慎"
        )
    p["cash"] = round(float(p["cash"]) - total, 2)
    p["fund"] = round(float(p["fund"]) + amt, 2)
    await asyncio.to_thread(db.save_player, p)
    note_lines = []
    if settle:
        emoji = "📈" if settle["change"] >= 0 else "📉"
        note_lines.append(f"今日净值波动：{emoji} {settle['change']:+.2f}%")
    return R(
        tmpl="panel",
        data={
            "icon": "📊",
            "title": "申购成功 · 祝你好运",
            "accent": "#ffd86f",
            "lines": note_lines,
            "blocks": [
                {"label": "买入金额", "value": f"{_fmt(amt)} 元"},
                {"label": "手续费", "value": f"-{_fmt(fee)} 元"},
                {"label": "当前持仓", "value": f"{_fmt(p['fund'])} 元"},
                {"label": "现金余额", "value": f"{_fmt(p['cash'])} 元"},
            ],
            "foot": "基金每日自动结算涨跌，绿了别哭，红了别飘",
        },
        text=f"买入基金 {_fmt(amt)} 元（手续费 {_fmt(fee)}），当前持仓 {_fmt(p['fund'])}",
    )


async def fund_sell(db, gid, uid, ratio_str, cfg, nickname=""):
    p = await _load(db, gid, uid, nickname, cfg)
    if float(p["fund"]) <= 0:
        return R(err="你还没有持仓，拿什么卖？「买基金」先上车")
    settle = _settle_fund(p)
    rs = (ratio_str or "").strip()
    hold = float(p["fund"])
    if not rs or rs in ("全部", "all"):
        ratio = 1.0
    elif rs.endswith("%") and rs[:-1].replace(".", "", 1).isdigit():
        ratio = min(1.0, max(0.01, float(rs[:-1]) / 100.0))
    elif rs.isdigit():
        ratio = min(1.0, max(0.01, float(rs) / 100.0))
    else:
        ratio = 1.0
    sell_amount = round(hold * ratio, 2)
    fee = math.ceil(sell_amount * float(logic.cfg_get(cfg, "fund_fee_rate", 0.005)))
    income = max(0, int(sell_amount - fee))
    p["fund"] = round(hold - sell_amount, 2)
    if abs(p["fund"]) < 0.01:
        p["fund"] = 0.0
    p["cash"] = round(float(p["cash"]) + income, 2)
    await asyncio.to_thread(db.save_player, p)
    lines = []
    if settle:
        emoji = "📈" if settle["change"] >= 0 else "📉"
        lines.append(f"今日净值波动：{emoji} {settle['change']:+.2f}%")
    profit_word = "割肉离场" if income < sell_amount else "落袋为安"
    return R(
        tmpl="panel",
        data={
            "icon": "💰",
            "title": f"赎回成功 · {profit_word}",
            "accent": "#7fd1ff",
            "lines": lines,
            "blocks": [
                {
                    "label": "赎回份额",
                    "value": f"{ratio * 100:.0f}%（{_fmt(sell_amount)} 元）",
                },
                {"label": "手续费", "value": f"-{_fmt(fee)} 元"},
                {"label": "实际到账", "value": f"{_fmt(income)} 元"},
                {"label": "剩余持仓", "value": f"{_fmt(p['fund'])} 元"},
            ],
        },
        text=f"赎回 {_fmt(sell_amount)} 元，到账 {_fmt(income)} 元，剩余持仓 {_fmt(p['fund'])}",
    )
