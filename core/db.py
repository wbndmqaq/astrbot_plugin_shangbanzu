"""SQLite 存储层（标准库 sqlite3，WAL 模式，线程安全：每操作独立连接）。"""

import datetime
import json
import random
import sqlite3
import threading
import time
from pathlib import Path

_write_lock = threading.Lock()

# players.company 的编码约定：>=0 为静态公司 ID，-1 为失业，
# >=CUSTOM_BASE 表示自建公司（值 = CUSTOM_BASE + custom_companies.id）。
# 定义在存储层、由 gamedata 复用，避免两处各写一个 10000。
CUSTOM_BASE = 10000

SCHEMA = """
CREATE TABLE IF NOT EXISTS players (
    gid TEXT NOT NULL,
    uid TEXT NOT NULL,
    nickname TEXT DEFAULT '',
    card TEXT DEFAULT '',
    cash REAL DEFAULT 0,
    deposit REAL DEFAULT 0,
    bank_level INTEGER DEFAULT 1,
    bank_limit REAL DEFAULT 5000,
    bank_upgrade_price REAL DEFAULT 200,
    last_interest INTEGER DEFAULT 0,
    health REAL DEFAULT 80,
    mind REAL DEFAULT 80,
    exp INTEGER DEFAULT 0,
    lvl INTEGER DEFAULT 1,
    company INTEGER DEFAULT -1,
    salary REAL DEFAULT 0,
    house INTEGER DEFAULT 0,
    fund REAL DEFAULT 0,
    fund_day TEXT DEFAULT '',
    attend_streak INTEGER DEFAULT 0,
    work_day TEXT DEFAULT '',
    leave_week TEXT DEFAULT '',
    leave_count INTEGER DEFAULT 0,
    value REAL DEFAULT 100,
    cds TEXT DEFAULT '{}',
    rank_score INTEGER DEFAULT 1000,
    rank_tier TEXT DEFAULT '菜鸟',
    rank_matches INTEGER DEFAULT 0,
    duel_wins INTEGER DEFAULT 0,
    duel_losses INTEGER DEFAULT 0,
    layoffs_survived INTEGER DEFAULT 0,
    promote_count INTEGER DEFAULT 0,
    fund_savings REAL DEFAULT 0,
    total_earned REAL DEFAULT 0,
    comp_leave INTEGER DEFAULT 0,
    commute TEXT DEFAULT '地铁',
    house_owned INTEGER DEFAULT 0,
    skills TEXT DEFAULT '[]',
    social_pts INTEGER DEFAULT 0,
    side_lvl INTEGER DEFAULT 1,
    annual_leave INTEGER DEFAULT 3,
    annual_year TEXT DEFAULT '',
    year_bonus_year TEXT DEFAULT '',
    workstation INTEGER DEFAULT 0,
    party_year TEXT DEFAULT '',
    checkup_year TEXT DEFAULT '',
    meeting_day TEXT DEFAULT '',
    reply_day TEXT DEFAULT '',
    room_day TEXT DEFAULT '',
    pet_day TEXT DEFAULT '',
    pet TEXT DEFAULT '',
    items TEXT DEFAULT '{}',
    title TEXT DEFAULT '',
    achievements TEXT DEFAULT '[]',
    review_year TEXT DEFAULT '',
    created_at INTEGER DEFAULT 0,
    updated_at INTEGER DEFAULT 0,
    PRIMARY KEY (gid, uid)
);
CREATE TABLE IF NOT EXISTS redpackets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    gid TEXT NOT NULL,
    sender_uid TEXT NOT NULL,
    sender_name TEXT DEFAULT '',
    total_amount REAL NOT NULL,
    total_count INTEGER NOT NULL,
    remain_amount REAL NOT NULL,
    remain_count INTEGER NOT NULL,
    claimed_records TEXT DEFAULT '[]',
    created_at INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS custom_companies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    gid TEXT NOT NULL,
    boss_uid TEXT NOT NULL,
    name TEXT NOT NULL,
    tag TEXT DEFAULT '创业',
    salary REAL DEFAULT 5000,
    balance REAL DEFAULT 0,
    created_at INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    gid TEXT NOT NULL,
    uid TEXT NOT NULL,
    kind TEXT NOT NULL,
    amount REAL NOT NULL,
    note TEXT DEFAULT '',
    created_at INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_tx_player ON transactions (gid, uid, id);
CREATE TABLE IF NOT EXISTS push_groups (
    gid TEXT PRIMARY KEY,
    enabled INTEGER DEFAULT 1,
    last_push TEXT DEFAULT '',
    updated_at INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS group_info (
    gid TEXT PRIMARY KEY,
    name TEXT DEFAULT '',
    updated_at INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS archives (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    gid TEXT NOT NULL,
    year INTEGER NOT NULL,
    week INTEGER NOT NULL,
    payload TEXT NOT NULL,
    created_at INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_archives ON archives (gid, year, week);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    gid TEXT NOT NULL,
    uid TEXT NOT NULL,
    kind TEXT NOT NULL,
    summary TEXT NOT NULL,
    created_at INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_events_time ON events (created_at);
CREATE TABLE IF NOT EXISTS stocks (
    code TEXT PRIMARY KEY,
    name TEXT DEFAULT '',
    sector TEXT DEFAULT '',
    price REAL DEFAULT 10,
    prev REAL DEFAULT 10,
    day TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS portfolio (
    gid TEXT NOT NULL,
    uid TEXT NOT NULL,
    code TEXT NOT NULL,
    shares REAL DEFAULT 0,
    cost REAL DEFAULT 0,
    PRIMARY KEY (gid, uid, code)
);

CREATE TABLE IF NOT EXISTS lottery_tickets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    gid TEXT NOT NULL,
    uid TEXT NOT NULL,
    name TEXT DEFAULT '',
    number TEXT NOT NULL,
    draw_date TEXT NOT NULL,
    created_at INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_lottery_date ON lottery_tickets (draw_date);
CREATE TABLE IF NOT EXISTS lottery_draws (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    draw_date TEXT NOT NULL UNIQUE,
    number TEXT NOT NULL,
    pool REAL DEFAULT 0,
    paid REAL DEFAULT 0,
    ticket_count INTEGER DEFAULT 0,
    winners TEXT DEFAULT '[]',
    created_at INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS lottery_pool (
    draw_date TEXT PRIMARY KEY,
    pool REAL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS webui_sessions (
    jti TEXT PRIMARY KEY,
    subject TEXT NOT NULL DEFAULT 'admin',
    user_agent TEXT DEFAULT '',
    ip TEXT DEFAULT '',
    created_at INTEGER NOT NULL,
    last_seen_at INTEGER NOT NULL,
    expires_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_webui_sessions_exp ON webui_sessions(expires_at);
"""

