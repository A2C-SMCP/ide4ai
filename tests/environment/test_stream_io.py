# filename: test_stream_io.py
"""`stream_io.wait_for_readable` 单元测试.

Bug: TFROB-588（terminal/LSP 用 select.select() 致高 FD 进程崩溃）

使命:
- 锁死「selectors 取代 select.select」的根因修复：fd≥1024（超 select() 的
  FD_SETSIZE=1024 上限）时 `wait_for_readable` 必须正常工作，而 `select.select`
  在同一 fd 上必抛 `ValueError: filedescriptor out of range`。

职责边界:
- 只测就绪查询语义（空入参 / 未就绪 / 就绪 / 高 fd），不测调用方循环。
"""

from __future__ import annotations

import os
import resource
import select
from collections.abc import Iterator

import pytest

from ide4ai.environment.stream_io import wait_for_readable


@pytest.fixture
def exhaust_low_fds() -> Iterator[None]:
    """占满 <1024 的 fd 槽位，逼迫后续 os.pipe 的 fd ≥ 1024，复现 select() FD_SETSIZE 上限。"""
    soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
    desired = 1100
    if hard == resource.RLIM_INFINITY:
        new_soft = max(soft, desired)
    else:
        new_soft = min(hard, max(soft, desired))
        if new_soft < desired:
            pytest.skip(f"RLIMIT_NOFILE hard limit {hard} 不足以复现 fd≥1024 场景")
    resource.setrlimit(resource.RLIMIT_NOFILE, (new_soft, hard))
    held: list[int] = []
    try:
        while True:
            fd = os.open(os.devnull, os.O_RDONLY)
            held.append(fd)
            if fd >= 1023:
                break
        yield
    finally:
        for fd in held:
            try:
                os.close(fd)
            except OSError:  # pragma: no cover - 防御性，正常不触发
                pass
        resource.setrlimit(resource.RLIMIT_NOFILE, (soft, hard))


def test_wait_for_readable_empty_inputs_return_empty_set() -> None:
    """空 streams / 全 None：返回空集，不抛、不阻塞。"""
    assert wait_for_readable([], 0) == set()
    assert wait_for_readable([None, None], 0) == set()


def test_wait_for_readable_not_ready_within_timeout() -> None:
    """管道无数据：timeout 内不就绪，返回空集。"""
    r_fd, w_fd = os.pipe()
    reader = os.fdopen(r_fd, "rb", buffering=0)
    writer = os.fdopen(w_fd, "wb", buffering=0)
    try:
        assert wait_for_readable([reader], 0.05) == set()
    finally:
        reader.close()
        writer.close()


def test_wait_for_readable_reports_ready_stream() -> None:
    """有数据写入后：对应流被报告为就绪。"""
    r_fd, w_fd = os.pipe()
    reader = os.fdopen(r_fd, "rb", buffering=0)
    writer = os.fdopen(w_fd, "wb", buffering=0)
    try:
        assert wait_for_readable([reader], 0) == set()
        writer.write(b"payload")
        writer.flush()
        assert wait_for_readable([reader], 1.0) == {reader}
    finally:
        reader.close()
        writer.close()


@pytest.mark.usefixtures("exhaust_low_fds")
def test_wait_for_readable_survives_high_fd() -> None:
    """TFROB-588 根因回归：fd≥1024 时 wait_for_readable 正常，而 select.select 抛 ValueError。"""
    r_fd, w_fd = os.pipe()
    reader = os.fdopen(r_fd, "rb", buffering=0)
    writer = os.fdopen(w_fd, "wb", buffering=0)
    try:
        if reader.fileno() < 1024:
            # 无法把管道 fd 推到 select() 上限之外属环境受限（非回归），跳过。
            pytest.skip("环境未能分配 fd≥1024，无法复现 select() FD_SETSIZE 场景")

        # 对照：select.select 在 fd≥1024 上必抛——这正是被替换掉的崩溃路径。
        with pytest.raises(ValueError, match="filedescriptor out of range"):
            select.select([reader], [], [], 0)

        # 修复路径：selectors 不受 FD_SETSIZE 约束。
        assert wait_for_readable([reader], 0) == set()
        writer.write(b"high-fd")
        writer.flush()
        assert wait_for_readable([reader], 1.0) == {reader}
    finally:
        reader.close()
        writer.close()
