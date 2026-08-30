"""职业系统服务：求职、打卡、摸鱼、加班、请假、晋升、辞职、跳槽。"""

import asyncio
import random

from . import gamedata as gd
from . import logic
from .result import R


def _resolve_company(cid: int, db=None) -> dict | None:
    """公司解析统一入口（静态公司 + 群友自建公司）。"""
    return gd.resolve_company(cid, db)


def _hiring_pool(db, gid) -> list[dict]:
    """在招公司池 = 静态公司 + 本群自建公司（同步函数，调用方负责入线程）。

    自建公司必须出现在这里，否则群友永远投递不进去，
    企业金库就只剩「老板自己打卡」这一个来源。
    """
    pool = gd.companies()
    try:
        rows = db.custom_companies_of_group(gid)
    except Exception:  # noqa: BLE001 - 自建公司不可用时不影响正常求职
        rows = []
    for row in rows:
        c = gd.custom_company(db, gd.CUSTOM_BASE + int(row["id"]))
        if c:
            pool.append(c)
    return pool


async def hiring_pool(db, gid) -> list[dict]:
    return await asyncio.to_thread(_hiring_pool, db, gid)


async def find_job(db, gid, uid, nickname, cfg, want: str = ""):
    p = await logic.load_player(db, gid, uid, nickname, cfg)
    if int(p["company"]) != -1:
        return R(err="你已经有工作了，想换工作请使用「跳槽」，不想干了请使用「辞职」")
    if not logic.is_exempt(cfg, uid) and logic.cd_left(p, "job") > 0:
        return R(
            err=f"面试太频繁，休息一下，剩余：{logic.fmt_remaining(logic.cd_left(p, 'job'))}"
        )

    pool = await hiring_pool(db, gid)
    eligible = [c for c in pool if c["min_exp"] <= int(p["exp"])]
    want = (want or "").strip()

    if want == "" and not eligible:
        return R(err="你当前的经验还投不了任何公司，先加班攒攒经验吧")

    if want:
        target = None
        for c in pool:
            if want == c["name"] or want in c["name"] or c["tag"] == want:
                target = c
                break
        if target is None:
            names = "、".join(c["name"] for c in pool)
            return R(err=f"没有叫「{want}」的公司。在招的有：{names}")
        if target not in eligible:
            need = target["min_exp"]
            return R(
                err=(
                    f"「{target['name']}」要求 {need} 点经验，你当前只有 {p['exp']}。"
                    "先去门槛低的公司攒经验吧"
                )
            )
        offer = target
        success_rate = float(logic.cfg_get(cfg, "job_apply_targeted_rate", 0.85))
    else:
        best = max(eligible, key=lambda c: c["salary"])
        best_rate = float(logic.cfg_get(cfg, "job_best_offer_rate", 0.7))
        offer = best if random.random() < best_rate else random.choice(eligible)
        success_rate = float(logic.cfg_get(cfg, "job_apply_auto_rate", 0.92))

    if random.random() > success_rate:
        logic.cd_set(p, "job", float(logic.cfg_get(cfg, "job_cooldown_minutes", 10)) * 60)
        await asyncio.to_thread(db.save_player, p)
        fail_line = logic.pick(gd.t("work", "job_fail"))
        return R(
            tmpl="panel",
            data={
                "icon": "📄",
                "title": "面试失败",
                "accent": "#fc6262",
                "lines": [fail_line],
                "foot": f"当前经验：{p['exp']}｜十分钟后可以再次投递",
            },
            text=f"面试失败：{fail_line}",
        )

    p["company"] = offer["id"]
    pos = gd.position(int(p["lvl"]))
    p["salary"] = logic.salary_of(offer["salary"], pos["mult"])
    logic.cd_set(p, "job", float(logic.cfg_get(cfg, "job_cooldown_minutes", 10)) * 60)
    await asyncio.to_thread(db.save_player, p)
    name = p.get("card") or p["nickname"] or uid
    await asyncio.to_thread(
        db.add_event,
        gid,
        uid,
        "入职",
        f"{name} 入职「{offer['name']}」担任{pos['title']}",
    )
    return R(
        tmpl="panel",
        data={
            "icon": "🎉",
            "title": "Offer 到手！",
            "accent": "#6fe08c",
            "lines": [logic.pick(gd.t("work", "job_offer"))],
            "blocks": [
                {"label": "公司", "value": f"{offer['name']}（{offer['tag']}）"},
                {"label": "职位", "value": pos["title"]},
                {"label": "月薪", "value": f"{logic.fmt_money(p['salary'])} 元"},
                {"label": "公司简介", "value": offer["desc"]},
                {
                    "label": "员工福利",
                    "value": "、".join(offer.get("perks") or []) or "暂无（画饼阶段）",
                },
            ],
            "foot": "发送「上班」开始每日打卡赚钱",
        },
        text=f"入职成功！{offer['name']} · {pos['title']} · 月薪 {logic.fmt_money(p['salary'])} 元",
    )


