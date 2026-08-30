"""打工人·上班族物语 —— AstrBot 群聊职场生存模拟插件（模块化主入口）。

架构：
    main.py            仅保留插件生命周期 + 输出渲染，指令通过声明式路由安装
    handlers/          指令路由表（按域拆分：职业/主雇/对抗/生活/理财/系统/管理）
    core/              业务服务层 + 存储与数据 + Playwright 渲染器
    webui/             独立端口 WebUI 面板（aiohttp）
    resources/         游戏文本 JSON / 静态数据 JSON / HTML 渲染模板

依赖：
    playwright（需执行一次 python -m playwright install chromium）
    aiohttp、jinja2

说明：
    AstrBot 以 handler.__module__ 与插件主模块做【精确匹配】来绑定插件实例
    （star_handler.get_handlers_by_module_name），因此 handlers/ 中的路由函数
    在装饰前由 install() 将 __module__ 重写为本模块路径。
"""

import asyncio
import time
from pathlib import Path

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, MessageChain, filter
from astrbot.api.star import Context, Star

try:
    from .core import gamedata as gd
    from .core import logic
    from .core.backup import BackupManager
    from .core.context import GameCtx
    from .core.db import DB
    from .core.renderer import PlaywrightRenderer
    from .core.stocks import StockMarket
    from .core.web_auth import hash_password, random_password, random_jwt_secret
    from .handlers import ALL_ROUTES
    from .handlers import install as install_routes
    from .webui.server import WebUIServer
except ImportError:  # 兼容以文件方式直接加载的旧版内核
    import sys

    sys.path.insert(0, str(Path(__file__).parent))
    from core import gamedata as gd
    from core import logic
    from core.context import GameCtx
    from core.db import DB
    from core.renderer import PlaywrightRenderer
    from core.stocks import StockMarket
    from handlers import ALL_ROUTES
    from handlers import install as install_routes
    from webui.server import WebUIServer

PLUGIN_NAME = "astrbot_plugin_shangbanzu"
VERSION = "1.0.2"


def _fmt_draw_lines(result: dict) -> list:
    from .core import logic as _logic
    from .core.lottery import TIER_NAMES, fmt_draw

    lines = [
        "🎰 一夜暴富梦双色球开奖啦！",
        f"开奖号码：{fmt_draw(result['number'])}（共 {result['ticket_count']} 注参与）",
    ]
    winners = result.get("winners") or []
    for tier in ("jackpot", "second", "third"):
        ws = [w for w in winners if w["tier"] == tier]
        if ws:
            names = "、".join(
                f"{w['name']}(+{_logic.fmt_money(w['amount'])})" for w in ws[:6]
            )
            more = f" 等 {len(ws)} 人" if len(ws) > 6 else ""
            lines.append(f"🎉 {TIER_NAMES[tier]}：{names}{more}")
        else:
            lines.append(f"{TIER_NAMES[tier]}：无人命中，滚存下期")
    lines.append(
        f"本期派奖 {result['paid']} 元，滚存 {result['carry']} 元 —— 头奖越滚越大！"
    )
    lines.append("（发送「买彩票 3 7 12 5」自选一注冲击下期）")
    return lines