COLUMNS = [
    "gid",
    "uid",
    "nickname",
    "card",
    "cash",
    "deposit",
    "bank_level",
    "bank_limit",
    "bank_upgrade_price",
    "last_interest",
    "health",
    "mind",
    "exp",
    "lvl",
    "company",
    "salary",
    "house",
    "fund",
    "fund_day",
    "attend_streak",
    "work_day",
    "leave_week",
    "leave_count",
    "value",
    "cds",
    "rank_score",
    "rank_tier",
    "rank_matches",
    "duel_wins",
    "duel_losses",
    "layoffs_survived",
    "promote_count",
    "fund_savings",
    "total_earned",
    "comp_leave",
    "commute",
    "house_owned",
    "skills",
    "social_pts",
    "side_lvl",
    "annual_leave",
    "annual_year",
    "year_bonus_year",
    "workstation",
    "party_year",
    "checkup_year",
    "meeting_day",
    "reply_day",
    "room_day",
    "pet_day",
    "pet",
    "items",
    "title",
    "achievements",
    "review_year",
    "created_at",
    "updated_at",
]

# 并发列：其它玩家（转账/红包/借钱/对线）与定时器（彩票派奖）会在本玩家
# 持有快照的窗口期内对这些列做原子增减。写回时只提交「本次变化量」，
# 而不是快照里的绝对值，否则窗口期内他人的入账会被整行覆盖抹掉。
# 值为 (小数位, 下限, 上限)，None 表示不限制。
DELTA_FLOAT_COLUMNS = {
    "cash": (2, 0.0, None),
    "total_earned": (2, 0.0, None),
    "mind": (1, 0.0, 100.0),
    "value": (2, 0.0, None),
    "deposit": (2, 0.0, None),
    "fund": (2, 0.0, None),
    "fund_savings": (2, 0.0, None),
}
DELTA_INT_COLUMNS = ("duel_wins", "duel_losses")

DEFAULTS = {
    "nickname": "",
    "card": "",
    "cash": 800.0,
    "deposit": 0.0,
    "bank_level": 1,
    "bank_limit": 5000.0,
    "bank_upgrade_price": 200.0,
    "last_interest": 0,
    "health": 80.0,
    "mind": 80.0,
    "exp": 0,
    "lvl": 1,
    "company": -1,
    "salary": 0.0,
    "house": 0,
    "fund": 0.0,
    "fund_day": "",
    "attend_streak": 0,
    "work_day": "",
    "leave_week": "",
    "leave_count": 0,
    "value": 100.0,
    "cds": "{}",
    "rank_score": 1000,
    "rank_tier": "菜鸟",
    "rank_matches": 0,
    "duel_wins": 0,
    "duel_losses": 0,
    "layoffs_survived": 0,
    "promote_count": 0,
    "fund_savings": 0.0,
    "total_earned": 0.0,
    "comp_leave": 0,
    "commute": "地铁",
    "house_owned": 0,
    "skills": "[]",
    "social_pts": 0,
    "side_lvl": 1,
    "annual_leave": 3,
    "annual_year": "",
    "year_bonus_year": "",
    "workstation": 0,
    "party_year": "",
    "checkup_year": "",
    "meeting_day": "",
    "reply_day": "",
    "room_day": "",
    "pet_day": "",
    "pet": "",
    "items": "{}",
    "title": "",
    "achievements": "[]",
    "review_year": "",
    "created_at": 0,
    "updated_at": 0,
}


# 新玩家初始值中「可由运维配置」的部分：键为 players 列名，值为配置项名。
# 注意 annual_leave 必须走配置，否则 DEFAULTS 里的 3 会和 annual_leave_days
# 各说一套——改了配置的新玩家仍拿 3，直到跨年才被重置。
START_CONFIG_KEYS = {
    "cash": "start_cash",
    "health": "start_health",
    "mind": "start_mind",
    "value": "start_value",
    "rank_score": "start_rank_score",
    "bank_limit": "bank_initial_limit",
    "bank_upgrade_price": "bank_initial_upgrade_price",
    "annual_leave": "annual_leave_days",
}


def new_player(
    gid: str, uid: str, nickname: str = "", start: dict | None = None
) -> dict:
    """建号。start 为 {列名: 初始值} 覆盖表（由 DB.start_values 按配置生成）。"""
    p = dict(DEFAULTS)
    p.update(start or {})
    p["gid"] = str(gid)
    p["uid"] = str(uid)
    p["nickname"] = nickname or ""
    now = int(time.time())
    p["created_at"] = now
    p["updated_at"] = now
    return p


