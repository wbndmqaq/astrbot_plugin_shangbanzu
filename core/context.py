"""运行时上下文：给各指令模块提供统一的工具入口，避免直接耦合 Star。"""

import asyncio
import re
import time

import astrbot.api.message_components as Comp
from astrbot.api import logger

from . import logic

# 缓存容量与 TTL 的默认值，可由插件配置覆盖
DEFAULT_MAX_UMOS = 2000
DEFAULT_CARD_CACHE_MAX = 2000
DEFAULT_CARD_TTL_MINUTES = 10
DEFAULT_GROUP_TTL_MINUTES = 30


class GameCtx:
    def __init__(self, star, db, config):
        self.star = star
        self.db = db
        self.config = config
        self._card_cache = {}  # (gid, uid) -> (expire_ts, card)
        self.umos = {}  # gid -> unified_msg_origin（推送用，指令触发时刷新）
        self.app_id = ""  # QQ 官方机器人的 appid（用于拼接开放平台头像）
        self.max_umos = max(1, int(self.c("max_session_cache", DEFAULT_MAX_UMOS)))
        self.card_cache_max = max(
            16, int(self.c("card_cache_max", DEFAULT_CARD_CACHE_MAX))
        )
        self.card_ttl = max(
            10.0, float(self.c("card_cache_ttl_minutes", DEFAULT_CARD_TTL_MINUTES)) * 60
        )
        self.group_ttl = max(
            10.0,
            float(self.c("group_name_cache_ttl_minutes", DEFAULT_GROUP_TTL_MINUTES)) * 60,
        )

    def avatar(self, uid) -> str:
        return logic.avatar_of(uid, self.app_id)

    def c(self, key, default=None):
        return logic.cfg_get(self.config, key, default)

    def exempt(self, uid) -> bool:
        ids = [str(x) for x in (self.c("cooldown_exempt_users") or [])]
        return str(uid) in ids

    @staticmethod
    def log_error(where: str, exc: BaseException):
        """路由兜底异常：带堆栈落日志，用户侧只看到一句友好提示。"""
        logger.error(f"[上班族物语] 指令 {where} 执行异常：{exc}", exc_info=True)

    def nick(self, event, uid=None):
        """同步版本：仅从内存缓存/消息事件取昵称，绝不落 DB（避免阻塞事件循环）。

        需要读数据库的调用方请改用 await self.anick(event, uid)。
        """
        uid = str(uid) if uid else str(event.get_sender_id())
        gid = event.get_group_id()
        if gid:
            hit = self._card_cache.get((str(gid), uid))
            if hit and hit[1]:
                return hit[1]
        name = ""
        if uid == str(event.get_sender_id()):
            name = event.get_sender_name() or ""
        if not name:
            for comp in event.get_messages():
                if isinstance(comp, Comp.At) and str(comp.qq) == uid:
                    name = getattr(comp, "name", "") or ""
                    if name:
                        break
        return name or f"用户{uid}"

    async def anick(self, event, uid=None):
        """异步版本：内存缓存 → 线程化 DB（昵称/群名片）→ 事件提取兜底。"""
        uid = str(uid) if uid else str(event.get_sender_id())
        gid = event.get_group_id()
        if gid:
            hit = self._card_cache.get((str(gid), uid))
            if hit and hit[1]:
                return hit[1]
        name = ""
        if gid:
            p = await asyncio.to_thread(self.db.find_player_any, gid, uid)
            if p and p.get("card"):
                return p["card"]
            if p and p.get("nickname"):
                name = p["nickname"]
        if not name and uid == str(event.get_sender_id()):
            name = event.get_sender_name() or ""
        if not name:
            for comp in event.get_messages():
                if isinstance(comp, Comp.At) and str(comp.qq) == uid:
                    name = getattr(comp, "name", "") or ""
                    if name:
                        break
        return name or f"用户{uid}"

    @staticmethod
    def ats(event) -> list[str]:
        out = []
        self_id = str(event.get_self_id())
        for comp in event.get_messages():
            if isinstance(comp, Comp.At):
                qq = str(comp.qq)
                if qq and qq != "all" and qq != self_id and qq not in out:
                    out.append(qq)
        return out

    @staticmethod
    def nums(event, words: tuple[str, ...]) -> list[str]:
        s = event.message_str or ""
        for w in sorted(words, key=len, reverse=True):
            s = s.replace(w, " ")
        return re.findall(r"\d+", s)

    def target(self, event, words: tuple[str, ...]):
        ats = self.ats(event)
        if ats:
            return ats[0]
        nums = self.nums(event, words)
        return nums[0] if nums else ""

    async def find_target(self, gid, keyword):
        """把「@某人 / 数字 ID / 昵称关键字」解析成【已入档】的玩家行。

        返回 None 表示对方还没玩过本插件——调用方必须据此拒绝，
        否则 get_player 会顺手给一个不存在的 ID 建号（可用来刷对线胜场）。
        """
        kw = str(keyword or "").strip()
        if not gid or not kw:
            return None
        return await asyncio.to_thread(self.db.find_player_any, gid, kw)

    async def render(self, template, data):
        return await self.star._render(template, data)

    # ------------------------------------------------------------------
    # 群昵称拉取：aiocqhttp 走 OneBot API；QQ官方走官方 HTTP 接口（ATK鉴权
    # 由 botpy 的 BotHttp 自动管理 access_token）。
    # ------------------------------------------------------------------

    # 昵称拉取整体超时：平台网关无响应时不能把用户的指令协程一直挂住
    CARD_FETCH_TIMEOUT = 5.0

    async def refresh_card(self, event, extra_uids=()):
        """拉取发送者与 @ 目标的群名片/昵称；任何失败静默，不影响指令。"""
        gid = event.get_group_id()
        if not gid:
            return
        try:
            await asyncio.wait_for(
                self._refresh_card_impl(event, gid, extra_uids),
                timeout=self.CARD_FETCH_TIMEOUT,
            )
        except (TimeoutError, asyncio.TimeoutError):
            logger.debug("[上班族物语] 昵称拉取超时，已跳过")
        except Exception:  # noqa: BLE001 - 昵称只是显示优化，绝不影响指令
            pass

    async def _refresh_card_impl(self, event, gid, extra_uids):
        # umo 登记是同步操作且位于首个 await 之前：即使拉取超时被取消，
        # 推送用的会话定位也一定已经记录完成
        umo = getattr(event, "unified_msg_origin", None)
        if umo:
            if len(self.umos) >= self.max_umos and str(gid) not in self.umos:
                # 丢掉最早记录的会话（dict 保序），只影响这些群的定时推送
                self.umos.pop(next(iter(self.umos)), None)
            self.umos[str(gid)] = umo
        bot = getattr(event, "bot", None)
        if bot is None:
            return

        # 尝试提取 QQ 官方平台的 appid
        appid = (
            getattr(bot, "appid", None)
            or getattr(bot, "bot_appid", None)
            or getattr(bot, "client_id", None)
        )
        if not appid and hasattr(bot, "_http"):
            appid = getattr(bot._http, "appid", None) or getattr(bot._http, "bot_appid", None)
        if not appid and hasattr(bot, "api") and hasattr(bot.api, "_http"):
            appid = getattr(bot.api._http, "appid", None) or getattr(bot.api._http, "bot_appid", None)
        if appid:
            self.app_id = str(appid)

        api = getattr(bot, "api", None)
        if hasattr(api, "call_action"):
            await self._refresh_card_onebot(event, gid, bot, extra_uids)
            return

        # 优先使用 bot.api 上的 _http，或 bot 自身绑定的 _http
        http = getattr(api, "_http", None) or getattr(bot, "_http", None)
        if http is not None:
            await self._refresh_card_qqofficial(event, gid, http, extra_uids)

    async def _collect_uids(self, event, extra_uids) -> list[str]:
        uids = [str(event.get_sender_id())]
        for comp in event.get_messages():
            if getattr(comp, "type", "") == "At":
                qq = str(getattr(comp, "qq", ""))
                if qq and qq != "all" and qq != str(event.get_self_id()):
                    uids.append(qq)
        for uid in extra_uids or ():
            if uid:
                uids.append(str(uid))
        seen: set[str] = set()
        out = []
        for uid in uids:
            if uid not in seen:
                seen.add(uid)
                out.append(uid)
        return out

    def _cache_set(self, key, expire_ts, val, now):
        # 缓存容量保护，避免大型群/多群环境内存泄露
        cap = self.card_cache_max
        if len(self._card_cache) > cap:
            for k in [k for k, v in self._card_cache.items() if v[0] <= now]:
                self._card_cache.pop(k, None)
            if len(self._card_cache) > cap:
                for k in list(self._card_cache.keys())[: max(1, cap // 4)]:
                    self._card_cache.pop(k, None)
        self._card_cache[key] = (expire_ts, val)

    async def _refresh_card_onebot(self, event, gid, bot, extra_uids):
        now = time.time()
        uids = await self._collect_uids(event, extra_uids)

        for uid in uids:
            key = (str(gid), uid)
            hit = self._card_cache.get(key)
            if hit and hit[0] > now:
                continue
            # ---- 1. 群名片 (OneBot / aiocqhttp) ----
            if str(gid).isdigit() and str(uid).isdigit():
                try:
                    info = await bot.api.call_action(
                        "get_group_member_info",
                        group_id=int(gid),
                        user_id=int(uid),
                        no_cache=False,
                    )
                    card = (info.get("card") or info.get("nickname") or "").strip()
                    if card:
                        self._cache_set(key, now + self.card_ttl, card, now)
                        await asyncio.to_thread(self.db.set_card, gid, uid, card)
                        continue
                except Exception:  # noqa: BLE001, S110
                    pass

            # ---- 2. 群名片兜底 (OneBot get_group_name) ----
            gkey = ("__grp__", str(gid))
            if str(gid).isdigit() and not (
                self._card_cache.get(gkey) and self._card_cache[gkey][0] > now
            ):
                try:
                    ginfo = await bot.api.call_action("get_group_info", group_id=int(gid), no_cache=False)
                    gname = (ginfo.get("group_name") or "").strip()
                    if gname:
                        self._cache_set(gkey, now + self.group_ttl, gname, now)
                        await asyncio.to_thread(self.db.set_group_name, gid, gname)
                except Exception:  # noqa: BLE001
                    self._cache_set(gkey, now + self.group_ttl / 3, "", now)

            self._cache_set(key, now + self.card_ttl / 2, "", now)

    async def _refresh_card_qqofficial(self, event, gid, http, extra_uids):
        """QQ 官方平台：
        - 群名：GET /v2/groups/{group_openid}/info 拉取并缓存入库，
          WebUI 显示真实群名；
        - 成员昵称：探测灰度接口 /v2/groups/{g}/members/{openid}，
          未开放时静默负缓存。
        """
        try:
            from botpy.http import Route
        except ImportError:  # 非 official 安装不含 botpy
            return

        now = time.time()

        # ---- 群名 ----
        gkey = ("__grp__", str(gid))
        hit = self._card_cache.get(gkey)
        if not (hit and hit[0] > now):
            try:
                route = Route(
                    "GET", "/v2/groups/{group_openid}/info",
                    group_openid=str(gid),
                )
                info = await http.request(route)
                name = str((info or {}).get("group_name") or "").strip()
                if name:
                    self._cache_set(gkey, now + self.group_ttl, name, now)
                    await asyncio.to_thread(
                        self.db.set_group_name, gid, name
                    )
                else:
                    self._cache_set(gkey, now + self.group_ttl / 2, "", now)
            except Exception:  # noqa: BLE001
                self._cache_set(gkey, now + self.group_ttl / 3, "", now)

        # ---- 用户昵称（群场景：探测灰度接口 /v2/groups/{g}/members/{openid}）----
        uids = await self._collect_uids(event, extra_uids)
        await self._fetch_group_nicks(http, gid, uids, now)

    @staticmethod
    def _pick_nick(item: dict, uid: str) -> str:
        """从频道/群成员信息里尽力提取昵称。"""
        user = item.get("user") or {}
        uid_in_user = user.get("id")
        if uid and uid_in_user and str(uid_in_user) != uid:
            return ""
        return str(
            item.get("nick")
            or item.get("nickname")
            or item.get("card")
            or user.get("username")
            or user.get("nickname")
            or ""
        ).strip()

    async def _fetch_group_nicks(self, http, gid, uids, now):
        from botpy.http import Route

        for uid in uids:
            key = (str(gid), uid)
            hit = self._card_cache.get(key)
            if hit and hit[0] > now:
                continue
            card = ""
            try:
                route = Route(
                    "GET",
                    "/v2/groups/{group_openid}/members/{member_openid}",
                    group_openid=str(gid), member_openid=uid,
                )
                info = await http.request(route)
                if isinstance(info, dict) and info:
                    card = self._pick_nick(
                        {k: v for k, v in info.items()
                         if k not in ("member_openid", "join_timestamp")},
                        uid,
                    )
            except Exception as e:  # noqa: BLE001
                logger.debug(f"[上班族物语] 群成员昵称探测未开放：{e}")
            await self._store_card(gid, uid, card, now)

    async def _store_card(self, gid, uid, card, now):
        key = (str(gid), str(uid))
        if card:
            self._cache_set(key, now + self.card_ttl, card, now)
            await asyncio.to_thread(self.db.set_card, gid, uid, card)
        else:
            self._cache_set(key, now + self.card_ttl / 2, "", now)

