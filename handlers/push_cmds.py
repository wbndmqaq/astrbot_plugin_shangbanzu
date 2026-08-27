"""推送开关指令路由。"""

import asyncio

from ..core.result import R
from .base import Route

GID = "该功能只能在群聊中使用"


async def toggle_push(ctx, event):
    gid = event.get_group_id() or ""
    if not gid:
        return R(err=GID)
    cur = await asyncio.to_thread(ctx.db.push_enabled, gid)
    await asyncio.to_thread(ctx.db.set_push, gid, not cur)
    state = "已开启" if not cur else "已关闭"
    body = (
        "开启后，每天早上会向本群推送职场早报与股市摘要。"
        if not cur
        else "本群将不再接收每日早报推送。"
    )
    return R(
        tmpl="panel",
        data={
            "icon": "🔔" if not cur else "🔕",
            "title": f"推送{state}",
            "accent": "#6fe08c" if not cur else "#fc6262",
            "lines": [body],
        },
        text=f"本群推送{state}。{body}",
    )


async def push_status(ctx, event):
    gid = event.get_group_id() or ""
    if not gid:
        return R(err=GID)
    on = await asyncio.to_thread(ctx.db.push_enabled, gid)
    groups = await asyncio.to_thread(ctx.db.push_group_ids)
    return R(
        tmpl="panel",
        data={
            "icon": "📡",
            "title": "推送状态",
            "accent": "#7fd1ff",
            "lines": ["推送内容：每日职场早报 + 股市摘要"],
            "blocks": [
                {"label": "本群推送", "value": "已开启" if on else "未开启"},
                {"label": "全服开启群数", "value": f"{len(groups)} 群"},
                {"label": "切换方式", "value": "发送「推送」"},
            ],
        },
        text=f"推送{'已' if on else '未'}开启（全服 {len(groups)} 群）",
    )


ROUTES = [
    Route(r"^[#]?推送$", "cmd_push_toggle", "切换本群推送开关", toggle_push),
    Route(r"^[#]?(推送状态|推送信息)$", "cmd_push_status", "查看推送状态", push_status),
]
