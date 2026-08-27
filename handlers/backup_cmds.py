"""备份管理指令路由（管理员）。"""

from ..core.result import R
from .base import Route


async def backup_create(ctx, event):
    label = ""
    import re

    m = re.search(r"备份\s*(\S+)", event.message_str or "")
    if m and m.group(1) not in ("创建", "备份"):
        label = m.group(1)
    info = await asyncio_backup(ctx, label)
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
                {"label": "恢复方式", "value": f"上班族恢复 {info['name'][:13]}"},
            ],
            "foot": "备份为 SQLite 在线快照，可在运行时安全创建",
        },
        text=f"备份成功：{info['name']}（{info['size'] // 1024} KB）",
    )


async def asyncio_backup(ctx, label):
    import asyncio

    return await asyncio.to_thread(ctx.star.backups.create, label)


async def backup_list(ctx, event):
    items = ctx.star.backups.list()
    if not items:
        return R(err="当前没有任何备份，发送「创建备份」生成第一个")
    rows = []
    for i, it in enumerate(items, 1):
        rows.append(
            {
                "cells": [
                    str(i),
                    it["name"],
                    f"{it['size'] // 1024} KB",
                    it["time"],
                ],
                "fail": False,
            }
        )
    return R(
        tmpl="table",
        data={
            "icon": "🗄️",
            "title": f"备份列表（{len(items)}）",
            "accent": "#7fd1ff",
            "summary": [{"label": "备份数量", "value": f"{len(items)} 个"}],
            "cols": ["序号", "备份名称", "大小", "创建时间"],
            "rows": rows,
            "note": "恢复/删除时可使用序号或名称关键字",
        },
        text="备份列表：" + "；".join(f"{it['name']}" for it in items),
    )


async def backup_restore(ctx, event):
    import re

    m = re.search(r"恢复备份\s*(\S+)", event.message_str or "")
    key = m.group(1) if m else ""
    item = await asyncio_restore(ctx, key)
    if item is None:
        return R(err=f"没有找到「{key}」对应的备份，发送「备份列表」查看")
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


async def asyncio_restore(ctx, key):
    import asyncio

    return await asyncio.to_thread(ctx.star.backups.restore, key)


async def backup_delete(ctx, event):
    import re

    m = re.search(r"删除备份\s*(\S+)", event.message_str or "")
    key = m.group(1) if m else ""
    item = await asyncio_delete(ctx, key)
    if item is None:
        return R(err=f"没有找到「{key}」对应的备份")
    return R(
        tmpl="panel",
        data={
            "icon": "🗑️",
            "title": "备份已删除",
            "accent": "#ffd86f",
            "blocks": [
                {"label": "已删除", "value": item["name"]},
                {"label": "剩余备份", "value": f"{len(ctx.star.backups.list())} 个"},
            ],
        },
        text=f"已删除备份 {item['name']}",
    )


async def asyncio_delete(ctx, key):
    import asyncio

    return await asyncio.to_thread(ctx.star.backups.delete, key)


ROUTES = [
    Route(
        r"^[#]?(创建备份|数据备份|备份)$",
        "cmd_backup_create",
        "管理员：创建全量数据备份",
        backup_create,
    ),
    Route(
        r"^[#]?(备份列表|备份额表)$",
        "cmd_backup_list",
        "管理员：查看所有备份",
        backup_list,
    ),
    Route(
        r"^[#]?恢复备份\s*\S+",
        "cmd_backup_restore",
        "管理员：恢复指定备份（序号或名称）",
        backup_restore,
    ),
    Route(
        r"^[#]?删除备份\s*\S+",
        "cmd_backup_delete",
        "管理员：删除指定备份",
        backup_delete,
    ),
]

