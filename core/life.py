"""生活系统服务：吃饭、健身、租房、通勤、午休、团建、购物、买房、工资条。"""

import asyncio
import json
import random
import time

from . import gamedata as gd
from . import logic
from .result import R


async def eat(db, gid, uid, nickname, mode, cfg):
    p = await logic.load_player(db, gid, uid, nickname, cfg)
    meals = gd.meals()
    mode = (mode or "").strip()
    if not mode:
        mode = random.choice(list(meals)[:2] or list(meals))
    if mode not in meals:
        return R(err="吃法不对！可选：" + " / ".join(f"「吃饭 {k}」" for k in meals))
    cd = float(logic.cfg_get(cfg, "meal_cooldown_minutes", 30)) * 60
    if not logic.is_exempt(cfg, uid) and logic.cd_left(p, "meal") > 0:
        return R(
            err=f"刚吃过就又饿？冷却中：{logic.fmt_remaining(logic.cd_left(p, 'meal'))}"
        )
    logic.cd_set(p, "meal", cd)
    meal = meals[mode]
    if float(p["cash"]) < meal["cost"]:
        return R(
            err=f"吃「{mode}」需要 {meal['cost']} 元，余额不足（要不试试喝西北风？）"
        )
    p["cash"] = round(max(0.0, float(p["cash"]) - meal["cost"]), 2)
    p["health"] = round(float(p["health"]) + meal["health"], 1)
    p["mind"] = round(float(p["mind"]) + meal["mind"], 1)
    logic.clamp_status(p)
    await asyncio.to_thread(db.save_player, p)
    line = logic.pick(gd.t("life", meal.get("key") or "takeout"))
    return R(
        tmpl="panel",
        data={
            "icon": "🍜",
            "title": f"干饭 · {mode}",
            "accent": "#ffd86f",
            "lines": [line],
            "blocks": [
                {"label": "花费", "value": f"-{meal['cost']} 元"},
                {"label": "健康", "value": f"+{meal['health']}（当前 {p['health']}）"},
                {"label": "精神", "value": f"+{meal['mind']}（当前 {p['mind']}）"},
                {"label": "现金", "value": f"{logic.fmt_money(p['cash'])} 元"},
            ],
        },
        text=f"吃完{mode}：{line}（-{meal['cost']}元，健康+{meal['health']}，精神+{meal['mind']}）",
    )


async def gym(db, gid, uid, nickname, cfg):
    p = await logic.load_player(db, gid, uid, nickname, cfg)
    cost = float(logic.cfg_get(cfg, "gym_cost", 30.0))
    cd = float(logic.cfg_get(cfg, "gym_cooldown_hours", 2)) * 3600
    if not logic.is_exempt(cfg, uid) and logic.cd_left(p, "gym") > 0:
        return R(
            err=f"肌肉还在酸痛，休息一下：剩余 {logic.fmt_remaining(logic.cd_left(p, 'gym'))}"
        )
    if float(p["cash"]) < cost:
        return R(err=f"健身需要 {logic.fmt_money(cost)} 元（年卡摊销），余额不足")
    logic.cd_set(p, "gym", cd)
    lo = int(logic.cfg_get(cfg, "gym_health_min", 8))
    hi = int(logic.cfg_get(cfg, "gym_health_max", 15))
    gain = logic.ri(lo, hi)
    p["cash"] = round(max(0.0, float(p["cash"]) - cost), 2)
    p["health"] = round(float(p["health"]) + gain, 1)
    p["mind"] = round(float(p["mind"]) + logic.ri(2, 6), 1)
    logic.clamp_status(p)
    await asyncio.to_thread(db.save_player, p)
    line = logic.pick(gd.t("life", "gym"))
    return R(
        tmpl="panel",
        data={
            "icon": "🏋️",
            "title": "健身完成",
            "accent": "#6fe08c",
            "lines": [line],
            "blocks": [
                {"label": "花费", "value": f"-{logic.fmt_money(cost)} 元"},
                {"label": "健康", "value": f"+{gain}（当前 {p['health']} / 100）"},
                {"label": "精神", "value": f"{p['mind']} / 100"},
            ],
        },
        text=f"健身完成！健康 +{gain}（当前 {p['health']}）：{line}",
    )


