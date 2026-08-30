"""扩展玩法第二批：年会抽奖、借钱、职场建议、工位升级、加班餐、年度体检。"""

import asyncio
import random
import time

from . import gamedata as gd
from . import logic
from .result import R


async def party_lottery(db, gid, uid, nickname, cfg):
    p = await logic.load_player(db, gid, uid, nickname, cfg)
    if int(p["company"]) == -1:
        return R(err="失业人士连年会邀请函都收不到")
    year = time.strftime("%Y")
    if p.get("party_year") == year:
        return R(err="今年的年会抽奖已经参加过了，明年再来")
    p["party_year"] = year

    prizes = gd.t("extra2", "party_prizes")
    # 四档中奖概率（累积），其余为「谢谢参与」。分桶阈值随奖品表走，不额外开放。
    rates = [
        float(logic.cfg_get(cfg, "party_grand_rate", 0.03)),
        float(logic.cfg_get(cfg, "party_first_rate", 0.07)),
        float(logic.cfg_get(cfg, "party_second_rate", 0.15)),
        float(logic.cfg_get(cfg, "party_third_rate", 0.25)),
    ]
    buckets = [
        [x for x in prizes if x["amount"] >= 8000],
        [x for x in prizes if 2000 <= x["amount"] < 8000],
        [x for x in prizes if 100 <= x["amount"] < 2000],
        [x for x in prizes if 0 < x["amount"] < 100],
    ]
    empty = [x for x in prizes if x["amount"] == 0]
    roll, accum, prize = random.random(), 0.0, None
    for rate, bucket in zip(rates, buckets, strict=True):
        accum += rate
        if roll < accum and bucket:
            prize = random.choice(bucket)
            break
    if prize is None:
        prize = random.choice(empty or prizes)

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
    if str(target) == str(me):
        return R(err="不能借钱给自己")
    amt = logic.parse_int(amount, lo=1)
    if amt is None:
        return R(err="请输入正确的借款金额，例如「借钱 @群友 500」")
    p = await logic.load_player(db, gid, me, "", cfg)
    # 借款对象必须已入档：load_player 会给陌生 ID 顺手建号
    td = await asyncio.to_thread(db.find_player_any, gid, str(target))
    if not td:
        return R(err="对方还没有加入游戏（让 TA 先发一次「上班」），借不了")
    target = td["uid"]
    if str(target) == str(me):
        return R(err="不能借钱给自己")
    tname = td.get("card") or td["nickname"] or target_name or f"用户{target}"
    if float(p["cash"]) < amt:
        return R(
            err=f"你只有 {logic.fmt_money(p['cash'])} 元，借不了 {logic.fmt_money(amt)} 元"
        )
    if random.random() < float(logic.cfg_get(cfg, "lend_fail_rate", 0.3)):
        if not await asyncio.to_thread(db.try_debit_cash, gid, me, float(amt)):
            return R(err="现金不足，借款失败")
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
    ok, _reason = await asyncio.to_thread(db.transfer_cash, gid, me, target, float(amt))
    if not ok:
        return R(err="现金不足或对方未加入游戏，借款失败")
    p = await asyncio.to_thread(db.get_player, gid, me)
    td = await asyncio.to_thread(db.get_player, gid, target)
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


async def career_advice(ctx_db=None):
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
    p = await logic.load_player(db, gid, uid, nickname, cfg)
    cur_lv = int(p.get("workstation") or 0)
    ws_list = gd.workstations()
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
    p = await logic.load_player(db, gid, uid, nickname, cfg)
    if int(p["company"]) == -1:
        return R(err="失业人士没有加班餐")
    now = int(time.time())
    hour = time.localtime(now).tm_hour
    start_hour = int(logic.cfg_get(cfg, "overtime_meal_start_hour", 18))
    if hour < start_hour:
        return R(err=f"现在还没到加班时间（{start_hour} 点后可领），正常吃饭去")
    if not logic.is_exempt(cfg, uid) and logic.cd_left(p, "ot_meal") > 0:
        return R(
            err=f"加班餐一天只能领一次：剩余 {logic.fmt_remaining(logic.cd_left(p, 'ot_meal'))}"
        )
    logic.cd_set(
        p, "ot_meal", float(logic.cfg_get(cfg, "overtime_meal_cooldown_hours", 24)) * 3600
    )
    line = logic.pick(gd.t("extra2", "ot_meal"))
    subsidy = min(
        float(logic.cfg_get(cfg, "overtime_meal_subsidy_max", 30.0)),
        float(p["salary"]) / (logic.workdays(cfg) * 10),
    )
    subsidy = round(subsidy, 2)
    p["cash"] = round(float(p["cash"]) + subsidy, 2)
    p["mind"] = round(float(p["mind"]) + 3, 1)
    logic.clamp_status(p)
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
    p = await logic.load_player(db, gid, uid, nickname, cfg)
    year = time.strftime("%Y")
    if p.get("checkup_year") == year:
        return R(err="今年的年度体检已经做过了")
    cost = float(logic.cfg_get(cfg, "checkup_cost", 200.0))
    if float(p["cash"]) < cost:
        return R(err=f"体检需要 {logic.fmt_money(cost)} 元，余额不足")
    # 余额够才标记本年已检：否则钱不够会被白锁一年
    p["checkup_year"] = year
    p["cash"] = round(max(0.0, float(p["cash"]) - cost), 2)
    if random.random() < float(logic.cfg_get(cfg, "checkup_ok_rate", 0.55)):
        line = logic.pick(gd.t("extra2", "checkup_ok"))
        p["health"] = round(min(100, float(p["health"]) + 5), 1)
        icon, accent, title = "✅", "#6fe08c", "体检结果良好"
    else:
        line = logic.pick(gd.t("extra2", "checkup_bad"))
        p["health"] = round(max(10, float(p["health"]) - 8), 1)
        icon, accent, title = "🏥", "#fc6262", "体检结果堪忧"
    logic.clamp_status(p)
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
