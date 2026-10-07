"""Real worker regressions; no MQTT/lifespan/persistence writer started.

Set MESHCORE_TEST_NODE_MODULES to the pinned package installation if needed.
Signed replay fixture from the investigation; no private key retained.
"""
import ast
import asyncio
import base64
import copy
import json
import os
from pathlib import Path
import shutil
import subprocess
from types import SimpleNamespace

import pytest
import decoder

VALID = "110073cec45732499f3685e9001122822e4a303f13a79972b4165442c8188e0a3fd2984ec26a9a61988772531b275df43cdde75027906d3a22ee0f4d3dba44ac5a6c78544f4dcff9c7052a483a8a0245d24f14eddfb62c63863b5592e65b0e61e6f874874e0a92ae970d022ea6f1f834343232"
UPSTREAM = "11007E7662676F7F0850A8A355BAAFBFC1EB7B4174C340442D7D7161C9474A2C94006CE7CF682E58408DD8FCC51906ECA98EBF94A037886BDADE7ECD09FD92B839491DF3809C9454F5286D1D3370AC31A34593D569E9A042A3B41FD331DFFB7E18599CE1E60992A076D50238C5B8F85757375354522F50756765744D65736820436F75676172"
PUBKEY = "73CEC45732499F3685E9001122822E4A303F13A79972B4165442C8188E0A3FD2"
RECEIVER = "AB" * 32
TOPIC = f"meshcore/TEST/{RECEIVER}/packets"


def mutated(offset):
  raw = bytearray.fromhex(VALID)
  raw[offset] ^= 1
  return raw.hex()


@pytest.fixture
def worker(tmp_path, monkeypatch):
  if not shutil.which("node"):
    pytest.skip("Node runtime required")
  modules = Path(os.environ.get("MESHCORE_TEST_NODE_MODULES",
      str(Path(decoder.__file__).parent / "node_modules")))
  package = modules / "@michaelhart/meshcore-decoder/package.json"
  if not package.exists():
    if "MESHCORE_TEST_NODE_MODULES" in os.environ:
      pytest.fail("Configured packet-decoder test dependency is missing")
    pytest.skip("Install @michaelhart/meshcore-decoder@0.3.0 for real worker tests")
  assert json.loads(package.read_text())["version"] == "0.3.0"
  (tmp_path / "node_modules").symlink_to(modules.resolve(), target_is_directory=True)
  tree = ast.parse(Path(decoder.__file__).read_text())
  fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef)
            and n.name == "_ensure_node_decoder")
  script = next(ast.literal_eval(n.value) for n in fn.body
                if isinstance(n, ast.Assign)
                and any(isinstance(t, ast.Name) and t.id == "script" for t in n.targets))
  helper = tmp_path / "helper.mjs"
  helper.write_text(script)
  decoder._stop_node_decoder_worker()
  monkeypatch.setattr(decoder, "_node_ready_once", True)
  monkeypatch.setattr(decoder, "NODE_SCRIPT_PATH", str(helper))
  monkeypatch.setattr(decoder, "APP_DIR", str(tmp_path))
  monkeypatch.setattr(decoder, "CHANNEL_SECRETS_FILE", "")
  yield helper
  decoder._stop_node_decoder_worker()


def run_lines(worker, hexes):
  result = subprocess.run(["node", str(worker)],
      input="".join(json.dumps({"hex": h}) + "\n" for h in hexes),
      text=True, capture_output=True, timeout=15, check=True)
  assert not result.stderr
  return [json.loads(line) for line in result.stdout.splitlines()]


def test_worker_rejects_corrupt_then_accepts_valid_in_order(worker):
  bad, good, upstream = run_lines(worker, [mutated(2), VALID, UPSTREAM])
  assert bad.get("invalid_packet") is True
  assert bad["ok"] is False
  assert bad["error"] == "invalid_advert"
  assert not ({"location", "role", "messageHash", "path", "senderName"} & bad.keys())
  assert good["ok"] is True
  assert good["signatureValid"] is True
  assert good["location"] == {"lat": 34.44523, "lon": -118.38101,
                              "name": "4422", "pubkey": PUBKEY}
  assert good["deviceRole"] == 2
  assert upstream["ok"] is True
  assert upstream["signatureValid"] is True


