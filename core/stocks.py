"""股票市场：100支股票、每日自动波动、买卖与持仓管理。"""

import asyncio
import json
import random
import time
from pathlib import Path

SEED_FILE = (
    Path(__file__).resolve().parent.parent / "resources" / "data" / "stocks.json"
)


def _today() -> str:
    return time.strftime("%Y-%m-%d")


def _clamp_pct(v: float) -> float:
    return max(-9.8, min(9.8, v))


class StockMarket:
    def __init__(self, db, cfg):
        self.db = db
        self.cfg = cfg

    # ---------- 基础 ----------

    def _conn(self):
        import sqlite3

        conn = sqlite3.connect(self.db.path, timeout=15)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout=15000")
        return conn

    def ensure_seeded(self):
        """首次使用时从 stocks.json 播种 100 支股票。"""
        conn = self._conn()
        try:
            n = conn.execute("SELECT COUNT(*) FROM stocks").fetchone()[0]
            if n >= 100:
                return
            if not SEED_FILE.exists():
                return
            data = json.loads(SEED_FILE.read_text(encoding="utf-8"))
            today = _today()
            for s in data["stocks"]:
                conn.execute(
                    "INSERT OR IGNORE INTO stocks (code,name,sector,price,prev,day) "
                    "VALUES (?,?,?,?,?,?)",
                    (
                        s["code"],
                        s["name"],
                        s.get("sector", ""),
                        s["price"],
                        s["price"],
                        today,
                    ),
                )
            conn.commit()
        finally:
            conn.close()

    # ---------- 每日波动 ----------

    async def settle_if_needed(self) -> int:
        """懒结算：跨天后的第一次访问触发全部未结算股票的价格更新。"""
        today = _today()

        def _do():
            conn = self._conn()
            try:
                rows = conn.execute(
                    "SELECT code, price FROM stocks WHERE day != ?", (today,)
                ).fetchall()
                for r in rows:
                    pct = random.gauss(0.15, 3.2)
                    pct = max(-9.8, min(9.8, pct))
                    new_price = round(float(r["price"]) * (1 + pct / 100), 2)
                    new_price = max(new_price, 0.5)
                    conn.execute(
                        "UPDATE stocks SET prev=price, price=?, day=? WHERE code=?",
                        (new_price, today, r["code"]),
                    )
                conn.commit()
                return len(rows)
            finally:
                conn.close()

        return await asyncio.to_thread(_do)

    # ---------- 查询 ----------

    def list_stocks(self, limit: int = 100) -> list[dict]:
        conn = self._conn()
        try:
            rows = conn.execute(
                "SELECT * FROM stocks ORDER BY code LIMIT ?", (limit,)
            ).fetchall()
        finally:
            conn.close()
        out = []
        for r in rows:
            chg = (
                round(
                    (float(r["price"]) - float(r["prev"])) / float(r["prev"]) * 100, 2
                )
                if float(r["prev"])
                else 0.0
            )
            out.append(
                {
                    "code": r["code"],
                    "name": r["name"],
                    "sector": r["sector"],
                    "price": float(r["price"]),
                    "prev": float(r["prev"]),
                    "chg": chg,
                }
            )
        return out

    def get_stock(self, key: str) -> dict | None:
        k = str(key).strip()
        conn = self._conn()
        try:
            r = conn.execute(
                "SELECT * FROM stocks WHERE code=? OR name=? OR name LIKE ? LIMIT 1",
                (k, k, f"%{k}%"),
            ).fetchone()
        finally:
            conn.close()
        if not r:
            return None
        chg = (
            round((float(r["price"]) - float(r["prev"])) / float(r["prev"]) * 100, 2)
            if float(r["prev"])
            else 0.0
        )
        return {
            "code": r["code"],
            "name": r["name"],
            "price": float(r["price"]),
            "chg": chg,
        }

    # ---------- 交易 ----------

    async def buy(
        self, gid, uid, key: str, amount_yuan: float, fee_rate: float
    ) -> dict | None:
        """按金额买入。股票不存在/金额非法返回 None；余额不足抛 ValueError。"""
        await self.settle_if_needed()
        st = self.get_stock(key)
        if not st or amount_yuan <= 0:
            return None
        fee = round(amount_yuan * fee_rate, 2)
        shares = round((amount_yuan - fee) / st["price"], 4)

        def _do():
            conn = self._conn()
            try:
                # 原子扣款：余额不足时 rowcount=0
                cur = conn.execute(
                    "UPDATE players SET cash=round(cash-?,2) "
                    "WHERE gid=? AND uid=? AND cash>=?",
                    (amount_yuan, str(gid), str(uid), amount_yuan),
                )
                if cur.rowcount == 0:
                    conn.rollback()
                    return False
                row = conn.execute(
                    "SELECT shares, cost FROM portfolio WHERE gid=? AND uid=? AND code=?",
                    (str(gid), str(uid), st["code"]),
                ).fetchone()
                if row:
                    ns = round(float(row["shares"]) + shares, 4)
                    nc = round(float(row["cost"]) + amount_yuan, 2)
                    conn.execute(
                        "UPDATE portfolio SET shares=?, cost=? WHERE gid=? AND uid=? AND code=?",
                        (ns, nc, str(gid), str(uid), st["code"]),
                    )
                else:
                    conn.execute(
                        "INSERT INTO portfolio (gid,uid,code,shares,cost) VALUES (?,?,?,?,?)",
                        (str(gid), str(uid), st["code"], shares, amount_yuan),
                    )
                conn.commit()
                return True
            finally:
                conn.close()

        ok = await asyncio.to_thread(_do)
        if not ok:
            raise ValueError("现金不足")
        return {"stock": st, "shares": shares, "amount": amount_yuan, "fee": fee}

    async def sell(
        self, gid, uid, key: str, ratio: float, fee_rate: float
    ) -> dict | None:
        if ratio <= 0:
            return None
        await self.settle_if_needed()
        pos = await self.position_of(gid, uid, key)
        if not pos:
            return None
        sell_shares = round(pos["shares"] * ratio, 4)
        if sell_shares <= 0:
            return None
        cash = round(sell_shares * pos["cur_price"], 2)
        fee = round(cash * fee_rate, 2)
        income = round(max(0.0, cash - fee), 2)

        remain = round(pos["shares"] - sell_shares, 4)
        remain_cost = (
            round(pos["total_cost"] * (remain / pos["shares"]), 2)
            if pos["shares"]
            else 0.0
        )

        def _do():
            conn = self._conn()
            try:
                if remain <= 0:
                    conn.execute(
                        "DELETE FROM portfolio WHERE gid=? AND uid=? AND code=?",
                        (str(gid), str(uid), pos["code"]),
                    )
                else:
                    conn.execute(
                        "UPDATE portfolio SET shares=?, cost=? WHERE gid=? AND uid=? AND code=?",
                        (remain, remain_cost, str(gid), str(uid), pos["code"]),
                    )
                # 同事务入账到账金额
                conn.execute(
                    "UPDATE players SET cash=round(cash+?,2) WHERE gid=? AND uid=?",
                    (income, str(gid), str(uid)),
                )
                conn.commit()
            finally:
                conn.close()

        await asyncio.to_thread(_do)
        profit = round(income - pos["avg_cost"] * sell_shares, 2)
        return {
            "name": pos["name"],
            "shares": sell_shares,
            "income": income,
            "fee": fee,
            "profit": profit,
        }

    async def position_of(self, gid, uid, key: str) -> dict | None:
        st = self.get_stock(key)
        if not st:
            return None
        conn = self._conn()
        try:
            r = conn.execute(
                "SELECT shares, cost FROM portfolio WHERE gid=? AND uid=? AND code=?",
                (str(gid), str(uid), st["code"]),
            ).fetchone()
        finally:
            conn.close()
        if not r:
            return None
        shares = float(r["shares"])
        cost = float(r["cost"])
        return {
            "code": st["code"],
            "name": st["name"],
            "shares": shares,
            "cur_price": st["price"],
            "avg_cost": round(cost / shares, 2) if shares else 0,
            "total_cost": cost,
            "market_value": round(shares * st["price"], 2),
        }

    async def my_positions(self, gid, uid) -> list[dict]:
        conn = self._conn()
        try:
            rows = conn.execute(
                "SELECT code, shares, cost FROM portfolio WHERE gid=? AND uid=? "
                "AND shares > 0 ORDER BY cost DESC",
                (str(gid), str(uid)),
            ).fetchall()
        finally:
            conn.close()
        out = []
        for r in rows:
            st = self.get_stock(r["code"])
            if st:
                out.append(
                    {
                        "code": st["code"],
                        "name": st["name"],
                        "shares": round(float(r["shares"]), 4),
                        "cur_price": st["price"],
                        "market_value": round(float(r["shares"]) * st["price"], 2),
                    }
                )
        return out

    # ---------- 管理端 ----------

    def admin_edit(
        self, code: str, name: str | None = None, price: float | None = None
    ) -> bool:
        conn = self._conn()
        try:
            if name is not None and price is not None:
                conn.execute(
                    "UPDATE stocks SET name=?, price=? WHERE code=?",
                    (name, price, code),
                )
            elif name is not None:
                conn.execute("UPDATE stocks SET name=? WHERE code=?", (name, code))
            elif price is not None:
                conn.execute(
                    "UPDATE stocks SET price=?, day=? WHERE code=?",
                    (price, _today(), code),
                )
            else:
                return False
            conn.commit()
            return True
        finally:
            conn.close()

    def admin_fluctuate_all(self) -> int:
        """强制全部股票立刻波动一次（无视日期）。"""
        conn = self._conn()
        try:
            rows = conn.execute("SELECT code, price FROM stocks").fetchall()
            for r in rows:
                pct = random.gauss(0.15, 3.2)
                pct = max(-9.8, min(9.8, pct))
                np_ = round(max(0.5, float(r["price"]) * (1 + pct / 100)), 2)
                conn.execute(
                    "UPDATE stocks SET prev=price, price=? WHERE code=?",
                    (np_, r["code"]),
                )
            conn.commit()
            return len(rows)
        finally:
            conn.close()

    def admin_set_price_all_random(self) -> int:
        conn = self._conn()
        try:
            rows = conn.execute("SELECT code, price FROM stocks").fetchall()
            for r in rows:
                base = random.uniform(6, 180)
                conn.execute(
                    "UPDATE stocks SET price=?, prev=? WHERE code=?",
                    (round(base, 2), round(base, 2), r["code"]),
                )
            conn.commit()
            return len(rows)
        finally:
            conn.close()
