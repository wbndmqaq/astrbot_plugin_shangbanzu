"""扩展玩法第三批：开会、帮带饭、回消息、抢会议室、和同事吃饭、帮领导做事、
行业峰会、养宠物、考证书、旅游。"""

import asyncio
import random
import time

from . import gamedata as gd
from . import logic
from .career import R, _cd_left, _cd_set, _clamp_status, _exempt, _load

GID = "该功能只能在群聊中使用"


def _today():
    return time.strftime("%Y-%m-%d")


async def meeting(ctx_db, gid, uid, nickname, cfg):
    p = await _load(ctx_db, gid, uid, nickname, cfg)
    if int(p["company"]) == -1:
        return R(err="失业人士不需要开会")
    today = _today()
    if p.get("meeting_day") == today:
        return R(err="今天已经开过会了")
    p["meeting_day"] = today
    ev = logic.pick(gd.t("extra3", "meeting"))
    p["mind"] = float(p["mind"]) + ev.get("mind", 0)
    p["exp"] = int(p["exp"]) + ev.get("exp", 0)
    _clamp_status(p)
    await asyncio.to_thread(ctx_db.save_player, p)
    return R(
        tmpl="panel",
        data={
            "icon": "📋",
            "title": "开会",
            "accent": "#7fd1ff",
            "lines": [ev["text"]],
            "blocks": [
                {
                    "label": "精神",
                    "value": f"{ev.get('mind', 0):+g}（当前 {p['mind']}）",
                },
                {"label": "经验", "value": f"+{ev.get('exp', 0)}（当前 {p['exp']}）"},
            ],
        },
        text=f"开会：{ev['text']}",
    )


async def bring_food(ctx_db, gid, uid, me, target, nickname, cfg, target_name=""):
    cost = 15
    p = await _load(ctx_db, gid, uid, nickname, cfg)
    if float(p["cash"]) < cost:
        return R(err=f"带饭要 {cost} 元，余额不足")
    td = await _load(ctx_db, gid, target, target_name, cfg)
    p["cash"] = round(float(p["cash"]) - cost, 2)
    p["social_pts"] = int(p.get("social_pts") or 0) + 2
    td["mind"] = round(float(td["mind"]) + 5, 1)
    await asyncio.to_thread(ctx_db.save_player, p)
    await asyncio.to_thread(ctx_db.save_player, td)
    tname = td.get("card") or td["nickname"] or target_name or f"用户{target}"
    return R(
        tmpl="panel",
        data={
            "icon": "🍱",
            "title": "帮带饭成功",
            "accent": "#6fe08c",
            "lines": [f"你帮 {tname} 带了份午饭，TA很感动"],
            "blocks": [
                {"label": "花费", "value": f"-{cost} 元"},
                {"label": "人脉值", "value": f"+2（当前 {p['social_pts']}）"},
                {"label": f"{tname} 精神", "value": "+5"},
            ],
        },
        text=f"帮 {tname} 带饭成功！人脉 +2",
    )


async def reply_msg(ctx_db, gid, uid, nickname, cfg):
    p = await _load(ctx_db, gid, uid, nickname, cfg)
    if int(p["company"]) == -1:
        return R(err="失业人士没有工作消息要回")
    today = _today()
    if p.get("reply_day") == today:
        return R(err="今天已经回过工作消息了，让手指休息一下吧")
    p["reply_day"] = today
    gain = logic.ri(2, 5)
    p["exp"] = int(p["exp"]) + gain
    p["mind"] = round(max(0, float(p["mind"]) - 3), 1)
    _clamp_status(p)
    await asyncio.to_thread(ctx_db.save_player, p)
    return R(
        tmpl="panel",
        data={
            "icon": "📱",
            "title": "回复工作消息",
            "accent": "#7fd1ff",
            "lines": ["你花了半小时认真回复了堆积的工作消息"],
            "blocks": [
                {"label": "经验", "value": f"+{gain}（当前 {p['exp']}）"},
                {"label": "精神", "value": f"-3（当前 {p['mind']}）"},
            ],
        },
        text=f"回复工作消息完成！经验 +{gain}",
    )


