"""扩展玩法：年终奖、技能、职场社交、副业升级、年假、职场八卦。"""

import asyncio
import random
import time

from . import gamedata as gd
from . import logic
from .career import R, _cd_left, _cd_set, _clamp_status, _exempt, _load

SKILL_LIST = ["编程", "设计", "管理", "演讲", "外语"]
SKILL_COST = 800
SKILL_EXP = 15


def _skills(p):
    return p.get("_skills", [])


async def year_bonus(db, gid, uid, nickname, cfg):
    p = await _load(db, gid, uid, nickname, cfg)
    if int(p["company"]) == -1:
        return R(err="失业人士没有年终奖，先找工作吧")
    year = time.strftime("%Y")
    if p.get("year_bonus_year") == year:
        return R(err="今年的年终奖已经领过了，明年再战")
    lvl = int(p["lvl"])
    streak = int(p["attend_streak"])
    int(p["exp"])
    base = float(p["salary"]) * (1 + lvl * 0.3 + min(streak, 20) * 0.02)
    roll = random.random()
    if roll < 0.05:
        bonus = round(base * 3, 2)
        line = logic.pick(gd.t("extra", "yearbonus_ok"))
        title, accent, icon = "年终奖翻倍！！", "#ffd86f", "🎉"
    elif roll < 0.30:
        bonus = round(base * 1.5, 2)
        line = logic.pick(gd.t("extra", "yearbonus_ok"))
        title, accent, icon = "年终奖到账", "#6fe08c", "🧧"
    else:
        bonus = round(base * 0.3, 2)
        line = logic.pick(gd.t("extra", "yearbonus_bad"))
        title, accent, icon = "年终奖…就这？", "#fc6262", "😞"
    p["cash"] = round(float(p["cash"]) + bonus, 2)
    p["total_earned"] = round(float(p.get("total_earned") or 0) + bonus, 2)
    p["year_bonus_year"] = year
    await asyncio.to_thread(db.save_player, p)
    await asyncio.to_thread(
        db.add_transaction, gid, uid, "年终奖", bonus, f"职级{lvl} 出勤{streak}天"
    )
    await asyncio.to_thread(
        db.add_event,
        gid,
        uid,
        "年终奖",
        f"{p['nickname'] or uid} 领取年终奖 {logic.fmt_money(bonus)} 元",
    )
    return R(
        tmpl="panel",
        data={
            "icon": icon,
            "title": title,
            "accent": accent,
            "lines": [line],
            "blocks": [
                {"label": "年终奖", "value": f"+{logic.fmt_money(bonus)} 元"},
                {"label": "职级", "value": f"L{lvl}"},
                {"label": "连续出勤", "value": f"{streak} 天"},
                {"label": "现金余额", "value": f"{logic.fmt_money(p['cash'])} 元"},
            ],
            "foot": "每年限领一次，好好表现明年拿更多",
        },
        text=f"{title}！年终奖 +{logic.fmt_money(bonus)} 元。{line}",
    )


