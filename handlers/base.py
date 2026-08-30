"""声明式路由基座。

AstrBot 通过 handler.__module__ 与插件主模块做【精确匹配】来绑定实例
（见 star_handler.get_handlers_by_module_name），因此所有被装饰的函数
必须归属到主模块。install() 在装饰前重写 __module__，从而允许把路由表
安全地拆分到任意子模块中。

注意：此写法依赖 AstrBot 内部的 get_handlers_by_module_name 精确匹配行为，
升级 AstrBot 后若指令全部失效，优先检查这里。
"""

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

GID_HINT = "该功能只能在群聊中使用"
ERR_HINT = "指令执行异常，已记录日志，请稍后再试"


def gid_of(event) -> str:
    """群 ID（私聊返回空串）。所有路由统一用它做群聊守卫，别再各文件抄一份。"""
    return event.get_group_id() or ""

# 每用户指令锁：同一 (群, 用户) 的指令串行执行，
# 消除「读余额→判断→写回」式资金操作被连发指令并发击穿的双花窗口。
#
# 锁表挂在插件实例字段（handler 里 lazy-init）而不是模块级 dict：
# 热重载时模块会连同旧模块对象一起被换掉，旧在飞协程持着旧模块的锁、
# 新指令从新模块拿新锁，双花窗口在重载瞬间重新打开；实例字段跟插件
# 生命周期走，terminate() 里 clear() 一次性收口。
class PlayerLockTable:
    """每 (群, 用户) 一把 asyncio.Lock，串行化单用户的多指令并发。"""

    SOFT_CAP = 10000

    def __init__(self):
        self._locks: dict[tuple[str, str], asyncio.Lock] = {}

    def get(self, gid, uid) -> asyncio.Lock:
        key = (str(gid or ""), str(uid))
        lock = self._locks.get(key)
        if lock is None:
            # 容量保护：只淘汰空闲锁。正在被持有的锁一旦被丢掉，
            # 在飞的指令与新指令会各持一把不同的锁，防双花的窗口就重新打开了。
            # 注：取锁与 async with 加锁之间没有 await 挂起点，二者在事件循环
            # 上是原子的，淘汰循环不会观察到「已交出但未上锁」的中间态。
            if len(self._locks) > self.SOFT_CAP:
                for k, v in list(self._locks.items()):
                    if not v.locked():
                        self._locks.pop(k, None)
            lock = self._locks.setdefault(key, asyncio.Lock())
        return lock

    def clear(self) -> None:
        """热重载 / 卸载时清空锁表。不抢持锁中的锁，让它们按协程退出自然释放。"""
        self._locks.clear()


@dataclass
class Route:
    pattern: str
    name: str
    doc: str
    run: Callable[..., Awaitable]
    admin: bool = False
    priority: int = 0


def install(cls, flt, module_path: str, routes) -> int:
    """把路由安装到插件类上，返回安装数量。

    flt 为 astrbot.api.event.filter 子模块。
    run() 通常是普通协程返回 R(dict)；若返回异步生成器，
    则逐条 yield dict(R) 或 str（纯文本）。
    """
    installed = 0
    for route in routes:

        async def handler(self, event, _route=route):
            try:
                await self.ctx.refresh_card(event)
            except Exception:  # noqa: BLE001, S110 - 昵称拉取失败不影响指令
                pass
            gid = event.get_group_id() or ""
            try:
                # 锁表 lazy-init 到插件实例字段，terminate() 时清空
                locks = getattr(self, "_player_locks", None)
                if locks is None:
                    locks = PlayerLockTable()
                    self._player_locks = locks
                async with locks.get(gid, event.get_sender_id()):
                    res = _route.run(self.ctx, event)
                    if hasattr(res, "__aiter__"):  # 异步生成器路由
                        async for item in res:
                            if isinstance(item, dict):
                                async for msg in self._emit_msg(event, item):
                                    yield msg
                            elif isinstance(item, str):
                                yield event.plain_result(item)
                    else:
                        r = await res
                        async for msg in self._emit_msg(event, r):
                            yield msg
            except Exception as e:  # noqa: BLE001 - 兜底：绝不让异常吞掉回复
                self.ctx.log_error(_route.name, e)
                yield event.plain_result(ERR_HINT)
            finally:
                # 无论成功失败都必须终止事件传播，否则异常指令会继续下发给
                # 其它插件 / LLM，用户看到的是两条互相矛盾的回复。
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