async def meeting_room(ctx_db, gid, uid, nickname, cfg):
    p = await _load(ctx_db, gid, uid, nickname, cfg)
    if int(p["company"]) == -1:
        return R(err="失业人士不需要抢会议室")
    today = _today()
    if p.get("room_day") == today:
        return R(err="今天已经抢过会议室了")
    p["room_day"] = today
    ev = random.choice(
        [
            {"text": "你成功抢到了带大屏幕的会议室！", "exp": 3, "mind": 3},
            {"text": "你抢到了会议室但发现投影仪坏了", "exp": 1, "mind": -2},
            {"text": "你没抢到会议室，只能在工位上开电话会", "exp": 0, "mind": -3},
        ]
    )
    p["exp"] = int(p["exp"]) + ev["exp"]
    p["mind"] = round(float(p["mind"]) + ev["mind"], 1)
    _clamp_status(p)
    await asyncio.to_thread(ctx_db.save_player, p)
    return R(
        tmpl="panel",
        data={
            "icon": "🏢",
            "title": "抢会议室",
            "accent": "#7fd1ff",
            "lines": [ev["text"]],
            "blocks": [
                {"label": "经验", "value": f"+{ev['exp']}"},
                {"label": "精神", "value": f"{ev['mind']:+g}"},
            ],
        },
        text=f"抢会议室：{ev['text']}",
    )


async def eat_with(ctx_db, gid, uid, me, target, nickname, cfg, target_name=""):
    cost = random.choice([50, 80, 120])
    p = await _load(ctx_db, gid, uid, nickname, cfg)
    td = await _load(ctx_db, gid, target, target_name, cfg)
    if float(p["cash"]) < cost:
        return R(err=f"吃饭预计 {cost} 元，余额不足")
    p["cash"] = round(float(p["cash"]) - cost, 2)
    p["mind"] = round(float(p["mind"]) + 10, 1)
    p["social_pts"] = int(p.get("social_pts") or 0) + 3
    td["mind"] = round(float(td["mind"]) + 8, 1)
    _clamp_status(p)
    await asyncio.to_thread(ctx_db.save_player, p)
    await asyncio.to_thread(ctx_db.save_player, td)
    tname = td.get("card") or td["nickname"] or target_name or f"用户{target}"
    return R(
        tmpl="panel",
        data={
            "icon": "🍜",
            "title": "和同事吃饭",
            "accent": "#6fe08c",
            "lines": [f"你和 {tname} 吃了顿饭，从项目聊到了人生"],
            "blocks": [
                {"label": "花费", "value": f"-{cost} 元"},
                {"label": "你的精神", "value": f"+10（当前 {p['mind']}）"},
                {"label": f"{tname} 精神", "value": "+8"},
                {"label": "人脉值", "value": f"+3（当前 {p['social_pts']}）"},
            ],
        },
        text=f"和 {tname} 吃饭，花费 {cost} 元，双方精神都恢复了",
    )


async def boss_task(ctx_db, gid, uid, nickname, cfg):
    p = await _load(ctx_db, gid, uid, nickname, cfg)
    if int(p["company"]) == -1:
        return R(err="失业人士没有领导可以使唤...啊不，可以服务")
    if not _exempt(cfg, uid) and _cd_left(p, "boss_task") > 0:
        return R(
            err=f"刚帮领导做完一件事：剩余 {logic.fmt_remaining(_cd_left(p, 'boss_task'))}"
        )
    _cd_set(p, "boss_task", 12 * 3600)
    if random.random() < 0.65:
        reward = logic.ri(50, 200)
        p["cash"] = round(float(p["cash"]) + reward, 2)
        p["exp"] = int(p["exp"]) + logic.ri(3, 8)
        await asyncio.to_thread(db_save(ctx_db, gid, uid, p))
        line = logic.pick(gd.t("extra3", "boss_task_ok"))
        return R(
            tmpl="panel",
            data={
                "icon": "👔",
                "title": "帮领导做事",
                "accent": "#6fe08c",
                "lines": [line],
                "blocks": [
                    {"label": "奖励", "value": f"+{logic.fmt_money(reward)} 元"}
                ],
            },
            text=f"帮领导做事成功！奖励 {logic.fmt_money(reward)} 元：{line}",
        )
    cost = logic.ri(30, 100)
    p["cash"] = round(max(0, float(p["cash"]) - cost), 2)
    p["mind"] = round(float(p["mind"]) - 5, 1)
    await asyncio.to_thread(db_save(ctx_db, gid, uid, p))
    line = logic.pick(gd.t("extra3", "boss_task_fail"))
    return R(
        tmpl="panel",
        data={
            "icon": "😅",
            "title": "帮领导做事搞砸了",
            "accent": "#fc6262",
            "lines": [line],
            "blocks": [{"label": "损失", "value": f"-{cost} 元"}],
        },
        text=f"帮领导做事搞砸了：{line}（损失 {cost} 元）",
    )


