"""扩展生活指令路由第二批。"""

import asyncio
import random

from ..core import gamedata as gd
from ..core import logic
from ..core.result import R
from .base import Route

GID = "该功能只能在群聊中使用"


async def job_market(ctx, event):
    """跳槽市场：查看全部在招公司。"""
    companies = gd.companies()
    companies.sort(key=lambda c: c["min_exp"])
    rows = []
    for c in companies:
        rows.append(
            {
                "cells": [
                    f"{c['name']}（{c['tag']}）",
                    f"{logic.fmt_money(c['salary'])} 元/月",
                    f"门槛 {c['min_exp']} 经验",
                    f"裁员率 {c['risk'] * 100:.1f}%",
                ],
                "fail": c["risk"] > 0.05,
            }
        )
    exp = 0
    p = await asyncio.to_thread(
        ctx.db.get_player, event.get_group_id(), event.get_sender_id()
    )
    exp = int(p["exp"])
    eligible = [c for c in companies if c["min_exp"] <= exp]
    return R(
        tmpl="table",
        data={
            "icon": "📋",
            "title": f"跳槽市场（你的经验：{exp}）",
            "accent": "#7fd1ff",
            "summary": [
                {"label": "在招公司", "value": f"{len(companies)} 家"},
                {"label": "你可投递", "value": f"{len(eligible)} 家"},
            ],
            "cols": ["公司", "月薪", "门槛", "风险"],
            "rows": [
                {
                    "cells": [
                        f"{c['name']}（{c['tag']}）",
                        f"{logic.fmt_money(c['salary'])} 元",
                        f"{c['min_exp']} 经验",
                        f"{c['risk'] * 100:.1f}%",
                    ],
                    "fail": False,
                }
                for c in companies
            ],
        },
        text="跳槽市场："
        + "；".join(
            f"{c['name']}({logic.fmt_money(c['salary'])}元/月)" for c in companies
        ),
    )


async def gossip_cmd(ctx, event):
    gid = event.get_group_id() or ""
    if not gid:
        return R(err=GID)
    return await extra_gossip(ctx, gid, event)


async def extra_gossip(ctx, gid, event):
    all_players = await asyncio.to_thread(ctx.db.all_players, gid)
    if len(all_players) < 2:
        return R(err=empty_hint("群里的打工人太少了"))
    uids = list(all_players.keys())
    a, b = random.sample(uids, 2)
    an = all_players[a].get("card") or all_players[a]["nickname"] or f"用户{a}"
    bn = all_players[b].get("card") or all_players[b]["nickname"] or f"用户{b}"
    text = random.choice(gd.t("extra", "gossip_texts"))
    gossip = text.replace("{a}", an).replace("{b}", bn)
    return R(
        tmpl="panel",
        data={
            "icon": "☕",
            "title": "今日职场八卦",
            "accent": "#b48cff",
            "lines": [gossip],
            "foot": "八卦仅供娱乐，请勿当真",
        },
        text=f"☕ {gossip}",
    )


def empty_hint(text):
    return text


ROUTES = [
    Route(
        r"^[#/]?(跳槽市场|招聘市场)$",
        "cmd_job_market",
        "查看全部在招公司和薪资范围",
        job_market,
    ),
]