async def checkin(db, gid, uid, nickname, cfg):
    p = await logic.load_player(db, gid, uid, nickname, cfg)
    if int(p["company"]) == -1:
        return R(err="你目前处于失业状态，先发送「找工作」拿到 Offer 再来打卡吧")

    today = logic.today_str()
    if p["work_day"] == today:
        return R(err="今天已经打过卡了，一天只上一次班（这是打工人的底线）")

    comp = await asyncio.to_thread(_resolve_company, int(p["company"]), db)
    scale = float(logic.cfg_get(cfg, "layoff_scale", 1.0))

    if scale > 0 and logic.weighted_layoff(comp["risk"], scale):
        severance = round(
            float(p["salary"]) * float(logic.cfg_get(cfg, "layoff_severance_rate", 0.3)), 2
        )
        p["company"] = -1
        p["salary"] = 0.0
        p["attend_streak"] = 0
        p["cash"] = round(float(p["cash"]) + severance, 2)
        p["work_day"] = today
        logic.clamp_status(p)
        await asyncio.to_thread(db.save_player, p)
        name = p.get("card") or p["nickname"] or uid
        await asyncio.to_thread(
            db.add_event,
            gid,
            uid,
            "裁员",
            f"{name} 被「{comp['name']}」裁员，获得补偿 {logic.fmt_money(severance)} 元",
        )
        return R(
            tmpl="panel",
            data={
                "icon": "📦",
                "title": "很遗憾，你被优化了",
                "accent": "#fc6262",
                "lines": [logic.pick(gd.t("work", "layoff_texts"))],
                "blocks": [
                    {
                        "label": "离职补偿",
                        "value": f"+{logic.fmt_money(severance)} 元（N+1？不存在的）",
                    },
                    {"label": "当前状态", "value": "失业中，发送「找工作」再就业"},
                ],
            },
            text=f"你被裁员了！获得补偿 {logic.fmt_money(severance)} 元。发送「找工作」再就业。",
        )

    blocks = []
    lines = []

    h = gd.house(int(p["house"]))
    if h["rent"] > 0 and logic.cfg_get(cfg, "rent_auto_deduct", True):
        if float(p["cash"]) >= h["rent"]:
            p["cash"] = round(float(p["cash"]) - h["rent"], 2)
            blocks.append({"label": "今日房租", "value": f"-{h['rent']} 元"})
            lines.append(logic.pick(gd.t("life", "rent_paid")))
            await asyncio.to_thread(
                db.add_transaction, gid, uid, "房租", -h["rent"], h["name"]
            )
        else:
            p["house"] = 0
            p["mind"] = float(p["mind"]) - 10
            h = gd.house(0)
            lines.append(logic.pick(gd.t("life", "rent_failed")))
            blocks.append({"label": "住房变动", "value": f"降级为「{h['name']}」"})

    perf = logic.rf(
        float(logic.cfg_get(cfg, "checkin_perf_min", 0.85)),
        float(logic.cfg_get(cfg, "checkin_perf_max", 1.25)),
    )
    pay = logic.daily_pay(
        float(p["salary"]), perf, int(p["attend_streak"]), cfg=cfg
    )

    commute = gd.commute_mode(str(p.get("commute") or ""))
    commute_mode = str(commute["name"])
    c_cost = float(commute["cost"])
    c_hp, c_mind = float(commute["health"]), float(commute["mind"])
    late = random.random() < float(commute["late_rate"])
    if float(p["cash"]) >= c_cost:
        p["cash"] = round(max(0.0, float(p["cash"]) - c_cost), 2)
        await asyncio.to_thread(
            db.add_transaction, gid, uid, "通勤", -c_cost, commute_mode
        )
    p["health"] = float(p["health"]) + c_hp
    p["mind"] = float(p["mind"]) + c_mind

    if late:
        pay = round(pay * (1 - float(logic.cfg_get(cfg, "late_pay_penalty_rate", 0.2))), 2)
        p["mind"] = float(p["mind"]) - 3
        lines.append(logic.pick(gd.t("work", "commute_late")))

    insurance_rate = float(logic.cfg_get(cfg, "social_insurance_rate", 0.10))
    insurance = round(pay * insurance_rate, 2)
    net_pay = round(pay - insurance, 2)
    p["fund_savings"] = round(float(p.get("fund_savings") or 0) + insurance, 2)
    p["cash"] = round(float(p["cash"]) + net_pay, 2)
    p["total_earned"] = round(float(p.get("total_earned") or 0) + pay, 2)
    p["attend_streak"] = int(p["attend_streak"]) + 1
    p["work_day"] = today
    await asyncio.to_thread(
        db.add_transaction,
        gid,
        uid,
        "薪资",
        net_pay,
        f"基本+绩效{logic.fmt_money(pay)}，五险一金-{logic.fmt_money(insurance)}",
    )

    hp_down = round(
        comp["intensity"] * float(logic.cfg_get(cfg, "work_intensity_health_factor", 0.4)), 1
    )
    mind_down = round(
        comp["intensity"] * float(logic.cfg_get(cfg, "work_intensity_mind_factor", 0.25)), 1
    )
    p["health"] = round(float(p["health"]) - hp_down + h["recover"], 1)
    p["mind"] = round(float(p["mind"]) - mind_down + h["recover"] * 0.5, 1)

    ev = logic.pick(gd.t("work", "checkin_events"))
    ev_cash = ev.get("cash", 0)
    p["cash"] = round(max(0.0, float(p["cash"]) + ev_cash), 2)
    p["health"] = float(p["health"]) + ev.get("health", 0)
    p["mind"] = float(p["mind"]) + ev.get("mind", 0)
    if ev_cash:
        await asyncio.to_thread(
            db.add_transaction, gid, uid, "职场事件", ev_cash, ev["text"][:40]
        )
    exp_gain = logic.ri(
        int(logic.cfg_get(cfg, "checkin_exp_min", 2)),
        int(logic.cfg_get(cfg, "checkin_exp_max", 5)),
    ) + int(ev.get("exp", 0))
    p["exp"] = int(p["exp"]) + exp_gain
    logic.clamp_status(p)
    await asyncio.to_thread(db.save_player, p)

    # 若为群友自建公司，员工打卡按配置比例为企业金库创造营收利润
    profit_rate = float(logic.cfg_get(cfg, "custom_company_profit_rate", 0.15))
    if comp.get("is_custom") and comp.get("custom_id") and profit_rate > 0:
        profit = round(pay * profit_rate, 2)
        await asyncio.to_thread(db.add_custom_company_balance, comp["custom_id"], profit)

    lines.append(ev["text"])
    if random.random() < 0.05:
        lines.append(logic.pick(gd.t("work", "layoff_safe")))
    blocks.extend(
        [
            {
                "label": "今日到账",
                "value": (
                    f"+{logic.fmt_money(net_pay)} 元（绩效 x{perf:.2f}"
                    + ("，迟到8折）" if late else "）")
                ),
            },
            {
                "label": "五险一金",
                "value": f"-{logic.fmt_money(insurance)} → 公积金 {logic.fmt_money(p['fund_savings'])}",
            },
            {
                "label": "通勤",
                "value": f"{commute_mode} -{logic.fmt_money(c_cost)} 元"
                + ("（迟到！）" if late else ""),
            },
            {"label": "连续出勤", "value": f"{p['attend_streak']} 天"},
            {"label": "经验", "value": f"+{exp_gain}（当前 {p['exp']}）"},
            {"label": "健康 / 精神", "value": f"{p['health']} / {p['mind']}"},
        ]
    )
    return R(
        tmpl="panel",
        data={
            "icon": "💼",
            "title": ("打卡成功（迟到了） · " if late else "打卡成功 · ")
            + comp["name"],
            "accent": "#fc6262" if late else "#7fd1ff",
            "subtitle": f"今日职场早报：{gd.news_of_day()}",
            "lines": lines,
            "blocks": blocks,
            "foot": "发送「加班」可额外赚钱，「写周报」每周一次拿绩效奖",
        },
        text=(
            f"打卡成功！实发 {logic.fmt_money(net_pay)} 元"
            + (f"（迟到，按 {(1 - float(logic.cfg_get(cfg, 'late_pay_penalty_rate', 0.2))) * 100:g}% 计薪）" if late else "")
            + f"｜五险一金 -{logic.fmt_money(insurance)}｜健康 {p['health']}｜精神 {p['mind']}\n{ev['text']}"
        ),
    )


