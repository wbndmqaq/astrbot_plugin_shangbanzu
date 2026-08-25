"""运行时上下文：给各指令模块提供统一的工具入口，避免直接耦合 Star。"""

import asyncio

import astrbot.api.message_components as Comp
from astrbot.api import logger

from . import logic


class GameCtx:
    def __init__(self, star, db, config):
        self.star = star
        self.db = db
        self.config = config
        self._card_cache = {}  # (gid, uid) -> (expire_ts, card)

    def c(self, key, default=None):
        return logic.cfg_get(self.config, key, default)

    def exempt(self, uid) -> bool:
        ids = [str(x) for x in (self.c("cooldown_exempt_users") or [])]
        return str(uid) in ids

    def nick(self, event, uid=None):
        uid = str(uid) if uid else str(event.get_sender_id())
        name = ""
        if uid == str(event.get_sender_id()):
            name = event.get_sender_name() or ""
        if not name:
            for comp in event.get_messages():
                if isinstance(comp, Comp.At) and str(comp.qq) == uid:
                    name = getattr(comp, "name", "") or ""
                    if name:
                        break
        return name

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
        import re

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

    async def render(self, template, data):
        return await self.star._render(template, data)

    # ------------------------------------------------------------------
    # 群昵称拉取：aiocqhttp 走 OneBot API；QQ官方走官方 HTTP 接口（ATK鉴权
    # 由 botpy 的 BotHttp 自动管理 access_token）。
    # ------------------------------------------------------------------

    async def refresh_card(self, event, extra_uids=()):
        gid = event.get_group_id()
        if not gid:
            return
        bot = getattr(event, "bot", None)
        if bot is None:
            return

        api = getattr(bot, "api", None)
        if hasattr(api, "call_action"):
            await self._refresh_card_onebot(event, gid, bot, extra_uids)
            return
        http = getattr(api, "_http", None)
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

    async def _refresh_card_onebot(self, event, gid, bot, extra_uids):
        import time as _t

        now = _t.time()
        uids = [str(event.get_sender_id())]
        for comp in event.get_messages():
            if getattr(comp, "type", "") == "At":
                qq = str(getattr(comp, "qq", ""))
                if qq and qq != "all" and qq != str(event.get_self_id()):
                    uids.append(qq)
        for uid in extra_uids or ():
            if uid:
                uids.append(str(uid))

        seen = set()
        for uid in uids:
            key = (str(gid), uid)
            hit = self._card_cache.get(key)
            if hit and hit[0] > now:
                continue
            if uid in seen:
                pass
            seen.add(uid)
            try:
                info = await bot.api.call_action(
                    "get_group_member_info",
                    group_id=int(gid),
                    user_id=int(uid),
                    no_cache=False,
                )
                card = (info.get("card") or "").strip()
                if card:
                    self._card_cache[key] = (now + 600, card)
                    await asyncio.to_thread(self.db.set_card, gid, uid, card)
                else:
                    self._card_cache[key] = (now + 300, "")
            except Exception:  # noqa: BLE001 - 拉取失败不影响指令执行
                self._card_cache[key] = (now + 120, "")

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

        import time as _t

        now = _t.time()

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
                    self._card_cache[gkey] = (now + 1800, name)
                    await asyncio.to_thread(
                        self.db.set_group_name, gid, name
                    )
                else:
                    self._card_cache[gkey] = (now + 900, "")
            except Exception:  # noqa: BLE001
                self._card_cache[gkey] = (now + 600, "")

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
                    # 灰度接口字段未知，尽力提取；仅含 openid/时间戳时取不到
                    card = self._pick_nick(
                        {k: v for k, v in info.items()
                         if k not in ("member_openid", "join_timestamp")},
                        "",
                    )
            except Exception as e:  # noqa: BLE001 - 未开放(403/404等)静默
                logger.debug(f"[上班族物语] 群成员昵称探测未开放：{e}")
            await self._store_card(gid, uid, card, now)

    async def _store_card(self, gid, uid, card, now):
        if card:
            self._card_cache[(str(gid), str(uid))] = (now + 600, card)
            await asyncio.to_thread(self.db.set_card, gid, uid, card)
        else:
            self._card_cache[(str(gid), str(uid))] = (now + 300, "")
