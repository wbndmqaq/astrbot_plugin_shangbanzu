"""股票交易指令路由：行情、买入、卖出、持仓。"""

import asyncio
import re

from ..core import logic
from ..core.result import R
from .base import GID_HINT, Route, gid_of


def _fmt(x):
    return logic.fmt_money(x)


async def market_overview(ctx, event):
    gid = gid_of(event)
    if not gid:
        return R(err=GID_HINT)
    await ctx.star.market.settle_if_needed()
    stocks = await asyncio.to_thread(ctx.star.market.list_stocks, 100)

    up = [s for s in stocks if s["chg"] > 0]
    down = [s for s in stocks if s["chg"] < 0]
    top_up = sorted(up, key=lambda s: -s["chg"])[:5]
    top_down = sorted(down, key=lambda s: s["chg"])[:5]

    rows = []
    for s in top_up:
        rows.append(
            {
                "cells": [
                    "🔴",
                    f"{s['name']}({s['code']})",
                    f"{s['price']}",
                    f"+{s['chg']}%",
                ],
                "fail": False,
            }
        )
    for s in top_down:
        rows.append(
            {
                "cells": [
                    "🟢",
                    f"{s['name']}({s['code']})",
                    f"{s['price']}",
                    f"{s['chg']}%",
                ],
                "fail": True,
            }
        )

    summary = [
        {"label": "上涨", "value": f"{len(up)} 支"},
        {"label": "下跌", "value": f"{len(down)} 支"},
        {"label": "平盘", "value": f"{len(stocks) - len(up) - len(down)} 支"},
        {"label": "总市值", "value": f"{_fmt(sum(s['price'] for s in stocks))} 元"},
    ]
    return R(
        tmpl="table",
        data={
            "icon": "📈",
            "title": "股市大盘 · 涨跌幅TOP10",
            "accent": "#ffd86f",
            "summary": summary,
            "cols": ["", "股票", "现价(元)", "涨跌"],
            "rows": rows,
        },
        text=(
            f"📈 股市大盘\n上涨 {len(up)} | 下跌 {len(down)}\n"
            + "\n".join(f"🔴 {s['name']} {s['chg']:+}%" for s in top_up[:3])
            + "\n"
            + "\n".join(f"🟢 {s['name']} {s['chg']:+}%" for s in top_down[:3])
        ),
    )


async def buy_stock(ctx, event):
    gid = gid_of(event)
    if not gid:
        return R(err=GID_HINT)
    m = re.search(r"(?:买股票|买入)\s+(\S+)\s+(\d+)", event.message_str or "")
    if not m:
        return R(err="格式：买股票 <代码或名称> <金额>\n例如：买股票 sh600037 5000")
    me = str(event.get_sender_id())
    key = m.group(1)
    min_amt = int(ctx.c("stock_min_buy_amount", 1))
    amt = logic.parse_int(m.group(2), lo=min_amt)
    if amt is None:
        return R(err=f"买入金额需为 {min_amt} ~ 999999999999 之间的整数")

    p = await asyncio.to_thread(ctx.db.get_player, gid, me, await ctx.anick(event))
    fee_rate = float(ctx.c("stock_fee_rate", 0.005))
    if float(p["cash"]) < amt:
        return R(err=f"现金不足（当前 {_fmt(p['cash'])} 元）")

    try:
        r = await ctx.star.market.buy(gid, me, key, float(amt), fee_rate)
    except ValueError:
        return R(err=f"现金不足（当前 {_fmt(p['cash'])} 元）")
    if r == "too_many":
        return R(
            err=f"持仓只数已达上限（{ctx.c('stock_max_positions', 50)} 只），"
            "先「卖出 <代码>」腾出仓位"
        )
    if r is None:
        return R(err=f"没有找到「{key}」这支股票，发送「股市」查看行情列表")

    # 扣款已在市场事务内完成，这里只读最新余额用于展示
    p = await asyncio.to_thread(ctx.db.get_player, gid, me)
    await asyncio.to_thread(
        ctx.db.add_transaction,
        gid,
        me,
        "买入股票",
        -amt,
        r["stock"]["name"],
    )
    st = r["stock"]
    emoji = "📈" if st["chg"] >= 0 else "📉"
    return R(
        tmpl="panel",
        data={
            "icon": emoji,
            "title": f"买入成功 · {st['name']}",
            "accent": "#6fe08c" if st["chg"] >= 0 else "#fc6262",
            "blocks": [
                {"label": "代码", "value": st["code"]},
                {
                    "label": "现价",
                    "value": f"{_fmt(st['price'])} 元（今日 {st['chg']:+}%）",
                },
                {"label": "买入金额", "value": f"{_fmt(r['amount'])} 元"},
                {"label": "手续费", "value": f"-{_fmt(fee_rate * r['amount'])} 元"},
                {"label": "获得份额", "value": f"{r['shares']} 份"},
                {"label": "剩余现金", "value": f"{_fmt(p['cash'])} 元"},
            ],
            "foot": "发送「持仓」查看盈亏；股价每日自动波动，绿了别哭红了别飘",
        },
        text=f"买入 {st['name']} 成功！花费 {_fmt(amt)} 元，获得 {r['shares']} 份",
    )