class Shangbanzu(Star):
    def __init__(self, context: Context, config: AstrBotConfig | None = None):
        super().__init__(context)
        self.config = config or {}
        self.db = DB(self._data_dir() / "shangbanzu.db", cfg=self.config)
        self.ctx = GameCtx(self, self.db, self.config)
        self.renderer = PlaywrightRenderer(
            self._data_dir() / "screenshots",
            scale=float(logic.cfg_get(self.config, "render_scale", 2.0)),
            logger=logger,
            max_concurrency=int(logic.cfg_get(self.config, "render_max_concurrency", 3)),
            max_keep=int(logic.cfg_get(self.config, "screenshot_max_keep", 60)),
            viewport_width=int(logic.cfg_get(self.config, "render_viewport_width", 780)),
            timeout_ms=int(logic.cfg_get(self.config, "render_timeout_ms", 15000)),
        )
        self.market = StockMarket(self.db, self.config)
        self._webui = None
        self._push_task = None
        self._last_cleanup_day = ""
        self.backups = BackupManager(
            self._data_dir() / "shangbanzu.db",
            self._data_dir() / "backups",
            logger,
            max_keep=int(logic.cfg_get(self.config, "backup_max_keep", 20)),
        )

    async def initialize(self):
        await asyncio.to_thread(self.db.init)
        await asyncio.to_thread(gd.load_all)  # 异步预热并全量载入静态游戏数据至内存
        await asyncio.to_thread(self.market.ensure_seeded)
        if bool(logic.cfg_get(self.config, "webui_enabled", True)):
            await self._start_webui()
        self._push_task = asyncio.create_task(self._push_loop())
        logger.info(f"[上班族物语] 插件已加载，共注册 {len(ALL_ROUTES)} 条指令路由")

    async def _start_webui(self):
        host = str(logic.cfg_get(self.config, "webui_host", "127.0.0.1") or "127.0.0.1")
        port = int(logic.cfg_get(self.config, "webui_port", 17817))
        stored = str(logic.cfg_get(self.config, "webui_password", "") or "")
        # 自动密码模式：
        #   - 未配置（空字符串）
        #   - 仍是旧 PBKDF2 哈希（pbkdf2$ 前缀）—— 不再做透明升级，老哈希作废
        # 任一情况都生成临时密码 → 哈希后写回 cfg → 启动 WebUI → 一次性打印到日志
        bootstrap = False
        temp_pwd = None
        if not stored or stored.startswith("pbkdf2$"):
            temp_pwd = random_password()
            self.config["webui_password"] = await asyncio.to_thread(
                hash_password, temp_pwd
            )
            stored = self.config["webui_password"]
            bootstrap = True
            self.config["_webui_must_change_password"] = True
            # 立即落盘：不能依赖后面 jwt_secret 分支"恰好需要保存"来兜底持久化，
            # 否则用户预填过 webui_jwt_secret 时临时密码哈希不落盘，
            # 每次重启都会重新生成一个新临时密码
            save = getattr(self.config, "save_config", None)
            if callable(save):
                try:
                    await asyncio.to_thread(save)
                except Exception as e:  # noqa: BLE001
                    logger.warning(f"[上班族物语] 持久化临时密码哈希失败：{e}")
        # 明文提交即哈希：旧部署若直接填了明文，自动哈希化一次（仅识别非 $argon2id$ 与非 pbkdf2$ 字符串）。
        # 已废弃的 pbkdf2$ 前缀落到上面的 bootstrap 分支处理。
        elif not stored.startswith("$argon2id$"):
            self.config["webui_password"] = await asyncio.to_thread(
                hash_password, stored
            )
            stored = self.config["webui_password"]
            save = getattr(self.config, "save_config", None)
            if callable(save):
                try:
                    await asyncio.to_thread(save)
                except Exception as e:  # noqa: BLE001
                    logger.warning(f"[上班族物语] 自动迁移明文密码为哈希失败：{e}")
        # JWT 签名密钥：首次启动生成 32 字节 hex，持久化到 cfg（重启后旧 JWT 仍可验）
        jwt_secret = str(self.config.get("webui_jwt_secret") or "")
        if not jwt_secret:
            jwt_secret = random_jwt_secret()
            self.config["webui_jwt_secret"] = jwt_secret
            save = getattr(self.config, "save_config", None)
            if callable(save):
                try:
                    await asyncio.to_thread(save)
                except Exception as e:  # noqa: BLE001
                    logger.warning(f"[上班族物语] 持久化 JWT 密钥失败：{e}")
        self._webui = WebUIServer(
            self.db,
            self.backups,
            self.market,
            host,
            port,
            self._get_version(),
            logger,
            password=stored,
            config_data=self.config,
            app_id_getter=lambda: self.ctx.app_id,
            jwt_secret=jwt_secret,
            renderer=self.renderer,
        )
        try:
            await self._webui.start()
            if bootstrap:
                # 临时密码只在启动瞬间打印一次（明文），配置里存的是 Argon2id 哈希
                border = "=" * 60
                msg = (
                    f"\n{border}\n"
                    "[上班族物语] WebUI 首次启动：自动生成 18 位临时密码（仅显示一次）。\n"
                    f"      临时密码：{temp_pwd}\n"
                    f"      访问地址：http://{host}:{port}\n"
                    "      用临时密码登录后请立即在「插件配置」页改密。\n"
                    "      密码以 Argon2id 哈希存储（m=64MiB, t=3, p=4，OWASP 推荐），"
                    "令牌走 JWT(HS256)+ 服务端会话表(12h TTL)，可单独撤销任意会话。\n"
                    f"{border}"
                )
                logger.warning(msg)
            logger.info(f"[上班族物语] WebUI(aiohttp) 已启动：http://{host}:{port} 🔒")
        except PermissionError:
            logger.warning(
                "[上班族物语] WebUI 启动失败：端口 "
                f"{port} 被系统保留或被防火墙拦截（WinError 10013）。"
                "常见于 Hyper-V/WSL 动态保留端口，请在插件配置中更换 webui_port 后重载。"
            )
            self._webui = None
        except OSError as e:
            logger.warning(
                f"[上班族物语] WebUI 启动失败（端口 {port} 被占用？）：{e}；"
                "本次运行将没有 WebUI，其余功能不受影响"
            )
            self._webui = None

    async def terminate(self):
        # 1. 先清指令锁表：卸载后没有人能再新来；持锁中的旧协程按自身退出自然释放。
        #    （清早于 WebUI/渲染器/DB 关闭，与 slave_market 的卸载顺序约定一致）
        locks = getattr(self, "_player_locks", None)
        if locks is not None:
            try:
                locks.clear()
            except Exception:  # noqa: BLE001
                logger.warning("[上班族物语] 清理指令锁表异常（已忽略）")
            self._player_locks = None
        if self._push_task:
            self._push_task.cancel()
            try:
                await self._push_task
            except asyncio.CancelledError:
                pass
            except Exception as e:  # noqa: BLE001 - 收尾异常不阻断卸载
                logger.warning(f"[上班族物语] 推送任务收尾异常（已忽略）：{e}")
            self._push_task = None
        if self._webui:
            try:
                await asyncio.wait_for(self._webui.stop(), timeout=15)
                logger.info("[上班族物语] WebUI 已停止，端口已释放")
            except Exception as e:  # noqa: BLE001 - 停止失败不阻断卸载
                logger.warning(f"[上班族物语] WebUI 停止异常（已忽略）：{e}")
            self._webui = None
        try:
            await self.renderer.close()
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[上班族物语] 渲染器关闭异常（已忽略）：{e}")

    async def _push_loop(self):
        """定时任务：到点后向开启推送的群发送每日早报，并做每周排行归档。"""
        while True:
            try:
                # 这个周期同时决定彩票开奖的时间精度（到点后最多晚一个周期）
                interval = float(
                    logic.cfg_get(self.config, "push_check_interval_minutes", 10)
                )
                await asyncio.sleep(max(30.0, interval * 60))
                lt = time.localtime()
                if lt.tm_hour < int(logic.cfg_get(self.config, "push_hour", 8)):
                    continue
                today = logic.today_str()
                # 归档与清理都是「每天一次」的重活（清理要扫全表并持写锁），
                # 用日期水位线挡住，否则从推送时间点起每 10 分钟就来一轮
                if self._last_cleanup_day != today:
                    self._last_cleanup_day = today
                    if bool(logic.cfg_get(self.config, "weekly_archive_enabled", True)):
                        try:
                            await asyncio.to_thread(self._weekly_archive)
                        except Exception as e:  # noqa: BLE001 - 归档失败不影响推送
                            logger.warning(f"[上班族物语] 每周归档失败：{e}")
                    try:
                        await asyncio.to_thread(self.db.cleanup_old_data)
                    except Exception as e:  # noqa: BLE001
                        logger.warning(f"[上班族物语] 数据清理异常：{e}")
                try:
                    await self._lottery_maybe_draw()
                except Exception as e:  # noqa: BLE001 - 开奖失败不影响推送
                    logger.warning(f"[上班族物语] 彩票开奖异常：{e}")
                await self._daily_push()
            except asyncio.CancelledError:
                raise
            except Exception as e:  # noqa: BLE001
                logger.error(f"[上班族物语] 推送循环异常：{e}")

    async def _daily_push(self):
        today = logic.today_str()
        for gid in await asyncio.to_thread(self.db.push_group_ids):
            gid = str(gid)
            umo = self.ctx.umos.get(gid)
            if not umo:
                continue  # 本轮未见过该群消息，无法定位会话
            if await asyncio.to_thread(self.db.push_last_date, gid) == today:
                continue
            text = await asyncio.to_thread(self._daily_report_text, gid)
            try:
                await self.context.send_message(umo, MessageChain().message(text))
                await asyncio.to_thread(self.db.mark_pushed, gid, today)
            except Exception as e:  # noqa: BLE001 - 单群失败不阻断其他群
                logger.warning(f"[上班族物语] 推送失败（{gid}）：{e}")

    def _daily_report_text(self, gid) -> str:
        lines = [f"📰 今日职场早报：{gd.news_of_day() or '暂无'}"]
        try:
            stocks = self.market.list_stocks(100)
            ups = sorted(
                (s for s in stocks if s["chg"] > 0), key=lambda s: -s["chg"]
            )[:3]
            downs = sorted(
                (s for s in stocks if s["chg"] < 0), key=lambda s: s["chg"]
            )[:3]
            if ups:
                lines.append(
                    "📈 领涨："
                    + " ".join(f"{s['name']} +{s['chg']}%" for s in ups)
                )
            if downs:
                lines.append(
                    "📉 领跌：" + " ".join(f"{s['name']} {s['chg']}%" for s in downs)
                )
        except Exception:  # noqa: BLE001, S110 - 股市摘要失败仅省略该段
            pass
        lines.append("（发送「推送」可开关本群推送）")
        return "\n".join(lines)

    async def _lottery_maybe_draw(self):
        """到达开奖时间且当期有售票时，自动开奖并向购票群播报结果。"""
        hour = int(logic.cfg_get(self.config, "lottery_draw_hour", 21))
        lt = time.localtime()
        if lt.tm_hour < hour:
            return
        today = logic.today_str()
        # 先把昨日及更早的「孤儿奖池」（开奖日到了但无人购票导致永不滚存的余额）
        # 滚存到今天，否则钱会被永久锁在历史池行里。
        try:
            await asyncio.to_thread(self.db.lottery_carry_unsettled_pool, today)
        except Exception as e:  # noqa: BLE001 - 滚存失败不影响开奖
            logger.warning(f"[上班族物语] 孤儿奖池滚存失败：{e}")
        gids = await asyncio.to_thread(self.db.lottery_today_gids, today)
        if not gids:
            return
        row = await asyncio.to_thread(self._lottery_already_drawn, today)
        if row:
            return

        from .core.lottery import fmt_draw, make_judge, random_number

        number = random_number()
        result = await asyncio.to_thread(
            self.db.lottery_settle, today, number, make_judge(number)
        )
        if not result:
            return
        logger.info(
            f"[上班族物语] 双色球开奖 {today}：{fmt_draw(number)}，"
            f"奖池 {result['pool']} 元，派奖 {result['paid']} 元，滚存 {result['carry']} 元"
        )
        # 向当期购票群播报（未在本轮见过消息的群无法定位会话，跳过）
        lines = _fmt_draw_lines(result)
        text = "\n".join(lines)
        for gid in gids:
            umo = self.ctx.umos.get(str(gid))
            if not umo:
                continue
            try:
                await self.context.send_message(umo, MessageChain().message(text))
            except Exception as e:  # noqa: BLE001 - 单群播报失败不阻断
                logger.warning(f"[上班族物语] 彩票开奖播报失败（{gid}）：{e}")

    def _lottery_already_drawn(self, today):
        last = self.db.lottery_last_draw()
        return last and last.get("date") == today

    def _weekly_archive(self):
        """每周首次触发时，把上一周各群的财富榜快照写入 archives。"""
        # 同步方法，由调用方 asyncio.to_thread 包裹

        y, w = logic.iso_week()
        if w > 1:
            prev = (y, w - 1)
        else:
            # 动态计算上一年最后一天的 ISO 周数（可能为 52 或 53）
            prev_y, prev_w = logic.iso_week(time.mktime((y - 1, 12, 31, 12, 0, 0, 0, 0, -1)))
            prev = (prev_y, prev_w)
        if self.db.max_archived_week() == prev:
            return
        for gid, _n in self.db.group_ids():
            top = self.db.top_wealth(
                gid, int(logic.cfg_get(self.config, "archive_top_n", 10))
            )
            if not top:
                continue
            payload = {
                "week": f"{prev[0]}-W{prev[1]:02d}",
                "top": [
                    {
                        "name": logic.display(p),
                        "total": p.get("total", 0),
                        "level": p.get("lvl", 1),
                    }
                    for p in top
                ],
            }
            self.db.save_archive(gid, prev[0], prev[1], payload)

    # ------------------------------------------------------------------
    # 输出渲染（独立 Playwright 渲染器，失败回退纯文本）
    # ------------------------------------------------------------------

    def _data_dir(self) -> Path:
        try:
            from astrbot.core.utils.astrbot_path import get_astrbot_data_path

            return Path(get_astrbot_data_path()) / "plugin_data" / PLUGIN_NAME
        except Exception:  # noqa: BLE001 - 兜底路径，保证任何内核版本都能初始化
            return Path("data") / "plugin_data" / PLUGIN_NAME

    async def _render(self, template, data):
        if not template or not bool(logic.cfg_get(self.config, "use_image", True)):
            return None
        try:
            from astrbot.core.config.default import VERSION as AB_VER

            data.setdefault("plugin_version", self._get_version())
            data.setdefault("astrbot_version", AB_VER)
            tmpl_path = gd.template_path(template)
            tmpl_str = await asyncio.to_thread(tmpl_path.read_text, "utf-8")
            html = await asyncio.to_thread(self.renderer.render_template, tmpl_str, data)
            return await self.renderer.screenshot(
                html, name=f"{template}_{int(time.time())}"
            )
        except Exception as e:  # noqa: BLE001 - 渲染失败必须回退文本而非中断指令
            logger.warning(f"[上班族物语] 渲染失败回退文本：{e}")
            return None

    def _get_version(self) -> str:
        try:
            meta = self.context.get_registered_star(PLUGIN_NAME)
            if meta and meta.version:
                return meta.version
        except Exception:  # noqa: BLE001, S110 - 元数据不可用时用常量兜底
            pass
        return VERSION

    async def _emit_msg(self, event: AstrMessageEvent, r: dict):
        """把一条 R 结果转成消息：err > img > 模板渲染 > 纯文本。"""
        max_len = int(logic.cfg_get(self.config, "max_text_length", 1500))
        if r.get("err"):
            yield event.plain_result(str(r["err"])[:max_len])
            return
        img = r.get("img") or (await self._render(r.get("tmpl"), r.get("data") or {}))
        if img:
            yield event.image_result(img)
        else:
            text = str(r.get("text") or "").strip()
            yield event.plain_result(text[:max_len] if text else "（执行完成）")


# 安装全部指令路由（handlers/ 目录按业务域维护）
install_routes(Shangbanzu, filter, __name__, ALL_ROUTES)