async def slack(db, gid, uid, nickname, cfg):
    p = await logic.load_player(db, gid, uid, nickname, cfg)
    if int(p["company"]) == -1:
        return R(err="失业的人摸什么鱼，先找工作！")
    cd = float(logic.cfg_get(cfg, "slack_cooldown_minutes", 60)) * 60
    if not logic.is_exempt(cfg, uid) and logic.cd_left(p, "slack") > 0:
        return R(
            err=f"鱼都让你摸秃了，冷却中：{logic.fmt_remaining(logic.cd_left(p, 'slack'))}"
        )
    logic.cd_set(p, "slack", cd)

    # 护盾仅在真正抵挡时消耗（get 探测，未触发保留）；拉屎卡必触发直接消耗
    cds = p.setdefault("_cds", {})
    shield = cds.get("shield_active")
    poop = cds.pop("poop_active", None)

    caught_prob = (
        0.0 if poop else float(logic.cfg_get(cfg, "slack_caught_rate", 0.15))
    )
    if random.random() < caught_prob:
        if shield:
            cds.pop("shield_active", None)
            await asyncio.to_thread(db.save_player, p)
            return R(
                tmpl="panel",
                data={
                    "icon": "🛡️",
                    "title": "摸鱼被抓 · 护盾生效！",
                    "accent": "#ffd86f",
                    "lines": ["HR 突然巡视，你装配的【防甩锅护盾】瞬间抵挡了一切罚款！"],
                    "blocks": [
                        {"label": "护盾状态", "value": "已消耗 1 层"},
                        {"label": "罚款减免", "value": "100%"},
                    ],
                },
                text="摸鱼被抓！但你的【防甩锅护盾】生效，免除了罚款！",
            )
        fine = max(
            float(logic.cfg_get(cfg, "slack_fine_min", 10.0)),
            round(
                float(p["salary"])
                / logic.workdays(cfg)
                * float(logic.cfg_get(cfg, "slack_fine_rate", 0.5)),
                2,
            ),
        )
        p["cash"] = round(max(0.0, float(p["cash"]) - fine), 2)
        p["mind"] = float(p["mind"]) - 5
        logic.clamp_status(p)
        await asyncio.to_thread(db.save_player, p)
        line = logic.pick(gd.t("work", "slack_caught"))
        return R(
            tmpl="panel",
            data={
                "icon": "🚨",
                "title": "摸鱼被抓！",
                "accent": "#fc6262",
                "lines": [line],
                "blocks": [
                    {"label": "罚款", "value": f"-{logic.fmt_money(fine)} 元"},
                    {"label": "精神", "value": f"-5（当前 {p['mind']}）"},
                    {"label": "现金", "value": f"{logic.fmt_money(p['cash'])} 元"},
                ],
            },
            text=f"摸鱼被抓！罚款 {logic.fmt_money(fine)} 元：{line}",
        )

    lo = int(logic.cfg_get(cfg, "slack_mind_min", 8))
    hi = int(logic.cfg_get(cfg, "slack_mind_max", 15))
    gain = (logic.ri(lo, hi) * 2) if poop else logic.ri(lo, hi)
    p["mind"] = round(float(p["mind"]) + gain, 1)
    p["exp"] = int(p["exp"]) + logic.ri(0, 1)
    logic.clamp_status(p)
    await asyncio.to_thread(db.save_player, p)
    line = logic.pick(gd.t("work", "slack_ok"))
    return R(
        tmpl="panel",
        data={
            "icon": "🐟",
            "title": "摸鱼成功",
            "accent": "#6fe08c",
            "lines": [line],
            "blocks": [
                {"label": "精神恢复", "value": f"+{gain}（当前 {p['mind']} / 100）"}
            ],
        },
        text=f"摸鱼成功！精神 +{gain}（当前 {p['mind']}）：{line}",
    )



