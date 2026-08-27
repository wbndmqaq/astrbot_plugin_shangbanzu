"""SQLite 存储层（标准库 sqlite3，WAL 模式，线程安全：每操作独立连接）。"""

import json
import sqlite3
import threading
import time
from pathlib import Path

_write_lock = threading.Lock()

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


def new_player(
    gid: str, uid: str, nickname: str = "", start_cash: float = 800.0
) -> dict:
    p = {k: v for k, v in DEFAULTS.items()}
    p["gid"] = str(gid)
    p["uid"] = str(uid)
    p["nickname"] = nickname or ""
    p["cash"] = float(start_cash)
    now = int(time.time())
    p["created_at"] = now
    p["updated_at"] = now
    return p


class DB:
    def __init__(self, path):
        self.path = Path(path)

    def init(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = self._conn()
        try:
            conn.executescript(SCHEMA)
            conn.commit()
        finally:
            conn.close()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=15)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=15000")
        return conn

    # ---------- 玩家 ----------

    def get_player(
        self, gid, uid, nickname: str = "", start_cash: float = 800.0
    ) -> dict:
        conn = self._conn()
        try:
            row = conn.execute(
                "SELECT * FROM players WHERE gid=? AND uid=?", (str(gid), str(uid))
            ).fetchone()
        finally:
            conn.close()
        if row is None:
            p = new_player(gid, uid, nickname, start_cash)
            self.save_player(p)
            return p
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
        return p

    def save_player(self, p: dict):
        p = dict(p)
        cds = p.pop("_cds", None)
        if cds is not None:
            p["cds"] = json.dumps(cds, ensure_ascii=False)
        skills = p.pop("_skills", None)
        if skills is not None:
            p["skills"] = json.dumps(skills, ensure_ascii=False)
        p["updated_at"] = int(time.time())
        cols = [c for c in COLUMNS]
        values = [p.get(c, DEFAULTS.get(c, 0)) for c in cols]
        placeholders = ",".join("?" for _ in cols)
        updates = ",".join(f"{c}=?" for c in cols if c not in ("gid", "uid"))
        sql = (
            f"INSERT INTO players ({','.join(cols)}) VALUES ({placeholders}) "
            f"ON CONFLICT(gid,uid) DO UPDATE SET {updates}"
        )
        args = values + [v for c, v in zip(cols, values) if c not in ("gid", "uid")]
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
        assert column in COLUMNS, f"bad column {column}"
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
                conn.execute(
                    "DELETE FROM events WHERE id NOT IN "
                    "(SELECT id FROM events ORDER BY id DESC LIMIT 800)"
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
                conn.execute(
                    "DELETE FROM transactions WHERE gid=? AND uid=? AND id NOT IN "
                    "(SELECT id FROM transactions WHERE gid=? AND uid=? ORDER BY id DESC LIMIT 60)",
                    (str(gid), str(uid), str(gid), str(uid)),
                )
                conn.commit()
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
            today_start = int(time.time()) - int(time.time()) % 86400
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
        y, w = (cur_year, cur_week - 1) if cur_week > 1 else (cur_year - 1, 52)
        data = self.get_archive(gid, y, w)
        if data is None:
            row = self.max_archived_week()
            if row:
                data = self.get_archive(gid, row[0], row[1])
        return data
