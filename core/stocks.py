"""股票市场：100支股票、每日自动波动、买卖与持仓管理。"""

import asyncio
import json
import random
import sqlite3
from pathlib import Path

from .db import _write_lock
from .logic import today_str as _today

SEED_FILE = (
    Path(__file__).resolve().parent.parent / "resources" / "data" / "stocks.json"
)

# 默认单日涨跌幅上下限（±9.8%，模拟 A 股涨跌停），可由配置覆盖
DEFAULT_PCT_LIMIT = 9.8
DEFAULT_DRIFT = 0.15
DEFAULT_VOLATILITY = 3.2
DEFAULT_MIN_PRICE = 0.5


class StockMarket:
    def __init__(self, db, cfg):
        self.db = db
        self.cfg = cfg

    def _c(self, key, default):
        from . import logic

        return logic.cfg_get(self.cfg, key, default)

    def _random_pct(self) -> float:
        """单日涨跌幅（%）。drift 为正即长期持有稳赚，所以三个参数都可配。"""
        drift = float(self._c("stock_drift", DEFAULT_DRIFT))
        vol = abs(float(self._c("stock_volatility", DEFAULT_VOLATILITY)))
        limit = abs(float(self._c("stock_daily_limit_pct", DEFAULT_PCT_LIMIT)))
        return max(-limit, min(limit, random.gauss(drift, vol)))

    def _min_price(self) -> float:
        return max(0.01, float(self._c("stock_min_price", DEFAULT_MIN_PRICE)))

    # ---------- 基础 ----------

    def _conn(self):
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
            with _write_lock:
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
                if not rows:
                    return 0
                floor_price = self._min_price()
                # 与 db.py 共用同一把写锁，保持「所有写入串行」的全局不变式
                with _write_lock:
                    for r in rows:
                        new_price = max(
                            floor_price,
                            round(float(r["price"]) * (1 + self._random_pct() / 100), 2),
                        )
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
        """按金额买入。

        返回 None = 股票不存在或金额非法；"too_many" = 持仓只数超上限；
        False（内部）= 余额不足，会转成 ValueError。
        """
        min_amt = float(self._c("stock_min_buy_amount", 1.0))
        if amount_yuan <= 0 or amount_yuan < min_amt:
            return None
        await self.settle_if_needed()

        def _do():
            # get_stock 会开连接查库，必须留在工作线程里，不能在事件循环上直接调
            st = self.get_stock(key)
            if not st:
                return None
            fee = round(amount_yuan * fee_rate, 2)
            cost = round(amount_yuan + fee, 2)  # 入账总额 = 本金 + 手续费
            # 实际入股的金额按扣除手续费后的净额算份额，但 cost 基线记【含费】，
            # 这样 sell 的 profit = income - 含费均价 与账户上的真实净扣款一致。
            # （以前只扣本金、cost 记本金，导致手续费既没入账也没入 portfolio，
            # 玩家每笔买入都会"凭空"留下 fee，相当于全游戏隐形通胀口。）
            net_amount = round(amount_yuan - fee, 2)
            shares = round(net_amount / st["price"], 4)
            max_pos = int(self._c("stock_max_positions", 50))
            conn = self._conn()
            try:
                with _write_lock:
                    # 原子扣款：余额不足时 rowcount=0
                    cur = conn.execute(
                        "UPDATE players SET cash=round(cash-?,2) "
                        "WHERE gid=? AND uid=? AND cash>=?",
                        (cost, str(gid), str(uid), cost),
                    )
                    if cur.rowcount == 0:
                        conn.rollback()
                        return False
                    row = conn.execute(
                        "SELECT shares, cost FROM portfolio WHERE gid=? AND uid=? AND code=?",
                        (str(gid), str(uid), st["code"]),
                    ).fetchone()
                    if not row:
                        # 新开一只仓位前检查只数上限：用单条 INSERT WHERE NOT EXISTS
                        # 避免两次并发 buy 都看到「当前持仓 N < max」然后都 INSERT，
                        # 导致 portfolio 持仓只数悄悄越过 max_pos。
                        inserted = conn.execute(
                            "INSERT INTO portfolio (gid,uid,code,shares,cost) "
                            "SELECT ?,?,?,?,? WHERE "
                            "(SELECT COUNT(*) FROM portfolio WHERE gid=? AND uid=? AND shares>0) < ?",
                            (
                                str(gid), str(uid), st["code"], shares, cost,
                                str(gid), str(uid), max_pos,
                            ),
                        )
                        if inserted.rowcount == 0:
                            conn.rollback()
                            return "too_many"
                    if row:
                        ns = round(float(row["shares"]) + shares, 4)
                        nc = round(float(row["cost"]) + cost, 2)
                        conn.execute(
                            "UPDATE portfolio SET shares=?, cost=? WHERE gid=? AND uid=? AND code=?",
                            (ns, nc, str(gid), str(uid), st["code"]),
                        )
                    # 注：新建仓位分支在上面用条件 INSERT 完成
                    conn.commit()
                return {
                    "stock": st,
                    "shares": shares,
                    "amount": amount_yuan,
                    "fee": fee,
                }
            finally:
                conn.close()

        res = await asyncio.to_thread(_do)
        if res is None or res == "too_many":
            return res
        if res is False:
            raise ValueError("现金不足")
        return res

    async def sell(
        self, gid, uid, key: str, ratio: float, fee_rate: float
    ) -> dict | None:
        if ratio <= 0:
            return None
        await self.settle_if_needed()

        def _do():
            # 持仓读取、份额计算、删/改仓与入账全部放在同一事务里：
            # 旧实现先在事务外读持仓再凭快照写回，两条并发卖出同一仓位会
            # 各自按旧份额清算、双双入账（清仓时 DELETE 均不校验 rowcount）。
            st = self.get_stock(key)
            if not st:
                return None
            conn = self._conn()
            try:
                with _write_lock:
                    row = conn.execute(
                        "SELECT shares, cost FROM portfolio WHERE gid=? AND uid=? AND code=?",
                        (str(gid), str(uid), st["code"]),
                    ).fetchone()
                    if not row:
                        return None
                    shares = float(row["shares"])
                    if shares <= 0:
                        return None
                    sell_shares = round(shares * ratio, 4)
                    # 极小仓位按比例取整后可能归零：按全仓卖出，避免残留灰尘份额
                    if sell_shares <= 0:
                        sell_shares = shares
                    sell_shares = min(sell_shares, shares)
                    cash = round(sell_shares * st["price"], 2)
                    fee = round(cash * fee_rate, 2)
                    income = round(max(0.0, cash - fee), 2)
                    remain = round(shares - sell_shares, 4)
                    remain_cost = (
                        round(float(row["cost"]) * (remain / shares), 2)
                        if shares
                        else 0.0
                    )
                    if remain <= 0:
                        conn.execute(
                            "DELETE FROM portfolio WHERE gid=? AND uid=? AND code=?",
                            (str(gid), str(uid), st["code"]),
                        )
                    else:
                        conn.execute(
                            "UPDATE portfolio SET shares=?, cost=? WHERE gid=? AND uid=? AND code=?",
                            (remain, remain_cost, str(gid), str(uid), st["code"]),
                        )
                    # 同事务入账到账金额
                    conn.execute(
                        "UPDATE players SET cash=round(cash+?,2) WHERE gid=? AND uid=?",
                        (income, str(gid), str(uid)),
                    )
                    conn.commit()
                avg_cost = round(float(row["cost"]) / shares, 2) if shares else 0.0
                return {
                    "name": st["name"],
                    "shares": sell_shares,
                    "income": income,
                    "fee": fee,
                    "profit": round(income - avg_cost * sell_shares, 2),
                }
            finally:
                conn.close()

        return await asyncio.to_thread(_do)

    async def position_of(self, gid, uid, key: str) -> dict | None:
        def _do():
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
        return await asyncio.to_thread(_do)

    async def my_positions(self, gid, uid) -> list[dict]:
        def _do():
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
        return await asyncio.to_thread(_do)

    # ---------- 管理端 ----------

    def admin_edit(
        self, code: str, name: str | None = None, price: float | None = None
    ) -> bool:
        conn = self._conn()
        try:
            with _write_lock:
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
            floor = self._min_price()
            with _write_lock:
                for r in rows:
                    np_ = round(
                        max(floor, float(r["price"]) * (1 + self._random_pct() / 100)), 2
                    )
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
            rows = conn.execute("SELECT code FROM stocks").fetchall()
            with _write_lock:
                for r in rows:
                    base = round(
                        random.uniform(
                            float(self._c("stock_reset_price_min", 6.0)),
                            float(self._c("stock_reset_price_max", 180.0)),
                        ),
                        2,
                    )
                    conn.execute(
                        "UPDATE stocks SET price=?, prev=? WHERE code=?",
                        (base, base, r["code"]),
                    )
                conn.commit()
            return len(rows)
        finally:
            conn.close()
