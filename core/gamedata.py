"""加载 resources 下的静态数据与文本 JSON。"""

import json
import random
import time
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent / "resources"
DATA_DIR = BASE / "data"
TEXTS_DIR = BASE / "texts"
TMPL_DIR = BASE / "templates"

# 自建公司的 players.company 取值 = CUSTOM_BASE + custom_companies.id
# （编码约定属于存储层，这里只做转发，保证全局单一来源）
from .db import CUSTOM_BASE  # noqa: E402

_cache: dict = {}


def _load_json(path: Path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_all(force: bool = False) -> dict:
    global _cache
    if _cache and not force:
        return _cache
    data = {}
    for p in DATA_DIR.glob("*.json"):
        data[p.stem] = _load_json(p)
    texts = {}
    for p in TEXTS_DIR.glob("*.json"):
        texts[p.stem] = _load_json(p)
    data["texts"] = texts
    _cache = data
    return _cache


def companies() -> list[dict]:
    """在招公司列表。

    返回浅拷贝：调用方对列表做 sort/append 不会污染全进程共享的缓存。
    """
    return list(load_all()["companies"]["companies"])


def company_by_id(cid: int) -> dict | None:
    for c in load_all()["companies"]["companies"]:
        if c["id"] == cid:
            return c
    return None


_LOST_COMPANY = {
    "id": 1,
    "name": "失联企业",
    "tag": "倒闭",
    "salary": 3500.0,
    "intensity": 5.0,
    "risk": 0.0,
    "min_exp": 0,
    "desc": "原公司已解散",
    "perks": [],
}


def custom_company(db, cid: int) -> dict | None:
    """把 custom_companies 行包装成与静态公司同构的 dict。"""
    if db is None or int(cid) < CUSTOM_BASE:
        return None
    custom_id = int(cid) - CUSTOM_BASE
    cc = db.get_custom_company(custom_id)
    if not cc:
        return None
    return {
        "id": int(cid),
        "name": cc["name"],
        "tag": cc.get("tag", "自建企业"),
        "salary": float(cc.get("salary", 6000.0)),
        "intensity": 5.0,
        "risk": 0.01,
        "min_exp": 0,
        "desc": f"群友自建公司，老板：{cc.get('boss_uid')}",
        "perks": ["自建福利", "企业分红池"],
        "is_custom": True,
        "custom_id": custom_id,
        "boss_uid": str(cc.get("boss_uid") or ""),
        "balance": float(cc.get("balance") or 0),
    }


def resolve_company(cid, db=None) -> dict | None:
    """统一的公司解析入口：静态公司与自建公司都能解析。

    简历/工资条/同事录/职级榜/考评一律走这里，否则自建公司的员工
    会因为 company_by_id 返回 None 而在各处显示成「失业」。
    未就业（-1）返回 None；公司已被删除时回退「失联企业」防止 None 下标崩溃。
    """
    cid = int(cid)
    if cid < 0:
        return None
    if cid >= CUSTOM_BASE:
        return custom_company(db, cid) or company_by_id(1) or dict(_LOST_COMPANY)
    return company_by_id(cid) or company_by_id(1) or dict(_LOST_COMPANY)


def company_name(cid, db=None) -> str:
    """公司名（未就业返回空串），供纯展示场景使用。"""
    c = resolve_company(cid, db)
    return str(c["name"]) if c else ""


def company_names(custom_rows=()) -> dict[int, str]:
    """{players.company 取值: 公司名} 映射。

    榜单/名录这类要展示几十个玩家的场景用它，一次查出本群自建公司即可，
    不必对每个玩家单独查库。custom_rows 为 db.custom_companies_of_group 的结果。
    """
    m = {int(c["id"]): str(c["name"]) for c in load_all()["companies"]["companies"]}
    for r in custom_rows or ():
        m[CUSTOM_BASE + int(r["id"])] = str(r["name"])
    return m


def display_company(cid, names: dict[int, str], jobless: str = "无业") -> str:
    """按映射表取展示用公司名；未就业返回 jobless，公司已删返回「失联企业」。"""
    cid = int(cid)
    if cid < 0:
        return jobless
    return names.get(cid) or _LOST_COMPANY["name"]


def positions() -> list[dict]:
    return sorted(load_all()["positions"]["positions"], key=lambda x: x["i"])


def position(i: int) -> dict:
    pos = positions()
    i = max(0, min(len(pos) - 1, int(i)))
    return pos[i]


def houses() -> list[dict]:
    return sorted(load_all()["houses"]["houses"], key=lambda x: x["i"])


def house(i: int) -> dict:
    hs = houses()
    i = max(0, min(len(hs) - 1, int(i)))
    return hs[i]


def meals() -> dict[str, dict]:
    """{吃法名: {cost, health, mind, key}}（数值表见 resources/data/meals.json）。"""
    return {str(m["name"]): dict(m) for m in load_all()["meals"]["meals"]}


def commute_modes() -> dict[str, dict]:
    """{通勤方式: {cost, health, mind, late_rate}}（resources/data/commute.json）。"""
    return {str(c["name"]): dict(c) for c in load_all()["commute"]["commute"]}


def commute_mode(name: str) -> dict:
    """取通勤方式；未知名称回退到表中第一项，避免 KeyError。"""
    modes = commute_modes()
    return modes.get(str(name)) or next(iter(modes.values()))


def certs() -> dict[str, dict]:
    """{证书名: {cost, exp}}（resources/data/certs.json）。"""
    return {str(c["name"]): dict(c) for c in load_all()["certs"]["certs"]}


def scratch_table() -> tuple[list[dict], dict]:
    """刮刮乐奖项表 (中奖档位列表, 未中奖档位)。

    金额以「相对售价的倍数」存储，返奖率由调用方按配置缩放，
    这样运维改售价不会连带破坏返奖率。
    """
    data = load_all()["scratch"]
    return [dict(x) for x in data["prizes"]], dict(data["lose"])


def shop_items() -> list[dict]:
    return list(load_all()["shop"]["shop"])


def opponents() -> list[dict]:
    """卷王大赛对手池（resources/data/opponents.json）。

    别名 opponent_pool 是历史命名，统一使用 opponents()。
    """
    return list(load_all()["opponents"]["opponents"])


# 兼容旧调用点
opponent_pool = opponents


def rank_events() -> list[dict]:
    return list(load_all()["rankevents"]["events"])


def side_hustle_titles() -> list[str]:
    """副业等级称号表（resources/data/workstations.json 中的 side_hustle_titles）。

    替代 core/extra.py 里硬编码的 names 列表；运维改 JSON 即可换文案。
    """
    raw = load_all().get("workstations", {}).get("side_hustle_titles") or []
    return [str(x) for x in raw]


def workstations() -> list[dict]:
    """工位配置（resources/data/workstations.json 中的 workstations）。"""
    return list(load_all().get("workstations", {}).get("workstations", []))


def match_opponent(score: int) -> dict:
    pool = load_all()["opponents"]["opponents"]
    near = [o for o in pool if abs(o["score"] - int(score)) <= 300]
    return random.choice(near or pool)


def news_of_day() -> str:
    heads = t("news", "headlines")
    if not heads:
        return ""
    rng = random.Random(int(time.strftime("%Y%m%d")))
    return rng.choice(heads)


def t(name: str, key: str):
    """取文本列表：t('work','slack_ok')。返回副本，避免调用方就地修改缓存。"""
    return list(load_all()["texts"].get(name, {}).get(key, []))


def template_path(name: str) -> Path:
    return TMPL_DIR / f"{name}.html"