async def overtime(db, gid, uid, nickname, cfg):
    p = await logic.load_player(db, gid, uid, nickname, cfg)
    if int(p["company"]) == -1:
        return R(err="你都没有公司给你加班，真让人羡慕")
    cd = float(logic.cfg_get(cfg, "overtime_cooldown_hours", 3)) * 3600
    if not logic.is_exempt(cfg, uid) and logic.cd_left(p, "ot") > 0:
        return R(
            err=f"身体是革命的本钱，休息够再来：剩余 {logic.fmt_remaining(logic.cd_left(p, 'ot'))}"
        )
    logic.cd_set(p, "ot", cd)

    ev = logic.pick(gd.t("work", "overtime_events"))
    # 技能加成：每掌握一门技能，加班收益 +2%
    per_skill = float(logic.cfg_get(cfg, "skill_overtime_bonus_rate", 0.02))
    skill_bonus = 1 + per_skill * len(p.get("_skills", []) or [])
    pay = round(
        float(p["salary"])
        / logic.workdays(cfg)
        * logic.rf(
            float(logic.cfg_get(cfg, "overtime_pay_min_rate", 0.5)),
            float(logic.cfg_get(cfg, "overtime_pay_max_rate", 1.1)),
        )
        * skill_bonus,
        2,
    )
    p["cash"] = round(float(p["cash"]) + pay, 2)
    p["total_earned"] = round(float(p.get("total_earned") or 0) + pay, 2)
    p["health"] = float(p["health"]) + ev.get("health", -8)
    p["mind"] = float(p["mind"]) + ev.get("mind", -4)
    exp_gain = int(ev.get("exp", 4)) + logic.ri(2, 6)
    p["exp"] = int(p["exp"]) + exp_gain
    await asyncio.to_thread(
        db.add_transaction, gid, uid, "加班费", pay, ev["text"][:40]
    )

    got_comp_leave = False
    if random.random() < float(logic.cfg_get(cfg, "overtime_comp_leave_rate", 0.2)):
        p["comp_leave"] = int(p.get("comp_leave") or 0) + 1
        got_comp_leave = True

    hospitalized = False
    threshold = int(logic.cfg_get(cfg, "hospital_threshold", 15))
    extra_lines = []
    medical = 0.0
    if float(p["health"]) < threshold and random.random() < float(
        logic.cfg_get(cfg, "hospital_rate", 0.35)
    ):
        hospitalized = True
        medical = round(min(3000.0, max(200.0, float(p["cash"]) * 0.25)), 2)
        p["cash"] = round(max(0.0, float(p["cash"]) - medical), 2)
        p["health"] = 45.0
        p["mind"] = float(p["mind"]) - 10
        extra_lines.append(logic.pick(gd.t("work", "hospital_texts")))
    logic.clamp_status(p)
    await asyncio.to_thread(db.save_player, p)
    name = p.get("card") or p["nickname"] or uid
    if hospitalized:
        await asyncio.to_thread(
            db.add_event,
            gid,
            uid,
            "住院",
            f"{name} 加班过度被送医，医疗费 {logic.fmt_money(medical)} 元",
        )

    blocks = [
        {"label": "加班费", "value": f"+{logic.fmt_money(pay)} 元"},
        {"label": "经验", "value": f"+{exp_gain}（当前 {p['exp']}）"},
        {"label": "健康", "value": f"{p['health']} / 100"},
        {"label": "精神", "value": f"{p['mind']} / 100"},
    ]
    if got_comp_leave:
        blocks.append({"label": "调休券", "value": f"+1（持有 {p['comp_leave']} 张）"})
    if hospitalized:
        blocks.insert(
            1, {"label": "医疗费", "value": f"-{logic.fmt_money(medical)} 元"}
        )
    title = "深夜医院见" if hospitalized else "加班完成"
    icon = "🏥" if hospitalized else "🌙"
    accent = "#fc6262" if hospitalized else "#ffd86f"
    return R(
        tmpl="panel",
        data={
            "icon": icon,
            "title": title,
            "accent": accent,
            "lines": [ev["text"], *extra_lines],
            "blocks": blocks,
            "foot": "注意身体，健康低于警戒线再加班可能住院"
            if not hospitalized
            else "医生建议：少加班",
        },
        text=f"{'住院了！医疗费 -' + logic.fmt_money(medical) + ' 元' if hospitalized else '加班完成！'} 加班费 +{logic.fmt_money(pay)} 元\n{ev['text']}",
    )


async def take_leave(db, gid, uid, nickname, cfg):
    p = await logic.load_player(db, gid, uid, nickname, cfg)
    if int(p["company"]) == -1:
        return R(err="无业游民不需要请假，你天天都在放假")
    week = logic.yearweek_str()
    if p["leave_week"] != week:
        p["leave_week"] = week
        p["leave_count"] = 0
    limit = int(logic.cfg_get(cfg, "weekly_leave_limit", 2))
    if int(p["leave_count"]) >= limit:
        return R(err=f"本周 {limit} 次请假额度已用完，全勤奖它不香吗")
    p["leave_count"] = int(p["leave_count"]) + 1
    p["attend_streak"] = 0
    p["mind"] = round(float(p["mind"]) + float(logic.cfg_get(cfg, "leave_mind_gain", 15)), 1)
    p["health"] = round(
        float(p["health"]) + float(logic.cfg_get(cfg, "leave_health_gain", 8)), 1
    )
    logic.clamp_status(p)
    await asyncio.to_thread(db.save_player, p)
    line = logic.pick(gd.t("work", "leave_texts"))
    return R(
        tmpl="panel",
        data={
            "icon": "🌴",
            "title": "请假成功",
            "accent": "#6fe08c",
            "lines": [line],
            "blocks": [
                {"label": "今日薪资", "value": "0 元（请假无薪）"},
                {"label": "精神", "value": f"+15（当前 {p['mind']}）"},
                {"label": "健康", "value": f"+8（当前 {p['health']}）"},
                {
                    "label": "本周剩余额度",
                    "value": f"{limit - int(p['leave_count'])} 次",
                },
            ],
            "foot": "连续出勤已中断，明天记得重新打卡",
        },
        text=f"请假成功！精神+15 健康+8。{line}",
    )



async def promote(db, gid, uid, nickname, cfg):
    p = await logic.load_player(db, gid, uid, nickname, cfg)
    if int(p["company"]) == -1:
        return R(err="失业状态无法晋升，先找工作吧")
    pos_list = gd.positions()
    if int(p["lvl"]) >= len(pos_list) - 1:
        return R(err="你已经是最高的「合伙人·打工皇帝」，再升就要收购公司了")
    nxt = pos_list[int(p["lvl"]) + 1]
    if int(p["exp"]) < nxt["need"]:
        return R(
            err=f"晋升到「{nxt['title']}」需要 {nxt['need']} 点经验，当前 {p['exp']}，多上班多加班攒经验吧"
        )
    cost = float(nxt["cost"])
    if float(p["cash"]) < cost:
        return R(
            err=f"请部门喝奶茶（晋升打点费）需要 {logic.fmt_money(cost)} 元，余额不足"
        )

    rate = logic.promote_rate(
        int(p["lvl"]),
        float(logic.cfg_get(cfg, "promote_base_rate", 0.85)),
        float(logic.cfg_get(cfg, "promote_decay", 0.06)),
    )
    # 技能加成：每掌握一门技能，晋升成功率 +3%（上限 95%）
    rate = min(
        float(logic.cfg_get(cfg, "promote_max_rate", 0.95)),
        rate
        + float(logic.cfg_get(cfg, "skill_promote_bonus_rate", 0.03))
        * len(p.get("_skills", []) or []),
    )
    comp = await asyncio.to_thread(_resolve_company, int(p["company"]), db)
    if random.random() < rate:
        p["lvl"] = int(p["lvl"]) + 1
        new_pos = gd.position(int(p["lvl"]))
        p["salary"] = logic.salary_of(comp["salary"], new_pos["mult"])
        p["cash"] = round(float(p["cash"]) - cost, 2)
        p["promote_count"] = int(p.get("promote_count") or 0) + 1
        await asyncio.to_thread(db.save_player, p)
        name = p.get("card") or p["nickname"] or uid
        await asyncio.to_thread(
            db.add_event,
            gid,
            uid,
            "晋升",
            f"{name} 晋升为「{new_pos['title']}」，月薪 {logic.fmt_money(p['salary'])}",
        )
        return R(
            tmpl="panel",
            data={
                "icon": "🚀",
                "title": f"恭喜晋升「{new_pos['title']}」",
                "accent": "#ffd86f",
                "lines": [logic.pick(gd.t("work", "promote_ok"))],
                "blocks": [
                    {"label": "打点费", "value": f"-{logic.fmt_money(cost)} 元"},
                    {"label": "新月薪", "value": f"{logic.fmt_money(p['salary'])} 元"},
                    {
                        "label": "下次晋升",
                        "value": (
                            f"需 {pos_list[p['lvl'] + 1]['need']} 经验"
                            if p["lvl"] + 1 < len(pos_list)
                            else "已是巅峰"
                        ),
                    },
                ],
            },
            text=f"晋升成功！现在是「{new_pos['title']}」，月薪 {logic.fmt_money(p['salary'])} 元",
        )
    refund_rate = float(logic.cfg_get(cfg, "promote_fail_refund_rate", 0.5))
    lost = round(cost * (1 - refund_rate), 2)
    p["cash"] = round(max(0.0, float(p["cash"]) - lost), 2)
    p["mind"] = float(p["mind"]) - 8
    logic.clamp_status(p)
    await asyncio.to_thread(db.save_player, p)
    return R(
        tmpl="panel",
        data={
            "icon": "😞",
            "title": "晋升失败",
            "accent": "#fc6262",
            "lines": [logic.pick(gd.t("work", "promote_fail"))],
            "blocks": [
                {"label": "本次成功率", "value": f"{rate * 100:.0f}%"},
                {
                    "label": f"打点费（退 {refund_rate * 100:g}%）",
                    "value": f"-{logic.fmt_money(lost)} 元",
                },
                {"label": "精神", "value": f"{p['mind']} / 100"},
            ],
        },
        text=f"晋升失败（成功率 {rate * 100:.0f}%）：{logic.pick(gd.t('work', 'promote_fail'))}",
    )


