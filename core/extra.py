"""扩展玩法：年终奖、技能、职场社交、副业升级、年假、职场八卦。"""

import asyncio
import random
import time

from . import db as db_module
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
    # 跨年自动重置年假额度
    year = time.strftime("%Y")
    if p.get("annual_year") != year:
        p["annual_year"] = year
        p["annual_leave"] = int(logic.cfg_get(cfg, "annual_leave_days", 3))
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
    players = await asyncio.to_thread(db.all_players, gid)
    if len(players) < 2:
        return R(err="群里的打工人太少了，八卦都编不出来")
    a, b = random.sample(players, 2)
    an = a.get("card") or a["nickname"] or f"用户{a['uid']}"
    bn = b.get("card") or b["nickname"] or f"用户{b['uid']}"
    text = random.choice(gd.t("extra", "gossip_texts"))
    gossip = text.replace("{a}", an).replace("{b}", bn)
    return R(
        tmpl="panel",
        data={
            "icon": "☕",
            "title": "职场八卦速递",
            "accent": "#ffd86f",
            "lines": [gossip],
            "foot": "八卦纯属娱乐，请勿对号入座",
        },
        text=f"【职场八卦】{gossip}",
    )


ACHIEVEMENTS_DEF = [
    {"id": "work_10", "name": "全勤劳模", "desc": "连续出勤达到10天", "cond": lambda p: int(p.get("attend_streak") or 0) >= 10},
    {"id": "wealth_100k", "name": "富甲一方", "desc": "总资产达到10万元", "cond": lambda p: (float(p.get("cash") or 0) + float(p.get("deposit") or 0) + float(p.get("fund") or 0)) >= 100000},
    {"id": "duel_king", "name": "PPT战神", "desc": "对线撕逼胜利达到10次", "cond": lambda p: int(p.get("duel_wins") or 0) >= 10},
    {"id": "emperor", "name": "打工皇帝", "desc": "职级达到合伙人·打工皇帝", "cond": lambda p: int(p.get("lvl") or 1) >= 11},
    {"id": "pet_lover", "name": "铲屎大官人", "desc": "成功领养一只宠物", "cond": lambda p: bool(p.get("pet"))},
    {"id": "homeowner", "name": "有房一族", "desc": "全款买下自购小窝", "cond": lambda p: int(p.get("house_owned") or 0) >= 1},
]


async def my_achievements(db, gid, uid, nickname, cfg):
    """查看个人成就并自动检测解锁。"""
    p = await _load(db, gid, uid, nickname, cfg)
    import json as _json
    unlocked = set(_json.loads(p.get("achievements") or "[]"))
    new_unlocked = []
    
    for ach in ACHIEVEMENTS_DEF:
        if ach["id"] not in unlocked and ach["cond"](p):
            unlocked.add(ach["id"])
            new_unlocked.append(ach["name"])
            
    if new_unlocked:
        p["achievements"] = _json.dumps(list(unlocked))
        await asyncio.to_thread(db.save_player, p)

    rows = []
    for ach in ACHIEVEMENTS_DEF:
        status = "✅ [已解锁]" if ach["id"] in unlocked else "🔒 [未达成]"
        equipped = " 🎖️(已佩戴)" if p.get("title") == ach["name"] else ""
        rows.append(f"{status} 【{ach['name']}】{equipped}：{ach['desc']}")

    cur_title = p.get("title") or "暂无佩戴"
    return R(
        tmpl="panel",
        data={
            "icon": "🎖️",
            "title": f"{p['nickname'] or uid} 的职场成就",
            "accent": "#ffd86f",
            "lines": rows,
            "blocks": [
                {"label": "当前称号", "value": cur_title},
                {"label": "解锁进度", "value": f"{len(unlocked)} / {len(ACHIEVEMENTS_DEF)}"},
            ],
            "foot": "发送「佩戴称号 称号名」或「卸下称号」佩戴展示",
        },
        text=f"🎖️ 我的成就 ({len(unlocked)}/{len(ACHIEVEMENTS_DEF)})，当前称号：{cur_title}\n" + "\n".join(rows),
    )


async def set_title(db, gid, uid, nickname, title_name, cfg):
    """佩戴已解锁的成就称号。"""
    p = await _load(db, gid, uid, nickname, cfg)
    import json as _json
    unlocked = set(_json.loads(p.get("achievements") or "[]"))
    title_name = (title_name or "").strip()
    if not title_name:
        return R(err="请输入要佩戴的称号名称，例如：「佩戴称号 全勤劳模」，发送「我的成就」查看已解锁称号")

    # 匹配称号
    target = next((ach for ach in ACHIEVEMENTS_DEF if ach["name"] == title_name or title_name in ach["name"]), None)
    if not target:
        return R(err=f"未找到称号「{title_name}」，发送「我的成就」查看列表")
    if target["id"] not in unlocked:
        return R(err=f"称号【{target['name']}】尚未解锁：{target['desc']}")

    p["title"] = target["name"]
    await asyncio.to_thread(db.save_player, p)
    return R(
        tmpl="panel",
        data={
            "icon": "✨",
            "title": "称号佩戴成功",
            "accent": "#6fe08c",
            "lines": [f"已成功佩戴专属职场头衔：【{target['name']}】！将在个人名片与对决中展示。"],
            "blocks": [
                {"label": "当前头衔", "value": f"🎖️ {target['name']}"},
                {"label": "成就描述", "value": target["desc"]},
            ],
        },
        text=f"✨ 成功佩戴称号【{target['name']}】！",
    )


