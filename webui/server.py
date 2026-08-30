"""独立端口 WebUI（aiohttp + JWT + 服务端会话表 + 全量管理API + 静态三文件）。

凭据体系：
- 密码：Argon2id（m=64MiB, t=3, p=4），OWASP 2024 推荐参数，内存硬化抗 GPU 暴力破解
- 令牌：PyJWT HS256 + 服务端会话表 webui_sessions（jti 绑定），支持主动撤销

明文密码不出现在持久化配置中：plugin_config.yaml 存的是 Argon2id 哈希字符串；
首次启动若未设密码则生成 18 位临时密码，明文仅一次性打到启动日志。
"""

import asyncio
import ipaddress
import json
import re
import time
import uuid
from pathlib import Path

import jwt
from aiohttp import web

try:
    from ..core import gamedata as gd
    from ..core import logic
    from ..core.web_auth import hash_password, verify_password
except ImportError:
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from core import gamedata as gd
    from core import logic
    from core.web_auth import hash_password, verify_password

COOKIE = "sbz_session"
TTL = 12 * 3600
JWT_ALG = "HS256"
JWT_ISSUER = "astrbot_plugin_shangbanzu"
# 这些键的值不回传前端；保存时留空 = 保持原值
CONFIG_HIDDEN_KEYS = {"webui_password", "webui_jwt_secret"}
# 无需登录即可访问的路径（其余一律由中间件拦下，新增路由默认受保护）
PUBLIC_PATHS = {
    "/",
    "/webui/style.css",
    "/webui/app.js",
    "/api/meta",
    "/api/auth/login",
    "/api/auth/logout",
    "/api/auth/check",
    "/api/auth/change-password",
}
# 登录失败限流：同一 IP 在窗口内失败达到上限即临时封禁
LOGIN_MAX_FAILS = 5
LOGIN_WINDOW = 300
LOGIN_BLOCK = 300
LOGIN_TRACK_MAX = 512


def _json(obj, status=200):
    return web.Response(
        text=json.dumps(obj, ensure_ascii=False),
        status=status,
        content_type="application/json",
        charset="utf-8",
        headers={"Cache-Control": "no-store"},
    )