async def resign_job(db, gid, uid, nickname, cfg):
    p = await logic.load_player(db, gid, uid, nickname, cfg)
    if int(p["company"]) == -1:
        return R(err="你本来就没有工作，无需辞职")
    comp = await asyncio.to_thread(_resolve_company, int(p["company"]), db)
    comp_name = comp["name"] if comp else "未知企业"
    p["company"] = -1
    p["salary"] = 0.0
    p["attend_streak"] = 0
    p["mind"] = round(float(p["mind"]) + 10, 1)
    logic.clamp_status(p)
    await asyncio.to_thread(db.save_player, p)
    name = p.get("card") or p["nickname"] or uid
    await asyncio.to_thread(
        db.add_event, gid, uid, "离职", f"{name} 从「{comp_name}」裸辞"
    )
    return R(
        tmpl="panel",
        data={
            "icon": "✈️",
            "title": "裸辞快乐！",
            "accent": "#6fe08c",
            "lines": [logic.pick(gd.t("work", "resign_texts"))],
            "blocks": [
                {"label": "前公司", "value": comp_name},
                {"label": "精神", "value": f"+10（当前 {p['mind']}）"},
                {"label": "提醒", "value": "没有收入了，存款和基金还在"},
            ],
        },
        text=f"已从「{comp_name}」辞职。发送「找工作」开启下一段打工生涯",
    )


async def job_hop(db, gid, uid, nickname, cfg):
    p = await logic.load_player(db, gid, uid, nickname, cfg)
    if int(p["company"]) == -1:
        return R(err="你都失业了还跳什么槽，先「找工作」")
    cd_key = "hop"
    if not logic.is_exempt(cfg, uid) and logic.cd_left(p, cd_key) > 0:
        return R(
            err=f"骑驴找马也别太频繁，冷却中：{logic.fmt_remaining(logic.cd_left(p, cd_key))}"
        )
    cur_id = int(p["company"])
    pool = await hiring_pool(db, gid)
    eligible = [
        c for c in pool if c["min_exp"] <= int(p["exp"]) and c["id"] != cur_id
    ]
    if not eligible:
        return R(
            err="你的经验已经登顶所有公司，没有更好的去处了（宇宙大厂在向你招手？）"
        )
    best = max(eligible, key=lambda c: c["salary"])
    target = (
        best
        if random.random() < float(logic.cfg_get(cfg, "job_best_offer_rate", 0.7))
        else random.choice(eligible)
    )

    hop_cd = float(logic.cfg_get(cfg, "hop_cooldown_hours", 1)) * 3600
    if random.random() > float(logic.cfg_get(cfg, "job_hop_success_rate", 0.75)):
        logic.cd_set(p, cd_key, hop_cd)
        await asyncio.to_thread(db.save_player, p)
        return R(
            tmpl="panel",
            data={
                "icon": "🙃",
                "title": "跳槽失败",
                "accent": "#fc6262",
                "lines": [logic.pick(gd.t("work", "hop_fail"))],
                "foot": "一小时后可再次尝试，驴还得继续骑",
            },
            text=f"跳槽失败：{logic.pick(gd.t('work', 'hop_fail'))}",
        )

    old_comp_obj = await asyncio.to_thread(_resolve_company, cur_id, db)
    old_comp = old_comp_obj["name"] if old_comp_obj else "原公司"
    p["company"] = target["id"]
    pos = gd.position(int(p["lvl"]))
    p["salary"] = logic.salary_of(target["salary"], pos["mult"])
    logic.cd_set(p, cd_key, hop_cd)
    await asyncio.to_thread(db.save_player, p)
    name = p.get("card") or p["nickname"] or uid
    await asyncio.to_thread(
        db.add_event,
        gid,
        uid,
        "跳槽",
        f"{name} 从「{old_comp}」跳槽至「{target['name']}」",
    )
    return R(
        tmpl="panel",
        data={
            "icon": "🐎",
            "title": "跳槽成功！",
            "accent": "#ffd86f",
            "lines": [logic.pick(gd.t("work", "hop_ok"))],
            "blocks": [
                {"label": "原公司", "value": old_comp},
                {"label": "新公司", "value": f"{target['name']}（{target['tag']}）"},
                {
                    "label": "新月薪",
                    "value": f"{logic.fmt_money(p['salary'])} 元（职级不变：{pos['title']}）",
                },
            ],
        },
        text=f"跳槽成功！{old_comp} → {target['name']}，月薪 {logic.fmt_money(p['salary'])} 元",
    )