def db_save(db, gid, uid, p):

    return db.save_player(p)


async def summit(ctx_db, gid, uid, nickname, cfg):
    p = await _load(ctx_db, gid, uid, nickname, cfg)
    cost = 500
    if float(p["cash"]) < cost:
        return R(err=f"行业峰会门票 {cost} 元，余额不足")
    if not _exempt(cfg, uid) and _cd_left(p, "summit") > 0:
        return R(
            err=f"峰会太频繁也没用：剩余 {logic.fmt_remaining(_cd_left(p, 'summit'))}"
        )
    _cd_set(p, "summit", 14 * 86400)
    p["cash"] = round(float(p["cash"]) - cost, 2)
    exp_gain = logic.ri(10, 25)
    social_gain = logic.ri(3, 8)
    p["exp"] = int(p["exp"]) + exp_gain
    p["social_pts"] = int(p.get("social_pts") or 0) + social_gain
    p["mind"] = round(float(p["mind"]) + 5, 1)
    await asyncio.to_thread(ctx_db.save_player, p)
    line = logic.pick(gd.t("extra3", "summit"))
    return R(
        tmpl="panel",
        data={
            "icon": "🎤",
            "title": "行业峰会",
            "accent": "#b48cff",
            "lines": [line],
            "blocks": [
                {"label": "门票", "value": f"-{cost} 元"},
                {"label": "经验", "value": f"+{exp_gain}（当前 {p['exp']}）"},
                {
                    "label": "人脉值",
                    "value": f"+{social_gain}（当前 {p['social_pts']}）",
                },
            ],
        },
        text=f"行业峰会收获满满！经验 +{exp_gain}，人脉 +{social_gain}",
    )


async def adopt_pet(ctx_db, gid, uid, nickname, pet_type, cfg):
    p = await _load(ctx_db, gid, uid, nickname, cfg)
    if p.get("_pet"):
        return R(err=f"你已经有宠物了（{p['_pet']}），一心不能二用")
    pets = gd.load_all().get("pets", {}).get("pets", [])
    pet = next((x for x in pets if x["type"] == pet_type), None)
    if not pet:
        return R(err=f"可以养：{' / '.join(x['type'] for x in pets)}")
    cost = float(pet["cost"])
    if float(p["cash"]) < cost:
        return R(
            err=f"养{pet_type}需要 {logic.fmt_money(cost)} 元（含 initial 费用），余额不足"
        )
    p["cash"] = round(float(p["cash"]) - cost, 2)
    p["_pet"] = pet_type
    await asyncio.to_thread(ctx_db.save_player, p)
    return R(
        tmpl="panel",
        data={
            "icon": "🐱" if pet_type == "猫" else "🐶",
            "title": f"领养了{pet_type}！",
            "accent": "#6fe08c",
            "lines": [pet["desc"]],
            "blocks": [
                {"label": "费用", "value": f"-{logic.fmt_money(cost)} 元"},
                {"label": "精神恢复加成", "value": f"+{pet.get('mind_bonus', 0)}"},
                {"label": "发送「撸猫」或「遛狗」", "value": "每天互动一次"},
            ],
        },
        text=f"领养了{pet_type}！花费 {logic.fmt_money(cost)} 元。{pet['desc']}",
    )