async def sell_stock(ctx, event):
    gid = gid_of(event)
    if not gid:
        return R(err=GID_HINT)
    m = re.search(
        r"(?:卖出|卖股票|清仓)\s+(\S+?)(?:\s+(\d+)\s*%?)?\s*$",
        event.message_str or "",
    )
    if not m:
        return R(
            err="格式：卖股票 <代码或名称> [比例%]\n例如：卖股票 sh600037 或 卖出 华晨通信 50"
        )
    me = str(event.get_sender_id())
    key = m.group(1)
    ratio = logic.parse_int(m.group(2), default=100, lo=1, hi=100) if m.group(2) else 100
    if ratio is None:
        return R(err="卖出比例需在 1~100 之间")

    fee_rate = float(ctx.c("stock_fee_rate", 0.005))
    pos = await ctx.star.market.position_of(gid, me, key)
    if not pos:
        return R(err=f"你没有持有「{key}」的仓位")

    r = await ctx.star.market.sell(gid, me, key, ratio / 100.0, fee_rate)
    if r is None:
        return R(err="卖出失败：份额不足或已清仓")

    # 入账已在市场事务内完成，这里只读最新余额用于展示
    p = await asyncio.to_thread(ctx.db.get_player, gid, me)
    await asyncio.to_thread(
        ctx.db.add_transaction,
        gid,
        me,
        "卖出股票",
        r["income"],
        f"{r['name']} 盈亏{r['profit']:+}",
    )
    icon = "🎉" if r["profit"] > 0 else "😢"
    accent = "#6fe08c" if r["profit"] > 0 else "#fc6262"
    return R(
        tmpl="panel",
        data={
            "icon": icon,
            "title": f"{'止盈' if r['profit'] > 0 else '割肉'}完成 · {r['name']}",
            "accent": accent,
            "blocks": [
                {"label": "卖出份额", "value": f"{r['shares']} 份（{ratio}%）"},
                {
                    "label": "到账金额",
                    "value": f"+{_fmt(r['income'])} 元（含手续费-{_fmt(r['fee'])}）",
                },
                {
                    "label": "本次盈亏",
                    "value": ("+" if r["profit"] >= 0 else "")
                    + _fmt(r["profit"])
                    + " 元",
                },
                {"label": "剩余现金", "value": f"{_fmt(p['cash'])} 元"},
            ],
        },
        text=f"卖出 {r['name']}：到账 {_fmt(r['income'])} 元（盈亏 {r['profit']:+} 元）",
    )


async def my_portfolio(ctx, event):
    gid = gid_of(event)
    if not gid:
        return R(err=GID_HINT)
    await ctx.star.market.settle_if_needed()
    positions = await ctx.star.market.my_positions(gid, str(event.get_sender_id()))
    if not positions:
        return R(err="你还没有任何持仓，「买股票 <代码> <金额>」开始投资之旅")
    rows = []
    for i, pos in enumerate(positions[:20], 1):
        rows.append(
            {
                "cells": [
                    f"{i}. {pos['name']}({pos['code']})",
                    f"{pos['shares']} 份",
                    f"{_fmt(pos['market_value'])} 元",
                ],
                "fail": False,
            }
        )
    return R(
        tmpl="table",
        data={
            "icon": "💼",
            "title": "我的股票持仓",
            "accent": "#7fd1ff",
            "summary": [
                {"label": "持仓支数", "value": f"{len(positions)}"},
                {
                    "label": "持仓市值",
                    "value": f"{_fmt(sum(p['market_value'] for p in positions))} 元",
                },
            ],
            "cols": ["股票", "份额", "市值"],
            "rows": rows,
        },
        text="持仓："
        + "；".join(f"{p['name']}({_fmt(p['market_value'])}元)" for p in positions),
    )


ROUTES = [
    Route(
        r"^[#]?(股市|大盘|行情|股市行情)$",
        "cmd_market",
        "查看股市涨跌TOP10与市场概况",
        market_overview,
    ),
    Route(
        r"^[#]?(我的股票|持仓)$",
        "cmd_my_portfolio",
        "查看个人股票持仓与市值",
        my_portfolio,
    ),
    Route(
        r"^[#]?(买股票|买入)\s+\S+\s+\d+$",
        "cmd_buy_stock",
        "按金额买入指定股票（买股票/买入均可）",
        buy_stock,
        priority=1,
    ),
    Route(
        r"^[#]?(卖出|卖股票|清仓)(?:\s+\S+)?(?:\s+\d+%?)?$",
        "cmd_sell_stock",
        "卖出股票，可带比例如「卖出 xx 50」",
        sell_stock,
        priority=1,
    ),
]
