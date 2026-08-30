"""独立 Playwright 渲染器：Jinja2 模板 → HTML → Chromium 截图。

- 浏览器懒启动、全局复用（启动阶段加锁，截图阶段用信号量限并发）
- 每次截图使用独立 BrowserContext，互不串扰，异常也保证关闭
- 截图保存到 plugin_data/screenshots/，自动清理旧图
- 任何失败返回 None，由调用方回退纯文本，绝不中断指令
"""

import asyncio
import time
from pathlib import Path

DEFAULT_MAX_KEEP = 60
# 同时进行的截图数量。Chromium 每个上下文都吃内存，放开太多会把小机器打爆，
# 所以按机器规格由运维配置（render_max_concurrency）。
DEFAULT_MAX_CONCURRENCY = 3
DEFAULT_VIEWPORT_WIDTH = 780
DEFAULT_TIMEOUT_MS = 15000
# Jinja2 模板缓存容量：模板文件本身只有 8 套，但 WebUI 文案编辑会
# 强制 load_all(force=True)，每次渲染都要 from_string 重编一遍很浪费。
# 给一个 LRU 上限防止模板被外部修改后旧缓存长期驻留。
TMPL_CACHE_MAX = 32


class PlaywrightRenderer:
    def __init__(
        self,
        shot_dir: Path,
        scale: float = 2.0,
        logger=None,
        max_concurrency: int = DEFAULT_MAX_CONCURRENCY,
        max_keep: int = DEFAULT_MAX_KEEP,
        viewport_width: int = DEFAULT_VIEWPORT_WIDTH,
        timeout_ms: int = DEFAULT_TIMEOUT_MS,
    ):
        self.shot_dir = Path(shot_dir)
        self.scale = max(1.0, min(4.0, float(scale)))
        self.log = logger
        self.max_concurrency = max(1, min(16, int(max_concurrency)))
        self.max_keep = max(1, int(max_keep))
        self.viewport_width = max(320, min(4096, int(viewport_width)))
        self.timeout_ms = max(1000, min(120000, int(timeout_ms)))
        self._pw = None
        self._browser = None
        self._env = None
        self._tmpl_cache: dict[str, object] = {}
        self._launch_lock = asyncio.Lock()
        self._sem = asyncio.Semaphore(self.max_concurrency)
        self._closing = False
        self._seq = 0

    # ---------- 模板 ----------

    def render_template(self, template_str: str, data: dict) -> str:
        if self._env is None:
            from jinja2 import Environment

            # 自动转义：昵称/群名片等用户可控内容不注入 HTML
            self._env = Environment(autoescape=True)
        # LRU 缓存编译后的 Template，避免每次截图重新解析；
        # key 用原始字符串（hash），避免大字符串拷贝。
        tmpl = self._tmpl_cache.get(template_str)
        if tmpl is None:
            tmpl = self._env.from_string(template_str)
            self._tmpl_cache[template_str] = tmpl
            if len(self._tmpl_cache) > TMPL_CACHE_MAX:
                self._tmpl_cache.pop(next(iter(self._tmpl_cache)))
        return tmpl.render(**data)

    def clear_template_cache(self):
        """模板文件被外部修改（WebUI 文案编辑）时调用。"""
        self._tmpl_cache.clear()

    # ---------- 截图 ----------

    async def screenshot(self, html: str, name: str = "") -> str | None:
        if self._closing:
            return None
        async with self._sem:
            # 拿到信号量后必须复查：close() 会置 _closing 并抽干信号量，
            # 但排队中的协程是在 close() 之前越过入口检查的。不复查的话，
            # 卸载/重载后仍会重新 launch 出一个没人负责关闭的 Chromium。
            if self._closing:
                return None
            browser = await self._ensure_browser()
            if browser is None:
                return None
            ctx = None
            try:
                ctx = await browser.new_context(
                    viewport={"width": self.viewport_width, "height": 600},
                    device_scale_factor=self.scale,
                )
                page = await ctx.new_page()
                try:
                    await page.set_content(
                        html, wait_until="networkidle", timeout=self.timeout_ms
                    )
                except Exception:  # noqa: BLE001 - 网络资源(头像)超时也照常出图
                    await page.set_content(
                        html,
                        wait_until="domcontentloaded",
                        timeout=max(1000, int(self.timeout_ms * 2 / 3)),
                    )
                self.shot_dir.mkdir(parents=True, exist_ok=True)
                self._seq += 1
                fname = f"{name or 'shot'}_{self._seq}_{int(time.time())}.png"
                out = self.shot_dir / fname
                body = await page.query_selector("body")
                if body:
                    await body.screenshot(path=str(out))
                else:
                    await page.screenshot(path=str(out), full_page=True)
                await asyncio.to_thread(self._cleanup)
                return str(out)
            except Exception as e:  # noqa: BLE001 - 渲染失败交由上层回退文本
                if self.log:
                    self.log.warning(f"[上班族物语][Playwright] 截图失败：{e}")
                # 浏览器可能已经崩了，丢掉引用让下次重新拉起；
                # 本次上下文由下面的 finally 关闭，不会留孤儿。
                await self._drop_browser(browser)
                return None
            finally:
                if ctx is not None:
                    try:
                        await ctx.close()
                    except Exception:  # noqa: BLE001, S110 - 关闭失败无需上抛
                        pass

    async def _ensure_browser(self):
        """返回可用浏览器实例；启动失败返回 None（调用方回退文本）。"""
        if self._browser is not None and self._browser.is_connected():
            return self._browser
        async with self._launch_lock:
            if self._browser is not None and self._browser.is_connected():
                return self._browser
            try:
                await self._launch()
            except Exception as e:  # noqa: BLE001
                if self.log:
                    self.log.warning(f"[上班族物语][Playwright] 启动失败：{e}")
                return None
            return self._browser

    async def _drop_browser(self, expected):
        """丢弃一个疑似已损坏的浏览器实例（仅当它还是当前实例时）。"""
        async with self._launch_lock:
            if self._browser is not expected:
                return  # 已被别人重建，不要误关新实例
            self._browser = None
        try:
            await expected.close()
        except Exception:  # noqa: BLE001, S110
            pass

    async def _launch(self):
        from playwright.async_api import async_playwright

        if self._pw is None:
            self._pw = await async_playwright().start()
        try:
            self._browser = await self._pw.chromium.launch(headless=True)
        except Exception as e:
            self._browser = None
            if self._pw is not None:
                try:
                    await self._pw.stop()
                except Exception:  # noqa: BLE001, S110
                    pass
                self._pw = None
            raise RuntimeError(
                "Chromium 启动失败。请先执行一次：python -m playwright install chromium"
            ) from e
        if self.log:
            self.log.info("[上班族物语][Playwright] 渲染器已就绪")

    def _cleanup(self):
        try:
            files = sorted(
                (p for p in self.shot_dir.glob("*.png") if p.is_file()),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
            for old in files[self.max_keep :]:
                old.unlink(missing_ok=True)
        except OSError:
            pass

    # ---------- 关闭 ----------

    async def close(self):
        """幂等关闭。先挡住新任务，再等在飞的截图收尾，避免关到一半被用。"""
        self._closing = True
        for _ in range(self.max_concurrency):
            try:
                await asyncio.wait_for(self._sem.acquire(), timeout=10)
            except (TimeoutError, asyncio.TimeoutError):
                break
        browser, pw = self._browser, self._pw
        self._browser = self._pw = None
        for label, obj, coro_name in (("browser", browser, "close"), ("playwright", pw, "stop")):
            if obj is None:
                continue
            try:
                await getattr(obj, coro_name)()
            except Exception as e:  # noqa: BLE001 - 关闭失败无需上抛
                if self.log:
                    self.log.warning(f"[上班族物语][Playwright] close {label}: {e}")