async def pet_interact(ctx_db, gid, uid, nickname):
    p = await asyncio.to_thread(ctx_db.get_player, gid, uid, nickname)
    pet = p.get("_pet")
    if not pet:
        return R(err="你还没有宠物，去宠物店领养一只吧")
    today = _today()
    if p.get("pet_day") == today:
        return R(err="今天已经陪过宠物了，明天再来")
    p["pet_day"] = today
    ev = logic.pick(gd.t("extra3", "pet_interact"))
    p["mind"] = round(float(p["mind"]) + ev.get("mind", 5), 1)
    if ev.get("health"):
        p["health"] = round(float(p["health"]) + ev["health"], 1)
    _clamp_status(p)
    await asyncio.to_thread(ctx_db.save_player, p)
    return R(
        tmpl="panel",
        data={
            "icon": "🐱" if pet == "猫" else "🐶",
            "title": f"和{pet}互动",
            "accent": "#6fe08c",
            "lines": [ev["text"]],
            "blocks": [
                {
                    "label": "精神",
                    "value": f"{ev.get('mind', 5):+g}（当前 {p['mind']}）",
                }
            ],
        },
        text=f"和{pet}互动：{ev['text']}",
    )


async def get_cert(ctx_db, gid, uid, nickname, cert_name, cfg):
    p = await _load(ctx_db, gid, uid, nickname, cfg)
    cert_name = (cert_name or "").strip()
    certs = {"PMP": 3000, "CPA": 5000, "法考": 4000, "CFA": 6000}
    if cert_name not in certs:
        return R(err=f"可考证书：{' / '.join(certs)}")
    cost = certs[cert_name]
    if float(p["cash"]) < cost:
        return R(
            err=f"考{cert_name}需要 {logic.fmt_money(cost)} 元（报名+教材+培训），余额不足"
        )
    skills = p.get("_skills", [])
    if cert_name in skills:
        return R(err=f"你已经考过了{cert_name}")
    p["cash"] = round(float(p["cash"]) - cost, 2)
    if random.random() < 0.55:
        skills.append(cert_name)
        p["_skills"] = skills
        p["exp"] = int(p["exp"]) + 30
        p["value"] = round(float(p["value"]) * 1.1, 2)
        await asyncio.to_thread(ctx_db.save_player, p)
        line = logic.pick(gd.t("extra3", "cert_ok"))
        return R(
            tmpl="panel",
            data={
                "icon": "📜",
                "title": f"{cert_name} 认证通过！",
                "accent": "#ffd86f",
                "lines": [line],
                "blocks": [
                    {"label": "考试费", "value": f"-{logic.fmt_money(cost)} 元"},
                    {
                        "label": "身价",
                        "value": f"+10%（当前 {logic.fmt_money(p['value'])}）",
                    },
                    {"label": "经验", "value": "+30"},
                ],
            },
            text=f"恭喜通过{cert_name}认证！身价提升10%",
        )
    line = logic.pick(gd.t("extra3", "cert_fail"))
    await asyncio.to_thread(ctx_db.save_player, p)
    return R(
        tmpl="panel",
        data={
            "icon": "😞",
            "title": f"{cert_name} 考试未通过",
            "accent": "#fc6262",
            "lines": [line],
            "blocks": [
                {"label": "考试费", "value": f"-{logic.fmt_money(cost)} 元（打水漂）"}
            ],
        },
        text=f"{cert_name}考试失败：{line}",
    )


async def travel(ctx_db, gid, uid, nickname, cfg):
    p = await _load(ctx_db, gid, uid, nickname, cfg)
    dests = gd.t("extra3", "travel")
    dest = random.choice(dests)
    if float(p["cash"]) < dest["cost"]:
        return R(
            err=f"去{dest['text'][:6]}需要约 {logic.fmt_money(dest['cost'])} 元，余额不足"
        )
    p["cash"] = round(float(p["cash"]) - dest["cost"], 2)
    p["mind"] = round(min(100, float(p["mind"]) + dest["mind"]), 1)
    p["health"] = round(min(100, float(p["health"]) + dest["health"]), 1)
    _clamp_status(p)
    await asyncio.to_thread(ctx_db.save_player, p)
    return R(
        tmpl="panel",
        data={
            "icon": "✈️",
            "title": "旅行归来",
            "accent": "#6fe08c",
            "lines": [dest["text"]],
            "blocks": [
                {"label": "旅行花费", "value": f"-{logic.fmt_money(dest['cost'])} 元"},
                {"label": "精神", "value": f"+{dest['mind']}（当前 {p['mind']}）"},
                {"label": "健康", "value": f"+{dest['health']}（当前 {p['health']}）"},
            ],
            "foot": "旅行是最好的充电方式，虽然回来还要面对现实",
        },
        text=f"旅行归来！{dest['text']}（花费 {logic.fmt_money(dest['cost'])} 元）",
    )