class DB:
    def __init__(self, path, cfg=None):
        self.path = Path(path)
        # 建号初始值统一从插件配置读取（cfg 为实时配置对象）。集中在存储层，
        # 避免各调用点漏传参数而退回硬编码默认值。
        self.cfg = cfg if hasattr(cfg, "get") else {}
        self.busy_timeout = max(
            1000, int(self._cfg("db_busy_timeout_ms", 15000) or 15000)
        )

    def _cfg(self, key, default=None):
        v = self.cfg.get(key) if hasattr(self.cfg, "get") else None
        return default if v is None else v

    def start_values(self) -> dict:
        """按配置生成新玩家的初始列值。"""
        out = {}
        for col, key in START_CONFIG_KEYS.items():
            v = self._cfg(key)
            if v is None:
                continue
            out[col] = int(v) if isinstance(DEFAULTS[col], int) else float(v)
        return out

    def init(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = self._conn()
        try:
            conn.executescript(SCHEMA)
            conn.commit()
        finally:
            conn.close()

    def _conn(self) -> sqlite3.Connection:
        timeout_s = self.busy_timeout / 1000.0
        conn = sqlite3.connect(self.path, timeout=timeout_s)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute(f"PRAGMA busy_timeout={self.busy_timeout}")
        return conn

    # ---------- 玩家 ----------

    def get_player(
        self, gid, uid, nickname: str = "", start_cash: float | None = None
    ) -> dict:
        conn = self._conn()
        try:
            row = conn.execute(
                "SELECT * FROM players WHERE gid=? AND uid=?", (str(gid), str(uid))
            ).fetchone()
        finally:
            conn.close()
        if row is None:
            start = self.start_values()
            if start_cash is not None:  # 调用方显式指定优先（兼容旧签名）
                start["cash"] = float(start_cash)
            p = new_player(gid, uid, nickname, start)
            self.save_player(p)
            return self.normalize(p)
        p = dict(row)
        if nickname:
            p["nickname"] = nickname
        return self.normalize(p)

    @staticmethod
    def normalize(p: dict) -> dict:
        d = dict(DEFAULTS)
        for k, dv in d.items():
            if k not in p or p[k] is None:
                p[k] = dv
        p["gid"] = str(p["gid"])
        p["uid"] = str(p["uid"])
        try:
            cds = json.loads(p.get("cds") or "{}")
        except json.JSONDecodeError:
            cds = {}
        p["_cds"] = cds if isinstance(cds, dict) else {}
        try:
            p["_skills"] = json.loads(p.get("skills") or "[]")
        except json.JSONDecodeError:
            p["_skills"] = []
        # 快照基准值：save_player 据此把并发列换算成增量写回
        p["_orig"] = {
            c: p.get(c, DEFAULTS.get(c, 0))
            for c in (*DELTA_FLOAT_COLUMNS, *DELTA_INT_COLUMNS)
        }
        return p

    def save_player(self, p: dict):
        p = dict(p)
        orig = p.pop("_orig", None)
        cds = p.pop("_cds", None)
        if cds is not None:
            p["cds"] = json.dumps(cds, ensure_ascii=False)
        skills = p.pop("_skills", None)
        if skills is not None:
            p["skills"] = json.dumps(skills, ensure_ascii=False)
        p["updated_at"] = int(time.time())
        if orig is not None and self._save_delta(p, orig):
            return
        self._save_full(p)

    def _save_delta(self, p: dict, orig: dict) -> bool:
        """增量写回既有行：并发列提交变化量，其余列照常覆盖。

        返回 False 表示目标行已不存在（如被管理员删档），由调用方走全量插入。

        重要约束：DELTA_FLOAT_COLUMNS 上的 SQL MIN/MAX 只能作为【最终钳制】，不能
        阻断合理 delta。比如 cash 已经被 atomic 列更新增到 80，本进程要扣 -30，
        数据库里 round(80 + (-30), 2) = 50，这是正常的；不能写成 MAX(0, ..)
        否则一旦数据库当前值 < (-delta) 就会被钳成 0，无视别人刚入账的钱。
        MIN/MAX 仅在 hi/lo 非 None 时用 ABS 截断防止溢出。
        """
        sets, args = [], []
        applied = {}
        for c in COLUMNS:
            if c in ("gid", "uid"):
                continue
            new = p.get(c, DEFAULTS.get(c, 0))
            if c in DELTA_FLOAT_COLUMNS:
                nd, lo, hi = DELTA_FLOAT_COLUMNS[c]
                # 用 ABS+MIN 防溢出（不要用 MIN/MAX 包裹当前值，
                # 否则与 atomic 列更新并发时会吞掉已入账的余额）。
                expr = f"round({c}+?,{nd})"
                if hi is not None:
                    expr = f"MIN(ABS({hi}),{expr})"  # 钳到上限
                if lo is not None:
                    expr = f"({lo}+MAX(0, {expr}-{lo}))"  # 钳到下限（不会无故抬升）
                sets.append(f"{c}={expr}")
                args.append(round(float(new) - float(orig.get(c) or 0), nd))
                applied[c] = new
            elif c in DELTA_INT_COLUMNS:
                sets.append(f"{c}={c}+?")
                args.append(int(new) - int(orig.get(c) or 0))
                applied[c] = new
            else:
                sets.append(f"{c}=?")
                args.append(new)
        args += [str(p["gid"]), str(p["uid"])]
        sql = f"UPDATE players SET {','.join(sets)} WHERE gid=? AND uid=?"
        with _write_lock:
            conn = self._conn()
            try:
                cur = conn.execute(sql, args)
                conn.commit()
            finally:
                conn.close()
        if cur.rowcount <= 0:
            return False
        # 推进基准值：同一个快照被保存两次时，第二次的增量必须是 0 而不是
        # 再算一遍完整差值（orig 与调用方的 p["_orig"] 是同一个对象）。
        orig.update(applied)
        return True

    def _save_full(self, p: dict):
        cols = list(COLUMNS)
        values = [p.get(c, DEFAULTS.get(c, 0)) for c in cols]
        placeholders = ",".join("?" for _ in cols)
        updates = ",".join(f"{c}=?" for c in cols if c not in ("gid", "uid"))
        sql = (
            f"INSERT INTO players ({','.join(cols)}) VALUES ({placeholders}) "
            f"ON CONFLICT(gid,uid) DO UPDATE SET {updates}"
        )
        args = values + [
            v for c, v in zip(cols, values, strict=True) if c not in ("gid", "uid")
        ]
        with _write_lock:
            conn = self._conn()
            try:
                conn.execute(sql, args)
                conn.commit()
            finally:
                conn.close()

    def remap_company_ids(
        self, mapping: dict[int, int], unemploy: list[int] | None = None
    ) -> int:
        """批量重映射 players.company（旧公司ID → 新公司ID）。

        使用负数偏移两段式更新，避免 ID 交换场景下互相覆盖；
        unemploy 中的 ID 对应玩家置为失业(-1)。返回受影响行数。
        """
        changed = 0
        off = 1_000_000
        with _write_lock:
            conn = self._conn()
            try:
                for old in mapping:
                    cur = conn.execute(
                        "UPDATE players SET company=? WHERE company=?",
                        (int(old) - off, int(old)),
                    )
                    changed += cur.rowcount
                for old, new in mapping.items():
                    if int(old) == int(new):
                        continue
                    cur = conn.execute(
                        "UPDATE players SET company=? WHERE company=?",
                        (int(new), int(old) - off),
                    )
                    changed += cur.rowcount
                for old in unemploy or []:
                    cur = conn.execute(
                        "UPDATE players SET company=-1 WHERE company=?", (int(old),)
                    )
                    changed += cur.rowcount
                conn.commit()
            finally:
                conn.close()
        return changed

    def delete_player(self, gid, uid):
        with _write_lock:
            conn = self._conn()
            try:
                conn.execute(
                    "DELETE FROM players WHERE gid=? AND uid=?", (str(gid), str(uid))
                )
                conn.commit()
            finally:
                conn.close()

    def all_players(self, gid) -> list[dict]:
        conn = self._conn()
        try:
            rows = conn.execute(
                "SELECT * FROM players WHERE gid=? ORDER BY cash DESC", (str(gid),)
            ).fetchall()
        finally:
            conn.close()
        return [self.normalize(dict(r)) for r in rows]

    def page_players(self, gid, page: int = 1, size: int = 20) -> tuple[int, list[dict]]:
        """分页取玩家（WebUI 管理列表用）。

        避免 all_players 一次性把整组玩家读进内存再切片：
        直接带 LIMIT/OFFSET 只取当前页，另用 COUNT 拿总数做分页。
        """
        page = max(1, int(page))
        size = max(1, min(200, int(size)))
        offset = (page - 1) * size
        conn = self._conn()
        try:
            total = conn.execute(
                "SELECT COUNT(*) AS n FROM players WHERE gid=?", (str(gid),)
            ).fetchone()["n"]
            rows = conn.execute(
                "SELECT * FROM players WHERE gid=? ORDER BY cash DESC LIMIT ? OFFSET ?",
                (str(gid), size, offset),
            ).fetchall()
        finally:
            conn.close()
        return int(total), [self.normalize(dict(r)) for r in rows]

    def find_player_any(self, gid, kw: str) -> dict | None:
        conn = self._conn()
        try:
            row = conn.execute(
                "SELECT * FROM players WHERE gid=? AND (uid=? OR uid LIKE ? OR nickname LIKE ?) LIMIT 1",
                (str(gid), str(kw), f"%{kw}%", f"%{kw}%"),
            ).fetchone()
        finally:
            conn.close()
        return self.normalize(dict(row)) if row else None

    def group_ids(self) -> list[tuple[str, int]]:
        conn = self._conn()
        try:
            rows = conn.execute(
                "SELECT gid, COUNT(*) AS n FROM players GROUP BY gid ORDER BY n DESC"
            ).fetchall()
        finally:
            conn.close()
        return [(r["gid"], int(r["n"])) for r in rows]

    # ---------- 排行 ----------

    def top_by_column(self, gid, column: str, n: int = 10) -> list[dict]:
        if column not in COLUMNS:  # 显式校验：assert 在 python -O 下会被剥离
            raise ValueError(f"bad column {column}")
        conn = self._conn()
        try:
            rows = conn.execute(
                f"SELECT * FROM players WHERE gid=? ORDER BY {column} DESC LIMIT ?",
                (str(gid), n),
            ).fetchall()
        finally:
            conn.close()
        out = []
        for i, r in enumerate(rows):
            p = self.normalize(dict(r))
            p["rank"] = i + 1
            out.append(p)
        return out

    def top_wealth(self, gid, n: int = 10) -> list[dict]:
        conn = self._conn()
        try:
            rows = conn.execute(
                "SELECT *, (cash+deposit+fund) AS total FROM players WHERE gid=? "
                "ORDER BY total DESC LIMIT ?",
                (str(gid), n),
            ).fetchall()
        finally:
            conn.close()
        out = []
        for i, r in enumerate(rows):
            p = self.normalize(dict(r))
            p["total"] = round(float(r["total"]), 2)
            p["rank"] = i + 1
            out.append(p)
        return out

    def top_level(self, gid, n: int = 10) -> list[dict]:
        conn = self._conn()
        try:
            rows = conn.execute(
                "SELECT * FROM players WHERE gid=? ORDER BY lvl DESC, salary DESC LIMIT ?",
                (str(gid), n),
            ).fetchall()
        finally:
            conn.close()
        out = []
        for i, r in enumerate(rows):
            p = self.normalize(dict(r))
            p["rank"] = i + 1
            out.append(p)
        return out

    # ---------- 推送开关 ----------

    def push_enabled(self, gid: str) -> bool:
        conn = self._conn()
        try:
            row = conn.execute(
                "SELECT enabled FROM push_groups WHERE gid=?", (str(gid),)
            ).fetchone()
            return bool(row and row["enabled"])
        finally:
            conn.close()

    def set_push(self, gid: str, enabled: bool):
        with _write_lock:
            conn = self._conn()
            try:
                if enabled:
                    conn.execute(
                        "INSERT INTO push_groups (gid,enabled,updated_at) VALUES (?,1,?) "
                        "ON CONFLICT(gid) DO UPDATE SET enabled=1,"
                        "updated_at=excluded.updated_at",
                        (str(gid), int(time.time())),
                    )
                else:
                    conn.execute(
                        "UPDATE push_groups SET enabled=0, updated_at=? WHERE gid=?",
                        (int(time.time()), str(gid)),
                    )
                conn.commit()
            finally:
                conn.close()

    def push_last_date(self, gid: str) -> str:
        conn = self._conn()
        try:
            row = conn.execute(
                "SELECT last_push FROM push_groups WHERE gid=?", (str(gid),)
            ).fetchone()
            return str(row["last_push"] or "") if row else ""
        finally:
            conn.close()

    def mark_pushed(self, gid: str, date_str: str):
        with _write_lock:
            conn = self._conn()
            try:
                conn.execute(
                    "UPDATE push_groups SET last_push=?, updated_at=? WHERE gid=?",
                    (str(date_str), int(time.time()), str(gid)),
                )
                conn.commit()
            finally:
                conn.close()

    def push_group_ids(self) -> list:
        conn = self._conn()
        try:
            rows = conn.execute(
                "SELECT gid FROM push_groups WHERE enabled=1"
            ).fetchall()
            return [r["gid"] for r in rows]
        finally:
            conn.close()

    # ---------- 群信息（QQ官方接口拉取的群名） ----------

    def set_group_name(self, gid, name: str):
        with _write_lock:
            conn = self._conn()
            try:
                conn.execute(
                    "INSERT INTO group_info (gid,name,updated_at) VALUES (?,?,?) "
                    "ON CONFLICT(gid) DO UPDATE SET name=excluded.name,"
                    "updated_at=excluded.updated_at",
                    (str(gid), str(name)[:60], int(time.time())),
                )
                conn.commit()
            finally:
                conn.close()

    def all_group_names(self) -> dict[str, str]:
        conn = self._conn()
        try:
            rows = conn.execute("SELECT gid, name FROM group_info").fetchall()
            return {r["gid"]: r["name"] for r in rows if r["name"]}
        finally:
            conn.close()

    # ---------- 动态事件 ----------

    def add_event(self, gid, uid, kind: str, summary: str):
        with _write_lock:
            conn = self._conn()
            try:
                conn.execute(
                    "INSERT INTO events (gid, uid, kind, summary, created_at) VALUES (?,?,?,?,?)",
                    (str(gid), str(uid), kind, summary[:200], int(time.time())),
                )
                conn.commit()
            finally:
                conn.close()

    # ---------- 收支流水（工资条） ----------

    def add_transaction(self, gid, uid, kind: str, amount: float, note: str = ""):
        with _write_lock:
            conn = self._conn()
            try:
                conn.execute(
                    "INSERT INTO transactions (gid, uid, kind, amount, note, created_at) "
                    "VALUES (?,?,?,?,?,?)",
                    (
                        str(gid),
                        str(uid),
                        kind,
                        round(float(amount), 2),
                        note[:100],
                        int(time.time()),
                    ),
                )
                conn.commit()
            finally:
                conn.close()

    def close(self):
        """卸载时执行 WAL checkpoint 将 -wal 数据并回主库，避免残留。"""
        try:
            conn = self._conn()
            try:
                conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            finally:
                conn.close()
        except Exception:  # noqa: BLE001
            pass  # checkpoint 失败不影响 SQLite 正常关闭

    def cleanup_old_data(self):
        """定期/后台批量清理超量动态事件、历史流水与已领完的旧红包，防止表无限膨胀。

        用「取第 N 新一行的 id 作为水位线，删掉更旧的」代替 NOT IN 反连接：
        前者只需沿主键索引倒扫 N 行，后者是全表自连接。
        """
        days = float(self._cfg("redpacket_retention_days", 7) or 7)
        week_ago = int(time.time() - days * 86400)
        caps = (
            ("events", int(self._cfg("events_max_rows", 800) or 800)),
            ("transactions", int(self._cfg("transactions_max_rows", 50000) or 50000)),
        )
        with _write_lock:
            conn = self._conn()
            try:
                for table, keep in caps:
                    row = conn.execute(
                        f"SELECT id FROM {table} ORDER BY id DESC LIMIT 1 OFFSET ?",
                        (keep - 1,),
                    ).fetchone()
                    if row:
                        conn.execute(
                            f"DELETE FROM {table} WHERE id < ?", (int(row["id"]),)
                        )
                conn.execute(
                    "DELETE FROM redpackets WHERE remain_count <= 0 AND created_at < ?",
                    (week_ago,),
                )
                conn.execute(
                    "DELETE FROM webui_sessions WHERE expires_at < ?",
                    (int(time.time()),),
                )
                conn.commit()
            finally:
                conn.close()

    def clear_events(self) -> int:
        """清空动态事件流（WebUI 管理操作）。返回删除行数。"""
        with _write_lock:
            conn = self._conn()
            try:
                cur = conn.execute("DELETE FROM events")
                conn.commit()
                return cur.rowcount
            finally:
                conn.close()

    def set_card(self, gid, uid, card: str):
        with _write_lock:
            conn = self._conn()
            try:
                conn.execute(
                    "UPDATE players SET card=?, nickname=CASE WHEN nickname='' THEN ? ELSE nickname END "
                    "WHERE gid=? AND uid=?",
                    (card[:50], card[:50], str(gid), str(uid)),
                )
                conn.commit()
            finally:
                conn.close()

    def recent_transactions(self, gid, uid, limit: int = 15) -> list[dict]:
        conn = self._conn()
        try:
            rows = conn.execute(
                "SELECT kind, amount, note, created_at FROM transactions "
                "WHERE gid=? AND uid=? ORDER BY id DESC LIMIT ?",
                (str(gid), str(uid), limit),
            ).fetchall()
        finally:
            conn.close()
        return [dict(r) for r in rows]

    def recent_events(self, limit: int = 20) -> list[dict]:
        conn = self._conn()
        try:
            rows = conn.execute(
                "SELECT * FROM events ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        finally:
            conn.close()
        return [dict(r) for r in rows]

    def event_stats(self) -> dict:
        conn = self._conn()
        try:
            lt = time.localtime()
            today_start = int(
                time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday, 0, 0, 0, 0, 0, -1))
            )
            total = conn.execute("SELECT COUNT(*) AS n FROM players").fetchone()["n"]
            groups = conn.execute(
                "SELECT COUNT(DISTINCT gid) AS n FROM players"
            ).fetchone()["n"]
            today_events = conn.execute(
                "SELECT COUNT(*) AS n FROM events WHERE created_at >= ?", (today_start,)
            ).fetchone()["n"]
            richest = conn.execute(
                "SELECT nickname, gid, (cash+deposit+fund) AS total FROM players "
                "ORDER BY total DESC LIMIT 1"
            ).fetchone()
        finally:
            conn.close()
        return {
            "players": int(total),
            "groups": int(groups),
            "events_today": int(today_events),
            "richest": dict(richest) if richest else None,
        }

    # ---------- 每周归档 ----------

    def max_archived_week(self) -> tuple[int, int] | None:
        conn = self._conn()
        try:
            row = conn.execute(
                "SELECT year, week FROM archives ORDER BY year DESC, week DESC LIMIT 1"
            ).fetchone()
        finally:
            conn.close()
        if not row:
            return None
        return int(row["year"]), int(row["week"])

    def save_archive(self, gid, year: int, week: int, payload: dict):
        with _write_lock:
            conn = self._conn()
            try:
                conn.execute(
                    "DELETE FROM archives WHERE gid=? AND year=? AND week=?",
                    (str(gid), year, week),
                )
                conn.execute(
                    "INSERT INTO archives (gid, year, week, payload, created_at) VALUES (?,?,?,?,?)",
                    (
                        str(gid),
                        year,
                        week,
                        json.dumps(payload, ensure_ascii=False),
                        int(time.time()),
                    ),
                )
                conn.commit()
            finally:
                conn.close()

    def get_archive(self, gid, year: int, week: int) -> dict | None:
        conn = self._conn()
        try:
            row = conn.execute(
                "SELECT payload FROM archives WHERE gid=? AND year=? AND week=?",
                (str(gid), year, week),
            ).fetchone()
        finally:
            conn.close()
        if not row:
            return None
        try:
            return json.loads(row["payload"])
        except json.JSONDecodeError:
            return None

    def last_review_payload(self, gid, cur_year: int, cur_week: int) -> dict | None:
        if cur_week > 1:
            y, w = cur_year, cur_week - 1
        else:
            # ISO 8601 可能有 53 周（如 2020/2026/2032），需正确回退
            prev_year = cur_year - 1
            _, prev_week, _ = datetime.date(prev_year, 12, 31).isocalendar()
            y, w = prev_year, prev_week
        data = self.get_archive(gid, y, w)
        if data is None:
            row = self.max_archived_week()
            if row:
                data = self.get_archive(gid, row[0], row[1])
        return data

    # ---------- 自建公司 ----------

    def get_custom_company_by_boss(self, gid: str, boss_uid: str) -> dict | None:
        conn = self._conn()
        try:
            row = conn.execute(
                "SELECT * FROM custom_companies WHERE gid=? AND boss_uid=?",
                (str(gid), str(boss_uid)),
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def get_custom_company(self, cid: int) -> dict | None:
        conn = self._conn()
        try:
            row = conn.execute(
                "SELECT * FROM custom_companies WHERE id=?", (int(cid),)
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def custom_companies_of_group(self, gid) -> list[dict]:
        """本群全部自建公司（求职/跳槽市场用）。"""
        conn = self._conn()
        try:
            rows = conn.execute(
                "SELECT * FROM custom_companies WHERE gid=? ORDER BY id", (str(gid),)
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def delete_custom_company(self, cid: int) -> int:
        """删除自建公司并让其员工失业（创业扣款失败时的回滚路径）。"""
        with _write_lock:
            conn = self._conn()
            try:
                conn.execute(
                    "UPDATE players SET company=-1, salary=0 WHERE company=?",
                    (CUSTOM_BASE + int(cid),),
                )
                cur = conn.execute(
                    "DELETE FROM custom_companies WHERE id=?", (int(cid),)
                )
                conn.commit()
                return cur.rowcount
            finally:
                conn.close()

    def add_custom_company_balance(self, cid: int, amount: float):
        with _write_lock:
            conn = self._conn()
            try:
                conn.execute(
                    "UPDATE custom_companies SET balance=round(balance+?, 2) WHERE id=?",
                    (float(amount), int(cid)),
                )
                conn.commit()
            finally:
                conn.close()

    def withdraw_custom_company_dividend(
        self, gid: str, boss_uid: str
    ) -> tuple[dict | None, float, str]:
        with _write_lock:
            conn = self._conn()
            try:
                row = conn.execute(
                    "SELECT * FROM custom_companies WHERE gid=? AND boss_uid=?",
                    (str(gid), str(boss_uid)),
                ).fetchone()
                if not row:
                    return None, 0.0, "not_boss"
                balance = float(row["balance"] or 0)
                if balance <= 0:
                    return dict(row), 0.0, "zero_balance"
                conn.execute(
                    "UPDATE custom_companies SET balance=0 WHERE id=?", (row["id"],)
                )
                conn.commit()
                return dict(row), balance, "ok"
            finally:
                conn.close()

    # ---------- 彩票（累积奖池数字彩） ----------

    def lottery_pool_add(self, date_str: str, amount: float):
        """向指定期次的奖池入金（购票款全部进池）。

        注意 INSERT VALUES 的占位必须是 0：若用 amount，第一次插入时 pool=amount，
        走 ON CONFLICT UPDATE 时会变成 pool+amount=2*amount——这条 SQL 之所以
        历史上没炸，只是因为同进程内同一天的多次买票都走 UPDATE 分支，pool 起始
        永远是 amount；但若将来加入「0 点预占一行」之类的逻辑就会 double-count。
        """
        with _write_lock:
            conn = self._conn()
            try:
                conn.execute(
                    "INSERT INTO lottery_pool (draw_date, pool) VALUES (?, 0) "
                    "ON CONFLICT(draw_date) DO UPDATE SET pool=round(pool+?,2)",
                    (str(date_str), round(float(amount), 2)),
                )
                conn.commit()
            finally:
                conn.close()

    def lottery_current_pool(self, date_str: str) -> float:
        conn = self._conn()
        try:
            row = conn.execute(
                "SELECT pool FROM lottery_pool WHERE draw_date=?", (str(date_str),)
            ).fetchone()
            return float(row["pool"]) if row else 0.0
        finally:
            conn.close()

    def lottery_today_count(self, gid, uid, date_str: str) -> int:
        conn = self._conn()
        try:
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM lottery_tickets "
                "WHERE gid=? AND uid=? AND draw_date=?",
                (str(gid), str(uid), str(date_str)),
            ).fetchone()
            return int(row["n"])
        finally:
            conn.close()

    def lottery_add_tickets(self, gid, uid, name: str, numbers: list, date_str: str):
        """批量写入一期的彩票号码（购票扣款由调用方原子完成后调用）。"""
        now = int(time.time())
        with _write_lock:
            conn = self._conn()
            try:
                conn.executemany(
                    "INSERT INTO lottery_tickets (gid, uid, name, number, draw_date, created_at) "
                    "VALUES (?,?,?,?,?,?)",
                    [
                        (str(gid), str(uid), str(name)[:50], str(n), str(date_str), now)
                        for n in numbers
                    ],
                )
                conn.commit()
            finally:
                conn.close()

    def lottery_carry_unsettled_pool(self, today: str) -> float:
        """把没人购票/开奖当天的奖池余额滚存到次日，删除今天的池行。

        返回滚存金额（仅诊断）。如果今天无池行，直接返回 0。
        必须在 _push_loop 调用以避免「钱进池但永不滚存」的孤儿资金。
        """
        with _write_lock:
            conn = self._conn()
            try:
                row = conn.execute(
                    "SELECT pool FROM lottery_pool WHERE draw_date=?", (str(today),)
                ).fetchone()
                if not row:
                    return 0.0
                pool = float(row["pool"] or 0)
                if pool > 0:
                    tomorrow = _next_date(today)
                    conn.execute(
                        "INSERT INTO lottery_pool (draw_date, pool) VALUES (?, 0) "
                        "ON CONFLICT(draw_date) DO UPDATE SET pool=round(pool+?,2)",
                        (tomorrow, round(pool, 2)),
                    )
                conn.execute(
                    "DELETE FROM lottery_pool WHERE draw_date=?", (str(today),)
                )
                conn.commit()
                return round(pool, 2)
            finally:
                conn.close()

    def lottery_settle(self, date_str: str, number: str, judge):
        """开奖结算（单事务）。

        number 为本期开奖号码（格式 '03,07,12|05'）；
        judge(tickets, pool) -> (winners, paid)：
        tickets 为当期票行（含 number 字符串），由调用方（core.lottery）实现
        双色球判奖与奖金分摊等游戏规则；本方法只负责事务、入账与滚存。
        返回结算结果 dict，无人购票返回 None。
        """
        with _write_lock:
            conn = self._conn()
            try:
                tickets = conn.execute(
                    "SELECT id, gid, uid, name, number FROM lottery_tickets WHERE draw_date=?",
                    (str(date_str),),
                ).fetchall()
                if not tickets:
                    return None
                pool_row = conn.execute(
                    "SELECT pool FROM lottery_pool WHERE draw_date=?", (str(date_str),)
                ).fetchone()
                # 保留两位小数：票价 100% 入池是 2 位小数，取整会永久磨掉角分
                pool = round(float(pool_row["pool"]), 2) if pool_row else 0.0

                winners, paid = judge([dict(t) for t in tickets], pool)
                # 派奖上限为奖池，永不透支：总额超池时按比例缩放各票奖金
                gross = round(sum(float(w["amount"]) for w in winners), 2)
                if gross > pool > 0:
                    scale = pool / gross
                    for w in winners:
                        w["amount"] = round(float(w["amount"]) * scale, 2)
                paid = round(min(float(paid), pool), 2)
                for w in winners:
                    conn.execute(
                        "UPDATE players SET cash=round(cash+?,2), "
                        "total_earned=round(total_earned+?,2) WHERE gid=? AND uid=?",
                        (w["amount"], w["amount"], str(w["gid"]), str(w["uid"])),
                    )
                conn.execute(
                    "INSERT OR REPLACE INTO lottery_draws "
                    "(draw_date, number, pool, paid, ticket_count, winners, created_at) "
                    "VALUES (?,?,?,?,?,?,?)",
                    (
                        str(date_str),
                        str(number),
                        pool,
                        paid,
                        len(tickets),
                        json.dumps(winners, ensure_ascii=False),
                        int(time.time()),
                    ),
                )
                # 清掉已开票，滚存进下一期
                conn.execute(
                    "DELETE FROM lottery_tickets WHERE draw_date=?", (str(date_str),)
                )
                carry = round(pool - paid, 2)
                if carry > 0:
                    tomorrow = _next_date(date_str)
                    conn.execute(
                        "INSERT INTO lottery_pool (draw_date, pool) VALUES (?,?) "
                        "ON CONFLICT(draw_date) DO UPDATE SET pool=round(pool+?,2)",
                        (tomorrow, carry, carry),
                    )
                conn.execute(
                    "DELETE FROM lottery_pool WHERE draw_date=?", (str(date_str),)
                )
                conn.commit()
                return {
                    "date": str(date_str),
                    "number": str(number),
                    "pool": pool,
                    "paid": paid,
                    "carry": carry,
                    "winners": winners,
                    "ticket_count": len(tickets),
                }
            finally:
                conn.close()

    def lottery_last_draw(self):
        conn = self._conn()
        try:
            row = conn.execute(
                "SELECT * FROM lottery_draws ORDER BY draw_date DESC LIMIT 1"
            ).fetchone()
            if not row:
                return None
            d = dict(row)
            d["date"] = d.get("draw_date")  # 与 lottery_settle 返回结构对齐
            d["carry"] = round(float(d.get("pool") or 0) - float(d.get("paid") or 0), 2)
            try:
                d["winners"] = json.loads(d.get("winners") or "[]")
            except json.JSONDecodeError:
                d["winners"] = []
            return d
        finally:
            conn.close()

    def lottery_my_tickets(self, gid, uid, date_str: str) -> list:
        conn = self._conn()
        try:
            rows = conn.execute(
                "SELECT number FROM lottery_tickets "
                "WHERE gid=? AND uid=? AND draw_date=? ORDER BY id",
                (str(gid), str(uid), str(date_str)),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def lottery_today_all_count(self, date_str: str) -> int:
        conn = self._conn()
        try:
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM lottery_tickets WHERE draw_date=?",
                (str(date_str),),
            ).fetchone()
            return int(row["n"])
        finally:
            conn.close()

    def lottery_today_gids(self, date_str: str) -> list:
        """当期购票群列表（开奖播报用）。"""
        conn = self._conn()
        try:
            rows = conn.execute(
                "SELECT DISTINCT gid FROM lottery_tickets WHERE draw_date=?",
                (str(date_str),),
            ).fetchall()
            return [r["gid"] for r in rows]
        finally:
            conn.close()

    # ---------- 原子资金操作（防连发指令并发双花） ----------

    def try_debit_cash(self, gid, uid, amount: float) -> bool:
        """条件扣款：余额不足时 rowcount=0 返回 False，不产生负资产。"""
        with _write_lock:
            conn = self._conn()
            try:
                cur = conn.execute(
                    "UPDATE players SET cash=round(cash-?,2) "
                    "WHERE gid=? AND uid=? AND cash>=?",
                    (float(amount), str(gid), str(uid), float(amount)),
                )
                conn.commit()
                return cur.rowcount > 0
            finally:
                conn.close()

    # ---------- 跨用户原子列更新（防"读对方快照→全列覆盖"丢失更新） ----------

    def add_cash_atomic(self, gid, uid, amount: float):
        """列级原子增减现金（不校验下限，调用方保证语义）。"""
        with _write_lock:
            conn = self._conn()
            try:
                conn.execute(
                    "UPDATE players SET cash=round(cash+?,2) WHERE gid=? AND uid=?",
                    (float(amount), str(gid), str(uid)),
                )
                conn.commit()
            finally:
                conn.close()

    def credit_income(self, gid, uid, amount: float):
        """入账并同步累计总收入（cash 与 total_earned 同事务原子更新）。

        供红包领取等跨用户高频资金路径使用，避免"快照全列覆盖写"
        冲掉窗口期内他人对本玩家的原子转账。
        """
        with _write_lock:
            conn = self._conn()
            try:
                conn.execute(
                    "UPDATE players SET cash=round(cash+?,2), "
                    "total_earned=round(total_earned+?,2) WHERE gid=? AND uid=?",
                    (float(amount), float(amount), str(gid), str(uid)),
                )
                conn.commit()
            finally:
                conn.close()

    def add_mind_atomic(self, gid, uid, delta: float):
        """列级原子增减精神（钳制 0~100）。"""
        with _write_lock:
            conn = self._conn()
            try:
                conn.execute(
                    "UPDATE players SET mind=MAX(0.0, MIN(100.0, round(mind+?,1))) "
                    "WHERE gid=? AND uid=?",
                    (float(delta), str(gid), str(uid)),
                )
                conn.commit()
            finally:
                conn.close()

    def bump_duel_win(self, gid, uid, v_up: float):
        """对线获胜方原子结算：身价 +，胜场 +1。"""
        with _write_lock:
            conn = self._conn()
            try:
                conn.execute(
                    "UPDATE players SET value=round(value+?,2), duel_wins=duel_wins+1 "
                    "WHERE gid=? AND uid=?",
                    (float(v_up), str(gid), str(uid)),
                )
                conn.commit()
            finally:
                conn.close()

    def bump_duel_loss(self, gid, uid, v_down: float):
        """对线落败方原子结算：身价 -（下限 20），负场 +1。"""
        with _write_lock:
            conn = self._conn()
            try:
                conn.execute(
                    "UPDATE players SET value=MAX(20.0, round(value-?,2)), "
                    "duel_losses=duel_losses+1 WHERE gid=? AND uid=?",
                    (float(v_down), str(gid), str(uid)),
                )
                conn.commit()
            finally:
                conn.close()

    def transfer_cash(
        self, gid, from_uid, to_uid, amount: float, fee: float = 0.0
    ) -> tuple[bool, str]:
        """单事务内完成「扣总额(本金+手续费) → 对方入账本金」；任一步失败整体回滚。

        手续费与本金同事务扣除，避免两步提交间崩溃/并发导致手续费丢失。
        """
        amount = round(float(amount), 2)
        total = round(float(amount) + float(fee), 2)
        with _write_lock:
            conn = self._conn()
            try:
                cur = conn.execute(
                    "UPDATE players SET cash=round(cash-?,2) "
                    "WHERE gid=? AND uid=? AND cash>=?",
                    (total, str(gid), str(from_uid), total),
                )
                if cur.rowcount == 0:
                    return False, "insufficient"
                cur = conn.execute(
                    "UPDATE players SET cash=round(cash+?,2) WHERE gid=? AND uid=?",
                    (amount, str(gid), str(to_uid)),
                )
                if cur.rowcount == 0:
                    conn.rollback()
                    return False, "no_target"
                conn.commit()
                return True, "ok"
            finally:
                conn.close()

    def create_custom_company_if_free(
        self,
        gid: str,
        boss_uid: str,
        name: str,
        tag: str,
        salary: float,
        balance: float,
    ) -> int | None:
        """仅在老板尚未拥有公司时创建，返回公司 ID；已存在返回 None（防连发竞态）。"""
        with _write_lock:
            conn = self._conn()
            try:
                row = conn.execute(
                    "SELECT id FROM custom_companies WHERE gid=? AND boss_uid=?",
                    (str(gid), str(boss_uid)),
                ).fetchone()
                if row:
                    return None
                cur = conn.execute(
                    "INSERT INTO custom_companies (gid, boss_uid, name, tag, salary, balance, created_at) "
                    "VALUES (?,?,?,?,?,?,?)",
                    (
                        str(gid),
                        str(boss_uid),
                        str(name),
                        str(tag),
                        float(salary),
                        float(balance),
                        int(time.time()),
                    ),
                )
                conn.commit()
                return cur.lastrowid
            finally:
                conn.close()

    # ---------- 红包（原子领取，避免 extra 层触碰内部锁与连接） ----------

    def create_redpacket_atomic(
        self, gid, sender_uid, sender_name: str, amount: float, count: int
    ) -> tuple[bool, str, int | None]:
        """单事务完成「条件扣款 + 创建红包」。

        返回 (ok, reason, packet_id)：
        - (False, "insufficient", None) 余额不足
        - (False, "no_player", None) 玩家不存在
        - (True, "ok", packet_id) 成功
        防止扣完款但因崩溃/异常留下「钱扣了红包没建」的孤儿资金。
        """
        with _write_lock:
            conn = self._conn()
            try:
                cur = conn.execute(
                    "UPDATE players SET cash=round(cash-?,2) "
                    "WHERE gid=? AND uid=? AND cash>=?",
                    (float(amount), str(gid), str(sender_uid), float(amount)),
                )
                if cur.rowcount == 0:
                    return False, "insufficient", None
                cur = conn.execute(
                    "INSERT INTO redpackets (gid, sender_uid, sender_name, total_amount, "
                    "total_count, remain_amount, remain_count, claimed_records, created_at) "
                    "VALUES (?,?,?,?,?,?,?,?,?)",
                    (
                        str(gid),
                        str(sender_uid),
                        sender_name,
                        float(amount),
                        int(count),
                        float(amount),
                        int(count),
                        "[]",
                        int(time.time()),
                    ),
                )
                conn.commit()
                return True, "ok", int(cur.lastrowid)
            finally:
                conn.close()

    def claim_redpacket(self, gid, uid, nickname: str) -> tuple[str, tuple | None]:
        """原子抢红包。

        返回 ("ok", (packet, get_amt, remain_amt, remain_cnt))
            | ("empty", None) | ("already", None)。
        """

        with _write_lock:
            conn = self._conn()
            try:
                row = conn.execute(
                    "SELECT * FROM redpackets WHERE gid=? AND remain_count > 0 "
                    "ORDER BY id DESC LIMIT 1",
                    (str(gid),),
                ).fetchone()
                if not row:
                    return "empty", None
                packet = dict(row)
                try:
                    claimed = json.loads(packet["claimed_records"] or "[]")
                except (json.JSONDecodeError, TypeError):
                    claimed = []
                if any(str(r.get("uid")) == str(uid) for r in claimed):
                    return "already", None

                remain_amt = float(packet["remain_amount"])
                remain_cnt = int(packet["remain_count"])
                if remain_cnt <= 0:
                    return "empty", None

                if remain_cnt == 1:
                    get_amt = round(remain_amt, 2)
                else:
                    max_possible = (remain_amt / remain_cnt) * 2
                    get_amt = round(random.uniform(0.5, max_possible), 2)
                    get_amt = max(
                        0.1, min(get_amt, remain_amt - (remain_cnt - 1) * 0.1)
                    )
                    get_amt = round(min(get_amt, remain_amt), 2)  # 兜底：不超剩余总额
                    if get_amt <= 0:
                        get_amt = remain_amt

                new_remain_amt = round(remain_amt - get_amt, 2)
                new_remain_cnt = remain_cnt - 1
                claimed.append(
                    {
                        "uid": str(uid),
                        "name": nickname,
                        "amount": get_amt,
                        "time": int(time.time()),
                    }
                )
                cur = conn.execute(
                    "UPDATE redpackets SET remain_amount=?, remain_count=?, claimed_records=? "
                    "WHERE id=? AND remain_count > 0",
                    (
                        new_remain_amt,
                        new_remain_cnt,
                        json.dumps(claimed, ensure_ascii=False),
                        packet["id"],
                    ),
                )
                if cur.rowcount == 0:
                    return "empty", None
                conn.commit()
                return "ok", (packet, get_amt, new_remain_amt, new_remain_cnt)
            finally:
                conn.close()

    # ---------- WebUI 会话表（JWT jti 绑定，支持主动撤销） ----------

    def create_webui_session(
        self, jti: str, ip: str, ua: str, ttl: int, subject: str = "admin"
    ) -> None:
        now = int(time.time())
        with _write_lock:
            conn = self._conn()
            try:
                conn.execute(
                    "INSERT INTO webui_sessions "
                    "(jti, subject, user_agent, ip, created_at, last_seen_at, expires_at) "
                    "VALUES (?,?,?,?,?,?,?)",
                    (
                        str(jti),
                        str(subject)[:32],
                        str(ua or "")[:256],
                        str(ip or "")[:64],
                        now,
                        now,
                        now + int(ttl),
                    ),
                )
                conn.commit()
            finally:
                conn.close()

    def get_webui_session(self, jti: str, include_expired: bool = False) -> dict | None:
        """取会话。默认过滤已过期行（expires_at < now）。

        include_expired=True 用于诊断/审计场景；正常鉴权路径应保持默认。
        """
        conn = self._conn()
        try:
            if include_expired:
                row = conn.execute(
                    "SELECT jti, subject, user_agent, ip, created_at, last_seen_at, expires_at "
                    "FROM webui_sessions WHERE jti=?",
                    (str(jti),),
                ).fetchone()
            else:
                row = conn.execute(
                    "SELECT jti, subject, user_agent, ip, created_at, last_seen_at, expires_at "
                    "FROM webui_sessions WHERE jti=? AND expires_at > ?",
                    (str(jti), int(time.time())),
                ).fetchone()
        finally:
            conn.close()
        if not row:
            return None
        d = dict(row)
        d["expires_at"] = int(d["expires_at"])
        d["created_at"] = int(d["created_at"])
        d["last_seen_at"] = int(d["last_seen_at"])
        return d

    def touch_webui_session(self, jti: str) -> bool:
        """滑动续期 last_seen_at。会话不存在或已过期返回 False。"""
        now = int(time.time())
        with _write_lock:
            conn = self._conn()
            try:
                cur = conn.execute(
                    "UPDATE webui_sessions SET last_seen_at=? "
                    "WHERE jti=? AND expires_at > ?",
                    (now, str(jti), now),
                )
                conn.commit()
                return cur.rowcount > 0
            finally:
                conn.close()

    def list_webui_sessions(self) -> list[dict]:
        conn = self._conn()
        try:
            rows = conn.execute(
                "SELECT jti, subject, user_agent, ip, created_at, last_seen_at, expires_at "
                "FROM webui_sessions WHERE expires_at > ? "
                "ORDER BY last_seen_at DESC",
                (int(time.time()),),
            ).fetchall()
        finally:
            conn.close()
        return [dict(r) for r in rows]

    def revoke_webui_session(self, jti: str) -> int:
        with _write_lock:
            conn = self._conn()
            try:
                cur = conn.execute(
                    "DELETE FROM webui_sessions WHERE jti=?",
                    (str(jti),),
                )
                conn.commit()
                return cur.rowcount
            finally:
                conn.close()

    def revoke_all_webui_sessions(self) -> int:
        with _write_lock:
            conn = self._conn()
            try:
                cur = conn.execute("DELETE FROM webui_sessions")
                conn.commit()
                return cur.rowcount
            finally:
                conn.close()

    def purge_expired_webui_sessions(self) -> int:
        with _write_lock:
            conn = self._conn()
            try:
                cur = conn.execute(
                    "DELETE FROM webui_sessions WHERE expires_at < ?",
                    (int(time.time()),),
                )
                conn.commit()
                return cur.rowcount
            finally:
                conn.close()


def _next_date(date_str: str) -> str:
    """YYYY-MM-DD 的下一天（彩票开奖滚存用）。"""
    y, m, d = (int(x) for x in str(date_str).split("-"))
    return (datetime.date(y, m, d) + datetime.timedelta(days=1)).strftime("%Y-%m-%d")
