"""声明式路由基座。

AstrBot 通过 handler.__module__ 与插件主模块做【精确匹配】来绑定实例
（见 star_handler.get_handlers_by_module_name），因此所有被装饰的函数
必须归属到主模块。install() 在装饰前重写 __module__，从而允许把路由表
安全地拆分到任意子模块中。
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field


@dataclass
class Route:
    pattern: str
    name: str
    doc: str
    run: Callable[..., Awaitable]
    admin: bool = False
    priority: int = 0
    raw: bool = False
    extras: dict = field(default_factory=dict)


def install(cls, flt, module_path: str, routes) -> int:
    """把路由安装到插件类上，返回安装数量。

    flt 为 astrbot.api.event.filter 子模块。
    """
    installed = 0
    for route in routes:
        if route.raw:

            async def handler(self, event, _route=route):
                try:
                    await self.ctx.refresh_card(event)
                except Exception:  # noqa: BLE001, S110 - 静默降级
                    pass
                async for item in _route.run(self.ctx, event):
                    if isinstance(item, dict):
                        async for msg in self._emit_msg(event, item):
                            yield msg
                    elif isinstance(item, str):
                        yield event.plain_result(item)
                event.stop_event()

        else:

            async def handler(self, event, _route=route):
                try:
                    await self.ctx.refresh_card(event)
                except Exception:  # noqa: BLE001, S110 - 昵称拉取失败不影响指令
                    pass
                r = await _route.run(self.ctx, event)
                async for msg in self._emit_msg(event, r):
                    yield msg
                event.stop_event()

        handler.__name__ = route.name
        handler.__qualname__ = f"{cls.__name__}.{route.name}"
        handler.__doc__ = route.doc
        handler.__module__ = module_path

        if route.admin:
            handler = flt.permission_type(flt.PermissionType.ADMIN)(handler)
        handler = flt.regex(route.pattern, priority=route.priority)(handler)
        setattr(cls, route.name, handler)
        installed += 1
    return installed