async def write_report(db, gid, uid, nickname, cfg):
    p = await logic.load_player(db, gid, uid, nickname, cfg)
    if int(p["company"]) == -1:
        return R(err="失业人士不用写周报，这是打工人才有的浪漫")
    if not logic.is_exempt(cfg, uid) and logic.cd_left(p, "report") > 0:
        return R(
            err=f"周报刚交过，下次可写还要等 {logic.fmt_remaining(logic.cd_left(p, 'report'))}，好好搬砖"
        )

    bonus_rate = random.random()
    exp_gain = logic.ri(3, 8)
    s_threshold = float(logic.cfg_get(cfg, "report_s_threshold", 0.85))
    bonus = round(
        float(p["salary"])
        / logic.workdays(cfg)
        * float(logic.cfg_get(cfg, "report_bonus_rate", 0.3))
        * (2.0 if bonus_rate > s_threshold else 1.0),
        2,
    )
    caught = random.random() < float(logic.cfg_get(cfg, "report_fail_rate", 0.12))

    lines = []
    if caught:
        p["cash"] = round(max(0.0, float(p["cash"]) - 50), 2)
        p["mind"] = float(p["mind"]) - 5
        await asyncio.to_thread(
            db.add_transaction, gid, uid, "周报", -50, "敷衍了事被领导识破"
        )
        result_text = logic.pick(gd.t("work", "weeklyreport_fail"))
        title, accent, icon = "周报被打回", "#fc6262", "📄"
        blocks = [{"label": "罚款", "value": "-50 元（态度问题）"}]
        lines.append(result_text)
    else:
        p["cash"] = round(float(p["cash"]) + bonus, 2)
        p["total_earned"] = round(float(p.get("total_earned") or 0) + bonus, 2)
        grade = "S" if bonus_rate > s_threshold else ("A" if bonus_rate > 0.5 else "B")
        result_text = logic.pick(gd.t("work", "weeklyreport_ok"))
        await asyncio.to_thread(
            db.add_transaction, gid, uid, "周报绩效", bonus, f"评级 {grade}"
        )
        title, accent, icon = f"周报评级 {grade}", "#6fe08c", "📝"
        blocks = [
            {"label": "绩效奖金", "value": f"+{logic.fmt_money(bonus)} 元"},
            {"label": "经验", "value": f"+{exp_gain}（当前 {p['exp']}）"},
        ]
        lines.append(result_text)

    p["exp"] = int(p["exp"]) + exp_gain
    logic.cd_set(
        p, "report", float(logic.cfg_get(cfg, "report_cooldown_days", 7)) * 86400
    )
    logic.clamp_status(p)
    await asyncio.to_thread(db.save_player, p)
    return R(
        tmpl="panel",
        data={
            "icon": icon,
            "title": title,
            "accent": accent,
            "lines": ["你熬了一个小时写的周报：", *lines],
            "blocks": blocks,
            "foot": "下周同一时间，继续汇报你在工位上的一举一动",
        },
        text=f"{title}！{result_text}",
    )


async def take_comp_leave(db, gid, uid, nickname, cfg):
    p = await logic.load_player(db, gid, uid, nickname, cfg)
    if int(p["company"]) == -1:
        return R(err="失业人士没有调休一说，你每天都在休假")
    if int(p.get("comp_leave") or 0) <= 0:
        rate = float(logic.cfg_get(cfg, "overtime_comp_leave_rate", 0.2))
        return R(err=f"你没有调休券。多发一次「加班」，有 {rate * 100:g}% 概率获得一张")
    today = logic.today_str()
    if p["work_day"] == today:
        return R(err="今天已经打过卡了，今天没法请调休啦")
    p["comp_leave"] = int(p["comp_leave"]) - 1
    pay = logic.daily_pay(float(p["salary"]), 1.0, int(p["attend_streak"]), cfg=cfg)
    insurance = round(pay * float(logic.cfg_get(cfg, "social_insurance_rate", 0.10)), 2)
    net_pay = round(pay - insurance, 2)
    p["fund_savings"] = round(float(p.get("fund_savings") or 0) + insurance, 2)
    p["cash"] = round(float(p["cash"]) + net_pay, 2)
    p["total_earned"] = round(float(p.get("total_earned") or 0) + pay, 2)
    p["mind"] = round(float(p["mind"]) + 15, 1)
    p["health"] = round(float(p["health"]) + 8, 1)
    p["work_day"] = today
    logic.clamp_status(p)
    await asyncio.to_thread(db.save_player, p)
    await asyncio.to_thread(
        db.add_transaction, gid, uid, "带薪调休", net_pay, "用调休券休息一天，工资照发"
    )
    return R(
        tmpl="panel",
        data={
            "icon": "🎫",
            "title": "带薪调休成功！",
            "accent": "#6fe08c",
            "lines": ["你用调休券换来了一个带薪的躺平日，工资照发，全勤不断"],
            "blocks": [
                {"label": "今日到账", "value": f"+{logic.fmt_money(net_pay)} 元"},
                {"label": "剩余调休券", "value": f"{p['comp_leave']} 张"},
                {"label": "精神", "value": f"+15（当前 {p['mind']}）"},
                {"label": "健康", "value": f"+8（当前 {p['health']}）"},
            ],
        },
        text=f"带薪调休成功！到账 {logic.fmt_money(net_pay)} 元，剩余调休券 {p['comp_leave']} 张",
    )


