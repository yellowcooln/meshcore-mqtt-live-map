"""Exercise snapshot ownership and real file-write scheduling."""
import asyncio
import builtins
import json
import threading
from collections import deque
from types import SimpleNamespace

import app
import history
import state


class ScalarBuckets(dict):
  def __deepcopy__(self, memo):
    raise AssertionError("snapshot recursively traversed scalar peer buckets")


def test_snapshot_copies_integer_bucket_mapping_without_recursive_walk(
  monkeypatch
):
  bucket_counts = ScalarBuckets({"100": 3, "400": 7})
  pairs = {"a|b": {
    "a_id": "a", "b_id": "b", "last_ts": 450.0,
    "buckets": bucket_counts,
  }}
  monkeypatch.setattr(app, "peer_history_pairs", pairs)
  monkeypatch.setattr(app, "devices", {})
  monkeypatch.setattr(app, "trails", {"a": [[42.0, -71.0, 450.0]]})
  snapshot = app._serialize_state()
  bucket_counts["100"] = 99
  pairs["a|b"]["last_ts"] = 999.0
  app.trails["a"][0][0] = 1.0
  assert snapshot["peer_history_pairs"]["a|b"]["buckets"] == {
    "100": 3, "400": 7
  }
  assert snapshot["peer_history_pairs"]["a|b"]["last_ts"] == 450.0
  assert snapshot["trails"]["a"][0][0] == 42.0
  assert json.loads(json.dumps(snapshot))["version"] == 1


def test_state_file_write_does_not_block_event_loop(tmp_path, monkeypatch):
  path = tmp_path / "state.json"
  entered = threading.Event()
  release = threading.Event()
  completed = asyncio.Event()
  original_open = builtins.open
  original_asyncio = app.asyncio

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
        assert release.wait(2), "test failed to release the file writer"
      return self.handle.write(text)

  def controlled_open(name, *args, **kwargs):
    handle = original_open(name, *args, **kwargs)
    return BlockingFile(handle) if str(name) == str(path) + ".tmp" else handle

  async def pause(_delay):
    completed.set()
    await asyncio.Event().wait()

  class AsyncioProxy:
    def __getattr__(self, name):
      return getattr(original_asyncio, name)

    sleep = staticmethod(pause)

  monkeypatch.setattr(builtins, "open", controlled_open)
  monkeypatch.setattr(app, "asyncio", AsyncioProxy())
  monkeypatch.setattr(app, "STATE_FILE", str(path))
  monkeypatch.setattr(app, "peer_history_pairs", {})
  monkeypatch.setattr(app, "devices", {})
  state.state_dirty = True

  def emergency_release():
    if entered.wait(2):
      release.wait(0.25)
      release.set()

  unblocker = threading.Thread(target=emergency_release, daemon=True)
  unblocker.start()

  async def exercise():
    task = asyncio.create_task(app._state_saver())
    try:
      assert await asyncio.to_thread(entered.wait, 2)
      assert not release.is_set(), "state file write blocked the event loop"
      release.set()
      await asyncio.wait_for(completed.wait(), 2)
      assert json.loads(path.read_text())["version"] == 1
      assert not state.state_dirty
    finally:
      release.set()
      task.cancel()
      await asyncio.gather(task, return_exceptions=True)

  try:
    asyncio.run(exercise())
  finally:
    release.set()
    unblocker.join(2)
    state.state_dirty = False


def _inflight_state_write(tmp_path, monkeypatch):
  path = tmp_path / "state.json"
  entered = threading.Event()
  release = threading.Event()
  completed = asyncio.Event()
  original_write = app._write_state_file
  original_asyncio = app.asyncio

  def controlled_write(name, payload):
    entered.set()
    assert release.wait(2), "test did not release the owned writer"
    original_write(name, payload)

  async def pause(_delay):
    completed.set()
    await asyncio.Event().wait()

  class AsyncioProxy:
    def __getattr__(self, name):
      return getattr(original_asyncio, name)

    sleep = staticmethod(pause)

  monkeypatch.setattr(app, "asyncio", AsyncioProxy())
  monkeypatch.setattr(app, "_write_state_file", controlled_write)
  monkeypatch.setattr(app, "STATE_FILE", str(path))
  monkeypatch.setattr(app, "devices", {})
  monkeypatch.setattr(app, "peer_history_pairs", {})
  monkeypatch.setattr(app, "seen_devices", {"before": 100.0})
  state.state_dirty = True
  return SimpleNamespace(
    path=path, entered=entered, release=release, completed=completed
  )


