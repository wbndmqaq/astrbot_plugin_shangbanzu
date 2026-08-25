"""独立端口 WebUI（aiohttp + HMAC认证 + 全量管理API + 静态三文件）。"""

import asyncio
import hashlib
import hmac
import json
import re
import secrets
import time
from pathlib import Path

from aiohttp import web

try:
    from ..core import gamedata as gd
    from ..core import logic
except ImportError:
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from core import gamedata as gd
    from core import logic

COOKIE = "sbz_session"
TTL = 12 * 3600
# 这些键的值不回传前端；保存时留空 = 保持原值
CONFIG_HIDDEN_KEYS = {"webui_password"}


def _json(obj, status=200):
    return web.Response(
        text=json.dumps(obj, ensure_ascii=False),
        status=status,
        content_type="application/json",
        charset="utf-8",
        headers={"Access-Control-Allow-Origin": "*", "Cache-Control": "no-store"},
    )


class WebUIServer:
    def __init__(
        self,
        db,
        backups,
        market,
        host,
        port,
        version,
        logger,
        password="",
        config_data: dict | None = None,
    ):
        self.db = db
        self.backups = backups
        self.market = market
        self.host = host or "0.0.0.0"
        self.port = int(port)
        self.version = version
        self.log = logger
        self.password = str(password or "")
        self._live_config = config_data if isinstance(config_data, dict) else {}
        self._config_data = dict(self._live_config)
        self.auth_on = bool(self.password)
        self._secret = secrets.token_hex(32)
        self.dir = Path(__file__).parent
        self._runner = None

    def _token(self, exp):
        sig = hmac.new(
            self._secret.encode(), b"sbz:" + str(exp).encode(), hashlib.sha256
        ).hexdigest()
        return f"{exp}.{sig}"

    def _authed(self, request):
        if not self.auth_on:
            return True
        raw = request.cookies.get(COOKIE, "")
        parts = raw.split(".", 1)
        if len(parts) != 2:
            return False
        try:
            exp = int(parts[0])
        except ValueError:
            return False
        if exp < int(time.time()):
            return False
        expect = hmac.new(
            self._secret.encode(), b"sbz:" + str(exp).encode(), hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(parts[1], expect)

    def _unauth(self):
        return _json({"error": "未登录"}, 401)

    async def start(self):
        app = web.Application()
        r = app.router
        r.add_get("/", self._index)
        r.add_get("/webui/style.css", self._style_css)
        r.add_get("/webui/app.js", self._app_js)
        r.add_get("/api/meta", self._meta)
        r.add_post("/api/auth/login", self._login)
        r.add_post("/api/auth/logout", self._logout)
        r.add_get("/api/auth/check", self._check)
        r.add_get("/api/overview", self._overview)
        r.add_get("/api/groups", self._groups)
        r.add_get("/api/news", self._news)
        r.add_get("/api/ranking", self._ranking)
        r.add_get("/api/player", self._player)
        r.add_get("/api/search", self._search)
        r.add_get("/api/stocks", self._stock_list)
        r.add_post("/api/stocks/edit", self._stock_edit)
        r.add_post("/api/stocks/fluctuate", self._stock_fluctuate)
        r.add_post("/api/stocks/randomize", self._stock_randomize)
        r.add_get("/api/backups", self._backup_list)
        r.add_post("/api/backups/create", self._backup_create)
        r.add_post("/api/backups/restore", self._backup_restore)
        r.add_post("/api/backups/delete", self._backup_delete)
        r.add_get("/api/admin/player", self._admin_get)
        r.add_get("/api/admin/config", self._admin_config)
        r.add_post("/api/admin/config/save", self._admin_config_save)
        r.add_get("/api/admin/companies", self._admin_companies)
        r.add_post("/api/admin/companies/save", self._admin_companies_save)
        r.add_get("/api/admin/json/list", self._json_list)
        r.add_get("/api/admin/json/get", self._json_get)
        r.add_post("/api/admin/json/save", self._json_save)
        r.add_get("/api/admin/players", self._admin_players)
        r.add_get("/api/admin/push", self._admin_push)
        r.add_post("/api/admin/push/toggle", self._admin_push_toggle)
        r.add_post("/api/admin/events/clear", self._admin_events_clear)
        r.add_post("/api/admin/player/save", self._admin_save)
        r.add_post("/api/admin/player/delete", self._admin_delete)
        self._runner = web.AppRunner(
            app,
            access_log=None,
            shutdown_timeout=2,  # 不等 keep-alive 长连接，快速释放端口
        )
        await self._runner.setup()
        # 跨平台自愈：仅对「端口占用(EADDRINUSE/10048)」做短重试——旧实例
        # 完全释放前有一小段失败窗口。注意：
        # - PermissionError(10013)=端口被系统保留(Hyper-V/WSL)或防火墙拦截，
        #   重试无意义，立即失败并在上层给出可操作提示；
        # - 每轮必须新建 TCPSite——失败的 site 已注册进 runner，复用会报重复注册。
        last_exc: Exception | None = None
        for attempt in range(3):
            site = web.TCPSite(
                self._runner, self.host, self.port, reuse_address=True
            )
            try:
                await site.start()
                return
            except PermissionError as e:
                last_exc = e
                break
            except OSError as e:
                last_exc = e
                await asyncio.sleep(0.6)
        await self._runner.cleanup()
        self._runner = None
        raise last_exc  # type: ignore[misc]

    async def stop(self):
        if self._runner:
            runner, self._runner = self._runner, None
            try:
                await asyncio.wait_for(runner.cleanup(), timeout=10)
            except asyncio.TimeoutError:
                pass  # 强制返回，端口交由系统回收

    # ===== 静态文件 =====

    async def _index(self, request):
        return self._file("index.html", "text/html")

    async def _style_css(self, request):
        return self._file("style.css", "text/css")

    async def _app_js(self, request):
        return self._file("app.js", "application/javascript")

    def _file(self, fname, ctype):
        try:
            body = (self.dir / fname).read_bytes()
            return web.Response(
                body=body,
                content_type=ctype,
                charset="utf-8",
                headers={"Cache-Control": "no-store"},
            )
        except OSError as e:
            return _json({"error": str(e)}, 500)

    # ===== 认证 =====

    async def _login(self, request):
        body = await request.json() if request.can_read_body else {}
        pwd = str(body.get("password", ""))
        if not self.auth_on:
            return _json({"ok": True, "msg": "未启用密码"})
        if hmac.compare_digest(pwd.encode("utf-8"), self.password.encode("utf-8")):
            exp = int(time.time()) + TTL
            resp = _json({"ok": True})
            resp.set_cookie(
                COOKIE,
                self._token(exp),
                max_age=TTL,
                httponly=True,
                samesite="Lax",
                path="/",
            )
            return resp
        await asyncio.sleep(0.5)
        return _json({"error": "密码错误"}, 401)

    async def _logout(self, request):
        resp = _json({"ok": True})
        resp.del_cookie(COOKIE, path="/")
        return resp

    async def _check(self, request):
        ok = (not self.auth_on) or self._authed(request)
        return _json({"required": self.auth_on, "ok": ok})

    # ===== 公开 =====

    async def _meta(self, request):
        return _json(
            {
                "name": "astrbot_plugin_shangbanzu",
                "display": "打工人·上班族物语",
                "version": self.version,
                "port": self.port,
                "auth_required": self.auth_on,
                "now": int(time.time()),
            }
        )

    # ===== 鉴权端点 =====

    async def _overview(self, request):
        if not self._authed(request):
            return self._unauth()
        stats = self.db.event_stats()
        events = [
            {
                "gid": e["gid"],
                "uid": e["uid"],
                "kind": e["kind"],
                "summary": e["summary"],
                "time": int(e["created_at"]),
            }
            for e in self.db.recent_events(30)
        ]
        return _json({"stats": stats, "events": events, "news": gd.news_of_day()})

    async def _groups(self, request):
        if not self._authed(request):
            return self._unauth()
        names = self.db.all_group_names()
        groups = [
            {"gid": g, "count": n, "name": names.get(g, "")}
            for g, n in self.db.group_ids()
        ]
        return _json({"groups": groups})

    async def _news(self, request):
        if not self._authed(request):
            return self._unauth()
        return _json({"news": gd.news_of_day()})

    async def _ranking(self, request):
        if not self._authed(request):
            return self._unauth()
        gid = request.query.get("gid", "")
        kind = request.query.get("kind", "wealth")
        if not gid:
            return _json({"error": "缺 gid"}, 400)
        kind = kind if kind in ("wealth", "exp", "value", "level") else "wealth"
        players = (
            self.db.top_level(gid, 15)
            if kind == "level"
            else self.db.top_wealth(gid, 15)
            if kind == "wealth"
            else self.db.top_by_column(gid, "exp" if kind == "exp" else "value", 15)
        )
        rows = []
        for p in players:
            comp = gd.company_by_id(int(p.get("company", -1)))
            pos = gd.position(int(p.get("lvl", 1)))["title"]
            if kind == "level":
                score = f"L{p['lvl']} · {pos}"
            elif kind == "exp":
                score = f"{p['exp']} 点"
            elif kind == "wealth":
                score = logic.fmt_money(p.get("total", 0))
            else:
                score = logic.fmt_money(p["value"])
            rows.append(
                {
                    "rank": p.get("rank", 0),
                    "uid": p["uid"],
                    "nickname": p.get("card") or p["nickname"] or f"用户{p['uid']}",
                    "score": score,
                    "position": pos,
                    "company": comp["name"] if comp else "无业",
                }
            )
        return _json({"kind": kind, "rows": rows})

    async def _player(self, request):
        if not self._authed(request):
            return self._unauth()
        gid = request.query.get("gid", "")
        uid = request.query.get("uid", "")
        p = self.db.find_player_any(gid, uid) if gid and uid else None
        if not p:
            return _json({"error": "未找到"}, 404)
        return _json(self.build_profile(p))

    async def _search(self, request):
        if not self._authed(request):
            return self._unauth()
        gid = request.query.get("gid", "")
        kw = request.query.get("kw", "")
        p = self.db.find_player_any(gid, kw) if gid and kw else None
        return _json({"results": [self.build_profile(p)] if p else []})

    # ===== 股票 =====

    async def _stock_list(self, request):
        if not self._authed(request):
            return self._unauth()
        await asyncio.to_thread(self.market.ensure_seeded)
        await self.market.settle_if_needed()
        return _json({"stocks": self.market.list_stocks(100)})

    async def _stock_edit(self, request):
        if not self._authed(request):
            return self._unauth()
        body = await request.json()
        ok = self.market.admin_edit(
            str(body.get("code", "")),
            str(body["name"]) if "name" in body else None,
            float(body["price"]) if "price" in body else None,
        )
        return _json({"ok": ok})

    async def _stock_fluctuate(self, request):
        if not self._authed(request):
            return self._unauth()
        n = await asyncio.to_thread(self.market.admin_fluctuate_all)
        return _json({"ok": True, "fluctuated": n})

    async def _stock_randomize(self, request):
        if not self._authed(request):
            return self._unauth()
        n = await asyncio.to_thread(self.market.admin_set_price_all_random)
        return _json({"ok": True, "reset": n})

    # ===== 备份 =====

    async def _backup_list(self, request):
        if not self._authed(request):
            return self._unauth()
        items = self.backups.list()
        return _json(
            {
                "backups": [
                    {"name": i["name"], "size_kb": i["size"] // 1024, "time": i["time"]}
                    for i in items
                ]
            }
        )

    async def _backup_create(self, request):
        if not self._authed(request):
            return self._unauth()
        body = await request.json() if request.can_read_body else {}
        info = await asyncio.to_thread(self.backups.create, str(body.get("label", "")))
        return _json(
            {"ok": True, "name": info["name"], "size_kb": info["size"] // 1024}
        )

    async def _backup_restore(self, request):
        if not self._authed(request):
            return self._unauth()
        body = await request.json()
        item = await asyncio.to_thread(self.backups.restore, str(body.get("name", "")))
        if not item:
            return _json({"error": "未找到"}, 404)
        return _json({"ok": True, "restored": item["name"]})

    async def _backup_delete(self, request):
        if not self._authed(request):
            return self._unauth()
        body = await request.json()
        item = await asyncio.to_thread(self.backups.delete, str(body.get("name", "")))
        if not item:
            return _json({"error": "未找到"}, 404)
        return _json({"ok": True, "deleted": item["name"]})

    # ===== 玩家管理 =====

    async def _admin_get(self, request):
        if not self._authed(request):
            return self._unauth()
        gid = request.query.get("gid", "")
        uid = request.query.get("uid", "")
        p = self.db.find_player_any(gid, uid) if gid and uid else None
        if not p:
            return _json({"error": "未找到"}, 404)
        return _json({"profile": self.build_profile(p)})

    async def _admin_save(self, request):
        if not self._authed(request):
            return self._unauth()
        body = await request.json()
        gid = str(body.get("gid", ""))
        uid = str(body.get("uid", ""))
        p = self.db.find_player_any(gid, uid)
        if not p:
            return _json({"error": "未找到"}, 404)
        allowed = {
            "cash": float,
            "deposit": float,
            "health": float,
            "mind": float,
            "exp": int,
            "salary": float,
            "fund_savings": float,
            "comp_leave": int,
            "value": float,
        }
        for k, tp in allowed.items():
            if k in body:
                try:
                    p[k] = round(tp(body[k]), 2) if tp is float else int(body[k])
                except (ValueError, TypeError):
                    pass
        self.db.save_player(p)
        return _json({"ok": True, "profile": self.build_profile(p)})

    async def _admin_delete(self, request):
        if not self._authed(request):
            return self._unauth()
        body = await request.json()
        gid = str(body.get("gid", ""))
        uid = str(body.get("uid", ""))
        if not gid or not uid:
            return _json({"error": "缺参数"}, 400)
        self.db.delete_player(gid, uid)
        return _json({"ok": True})

    # ===== 构建 =====

    def _load_schema(self) -> dict:
        import json as _j

        sp = Path(__file__).resolve().parent.parent / "_conf_schema.json"
        try:
            return _j.loads(sp.read_text("utf-8"))
        except (OSError, ValueError):
            return {}

    async def _admin_config(self, request):
        if not self._authed(request):
            return self._unauth()
        schema = self._load_schema()
        cfg = {}
        for k, meta in schema.items():
            v = self._config_data.get(k, meta.get("default"))
            cfg[k] = "" if k in CONFIG_HIDDEN_KEYS else v
        return _json(
            {
                "schema": schema,
                "config": cfg,
                "hidden_keys": sorted(CONFIG_HIDDEN_KEYS & set(schema)),
            }
        )

    async def _admin_config_save(self, request):
        if not self._authed(request):
            return self._unauth()
        body = await request.json()
        values = body.get("values") or {}
        if not isinstance(values, dict):
            return _json({"error": "bad body"}, 400)
        schema = self._load_schema()
        target = self._live_config
        applied = 0
        for k, raw in values.items():
            meta = schema.get(k)
            if not meta:
                continue
            tp = meta.get("type", "string")
            try:
                if tp == "bool":
                    if isinstance(raw, str):
                        raw = raw.strip().lower() in ("1", "true", "on", "yes", "是")
                    v = bool(raw)
                elif tp == "int":
                    v = int(float(raw))
                elif tp == "float":
                    v = float(raw)
                elif tp == "list":
                    if isinstance(raw, str):
                        raw = [
                            x.strip()
                            for x in raw.replace("，", "\n").replace(",", "\n").split("\n")
                        ]
                    v = [str(x).strip() for x in raw if str(x).strip()]
                else:
                    v = str(raw).strip()
            except (TypeError, ValueError):
                continue
            if k in CONFIG_HIDDEN_KEYS and v == "":
                continue  # 敏感键留空 = 保持原值
            target[k] = v
            applied += 1
        save = getattr(target, "save_config", None)
        persisted = False
        if callable(save):
            save()
            persisted = True
        self._config_data = dict(target)
        # 密码修改即时生效（无需重载插件）
        if "webui_password" in values:
            self.password = str(target.get("webui_password") or "")
            self.auth_on = bool(self.password)
        return _json({"ok": True, "applied": applied, "persisted": persisted})

    async def _admin_companies(self, request):
        if not self._authed(request):
            return self._unauth()
        return _json({"companies": gd.companies()})

    async def _admin_companies_save(self, request):
        if not self._authed(request):
            return self._unauth()
        body = await request.json()
        raw_list = body.get("companies", [])
        if not isinstance(raw_list, list) or not raw_list:
            return _json({"error": "empty"}, 400)

        def num(raw, key, default, lo, hi):
            try:
                v = float(raw.get(key, default))
            except (TypeError, ValueError):
                v = float(default)
            return round(min(hi, max(lo, v)), 4)

        cleaned: list[dict] = []
        seen_names: set[str] = set()
        for raw in raw_list:
            if not isinstance(raw, dict):
                continue
            name = str(raw.get("name") or "").strip()[:40]
            if not name or name in seen_names:
                continue
            seen_names.add(name)
            cleaned.append(
                {
                    "id": int(raw.get("id") or 0),
                    "name": name,
                    "tag": str(raw.get("tag") or "综合").strip()[:12],
                    "salary": num(raw, "salary", 3500, 0, 9_999_999),
                    "intensity": num(raw, "intensity", 5, 0, 24),
                    "risk": num(raw, "risk", 0.01, 0, 100),
                    "min_exp": int(num(raw, "min_exp", 0, 0, 999_999)),
                    "desc": str(raw.get("desc") or "").strip()[:120],
                    "perks": [str(x).strip()[:30] for x in (raw.get("perks") or [])][:6],
                }
            )
        if not cleaned:
            return _json({"error": "empty"}, 400)

        # 规律性保证：按薪资升序排列后统一重编号为 1..N
        cleaned.sort(key=lambda c: (c["salary"], c["min_exp"], c["name"]))
        prev_ids = {int(c["id"]) for c in gd.companies()}
        submitted: list[int] = []
        remap: dict[int, int] = {}
        for i, c in enumerate(cleaned, start=1):
            oid = int(c["id"])
            c["id"] = i
            if oid > 0 and oid in prev_ids:
                submitted.append(oid)
                if oid != i:
                    remap[oid] = i
        unemploy = [oid for oid in sorted(prev_ids) if oid not in submitted]
        # 清理重编号后的重复值（新行临时 ID 撞上已有 ID 时）
        remap = {k: v for k, v in remap.items() if k != v}

        cp = (
            Path(__file__).resolve().parent.parent
            / "resources"
            / "data"
            / "companies.json"
        )
        import json as _j

        cp.write_text(
            _j.dumps({"companies": cleaned}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        if remap or unemploy:
            await asyncio.to_thread(self.db.remap_company_ids, remap, unemploy)
        gd.load_all(force=True)
        return _json({"ok": True, "count": len(cleaned)})

    # ===== 文案 JSON 编辑（resources/texts）=====

    def _texts_root(self) -> Path:
        return Path(__file__).resolve().parent.parent / "resources" / "texts"

    async def _json_list(self, request):
        if not self._authed(request):
            return self._unauth()
        import json as _j

        files = []
        for p in sorted(self._texts_root().glob("*.json")):
            try:
                d = _j.loads(p.read_text("utf-8"))
            except (OSError, ValueError):
                continue
            if isinstance(d, dict):
                files.append({"name": p.stem, "keys": len(d)})
        return _json({"files": files})

    async def _json_get(self, request):
        if not self._authed(request):
            return self._unauth()
        import json as _j

        name = request.query.get("name", "")
        if not re.fullmatch(r"[a-z0-9_]+", name or ""):
            return _json({"error": "bad name"}, 400)
        p = self._texts_root() / f"{name}.json"
        try:
            data = _j.loads(p.read_text("utf-8"))
        except (OSError, ValueError):
            return _json({"error": "未找到"}, 404)
        return _json({"name": name, "data": data})

    async def _json_save(self, request):
        if not self._authed(request):
            return self._unauth()
        body = await request.json()
        name = str(body.get("name") or "")
        data = body.get("data")
        if not re.fullmatch(r"[a-z0-9_]+", name):
            return _json({"error": "bad name"}, 400)
        if not isinstance(data, dict) or not data:
            return _json({"error": "empty"}, 400)
        for k, v in data.items():
            if not isinstance(k, str) or not re.fullmatch(r"[A-Za-z0-9_]+", k):
                return _json({"error": f"非法键名：{str(k)[:30]}"}, 400)
            if not isinstance(v, list):
                return _json({"error": f"键 {k} 的值必须是数组"}, 400)
        import json as _j

        (self._texts_root() / f"{name}.json").write_text(
            _j.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        gd.load_all(force=True)
        return _json({"ok": True, "keys": len(data)})

    async def _admin_players(self, request):
        if not self._authed(request):
            return self._unauth()
        gid = request.query.get("gid", "")
        page = int(request.query.get("page", "1"))
        size = 20
        players = await asyncio.to_thread(self.db.all_players, gid) if gid else []
        total = len(players)
        start = (page - 1) * size
        page_data = players[start : start + size]
        return _json(
            {
                "total": total,
                "page": page,
                "players": [self.build_profile(p) for p in page_data],
            }
        )

    async def _admin_push(self, request):
        if not self._authed(request):
            return self._unauth()
        gids = self.db.push_group_ids()
        return _json({"enabled_groups": gids})

    async def _admin_push_toggle(self, request):
        if not self._authed(request):
            return self._unauth()
        body = await request.json()
        gid = str(body.get("gid", ""))
        if not gid:
            return _json({"error": "缺 gid"}, 400)
        cur = self.db.push_enabled(gid)
        self.db.set_push(gid, not cur)
        return _json({"ok": True, "enabled": not cur})

    async def _admin_events_clear(self, request):
        if not self._authed(request):
            return self._unauth()
        import sqlite3

        conn = sqlite3.connect(self.db.path, timeout=15)
        try:
            conn.execute("DELETE FROM events")
            conn.commit()
        finally:
            conn.close()
        return _json({"ok": True})

    def build_profile(self, p):
        comp = gd.company_by_id(int(p["company"]))
        house = gd.house(int(p["house"]))
        disp = p.get("card") or p.get("nickname") or f"用户{p['uid']}"
        return {
            "gid": p["gid"],
            "uid": p["uid"],
            "nickname": disp,
            "avatar": logic.avatar_of(p["uid"]),
            "company": comp["name"] if comp else "失业中",
            "tag": comp["tag"] if comp else "",
            "position": gd.position(int(p["lvl"]))["title"],
            "salary": logic.fmt_money(p["salary"]),
            "exp": int(p["exp"]),
            "health": float(p["health"]),
            "mind": float(p["mind"]),
            "house": {"name": house["name"], "rent": house["rent"]},
            "cash": logic.fmt_money(p["cash"]),
            "deposit": logic.fmt_money(p["deposit"]),
            "fund": logic.fmt_money(p["fund"]),
            "total": logic.fmt_money(
                round(float(p["cash"]) + float(p["deposit"]) + float(p["fund"]), 2)
            ),
            "value": logic.fmt_money(p["value"]),
            "streak": int(p["attend_streak"]),
            "duel": f"{p['duel_wins']}胜{p['duel_losses']}负",
            "tier": f"{p['rank_tier']}（{p['rank_score']}分）",
            "commute": p.get("commute", "地铁"),
            "fund_savings": logic.fmt_money(p.get("fund_savings") or 0),
            "comp_leave": int(p.get("comp_leave") or 0),
            "updated": int(p["updated_at"]),
        }
