import json
import time

import app
import history
import state


def test_load_state_drops_zero_devices_and_keeps_valid_entries(
  tmp_path, monkeypatch
):
  now = time.time()
  state_file = tmp_path / "state.json"
  state_file.write_text(
    json.dumps(
      {
        "devices": {
          "ABCD1111": {
            "device_id": "ABCD1111",
            "lat": 42.36,
            "lon": -71.05,
            "ts": now,
            "name": "Node A",
            "role": "repeater",
            "heading": None,
            "speed": None,
            "rssi": None,
            "snr": None,
            "raw_topic": None,
          },
          "ZERO0000": {
            "device_id": "ZERO0000",
            "lat": 0.0,
            "lon": 0.0,
            "ts": now,
            "name": "Zero",
            "role": "repeater",
            "heading": None,
            "speed": None,
            "rssi": None,
            "snr": None,
            "raw_topic": None,
          },
        },
        "trails": {
          "ABCD1111": [[42.36, -71.05, now], [0.0, 0.0, now]],
          "ZERO0000": [[0.0, 0.0, now]],
        },
        "seen_devices": {
          "ABCD1111": now,
          "ZERO0000": now,
        },
        "device_names": {
          "ABCD1111": "Node A",
          "ZERO0000": "Zero",
        },
        "device_roles": {
          "ABCD1111": "repeater",
          "ZERO0000": "repeater",
        },
        "device_role_sources": {
          "ABCD1111": "explicit",
          "ZERO0000": "explicit",
        },
        "last_seen_in_path": {
          "ABCD1111": now,
          "ZERO0000": now,
        },
      }
    ),
    encoding="utf-8",
  )

  state.devices.clear()
  state.trails.clear()
  state.seen_devices.clear()
  state.device_names.clear()
  state.device_roles.clear()
  state.device_role_sources.clear()
  state.last_seen_in_path.clear()
  state.peer_history_pairs.clear()

  monkeypatch.setattr(app, "STATE_FILE", str(state_file))
  monkeypatch.setattr(app, "DEVICE_ROLES_FILE", "")
  monkeypatch.setattr(app, "DEVICE_COORDS_FILE", "")
  monkeypatch.setattr(app, "TRAIL_LEN", 10)

  app._load_state()

  assert "ABCD1111" in state.devices
  assert "ZERO0000" not in state.devices
  assert "ZERO0000" not in state.seen_devices
  assert "ZERO0000" not in state.device_names
  assert "ZERO0000" not in state.last_seen_in_path
  assert len(state.trails["ABCD1111"]) == 1


def test_route_history_round_trip_file_load(tmp_path, monkeypatch):
  hist_file = tmp_path / "route_history.jsonl"
  now = time.time()
  entry = {
    "ts": now,
    "a": [42.3601, -71.0589],
    "b": [42.3611, -71.0579],
    "a_id": "AA001111",
    "b_id": "BB001111",
    "message_hash": "msg1",
    "payload_type": 2,
    "origin_id": "AA001111",
    "receiver_id": "BB001111",
    "route_mode": "path",
    "topic": "meshcore/test",
  }

  monkeypatch.setattr(history, "ROUTE_HISTORY_FILE", str(hist_file))
  monkeypatch.setattr(history, "ROUTE_HISTORY_ENABLED", True)
  monkeypatch.setattr(history, "ROUTE_HISTORY_HOURS", 24)

  state.route_history_segments.clear()
  state.route_history_edges.clear()
  state.peer_history_pairs.clear()
  history._append_route_history_file([entry])

  state.route_history_segments.clear()
  state.route_history_edges.clear()
  state.peer_history_pairs.clear()
  history._load_route_history()

  assert len(state.route_history_segments) == 1
  assert len(state.route_history_edges) == 1
  assert len(state.peer_history_pairs) == 1
  loaded = state.route_history_segments[0]
  assert loaded["a_id"] == "AA001111"
  assert loaded["b_id"] == "BB001111"


def test_load_state_ignores_corrupt_json_file(tmp_path, monkeypatch):
  state_file = tmp_path / "state.json"
  state_file.write_text("{not-valid-json", encoding="utf-8")

  state.devices.clear()
  state.devices["KEEP1111"] = state.DeviceState(
    device_id="KEEP1111",
    lat=42.0,
    lon=-71.0,
    ts=time.time(),
    role="repeater",
  )

  monkeypatch.setattr(app, "STATE_FILE", str(state_file))
  app._load_state()

  assert "KEEP1111" in state.devices