def test_changes_during_state_write_remain_dirty(tmp_path, monkeypatch):
  fixture = _inflight_state_write(tmp_path, monkeypatch)

  async def exercise():
    task = asyncio.create_task(app._state_saver())
    try:
      assert await asyncio.to_thread(fixture.entered.wait, 2)
      app.seen_devices["during"] = 200.0
      state.state_dirty = True
      fixture.release.set()
      await asyncio.wait_for(fixture.completed.wait(), 2)
      saved = json.loads(fixture.path.read_text())
      assert "during" not in saved["seen_devices"], "snapshot was mutable"
      assert state.state_dirty, "completed old snapshot erased newer changes"
    finally:
      fixture.release.set()
      task.cancel()
      await asyncio.gather(task, return_exceptions=True)

  try:
    asyncio.run(exercise())
  finally:
    state.state_dirty = False


def test_cancellation_retains_writer_until_atomic_replace(tmp_path, monkeypatch):
  fixture = _inflight_state_write(tmp_path, monkeypatch)

  async def exercise():
    task = asyncio.create_task(app._state_saver())
    try:
      assert await asyncio.to_thread(fixture.entered.wait, 2)
      task.cancel()
      for _ in range(3):
        await asyncio.sleep(0)
      assert not task.done(), "cancellation abandoned an active file writer"
      task.cancel()
      for _ in range(3):
        await asyncio.sleep(0)
      assert not task.done(), "repeated cancellation abandoned the writer"
      fixture.release.set()
      result = await asyncio.gather(task, return_exceptions=True)
      assert isinstance(result[0], asyncio.CancelledError)
      assert json.loads(fixture.path.read_text())["version"] == 1
      assert not fixture.path.with_suffix(".json.tmp").exists()
    finally:
      fixture.release.set()
      task.cancel()
      await asyncio.gather(task, return_exceptions=True)

  try:
    asyncio.run(exercise())
  finally:
    state.state_dirty = False


def test_shutdown_saves_processed_changes_before_periodic_interval(
  tmp_path, monkeypatch
):
  path = tmp_path / "state.json"
  history_path = tmp_path / "history.jsonl"

  class FakeClient:
    def __init__(self, *args, **kwargs):
      pass

    def reconnect_delay_set(self, *args, **kwargs):
      pass

    def connect_async(self, *args, **kwargs):
      pass

    def loop_start(self):
      pass

    def loop_stop(self):
      pass

    def disconnect(self):
      pass

  monkeypatch.setattr(app.mqtt, "Client", FakeClient)
  monkeypatch.setattr(app, "_ensure_node_decoder", lambda: None)
  monkeypatch.setattr(app, "_check_git_updates", lambda: None)
  monkeypatch.setattr(app, "STATE_FILE", str(path))
  monkeypatch.setattr(app, "devices", {})
  monkeypatch.setattr(app, "peer_history_pairs", {})
  monkeypatch.setattr(app, "seen_devices", {})
  monkeypatch.setattr(app, "background_tasks", set())
  monkeypatch.setattr(app, "MQTT_USERNAME", "")
  monkeypatch.setattr(app, "MQTT_TLS", False)
  monkeypatch.setattr(app, "MQTT_TRANSPORT", "tcp")
  monkeypatch.setattr(app, "BACKUP_ENABLED", False)
  monkeypatch.setattr(history, "ROUTE_HISTORY_FILE", str(history_path))
  monkeypatch.setattr(history, "ROUTE_HISTORY_ENABLED", True)
  monkeypatch.setattr(state, "route_history_segments", deque())
  monkeypatch.setattr(state, "route_history_compact", False)
  state.state_dirty = False

  async def exercise():
    async with app._lifespan(app.app):
      # No scheduling turn: periodic saver has not run yet.
      app.seen_devices["accepted-before-shutdown"] = 123.0
      state.state_dirty = True
      state.route_history_segments.append({"message_hash": "accepted"})
      state.route_history_compact = True
    assert path.exists(), "shutdown lost changes awaiting the next save tick"
    saved = json.loads(path.read_text())
    assert saved["seen_devices"]["accepted-before-shutdown"] == 123.0
    assert not state.state_dirty
    assert history_path.exists(), "shutdown skipped pending history compaction"
    assert json.loads(history_path.read_text())["message_hash"] == "accepted"

  try:
    asyncio.run(exercise())
  finally:
    state.state_dirty = False