async def unset_title(db, gid, uid, nickname, cfg):
    """卸下当前佩戴的头衔。"""
    p = await _load(db, gid, uid, nickname, cfg)
    p["title"] = ""
    await asyncio.to_thread(db.save_player, p)
    return R(
        tmpl="panel",
        data={
            "icon": "🍃",
            "title": "已卸下称号",
            "accent": "#7fd1ff",
            "lines": ["已恢复默认低调打工人身份。"],
        },
        text="🍃 已卸下称号头衔，回归低调打工生活。",
    )


async def send_redpacket(db, gid, uid, nickname, amount_str, count_str, cfg):
    """在群内发送拼手气红包。"""
    p = await _load(db, gid, uid, nickname, cfg)
    try:
        amt = float(amount_str)
        cnt = int(count_str)
    except (TypeError, ValueError):
        return R(err="格式错误！请发送：「发红包 <总金额> <个数>」，例如：「发红包 1000 5」")

    min_packet = float(logic.cfg_get(cfg, "redpacket_min_amount", 10.0))
    if amt < min_packet or cnt < 1 or cnt > 50 or amt < cnt:
        return R(err=f"发红包总金额需 >= {logic.fmt_money(min_packet)}元，且每个红包至少 1 元，单个红包最多 50 个（当前金额 {amt} 元，个数 {cnt}）")

    if float(p["cash"]) < amt:
        return R(err=f"你的现金不足 {logic.fmt_money(amt)} 元，囊中羞涩发不起红包")

    p["cash"] = round(float(p["cash"]) - amt, 2)
    await asyncio.to_thread(db.save_player, p)
    await asyncio.to_thread(db.add_transaction, gid, uid, "发群红包", -amt, f"{cnt}个红包")

    def _do_send():
        with db_module._write_lock:
            conn = db._conn()
            try:
                cur = conn.execute(
                    "INSERT INTO redpackets (gid, sender_uid, sender_name, total_amount, total_count, remain_amount, remain_count, claimed_records, created_at) "
                    "VALUES (?,?,?,?,?,?,?,?,?)",
                    (
                        str(gid),
                        str(uid),
                        p["nickname"] or uid,
                        amt,
                        cnt,
                        amt,
                        cnt,
                        "[]",
                        int(time.time()),
                    ),
                )
                conn.commit()
                return cur.lastrowid
            finally:
                conn.close()

    packet_id = await asyncio.to_thread(_do_send)

    await asyncio.to_thread(
        db.add_event, gid, uid, "发红包", f"{p['nickname'] or uid} 豪气撒币发送了 {logic.fmt_money(amt)} 元拼手气红包（共 {cnt} 个）！"
    )
    return R(
        tmpl="panel",
        data={
            "icon": "🧧",
            "title": "🎉 拼手气红包已发出！",
            "accent": "#fc6262",
            "lines": [
                f"{p['nickname'] or uid} 豪气塞了 {logic.fmt_money(amt)} 元大红包！",
                f"红包ID: #{packet_id} · 共 {cnt} 个，群友快发送「抢红包」开抢！",
            ],
            "blocks": [
                {"label": "红包总额", "value": f"{logic.fmt_money(amt)} 元"},
                {"label": "红包数量", "value": f"{cnt} 个"},
                {"label": "抢夺指令", "value": "抢红包"},
            ],
            "foot": "手快有，手慢无，看谁是群内手气王！",
        },
        text=f"🧧 {p['nickname'] or uid} 发送了 {logic.fmt_money(amt)} 元红包（共{cnt}个）！发送「抢红包」开抢！",
    )


