"""加载 resources 下的静态数据与文本 JSON。"""

import json
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent / "resources"
DATA_DIR = BASE / "data"
TEXTS_DIR = BASE / "texts"
TMPL_DIR = BASE / "templates"

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
    return load_all()["companies"]["companies"]


def company_by_id(cid: int) -> dict | None:
    for c in companies():
        if c["id"] == cid:
            return c
    return None


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


def shop_items() -> list[dict]:
    return load_all()["shop"]["shop"]


def opponents() -> list[dict]:
    return load_all()["opponents"]["opponents"]


def rank_events() -> list[dict]:
    return load_all()["rankevents"]["events"]


def match_opponent(score: int) -> dict:
    near = [o for o in opponents() if abs(o["score"] - int(score)) <= 300]
    import random

    return random.choice(near or opponents())


def news_of_day() -> str:
    import random
    import time

    heads = t("news", "headlines")
    if not heads:
        return ""
    seed = int(time.strftime("%Y%m%d"))
    rng = random.Random(seed)
    return rng.choice(heads)


def t(name: str, key: str):
    """取文本列表：t('work','slack_ok')"""
    return load_all()["texts"].get(name, {}).get(key, [])


def template_path(name: str) -> Path:
    return TMPL_DIR / f"{name}.html"
