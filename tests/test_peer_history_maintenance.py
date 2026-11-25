"""Peer maintenance must not scale every route with unrelated history."""
import asyncio
import time

import pytest

import app
import history
import state


class UnrelatedBuckets(dict):
  def copy(self):
    raise AssertionError("route processing scanned unrelated peer buckets")


@pytest.fixture(autouse=True)
def isolated_history(monkeypatch):
  state.peer_history_pairs.clear()
  state.route_history_segments.clear()
  state.route_history_edges.clear()
  state.state_dirty = False
  monkeypatch.setattr(history, "ROUTE_HISTORY_FILE", "")
  monkeypatch.setattr(history, "ROUTE_HISTORY_HOURS", 24)
  monkeypatch.setattr(history, "ROUTE_HISTORY_ALLOWED_MODES_SET", {"path"})
  monkeypatch.setattr(history, "ROUTE_HISTORY_PAYLOAD_TYPES_SET", {5})
  monkeypatch.setattr(app, "ROUTE_HISTORY_HOURS", 24)
  yield
  state.peer_history_pairs.clear()
  state.route_history_segments.clear()
  state.route_history_edges.clear()
  state.state_dirty = False


@pytest.mark.parametrize("enabled", [True, False])
@pytest.mark.parametrize("drawable", [True, False])
def test_route_only_updates_its_own_peer_history(monkeypatch, enabled, drawable):
  now = time.time()
  bucket = str(history._peer_history_bucket_start(now))
  unrelated = UnrelatedBuckets({bucket: 7})
  state.peer_history_pairs["unrelated"] = {
    "a_id": "11" * 32,
    "b_id": "22" * 32,
    "buckets": unrelated,
    "last_ts": now,
  }
  monkeypatch.setattr(history, "ROUTE_HISTORY_ENABLED", enabled)
  a_id, b_id = "AA" * 32, "BB" * 32
  points = [[42.36, -71.05], [42.37, -71.06]] if drawable else []
  updates, removed = history._record_route_history({
    "points": points,
    "point_ids": [a_id, b_id],
    "payload_type": 5,
    "route_mode": "path",
    "message_hash": "accepted-observation",
    "receiver_id": b_id,
    "ts": now,
  })

  assert state.peer_history_pairs["unrelated"]["buckets"] is unrelated
  assert unrelated[bucket] == 7
  pair = state.peer_history_pairs[history._peer_history_pair_key(a_id, b_id)]
  assert pair["buckets"] == {bucket: 1}
  assert state.state_dirty
  assert len(state.route_history_segments) == int(enabled and drawable)
  assert len(updates) == int(enabled and drawable)
  assert removed == []


def test_reaper_yields_during_large_peer_cleanup(monkeypatch):
  now = time.time()
  old_bucket = str(history._peer_history_bucket_start(now - 26 * 3600))
  current_bucket = str(history._peer_history_bucket_start(now))
  for index in range(513):
    state.peer_history_pairs[str(index)] = {
      "a_id": "AA" * 32,
      "b_id": "BB" * 32,
      "buckets": {old_bucket: 1},
      "last_ts": now - 26 * 3600,
    }
  for name in ("devices", "routes", "message_origins", "seen_devices"):
    monkeypatch.setattr(app, name, {})
  monkeypatch.setattr(app, "heat_events", [])
  monkeypatch.setattr(app, "clients", set())

  async def exercise():
    task = asyncio.create_task(app.reaper())
    try:
      await asyncio.sleep(0)
      assert state.peer_history_pairs, (
        "global cleanup monopolized the loop until all peers were scanned"
      )
      state.peer_history_pairs["512"] = {
        "a_id": "AA" * 32,
        "b_id": "BB" * 32,
        "buckets": {current_bucket: 3},
        "last_ts": now,
      }
      for _ in range(32):
        await asyncio.sleep(0)
      assert set(state.peer_history_pairs) == {"512"}
      assert state.peer_history_pairs["512"]["buckets"] == {
        current_bucket: 3
      }
      assert state.state_dirty
    finally:
      task.cancel()
      await asyncio.gather(task, return_exceptions=True)

  asyncio.run(exercise())


def test_peer_expiry_preserves_bucket_at_cutoff_and_read_filter(monkeypatch):
  now = float(history._peer_history_bucket_start(time.time()))
  boundary = now - 24 * 3600
  a_id, b_id = "AA" * 32, "BB" * 32
  state.peer_history_pairs["edge"] = {
    "a_id": a_id,
    "b_id": b_id,
    "buckets": {
      str(int(boundary - 600)): 9,
      str(int(boundary - 300)): 2,
      str(int(boundary)): 3,
    },
    "last_ts": now,
  }
  monkeypatch.setattr(app.time, "time", lambda: now)
  assert app._peer_stats_for_device(a_id, limit=8)["outgoing_total"] == 5
  assert history._prune_peer_history(now)
  assert state.peer_history_pairs["edge"]["buckets"] == {
    str(int(boundary - 300)): 2,
    str(int(boundary)): 3,
  }
