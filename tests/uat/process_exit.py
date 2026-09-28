"""Observe exact process exits with OS events, without polling or sending signals."""

from __future__ import annotations

import json
import os
import select
import selectors
import sys
import time
from contextlib import closing


def emit(kind: str, value: object) -> None:
    print(json.dumps({"kind": kind, "value": value}), flush=True)


def main() -> None:
    timeout = float(sys.argv[1])
    pids = {int(value) for value in sys.argv[2:]}
    deadline = time.monotonic() + timeout
    if hasattr(select, "kqueue"):
        with closing(select.kqueue()) as queue:
            watching = set()
            for pid in pids:
                try:
                    queue.control(
                        [
                            select.kevent(
                                pid,
                                filter=select.KQ_FILTER_PROC,
                                flags=select.KQ_EV_ADD | select.KQ_EV_ONESHOT,
                                fflags=select.KQ_NOTE_EXIT,
                            )
                        ],
                        0,
                        0,
                    )
                    watching.add(pid)
                except ProcessLookupError:
                    pass
            emit("ready", sorted(watching))
            while watching and time.monotonic() < deadline:
                for event in queue.control(None, len(watching), max(0, deadline - time.monotonic())):
                    watching.discard(event.ident)
                    emit("exit", event.ident)
            emit("done", sorted(watching))
    elif hasattr(os, "pidfd_open"):
        with selectors.DefaultSelector() as selector:
            for pid in pids:
                try:
                    fd = os.pidfd_open(pid)
                except ProcessLookupError:
                    continue
                selector.register(fd, selectors.EVENT_READ, pid)
            emit("ready", sorted(key.data for key in selector.get_map().values()))
            try:
                while selector.get_map() and time.monotonic() < deadline:
                    for key, _ in selector.select(max(0, deadline - time.monotonic())):
                        selector.unregister(key.fd)
                        os.close(key.fd)
                        emit("exit", key.data)
                emit("done", sorted(key.data for key in selector.get_map().values()))
            finally:
                for key in list(selector.get_map().values()):
                    os.close(key.fd)
    else:
        raise SystemExit("UAT process exit verification requires macOS/BSD kqueue or Linux pidfd")


if __name__ == "__main__":
    main()