async def move_house(db, gid, uid, nickname, keyword, cfg):
    p = await logic.load_player(db, gid, uid, nickname, cfg)
    kw = (keyword or "").strip()
    if not kw:
        hs = [h for h in gd.houses() if h["i"] != 7]
        lines = [
            f"{h_['i']}. {h_['name']}｜月租 {h_['rent']} 元｜押金 {h_['deposit']} 元｜精神恢复 +{h_['recover']}"
            for h_ in hs
        ]
        return R(
            tmpl="panel",
            data={
                "icon": "🏠",
                "title": "租房中介 · 房源列表",
                "accent": "#7fd1ff",
                "lines": lines,
                "foot": (
                    "你已拥有自购小窝，无需再租房"
                    if int(p.get("house_owned") or 0) == 1
                    else "自购小窝仅可通过「买房」获得；发送「租房 名称」入住，搬家需支付押金"
                ),
            },
            text="租房可选："
            + "、".join(f"{h_['name']}(押金{h_['deposit']})" for h_ in hs),
        )
    if int(p.get("house_owned") or 0) == 1:
        return R(
            err="你已经全款拿下「自购小窝」了（房租0元，每日恢复+40），无需再租房！"
        )
    # 优先数字索引；其它按 houses.json 名称子串匹配（取第一个）。
    # 单一来源 houses.json：以前在 HOUSE_KEYS 里写死的别名表已删除。
    target_i = None
    if kw.isdigit() and 0 <= int(kw) <= 11:
        target_i = int(kw)
    if target_i is None:
        for h_ in gd.houses():
            if kw in h_["name"]:
                target_i = h_["i"]
                break
    if target_i is None:
        return R(err=f"没有叫「{kw}」的房子，发送「租房」查看房源列表")
    cur = gd.house(int(p["house"]))
    tgt = gd.house(target_i)
    if tgt["i"] == cur["i"]:
        return R(err=f"你就住在「{cur['name']}」，不用重复租")
    if float(p["cash"]) < tgt["deposit"]:
        return R(
            err=f"「{tgt['name']}」需要押金 {tgt['deposit']} 元（押一付一），余额不足"
        )
    p["cash"] = round(float(p["cash"]) - tgt["deposit"], 2)
    p["house"] = tgt["i"]
    p["mind"] = round(min(100.0, float(p["mind"]) + 5), 1)
    await asyncio.to_thread(db.save_player, p)
    line = logic.pick(gd.t("life", "house_move"))
    return R(
        tmpl="panel",
        data={
            "icon": "🔑",
            "title": f"乔迁之喜 · {tgt['name']}",
            "accent": "#7fd1ff",
            "lines": [line],
            "blocks": [
                {"label": "押金", "value": f"-{tgt['deposit']} 元"},
                {"label": "月租", "value": f"{tgt['rent']} 元/天（打卡时自动扣）"},
                {"label": "每日恢复", "value": f"健康/精神 +{tgt['recover']}"},
                {"label": "房源描述", "value": tgt["desc"]},
            ],
        },
        text=f"已搬进「{tgt['name']}」，押金 -{tgt['deposit']} 元。{tgt['desc']}",
    )


