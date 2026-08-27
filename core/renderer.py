"""独立 Playwright 渲染器：Jinja2 模板 → HTML → Chromium 截图。

- 浏览器懒启动、全局复用（单例锁串行截图）
- 截图保存到 plugin_data/screenshots/，自动清理旧图
- 任何失败返回 None，由调用方回退纯文本，绝不中断指令
"""

import asyncio
import time
from pathlib import Path

MAX_KEEP = 60


class PlaywrightRenderer:
    def __init__(self, shot_dir: Path, scale: float = 2.0, logger=None):
        self.shot_dir = Path(shot_dir)
        self.scale = max(1.0, float(scale))
        self.log = logger
        self._pw = None
        self._browser = None
        self._ctx = None
        self._env = None
        self._lock = asyncio.Lock()
        self._seq = 0

    # ---------- 模板 ----------

    def render_template(self, template_str: str, data: dict) -> str:
        if self._env is None:
            from jinja2 import Environment

            # 自动转义：昵称/群名片等用户可控内容不注入 HTML
            self._env = Environment(autoescape=True)
        return self._env.from_string(template_str).render(**data)

    # ---------- 截图 ----------

    async def screenshot(self, html: str, name: str = "") -> str | None:
        async with self._lock:
            try:
                if self._browser is None or self._ctx is None:
                    await self._launch()
                page = await self._ctx.new_page()
                try:
                    try:
                        await page.set_content(
                            html, wait_until="networkidle", timeout=15000
                        )
                    except Exception:  # noqa: BLE001 - 网络资源(头像)超时也照常出图
                        await page.set_content(
                            html, wait_until="domcontentloaded", timeout=10000
                        )
                    self.shot_dir.mkdir(parents=True, exist_ok=True)
                    self._seq += 1
                    fname = f"{name or 'shot'}_{self._seq}_{int(time.time())}.png"
                    out = self.shot_dir / fname
                    await page.screenshot(path=str(out), full_page=True)
                finally:
                    await page.close()
                self._cleanup()
                return str(out)
            except Exception as e:  # noqa: BLE001 - 渲染失败交由上层回退文本
                if self.log:
                    self.log.warning(f"[上班族物语][Playwright] 截图失败：{e}")
                self._browser = None
                self._ctx = None
                return None

    async def _launch(self):
        from playwright.async_api import async_playwright

        self._pw = await async_playwright().start()
        try:
            self._browser = await self._pw.chromium.launch(headless=True)
        except Exception as e:
            self._browser = None
            raise RuntimeError(
                "Chromium 启动失败。请先执行一次：python -m playwright install chromium"
            ) from e
        self._ctx = await self._browser.new_context(
            viewport={"width": 780, "height": 600},
            device_scale_factor=self.scale,
        )
        if self.log:
            self.log.info("[上班族物语][Playwright] 渲染器已就绪")

    def _cleanup(self):
        try:
            files = sorted(
                (p for p in self.shot_dir.glob("*.png") if p.is_file()),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
            for old in files[MAX_KEEP:]:
                old.unlink(missing_ok=True)
        except OSError:
            pass

    # ---------- 关闭 ----------

    async def close(self):
        for label, coro in (
            ("ctx", self._ctx.close() if self._ctx is not None else None),
            ("browser", self._browser.close() if self._browser is not None else None),
            ("playwright", self._pw.stop() if self._pw is not None else None),
        ):
            if coro is None:
                continue
            try:
                await coro
            except Exception as e:  # noqa: BLE001 - 关闭失败无需上抛
                if self.log:
                    self.log.warning(f"[上班族物语][Playwright] close {label}: {e}")
        self._ctx = self._browser = self._pw = None
