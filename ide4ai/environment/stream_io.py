# filename: stream_io.py
# @Author  : JQQ
# @Email   : jqq1716@gmail.com
# @Software: PyCharm
"""IDE environment 子系统共享的流就绪检测原语 / Shared stream-readiness primitive.

Bug: TFROB-588（terminal/LSP 用 select.select() 致高 FD 进程崩溃）

使命:
- 提供一个**不受 `select()` FD_SETSIZE(1024) 上限约束**的「哪些流当前可读」检测，
  供 terminal 输出捕获与 LSP stdout 读取共用。

为什么不用 `select.select()`:
- `select.select()` 底层 `fd_set` 是受 `FD_SETSIZE=1024` 限制的位图；传入 fd ≥ 1024 时
  CPython 抛 `ValueError: filedescriptor out of range in select()`。长跑 agent 进程
  打开过 >1024 个 FD（连接池 / 子进程管道 / 模型句柄）后，新管道 fd 必然越界 → 崩。
- `selectors.DefaultSelector` 在 Linux=epoll / macOS=kqueue（退化时 poll），均无此上限。

职责边界:
- 只做「就绪查询」这一件事，无状态、无副作用（每次调用自建并关闭 selector）。
- 不负责读取数据、不负责轮询循环——调用方自行决定读多少、循环到何时。
"""

from __future__ import annotations

import selectors
from collections.abc import Iterable
from typing import IO, Any


def wait_for_readable(streams: Iterable[IO[Any] | None], timeout: float | None) -> set[IO[Any]]:
    """返回 ``streams`` 中在 ``timeout`` 内变为可读的文件对象集合。

    `select.select()` 的安全替代：走 `selectors.DefaultSelector`（epoll/kqueue），
    不受 FD_SETSIZE(1024) 上限约束，详见模块 docstring。

    Args:
        streams: 待监听的文件对象；``None`` 元素会被跳过（兼容 ``proc.stdout`` 可能为 None）。
        timeout: 最长等待秒数；``0`` 表示轮询即返回，``None`` 表示阻塞至任一就绪。

    Returns:
        set[IO[Any]]: 当前可读的文件对象子集（原样返回传入的对象，便于调用方按身份比对）。
    """
    selector = selectors.DefaultSelector()
    # fd -> 原始文件对象。用 key.fd 回映而非 key.fileobj，规避 selectors 的
    # FileObject(Union[int, HasFileno]) 类型与 IO 的不匹配，无需 cast。
    registered: dict[int, IO[Any]] = {}
    try:
        for stream in streams:
            if stream is not None:
                key = selector.register(stream, selectors.EVENT_READ)
                registered[key.fd] = stream
        if not registered:
            return set()
        return {registered[key.fd] for key, _ in selector.select(timeout)}
    finally:
        selector.close()
