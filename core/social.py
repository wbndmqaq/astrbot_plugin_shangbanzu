"""对抗与信息线：职场对线、卷王大赛（亲自出战）、同事录。"""

import asyncio
import random

from . import gamedata as gd
from . import logic
from .result import R


async def market_list(db, gid, app_id: str = "", cfg=None):
    players = await asyncio.to_thread(db.all_players, gid)
    if not players:
        return R(err="本群还没有人入职任何公司，快发送「找工作」当第一个上班族")
    players.sort(key=lambda x: (int(x["lvl"]), float(x["salary"])), reverse=True)
    names = gd.company_names(await asyncio.to_thread(db.custom_companies_of_group, gid))
    rows = []
    cap = int(logic.cfg_get(cfg, "market_list_max", 60))
    for i, pl in enumerate(players[:cap], 1):
        rows.append(
            {
                "rank": i,
                "name": pl.get("card") or pl["nickname"] or f"用户{pl['uid']}",
                "id": pl["uid"],
                "value": logic.fmt_money(pl["value"]),
                "position": gd.position(int(pl["lvl"]))["title"],
                "company": gd.display_company(pl["company"], names),
                "boss": logic.fmt_money(pl["salary"]) + " 元/月",
                "avatar": logic.avatar_of(pl["uid"], app_id),
            }
        )
    return R(
        tmpl="market",
        data={"rows": rows, "count": len(players)},
        text="同事名录："
        + "；".join(f"{r['name']}({r['company']}·{r['position']})" for r in rows[:15]),
    )


