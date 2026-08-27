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
VERSION = "1.0.0"


class Shangbanzu(Star):
    def __init__(self, context: Context, config: AstrBotConfig | None = None):
        super().__init__(context)
        self.config = config or {}
        self.db = DB(self._data_dir() / "shangbanzu.db")
        self.ctx = GameCtx(self, self.db, self.config)
        self.renderer = PlaywrightRenderer(
            self._data_dir() / "screenshots",
            scale=float(logic.cfg_get(self.config, "render_scale", 2.0)),
            logger=logger,
        )
        self.market = StockMarket(self.db, self.config)
        self._webui = None
        self.backups = BackupManager(
            self._data_dir() / "shangbanzu.db",
            self._data_dir() / "backups",
            logger,
        )

    async def initialize(self):
        await asyncio.to_thread(self.db.init)
        await asyncio.to_thread(self.market.ensure_seeded)
        if bool(logic.cfg_get(self.config, "webui_enabled", True)):
            host = str(logic.cfg_get(self.config, "webui_host", "0.0.0.0"))
            port = int(logic.cfg_get(self.config, "webui_port", 17817))
            self._webui = WebUIServer(
                self.db,
                self.backups,
                self.market,
                host,
                port,
                VERSION,
                logger,
                password=str(logic.cfg_get(self.config, "webui_password", "")),
                config_data=self.config,
            )
            try:
                await self._webui.start()
                logger.info(
                    f"[上班族物语] WebUI(aiohttp) 已启动：http://{host}:{port}"
                    + (
                        " 🔒"
                        if str(logic.cfg_get(self.config, "webui_password", ""))
                        else ""
                    )
                )
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
        self._push_task = asyncio.create_task(self._push_loop())
        logger.info(f"[上班族物语] 插件已加载，共注册 {len(ALL_ROUTES)} 条指令路由")

    async def terminate(self):
        if getattr(self, "_push_task", None):
            self._push_task.cancel()
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
                await asyncio.sleep(600)
                lt = time.localtime()
                if lt.tm_hour < int(logic.cfg_get(self.config, "push_hour", 8)):
                    continue
                if bool(logic.cfg_get(self.config, "weekly_archive_enabled", True)):
                    try:
                        await asyncio.to_thread(self._weekly_archive)
                    except Exception as e:  # noqa: BLE001 - 归档失败不影响推送
                        logger.warning(f"[上班族物语] 每周归档失败：{e}")
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

    def _weekly_archive(self):
        """每周首次触发时，把上一周各群的财富榜快照写入 archives。"""
        y, w = logic.iso_week()
        prev = (y, w - 1) if w > 1 else (y - 1, 52)
        if self.db.max_archived_week() == prev:
            return
        for gid, _n in self.db.group_ids():
            top = self.db.top_wealth(gid, 10)
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
            tmpl_str = gd.template_path(template).read_text("utf-8")
            html = self.renderer.render_template(tmpl_str, data)
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
        if r.get("err"):
            yield event.plain_result(str(r["err"])[:500])
            return
        img = r.get("img") or (await self._render(r.get("tmpl"), r.get("data") or {}))
        if img:
            yield event.image_result(img)
        else:
            text = str(r.get("text") or "").strip()
            yield event.plain_result(text[:1500] if text else "（执行完成）")


# 安装全部指令路由（handlers/ 目录按业务域维护）
install_routes(Shangbanzu, filter, __name__, ALL_ROUTES)