async def stall(db, gid, uid, nickname, cfg):
    p = await logic.load_player(db, gid, uid, nickname, cfg)
    cd = float(logic.cfg_get(cfg, "stall_cooldown_hours", 6)) * 3600
    if not logic.is_exempt(cfg, uid) and logic.cd_left(p, "stall") > 0:
        return R(
            err=f"摊位还热乎着呢，冷却中：{logic.fmt_remaining(logic.cd_left(p, 'stall'))}"
        )
    logic.cd_set(p, "stall", cd)
    if random.random() < float(logic.cfg_get(cfg, "stall_fail_rate", 0.2)):
        p["mind"] = round(float(p["mind"]) - 5, 1)
        logic.clamp_status(p)
        await asyncio.to_thread(db.save_player, p)
        line = logic.pick(gd.t("life", "stall_fail"))
        return R(
            tmpl="panel",
            data={
                "icon": "🌧️",
                "title": "出师不利",
                "accent": "#fc6262",
                "lines": [line],
                "blocks": [{"label": "外快", "value": "0 元"}],
            },
            text=f"摆摊失败：{line}",
        )
    per_level = float(logic.cfg_get(cfg, "side_hustle_bonus_per_level", 0.2))
    side_mult = 1 + (int(p.get("side_lvl") or 1) - 1) * per_level
    lo = int(logic.cfg_get(cfg, "stall_income_min", 10))
    hi = int(logic.cfg_get(cfg, "stall_income_max", 60))
    exp_bonus = float(logic.cfg_get(cfg, "stall_exp_bonus_per_100", 5))
    income = round((logic.ri(lo, hi) + int(p["exp"]) // 100 * exp_bonus) * side_mult, 2)
    p["cash"] = round(float(p["cash"]) + income, 2)
    await asyncio.to_thread(db.save_player, p)
    line = logic.pick(gd.t("life", "stall_income"))
    lvl_note = (
        f"（副业 Lv.{int(p.get('side_lvl') or 1)} 加成 ×{side_mult:.1f}）"
        if side_mult > 1
        else ""
    )
    return R(
        tmpl="panel",
        data={
            "icon": "🛒",
            "title": "副业创收",
            "accent": "#ffd86f",
            "lines": [line],
            "blocks": [
                {"label": "外快到账", "value": f"+{logic.fmt_money(income)} 元"},
                {"label": "现金", "value": f"{logic.fmt_money(p['cash'])} 元"},
            ],
        },
        text=f"摆摊赚了 {logic.fmt_money(income)} 元{lvl_note}：{line}",
    )


async def shop_page():
    items = gd.shop_items()
    rows = []
    for it in items:
        eff = []
        if it.get("type") == "card":
            eff.append("【功能道具卡】")
        else:
            if it.get("health"):
                eff.append(f"健康+{it['health']}")
            if it.get("mind"):
                eff.append(f"精神+{it['mind']}")
        rows.append(
            {
                "id": it["id"],
                "name": it["name"],
                "price": logic.fmt_money(it["price"]),
                "effect": " / ".join(eff) or "无",
                "desc": it["desc"],
            }
        )
    return R(
        tmpl="shop",
        data={"items": rows},
        text="商店："
        + "；".join(
            f"{r['id']}.{r['name']} {r['price']}元({r['effect']})" for r in rows
        ),
    )


async def shop_buy(db, gid, uid, nickname, keyword, cfg):
    p = await logic.load_player(db, gid, uid, nickname, cfg)
    kw = (keyword or "").strip()
    if not kw:
        return R(err="想买什么？例如：「购买 红牛」或「购买 3」，发送「商店」查看货架")
    item = None
    if kw.isdigit():
        target_id = int(kw)
        item = next((x for x in gd.shop_items() if x["id"] == target_id), None)
    if item is None:
        # 精确名匹配优先
        item = next((x for x in gd.shop_items() if x["name"] == kw), None)
    if item is None:
        # 子串匹配只接受「唯一候选」，否则把全部候选列出来让用户改发
        matches = [x for x in gd.shop_items() if kw in x["name"]]
        if len(matches) == 1:
            item = matches[0]
        elif len(matches) > 1:
            names = " / ".join(f"「{x['name']}」" for x in matches[:6])
            return R(err=f"「{kw}」匹配到多个道具：{names}，请发更精确的名称")
    if item is None:
        return R(err=f"店里没有「{kw}」这个东西，发送「商店」看看货架吧")
    price = float(item["price"])
    if float(p["cash"]) < price:
        return R(err=f"{item['name']}售价 {logic.fmt_money(price)} 元，余额不足")
    p["cash"] = round(float(p["cash"]) - price, 2)
    if item.get("type") == "card":
        # 道具卡入背包
        bag = json.loads(p.get("items") or "{}")
        ckey = item.get("card_key", str(item["id"]))
        bag[ckey] = int(bag.get(ckey, 0)) + 1
        p["items"] = json.dumps(bag)
    else:
        p["health"] = round(float(p["health"]) + item.get("health", 0), 1)
        p["mind"] = round(float(p["mind"]) + item.get("mind", 0), 1)
        logic.clamp_status(p)
    await asyncio.to_thread(db.save_player, p)
    eff_text = []
    if item.get("type") == "card":
        eff_text.append("已放入背包（发送「我的背包」或「使用 道具名」）")
    else:
        if item.get("health"):
            eff_text.append(f"健康{item['health']:+g}")
        if item.get("mind"):
            eff_text.append(f"精神{item['mind']:+g}")
    return R(
        tmpl="panel",
        data={
            "icon": "🛍️",
            "title": f"已购入 · {item['name']}",
            "accent": "#6fe08c",
            "lines": [item["desc"]],
            "blocks": [
                {"label": "花费", "value": f"-{logic.fmt_money(price)} 元"},
                {"label": "效果", "value": "，".join(eff_text) or "无"},
                {"label": "健康", "value": f"{p['health']} / 100"},
                {"label": "精神", "value": f"{p['mind']} / 100"},
            ],
        },
        text=f"购买 {item['name']} 成功（-{logic.fmt_money(price)} 元）：{item['desc']}",
    )


async def resume(db, gid, uid, nickname, app_id: str = ""):
    p = await asyncio.to_thread(db.get_player, gid, uid, nickname)
    comp = await asyncio.to_thread(gd.resolve_company, int(p["company"]), db)
    pos = gd.position(int(p["lvl"]))
    pos_list = gd.positions()
    nxt = pos_list[int(p["lvl"]) + 1] if int(p["lvl"]) + 1 < len(pos_list) else None
    hs = gd.house(int(p["house"]))

    total_assets = round(float(p["cash"]) + float(p["deposit"]) + float(p["fund"]), 2)
    progress = 1.0
    if nxt and nxt["need"] > 0:
        progress = min(1.0, int(p["exp"]) / max(1, nxt["need"]))

    return R(
        tmpl="resume",
        data={
            "me": {
                "name": p["nickname"] or f"用户{uid}",
                "id": uid,
                "avatar": logic.avatar_of(uid, app_id),
            },
            "company": comp,
            "position": pos["title"],
            "salary": logic.fmt_money(p["salary"]),
            "exp": int(p["exp"]),
            "next_title": nxt["title"] if nxt else None,
            "next_need": nxt["need"] if nxt else 0,
            "progress": round(progress * 100),
            "health": round(float(p["health"]), 1),
            "mind": round(float(p["mind"]), 1),
            "house": {"name": hs["name"], "rent": hs["rent"], "recover": hs["recover"]},
            "cash": logic.fmt_money(p["cash"]),
            "deposit": logic.fmt_money(p["deposit"]),
            "fund": logic.fmt_money(p["fund"]),
            "total": logic.fmt_money(total_assets),
            "streak": p["attend_streak"],
            "commute": p.get("commute", "地铁"),
            "fund_savings": logic.fmt_money(p.get("fund_savings") or 0),
            "comp_leave": int(p.get("comp_leave") or 0),
            "value": logic.fmt_money(p["value"]),
            "duel": f"{p['duel_wins']}胜 {p['duel_losses']}负",
            "rank": f"{p['rank_tier']}（{p['rank_score']}分）",
        },
        text=(
            f"📋 我的简历\n"
            f"公司：{comp['name'] if comp else '失业中'}｜职位：{pos['title']}｜月薪：{logic.fmt_money(p['salary'])} 元\n"
            f"经验：{p['exp']}｜健康：{p['health']}｜精神：{p['mind']}\n"
            f"住房：{hs['name']}\n"
            f"现金：{logic.fmt_money(p['cash'])}｜存款：{logic.fmt_money(p['deposit'])}｜基金：{logic.fmt_money(p['fund'])}\n"
            f"总资产：{logic.fmt_money(total_assets)} 元\n"
            f"身价：{logic.fmt_money(p['value'])}｜通勤：{p.get('commute', '地铁')}｜公积金：{logic.fmt_money(p.get('fund_savings') or 0)}\n"
            f"对线战绩：{p['duel_wins']}胜{p['duel_losses']}负｜卷王段位：{p['rank_tier']}"
        ),
    )


async def set_commute(ctx_db, gid, uid, mode):
    modes = gd.commute_modes()
    names = " / ".join(modes)
    mode = (mode or "").strip()
    if not mode:
        p = await asyncio.to_thread(ctx_db.get_player, gid, uid)
        cur = str(p.get("commute") or next(iter(modes)))
        lines = [
            f"「{name}」单程 {m['cost']:g} 元｜健康{m['health']:+g} 精神{m['mind']:+g}"
            f"｜迟到率 {m['late_rate'] * 100:g}%"
            for name, m in modes.items()
        ]
        return R(
            tmpl="panel",
            data={
                "icon": "🚇",
                "title": f"通勤方案（当前：{cur}）",
                "accent": "#7fd1ff",
                "lines": lines,
                "foot": f"发送「通勤 {names}」切换，每天打卡时自动生效",
            },
            text="通勤可选：" + "、".join(modes),
        )
    if mode not in modes:
        return R(err=f"通勤方式仅支持：{names}")
    p = await asyncio.to_thread(ctx_db.get_player, gid, uid)
    p["commute"] = mode
    await asyncio.to_thread(ctx_db.save_player, p)
    m = modes[mode]
    return R(
        tmpl="panel",
        data={
            "icon": "🚇",
            "title": f"已切换通勤方式：{mode}",
            "accent": "#6fe08c",
            "blocks": [
                {"label": "单程花费", "value": f"{m['cost']:g} 元"},
                {"label": "体感", "value": f"健康{m['health']:+g} 精神{m['mind']:+g}"},
                {
                    "label": "迟到率",
                    "value": f"{m['late_rate'] * 100:g}%（迟到当日薪资按配置折扣计薪）",
                },
            ],
            "foot": "明天打卡时自动按新路线通勤",
        },
        text=f"通勤方式已切换为「{mode}」",
    )


async def nap(db, gid, uid, nickname, cfg):
    p = await logic.load_player(db, gid, uid, nickname, cfg)
    if int(p["company"]) == -1:
        return R(err="失业人士想睡多久睡多久，不需要午休指令")
    now = time.time()
    if not logic.is_exempt(cfg, uid) and logic.cd_left(p, "nap") > 0:
        return R(err="一天只能午休一次，下午靠咖啡续命吧")
    # CD 设置到「下一个 00:00 之后 60s」：过零点意味着新一天自动解锁，
    # 不再出现 23:59 午休 → 30 秒后又合法的小窗口。
    lt = time.localtime(now)
    secs_to_midnight = 86400 - (lt.tm_hour * 3600 + lt.tm_min * 60 + lt.tm_sec)
    logic.cd_set(p, "nap", secs_to_midnight + 60)
    caught = random.random() < float(logic.cfg_get(cfg, "nap_caught_rate", 0.15))
    if caught:
        p["mind"] = round(float(p["mind"]) - 2, 1)
        line = logic.pick(gd.t("life", "nap_caught"))
        title, accent, icon = "午休翻车", "#fc6262", "😳"
        blocks = [{"label": "精神", "value": f"-2（当前 {p['mind']}）"}]
    else:
        gain = logic.ri(8, 12)
        p["mind"] = round(float(p["mind"]) + gain, 1)
        p["health"] = round(float(p["health"]) + 1, 1)
        line = logic.pick(gd.t("life", "nap_ok"))
        title, accent, icon = "午休完毕", "#6fe08c", "😴"
        blocks = [
            {"label": "精神", "value": f"+{gain}（当前 {p['mind']}）"},
            {"label": "健康", "value": "+1"},
        ]
    logic.clamp_status(p)
    await asyncio.to_thread(db.save_player, p)
    return R(
        tmpl="panel",
        data={
            "icon": icon,
            "title": title,
            "accent": accent,
            "lines": [line],
            "blocks": blocks,
        },
        text=f"{title}：{line}",
    )


async def team_building(db, gid, uid, nickname, cfg):
    p = await logic.load_player(db, gid, uid, nickname, cfg)
    if int(p["company"]) == -1:
        return R(err="失业人士没有团建，只有自由的空气")
    if not logic.is_exempt(cfg, uid) and logic.cd_left(p, "teambuild") > 0:
        return R(
            err=f"刚被团建完，缓一缓：剩余 {logic.fmt_remaining(logic.cd_left(p, 'teambuild'))}"
        )
    logic.cd_set(p, "teambuild", 7 * 86400)

    ev = logic.pick(gd.t("life", "teambuild"))
    # 文案里 cash 字段缺失或异常时按 0 处理；非正数也钳到 0，避免「垫付负数 = 报销反向」账目错位
    spend = max(0, int(ev.get("cash", 0) or 0))
    p["cash"] = round(max(0.0, float(p["cash"]) - spend), 2)
    p["health"] = float(p["health"]) + ev.get("health", 0)
    p["mind"] = float(p["mind"]) + ev.get("mind", 0)
    exp_gain = int(ev.get("exp", 1))
    p["exp"] = int(p["exp"]) + exp_gain
    logic.clamp_status(p)
    await asyncio.to_thread(db.save_player, p)
    if spend:
        await asyncio.to_thread(
            db.add_transaction, gid, uid, "团建垫付", -spend, ev["text"][:40]
        )
    blocks = [
        {
            "label": "个人花费",
            "value": (f"-{logic.fmt_money(spend)} 元" if spend else "公司报销，0 元"),
        },
        {"label": "健康", "value": f"{p['health']} / 100"},
        {"label": "精神", "value": f"{p['mind']} / 100"},
        {"label": "经验", "value": f"+{exp_gain}（当前 {p['exp']}）"},
    ]
    return R(
        tmpl="panel",
        data={
            "icon": "🏕️",
            "title": f"团建 · {ev['type']}",
            "accent": "#7fd1ff",
            "lines": [ev["text"]],
            "blocks": blocks,
            "foot": "团建占用的是周末，但老板觉得这是福利",
        },
        text=f"团建「{ev['type']}」：{ev['text']}",
    )


async def shopping(db, gid, uid, nickname, cfg):
    p = await logic.load_player(db, gid, uid, nickname, cfg)
    if not logic.is_exempt(cfg, uid) and logic.cd_left(p, "shopping") > 0:
        return R(
            err=f"钱包还在流泪，冷静一下：剩余 {logic.fmt_remaining(logic.cd_left(p, 'shopping'))}"
        )
    logic.cd_set(p, "shopping", 6 * 3600)

    budgets = list(logic.cfg_get(cfg, "shopping_budgets", [99, 299, 999]) or [99, 299, 999])
    weights = list(logic.cfg_get(cfg, "shopping_weights", [60, 30, 10]) or [60, 30, 10])
    # 配置写歪时退回等权，避免 random.choices 抛异常后变成永久兜底
    if len(weights) != len(budgets):
        weights = [1.0] * len(budgets)
    budget = random.choices(budgets, weights=weights)[0]
    roll = random.random()
    if roll < 0.15:
        shipping = round(budget * 0.1, 2)
        p["cash"] = round(max(0.0, float(p["cash"]) - shipping), 2)
        p["mind"] = round(float(p["mind"]) + 5, 1)
        note, title, accent = (
            f"凑单失误后成功退货，只花了运费 {shipping} 元",
            "退货小能手",
            "#7fd1ff",
        )
        await asyncio.to_thread(
            db.add_transaction,
            gid,
            uid,
            "购物退款",
            -shipping,
            "退货成功仅付运费",
        )
        outcome = "refund"
    elif roll < 0.30:
        saved = random.randint(20, min(200, budget))
        pay = budget - saved
        p["cash"] = round(max(0.0, float(p["cash"]) - pay), 2)
        p["mind"] = round(float(p["mind"]) + 18, 1)
        note = f"蹲到满减神券，原价 {budget} 只付了 {pay} 元，省下的都是赚的"
        title, accent = "薅羊毛成功", "#6fe08c"
        await asyncio.to_thread(
            db.add_transaction, gid, uid, "购物", -pay, f"省了 {saved} 元"
        )
        outcome = "deal"
    else:
        p["cash"] = round(max(0.0, float(p["cash"]) - budget), 2)
        p["mind"] = round(float(p["mind"]) + logic.ri(8, 16), 1)
        note = logic.pick(gd.t("life", "shopping"))
        title, accent = "剁手快乐", "#ffd86f"
        await asyncio.to_thread(
            db.add_transaction, gid, uid, "购物", -budget, note[:40]
        )
        outcome = "normal"
    logic.clamp_status(p)
    await asyncio.to_thread(db.save_player, p)
    return R(
        tmpl="panel",
        data={
            "icon": "🛍️",
            "title": title,
            "accent": accent,
            "lines": [note],
            "blocks": [
                {"label": "现金余额", "value": f"{logic.fmt_money(p['cash'])} 元"},
                {"label": "精神", "value": f"{p['mind']} / 100"},
                {
                    "label": "提醒",
                    "value": "下单一时爽，吃土月底见"
                    if outcome != "refund"
                    else "下次继续",
                },
            ],
        },
        text=f"{title}：{note}",
    )


async def buy_house(db, gid, uid, nickname, cfg):
    p = await logic.load_player(db, gid, uid, nickname, cfg)
    if int(p.get("house_owned") or 0) == 1:
        return R(err="你已经有自己的小窝了，还想买第二套？炒房行为不予支持")
    price = float(logic.cfg_get(cfg, "house_price", 100000))
    fund_pool = float(p.get("fund_savings") or 0)
    offset_rate = float(logic.cfg_get(cfg, "house_fund_offset_max_rate", 0.3))
    offset = round(min(fund_pool, price * offset_rate), 2)
    due = round(price - offset, 2)
    fmt = logic.fmt_money
    if float(p["cash"]) < due:
        return R(
            err=(
                f"首付还差得远！总价 {fmt(price)} 元，公积金最高抵扣 {fmt(offset)} 元"
                f"（当前余额 {fmt(fund_pool)}），仍需现金 {fmt(due)} 元，你只有 {fmt(p['cash'])}"
            )
        )
    p["cash"] = round(float(p["cash"]) - due, 2)
    p["house_owned"] = 1
    p["house"] = 7
    p["fund_savings"] = 0.0
    p["mind"] = round(min(100.0, float(p["mind"]) + 30), 1)
    await asyncio.to_thread(db.save_player, p)
    name = p.get("card") or p["nickname"] or uid
    await asyncio.to_thread(
        db.add_event, gid, uid, "买房", f"{name} 全款拿下自购小窝（{fmt(due)} 元）！"
    )
    await asyncio.to_thread(
        db.add_transaction, gid, uid, "买房", -due, "公积金抵扣 " + fmt(offset)
    )
    line = logic.pick(gd.t("life", "house_owned_texts"))
    return R(
        tmpl="panel",
        data={
            "icon": "🏡",
            "title": "恭喜！你在这个城市有家了",
            "accent": "#ffd86f",
            "lines": [line],
            "blocks": [
                {"label": "房屋总价", "value": f"{fmt(price)} 元"},
                {"label": "公积金抵扣", "value": f"-{fmt(offset)} 元"},
                {"label": "实付", "value": f"-{fmt(due)} 元"},
                {
                    "label": "从此以后",
                    "value": "房租 0 元｜每日恢复 +40｜再也不用看房东脸色",
                },
            ],
            "foot": "这是打工人能写进简历的荣耀",
        },
        text=f"买房成功！实付 {fmt(due)} 元（公积金抵扣 {fmt(offset)}）。{line}",
    )


async def payslip(db, gid, uid, nickname):
    p = await asyncio.to_thread(db.get_player, gid, uid, nickname)
    comp = await asyncio.to_thread(gd.resolve_company, int(p["company"]), db)
    txs = await asyncio.to_thread(db.recent_transactions, gid, uid, 12)
    rows = []
    for t in reversed(txs):
        amount = float(t["amount"])
        rows.append(
            {
                "cells": [
                    time.strftime("%m-%d %H:%M", time.localtime(t["created_at"])),
                    t["kind"],
                    ("+" if amount >= 0 else "") + logic.fmt_money(amount) + " 元",
                    t.get("note") or "",
                ],
                "fail": amount < 0,
            }
        )
    if not rows:
        rows.append({"cells": ["-", "暂无流水", "-", "先去打卡赚钱吧"], "fail": True})
    return R(
        tmpl="table",
        data={
            "icon": "🧾",
            "title": "我的工资条 · 收支流水",
            "accent": "#7fd1ff",
            "summary": [
                {
                    "label": "累计总收入",
                    "value": f"{logic.fmt_money(p['total_earned'])} 元",
                },
                {
                    "label": "公积金余额",
                    "value": f"{logic.fmt_money(p['fund_savings'])} 元",
                },
                {
                    "label": "现金 / 存款",
                    "value": f"{logic.fmt_money(p['cash'])} / {logic.fmt_money(p['deposit'])}",
                },
                {
                    "label": "月薪标准",
                    "value": (
                        f"{logic.fmt_money(p['salary'])} 元" if comp else "无业中"
                    ),
                },
            ],
            "cols": ["时间", "项目", "金额", "备注"],
            "rows": rows[-12:][::-1],
            "note": f"调休券 {p.get('comp_leave', 0)} 张｜通勤方式 {p.get('commute', '地铁')}",
        },
        text="工资条：累计收入 "
        + logic.fmt_money(p["total_earned"])
        + " 元；公积金 "
        + logic.fmt_money(p["fund_savings"]),
    )


async def train_self(db, gid, uid, nickname, cfg):
    """自费进修班：花现金提升身价与经验。"""
    p = await logic.load_player(db, gid, uid, nickname, cfg)
    cost = max(
        float(logic.cfg_get(cfg, "train_cost_min", 200)),
        round(
            float(p["value"])
            * float(logic.cfg_get(cfg, "train_cost_rate", 0.1))
            * float(logic.cfg_get(cfg, "train_cost_multiplier", 5))
        ),
    )
    if float(p["cash"]) < cost:
        return R(
            err=f"报名进修班需要 {logic.fmt_money(cost)} 元（按当前身价浮动），余额不足"
        )
    cd = int(float(logic.cfg_get(cfg, "train_cooldown_hours", 2.0)) * 3600)
    if not logic.is_exempt(cfg, uid) and logic.cd_left(p, "jinxiu") > 0:
        return R(
            err=f"刚结业一门课，先消化消化：剩余 {logic.fmt_remaining(logic.cd_left(p, 'jinxiu'))}"
        )
    logic.cd_set(p, "jinxiu", cd)
    p["cash"] = round(float(p["cash"]) - cost, 2)
    exp_gain = logic.ri(3, 8)

    if random.random() < float(logic.cfg_get(cfg, "train_success_rate", 0.7)):
        increase = round(
            float(p["value"])
            * float(logic.cfg_get(cfg, "train_value_increase_rate", 0.2)),
            2,
        )
        p["value"] = round(float(p["value"]) + increase, 2)
        p["exp"] = int(p["exp"]) + exp_gain
        line = logic.pick(gd.t("company", "jinxiu_ok"))
        await asyncio.to_thread(db.save_player, p)
        await asyncio.to_thread(
            db.add_transaction, gid, uid, "进修学费", -cost, "能力提升"
        )
        return R(
            tmpl="panel",
            data={
                "icon": "🎓",
                "title": "进修结业 · 能力提升",
                "accent": "#6fe08c",
                "lines": [line],
                "blocks": [
                    {"label": "学费", "value": f"-{logic.fmt_money(cost)} 元"},
                    {
                        "label": "职场身价",
                        "value": f"+{increase} -> {logic.fmt_money(p['value'])}",
                    },
                    {"label": "经验", "value": f"+{exp_gain}（当前 {p['exp']}）"},
                ],
            },
            text=f"进修成功！身价 +{increase} 至 {logic.fmt_money(p['value'])}，学费 {logic.fmt_money(cost)} 元",
        )

    p["exp"] = int(p["exp"]) + logic.ri(1, 3)
    line = logic.pick(gd.t("company", "jinxiu_fail"))
    await asyncio.to_thread(db.save_player, p)
    await asyncio.to_thread(
        db.add_transaction, gid, uid, "进修学费", -cost, "未通过考核"
    )
    return R(
        tmpl="panel",
        data={
            "icon": "📉",
            "title": "进修未果",
            "accent": "#fc6262",
            "lines": [line],
            "blocks": [
                {"label": "学费", "value": f"-{logic.fmt_money(cost)} 元（打水漂）"},
                {"label": "经验", "value": "+少量（好歹听了几节）"},
            ],
        },
        text=f"进修失败：{line}（学费 {logic.fmt_money(cost)} 元）",
    )


async def my_bag(db, gid, uid, nickname, cfg):
    p = await logic.load_player(db, gid, uid, nickname, cfg)
    bag = json.loads(p.get("items") or "{}")
    items_meta = {it.get("card_key", str(it["id"])): it for it in gd.shop_items()}
    rows = []
    for k, cnt in bag.items():
        if cnt > 0:
            meta = items_meta.get(k) or {"name": k, "desc": "未知道具"}
            rows.append(f"{meta['name']} x{cnt} ({meta['desc']})")
    if not rows:
        return R(err="你的背包空空如也，发送「商店」去采购些职场道具卡吧！")
    return R(
        tmpl="panel",
        data={
            "icon": "🎒",
            "title": f"{p['nickname'] or uid} 的职场道具包",
            "accent": "#ffd86f",
            "lines": rows,
            "foot": "使用方法：发送「使用 道具名」即可消耗并生效",
        },
        text="🎒 我的背包：\n" + "\n".join(rows),
    )


async def use_item(db, gid, uid, nickname, item_name, cfg):
    p = await logic.load_player(db, gid, uid, nickname, cfg)
    bag = json.loads(p.get("items") or "{}")
    item_name = (item_name or "").strip()
    if not item_name:
        return R(err="请指定要使用的道具名，例如：「使用 咖啡续命包」，发送「我的背包」查看持有道具")
    
    # 匹配道具 key
    target_key = None
    target_item = None
    for it in gd.shop_items():
        if it.get("type") == "card":
            ckey = it.get("card_key", str(it["id"]))
            if item_name in it["name"] or it["name"] in item_name or item_name == ckey:
                target_key = ckey
                target_item = it
                break

    if not target_key or bag.get(target_key, 0) <= 0:
        return R(err=f"背包里没有可用道具「{item_name}」，发送「我的背包」确认")

    # 消耗道具
    bag[target_key] -= 1
    p["items"] = json.dumps(bag)

    # 触发道具效果
    msg_lines = []
    if target_key == "coffee_pack":
        p["health"] = round(logic.clamp(float(p["health"]) + 30, 0, 100), 1)
        p["mind"] = round(logic.clamp(float(p["mind"]) + 30, 0, 100), 1)
        # 清除加班 CD
        cds = p.setdefault("_cds", {})
        cds.pop("ot", None)
        msg_lines.append("喝下顶级特调咖啡，瞬间满血复活！健康+30，精神+30，加班疲劳已重置！")
    elif target_key == "shield":
        # 写入护盾标记
        cds = p.setdefault("_cds", {})
        cds["shield_active"] = 1
        msg_lines.append("【防甩锅护盾】已装配！将自动抵挡下一次摸鱼被抓或撕逼对线失败的惩罚。")
    elif target_key == "poop":
        cds = p.setdefault("_cds", {})
        cds["poop_active"] = 1
        msg_lines.append("【带薪拉屎卡】已激活！下一次摸鱼 100% 成功，且精神双倍恢复！")
    elif target_key == "radar":
        # 探测全群摸鱼风险与今日早报
        msg_lines.append(f"【老板雷达】今日职场大盘：{gd.news_of_day()}")
        msg_lines.append(f"当前全服裁员概率倍率：{float(logic.cfg_get(cfg, 'layoff_scale', 1.0)):.1f}x")
        msg_lines.append("老板动向：HR 正在巡视工位，摸鱼请留意！")

    await asyncio.to_thread(db.save_player, p)
    return R(
        tmpl="panel",
        data={
            "icon": "✨",
            "title": f"使用道具 · {target_item['name']}",
            "accent": "#6fe08c",
            "lines": msg_lines,
            "blocks": [
                {"label": "道具状态", "value": "已消耗 1 件"},
                {"label": "剩余数量", "value": f"{bag[target_key]} 件"},
                {"label": "健康/精神", "value": f"{p['health']} / {p['mind']}"},
            ],
        },
        text=f"使用「{target_item['name']}」成功：" + " ".join(msg_lines),
    )

