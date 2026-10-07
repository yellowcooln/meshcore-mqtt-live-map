import asyncio

import app
import pytest


@pytest.fixture
def isolated_broadcaster(monkeypatch):
  queue = asyncio.Queue()
  monkeypatch.setattr(app, "update_queue", queue)
  for name in (
    "devices", "device_names", "device_roles", "trails", "seen_devices",
    "mqtt_seen", "mqtt_online_source", "mqtt_status_seen",
    "mqtt_status_values", "mqtt_internal_seen", "mqtt_packets_seen",
    "broadcaster_stats",
  ):
    monkeypatch.setattr(app, name, {})
  monkeypatch.setattr(app, "clients", set())
  monkeypatch.setattr(app, "BLOCKED_NAME_SYMBOL_FILTER_ENABLED", False)
  monkeypatch.setattr(app, "MQTT_ONLINE_FORCE_NAMES_SET", set())
  monkeypatch.setattr(app, "PROD_MODE", False)
  return queue


async def _cancel_broadcaster(task):
  task.cancel()
  with pytest.raises(asyncio.CancelledError):
    await task
  assert task.cancelled()


async def _assert_sibling_runs_before_drain(queue):
  count = queue.qsize()

  async def sibling():
    # Let the broadcaster start and process an event before observing progress.
    await asyncio.sleep(0)
    processed = count - queue.qsize()
    assert 0 < processed < count
    assert "last_event_ts" in app.broadcaster_stats

  task = asyncio.create_task(app.broadcaster())
  try:
    await asyncio.create_task(sibling())
  finally:
    await _cancel_broadcaster(task)


def test_missing_device_names_do_not_starve_sibling(isolated_broadcaster):
  queue = isolated_broadcaster
  for _ in range(20000):
    queue.put_nowait({"type": "device_name", "device_id": "missing-node"})

  asyncio.run(_assert_sibling_runs_before_drain(queue))


def test_no_client_presence_broadcast_does_not_starve_sibling(
  isolated_broadcaster, monkeypatch,
):
  queue = isolated_broadcaster
  broadcast_payloads = app._broadcast_payloads
  broadcasts = []

  async def record_real_broadcast(payloads):
    assert not app.clients
    broadcasts.extend(payloads)
    await broadcast_payloads(payloads)

  monkeypatch.setattr(app, "_broadcast_payloads", record_real_broadcast)
  for timestamp in range(1, 20001):
    queue.put_nowait({
      "type": "device_seen", "device_id": "observer",
      "last_seen_ts": timestamp,
    })

  asyncio.run(_assert_sibling_runs_before_drain(queue))

  assert broadcasts
  assert broadcasts[0]["type"] == "device_seen"
  assert broadcasts[0]["last_seen_ts"] == 1
  assert 0 < app.seen_devices["observer"] < 20000


def test_backlog_eventually_drains_preserving_valid_updates(
  isolated_broadcaster,
):
  queue = isolated_broadcaster
  app.devices["mapped-node"] = app.DeviceState(
    device_id="mapped-node", lat=1.0, lon=2.0, ts=1.0,
  )
  app.device_names["mapped-node"] = "Updated node"
  app.device_roles["mapped-node"] = "repeater"
  expected_seen = {}
  for timestamp in range(1, 20001):
    device_id = f"observer-{timestamp}"
    expected_seen[device_id] = timestamp
    queue.put_nowait({
      "type": "device_seen", "device_id": device_id,
      "last_seen_ts": timestamp,
    })
  for event_type in ("device_name", "device_role"):
    queue.put_nowait({"type": event_type, "device_id": "mapped-node"})

  async def drain():
    task = asyncio.create_task(app.broadcaster())
    try:
      # Each turn permits one event; bounded turns avoid wall-clock timing.
      for _ in range(queue.qsize() + 2):
        await asyncio.sleep(0)
        if queue.empty():
          break
      assert queue.empty()
      assert not task.done()
      assert app.seen_devices == expected_seen
      assert app.devices["mapped-node"].name == "Updated node"
      assert app.devices["mapped-node"].role == "repeater"
    finally:
      await _cancel_broadcaster(task)

  asyncio.run(drain())


def test_broadcaster_cancels_while_waiting_on_empty_queue(
  isolated_broadcaster,
):
  async def cancel_idle():
    task = asyncio.create_task(app.broadcaster())
    try:
      # Allow the initial fairness yield and then the empty queue wait.
      for _ in range(3):
        await asyncio.sleep(0)
      assert isolated_broadcaster.empty()
      assert not task.done()
      assert app.broadcaster_stats == {}
    finally:
      await _cancel_broadcaster(task)

  asyncio.run(cancel_idle())