async def learn_skill(db, gid, uid, nickname, cfg, skill):
    p = await _load(db, gid, uid, nickname, cfg)
    skill = (skill or "").strip()
    if skill not in SKILL_LIST:
        return R(err=f"可学技能：{' / '.join(SKILL_LIST)}")
    skills = _skills(p)
    if skill in skills:
        return R(err=f"你已经学会了「{skill}」，不用重复学习")
    if float(p["cash"]) < SKILL_COST:
        return R(err=f"学费 {SKILL_COST} 元，余额不足")
    if not _exempt(cfg, uid) and _cd_left(p, "skill") > 0:
        return R(
            err=f"刚学完一门课，脑子装不下了：剩余 {logic.fmt_remaining(_cd_left(p, 'skill'))}"
        )
    _cd_set(p, "skill", 7 * 86400)
    p["cash"] = round(float(p["cash"]) - SKILL_COST, 2)
    p["exp"] = int(p["exp"]) + SKILL_EXP + logic.ri(0, 5)
    if random.random() < 0.75:
        skills.append(skill)
        p["_skills"] = skills
        line = logic.pick(gd.t("extra", "skill_learn_ok"))
        await asyncio.to_thread(db.save_player, p)
        await asyncio.to_thread(
            db.add_transaction, gid, uid, "技能学费", -SKILL_COST, skill
        )
        return R(
            tmpl="panel",
            data={
                "icon": "🎓",
                "title": f"学会「{skill}」！",
                "accent": "#6fe08c",
                "lines": [line],
                "blocks": [
                    {"label": "学费", "value": f"-{SKILL_COST} 元"},
                    {"label": "已掌握技能", "value": "、".join(skills) or "无"},
                    {"label": "经验", "value": f"+{SKILL_EXP}+（当前 {p['exp']}）"},
                ],
                "foot": "技能越多，加班收益和晋升成功率越高",
            },
            text=f"学会「{skill}」！{line}",
        )
    p["exp"] = int(p["exp"]) + logic.ri(1, 3)
    line = logic.pick(gd.t("extra", "skill_learn_fail"))
    await asyncio.to_thread(db.save_player, p)
    return R(
        tmpl="panel",
        data={
            "icon": "📉",
            "title": "学习失败",
            "accent": "#fc6262",
            "lines": [line],
            "blocks": [{"label": "学费", "value": f"-{SKILL_COST} 元（打水漂）"}],
        },
        text=f"学习失败：{line}",
    )


async def my_skills(db, gid, uid, nickname):
    p = await asyncio.to_thread(db.get_player, gid, uid, nickname)
    skills = _skills(p)
    all_sk = "、".join(SKILL_LIST)
    owned = "、".join(skills) if skills else "暂无"
    return R(
        tmpl="panel",
        data={
            "icon": "🎯",
            "title": "我的技能",
            "accent": "#7fd1ff",
            "blocks": [
                {"label": "已掌握", "value": owned},
                {"label": "可学技能", "value": all_sk},
                {"label": "学费", "value": f"{SKILL_COST} 元/门"},
                {"label": "冷却", "value": "7 天"},
            ],
            "foot": "技能越多，加班收益和晋升成功率越高",
        },
        text=f"已掌握技能：{owned}｜可学：{all_sk}",
    )


async def social_network(db, gid, me, target, nickname, cfg, target_name=""):
    p = await _load(db, gid, me, nickname, cfg)
    td = await _load(db, gid, target, target_name, cfg)
    if str(target) == str(me):
        return R(err="和自己社交？先学会和自己相处吧")
    if not _exempt(cfg, me) and _cd_left(p, "social") > 0:
        return R(
            err=f"社交频率太高会显得刻意：剩余 {logic.fmt_remaining(_cd_left(p, 'social'))}"
        )
    _cd_set(p, "social", 4 * 3600)
    cost = 20
    if float(p["cash"]) < cost:
        return R(err=f"请喝奶茶要 {cost} 元，余额不足")
    p["cash"] = round(float(p["cash"]) - cost, 2)
    tname = td.get("card") or td["nickname"] or target_name or f"用户{target}"
    if random.random() < 0.65:
        gain = logic.ri(3, 8)
        p["social_pts"] = int(p.get("social_pts") or 0) + gain
        p["mind"] = round(float(p["mind"]) + 5, 1)
        td["cash"] = round(float(td["cash"]) + 10, 2)
        line = logic.pick(gd.t("extra", "social_ok"))
        await asyncio.to_thread(db.save_player, p)
        await asyncio.to_thread(db.save_player, td)
        await asyncio.to_thread(
            db.add_event,
            gid,
            me,
            "社交",
            f"{p['nickname'] or me} 和 {tname} 搞好了关系（人脉+{gain}）",
        )
        return R(
            tmpl="panel",
            data={
                "icon": "🤝",
                "title": "社交成功",
                "accent": "#6fe08c",
                "lines": [line],
                "blocks": [
                    {"label": "奶茶钱", "value": f"-{cost} 元（TA也赚了10）"},
                    {"label": "人脉值", "value": f"+{gain}（当前 {p['social_pts']}）"},
                    {"label": "精神", "value": f"+5（当前 {p['mind']}）"},
                ],
                "foot": "人脉值越高，职场社交事件触发率越高",
            },
            text=f"和 {tname} 社交成功！人脉 +{gain}",
        )
    p["mind"] = round(max(0, float(p["mind"]) - 3), 1)
    line = logic.pick(gd.t("extra", "social_fail"))
    await asyncio.to_thread(db.save_player, p)
    return R(
        tmpl="panel",
        data={
            "icon": "😅",
            "title": "社交翻车",
            "accent": "#fc6262",
            "lines": [line],
            "blocks": [{"label": "精神", "value": f"-3（当前 {p['mind']}）"}],
        },
        text=f"社交翻车：{line}",
    )


