"""Live-route expiry is independent of retained observation evidence."""
import asyncio
import json
import time

import pytest

import app
import decoder
import history
import state


@pytest.fixture
def isolated_routes(monkeypatch):
  for name in (
    "devices", "routes", "seen_devices", "last_seen_in_path",
    "neighbor_edges", "node_hash_candidates", "node_hash_to_device",
    "peer_history_pairs", "route_history_edges", "device_names",
    "device_roles", "device_role_sources", "first_seen_devices",
    "last_seen_in_advert", "message_origins", "mqtt_seen",
  ):
    value = {}
    for module in (state, app, decoder):
      if hasattr(module, name):
        monkeypatch.setattr(module, name, value)
  for module in (state, decoder):
    monkeypatch.setattr(module, "node_hash_collisions", set())
  monkeypatch.setattr(state, "route_history_segments", [])
  monkeypatch.setattr(state, "route_generation", 0, raising=False)
  monkeypatch.setattr(app, "heat_events", [])
  monkeypatch.setattr(app, "clients", set())
  monkeypatch.setattr(app, "MAP_RADIUS_KM", 0)
  monkeypatch.setattr(app, "BLOCKED_NAME_SYMBOL_FILTER_ENABLED", False)
  monkeypatch.setattr(app, "ROUTE_TTL_SECONDS", 60)
  monkeypatch.setattr(app, "PROD_MODE", True)
  monkeypatch.setattr(history, "ROUTE_HISTORY_FILE", "")
  monkeypatch.setattr(history, "ROUTE_HISTORY_ENABLED", True)
  monkeypatch.setattr(history, "ROUTE_HISTORY_ALLOWED_MODES_SET", {"path"})
  monkeypatch.setattr(history, "ROUTE_HISTORY_PAYLOAD_TYPES_SET", {5})
  monkeypatch.setattr(history, "ROUTE_HISTORY_HOURS", 24)
  state.state_dirty = False


def test_expiry_cleanup_cannot_delete_fresh_same_id(isolated_routes, monkeypatch):
  now = time.time()
  old = {
    "id": "same", "generation": 1, "ts": now - 61,
    "expires_at": now - 1, "points": [[42, -71], [42.1, -71.1]],
  }
  fresh = {**old, "generation": 2, "ts": now, "expires_at": now + 60}
  app.routes["same"] = old
  frames = []
  entered, release, iteration_done = (
    asyncio.Event(), asyncio.Event(), asyncio.Event()
  )
  original_asyncio = app.asyncio

  async def sleep(delay):
    if delay == 5:
      iteration_done.set()
      await asyncio.Event().wait()
    else:
      await original_asyncio.sleep(delay)

  class AsyncioProxy:
    def __getattr__(self, name):
      return getattr(original_asyncio, name)

  proxy = AsyncioProxy()
  proxy.sleep = sleep
  monkeypatch.setattr(app, "asyncio", proxy)

  class Receiver:
    async def send_text(self, text):
      message = json.loads(text)
      if message["type"] == "route_remove":
        entered.set()
        await release.wait()
      frames.append(message)

  monkeypatch.setattr(app, "clients", {Receiver()})

  async def exercise():
    task = asyncio.create_task(app.reaper())
    try:
      await asyncio.wait_for(entered.wait(), 2)
      app.routes["same"] = fresh
      await app._broadcast_payloads([
        {"type": "route", "route": app._route_payload(fresh)}
      ])
      release.set()
      await asyncio.wait_for(iteration_done.wait(), 2)
      assert app.routes.get("same") is fresh, "old cleanup deleted fresh route"
      removal = next(frame for frame in frames
                     if frame["type"] == "route_remove")
      assert removal["route_generations"] == {"same": 1}
      assert frames.index(removal) > next(
        index for index, frame in enumerate(frames)
        if frame["type"] == "route"
      ), "fixture must exercise removal delivered after the replacement"
    finally:
      release.set()
      task.cancel()
      await asyncio.gather(task, return_exceptions=True)

  asyncio.run(exercise())


def test_expired_queue_event_keeps_history_without_live_route(
  isolated_routes, monkeypatch
):
  now = time.time()
  origin, hop, receiver = "AA" * 32, "CC" * 32, "BB" * 32
  for key, lat, lon in (
    (origin, 42.0, -71.0), (hop, 42.001, -71.001),
    (receiver, 42.002, -71.002),
  ):
    state.devices[key] = state.DeviceState(
      device_id=key, lat=lat, lon=lon, ts=now, role="repeater"
    )
  decoder._rebuild_node_hash_map()
  frames = []
  recorded = asyncio.Event()
  original_record = app._record_route_history_async

  async def record(route):
    result = await original_record(route)
    recorded.set()
    return result

  class Receiver:
    async def send_text(self, text):
      frames.append(json.loads(text))

  monkeypatch.setattr(app, "_record_route_history_async", record)
  monkeypatch.setattr(app, "clients", {Receiver()})

  async def exercise():
    queue = asyncio.Queue()
    monkeypatch.setattr(app, "update_queue", queue)
    queue.put_nowait({
      "type": "route", "path_hashes": ["cc"], "route_mode": "path",
      "origin_id": origin, "receiver_id": receiver, "payload_type": 5,
      "message_hash": "expired-observation", "ts": now - 61,
    })
    task = asyncio.create_task(app.broadcaster())
    try:
      await asyncio.wait_for(recorded.wait(), 2)
      for _ in range(32):
        await asyncio.sleep(0)
      assert not app.routes, "already-expired event became an active route"
      assert not [frame for frame in frames if frame["type"] == "route"]
      assert len(state.route_history_segments) == 2
      assert len(state.peer_history_pairs) == 2
      assert all(segment["ts"] == now - 61
                 for segment in state.route_history_segments)
      assert all(sum(pair["buckets"].values()) == 1
                 for pair in state.peer_history_pairs.values())
    finally:
      task.cancel()
      await asyncio.gather(task, return_exceptions=True)

  asyncio.run(exercise())