@pytest.fixture
def ingest(worker, monkeypatch):
  import app
  import state
  from collections import deque
  # Replace process-local state in every participating module, preserving aliases.
  for name, value in vars(state).copy().items():
    if not name.startswith("_") and isinstance(value, (dict, list, set, deque)):
      fresh = copy.deepcopy(value) if name == "stats" else type(value)()
      for module in (state, app, decoder):
        if getattr(module, name, None) is value:
          monkeypatch.setattr(module, name, fresh)
  monkeypatch.setattr(state, "state_dirty", False)
  monkeypatch.setattr(app, "MAP_RADIUS_KM", 0)
  monkeypatch.setattr(app, "DEBUG_PAYLOAD", True)
  monkeypatch.setattr(decoder, "DIRECT_COORDS_MODE", "any")
  monkeypatch.setattr(app, "update_queue", asyncio.Queue())
  async def no_broadcast(_):
    pass
  monkeypatch.setattr(app, "_broadcast_payloads", no_broadcast)
  return app


class ImmediateLoop:
  def call_soon_threadsafe(self, fn, *args):
    fn(*args)


def deliver(app, payload, topic=TOPIC):
  app._handle_mqtt_message(None, {"loop": ImmediateLoop()},
      SimpleNamespace(topic=topic, payload=payload))


def authoritative_state(app):
  return copy.deepcopy({name: getattr(app.state, name) for name in (
      "devices", "device_names", "device_roles", "device_role_sources",
      "message_origins", "last_seen_in_advert", "last_seen_in_path",
      "seen_devices", "first_seen_devices", "trails", "routes", "heat_events",
      "node_hash_to_device", "node_hash_candidates", "node_hash_collisions",
      "neighbor_edges", "peer_history_pairs", "route_history_edges",
      "route_history_segments")})


@pytest.mark.parametrize("override", ["origin", "receiver", "none"])
@pytest.mark.parametrize("coords", [False, True])
def test_invalid_ingest_cannot_override_or_mutate_metadata(ingest, override, coords, capsys):
  app = ingest
  # Pre-existing good metadata must never be overwritten by envelope hints.
  app.device_names[PUBKEY] = "trusted"
  app.device_roles[PUBKEY] = "repeater"
  if override != "none":
    target = PUBKEY if override == "origin" else RECEIVER
    app.device_coords[target] = {"lat": 40, "lon": -70}
  before = authoritative_state(app)
  payload = {"raw": mutated(38), "origin_id": PUBKEY, "name": "untrusted",
             "role": "room", "hash": "untrusted-hash", "direction": "rx"}
  if coords:
    payload.update(lat=40, lon=-70)
  deliver(app, json.dumps(payload).encode())
  assert authoritative_state(app) == before
  events = []
  while not app.update_queue.empty():
    events.append(app.update_queue.get_nowait())
  assert all(e["type"] == "mqtt_seen" for e in events), events
  assert app.result_counts.get("invalid_packet") == 1
  assert not app.state.state_dirty or app.mqtt_seen  # independent presence allowed
  assert payload["raw"] not in capsys.readouterr().out


@pytest.mark.parametrize("representation", ["json", "hex", "base64", "binary"])
def test_parser_propagates_invalid_signal_for_all_packet_encodings(worker, representation):
  raw = bytes.fromhex(mutated(2))
  payload = {"json": json.dumps({"raw": raw.hex()}).encode(),
             "hex": raw.hex().encode(), "base64": base64.b64encode(raw),
             "binary": raw}[representation]
  parsed, debug = decoder._try_parse_payload(TOPIC, payload)
  assert parsed is None
  assert debug.get("invalid_packet") is True
  assert debug["result"] == "invalid_packet"
  assert debug["decoded_pubkey"] is None
  assert debug["device_name"] is None
  assert debug["device_role"] is None


def test_invalid_then_valid_reaches_real_broadcaster(ingest):
  app = ingest
  async def replay():
    deliver(app, json.dumps({"raw": mutated(2), "direction": "rx"}).encode())
    assert not app.last_seen_in_advert
    deliver(app, json.dumps({"raw": VALID, "direction": "rx"}).encode())
    task = asyncio.create_task(app.broadcaster())
    try:
      for _ in range(100):
        if app.update_queue.empty():
          break
        await asyncio.sleep(0)
      assert app.update_queue.empty()
      assert set(app.devices) == {PUBKEY}
      node = app.devices[PUBKEY]
      assert (node.name, node.lat, node.lon, node.role) == (
          "4422", 34.44523, -118.38101, "repeater")
      assert set(app.last_seen_in_advert) == {PUBKEY}
    finally:
      task.cancel()
      try:
        await task
      except asyncio.CancelledError:
        pass
  asyncio.run(replay())


