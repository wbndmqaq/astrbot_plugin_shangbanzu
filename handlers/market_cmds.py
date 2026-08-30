"""跳槽市场指令路由。"""

import asyncio

from ..core import career, logic
from ..core.result import R
from .base import GID_HINT, Route, gid_of


async def job_market(ctx, event):
    """跳槽市场：查看全部在招公司（含群友自建公司）。"""
    gid = gid_of(event)
    if not gid:
        return R(err=GID_HINT)
    companies = await career.hiring_pool(ctx.db, gid)
    companies.sort(key=lambda c: c["min_exp"])
    p = await asyncio.to_thread(ctx.db.get_player, gid, event.get_sender_id())
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
                    "fail": c["risk"] > 0.05,
                }
                for c in companies
            ],
        },
        text="跳槽市场："
        + "；".join(
            f"{c['name']}({logic.fmt_money(c['salary'])}元/月)" for c in companies
        ),
    )


ROUTES = [
    Route(
        r"^[#]?(跳槽市场|招聘市场)$",
        "cmd_job_market",
        "查看全部在招公司和薪资范围",
        job_market,
    ),
]
