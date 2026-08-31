"""彩票系统：游戏化双色球（累积奖池）。

规则：
- 每注号码 = 红球 16 选 3（不计顺序）+ 蓝球 8 选 1；
- 票价与每期每人限购由配置决定，购票款 100% 进入当期奖池（资金零和，不通胀）；
- 每日 lottery_draw_hour 点自动开奖（由 main._push_loop 触发），开奖号同构；
- 奖级（红球命中数 + 蓝球是否命中）：
    一等奖  3红+蓝  → 奖池 60%（同注平分）
    二等奖  3红     → 奖池 25%（同注平分）
    三等奖  2红+蓝  → 奖池 15%（同注平分）
  无人命中的份额自动滚存下一期，头奖越滚越大。
- 购票支持自选（`买彩票 3 7 12 5`，前 3 位红球 + 末 1 位蓝球）与机选（`买彩票 [张数]`）。
"""

import asyncio
import random

from . import logic
from .result import R

RED_MAX = 16  # 红球号码池 1~16
BLUE_MAX = 8  # 蓝球号码池 1~8
RED_PICK = 3  # 每注红球个数

TIER_NAMES = {"jackpot": "一等奖", "second": "二等奖", "third": "三等奖"}
TIERS_DEFAULT = {"jackpot": 0.6, "second": 0.25, "third": 0.15}


def _tiers_from_cfg(cfg) -> dict:
    """从插件配置读取奖金分配比例，缺失时回退默认。"""
    return {
        "jackpot": float(logic.cfg_get(cfg, "lottery_jackpot_pct", 0.6)),
        "second": float(logic.cfg_get(cfg, "lottery_second_pct", 0.25)),
        "third": float(logic.cfg_get(cfg, "lottery_third_pct", 0.15)),
    }


def fmt_number(red: list, blue: int) -> str:
    """规范化存储格式：'03,07,12|05'（红球升序 | 蓝球）。"""
    return ",".join(f"{n:02d}" for n in sorted(red)) + f"|{blue:02d}"


def parse_number(s: str):
    """'03,07,12|05' -> (red_set, blue)；非法返回 None。"""
    try:
        red_part, blue_part = str(s).split("|")
        red = {int(x) for x in red_part.split(",")}
        blue = int(blue_part)
        if len(red) != RED_PICK or not (1 <= blue <= BLUE_MAX):
            return None
        if any(not (1 <= r <= RED_MAX) for r in red):
            return None
        return red, blue
    except (ValueError, AttributeError):
        return None


def random_number() -> str:
    return fmt_number(
        random.sample(range(1, RED_MAX + 1), RED_PICK), random.randint(1, BLUE_MAX)
    )


def make_judge(draw_number: str, cfg=None):
    """生成绑定开奖号的判奖函数，供 db.lottery_settle 调用。"""
    parsed = parse_number(draw_number)
    if parsed is None:
        raise ValueError(f"bad draw number {draw_number}")
    draw_red, draw_blue = parsed
    tiers = _tiers_from_cfg(cfg) if cfg else TIERS_DEFAULT

    def judge(tickets: list, pool: float):
        winners = []
        paid = 0.0
        buckets: dict[str, list] = {}
        for t in tickets:
            tp = parse_number(t["number"])
            if tp is None:
                continue
            t_red, t_blue = tp
            red_hit = len(t_red & draw_red)
            blue_hit = t_blue == draw_blue
            tier = None
            if red_hit == RED_PICK and blue_hit:
                tier = "jackpot"
            elif red_hit == RED_PICK:
                tier = "second"
            elif red_hit == RED_PICK - 1 and blue_hit:
                tier = "third"
            if tier:
                buckets.setdefault(tier, []).append(t)
        for tier, ratio in tiers.items():
            hits = buckets.get(tier) or []
            if not hits:
                continue
            share = round(pool * ratio / len(hits), 2)
            for t in hits:
                winners.append(
                    {
                        "tier": tier,
                        "gid": t["gid"],
                        "uid": t["uid"],
                        "name": t["name"],
                        "number": t["number"],
                        "amount": share,
                    }
                )
                paid = round(paid + share, 2)
        return winners, paid

    return judge


def fmt_draw(number: str) -> str:
    """'03,07,12|05' -> '红球 03 07 12 + 蓝球 05'。"""
    red_part, blue_part = str(number).split("|")
    return f"红球 {' '.join(red_part.split(','))} + 蓝球 {blue_part}"


