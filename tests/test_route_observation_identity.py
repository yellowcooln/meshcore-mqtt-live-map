"""Compatibility: multi-observer and changed-path observations are not deduped."""
import asyncio
import json
import time

import pytest

import app
import decoder
import history
import state
from test_route_expiry import isolated_routes


@pytest.mark.parametrize("enabled", [True, False])
def test_many_observers_and_changed_path_keep_all_evidence(
  isolated_routes, monkeypatch, tmp_path, enabled
):
  now = time.time()
  origin, hop, alternate = "AA" * 32, "CC" * 32, "DD" * 32
  observers = [f"{index + 1:064x}" for index in range(40)]
  for key, lat, lon in [
    (origin, 42.0, -71.0), (hop, 42.001, -71.001),
    (alternate, 42.0015, -71.0015),
    *[(key, 42.002, -71.002) for key in observers],
  ]:
    state.devices[key] = state.DeviceState(
      device_id=key, lat=lat, lon=lon, ts=now, role="repeater"
    )
  decoder._rebuild_node_hash_map()
  path = tmp_path / "history.jsonl"
  monkeypatch.setattr(history, "ROUTE_HISTORY_FILE", str(path))
  monkeypatch.setattr(history, "ROUTE_HISTORY_ENABLED", enabled)
  delivered = asyncio.Event()
  frames = []

  class Receiver:
    async def send_text(self, text):
      payload = json.loads(text)
      if payload["type"] == "route":
        frames.append(payload["route"])
        delivered.set()

  monkeypatch.setattr(app, "clients", {Receiver()})

  async def exercise():
    queue = asyncio.Queue()
    monkeypatch.setattr(app, "update_queue", queue)
    task = asyncio.create_task(app.broadcaster())
    try:
      for observer in observers:
        delivered.clear()
        queue.put_nowait({
          "type": "route", "path_hashes": ["cc"],
          "route_mode": "path", "payload_type": 5,
          "origin_id": origin, "receiver_id": observer,
          "message_hash": "one-message", "ts": now,
        })
        await asyncio.wait_for(delivered.wait(), 2)
      assert len(app.routes) == len(observers)
      assert len({route["generation"] for route in frames}) == len(observers)
      assert all(route["generation"] > 0 for route in frames)
      original_id = f"one-message:{observers[0]}"
      original_generation = app.routes[original_id]["generation"]
      original_points = app.routes[original_id]["points"]
      delivered.clear()
      queue.put_nowait({
        "type": "route", "path_hashes": ["dd"],
        "route_mode": "path", "payload_type": 5,
        "origin_id": origin, "receiver_id": observers[0],
        "message_hash": "one-message", "ts": now,
      })
      await asyncio.wait_for(delivered.wait(), 2)
      assert len(app.routes) == len(observers)
      assert app.routes[original_id]["generation"] > original_generation
      assert app.routes[original_id]["points"] != original_points
      expected_segments = (len(observers) + 1) * 2
      assert len(state.route_history_segments) == (
        expected_segments if enabled else 0
      )
      assert sum(sum(pair["buckets"].values())
                 for pair in state.peer_history_pairs.values()) == (
                   expected_segments
                 )
      if enabled:
        rows = [json.loads(line) for line in path.read_text().splitlines()]
        assert len(rows) == expected_segments
        assert {row["receiver_id"] for row in rows} == set(observers)
      else:
        assert not path.exists()
    finally:
      task.cancel()
      await asyncio.gather(task, return_exceptions=True)

  asyncio.run(exercise())