async def claim_redpacket(db, gid, uid, nickname, cfg):
    """群友抢最近的可用红包。"""
    p = await _load(db, gid, uid, nickname, cfg)
    import json as _json

    def _do_claim():
        with db_module._write_lock:
            conn = db._conn()
            try:
                row = conn.execute(
                    "SELECT * FROM redpackets WHERE gid=? AND remain_count > 0 ORDER BY id DESC LIMIT 1",
                    (str(gid),)
                ).fetchone()
                if not row:
                    return None, "empty"
                packet = dict(row)
                claimed_records = _json.loads(packet["claimed_records"] or "[]")
                if any(str(r.get("uid")) == str(uid) for r in claimed_records):
                    return None, "already_claimed"

                remain_amt = float(packet["remain_amount"])
                remain_cnt = int(packet["remain_count"])
                if remain_cnt <= 0:
                    return None, "empty"

                if remain_cnt == 1:
                    get_amt = round(remain_amt, 2)
                else:
                    max_possible = (remain_amt / remain_cnt) * 2
                    get_amt = round(random.uniform(0.5, max_possible), 2)
                    get_amt = max(0.1, min(get_amt, remain_amt - (remain_cnt - 1) * 0.1))

                new_remain_amt = round(remain_amt - get_amt, 2)
                new_remain_cnt = remain_cnt - 1
                claimed_records.append({
                    "uid": str(uid),
                    "name": p["nickname"] or uid,
                    "amount": get_amt,
                    "time": int(time.time()),
                })

                cur = conn.execute(
                    "UPDATE redpackets SET remain_amount=?, remain_count=?, claimed_records=? WHERE id=? AND remain_count > 0",
                    (new_remain_amt, new_remain_cnt, _json.dumps(claimed_records, ensure_ascii=False), packet["id"]),
                )
                if cur.rowcount == 0:
                    return None, "empty"
                conn.commit()
                return (packet, get_amt, new_remain_amt, new_remain_cnt), "ok"
            finally:
                conn.close()

    res, status = await asyncio.to_thread(_do_claim)
    if status == "empty":
        return R(err="当前群内没有未领完的红包，发送「发红包 1000 5」自己当老板发一个吧！")
    if status == "already_claimed":
        return R(err="你已经抢过这个红包了，给其他群友留点机会吧！")
    if not res:
        return R(err="手慢了一步，红包已被抢光！")

    packet, get_amt, new_remain_amt, new_remain_cnt = res
    p["cash"] = round(float(p["cash"]) + get_amt, 2)
    p["total_earned"] = round(float(p.get("total_earned") or 0) + get_amt, 2)
    await asyncio.to_thread(db.save_player, p)
    await asyncio.to_thread(db.add_transaction, gid, uid, "抢群红包", get_amt, f"来自 {packet['sender_name']}")

    return R(
        tmpl="panel",
        data={
            "icon": "🧧",
            "title": "🎉 抢到红包！",
            "accent": "#ffd86f",
            "lines": [f"手速惊人！成功抢到来自 {packet['sender_name']} 的红包！"],
            "blocks": [
                {"label": "抢到金额", "value": f"+{logic.fmt_money(get_amt)} 元"},
                {"label": "个人现金", "value": f"{logic.fmt_money(p['cash'])} 元"},
                {"label": "红包剩余", "value": f"{new_remain_cnt} 个（{logic.fmt_money(new_remain_amt)} 元）"},
            ],
            "foot": "恭喜发财，大吉大利！",
        },
        text=f"🧧 恭喜抢到 {packet['sender_name']} 的红包：+{logic.fmt_money(get_amt)} 元！当前现金 {logic.fmt_money(p['cash'])} 元",
    )


async def scratch_lottery(db, gid, uid, nickname, cfg):
    """下班刮刮乐：小赌怡情。"""
    p = await _load(db, gid, uid, nickname, cfg)
    cost = float(logic.cfg_get(cfg, "scratch_lottery_cost", 20.0))
    if float(p["cash"]) < cost:
        return R(err=f"刮一张「职场刮刮乐」需要 {logic.fmt_money(cost)} 元，当前余额不足")

    p["cash"] = round(float(p["cash"]) - cost, 2)

    # 随机奖项
    prizes = [
        ("特等奖 · 打工人逆袭", 5000.0, 0.005, "#ffd86f"),
        ("一等奖 · 年终奖提前发", 800.0, 0.03, "#6fe08c"),
        ("二等奖 · 下午茶基金", 200.0, 0.10, "#7fd1ff"),
        ("三等奖 · 回本安慰奖", 30.0, 0.25, "#b48cff"),
        ("谢谢惠顾 · 感谢为福彩做贡献", 0.0, 0.615, "#fc6262"),
    ]

    roll = random.random()
    accum = 0.0
    chosen = prizes[-1]
    for name, amt, prob, color in prizes:
        accum += prob
        if roll <= accum:
            chosen = (name, amt, prob, color)
            break

    prize_name, reward, _, color = chosen
    if reward > 0:
        p["cash"] = round(float(p["cash"]) + reward, 2)
        p["total_earned"] = round(float(p.get("total_earned") or 0) + reward, 2)

    await asyncio.to_thread(db.save_player, p)
    await asyncio.to_thread(db.add_transaction, gid, uid, "刮刮乐", reward - cost, prize_name)

    return R(
        tmpl="panel",
        data={
            "icon": "🎫",
            "title": "🎰 职场刮刮乐开奖！",
            "accent": color,
            "lines": [f"刮开图层：【{prize_name}】！"],
            "blocks": [
                {"label": "中奖金额", "value": f"{logic.fmt_money(reward)} 元" if reward > 0 else "0 元"},
                {"label": "刮刮乐花费", "value": f"-{logic.fmt_money(cost)} 元"},
                {"label": "个人现金", "value": f"{logic.fmt_money(p['cash'])} 元"},
            ],
            "foot": "刮刮乐小赌怡情，大赌伤身，请适度娱乐",
        },
        text=f"🎫 刮刮乐开奖：【{prize_name}】获得 {logic.fmt_money(reward)} 元！当前现金 {logic.fmt_money(p['cash'])} 元",
    )