async def negotiate_salary(db, gid, uid, nickname, cfg):
    """和公司谈加薪：成功率与经验、职级挂钩。"""
    p = await logic.load_player(db, gid, uid, nickname, cfg)
    if int(p["company"]) == -1:
        return R(err="和谁谈？先找到一份工作再说")
    if not logic.is_exempt(cfg, uid) and logic.cd_left(p, "negotiate") > 0:
        return R(
            err=f"刚谈崩没多久，别急着再进办公室：剩余 {logic.fmt_remaining(logic.cd_left(p, 'negotiate'))}"
        )
    logic.cd_set(
        p, "negotiate", float(logic.cfg_get(cfg, "negotiate_cooldown_days", 7)) * 86400
    )

    pos_list = gd.positions()
    nxt = pos_list[int(p["lvl"]) + 1] if int(p["lvl"]) + 1 < len(pos_list) else None
    benchmark = max(100, nxt["need"] if nxt else 500)
    rate = min(
        float(logic.cfg_get(cfg, "negotiate_max_rate", 0.75)),
        float(logic.cfg_get(cfg, "negotiate_base_rate", 0.25))
        + int(p["exp"]) / (benchmark * 1.5),
    )
    comp = await asyncio.to_thread(_resolve_company, int(p["company"]), db)

    if random.random() < rate:
        pct = logic.rf(
            float(logic.cfg_get(cfg, "negotiate_raise_min_rate", 0.05)),
            float(logic.cfg_get(cfg, "negotiate_raise_max_rate", 0.15)),
        )
        old_salary = float(p["salary"])
        p["salary"] = round(old_salary * (1 + pct), 0)
        p["mind"] = round(float(p["mind"]) + 6, 1)
        gain = round(p["salary"] - old_salary, 0)
        logic.clamp_status(p)
        await asyncio.to_thread(db.save_player, p)
        name = p.get("card") or p["nickname"] or uid
        await asyncio.to_thread(
            db.add_event,
            gid,
            uid,
            "加薪",
            f"{name} 谈薪成功，月薪 {logic.fmt_money(old_salary)} -> {logic.fmt_money(p['salary'])}",
        )
        line = logic.pick(gd.t("company", "negotiation_ok"))
        return R(
            tmpl="panel",
            data={
                "icon": "📈",
                "title": "加薪谈判成功！",
                "accent": "#6fe08c",
                "lines": [line],
                "blocks": [
                    {"label": "本次成功率", "value": f"{rate * 100:.0f}%"},
                    {
                        "label": "月薪变化",
                        "value": f"{logic.fmt_money(old_salary)} -> {logic.fmt_money(p['salary'])}（+{logic.fmt_money(gain)}）",
                    },
                    {"label": "精神", "value": f"+6（当前 {p['mind']}）"},
                ],
                "foot": f"在「{comp['name']}」的底气又足了一分",
            },
            text=f"加薪成功！月薪 {logic.fmt_money(old_salary)} -> {logic.fmt_money(p['salary'])} 元",
        )

    p["mind"] = round(float(p["mind"]) - 8, 1)
    logic.clamp_status(p)
    await asyncio.to_thread(db.save_player, p)
    line = logic.pick(gd.t("company", "negotiation_fail"))
    return R(
        tmpl="panel",
        data={
            "icon": "🥾",
            "title": "谈判失败",
            "accent": "#fc6262",
            "lines": [line],
            "blocks": [
                {"label": "本次成功率", "value": f"{rate * 100:.0f}%"},
                {"label": "精神", "value": f"-8（当前 {p['mind']}）"},
                {"label": "建议", "value": "多攒经验多加班，下次带着成绩单再去"},
            ],
        },
        text=f"加薪失败（成功率{rate * 100:.0f}%）：{line}",
    )


async def my_company(db, gid, uid, nickname, cfg):
    """查看当前雇主公司详情。"""
    p = await logic.load_player(db, gid, uid, nickname, cfg)
    n_comp = len(gd.companies())
    if int(p["company"]) == -1:
        return R(
            tmpl="panel",
            data={
                "icon": "🧳",
                "title": "你目前处于失业状态",
                "accent": "#fc6262",
                "lines": [
                    f"插件里有 {n_comp} 家公司在招人：从快餐店到宇宙大厂。",
                    "经验越高，能面进门槛越高的公司，月薪也越高。",
                ],
                "foot": "发送「找工作」投递简历；发送「我的简历」查看自身条件",
            },
            text=f"你目前失业中。发送「找工作」开始求职（{n_comp} 家公司可选，门槛看经验）",
        )

    comp = await asyncio.to_thread(_resolve_company, int(p["company"]), db)
    pos = gd.position(int(p["lvl"]))
    pos_list = gd.positions()
    nxt = pos_list[int(p["lvl"]) + 1] if int(p["lvl"]) + 1 < len(pos_list) else None
    today = logic.today_str()
    perks = comp.get("perks") or []
    today_perk = (
        random.Random(f"{today}-{comp['id']}").choice(perks) if perks else "暂无"
    )
    checked = p["work_day"] == today
    commute = gd.commute_mode(str(p.get("commute") or ""))
    mode, c_cost, late_r = (
        str(commute["name"]),
        float(commute["cost"]),
        float(commute["late_rate"]),
    )

    lines = [
        f"公司简介：{comp['desc']}",
        f"今日员工福利：{today_perk}",
        (
            "今天已打卡 ✓"
            if checked
            else "今天还没打卡，日薪约 "
            + logic.fmt_money(
                logic.daily_pay(
                    float(p["salary"]), 1.0, int(p["attend_streak"]), cfg=cfg
                )
            )
            + " 元"
        ),
    ]
    blocks = [
        {"label": "公司", "value": f"{comp['name']}（{comp['tag']}）"},
        {
            "label": "你的职位",
            "value": f"{pos['title']}｜月薪 {logic.fmt_money(p['salary'])} 元",
        },
        {
            "label": "工作强度",
            "value": f"每日健康 -{round(comp['intensity'] * 0.4, 1)}",
        },
        {"label": "裁员风险", "value": f"{comp['risk'] * 100:.1f}%/天"},
        {"label": "连续出勤", "value": f"{p['attend_streak']} 天（有全勤加成）"},
        {
            "label": "通勤",
            "value": f"{mode} 单程 {logic.fmt_money(c_cost)} 元｜迟到率 {int(late_r * 100)}%",
        },
    ]
    if nxt:
        blocks.append(
            {
                "label": "晋升目标",
                "value": f"{nxt['title']}（需 {nxt['need']} 经验 + {logic.fmt_money(nxt['cost'])} 打点费）",
            }
        )
    return R(
        tmpl="panel",
        data={
            "icon": "🏢",
            "title": f"我的公司 · {comp['name']}",
            "accent": "#7fd1ff",
            "lines": lines,
            "blocks": blocks,
            "foot": "日常：上班 / 加班 / 摸鱼 / 写周报 · 进阶：晋升 / 谈薪 / 跳槽 / 辞职",
        },
        text=(
            f"当前雇主：{comp['name']}（{pos['title']}，月薪 {logic.fmt_money(p['salary'])} 元）｜"
            f"{'今日已打卡' if checked else '今日未打卡'}"
        ),
    )