def test_load_state_preserves_distinct_same_name_same_location_ids(
  tmp_path, monkeypatch
):
  now = time.time()
  state_file = tmp_path / "state.json"
  state_file.write_text(
    json.dumps(
      {
        "devices": {
          "REAL1111": {
            "device_id": "REAL1111",
            "lat": 42.36,
            "lon": -71.05,
            "ts": now,
            "name": "Node A",
            "role": "repeater",
            "heading": None,
            "speed": None,
            "rssi": None,
            "snr": None,
            "raw_topic": None,
          },
          "GHOST111": {
            "device_id": "GHOST111",
            "lat": 42.36,
            "lon": -71.05,
            "ts": now - 300,
            "name": "Node A",
            "role": "repeater",
            "heading": None,
            "speed": None,
            "rssi": None,
            "snr": None,
            "raw_topic": None,
          },
          "025055A6AAAA": {
            "device_id": "025055A6AAAA",
            "lat": 33.821170,
            "lon": -118.381010,
            "ts": now - 100,
            "name": "4422",
            "role": "repeater",
            "heading": None,
            "speed": None,
            "rssi": None,
            "snr": None,
            "raw_topic": None,
          },
          "025055A6BBBB": {
            "device_id": "025055A6BBBB",
            "lat": 33.823170,
            "lon": -118.383010,
            "ts": now - 50,
            "name": "4422",
            "role": "repeater",
            "heading": None,
            "speed": None,
            "rssi": None,
            "snr": None,
            "raw_topic": None,
          },
        },
        "seen_devices": {
          "REAL1111": now,
          "GHOST111": now - 300,
          "025055A6AAAA": now - 100,
          "025055A6BBBB": now - 50,
        },
        "first_seen_devices": {
          "REAL1111": now - 7200,
          "GHOST111": now - 600,
          "025055A6AAAA": now - 7200,
          "025055A6BBBB": now - 600,
        },
        "device_names": {
          "REAL1111": "Node A",
          "GHOST111": "Node A",
          "025055A6AAAA": "4422",
          "025055A6BBBB": "4422",
        },
        "device_roles": {
          "REAL1111": "repeater",
          "GHOST111": "repeater",
          "025055A6AAAA": "repeater",
          "025055A6BBBB": "repeater",
        },
        "device_role_sources": {
          "REAL1111": "explicit",
          "GHOST111": "explicit",
          "025055A6AAAA": "explicit",
          "025055A6BBBB": "explicit",
        },
        "last_seen_in_advert": {
          "025055A6AAAA": now - 3600,
          "025055A6BBBB": now,
        },
        "peer_history_pairs": {
          "025055A6BBBB|PEER1111": {
            "a_id": "025055A6BBBB",
            "b_id": "PEER1111",
            "buckets": {
              str(int(now)): 3,
            },
            "last_ts": now,
          },
        },
      }
    ),
    encoding="utf-8",
  )

  state.devices.clear()
  state.trails.clear()
  state.seen_devices.clear()
  state.device_names.clear()
  state.device_roles.clear()
  state.device_role_sources.clear()
  state.first_seen_devices.clear()

  monkeypatch.setattr(app, "STATE_FILE", str(state_file))
  monkeypatch.setattr(app, "DEVICE_ROLES_FILE", "")
  monkeypatch.setattr(app, "DEVICE_COORDS_FILE", "")

  app._load_state()

  # These are distinct identifiers; their names/location/prefix similarity
  # is not evidence permitting deletion or transfer of one node's history.
  assert set(state.devices) == {
    "REAL1111", "GHOST111", "025055A6AAAA", "025055A6BBBB"
  }
  assert state.seen_devices["GHOST111"] == now - 300
  assert state.device_names["GHOST111"] == "Node A"
  assert state.last_seen_in_advert["025055A6AAAA"] == now - 3600
  assert set(state.peer_history_pairs) == {"025055A6BBBB|PEER1111"}


def test_route_history_load_skips_bad_lines_and_marks_compact(
  tmp_path, monkeypatch
):
  hist_file = tmp_path / "route_history.jsonl"
  now = time.time()
  old_ts = now - (72 * 3600)

  lines = [
    "{bad-json",
    json.dumps(["not", "a", "dict"]),
    json.dumps(
      {
        "ts": old_ts,
        "a": [42.0, -71.0],
        "b": [42.1, -71.1],
      }
    ),
    json.dumps(
      {
        "ts": now,
        "a": [42.0, -71.0],
        "b": None,
      }
    ),
    json.dumps(
      {
        "ts": now,
        "a": [42.3601, -71.0589],
        "b": [42.3611, -71.0579],
        "a_id": "AA001111",
        "b_id": "BB001111",
        "message_hash": "msg1",
      }
    ),
  ]
  hist_file.write_text("\n".join(lines) + "\n", encoding="utf-8")

  monkeypatch.setattr(history, "ROUTE_HISTORY_FILE", str(hist_file))
  monkeypatch.setattr(history, "ROUTE_HISTORY_ENABLED", True)
  monkeypatch.setattr(history, "ROUTE_HISTORY_HOURS", 24)

  state.route_history_segments.clear()
  state.route_history_edges.clear()
  state.peer_history_pairs.clear()
  state.route_history_compact = False
  history._load_route_history()

  assert len(state.route_history_segments) == 1
  assert len(state.route_history_edges) == 1
  assert len(state.peer_history_pairs) == 1
  assert state.route_history_compact is True
