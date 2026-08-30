"""备份管理指令路由（管理员）。"""

import asyncio
import re

from ..core.result import R
from .base import Route

_KEY_HINT = "请指定备份序号或完整名称，例如「恢复备份 1」；发送「备份列表」查看"


async def backup_create(ctx, event):
    m = re.search(r"备份\s+(\S+)", event.message_str or "")
    label = m.group(1) if m else ""
    info = await asyncio.to_thread(ctx.star.backups.create, label)
    if info is None:
        return R(err="备份失败，请查看控制台日志")
    return R(
        tmpl="panel",
        data={
            "icon": "💾",
            "title": "备份创建成功",
            "accent": "#6fe08c",
            "blocks": [
                {"label": "备份名称", "value": info["name"]},
                {"label": "大小", "value": f"{info['size'] // 1024} KB"},
                {"label": "位置", "value": "data/plugin_data/astrbot_plugin_shangbanzu/backups/"},
                {"label": "恢复方式", "value": f"恢复备份 {info['name']}"},
            ],
            "foot": f"备份为 SQLite 在线快照，可在运行时安全创建；仅保留最新 {ctx.star.backups.max_keep} 个",
        },
        text=f"备份成功：{info['name']}（{info['size'] // 1024} KB）",
    )


async def backup_list(ctx, event):
    items = await asyncio.to_thread(ctx.star.backups.list)
    if not items:
        return R(err="当前没有任何备份，发送「创建备份」生成第一个")
    rows = [
        {
            "cells": [str(i), it["name"], f"{it['size'] // 1024} KB", it["time"]],
            "fail": False,
        }
        for i, it in enumerate(items, 1)
    ]
    return R(
        tmpl="table",
        data={
            "icon": "🗄️",
            "title": f"备份列表（{len(items)}）",
            "accent": "#7fd1ff",
            "summary": [{"label": "备份数量", "value": f"{len(items)} 个"}],
            "cols": ["序号", "备份名称", "大小", "创建时间"],
            "rows": rows,
            "note": "恢复/删除请使用序号，或备份的完整名称",
        },
        text="备份列表：" + "；".join(f"{i}. {it['name']}" for i, it in enumerate(items, 1)),
    )


def _key(message: str, verb: str) -> str:
    m = re.search(rf"{verb}\s+(\S+)", message or "")
    return m.group(1) if m else ""


async def backup_restore(ctx, event):
    key = _key(event.message_str, "恢复备份")
    if not key:
        return R(err=_KEY_HINT)
    item = await asyncio.to_thread(ctx.star.backups.restore, key)
    if item is None:
        return R(err=f"没有找到「{key}」对应的备份，发送「备份列表」查看（名称需完整）")
    if item.get("error"):
        return R(err=f"恢复已中止：{item['error']}")
    # 恢复后的库可能来自同版本的另一份快照，重跑一次建表保证索引/表齐全
    await asyncio.to_thread(ctx.db.init)
    return R(
        tmpl="panel",
        data={
            "icon": "♻️",
            "title": "备份恢复完成",
            "accent": "#6fe08c",
            "blocks": [
                {"label": "恢复自", "value": item["name"]},
                {"label": "生效时间", "value": "立即生效，后续操作读写恢复后的数据"},
                {"label": "提醒", "value": "如需回到当前状态，请先创建一次新备份"},
            ],
        },
        text=f"已从备份 {item['name']} 恢复数据",
    )


async def backup_delete(ctx, event):
    key = _key(event.message_str, "删除备份")
    if not key:
        return R(err=_KEY_HINT.replace("恢复备份 1", "删除备份 1"))
    item = await asyncio.to_thread(ctx.star.backups.delete, key)
    if item is None:
        return R(err=f"没有找到「{key}」对应的备份（名称需完整，或使用序号）")
    remain = await asyncio.to_thread(ctx.star.backups.list)
    return R(
        tmpl="panel",
        data={
            "icon": "🗑️",
            "title": "备份已删除",
            "accent": "#ffd86f",
            "blocks": [
                {"label": "已删除", "value": item["name"]},
                {"label": "剩余备份", "value": f"{len(remain)} 个"},
            ],
        },
        text=f"已删除备份 {item['name']}",
    )


ROUTES = [
    Route(
        r"^[#]?(创建备份|数据备份|备份)(?:\s+\S+)?$",
        "cmd_backup_create",
        "管理员：创建全量数据备份",
        backup_create,
        admin=True,
    ),
    Route(
        r"^[#]?备份列表$",
        "cmd_backup_list",
        "管理员：查看所有备份",
        backup_list,
        admin=True,
    ),
    Route(
        r"^[#]?恢复备份(?:\s+\S+)?$",
        "cmd_backup_restore",
        "管理员：恢复指定备份（序号或完整名称）",
        backup_restore,
        admin=True,
    ),
    Route(
        r"^[#]?删除备份(?:\s+\S+)?$",
        "cmd_backup_delete",
        "管理员：删除指定备份（序号或完整名称）",
        backup_delete,
        admin=True,
    ),
]