async def create_company(db, gid, uid, nickname, comp_name, cfg):
    """创业自建公司：身价达标且消耗启动资金。"""
    p = await logic.load_player(db, gid, uid, nickname, cfg)
    comp_name = (comp_name or "").strip()
    if not comp_name:
        return R(err="请输入公司名称，例如：「创建公司 赛博科技」或「创业 星芒游戏」")
    max_len = int(logic.cfg_get(cfg, "company_name_max_len", 15))
    if len(comp_name) > max_len:
        return R(err=f"公司名称过长（最多{max_len}个字）")

    # 检查是否已是老板或已有公司
    row = await asyncio.to_thread(db.get_custom_company_by_boss, gid, uid)

    if row:
        return R(err=f"你已经创立了公司「{row['name']}」，当老板要有定力！发送「公司分红」领取利润")

    # 门槛：职级 >= 10 (VP/合伙人) 或 身价 >= min_val，且启动资金 cost 元
    cost = float(logic.cfg_get(cfg, "create_company_cost", 30000.0))
    min_val = float(logic.cfg_get(cfg, "create_company_min_value", 50000.0))
    min_lvl = int(logic.cfg_get(cfg, "create_company_min_level", 10))
    base_salary = float(logic.cfg_get(cfg, "custom_company_base_salary", 6000.0))
    init_balance = float(logic.cfg_get(cfg, "custom_company_init_balance", 10000.0))
    value_bonus = float(logic.cfg_get(cfg, "create_company_value_bonus", 20000.0))
    if int(p["lvl"]) < min_lvl and float(p["value"]) < min_val:
        return R(err=f"创业门槛极高！需要职级达到 VP/合伙人，或职场身价超过 {logic.fmt_money(min_val)} 元，打铁还需自身硬！")
    if float(p["cash"]) < cost:
        return R(err=f"注册公司需要 {logic.fmt_money(cost)} 元启动验资资金，当前现金不足")

    # 先建公司再扣钱：注册失败就没有钱可退，也不会留下「已扣款但无公司」的中间态。
    # create_custom_company_if_free 自带「一人一司」竞态保护。
    cid = await asyncio.to_thread(
        db.create_custom_company_if_free,
        str(gid),
        str(uid),
        comp_name,
        "自建企业",
        base_salary,
        init_balance,
    )
    if not cid:
        return R(err="你已经创立了公司，当老板要有定力！发送「公司分红」领取利润")

    # 条件扣款：余额不足时不产生负资产。失败则把刚建的公司撤掉，保持一致。
    ok = await asyncio.to_thread(db.try_debit_cash, gid, uid, cost)
    if not ok:
        await asyncio.to_thread(db.delete_custom_company, cid)
        return R(err=f"注册公司需要 {logic.fmt_money(cost)} 元启动验资资金，当前现金不足")
    await asyncio.to_thread(
        db.add_transaction, gid, uid, "创业注册资金", -cost, f"创立公司 {comp_name}"
    )

    # 老板挂职自建公司：company / salary 必须同时写，
    # 否则 salary 留在 0，daily_pay 永远发 0 元，企业金库也永远进 0。
    # 注意：扣款已由 try_debit_cash 在库内完成，这里绝不能再动 p["cash"]，
    # 否则 save_player 的增量写回会把同一笔钱扣第二次。
    p["value"] = round(float(p["value"]) + value_bonus, 2)
    p["company"] = gd.CUSTOM_BASE + cid
    p["salary"] = logic.salary_of(base_salary, gd.position(int(p["lvl"]))["mult"])
    await asyncio.to_thread(db.save_player, p)

    await asyncio.to_thread(
        db.add_event, gid, uid, "创业", f"{p['nickname'] or uid} 豪掷千金创立了「{comp_name}」，正式晋升为资本家/大老板！"
    )
    return R(
        tmpl="panel",
        data={
            "icon": "👑",
            "title": "🎉 创业成功 · 公司成立！",
            "accent": "#ffd86f",
            "lines": [
                f"恭喜 {p['nickname'] or uid} 晋升为大老板！「{comp_name}」正式开门营业！",
                "群内员工每次打卡都将为公司带来利润，发送「公司分红」即可提取企业营收分红！",
            ],
            "blocks": [
                {"label": "公司名称", "value": comp_name},
                {"label": "注册资金", "value": f"-{logic.fmt_money(cost)} 元"},
                {"label": "你的月薪", "value": f"{logic.fmt_money(p['salary'])} 元"},
                {
                    "label": "身价暴涨",
                    "value": f"+{logic.fmt_money(value_bonus)}（当前 {logic.fmt_money(p['value'])}）",
                },
                {"label": "企业金库", "value": f"{logic.fmt_money(init_balance)} 元"},
            ],
            "foot": "老板指令：发送「公司分红」提现；群友可「找工作 公司名」投递入职",
        },
        text=f"👑 恭喜创业成功！你创立了「{comp_name}」，身价暴涨 {logic.fmt_money(value_bonus)} 元！",
    )


async def company_dividend(db, gid, uid, nickname, cfg):
    """老板提取公司利润分红。"""
    p = await logic.load_player(db, gid, uid, nickname, cfg)
    row_data, dividend, status = await asyncio.to_thread(
        db.withdraw_custom_company_dividend, str(gid), str(uid)
    )
    if status == "not_boss":
        return R(err="你还不是老板，发送「创建公司 公司名」开启创业当老板！")
    if status == "zero_balance":
        return R(err=f"公司「{row_data['name']}」金库暂无可分红资金，员工努力搬砖中...")

    # 金库已在库内原子清零，入账必须同样走原子列更新：
    # 若这里改走「快照 + 全列覆盖」，一旦写回丢失，钱就凭空消失且无法追回。
    await asyncio.to_thread(db.credit_income, gid, uid, float(dividend))
    await asyncio.to_thread(db.add_transaction, gid, uid, "企业分红", dividend, f"来自 {row_data['name']}")
    p = await asyncio.to_thread(db.get_player, gid, uid)

    return R(
        tmpl="panel",
        data={
            "icon": "💰",
            "title": f"企业分红到账 · {row_data['name']}",
            "accent": "#6fe08c",
            "lines": [f"公司运营良好，本次分红 {logic.fmt_money(dividend)} 元已存入个人现金！"],
            "blocks": [
                {"label": "分红金额", "value": f"+{logic.fmt_money(dividend)} 元"},
                {"label": "当前现金", "value": f"{logic.fmt_money(p['cash'])} 元"},
                {"label": "金库剩余", "value": "0.00 元"},
            ],
            "foot": "资本家的快乐就是这么简单朴素",
        },
        text=f"💰 公司分红成功！已提现 {logic.fmt_money(dividend)} 元至个人现金！",
    )