def _jti_from_request(request) -> str:
    """从当前 cookie 解码 JWT 拿 jti；任何异常返回空串。"""
    raw = request.cookies.get(COOKIE, "")
    if not raw:
        return ""
    try:
        # 不过期校验：调用方通常已经 _authed 过，这里只取 jti
        claims = jwt.decode(
            raw,
            options={
                "verify_signature": False,
                "verify_exp": False,
                "verify_iss": False,
            },
        )
    except jwt.PyJWTError:
        return ""
    return str(claims.get("jti", "")) if isinstance(claims, dict) else ""


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
        app_id_getter=None,
        jwt_secret: str = "",
        renderer=None,
    ):
        self.db = db
        self.backups = backups
        self.market = market
        # 空 host 不再回落 0.0.0.0：那等于把管理后台暴露到全部网卡
        self.host = host or "127.0.0.1"
        self.port = int(port)
        self.version = version
        self.log = logger
        self.password_stored = str(password or "")  # Argon2id 哈希；_verify_pwd 统一校验
        # QQ 官方机器人的 appid 要到收到第一条消息才知道，所以取回调而非快照
        self._app_id_getter = app_id_getter
        # 实时引用插件配置对象本身（不是快照）：面板读到的永远是当前值
        self._live_config = config_data if isinstance(config_data, dict) else {}
        self.auth_on = bool(self.password_stored)
        # JWT 签名密钥：main.py 启动期持久化到 cfg；缺失则拒启动
        self._jwt_secret = str(jwt_secret or "")
        self._fails: dict[str, list] = {}  # ip -> [失败次数, 窗口起点, 解封时间]
        self.dir = Path(__file__).parent
        self._schema: dict | None = None
        self._schema_mtime: int = -1
        self._runner = None
        self._renderer = renderer  # 用于文案/模板编辑后失效 Jinja2 缓存

    # ===== 认证 =====

    async def _authed(self, request):
        """JWT + 服务端会话表双校验：

        1. JWT 签名/issuer/exp/iat/jti 校验（PyJWT 抛 PyJWTError 即拒绝）
        2. 会话表里 jti 必须存在且未过期
        3. last_seen_at 每 60s 续期一次（避免每请求写库）

        会话表在主库上，同步 sqlite3 一旦撞上 busy_timeout（最长 15s）会把
        整条事件循环卡死、全部群消息停摆，因此所有库操作必须走 to_thread。
        """
        if not self.auth_on:
            return True
        raw = request.cookies.get(COOKIE, "")
        if not raw:
            return False
        try:
            claims = jwt.decode(
                raw,
                self._jwt_secret,
                algorithms=[JWT_ALG],
                issuer=JWT_ISSUER,
                options={"require": ["exp", "iat", "jti"]},
            )
        except jwt.PyJWTError:
            return False
        jti = str(claims.get("jti", ""))
        if not jti:
            return False
        sess = await asyncio.to_thread(self.db.get_webui_session, jti)
        if not sess:
            return False
        now = int(time.time())
        if sess["expires_at"] < now:
            # 过期会话：lazy 清理，避免每请求写库
            try:
                await asyncio.to_thread(self.db.revoke_webui_session, jti)
            except Exception:  # noqa: BLE001
                pass
            return False
        if now - sess["last_seen_at"] > 60:
            try:
                await asyncio.to_thread(self.db.touch_webui_session, jti)
            except Exception:  # noqa: BLE001
                pass  # 续期失败不阻断当前请求
        return True

    def _unauth(self):
        return _json({"error": "未登录"}, 401)

    def _verify_pwd(self, plain: str) -> bool:
        return verify_password(plain, self.password_stored)

    def _c(self, key, default=None):
        """读 WebUI 实例自身的配置偏好：_live_config 是实时引用，operator 在 AstrBot
        / WebUI 里改了立刻可见，无需重启插件。"""
        try:
            v = self._live_config.get(key) if hasattr(self._live_config, "get") else None
        except Exception:  # noqa: BLE001 - 配置对象异常不应让面板打不开
            return default
        return default if v is None else v

    def _app_id(self) -> str:
        try:
            return str(self._app_id_getter() or "") if self._app_id_getter else ""
        except Exception:  # noqa: BLE001 - 头像取不到不影响面板
            return ""

    def _allowed_hosts(self) -> set[str]:
        names = {self.host, "127.0.0.1", "localhost", "::1", "[::1]"}
        return {f"{n}:{self.port}" for n in names if n} | {n for n in names if n}

    def _netloc_ok(self, netloc: str) -> bool:
        """Host / Origin 的 netloc 白名单判定。

        配置为具体地址时维持严格精确匹配；仅当绑定全部网卡
        （webui_host=0.0.0.0 / ::，即局域网访问场景）时，额外放行
        「端口匹配 + IP 字面量或 localhost」的 netloc：

        - 域名一律拒绝：DNS rebinding 与跨站伪造用的都是域名 Host/Origin；
        - 端口必须等于本面板端口：本机其它端口页面借同 IP Origin 打 CSRF
          仍被挡住；
        - 修复前 0.0.0.0 部署的局域网用户 Host 是内网 IP:port，不在
          白名单里，所有请求一律 400，绑定全部网卡等于完全没法远程访问。
        """
        netloc = (netloc or "").strip()
        if not netloc:
            return False
        if netloc in self._allowed_hosts():
            return True
        if str(self.host).strip("[]") not in ("0.0.0.0", "::", ""):
            return False
        # 解析 host[:port]（兼容 [IPv6]:port 写法）
        if netloc.startswith("["):
            inner = netloc[1:].split("]", 1)
            host_part = inner[0]
            rest = inner[1] if len(inner) > 1 else ""
            port_part = rest[1:] if rest.startswith(":") else ""
        elif ":" in netloc:
            host_part, _, port_part = netloc.rpartition(":")
        else:
            host_part, port_part = netloc, ""
        if not port_part.isdigit() or int(port_part) != self.port:
            return False
        hp = host_part.strip("[]").lower()
        if hp == "localhost":
            return True
        try:
            ip = ipaddress.ip_address(hp)
        except ValueError:
            return False  # 域名 Host：拒绝
        return ip.is_loopback or ip.is_private

    def _host_ok(self, request) -> bool:
        """防 DNS rebinding：Host 必须是配置的地址、回环名，或（仅绑定
        全部网卡时）回环/内网 IP 字面量且端口匹配。"""
        host = (request.headers.get("Host") or "").strip()
        if not host:
            return False
        return self._netloc_ok(host)

    def _origin_ok(self, request) -> bool:
        """跨站写保护：带 Origin 时必须同源。

        aiohttp 的 request.json() 不校验 Content-Type，
        没有这道检查时任意网页都能用表单/fetch 打到管理接口。
        """
        origin = request.headers.get("Origin") or ""
        if not origin:
            return True  # 同源的简单请求通常不带 Origin
        try:
            netloc = origin.split("://", 1)[1]
        except IndexError:
            return False
        return self._netloc_ok(netloc)

    @web.middleware
    async def _guard(self, request, handler):
        if not self._host_ok(request):
            return _json({"error": "Host 不被允许"}, 400)
        if request.method not in ("GET", "HEAD") and not self._origin_ok(request):
            return _json({"error": "跨站请求已被拒绝"}, 403)
        # 白名单之外的一切路径默认需要登录：以后新增路由不会忘记加鉴权
        if request.path not in PUBLIC_PATHS and not await self._authed(request):
            return self._unauth()
        return await handler(request)

    def _rate_limited(self, ip: str) -> bool:
        now = time.time()
        rec = self._fails.get(ip)
        if not rec:
            return False
        if rec[2] > now:
            return True
        if now - rec[1] > LOGIN_WINDOW:
            self._fails.pop(ip, None)
        return False

    def _note_fail(self, ip: str):
        now = time.time()
        if len(self._fails) > LOGIN_TRACK_MAX:
            for k, v in list(self._fails.items()):
                if v[2] < now and now - v[1] > LOGIN_WINDOW:
                    self._fails.pop(k, None)
        rec = self._fails.setdefault(ip, [0, now, 0.0])
        if now - rec[1] > LOGIN_WINDOW:
            rec[0], rec[1] = 0, now
        rec[0] += 1
        if rec[0] >= LOGIN_MAX_FAILS:
            rec[2] = now + LOGIN_BLOCK

    async def start(self):
        app = web.Application(middlewares=[self._guard])
        r = app.router
        r.add_get("/", self._index)
        r.add_get("/webui/style.css", self._style_css)
        r.add_get("/webui/app.js", self._app_js)
        r.add_get("/api/meta", self._meta)
        r.add_post("/api/auth/login", self._login)
        r.add_post("/api/auth/logout", self._logout)
        r.add_get("/api/auth/check", self._check)
        r.add_post("/api/auth/change-password", self._change_password)
        r.add_get("/api/auth/sessions", self._list_sessions)
        r.add_post("/api/auth/sessions/revoke", self._revoke_session)
        r.add_get("/api/overview", self._overview)
        r.add_get("/api/groups", self._groups)
        r.add_get("/api/ranking", self._ranking)
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
        r.add_get("/api/admin/json/get", self._json_get)
        r.add_post("/api/admin/json/save", self._json_save)
        r.add_get("/api/admin/players", self._admin_players)
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
        for _attempt in range(3):
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
        return await self._file("index.html", "text/html")

    async def _style_css(self, request):
        return await self._file("style.css", "text/css")

    async def _app_js(self, request):
        return await self._file("app.js", "application/javascript")

    async def _file(self, fname, ctype):
        try:
            body = await asyncio.to_thread((self.dir / fname).read_bytes)
            return web.Response(
                body=body,
                content_type=ctype,
                charset="utf-8",
                headers={
                    "Cache-Control": "no-store",
                    "X-Frame-Options": "DENY",
                    "Referrer-Policy": "no-referrer",
                    "X-Content-Type-Options": "nosniff",
                    # 页面用了内联 onclick，脚本/样式必须放开 inline；
                    # 但外部脚本、内嵌框架、表单外发一律禁掉，
                    # 头像只允许 https/data，杜绝把面板数据带去第三方。
                    "Content-Security-Policy": (
                        "default-src 'self'; "
                        "img-src 'self' https: data:; "
                        "style-src 'self' 'unsafe-inline'; "
                        "script-src 'self' 'unsafe-inline'; "
                        "connect-src 'self'; "
                        "frame-ancestors 'none'; base-uri 'none'; form-action 'none'"
                    ),
                },
            )
        except OSError as e:
            return _json({"error": str(e)}, 500)

    @staticmethod
    async def _body(request) -> dict:
        """统一读 JSON 体：畸形请求返回空 dict，而不是抛 500 带堆栈。"""
        if not request.can_read_body:
            return {}
        try:
            data = await request.json()
        except (ValueError, TypeError):
            return {}
        return data if isinstance(data, dict) else {}

    # ===== 认证 =====

    async def _login(self, request):
        if not self.auth_on:
            return _json({"ok": True, "msg": "未启用密码"})
        ip = request.remote or "?"
        if self._rate_limited(ip):
            return _json({"error": "失败次数过多，请稍后再试"}, 429)
        body = await self._body(request)
        pwd = str(body.get("password", ""))
        # Argon2id 校验是 CPU 密集型（m=64MiB, t=3，约 50~100ms），
        # 直接跑在事件循环上会卡停全部消息处理，必须下放到线程
        if not await asyncio.to_thread(self._verify_pwd, pwd):
            self._note_fail(ip)
            await asyncio.sleep(0.5)
            return _json({"error": "密码错误"}, 401)
        self._fails.pop(ip, None)
        # 启动期临时密码标记：登录后强制改密
        must_change = bool(self._live_config.get("_webui_must_change_password"))
        now = int(time.time())
        jti = uuid.uuid4().hex
        ua = request.headers.get("User-Agent", "")[:256]
        try:
            await asyncio.to_thread(
                self.db.create_webui_session, jti, ip, ua, TTL
            )
        except Exception as e:  # noqa: BLE001 - DB 失败不能让密码错误遮盖真实原因
            self.log.error(f"[上班族物语] 创建会话失败：{e}")
            return _json({"error": "服务器内部错误"}, 500)
        token = jwt.encode(
            {
                "iss": JWT_ISSUER,
                "sub": "admin",
                "jti": jti,
                "iat": now,
                "exp": now + TTL,
            },
            self._jwt_secret,
            algorithm=JWT_ALG,
        )
        resp = _json({"ok": True, "must_change_password": must_change, "jti": jti})
        resp.set_cookie(
            COOKIE,
            token,
            max_age=TTL,
            httponly=True,
            samesite="Lax",
            path="/",
            secure=self.host not in ("127.0.0.1", "localhost", "::1"),
        )
        return resp

    async def _logout(self, request):
        jti = _jti_from_request(request)
        if jti:
            try:
                await asyncio.to_thread(self.db.revoke_webui_session, jti)
            except Exception:  # noqa: BLE001
                pass  # 服务端清理失败不影响客户端登出
        resp = _json({"ok": True})
        resp.del_cookie(COOKIE, path="/")
        return resp

    async def _change_password(self, request):
        """改密：需要已登录 + 提供旧密码 + 新密码。

        成功后：
        - cfg 里 webui_password 改成新密码的 Argon2id 哈希
        - 清掉 _webui_must_change_password 标记
        - 撤销全部活跃会话（含当前会话），强制用新密码重新登录
        - 持久化到 AstrBot 配置（save_config 落盘）
        """
        if not await self._authed(request):
            return self._unauth()
        body = await self._body(request)
        old = str(body.get("old_password", ""))
        new = str(body.get("new_password", ""))
        if not await asyncio.to_thread(self._verify_pwd, old):
            return _json({"error": "旧密码错误"}, 400)
        if len(new) < 8 or new != new.strip():
            return _json({"error": "新密码需 8 位以上且无首尾空格"}, 400)
        if new == old:
            return _json({"error": "新密码不能与旧密码相同"}, 400)
        self.password_stored = await asyncio.to_thread(hash_password, new)
        self._live_config["webui_password"] = self.password_stored
        self._live_config.pop("_webui_must_change_password", None)
        try:
            await asyncio.to_thread(self.db.revoke_all_webui_sessions)
        except Exception as e:  # noqa: BLE001
            self.log.warning(f"[上班族物语] 撤销会话失败：{e}")
        save = getattr(self._live_config, "save_config", None)
        if callable(save):
            try:
                await asyncio.to_thread(save)
            except Exception as e:  # noqa: BLE001
                self.log.warning(f"[上班族物语] 持久化新密码失败：{e}")
        resp = _json({"ok": True, "message": "密码已更新，请用新密码重新登录"})
        resp.del_cookie(COOKIE, path="/")
        return resp

    async def _list_sessions(self, request):
        """返回当前所有活跃会话（含当前设备标记）。"""
        if not await self._authed(request):
            return self._unauth()
        current_jti = _jti_from_request(request)
        try:
            rows = await asyncio.to_thread(self.db.list_webui_sessions)
        except Exception as e:  # noqa: BLE001
            self.log.warning(f"[上班族物语] 列出会话失败：{e}")
            return _json({"sessions": []})
        out = [
            {
                "jti": str(r["jti"]),
                "ip": str(r.get("ip") or ""),
                "user_agent": str(r.get("user_agent") or ""),
                "created_at": int(r["created_at"]),
                "last_seen_at": int(r["last_seen_at"]),
                "expires_at": int(r["expires_at"]),
                "current": str(r["jti"]) == current_jti,
            }
            for r in rows
        ]
        return _json({"sessions": out})

    async def _revoke_session(self, request):
        """撤销单个会话：当前会话则同时清 cookie。"""
        if not await self._authed(request):
            return self._unauth()
        body = await self._body(request)
        target = str(body.get("jti", ""))
        if not target:
            return _json({"error": "缺 jti"}, 400)
        current_jti = _jti_from_request(request)
        try:
            n = await asyncio.to_thread(self.db.revoke_webui_session, target)
        except Exception as e:  # noqa: BLE001
            self.log.warning(f"[上班族物语] 撤销会话失败：{e}")
            return _json({"error": "服务器内部错误"}, 500)
        resp = _json({"ok": True, "revoked": n, "current_revoked": target == current_jti})
        if target == current_jti:
            resp.del_cookie(COOKIE, path="/")
        return resp

    async def _check(self, request):
        ok = (not self.auth_on) or await self._authed(request)
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
        stats = await asyncio.to_thread(self.db.event_stats)
        raw_events = await asyncio.to_thread(self.db.recent_events, 30)
        events = [
            {
                "gid": e["gid"],
                "uid": e["uid"],
                "kind": e["kind"],
                "summary": e["summary"],
                "time": int(e["created_at"]),
            }
            for e in raw_events
        ]
        return _json({"stats": stats, "events": events, "news": gd.news_of_day()})

    async def _groups(self, request):
        names = await asyncio.to_thread(self.db.all_group_names)
        gids = await asyncio.to_thread(self.db.group_ids)
        groups = [
            {"gid": g, "count": n, "name": names.get(g, "")}
            for g, n in gids
        ]
        return _json({"groups": groups})

    async def _ranking(self, request):
        gid = request.query.get("gid", "")
        kind = request.query.get("kind", "wealth")
        if not gid:
            return _json({"error": "缺 gid"}, 400)
        kind = kind if kind in ("wealth", "exp", "value", "level") else "wealth"
        # 与群内榜单同源：都读 ranking_top_n，不再一边 10 条一边 15 条
        top_n = int(self._c("ranking_top_n", 10))
        if kind == "level":
            players = await asyncio.to_thread(self.db.top_level, gid, top_n)
        elif kind == "wealth":
            players = await asyncio.to_thread(self.db.top_wealth, gid, top_n)
        else:
            players = await asyncio.to_thread(
                self.db.top_by_column, gid, "exp" if kind == "exp" else "value", top_n
            )
        rows = []
        names = await self._company_names(gid)
        for p in players:
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
                    "company": gd.display_company(p.get("company", -1), names),
                }
            )
        return _json({"kind": kind, "rows": rows})

    async def _company_names(self, gid) -> dict:
        """本群公司名映射（含自建公司），一次查库供整页复用。"""
        if not gid:
            return gd.company_names()
        rows = await asyncio.to_thread(self.db.custom_companies_of_group, gid)
        return gd.company_names(rows)

    async def _search(self, request):
        gid = request.query.get("gid", "")
        kw = request.query.get("kw", "")
        p = await asyncio.to_thread(self.db.find_player_any, gid, kw) if gid and kw else None
        if not p:
            return _json({"results": []})
        return _json({"results": [self.build_profile(p, await self._company_names(gid))]})

    # ===== 股票 =====

    async def _stock_list(self, request):
        await asyncio.to_thread(self.market.ensure_seeded)
        await self.market.settle_if_needed()
        stocks = await asyncio.to_thread(self.market.list_stocks, 100)
        return _json({"stocks": stocks})

    async def _stock_edit(self, request):
        body = await self._body(request)
        try:
            price = float(body["price"]) if "price" in body else None
            if price is not None and not (0 < price < 1_000_000):
                raise ValueError
        except (TypeError, ValueError):
            return _json({"ok": False, "error": "价格非法"}, 400)
        ok = await asyncio.to_thread(
            self.market.admin_edit,
            str(body.get("code", "")),
            str(body["name"])[:40] if "name" in body else None,
            price,
        )
        return _json({"ok": ok})

    async def _stock_fluctuate(self, request):
        n = await asyncio.to_thread(self.market.admin_fluctuate_all)
        return _json({"ok": True, "fluctuated": n})

    async def _stock_randomize(self, request):
        n = await asyncio.to_thread(self.market.admin_set_price_all_random)
        return _json({"ok": True, "reset": n})

    # ===== 备份 =====

    async def _backup_list(self, request):
        items = await asyncio.to_thread(self.backups.list)
        return _json(
            {
                "backups": [
                    {"name": i["name"], "size_kb": i["size"] // 1024, "time": i["time"]}
                    for i in items
                ]
            }
        )

    async def _backup_create(self, request):
        body = await self._body(request)
        info = await asyncio.to_thread(self.backups.create, str(body.get("label", "")))
        return _json(
            {"ok": True, "name": info["name"], "size_kb": info["size"] // 1024}
        )

    async def _backup_restore(self, request):
        body = await self._body(request)
        item = await asyncio.to_thread(self.backups.restore, str(body.get("name", "")))
        if not item:
            return _json({"error": "未找到（名称需完整）"}, 404)
        if item.get("error"):
            return _json({"error": item["error"]}, 400)
        # 恢复后重跑建表，保证索引/表结构齐全
        await asyncio.to_thread(self.db.init)
        return _json({"ok": True, "restored": item["name"]})

    async def _backup_delete(self, request):
        body = await self._body(request)
        item = await asyncio.to_thread(self.backups.delete, str(body.get("name", "")))
        if not item:
            return _json({"error": "未找到"}, 404)
        return _json({"ok": True, "deleted": item["name"]})

    # ===== 玩家管理 =====

    async def _admin_get(self, request):
        gid = request.query.get("gid", "")
        uid = request.query.get("uid", "")
        p = await asyncio.to_thread(self.db.find_player_any, gid, uid) if gid and uid else None
        if not p:
            return _json({"error": "未找到"}, 404)
        return _json({"profile": self.build_profile(p, await self._company_names(gid))})

    # 可改字段 -> (类型, 下限, 上限)。管理端也必须守住游戏不变式：
    # health/mind 是 0~100 的状态条，金额不设上限会直接把经济系统冲垮。
    EDITABLE = {
        "cash": (float, 0.0, 1e12),
        "deposit": (float, 0.0, 1e12),
        "health": (float, 0.0, 100.0),
        "mind": (float, 0.0, 100.0),
        "exp": (int, 0, 10**9),
        "salary": (float, 0.0, 1e9),
        "fund_savings": (float, 0.0, 1e12),
        "comp_leave": (int, 0, 3650),
        "value": (float, 0.0, 1e12),
    }

    async def _admin_save(self, request):
        body = await self._body(request)
        gid = str(body.get("gid", ""))
        uid = str(body.get("uid", ""))
        p = await asyncio.to_thread(self.db.find_player_any, gid, uid)
        if not p:
            return _json({"error": "未找到"}, 404)
        rejected = []
        for k, (tp, lo, hi) in self.EDITABLE.items():
            if k not in body:
                continue
            try:
                v = tp(body[k])
            except (ValueError, TypeError):
                rejected.append(k)
                continue
            if v != v or v in (float("inf"), float("-inf")):  # NaN / inf
                rejected.append(k)
                continue
            v = max(lo, min(hi, v))
            p[k] = round(v, 2) if tp is float else int(v)
        await asyncio.to_thread(self.db.save_player, p)
        return _json(
            {
                "ok": True,
                "rejected": rejected,
                "profile": self.build_profile(p, await self._company_names(gid)),
            }
        )

    async def _admin_delete(self, request):
        body = await self._body(request)
        gid = str(body.get("gid", ""))
        uid = str(body.get("uid", ""))
        if not gid or not uid:
            return _json({"error": "缺参数"}, 400)
        await asyncio.to_thread(self.db.delete_player, gid, uid)
        return _json({"ok": True})

    # ===== 构建 =====

    async def _schema_async(self) -> dict:
        """读取并缓存配置 schema（磁盘 IO 放线程，别在事件循环上做）。

        运维在面板外改了 _conf_schema.json 后，下次访问 _admin_config 会
        自动重读——按 mtime 检测即可，避免重启插件。
        """
        sp = Path(__file__).resolve().parent.parent / "_conf_schema.json"
        try:
            mtime = int(sp.stat().st_mtime)
        except OSError:
            mtime = 0
        if self._schema is None or self._schema_mtime != mtime:
            self._schema = await asyncio.to_thread(self._load_schema)
            self._schema_mtime = mtime
        return self._schema

    def _load_schema(self) -> dict:
        sp = Path(__file__).resolve().parent.parent / "_conf_schema.json"
        try:
            return json.loads(sp.read_text("utf-8"))
        except (OSError, ValueError):
            return {}

    async def _admin_config(self, request):
        schema = await self._schema_async()
        # 直接读实时配置对象：快照会让面板显示过期值，
        # 并让一次「基于旧表单的保存」把别处的改动写回去
        cfg = {}
        for k, meta in schema.items():
            v = self._live_config.get(k, meta.get("default"))
            cfg[k] = "" if k in CONFIG_HIDDEN_KEYS else v
        return _json(
            {
                "schema": schema,
                "config": cfg,
                "hidden_keys": sorted(CONFIG_HIDDEN_KEYS & set(schema)),
            }
        )

    @staticmethod
    def _coerce(tp: str, raw, meta: dict):
        """按 schema 类型转换并做范围钳制；非法值抛 ValueError/TypeError。"""
        if tp == "bool":
            if isinstance(raw, str):
                raw = raw.strip().lower() in ("1", "true", "on", "yes", "是")
            return bool(raw)
        if tp in ("int", "float"):
            v = float(raw)
            if v != v or v in (float("inf"), float("-inf")):
                raise ValueError("nan/inf")
            lo, hi = meta.get("min"), meta.get("max")
            if lo is not None:
                v = max(float(lo), v)
            if hi is not None:
                v = min(float(hi), v)
            return int(v) if tp == "int" else v
        if tp == "list":
            if isinstance(raw, str):
                raw = [
                    x.strip()
                    for x in raw.replace("，", "\n").replace(",", "\n").split("\n")
                ]
            return [str(x).strip()[:100] for x in raw if str(x).strip()][:200]
        return str(raw).strip()[:500]

    async def _admin_config_save(self, request):
        body = await self._body(request)
        values = body.get("values") or {}
        if not isinstance(values, dict):
            return _json({"error": "bad body"}, 400)
        schema = await self._schema_async()
        target = self._live_config
        applied = 0
        notes: list[str] = []
        pwd_changed = False
        for k, raw in values.items():
            meta = schema.get(k)
            if not meta:
                continue
            try:
                v = self._coerce(meta.get("type", "string"), raw, meta)
            except (TypeError, ValueError):
                continue
            if k == "webui_password":
                # 密码特殊处理：写入 _live_config 的必须是 Argon2id 哈希，明文只活在
                # 本次请求的局部变量里。空串表示"保持原值"，仅本机监听允许显式清空。
                if v == "":
                    cur_host = str(target.get("webui_host") or self.host)
                    if cur_host in ("127.0.0.1", "localhost", "::1"):
                        target[k] = ""
                        applied += 1
                        pwd_changed = True
                    else:
                        notes.append("非本机监听下不允许清空访问密码，已保持原值")
                else:
                    new_hash = (
                        v
                        if v.startswith("$argon2id$")
                        else await asyncio.to_thread(hash_password, v)
                    )
                    if new_hash != self.password_stored:
                        target[k] = new_hash  # 落盘前先写成哈希
                        applied += 1
                        pwd_changed = True
                continue
            if k in CONFIG_HIDDEN_KEYS and v == "":
                # 其余敏感键留空 = 保持原值
                continue
            target[k] = v
            applied += 1
        save = getattr(target, "save_config", None)
        persisted = False
        if callable(save):
            await asyncio.to_thread(save)  # 落盘是同步文件写，别堵事件循环
            persisted = True
        # 密码修改即时生效（无需重载插件）；同时让旧 cookie 全部失效
        if pwd_changed:
            new_pwd = str(target.get("webui_password") or "")
            # 哈希已在上面的循环里写回 target，这里只做内存态同步 + 撤销旧会话。
            # 哈希可能因平台不同而不相等，仅当实际改了口令时才撤销会话，避免每次
            # 保存配置都把管理员踢下线。
            if new_pwd != self.password_stored:
                try:
                    await asyncio.to_thread(self.db.revoke_all_webui_sessions)
                except Exception as e:  # noqa: BLE001
                    self.log.warning(f"[上班族物语] 撤销会话失败：{e}")
                self.password_stored = new_pwd
            self.auth_on = bool(self.password_stored)
        return _json(
            {"ok": True, "applied": applied, "persisted": persisted, "notes": notes}
        )

    async def _admin_companies(self, request):
        return _json({"companies": gd.companies()})

    async def _admin_companies_save(self, request):
        body = await self._body(request)
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
                    "risk": num(raw, "risk", 0.01, 0, 1),
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
        claimed: set[int] = set()
        remap: dict[int, int] = {}
        for i, c in enumerate(cleaned, start=1):
            oid = int(c["id"])
            c["id"] = i
            # 一个旧 ID 只能被一行认领：前端若给新行分配了「已存在的 ID」，
            # 后续行不会再冒充它，避免把被删公司的员工划给一家无关新公司
            if oid > 0 and oid in prev_ids and oid not in claimed:
                claimed.add(oid)
                if oid != i:
                    remap[oid] = i
        unemploy = [oid for oid in sorted(prev_ids) if oid not in claimed]

        cp = (
            Path(__file__).resolve().parent.parent
            / "resources"
            / "data"
            / "companies.json"
        )
        content = json.dumps({"companies": cleaned}, ensure_ascii=False, indent=2)
        await asyncio.to_thread(cp.write_text, content, encoding="utf-8")
        if remap or unemploy:
            await asyncio.to_thread(self.db.remap_company_ids, remap, unemploy)
        await asyncio.to_thread(gd.load_all, force=True)
        return _json({"ok": True, "count": len(cleaned)})

    # ===== 文案 JSON 编辑（resources/texts）=====

    def _texts_root(self) -> Path:
        return Path(__file__).resolve().parent.parent / "resources" / "texts"

    async def _json_get(self, request):
        name = request.query.get("name", "")
        if not re.fullmatch(r"[a-z0-9_]+", name or ""):
            return _json({"error": "bad name"}, 400)
        p = self._texts_root() / f"{name}.json"
        try:
            raw_text = await asyncio.to_thread(p.read_text, "utf-8")
            data = json.loads(raw_text)
        except (OSError, ValueError):
            return _json({"error": "未找到"}, 404)
        return _json({"name": name, "data": data})

    async def _json_save(self, request):
        body = await self._body(request)
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
        content = json.dumps(data, ensure_ascii=False, indent=2)
        target_path = self._texts_root() / f"{name}.json"
        await asyncio.to_thread(target_path.write_text, content, encoding="utf-8")
        await asyncio.to_thread(gd.load_all, force=True)
        # 文案改了 → Jinja2 编译过的模板也要清，否则下次截图仍是旧模板
        if self._renderer is not None and hasattr(self._renderer, "clear_template_cache"):
            self._renderer.clear_template_cache()
        return _json({"ok": True, "keys": len(data)})

    async def _admin_players(self, request):
        gid = request.query.get("gid", "")
        page = logic.parse_int(request.query.get("page", "1"), default=1, lo=1) or 1
        size = 20
        players = await asyncio.to_thread(self.db.all_players, gid) if gid else []
        total = len(players)
        start = (page - 1) * size
        page_data = players[start : start + size]
        names = await self._company_names(gid)
        return _json(
            {
                "total": total,
                "page": page,
                "players": [self.build_profile(p, names) for p in page_data],
            }
        )

    async def _admin_events_clear(self, request):
        # 走 db 层：与游戏内写入共用同一把写锁，不再在这里裸开连接
        n = await asyncio.to_thread(self.db.clear_events)
        return _json({"ok": True, "deleted": n})

    def build_profile(self, p, names: dict | None = None):
        names = names if names is not None else gd.company_names()
        cid = int(p["company"])
        comp_name = gd.display_company(cid, names, jobless="失业中")
        house = gd.house(int(p["house"]))
        disp = p.get("card") or p.get("nickname") or f"用户{p['uid']}"
        return {
            "gid": p["gid"],
            "uid": p["uid"],
            "nickname": disp,
            "avatar": logic.avatar_of(p["uid"], self._app_id()),
            "company": comp_name,
            "tag": "自建企业" if cid >= gd.CUSTOM_BASE else "",
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
