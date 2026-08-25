"""扩展玩法第二批：年会抽奖、借钱、职场建议、工位升级、加班餐、年度体检。"""

import asyncio
import random
import time

from . import gamedata as gd
from . import logic
from .career import R, _cd_left, _cd_set, _clamp_status, _exempt, _load


def _ws_data():
    return gd.load_all().get("workstations", {}).get("workstations", [])


async def party_lottery(db, gid, uid, nickname, cfg):
    p = await _load(db, gid, uid, nickname, cfg)
    if int(p["company"]) == -1:
        return R(err="失业人士连年会邀请函都收不到")
    year = time.strftime("%Y")
    if p.get("party_year") == year:
        return R(err="今年的年会抽奖已经参加过了，明年再来")
    p["party_year"] = year

    prizes = gd.t("extra2", "party_prizes")
    roll = random.random()
    if roll < 0.03:
        prize = random.choice([x for x in prizes if x["amount"] >= 8000])
    elif roll < 0.10:
        prize = random.choice([x for x in prizes if 2000 <= x["amount"] < 8000])
    elif roll < 0.25:
        prize = random.choice([x for x in prizes if 100 <= x["amount"] < 2000])
    elif roll < 0.50:
        prize = random.choice([x for x in prizes if 0 < x["amount"] < 100])
    else:
        prize = random.choice([x for x in prizes if x["amount"] == 0])

    amount = int(prize.get("amount", 0))
    if amount > 0:
        p["cash"] = round(float(p["cash"]) + amount, 2)
        p["total_earned"] = round(float(p.get("total_earned") or 0) + amount, 2)
    await asyncio.to_thread(db.save_player, p)
    await asyncio.to_thread(
        db.add_event,
        gid,
        uid,
        "年会抽奖",
        f"{p['nickname'] or uid} 年会抽中{prize['rank']}：{prize['text'][:30]}",
    )
    return R(
        tmpl="panel",
        data={
            "icon": "🎊",
            "title": f"年会抽奖 · {prize['rank']}",
            "accent": "#ffd86f" if amount > 100 else "#7fd1ff",
            "lines": [prize["text"]],
            "blocks": [
                {
                    "label": "奖品价值",
                    "value": f"{logic.fmt_money(amount)} 元" if amount else "0 元",
                },
                {"label": "现金余额", "value": f"{logic.fmt_money(p['cash'])} 元"},
            ],
            "foot": "年会每年一次，奖品随机",
        },
        text=f"年会抽奖[{prize['rank']}]：{prize['text']}（{logic.fmt_money(amount)} 元）",
    )


async def lend_money(db, gid, me, target, amount, cfg, target_name=""):
    p = await _load(db, gid, me, "", cfg)
    td = await _load(db, gid, target, target_name, cfg)
    amt = int(amount) if str(amount).isdigit() else 0
    if amt <= 0:
        return R(err="请输入正确的借款金额")
    if str(target) == str(me):
        return R(err="不能借钱给自己")
    tname = td.get("card") or td["nickname"] or target_name or f"用户{target}"
    if float(p["cash"]) < amt:
        return R(
            err=f"你只有 {logic.fmt_money(p['cash'])} 元，借不了 {logic.fmt_money(amt)} 元"
        )
    if random.random() < 0.30:
        p["cash"] = round(float(p["cash"]) - amt, 2)
        await asyncio.to_thread(db.save_player, p)
        await asyncio.to_thread(
            db.add_transaction, gid, me, "借钱(未还)", -amt, f"借给{tname}"
        )
        line = logic.pick(gd.t("extra2", "lend_fail"))
        return R(
            tmpl="panel",
            data={
                "icon": "💸",
                "title": "借钱有去无回",
                "accent": "#fc6262",
                "lines": [line],
                "blocks": [{"label": "损失", "value": f"-{logic.fmt_money(amt)} 元"}],
            },
            text=f"借钱给 {tname} 失败：{line}（损失 {logic.fmt_money(amt)} 元）",
        )
    p["cash"] = round(float(p["cash"]) - amt, 2)
    td["cash"] = round(float(td["cash"]) + amt, 2)
    await asyncio.to_thread(db.save_player, p)
    await asyncio.to_thread(db.save_player, td)
    await asyncio.to_thread(
        db.add_transaction, gid, me, "借钱(出)", -amt, f"借给{tname}"
    )
    await asyncio.to_thread(
        db.add_transaction, gid, target, "借钱(入)", amt, f"来自{p['nickname'] or me}"
    )
    line = logic.pick(gd.t("extra2", "lend_ok"))
    return R(
        tmpl="panel",
        data={
            "icon": "🤝",
            "title": "借钱成功",
            "accent": "#6fe08c",
            "lines": [line],
            "blocks": [
                {"label": "借款金额", "value": f"{logic.fmt_money(amt)} 元"},
                {"label": "你的现金", "value": f"{logic.fmt_money(p['cash'])} 元"},
                {"label": "对方现金", "value": f"{logic.fmt_money(td['cash'])} 元"},
            ],
            "foot": "借出去的钱能不能收回来，看人品",
        },
        text=f"借钱给 {tname} 成功！{logic.fmt_money(amt)} 元已转账",
    )