async def duel(db, gid, me, target, cfg, target_name="", app_id: str = ""):
    if str(target) == str(me):
        return R(err="自己跟自己对线？精神状态堪忧啊朋友")
    # 对手必须是已入档玩家：否则可以对着随手编的 ID 建号刷胜场和奖金
    td = await asyncio.to_thread(db.find_player_any, gid, str(target))
    if not td:
        return R(err="对方还没有加入游戏（让 TA 先发一次「上班」），没法对线")
    target = td["uid"]
    # find_player_any 可能解析到自己的别名（如昵称匹配命中自己），再防一次
    if str(target) == str(me):
        return R(err="自己跟自己对线？精神状态堪忧啊朋友")
    p = await logic.load_player(db, gid, me, "", cfg)
    fmt = logic.fmt_money
    my_name = p.get("card") or p["nickname"] or me
    t_name = td.get("card") or td["nickname"] or target_name or f"用户{target}"

    cd = float(logic.cfg_get(cfg, "duel_cooldown_hours", 2)) * 3600
    if not logic.is_exempt(cfg, me) and logic.cd_left(p, "duel") > 0:
        return R(
            err=f"对线上头伤身，冷却中：剩余 {logic.fmt_remaining(logic.cd_left(p, 'duel'))}"
        )
    fee = float(logic.cfg_get(cfg, "duel_entry_fee", 50))
    if float(p["cash"]) < fee:
        return R(err=f"对线需要 {logic.fmt_money(fee)} 元场地费，余额不足")
    logic.cd_set(p, "duel", cd)

    # 探测【防甩锅护盾】（仅失利时消耗，胜利保留）
    cds = p.setdefault("_cds", {})
    shield = cds.get("shield_active")

    v1, v2 = float(p["value"]), float(td["value"])
    diff = v1 - v2
    weight = float(logic.cfg_get(cfg, "duel_value_weight", 0.5))
    max_adv = float(logic.cfg_get(cfg, "duel_max_advantage", 0.3))
    win_rate = float(logic.cfg_get(cfg, "duel_base_win_rate", 0.5)) + min(
        max_adv, abs(diff) / max(v1, v2, 1) * weight
    ) * (1 if diff > 0 else -1)
    win = random.random() < win_rate

    actions_pool = [t.format(a=my_name, b=t_name) for t in gd.t("duel", "actions")]
    process = random.sample(
        actions_pool, k=min(len(actions_pool), random.randint(3, 4))
    )

    # 护盾生效分支：对线失败但持有护盾，免除场地费扣除与身价下跌
    if not win and shield:
        cds.pop("shield_active", None)
        await asyncio.to_thread(db.save_player, p)
        return R(
            tmpl="panel",
            data={
                "icon": "🛡️",
                "title": "对线失利 · 护盾生效！",
                "accent": "#ffd86f",
                "lines": [
                    f"你在与 {t_name} 的PPT对线中落于下风，但你装配的【防甩锅护盾】为你吸收了全部惩罚！"
                ],
                "blocks": [
                    {"label": "护盾状态", "value": "已消耗 1 层"},
                    {"label": "场地费/身价", "value": "100% 豁免"},
                    {"label": "战绩记录", "value": "不计入负场"},
                ],
            },
            text="对线失利！但你的【防甩锅护盾】生效，免除了场地费与身价扣除！",
        )

    result_line = logic.pick(gd.t("duel", "win_lines" if win else "lose_lines"))

    reward_rate = float(logic.cfg_get(cfg, "duel_reward_rate", 0.2))
    bonus_rate = float(logic.cfg_get(cfg, "duel_value_bonus_rate", 0.1))
    # 获胜：退还报名费并按报名费比例发放奖金，确保赢家净收益为正
    reward = round(fee * (1 + reward_rate), 2) if win else 0.0
    net = round(reward - fee, 2)
    p["cash"] = round(float(p["cash"]) + net, 2)
    v_up = (
        int(float(p["value"]) * bonus_rate)
        if win
        else int(float(td["value"]) * bonus_rate)
    )
    # 败方身价惩罚率必须与胜方加成一起可调：只调加成会让每场对线净增身价
    penalty_rate = float(logic.cfg_get(cfg, "duel_value_penalty_rate", 0.05))
    v_down = (
        int(float(td["value"]) * penalty_rate)
        if win
        else int(float(p["value"]) * penalty_rate)
    )
    # 我方在 per-user 锁内走 save_player；对方走原子列更新，
    # 防止"读对方快照→全列覆盖"把对方并发改动（存款/打卡等）冲掉
    if win:
        p["value"] = round(float(p["value"]) + v_up, 2)
        p["duel_wins"] = int(p["duel_wins"]) + 1
        await asyncio.to_thread(db.save_player, p)
        await asyncio.to_thread(db.bump_duel_loss, gid, str(target), float(v_down))
    else:
        p["value"] = round(max(20.0, float(p["value"]) - v_down), 2)
        p["duel_losses"] = int(p["duel_losses"]) + 1
        await asyncio.to_thread(db.save_player, p)
        await asyncio.to_thread(db.bump_duel_win, gid, str(target), float(v_up))
    # 展示值：我方取内存，对方取落库后的真实值（含 MAX(20) 下限）
    td_after = await asyncio.to_thread(db.get_player, gid, str(target))
    winner_value = p["value"] if win else td_after["value"]
    loser_value = td_after["value"] if win else p["value"]
    w_name = my_name if win else t_name
    l_name = t_name if win else my_name
    await asyncio.to_thread(
        db.add_event,
        gid,
        me,
        "对线",
        f"{w_name} 在PPT对线中击败 {l_name}（{'+' if net >= 0 else ''}{fmt(net)} 元）",
    )
    return R(
        tmpl="duel",
        data={
            "a": {"name": my_name, "avatar": logic.avatar_of(me, app_id)},
            "b": {"name": t_name, "avatar": logic.avatar_of(target, app_id)},
            "process": process,
            "win": win,
            "winner": w_name,
            "result_line": result_line,
            "blocks": [
                {"label": "场地费", "value": f"-{fmt(fee)} 元"},
                {
                    "label": "奖金",
                    "value": f"+{fmt(reward)} 元（含退还报名费）"
                    if win
                    else "颗粒无收",
                },
                {
                    "label": "净收益",
                    "value": ("+" if net >= 0 else "") + fmt(net) + " 元",
                },
                {
                    "label": f"{w_name} 身价",
                    "value": f"+{v_up} -> {fmt(winner_value)}",
                },
                {
                    "label": f"{l_name} 身价",
                    "value": f"-{v_down} -> {fmt(loser_value)}",
                },
                {
                    "label": "你的战绩",
                    "value": f"{p['duel_wins']}胜 {p['duel_losses']}负",
                },
            ],
        },
        text=f"对线结束：{w_name} 获胜！{result_line}\n你的净收益 {'+' if net >= 0 else ''}{fmt(net)} 元",
    )


async def rank_show(db, gid, me):
    # 纯查看命令，不能 get_player 给陌生 ID 顺手建号
    p = await asyncio.to_thread(db.find_player_any, gid, str(me))
    if not p:
        return R(err="你还没有参赛记录，先发一次「上班」建档吧")
    lines = [
        f"你的段位：{p['rank_tier']}｜积分：{p['rank_score']}｜场次：{p['rank_matches']}",
        "对手池里全是真实同事原型，赢的是积分与奖金，输的只是面子",
    ]
    return R(
        tmpl="panel",
        data={
            "icon": "🏁",
            "title": "卷王大赛 · 我的战绩",
            "accent": "#ffd86f",
            "lines": lines,
            "foot": "段位线：菜鸟<1000｜老油条≥1000｜职场精英≥1400｜行业大佬≥1800｜传奇卷王≥2200。"
            "发送「参加卷王大赛」亲自出战",
        },
        text=lines[0],
    )


