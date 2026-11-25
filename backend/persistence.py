"""Serialized file I/O with explicit ownership through cancellation."""
import asyncio
import logging
from typing import Any, Callable, Optional


logger = logging.getLogger(__name__)


class FileWriter:
  """One file operation at a time, never abandon a running writer thread.

  Callers await their operation rather than spawning per-event background jobs.
  A new application/test loop may reuse the writer only after the old one has
  released all ownership. No mutable application state is read by the worker.
  """

  def __init__(self) -> None:
    self._loop: Optional[asyncio.AbstractEventLoop] = None
    self._lock: Optional[asyncio.Lock] = None
    self._pending = 0

  async def run(self, operation: Callable[..., Any], *args: Any) -> Any:
    loop = asyncio.get_running_loop()
    if self._loop is not loop:
      if self._pending:
        raise RuntimeError("file writer is owned by another event loop")
      self._loop = loop
      self._lock = asyncio.Lock()
    self._pending += 1
    try:
      lock = self._lock
      assert lock is not None
      async with lock:
        task = asyncio.create_task(asyncio.to_thread(operation, *args))
        try:
          return await asyncio.shield(task)
        except asyncio.CancelledError as cancelled:
          # Canceling to_thread's Future does not stop the actual thread.
          # Keep the lock and await it even if shutdown cancels us again.
          while not task.done():
            try:
              await asyncio.shield(task)
            except asyncio.CancelledError:
              continue
            except Exception:
              break
          if not task.cancelled():
            try:
              task.result()
            except Exception:
              logger.exception("File operation failed during cancellation")
          raise cancelled
    finally:
      self._pending -= 1