async def career_advice(ctx_db):
    advices = gd.t("extra2", "career_advice")
    tip = logic.pick(advices)
    return R(
        tmpl="panel",
        data={
            "icon": "💡",
            "title": "职场生存建议",
            "accent": "#b48cff",
            "lines": [tip],
            "foot": "建议仅供参考，请结合自身情况使用",
        },
        text=f"💡 职场建议：{tip}",
    )


async def upgrade_workstation(db, gid, uid, nickname, cfg):
    p = await _load(db, gid, uid, nickname, cfg)
    cur_lv = int(p.get("workstation") or 0)
    ws_list = _ws_data()
    if cur_lv >= len(ws_list) - 1:
        return R(err="你的工位已经是顶级配置了，全公司最靓的仔")
    nxt = ws_list[cur_lv + 1]
    cost = float(nxt["cost"])
    if float(p["cash"]) < cost:
        return R(
            err=f"升级到「{nxt['name']}」需要 {logic.fmt_money(cost)} 元，余额不足"
        )
    p["cash"] = round(float(p["cash"]) - cost, 2)
    p["workstation"] = cur_lv + 1
    await asyncio.to_thread(db.save_player, p)
    await asyncio.to_thread(
        db.add_transaction, gid, uid, "工位升级", -cost, nxt["name"]
    )
    return R(
        tmpl="panel",
        data={
            "icon": "🖥️",
            "title": f"工位升级 → {nxt['name']}",
            "accent": "#7fd1ff",
            "lines": [nxt["desc"]],
            "blocks": [
                {"label": "升级费用", "value": f"-{logic.fmt_money(cost)} 元"},
                {"label": "摸鱼舒适度", "value": f"+{nxt['bonus']}"},
                {"label": "现金余额", "value": f"{logic.fmt_money(p['cash'])} 元"},
            ],
        },
        text=f"工位升级到「{nxt['name']}」！{nxt['desc']}",
    )


async def overtime_meal(db, gid, uid, nickname, cfg):
    p = await _load(db, gid, uid, nickname, cfg)
    if int(p["company"]) == -1:
        return R(err="失业人士没有加班餐")
    now = int(time.time())
    hour = time.localtime(now).tm_hour
    if hour < 18:
        return R(err="现在还没到加班时间，正常吃饭去")
    if not _exempt(cfg, uid) and _cd_left(p, "ot_meal") > 0:
        return R(
            err=f"加班餐一天只能领一次：剩余 {logic.fmt_remaining(_cd_left(p, 'ot_meal'))}"
        )
    _cd_set(p, "ot_meal", 86400)
    line = logic.pick(gd.t("extra2", "ot_meal"))
    subsidy = min(30, int(float(p["salary"]) / 220))
    p["cash"] = round(float(p["cash"]) + subsidy, 2)
    p["mind"] = round(float(p["mind"]) + 3, 1)
    _clamp_status(p)
    await asyncio.to_thread(db.save_player, p)
    await asyncio.to_thread(
        db.add_transaction, gid, uid, "加班餐补", subsidy, "加班餐补贴"
    )
    return R(
        tmpl="panel",
        data={
            "icon": "🍱",
            "title": "加班餐补贴",
            "accent": "#ffd86f",
            "lines": [line],
            "blocks": [
                {"label": "餐补", "value": f"+{logic.fmt_money(subsidy)} 元"},
                {"label": "精神", "value": f"+3（当前 {p['mind']}）"},
            ],
        },
        text=f"加班餐补贴 +{logic.fmt_money(subsidy)} 元：{line}",
    )


async def health_checkup(db, gid, uid, nickname, cfg):
    p = await _load(db, gid, uid, nickname, cfg)
    year = time.strftime("%Y")
    if p.get("checkup_year") == year:
        return R(err="今年的年度体检已经做过了")
    p["checkup_year"] = year
    cost = 200
    if float(p["cash"]) < cost:
        return R(err=f"体检需要 {cost} 元，余额不足")
    p["cash"] = round(float(p["cash"]) - cost, 2)
    if random.random() < 0.55:
        line = logic.pick(gd.t("extra2", "checkup_ok"))
        p["health"] = round(min(100, float(p["health"]) + 5), 1)
        icon, accent, title = "✅", "#6fe08c", "体检结果良好"
    else:
        line = logic.pick(gd.t("extra2", "checkup_bad"))
        p["health"] = round(max(10, float(p["health"]) - 8), 1)
        icon, accent, title = "🏥", "#fc6262", "体检结果堪忧"
    _clamp_status(p)
    await asyncio.to_thread(db.save_player, p)
    await asyncio.to_thread(db.add_transaction, gid, uid, "年度体检", -cost, title)
    return R(
        tmpl="panel",
        data={
            "icon": icon,
            "title": title,
            "accent": accent,
            "lines": [line],
            "blocks": [
                {"label": "体检费", "value": f"-{cost} 元"},
                {"label": "健康", "value": f"{p['health']} / 100"},
            ],
        },
        text=f"{title}：{line}",
    )
