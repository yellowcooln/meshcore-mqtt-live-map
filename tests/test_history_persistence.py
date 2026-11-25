"""Real history files: background compaction must not stall the loop."""
import asyncio
import builtins
import json
import threading
import time

import history
import state
import app


def _live_route(stamp, message="live"):
  return {
    "type": "route", "ts": stamp, "message_hash": message,
    "origin_id": "AA" * 32, "receiver_id": "BB" * 32,
    "points": [[42.0, -71.0], [42.1, -71.1]],
    "route_mode": "path", "payload_type": 5,
  }


def _isolate_live_history(monkeypatch, path):
  state.route_history_segments.clear()
  state.route_history_edges.clear()
  state.peer_history_pairs.clear()
  monkeypatch.setattr(history, "ROUTE_HISTORY_FILE", str(path))
  monkeypatch.setattr(history, "ROUTE_HISTORY_ENABLED", True)
  monkeypatch.setattr(history, "ROUTE_HISTORY_ALLOWED_MODES_SET", {"path"})
  monkeypatch.setattr(history, "ROUTE_HISTORY_PAYLOAD_TYPES_SET", {5})
  monkeypatch.setattr(app, "routes", {})
  monkeypatch.setattr(app, "clients", set())
  monkeypatch.setattr(app, "MAP_RADIUS_KM", 0)
  monkeypatch.setattr(app, "BLOCKED_NAME_SYMBOL_FILTER_ENABLED", False)
  monkeypatch.setattr(app, "ROUTE_TTL_SECONDS", 120)


def _entry(stamp, message="first"):
  return {
    "ts": stamp, "a": [42.0, -71.0], "b": [42.1, -71.1],
    "a_id": "AA" * 32, "b_id": "BB" * 32,
    "message_hash": message, "payload_type": 5,
    "route_mode": "path", "receiver_id": "BB" * 32,
  }


def test_history_compaction_does_not_block_live_loop(tmp_path, monkeypatch):
  path = tmp_path / "route_history.jsonl"
  original_open = builtins.open
  original_asyncio = history.asyncio
  entered, release = threading.Event(), threading.Event()
  completed = asyncio.Event()
  state.route_history_segments.clear()
  state.route_history_segments.append(_entry(time.time()))
  state.route_history_compact = True
  state.route_history_last_compact = 0
  monkeypatch.setattr(history, "ROUTE_HISTORY_FILE", str(path))
  monkeypatch.setattr(history, "ROUTE_HISTORY_ENABLED", True)
  monkeypatch.setattr(history, "ROUTE_HISTORY_COMPACT_INTERVAL", 0)

  class BlockingFile:
    def __init__(self, handle):
      self.handle = handle
      self.blocked = False

    def __enter__(self):
      return self

    def __exit__(self, *args):
      self.handle.close()

    def write(self, text):
      if not self.blocked:
        self.blocked = True
        entered.set()
        assert release.wait(2)
      return self.handle.write(text)

  def controlled_open(name, *args, **kwargs):
    handle = original_open(name, *args, **kwargs)
    return BlockingFile(handle) if str(name) == str(path) + ".tmp" else handle

  sleeps = 0

  async def pause(_delay):
    nonlocal sleeps
    sleeps += 1
    if sleeps == 1:
      return
    completed.set()
    await asyncio.Event().wait()

  class AsyncioProxy:
    def __getattr__(self, name):
      return getattr(original_asyncio, name)

    sleep = staticmethod(pause)

  monkeypatch.setattr(builtins, "open", controlled_open)
  monkeypatch.setattr(history, "asyncio", AsyncioProxy())

  def emergency_release():
    if entered.wait(2):
      release.wait(0.25)
      release.set()

  unblocker = threading.Thread(target=emergency_release, daemon=True)
  unblocker.start()

  async def exercise():
    task = asyncio.create_task(history._route_history_saver())
    try:
      assert await asyncio.to_thread(entered.wait, 2)
      assert not release.is_set(), "history compaction blocked the live loop"
      release.set()
      await asyncio.wait_for(completed.wait(), 2)
      rows = [json.loads(line) for line in path.read_text().splitlines()]
      assert len(rows) == 1
      assert rows[0]["message_hash"] == "first"
      assert not state.route_history_compact
    finally:
      release.set()
      task.cancel()
      await asyncio.gather(task, return_exceptions=True)

  try:
    asyncio.run(exercise())
  finally:
    release.set()
    unblocker.join(2)
    state.route_history_segments.clear()
    state.route_history_compact = False


