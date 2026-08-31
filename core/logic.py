"""纯函数工具：数值规则、格式化、Elo、段位。"""

import asyncio
import random
import time
from datetime import date


def cfg_get(cfg, key, default=None):
    v = cfg.get(key) if hasattr(cfg, "get") else None
    return default if v is None else v


def clamp(v, lo, hi):
    if v is None:
        return lo
    return max(lo, min(hi, float(v)))


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
    diff = int(k * ((1 - expected) if is_win else (0 - expected)))
    # int() 向零截断在极端分差下会把变化削成 0（赢了不加分/输了不扣分），
    # 钳到 ±1 保证每场对战积分必有变动
    if diff == 0:
        diff = 1 if is_win else -1
    return diff


def fund_daily_change(cfg=None) -> float:
    """基金单日涨跌幅（百分比）。

    drift 为正意味着长期持有稳赚，是最容易被忽视的通胀口，
    所以漂移、波动率、单日涨跌停三个参数都开放给运维调。
    """
    drift = float(cfg_get(cfg, "fund_drift", 0.2))
    vol = abs(float(cfg_get(cfg, "fund_volatility", 4.5)))
    limit = abs(float(cfg_get(cfg, "fund_daily_limit_pct", 12.0)))
    return clamp(random.gauss(drift, vol), -limit, limit)


def interest_of(
    deposit: float,
    last_interest: int,
    rate_hourly: float,
    max_hours: int,
    now: int | None = None,
) -> float:
    now = now_ts() if now is None else now
    if deposit <= 0 or not last_interest:
        return 0.0
    hours = int((now - last_interest) // 3600)
    if hours < 1:
        return 0.0
    effective = min(hours, max_hours)
    return round(deposit * rate_hourly * effective, 2)


def salary_of(base_salary: float, mult: float) -> float:
    return round(float(base_salary) * float(mult), 0)


def workdays(cfg=None) -> int:
    """月薪折算日薪的工作日数。散落多处，统一从这里取。"""
    return max(1, int(cfg_get(cfg, "monthly_workdays", 22)))


def daily_pay(salary: float, perf: float, streak: int, cfg=None) -> float:
    cap = int(cfg_get(cfg, "attend_streak_bonus_days", 20))
    rate = float(cfg_get(cfg, "attend_streak_bonus_rate", 0.005))
    bonus = min(int(streak), cap) * rate
    return round(salary / workdays(cfg) * perf * (1 + bonus), 2)


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


# ==================================================================
# 玩家状态与冷却辅助工具（统一在此管理，避免跨模块私有调用与重复定义）
# ==================================================================


async def load_player(db, gid, uid, nickname, cfg):
    start_cash = float(cfg_get(cfg, "start_cash", 800))
    return await asyncio.to_thread(db.get_player, gid, uid, nickname, start_cash)


def cd_left(p: dict, key: str) -> float:
    return float(p.get("_cds", {}).get(key, 0)) - time.time()


def cd_set(p: dict, key: str, seconds: float | int):
    p.setdefault("_cds", {})[key] = int(time.time()) + int(seconds)


def is_exempt(cfg, uid) -> bool:
    ids = [str(x) for x in (cfg_get(cfg, "cooldown_exempt_users") or [])]
    return str(uid) in ids


def clamp_status(p: dict):
    p["health"] = round(clamp(float(p["health"]), 0, 100), 1)
    p["mind"] = round(clamp(float(p["mind"]), 0, 100), 1)


# ==================================================================
# 用户输入解析：一律走这里，绝不把原始文本喂给 int()/float()
# ==================================================================

# 金额/数量的最大位数。Python 3.11+ 对 int() 有 4300 位上限，
# int("1" * 5000) 会直接抛 ValueError 打断指令，所以必须先限长再转换。
MAX_ARG_DIGITS = 12
# 单笔金额上限：防止 1e18 这类数值把经济系统冲垮
MAX_AMOUNT = 1e12


def parse_int(text, default=None, lo: int | None = None, hi: int | None = None):
    """安全解析用户输入的非负整数；非法/超长返回 default。"""
    s = str(text if text is not None else "").strip()
    if not s.isdigit() or len(s) > MAX_ARG_DIGITS:
        return default
    v = int(s)
    if lo is not None and v < lo:
        return default
    if hi is not None and v > hi:
        return default
    return v


def parse_amount(text, default=None, lo: float = 0.01, hi: float = MAX_AMOUNT):
    """安全解析用户输入的金额（支持小数）；非法/越界返回 default。"""
    s = str(text if text is not None else "").strip()
    if not s or len(s) > MAX_ARG_DIGITS + 3:
        return default
    try:
        v = float(s)
    except ValueError:
        return default
    if v != v or v in (float("inf"), float("-inf")):  # NaN / inf
        return default
    if v < lo or v > hi:
        return default
    return round(v, 2)
