"""Exclusive daily-run lock. POSIX uses fcntl.flock; released on process exit."""

from __future__ import annotations

import errno
import sys
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Self

_THREAD_LOCK = threading.Lock()

try:
    import fcntl
except ImportError:  # pragma: no cover — Windows
    fcntl = None  # type: ignore[assignment]


class RunLocked(Exception):
    """Another foreshadow process holds the run lock."""


class RunLock:
    """Non-blocking exclusive lock on ``$HOME/run.lock``."""

    def __init__(self, data_dir: Path) -> None:
        self.path = Path(data_dir) / "run.lock"
        self._fh: Any = None

    def acquire(self) -> Self:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        handle = self.path.open("a+")
        try:
            handle.seek(0)
            if handle.read(1) == "":
                handle.write("0")
                handle.flush()
            _lock_exclusive_nb(handle)
        except BaseException:
            handle.close()
            raise
        self._fh = handle
        try:
            self.path.chmod(0o600)
        except OSError:
            pass
        return self

    def release(self) -> None:
        handle = self._fh
        self._fh = None
        if handle is None:
            return
        try:
            _unlock(handle)
        except OSError:
            pass
        try:
            handle.close()
        except OSError:
            pass

    def __enter__(self) -> Self:
        return self.acquire()

    def __exit__(self, *exc: object) -> None:
        self.release()


def run_lock(data_dir: Path) -> RunLock:
    return RunLock(data_dir)


@contextmanager
def official_run_lock(data_dir: Path, *, blocking: bool = False) -> Iterator[bool]:
    """Yield True if this process holds ``run.lock``. Non-blocking by default.

    ``run_pipeline`` uses ``blocking=False`` so a second Official CLI exits
    with status ``locked`` instead of waiting.
    """
    thread_got = _THREAD_LOCK.acquire(blocking=blocking)
    if not thread_got:
        yield False
        return
    lock = RunLock(data_dir)
    try:
        try:
            if blocking:
                _acquire_blocking(lock)
            else:
                lock.acquire()
        except RunLocked:
            yield False
            return
        try:
            yield True
        finally:
            lock.release()
    finally:
        _THREAD_LOCK.release()


def _acquire_blocking(lock: RunLock) -> RunLock:
    lock.path.parent.mkdir(parents=True, exist_ok=True)
    handle = lock.path.open("a+")
    try:
        handle.seek(0)
        if handle.read(1) == "":
            handle.write("0")
            handle.flush()
        _lock_exclusive(handle)
    except BaseException:
        handle.close()
        raise
    lock._fh = handle
    try:
        lock.path.chmod(0o600)
    except OSError:
        pass
    return lock


def _lock_exclusive(handle: Any) -> None:
    if fcntl is not None:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        return
    if sys.platform.startswith("win"):  # pragma: no cover
        import msvcrt

        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
        return
    raise RunLocked("run lock is unavailable on this platform")


def _lock_exclusive_nb(handle: Any) -> None:
    if fcntl is not None:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            return
        except OSError as exc:
            if exc.errno in (errno.EAGAIN, errno.EACCES, errno.EWOULDBLOCK):
                raise RunLocked("run in progress (lock held)") from exc
            raise
    if sys.platform.startswith("win"):  # pragma: no cover
        import msvcrt

        try:
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            return
        except OSError as exc:
            raise RunLocked("run in progress (lock held)") from exc
    raise RunLocked("run lock is unavailable on this platform")


def _unlock(handle: Any) -> None:
    if fcntl is not None:
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        return
    if sys.platform.startswith("win"):  # pragma: no cover
        import msvcrt

        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
