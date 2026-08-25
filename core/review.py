"""年终考评系统：每年12月可触发一次，S/A/B/C/D 五档考评。"""

import asyncio
import random
import time

from . import gamedata as gd
from . import logic
from .career import R, _load


async def annual_review(db, gid, uid, nickname, cfg):
    p = await _load(db, gid, uid, nickname, cfg)
    if int(p["company"]) == -1:
        return R(err="失业人士没有年终考评，先找工作吧")

    year = time.strftime("%Y")
    key = f"review_{year}"
    if p.get(key):
        return R(err=f"{year} 年的年终考评已经做过了，明年再战")

    lvl = int(p["lvl"])
    exp = int(p["exp"])
    streak = int(p.get("attend_streak") or 0)
    skills = p.get("_skills", [])
    social = int(p.get("social_pts") or 0)

    # 综合评分
    score = exp * 2 + streak * 5 + len(skills) * 20 + social * 3 + lvl * 50
    roll = random.random()
    score = round(score * (0.8 + roll * 0.4))

    if score >= 800:
        grade, grade_name = "S", "传奇打工者"
        bonus_mult = 3.0
        raise_pct = 0.15
        color, icon = "#ffd86f", "👑"
    elif score >= 500:
        grade, grade_name = "A", "优秀员工"
        bonus_mult = 2.0
        raise_pct = 0.10
        color, icon = "#6fe08c", "🌟"
    elif score >= 300:
        grade, grade_name = "B", "合格员工"
        bonus_mult = 1.0
        raise_pct = 0.05
        color, icon = "#7fd1ff", "📋"
    elif score >= 150:
        grade, grade_name = "C", "待改进"
        bonus_mult = 0.3
        raise_pct = 0.0
        color, icon = "#ffb86f", "⚠️"
    else:
        grade, grade_name = "D", "绩效不达标"
        bonus_mult = 0.0
        raise_pct = 0.0
        color, icon = "#fc6262", "🔴"

    comp = gd.company_by_id(int(p["company"]))
    bonus = round(float(p["salary"]) * bonus_mult, 2)
    old_salary = float(p["salary"])
    if raise_pct > 0:
        p["salary"] = round(old_salary * (1 + raise_pct), 0)

    p[key] = time.strftime("%Y-%m-%d")
    p["cash"] = round(float(p["cash"]) + bonus, 2)
    p["total_earned"] = round(float(p.get("total_earned") or 0) + bonus, 2)
    _clamp = lambda v: max(0, min(100, v))
    p["health"] = _clamp(float(p["health"]))
    p["mind"] = _clamp(float(p["mind"]))
    await asyncio.to_thread(db.save_player, p)

    await asyncio.to_thread(
        db.add_transaction, gid, uid, "年终奖", bonus, f"考评{grade}"
    )
    await asyncio.to_thread(
        db.add_event,
        gid,
        uid,
        "年终考评",
        f"{p['nickname'] or uid} 年终考评 {grade}（{grade_name}），年终奖 {logic.fmt_money(bonus)} 元",
    )

    skill_names = "、".join(skills) if skills else "无"
    return R(
        tmpl="panel",
        data={
            "icon": icon,
            "title": f"年终考评 {grade} 级 · {grade_name}",
            "accent": color,
            "subtitle": f"公司：{comp['name'] if comp else '无'}",
            "blocks": [
                {"label": "综合评分", "value": str(score)},
                {
                    "label": "年终奖",
                    "value": f"+{logic.fmt_money(bonus)} 元（{bonus_mult}倍月薪）",
                },
                {
                    "label": "调薪",
                    "value": f"+{raise_pct * 100:.0f}%" if raise_pct > 0 else "无调薪",
                },
                {"label": "已掌握技能", "value": skill_names or "无"},
                {"label": "人脉值", "value": str(social)},
                {"label": "连续出勤", "value": f"{streak} 天"},
            ],
            "foot": "考评影响年终奖倍数和调薪幅度，明年继续努力",
        },
        text=(
            f"年终考评 {grade} 级（{grade_name}）！\n"
            f"年终奖 +{logic.fmt_money(bonus)} 元"
            + (f"，调薪 +{raise_pct * 100:.0f}%" if raise_pct > 0 else "")
        ),
    )