async def rank_join(db, gid, me, cfg, nickname=""):
    p = await logic.load_player(db, gid, me, nickname, cfg)
    if int(p["company"]) == -1:
        return R(err="连工作都没有还想去卷？先「找工作」")
    cooldown = int(float(logic.cfg_get(cfg, "rank_cooldown_minutes", 60.0)) * 60)
    if not logic.is_exempt(cfg, me) and logic.cd_left(p, "rank") > 0:
        return R(
            err=f"大赛间隔中，让选手缓缓：剩余 {logic.fmt_remaining(logic.cd_left(p, 'rank'))}"
        )

    ev = logic.pick(gd.rank_events())
    if not isinstance(ev, dict):
        ev = {"effect": 1.0, "text": "比赛正常进行"}
    opponent = gd.match_opponent(int(p["rank_score"]))
    base = float(logic.cfg_get(cfg, "rank_base_win_rate", 0.5))
    win = random.random() < base * float(ev["effect"])
    diff = logic.elo_change(
        int(p["rank_score"]),
        int(opponent["score"]),
        win,
        k=int(logic.cfg_get(cfg, "rank_elo_k", 32)),
    )
    p["rank_score"] = max(0, int(p["rank_score"]) + diff)
    p["rank_matches"] = int(p["rank_matches"]) + 1
    p["rank_tier"] = logic.tier_of(p["rank_score"])
    # 只对胜利发奖金：此前输了也按积分差发钱，等于人人都有稳定出场费
    reward = (
        int(abs(diff) * float(logic.cfg_get(cfg, "rank_reward_rate", 0.1)))
        if win
        else 0
    )
    p["cash"] = round(float(p["cash"]) + reward, 2)
    logic.cd_set(p, "rank", cooldown)
    await asyncio.to_thread(db.save_player, p)
    name = p.get("card") or p["nickname"] or me
    await asyncio.to_thread(
        db.add_event,
        gid,
        me,
        "卷王大赛",
        f"{name} 对阵「{opponent['name']}」{'获胜' if win else '落败'}，积分{diff:+d} -> {p['rank_score']}",
    )
    return R(
        tmpl="panel",
        data={
            "icon": "🏆",
            "title": f"卷王大赛 · {'胜利！' if win else '惜败...'}",
            "accent": "#ffd86f" if win else "#fc6262",
            "lines": [
                f"当前事件：{ev['name']}（{ev['desc']}）",
                f"你 VS 「{opponent['name']}」—— {opponent['effect']}",
            ],
            "blocks": [
                {"label": "结果", "value": "胜利" if win else "失败"},
                {"label": "积分变化", "value": f"{diff:+d}（当前 {p['rank_score']}）"},
                {"label": "当前段位", "value": p["rank_tier"]},
                {"label": "出场费奖励", "value": f"+{logic.fmt_money(reward)} 元"},
            ],
        },
        text=(
            f"卷王大赛：你 VS {opponent['name']} {'胜' if win else '负'}，"
            f"积分{diff:+d}至 {p['rank_score']}，奖励 {reward} 元"
        ),
    )


async def rank_data(db, gid, kind, app_id: str = "", cfg=None):
    kind = kind if kind in ("wealth", "exp", "value", "level") else "wealth"
    titles = {
        "wealth": "富豪榜（总资产）",
        "exp": "卷王榜（职场经验）",
        "value": "身价榜",
        "level": "职级榜（职位·月薪）",
    }
    units = {"wealth": "元", "exp": "点经验", "value": "身价", "level": "职级"}
    top_n = int(logic.cfg_get(cfg, "ranking_top_n", 10))
    if kind == "level":
        players = await asyncio.to_thread(db.top_level, gid, top_n)
    elif kind == "wealth":
        players = await asyncio.to_thread(db.top_wealth, gid, top_n)
    else:
        col = "exp" if kind == "exp" else "value"
        players = await asyncio.to_thread(db.top_by_column, gid, col, top_n)
    rows = []
    names = (
        gd.company_names(await asyncio.to_thread(db.custom_companies_of_group, gid))
        if kind == "level"
        else {}
    )
    for pl in players:
        if kind == "wealth":
            score_val = logic.fmt_money(pl.get("total", 0))
        elif kind == "level":
            comp_name = gd.display_company(pl["company"], names, jobless="")
            score_val = f"L{pl['lvl']} · {gd.position(int(pl['lvl']))['title']}" + (
                f" @ {comp_name}" if comp_name else ""
            )
        elif kind == "exp":
            score_val = f"{pl['exp']} 点"
        else:
            score_val = logic.fmt_money(pl["value"])
        rows.append(
            {
                "rank": int(pl.get("rank", 0)),
                "name": pl.get("card") or pl["nickname"] or f"用户{pl['uid']}",
                "id": pl["uid"],
                "score": score_val,
                "avatar": logic.avatar_of(pl["uid"], app_id),
            }
        )
    return R(
        tmpl="ranking",
        data={"title": titles[kind], "unit": units[kind], "rows": rows},
        text=titles[kind]
        + "\n"
        + "\n".join(f"{r['rank']}. {r['name']}：{r['score']}" for r in rows),
    )