def test_genuine_observer_status_direct_coordinates_preserved(ingest):
  app = ingest
  deliver(app, json.dumps({"origin": "Test observer", "lat": 40, "lon": -70,
                          "role": "repeater"}).encode(), TOPIC.replace("packets", "status"))
  events = []
  while not app.update_queue.empty():
    events.append(app.update_queue.get_nowait())
  event = next(e for e in events if e["type"] == "device")
  assert event["data"]["device_id"] == RECEIVER
  assert event["data"]["lat"] == 40
  assert app.device_names[RECEIVER] == "Test observer"


def test_genuine_observer_status_without_coordinates_preserved(ingest):
  app = ingest
  deliver(app, json.dumps({"origin": "Test observer", "role": "repeater",
      "jwt_payload": {"publickey": RECEIVER}}).encode(),
      TOPIC.replace("packets", "status"))
  assert app.device_names[RECEIVER] == "Test observer"
  assert app.device_roles.get(RECEIVER) == "repeater", json.dumps(list(app.debug_last))
  assert not app.result_counts.get("invalid_packet")


@pytest.mark.parametrize("offset", [2, 34, 38, 102, 103, 107, 111])
def test_signed_byte_mutations_never_refresh_existing_device(ingest, offset):
  app = ingest
  app.devices[PUBKEY] = app.state.DeviceState(
      PUBKEY, 34.44523, -118.38101, 123, name="4422", role="repeater")
  app.last_seen_in_advert[PUBKEY] = 123
  before = authoritative_state(app)
  deliver(app, json.dumps({"raw": mutated(offset), "direction": "rx"}).encode())
  assert authoritative_state(app) == before
  assert app.result_counts.get("invalid_packet") == 1
  assert "payload_preview" not in app.debug_last[-1]


@pytest.mark.parametrize("hex_value", ["11", VALID[:80], "not-hex"])
def test_worker_structural_invalidity_is_bounded_and_recoverable(worker, hex_value):
  bad, good = run_lines(worker, [hex_value, VALID])
  assert bad["ok"] is False
  assert bad["invalid_packet"] is True
  assert len(json.dumps(bad)) < 256
  assert "location" not in bad
  assert good["ok"] is True


@pytest.mark.parametrize("fault", ["missing_signature", "verification_exception"])
def test_worker_fails_closed_on_verification_fault(worker, fault):
  # Fault injection only: exercise missing verification status and thrown errors
  # using the actual worker, without substituting fake cryptographic results.
  source = worker.read_text()
  anchor = "  const advert = pickAdvertPayload(decoded);"
  if fault == "missing_signature":
    source = source.replace(anchor,
        "  delete decoded.payload.decoded.signatureValid;\n" + anchor)
  else:
    source = source.replace(anchor,
        "  throw new Error('secret raw packet ' + hex);\n" + anchor)
  worker.write_text(source)
  bad = run_lines(worker, [VALID])[0]
  assert bad["ok"] is False
  assert bad["invalid_packet"] is True
  assert VALID not in json.dumps(bad)
  assert len(json.dumps(bad)) < 256
  assert "location" not in bad


def test_nonadvert_multibyte_routing_and_channel_secret_preserved(ingest, monkeypatch):
  app = ingest
  # Public upstream test fixture (#bot), not a deployment secret.
  secret = "eb50a1bcb3e4e5d7bf69a57c9dada211"
  hex_value = "15833fa002860ccae0eed9ca78b9ab0775d477c1f6490a398bf4edc75240"
  monkeypatch.setattr(decoder, "_load_channel_secrets", lambda: [secret])
  lat, lon, key, name, meta = decoder._decode_meshcore_hex(hex_value)
  assert meta["ok"] is True
  assert meta["signatureValid"] is None
  assert meta["payloadType"] == 5
  assert meta["senderName"] == "Roy B V4"
  assert meta["path"] == ["3FA002", "860CCA", "E0EED9"]
  assert (lat, lon, key, name) == (None, None, None, None)
  deliver(app, json.dumps({"raw": hex_value, "direction": "rx"}).encode())
  events = []
  while not app.update_queue.empty():
    events.append(app.update_queue.get_nowait())
  route = next(e for e in events if e["type"] == "route")
  assert route["path_hashes"] == ["3FA002", "860CCA", "E0EED9"]
  assert route["sender_name"] == "Roy B V4"
  assert app.message_origins[meta["messageHash"]]["sender_name"] == "Roy B V4"
  # Changing secrets in the same persistent worker must update its keystore.
  monkeypatch.setattr(decoder, "_load_channel_secrets", lambda: [])
  undeciphered = decoder._decode_meshcore_hex(hex_value)[4]
  assert undeciphered["ok"] is True
  assert undeciphered["senderName"] is None
