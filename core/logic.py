"""纯函数工具：数值规则、格式化、Elo、段位。"""

import random
import time
from datetime import date


def cfg_get(cfg, key, default=None):
    v = cfg.get(key) if hasattr(cfg, "get") else None
    return default if v is None else v


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


def now_ts() -> int:
    return int(time.time())


def today_str() -> str:
    return time.strftime("%Y-%m-%d")


def iso_week(t: float | None = None) -> tuple[int, int]:
    dt = time.localtime(t) if t else time.localtime()
    y, w, _ = date(dt.tm_year, dt.tm_mon, dt.tm_mday).isocalendar()
    return y, w


def yearweek_str() -> str:
    y, w = iso_week()
    return f"{y}-W{w:02d}"


def fmt_money(value) -> str:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return "0"
    if abs(v - round(v)) < 1e-9:
        return str(round(v))
    return f"{v:.2f}"


def fmt_remaining(seconds) -> str:
    s = max(0, int(seconds))
    h, m, sec = s // 3600, (s % 3600) // 60, s % 60
    if h:
        return f"{h}小时{m}分{sec}秒"
    if m:
        return f"{m}分{sec}秒"
    return f"{sec}秒"


def ri(lo: int, hi: int) -> int:
    """random.randint 的安全版（lo>hi 时自动交换）"""
    if lo > hi:
        lo, hi = hi, lo
    return random.randint(lo, hi)


def rf(lo: float, hi: float) -> float:
    return random.uniform(min(lo, hi), max(lo, hi))


TIER_NAMES = ["菜鸟", "老油条", "职场精英", "行业大佬", "传奇卷王"]
TIER_SCORES = [0, 1000, 1400, 1800, 2200]


def tier_of(score: int) -> str:
    name = TIER_NAMES[0]
    for i, threshold in enumerate(TIER_SCORES):
        if score >= threshold:
            name = TIER_NAMES[i]
    return name


def elo_change(my: int, opp: int, is_win: bool, k: int = 32) -> int:
    expected = 1 / (1 + 10 ** ((opp - my) / 400))
    return int(k * ((1 - expected) if is_win else (0 - expected)))


def fund_daily_change() -> float:
    """单日基金涨跌幅（百分比），截断在 [-12%, +12%]。"""
    change = random.gauss(0.2, 4.5)
    return clamp(change, -12.0, 12.0)


def interest_of(
    deposit: float,
    last_interest: int,
    rate_hourly: float,
    max_hours: int,
    now: int | None = None,
) -> float:
    now = now or now_ts()
    if deposit <= 0 or not last_interest:
        return 0.0
    hours = int((now - last_interest) // 3600)
    if hours < 1:
        return 0.0
    effective = min(hours, max_hours)
    return round(deposit * rate_hourly * effective, 2)


def salary_of(base_salary: float, mult: float) -> float:
    return round(float(base_salary) * float(mult), 0)


def daily_pay(salary: float, perf: float, streak: int) -> float:
    bonus = min(streak, 20) * 0.005
    return round(salary / 22 * perf * (1 + bonus), 2)


def promote_rate(level_index: int, base: float, decay: float) -> float:
    return max(0.15, base - level_index * decay)


def avatar_of(uid, app_id: str = "") -> str:
    """生成头像 URL。

    - OneBot (纯数字 QQ 号)：走 q1.qlogo.cn
    - QQ 官方机器人 (32 位 openid / user_str 且包含 app_id)：走 q.qlogo.cn/qqapp/{app_id}/{user_str}/640
    """
    uid = str(uid).strip()
    if not uid:
        return ""
    if uid.isdigit():
        return f"https://q1.qlogo.cn/g?b=qq&nk={uid}&s=640"
    if app_id:
        return f"https://q.qlogo.cn/qqapp/{app_id}/{uid}/640"
    return ""


def display(p: dict) -> str:
    """展示名优先级：【称号】+ 群昵称(card) > 昵称 > 用户{id}"""
    name = p.get("card") or p.get("nickname") or f"用户{p.get('uid', '')}"
    title = p.get("title")
    return f"【{title}】{name}" if title else name


def pick(seq):
    return random.choice(seq) if seq else ""


def weighted_layoff(risk: float, scale: float) -> bool:
    return random.random() < risk * scale