async def buy_ticket(db, gid, uid, args_str, cfg, nickname=""):
    """购票：`买彩票` / `买彩票 3`（机选 N 张）/ `买彩票 3 7 12 5`（自选一注）。"""
    p = await logic.load_player(db, gid, uid, nickname, cfg)
    price = float(logic.cfg_get(cfg, "lottery_ticket_price", 100))
    limit = max(1, int(logic.cfg_get(cfg, "lottery_max_tickets", 5)))
    today = logic.today_str()

    bought = await asyncio.to_thread(db.lottery_today_count, gid, uid, today)
    remain = limit - bought
    if remain <= 0:
        return R(err=f"本期（今日）限购 {limit} 注，你已经买满了，明天再来")

    tokens = [
        t for t in str(args_str or "").replace(",", " ").replace("，", " ").split() if t
    ]
    numbers: list[str] = []
    if not tokens:
        count = 1
        numbers = [random_number() for _ in range(count)]
    elif len(tokens) == 1 and tokens[0].isdigit():
        # 单数字 = 机选张数（按剩余额度截断，保证每期限购）
        count = max(1, min(int(tokens[0]), remain))
        numbers = [random_number() for _ in range(count)]
    elif len(tokens) == RED_PICK + 1 and all(t.isdigit() for t in tokens):
        # 4 个数字 = 自选一注（前 3 红 + 末 1 蓝）
        red = [int(x) for x in tokens[:RED_PICK]]
        blue = int(tokens[RED_PICK])
        if len(set(red)) != RED_PICK or any(not (1 <= r <= RED_MAX) for r in red):
            return R(
                err=f"红球需为 1~{RED_MAX} 中互不相同的 {RED_PICK} 个号码，例如：「买彩票 3 7 12 5」"
            )
        if not (1 <= blue <= BLUE_MAX):
            return R(
                err=f"蓝球需为 1~{BLUE_MAX} 的号码，例如：「买彩票 3 7 12 5」（末位为蓝球）"
            )
        numbers = [fmt_number(red, blue)]
    else:
        return R(
            err=(
                f"格式：机选「买彩票 3」（{limit} 注内），或自选一注「买彩票 3 7 12 5」"
                f"（前 {RED_PICK} 位红球 1~{RED_MAX}，末位蓝球 1~{BLUE_MAX}）"
            )
        )

    count = len(numbers)
    total = round(price * count, 2)
    if float(p["cash"]) < total:
        return R(
            err=f"买 {count} 注需要 {logic.fmt_money(total)} 元（单价 {logic.fmt_money(price)}），现金不足"
        )

    # 原子扣款 → 批量出票 → 奖池入金
    if not await asyncio.to_thread(db.try_debit_cash, gid, uid, total):
        return R(
            err=f"买 {count} 注需要 {logic.fmt_money(total)} 元（单价 {logic.fmt_money(price)}），现金不足"
        )
    name = p.get("card") or p["nickname"] or uid
    await asyncio.to_thread(db.lottery_add_tickets, gid, uid, name, numbers, today)
    await asyncio.to_thread(db.lottery_pool_add, today, total)
    await asyncio.to_thread(
        db.add_transaction, gid, uid, "购买彩票", -total, f"{count} 注 · 期号 {today}"
    )
    await asyncio.to_thread(
        db.add_event,
        gid,
        uid,
        "买彩票",
        f"{name} 花 {logic.fmt_money(total)} 元买了 {count} 注双色球，冲击一夜暴富梦！",
    )
    pool = await asyncio.to_thread(db.lottery_current_pool, today)

    pick_note = (
        "机选" if (not tokens or (len(tokens) == 1 and tokens[0].isdigit())) else "自选"
    )
    return R(
        tmpl="panel",
        data={
            "icon": "🎰",
            "title": f"双色球出票成功 · {count} 注（{pick_note}）",
            "accent": "#ffd86f",
            "lines": [
                f"{i + 1}. 红 {n.split('|')[0].replace(',', ' ')} + 蓝 {n.split('|')[1]}"
                for i, n in enumerate(numbers)
            ],
            "blocks": [
                {"label": "花费", "value": f"-{logic.fmt_money(total)} 元"},
                {"label": "本期持有", "value": f"{bought + count}/{limit} 注"},
                {"label": "当前奖池", "value": f"{logic.fmt_money(pool)} 元"},
            ],
            "foot": "每晚自动开奖：一等奖 3红+蓝 · 二等奖 3红 · 三等奖 2红+蓝，无人中滚存下期",
        },
        text=(
            f"🎰 双色球{pick_note}出票 {count} 注：\n"
            + "\n".join(
                f"{i + 1}. 红 {n.split('|')[0].replace(',', ' ')} + 蓝 {n.split('|')[1]}"
                for i, n in enumerate(numbers)
            )
            + f"\n花费 {logic.fmt_money(total)} 元，本期奖池已累积 {logic.fmt_money(pool)} 元"
        ),
    )


