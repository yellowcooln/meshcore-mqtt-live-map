"""Full device IDs, not names/prefixes/proximity, define node identity."""
import asyncio
from collections import deque
import copy
import json
import time

import pytest

import app
import decoder
import history
import state


A = "32FBB64C" + "11" * 28
B = "32FBB64C" + "22" * 28
C = "99AABBCC" + "33" * 28
PEER = "EE" * 32


@pytest.fixture
def isolated_state(monkeypatch):
  # No lifespan/MQTT/writer; preserve shared aliases in the process-local model.
  for name, value in vars(state).copy().items():
    if name.startswith("_") or not isinstance(value, (dict, list, set, deque)):
      continue
    fresh = copy.deepcopy(value) if name == "stats" else type(value)()
    for module in (state, app, decoder, history):
      if getattr(module, name, None) is value:
        monkeypatch.setattr(module, name, fresh)
  monkeypatch.setattr(state, "state_dirty", False)
  monkeypatch.setattr(app, "MAP_RADIUS_KM", 0)
  monkeypatch.setattr(app, "DEVICE_ROLES_FILE", "")
  monkeypatch.setattr(app, "DEVICE_COORDS_FILE", "")
  monkeypatch.setattr(app, "TRAIL_LEN", 4)
  monkeypatch.setattr(app, "BLOCKED_NAME_SYMBOL_FILTER_ENABLED", False)


def device(device_id, ts, lat=42.36, lon=-71.05):
  return {
    "device_id": device_id, "lat": lat, "lon": lon, "ts": ts,
    "name": "Shared repeater name", "role": "repeater",
  }


@pytest.mark.parametrize("other_id,offset", [(B, 0), (B, .05), (C, 0)])
def test_loaded_distinct_ids_keep_metadata_and_peer_history(
  isolated_state, tmp_path, monkeypatch, other_id, offset
):
  now = time.time()
  ids = (A, other_id)
  payload = {
    "devices": {
      A: device(A, now - 300),
      other_id: device(other_id, now, lat=42.36 + offset),
    },
    "trails": {key: [[42.36, -71.05, now]] for key in ids},
    "device_names": {key: "Shared repeater name" for key in ids},
    "device_roles": {key: "repeater" for key in ids},
    "device_role_sources": {key: "explicit" for key in ids},
    "seen_devices": {A: now - 300, other_id: now},
    "first_seen_devices": {A: now - 7200, other_id: now - 600},
    "last_seen_in_advert": {A: now - 300, other_id: now},
    "last_seen_in_path": {A: now - 300, other_id: now},
    "peer_history_pairs": {
      f"{key}|{PEER}": {
        "a_id": key, "b_id": PEER,
        "buckets": {str(history._peer_history_bucket_start(now)): count},
        "last_ts": (history._peer_history_bucket_start(now) +
                    history.PEER_HISTORY_BUCKET_SECONDS),
      } for key, count in [(A, 3), (other_id, 999)]
    },
  }
  state_file = tmp_path / "state.json"
  state_file.write_text(json.dumps(payload), encoding="utf-8")
  monkeypatch.setattr(app, "STATE_FILE", str(state_file))

  app._load_state()

  assert set(state.devices) == set(ids)
  for field in ("trails", "device_names", "device_roles", "device_role_sources",
                "seen_devices", "first_seen_devices", "last_seen_in_advert",
                "last_seen_in_path"):
    assert getattr(state, field) == payload[field], field
  assert state.peer_history_pairs == payload["peer_history_pairs"]
  if other_id == B:
    assert set(state.node_hash_candidates["32FBB6"]) == set(ids)

  # A save/reload must not silently collapse either identity, either.
  state_file.write_text(json.dumps(app._serialize_state()), encoding="utf-8")
  app._load_state()
  assert set(state.devices) == set(ids)
  assert state.peer_history_pairs == payload["peer_history_pairs"]


def deliver_events(monkeypatch, events):
  emitted = []

  async def run():
    queue = asyncio.Queue()
    monkeypatch.setattr(app, "update_queue", queue)

    async def capture(payloads):
      emitted.extend(copy.deepcopy(payloads))

    monkeypatch.setattr(app, "_broadcast_payloads", capture)
    for update in events:
      queue.put_nowait({"type": "device", "data": update})
    task = asyncio.create_task(app.broadcaster())
    try:
      for _ in range(100):
        await asyncio.sleep(0)
        if task.done():
          task.result()
        if queue.empty():
          await asyncio.sleep(0)
          break
      assert queue.empty(), "broadcaster did not consume the fixture events"
    finally:
      task.cancel()
      with pytest.raises(asyncio.CancelledError):
        await task

  asyncio.run(run())
  return emitted


@pytest.mark.parametrize("other_id", [B, C])
def test_live_distinct_ids_do_not_delete_or_merge_each_other(
  isolated_state, monkeypatch, other_id
):
  now = time.time()
  state.peer_history_pairs[f"{A}|{PEER}"] = {
    "a_id": A, "b_id": PEER,
    "buckets": {str(int(now)): 99}, "last_ts": now,
  }
  peers_before = copy.deepcopy(state.peer_history_pairs)
  emitted = deliver_events(monkeypatch, [device(A, now), device(other_id, now)])

  assert set(state.devices) == {A, other_id}
  assert set(state.trails) == {A, other_id}
  assert state.peer_history_pairs == peers_before
  assert not any(message["type"] == "stale" for message in emitted)
  assert [message["device"]["device_id"] for message in emitted] == [A, other_id]


def test_live_same_full_id_updates_one_record_without_erasing_history(
  isolated_state, monkeypatch
):
  now = time.time()
  first = device(A, now)
  second = {**device(A, now + 1, lat=42.37), "name": "Renamed repeater"}
  state.peer_history_pairs[f"{A}|{PEER}"] = {
    "a_id": A, "b_id": PEER,
    "buckets": {str(int(now)): 3}, "last_ts": now,
  }
  peers_before = copy.deepcopy(state.peer_history_pairs)
  emitted = deliver_events(monkeypatch, [first, second])

  assert set(state.devices) == {A}
  assert state.devices[A].name == "Renamed repeater"
  assert state.devices[A].lat == 42.37
  assert len(state.trails[A]) == 2
  assert state.peer_history_pairs == peers_before
  assert [message["type"] for message in emitted] == ["update", "update"]
