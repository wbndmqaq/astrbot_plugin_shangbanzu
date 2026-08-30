"""年终考评系统：每年限一次，S/A/B/C/D 五档考评。"""

import asyncio
import random
import time

from . import gamedata as gd
from . import logic
from .result import R


async def annual_review(db, gid, uid, nickname, cfg):
    p = await logic.load_player(db, gid, uid, nickname, cfg)
    if int(p["company"]) == -1:
        return R(err="失业人士没有年终考评，先找工作吧")

    year = time.strftime("%Y")
    if p.get("review_year") == year:
        return R(err=f"{year} 年的年终考评已经做过了，明年再战")

    lvl = int(p["lvl"])
    exp = int(p["exp"])
    streak = int(p.get("attend_streak") or 0)
    skills = p.get("_skills", [])
    social = int(p.get("social_pts") or 0)

    # 综合评分：五项权重可配（默认与老版本一致）
    def c(key, default):
        return float(logic.cfg_get(cfg, key, default))

    score = (
        exp * c("review_weight_exp", 2)
        + streak * c("review_weight_streak", 5)
        + len(skills) * c("review_weight_skill", 20)
        + social * c("review_weight_social", 3)
        + lvl * c("review_weight_level", 50)
    )
    score = round(score * (0.8 + random.random() * 0.4))

    # 档位阈值 + 年终奖倍数 + 调薪幅度。这是全插件最大的通胀杠杆
    # （S 级一次给数倍月薪现金 **且永久涨薪**），必须让运维能压制。
    tiers = [
        ("S", "传奇打工者", "review_grade_s_threshold", 800,
         "review_bonus_multi_s", 3.0, "review_raise_s", 0.15, "#ffd86f", "👑"),
        ("A", "优秀员工", "review_grade_a_threshold", 500,
         "review_bonus_multi_a", 2.0, "review_raise_a", 0.10, "#6fe08c", "🌟"),
        ("B", "合格员工", "review_grade_b_threshold", 300,
         "review_bonus_multi_b", 1.0, "review_raise_b", 0.05, "#7fd1ff", "📋"),
        ("C", "待改进", "review_grade_c_threshold", 150,
         "review_bonus_multi_c", 0.3, "review_raise_c", 0.0, "#ffb86f", "⚠️"),
    ]
    grade, grade_name = "D", "绩效不达标"
    bonus_mult = c("review_bonus_multi_d", 0.0)
    raise_pct = 0.0
    color, icon = "#fc6262", "🔴"
    for g, gname, tkey, tdef, mkey, mdef, rkey, rdef, col, ic in tiers:
        if score >= c(tkey, tdef):
            grade, grade_name = g, gname
            bonus_mult = c(mkey, mdef)
            raise_pct = c(rkey, rdef)
            color, icon = col, ic
            break

    comp = await asyncio.to_thread(gd.resolve_company, int(p["company"]), db)
    bonus = round(float(p["salary"]) * bonus_mult, 2)
    old_salary = float(p["salary"])
    if raise_pct > 0:
        p["salary"] = round(old_salary * (1 + raise_pct), 0)

    p["review_year"] = year
    p["cash"] = round(float(p["cash"]) + bonus, 2)
    p["total_earned"] = round(float(p.get("total_earned") or 0) + bonus, 2)
    logic.clamp_status(p)
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