async def my_tickets(db, gid, uid, cfg):
    today = logic.today_str()
    tickets = await asyncio.to_thread(db.lottery_my_tickets, gid, uid, today)
    if not tickets:
        return R(err="本期你还没有彩票，发送「买彩票 3 7 12 5」自选一注冲刺一夜暴富")
    pool = await asyncio.to_thread(db.lottery_current_pool, today)
    limit = max(1, int(logic.cfg_get(cfg, "lottery_max_tickets", 5)))
    return R(
        tmpl="panel",
        data={
            "icon": "🎟️",
            "title": "我的双色球 · 本期",
            "accent": "#7fd1ff",
            "lines": [
                f"{i + 1}. 红 {t['number'].split('|')[0].replace(',', ' ')} + 蓝 {t['number'].split('|')[1]}"
                for i, t in enumerate(tickets)
            ],
            "blocks": [
                {"label": "持有", "value": f"{len(tickets)}/{limit} 注"},
                {"label": "当前奖池", "value": f"{logic.fmt_money(pool)} 元"},
                {
                    "label": "奖级",
                    "value": "一等奖 3红+蓝 · 二等奖 3红 · 三等奖 2红+蓝",
                },
            ],
        },
        text="🎟️ 本期号码：" + "；".join(t["number"] for t in tickets),
    )


async def lottery_result(db):
    last = await asyncio.to_thread(db.lottery_last_draw)
    if not last:
        return R(err="还没有开过奖，发送「买彩票」成为第一期彩民")
    winners = last.get("winners") or []
    lines = []
    for tier in ("jackpot", "second", "third"):
        ws = [w for w in winners if w["tier"] == tier]
        if ws:
            names = "、".join(
                f"{w['name']}（+{logic.fmt_money(w['amount'])}）" for w in ws[:5]
            )
            more = f" 等 {len(ws)} 人" if len(ws) > 5 else ""
            lines.append(f"{TIER_NAMES[tier]}：{names}{more}")
        else:
            lines.append(f"{TIER_NAMES[tier]}：无人命中，滚存奖池")
    return R(
        tmpl="panel",
        data={
            "icon": "🎊",
            "title": f"双色球开奖 · {last['date']}",
            "accent": "#ffd86f",
            "lines": [
                f"开奖号码：{fmt_draw(last['number'])}（共 {last.get('ticket_count', 0)} 注参与）",
                *lines,
            ],
            "blocks": [
                {"label": "本期奖池", "value": f"{logic.fmt_money(last['pool'])} 元"},
                {"label": "派奖合计", "value": f"{logic.fmt_money(last['paid'])} 元"},
                {"label": "滚存下期", "value": f"{logic.fmt_money(last['carry'])} 元"},
            ],
        },
        text=(
            f"🎊 双色球开奖（{last['date']}）：{fmt_draw(last['number'])}"
            f"（共 {last.get('ticket_count', 0)} 注参与）\n"
            + "\n".join(lines)
            + f"\n派奖 {logic.fmt_money(last['paid'])} 元，滚存 {logic.fmt_money(last['carry'])} 元"
        ),
    )


async def lottery_pool_view(db, cfg):
    today = logic.today_str()
    pool = await asyncio.to_thread(db.lottery_current_pool, today)
    tickets = await asyncio.to_thread(db.lottery_today_all_count, today)
    draw_hour = int(logic.cfg_get(cfg, "lottery_draw_hour", 21))
    price = float(logic.cfg_get(cfg, "lottery_ticket_price", 100))
    tiers = _tiers_from_cfg(cfg)
    return R(
        tmpl="panel",
        data={
            "icon": "🏦",
            "title": "一夜暴富梦 · 双色球奖池",
            "accent": "#ffd86f",
            "blocks": [
                {"label": "当前奖池", "value": f"{logic.fmt_money(pool)} 元"},
                {"label": "本期售出", "value": f"{tickets} 注"},
                {"label": "开奖时间", "value": f"每天 {draw_hour}:00 自动开奖"},
                {"label": "票价", "value": f"{logic.fmt_money(price)} 元/注"},
                {
                    "label": "玩法",
                    "value": f"红球 1~{RED_MAX} 选 {RED_PICK} + 蓝球 1~{BLUE_MAX} 选 1",
                },
                {
                    "label": "奖级",
                    "value": (
                        f"一等奖 {tiers['jackpot']:.0%} · "
                        f"二等奖 {tiers['second']:.0%} · "
                        f"三等奖 {tiers['third']:.0%}"
                    ),
                },
            ],
            "foot": "彩票收入全部进入奖池，无人中奖自动滚存，头奖越滚越大",
        },
        text=(
            f"🏦 双色球本期奖池 {logic.fmt_money(pool)} 元（{tickets} 注），"
            f"每天 {draw_hour}:00 开奖。红球 1~{RED_MAX} 选 {RED_PICK} + 蓝球 1~{BLUE_MAX} 选 1"
        ),
    )