async def side_hustle_upgrade(db, gid, uid, nickname, cfg):
    p = await _load(db, gid, uid, nickname, cfg)
    lvl = int(p.get("side_lvl") or 1)
    if lvl >= 5:
        return R(err="副业已经满级了（工作室级别），不能再升了")
    cost = lvl * 2000
    if float(p["cash"]) < cost:
        return R(
            err=f"升级副业需要 {logic.fmt_money(cost)} 元（当前 Lv.{lvl}→Lv.{lvl + 1}），余额不足"
        )
    p["cash"] = round(float(p["cash"]) - cost, 2)
    p["side_lvl"] = lvl + 1
    await asyncio.to_thread(db.save_player, p)
    names = ["", "地摊小贩", "网店店主", "自由职业者", "小工作室", "副业大亨"]
    line = logic.pick(gd.t("extra", "side_hustle_up"))
    return R(
        tmpl="panel",
        data={
            "icon": "💼",
            "title": f"副业升级 → Lv.{lvl + 1} {names[min(lvl + 1, 5)]}",
            "accent": "#ffd86f",
            "lines": [line],
            "blocks": [
                {"label": "升级费用", "value": f"-{logic.fmt_money(cost)} 元"},
                {
                    "label": "当前等级",
                    "value": f"Lv.{lvl + 1} {names[min(lvl + 1, 5)]}",
                },
                {"label": "摆摊收益加成", "value": f"+{(lvl + 1 - 1) * 20}%"},
            ],
        },
        text=f"副业升级到 Lv.{lvl + 1}！摆摊收益将提升",
    )


async def annual_leave(db, gid, uid, nickname, cfg):
    p = await _load(db, gid, uid, nickname, cfg)
    if int(p["company"]) == -1:
        return R(err="失业人士没有年假一说")
    days = int(p.get("annual_leave") or 0)
    if days <= 0:
        return R(err="今年的年假已经用完了，明年职级越高年假越多")
    p["annual_leave"] = days - 1
    p["mind"] = round(min(100, float(p["mind"]) + 25), 1)
    p["health"] = round(min(100, float(p["health"]) + 15), 1)
    p["attend_streak"] = 0
    _clamp_status(p)
    await asyncio.to_thread(db.save_player, p)
    line = logic.pick(gd.t("extra", "annual_leave"))
    return R(
        tmpl="panel",
        data={
            "icon": "🏖️",
            "title": "年假开始！",
            "accent": "#6fe08c",
            "lines": [line],
            "blocks": [
                {"label": "剩余年假", "value": f"{days - 1} 天"},
                {"label": "精神", "value": f"+25（当前 {p['mind']}）"},
                {"label": "健康", "value": f"+15（当前 {p['health']}）"},
                {"label": "注意", "value": "年假会中断连续出勤"},
            ],
        },
        text=f"年假开始！剩余 {days - 1} 天。{line}",
    )


async def gossip(db, gid, uid, nickname):
    all_players = await asyncio.to_thread(db.all_players, gid)
    if len(all_players) < 2:
        return R(err="群里的打工人太少了，八卦都编不出来")
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
            "foot": "八卦仅供娱乐，请勿当真（但你可以信一半）",
        },
        text=f"☕ {gossip}",
    )