def test_live_append_waits_for_compaction_without_losing_observation(
  tmp_path, monkeypatch
):
  path = tmp_path / "route_history.jsonl"
  _isolate_live_history(monkeypatch, path)
  first = _entry(time.time())
  state.route_history_segments.append(first)
  path.write_text(json.dumps(first) + "\n")
  state.route_history_compact = True
  state.route_history_last_compact = 0
  monkeypatch.setattr(history, "ROUTE_HISTORY_COMPACT_INTERVAL", 0)
  original_asyncio = history.asyncio
  original_compact = history._write_route_history_snapshot
  entered, release = threading.Event(), threading.Event()
  compact_completed = asyncio.Event()
  delivered = asyncio.Event()
  sleeps = 0

  def blocked_compact(name, entries):
    entered.set()
    assert release.wait(2)
    original_compact(name, entries)

  async def pause(_delay):
    nonlocal sleeps
    sleeps += 1
    if sleeps == 1:
      return
    compact_completed.set()
    await asyncio.Event().wait()

  class AsyncioProxy:
    def __getattr__(self, name):
      return getattr(original_asyncio, name)

    sleep = staticmethod(pause)

  class Receiver:
    async def send_text(self, text):
      if json.loads(text).get("type") == "route":
        delivered.set()

  monkeypatch.setattr(history, "asyncio", AsyncioProxy())
  monkeypatch.setattr(history, "_write_route_history_snapshot", blocked_compact)
  monkeypatch.setattr(app, "clients", {Receiver()})

  async def exercise():
    queue = asyncio.Queue()
    monkeypatch.setattr(app, "update_queue", queue)
    saver = asyncio.create_task(history._route_history_saver())
    broadcaster = None
    try:
      assert await asyncio.to_thread(entered.wait, 2)
      queue.put_nowait(_live_route(time.time(), "during-compaction"))
      broadcaster = asyncio.create_task(app.broadcaster())
      for _ in range(8):
        await asyncio.sleep(0)
      assert len(state.route_history_segments) == 2
      # Pruning during an in-flight compaction must request another pass.
      state.route_history_compact = True
      release.set()
      await asyncio.wait_for(compact_completed.wait(), 2)
      await asyncio.wait_for(delivered.wait(), 2)
      rows = [json.loads(line) for line in path.read_text().splitlines()]
      assert [row["message_hash"] for row in rows] == [
        "first", "during-compaction"
      ], "compaction replaced an append accepted during its write"
      assert state.route_history_compact
    finally:
      release.set()
      saver.cancel()
      tasks = [saver]
      if broadcaster:
        broadcaster.cancel()
        tasks.append(broadcaster)
      await asyncio.gather(*tasks, return_exceptions=True)

  try:
    asyncio.run(exercise())
  finally:
    state.route_history_segments.clear()
    state.route_history_edges.clear()
    state.peer_history_pairs.clear()
    state.route_history_compact = False


def test_failed_live_append_requests_recovery_compaction(tmp_path, monkeypatch):
  path = tmp_path / "route_history.jsonl"
  _isolate_live_history(monkeypatch, path)
  state.route_history_compact = False
  state.route_history_last_compact = 0
  original_open = builtins.open

  def failing_open(name, mode="r", *args, **kwargs):
    if str(name) == str(path) and mode == "a":
      raise OSError("simulated append failure")
    return original_open(name, mode, *args, **kwargs)

  monkeypatch.setattr(builtins, "open", failing_open)

  async def exercise():
    await history._record_route_history_async(_live_route(time.time()))
    assert state.route_history_compact, "failed append was never retried"
    assert len(state.route_history_segments) == 1
    monkeypatch.setattr(builtins, "open", original_open)
    original_asyncio = history.asyncio
    calls = 0

    async def one_tick(_delay):
      nonlocal calls
      calls += 1
      if calls > 1:
        raise asyncio.CancelledError()

    class AsyncioProxy:
      def __getattr__(self, name):
        return getattr(original_asyncio, name)

      sleep = staticmethod(one_tick)

    monkeypatch.setattr(history, "asyncio", AsyncioProxy())
    monkeypatch.setattr(history, "ROUTE_HISTORY_COMPACT_INTERVAL", 0)
    task = asyncio.create_task(history._route_history_saver())
    await asyncio.gather(task, return_exceptions=True)
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    assert len(rows) == 1
    assert rows[0]["message_hash"] == "live"
    assert not state.route_history_compact

  try:
    asyncio.run(exercise())
  finally:
    state.route_history_segments.clear()
    state.route_history_edges.clear()
    state.peer_history_pairs.clear()
    state.route_history_compact = False


def test_cancelled_pending_append_is_retained_for_final_flush(
  tmp_path, monkeypatch
):
  path = tmp_path / "history.jsonl"
  _isolate_live_history(monkeypatch, path)
  state.route_history_compact = False
  entered, release = threading.Event(), threading.Event()

  def hold_writer():
    entered.set()
    assert release.wait(2)

  async def exercise():
    owner = asyncio.create_task(history._history_file_writer.run(hold_writer))
    append = None
    try:
      assert await asyncio.to_thread(entered.wait, 2)
      append = asyncio.create_task(
        history._record_route_history_async(_live_route(time.time()))
      )
      for _ in range(4):
        await asyncio.sleep(0)
      assert len(state.route_history_segments) == 1
      append.cancel()
      await asyncio.gather(append, return_exceptions=True)
      assert state.route_history_compact, "cancelled pending evidence lost"
      release.set()
      await owner
      await history._flush_route_history()
      assert len(path.read_text().splitlines()) == 1
      assert json.loads(path.read_text())["message_hash"] == "live"
    finally:
      release.set()
      tasks = [owner]
      if append:
        append.cancel()
        tasks.append(append)
      await asyncio.gather(*tasks, return_exceptions=True)

  try:
    asyncio.run(exercise())
  finally:
    state.route_history_segments.clear()
    state.route_history_edges.clear()
    state.peer_history_pairs.clear()
    state.route_history_compact = False
