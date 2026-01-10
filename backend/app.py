import asyncio
import json
import os
import html
import time
from datetime import datetime, timezone
from dataclasses import asdict
from typing import Any, Dict, Optional, Set, List

import httpx
import paho.mqtt.client as mqtt
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

import state
from decoder import (
  ROUTE_PAYLOAD_TYPES_SET,
  _append_heat_points,
  _coords_are_zero,
  _device_id_from_topic,
  _ensure_node_decoder,
  _normalize_lat_lon,
  _normalize_role,
  _rebuild_node_hash_map,
  _route_points_from_hashes,
  _route_points_from_device_ids,
  _safe_preview,
  _serialize_heat_events,
  _topic_marks_online,
  _try_parse_payload,
  DIRECT_COORDS_TOPIC_RE,
  _node_ready_once,
  _node_unavailable_once,
)
from history import (
  _load_route_history,
  _prune_route_history,
  _record_route_history,
  _route_history_saver,
)
from los import (
  _fetch_elevations,
  _find_los_peaks,
  _find_los_suggestion,
  _haversine_m,
  _los_max_obstruction,
  _sample_los_points,
)
from config import (
  MQTT_HOST,
  MQTT_PORT,
  MQTT_USERNAME,
  MQTT_PASSWORD,
  MQTT_TOPIC,
  MQTT_TOPICS,
  MQTT_TLS,
  MQTT_TLS_INSECURE,
  MQTT_CA_CERT,
  MQTT_TRANSPORT,
  MQTT_WS_PATH,
  MQTT_CLIENT_ID,
  STATE_DIR,
  STATE_FILE,
  DEVICE_ROLES_FILE,
  STATE_SAVE_INTERVAL,
  DEVICE_TTL_SECONDS,
  TRAIL_LEN,
  ROUTE_TTL_SECONDS,
  ROUTE_PAYLOAD_TYPES,
  ROUTE_PATH_MAX_LEN,
  ROUTE_HISTORY_ENABLED,
  ROUTE_HISTORY_HOURS,
  ROUTE_HISTORY_MAX_SEGMENTS,
  ROUTE_HISTORY_FILE,
  ROUTE_HISTORY_PAYLOAD_TYPES,
  ROUTE_HISTORY_ALLOWED_MODES,
  ROUTE_HISTORY_COMPACT_INTERVAL,
  HISTORY_EDGE_SAMPLE_LIMIT,
  MESSAGE_ORIGIN_TTL_SECONDS,
  HEAT_TTL_SECONDS,
  MQTT_ONLINE_SECONDS,
  MQTT_SEEN_BROADCAST_MIN_SECONDS,
  MQTT_ONLINE_TOPIC_SUFFIXES,
  MQTT_ONLINE_FORCE_NAMES_SET,
  DEBUG_PAYLOAD,
  DEBUG_PAYLOAD_MAX,
  DECODE_WITH_NODE,
  NODE_DECODE_TIMEOUT_SECONDS,
  PAYLOAD_PREVIEW_MAX,
  DIRECT_COORDS_MODE,
  DIRECT_COORDS_TOPIC_REGEX,
  DIRECT_COORDS_ALLOW_ZERO,
  ROUTE_HISTORY_ALLOWED_MODES_SET,
  SITE_TITLE,
  SITE_DESCRIPTION,
  SITE_OG_IMAGE,
  SITE_URL,
  SITE_ICON,
  SITE_FEED_NOTE,
  DISTANCE_UNITS,
  NODE_MARKER_RADIUS,
  HISTORY_LINK_SCALE,
  MAP_START_LAT,
  MAP_START_LON,
  MAP_START_ZOOM,
  MAP_RADIUS_KM,
  MAP_RADIUS_SHOW,
  MAP_DEFAULT_LAYER,
  PROD_MODE,
  PROD_TOKEN,
  LOS_ELEVATION_URL,
  LOS_SAMPLE_MIN,
  LOS_SAMPLE_MAX,
  LOS_SAMPLE_STEP_METERS,
  ELEVATION_CACHE_TTL,
  LOS_PEAKS_MAX,
  COVERAGE_API_URL,
  APP_DIR,
  NODE_SCRIPT_PATH,
)
from state import (
  DeviceState,
  stats,
  result_counts,
  seen_devices,
  mqtt_seen,
  last_seen_broadcast,
  topic_counts,
  debug_last,
  status_last,
  devices,
  trails,
  routes,
  heat_events,
  route_history_segments,
  route_history_edges,
  node_hash_to_device,
  node_hash_collisions,
  node_hash_candidates,
  elevation_cache,
  device_names,
  message_origins,
  device_roles,
  device_role_sources,
)

# =========================
# App / State
# =========================
app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")

mqtt_client: Optional[mqtt.Client] = None
clients: Set[WebSocket] = set()
update_queue: asyncio.Queue[Dict[str, Any]] = asyncio.Queue()

# =========================
# Helpers: coordinate hunting
# =========================
def _load_role_overrides() -> Dict[str, str]:
  if not DEVICE_ROLES_FILE or not os.path.exists(DEVICE_ROLES_FILE):
    return {}
  try:
    with open(DEVICE_ROLES_FILE, "r", encoding="utf-8") as handle:
      data = json.load(handle)
  except Exception:
    return {}
  if not isinstance(data, dict):
    return {}
  roles: Dict[str, str] = {}
  for key, value in data.items():
    if not isinstance(key, str) or not isinstance(value, str):
      continue
    role = _normalize_role(value)
    if not role:
      continue
    roles[key.strip()] = role
  return roles


def _serialize_state() -> Dict[str, Any]:
  return {
    "version": 1,
    "saved_at": time.time(),
    "devices": {k: asdict(v) for k, v in devices.items()},
    "trails": trails,
    "seen_devices": seen_devices,
    "device_names": device_names,
    "device_roles": device_roles,
    "device_role_sources": device_role_sources,
  }


def _device_payload(device_id: str, state: "DeviceState") -> Dict[str, Any]:
  payload = asdict(state)
  last_seen = seen_devices.get(device_id)
  if last_seen:
    payload["last_seen_ts"] = last_seen
  else:
    payload["last_seen_ts"] = payload.get("ts")
  mqtt_seen_ts = mqtt_seen.get(device_id)
  if mqtt_seen_ts:
    payload["mqtt_seen_ts"] = mqtt_seen_ts
  if MQTT_ONLINE_FORCE_NAMES_SET:
    name_value = (state.name or device_names.get(device_id) or "").strip().lower()
    if name_value and name_value in MQTT_ONLINE_FORCE_NAMES_SET:
      payload["mqtt_forced"] = True
  if PROD_MODE:
    payload.pop("raw_topic", None)
  return payload


def _iso_from_ts(ts: Optional[float]) -> Optional[str]:
  if ts is None:
    return None
  try:
    return datetime.fromtimestamp(float(ts), tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
  except Exception:
    return None


def _within_map_radius(lat: Any, lon: Any) -> bool:
  if MAP_RADIUS_KM <= 0:
    return True
  try:
    lat_val = float(lat)
    lon_val = float(lon)
  except (TypeError, ValueError):
    return False
  distance_m = _haversine_m(MAP_START_LAT, MAP_START_LON, lat_val, lon_val)
  return distance_m <= (MAP_RADIUS_KM * 1000.0)


def _evict_device(device_id: str) -> bool:
  removed = False
  if device_id in devices:
    devices.pop(device_id, None)
    removed = True
  trails.pop(device_id, None)
  seen_devices.pop(device_id, None)
  mqtt_seen.pop(device_id, None)
  last_seen_broadcast.pop(device_id, None)
  if removed:
    state.state_dirty = True
    _rebuild_node_hash_map()
  return removed


def _device_role_code(value: Any) -> int:
  if isinstance(value, int):
    if value in (1, 2, 3):
      return value
    return 1
  if isinstance(value, str):
    trimmed = value.strip()
    if trimmed.isdigit():
      num = int(trimmed)
      if num in (1, 2, 3):
        return num
      return 1
    normalized = _normalize_role(trimmed)
    if normalized == "repeater":
      return 2
    if normalized == "room":
      return 3
    if normalized == "companion":
      return 1
  return 1


def _parse_updated_since(value: Optional[str]) -> Optional[float]:
  if not value:
    return None
  try:
    text = value.strip()
    if text.endswith("Z"):
      text = text[:-1] + "+00:00"
    return datetime.fromisoformat(text).timestamp()
  except Exception:
    return None


def _node_api_payload(device_id: str, state: "DeviceState") -> Dict[str, Any]:
  last_seen = seen_devices.get(device_id) or state.ts
  last_seen_iso = _iso_from_ts(last_seen)
  role_value = state.role or device_roles.get(device_id)
  device_role = _device_role_code(role_value)
  return {
    "public_key": device_id,
    "name": (state.name or device_names.get(device_id) or ""),
    "device_role": device_role,
    "role": role_value,
    "location": {
      "latitude": float(state.lat),
      "longitude": float(state.lon),
    },
    "lat": state.lat,
    "lon": state.lon,
    "last_seen_ts": last_seen,
    "last_seen": last_seen_iso,
    "timestamp": int(last_seen) if last_seen else None,
    "first_seen": last_seen_iso,
    "battery_voltage": 0,
  }


def _route_payload(route: Dict[str, Any]) -> Dict[str, Any]:
  if not PROD_MODE:
    return route
  return {
    "id": route.get("id"),
    "points": route.get("points"),
    "route_mode": route.get("route_mode"),
    "ts": route.get("ts"),
    "expires_at": route.get("expires_at"),
    "payload_type": route.get("payload_type"),
  }


def _history_edge_payload(edge: Dict[str, Any]) -> Dict[str, Any]:
  return {
    "id": edge.get("id"),
    "a": edge.get("a"),
    "b": edge.get("b"),
    "count": edge.get("count"),
    "last_ts": edge.get("last_ts"),
    "recent": edge.get("recent") if isinstance(edge.get("recent"), list) else [],
  }


def _extract_token(headers: Dict[str, str]) -> Optional[str]:
  auth = headers.get("authorization")
  if auth:
    parts = auth.strip().split()
    if len(parts) == 2 and parts[0].lower() == "bearer":
      return parts[1]
    return auth.strip()
  return headers.get("x-access-token") or headers.get("x-token")


def _require_prod_token(request: Request) -> None:
  if not PROD_MODE:
    return
  if not PROD_TOKEN:
    raise HTTPException(status_code=503, detail="prod_token_not_set")
  token = request.query_params.get("token") or request.query_params.get("access_token")
  if not token:
    token = _extract_token(request.headers)
  if token != PROD_TOKEN:
    raise HTTPException(status_code=401, detail="unauthorized")


def _ws_authorized(ws: WebSocket) -> bool:
  if not PROD_MODE:
    return True
  if not PROD_TOKEN:
    return False
  token = ws.query_params.get("token") or ws.query_params.get("access_token")
  if not token:
    token = _extract_token(ws.headers)
  return token == PROD_TOKEN


def _load_state() -> None:
  try:
    if not os.path.exists(STATE_FILE):
      return
    with open(STATE_FILE, "r", encoding="utf-8") as handle:
      data = json.load(handle)
  except Exception as exc:
    print(f"[state] failed to load {STATE_FILE}: {exc}")
    return

  raw_devices = data.get("devices") or {}
  loaded_devices: Dict[str, DeviceState] = {}
  dropped_ids: Set[str] = set()
  for key, value in raw_devices.items():
    if not isinstance(value, dict):
      continue
    try:
      state = DeviceState(**value)
    except Exception:
      continue
    if _coords_are_zero(state.lat, state.lon) or not _within_map_radius(state.lat, state.lon):
      dropped_ids.add(str(key))
      continue
    loaded_devices[key] = state

  devices.clear()
  devices.update(loaded_devices)
  trails.clear()
  trails.update(data.get("trails") or {})
  seen_devices.clear()
  seen_devices.update(data.get("seen_devices") or {})
  cleaned_trails: Dict[str, list] = {}
  trails_dirty = False
  for device_id, trail in trails.items():
    if not isinstance(trail, list):
      continue
    filtered: list = []
    for entry in trail:
      if not isinstance(entry, (list, tuple)) or len(entry) < 2:
        continue
      lat = entry[0]
      lon = entry[1]
      try:
        lat_val = float(lat)
        lon_val = float(lon)
      except (TypeError, ValueError):
        continue
      if _coords_are_zero(lat_val, lon_val) or not _within_map_radius(lat_val, lon_val):
        trails_dirty = True
        continue
      filtered.append(list(entry))
    if filtered:
      cleaned_trails[device_id] = filtered
    else:
      trails_dirty = True
  trails.clear()
  trails.update(cleaned_trails)
  if TRAIL_LEN <= 0 and trails:
    trails.clear()
    trails_dirty = True
  if dropped_ids:
    for device_id in dropped_ids:
      trails.pop(device_id, None)
      seen_devices.pop(device_id, None)
      trails_dirty = True
  if trails_dirty:
    state.state_dirty = True
  raw_names = data.get("device_names") or {}
  if isinstance(raw_names, dict):
    device_names.clear()
    device_names.update({str(k): str(v) for k, v in raw_names.items() if str(v).strip()})
  else:
    device_names.clear()
  if dropped_ids:
    for device_id in dropped_ids:
      device_names.pop(device_id, None)
  raw_role_sources = data.get("device_role_sources") or {}
  if isinstance(raw_role_sources, dict):
    device_role_sources.clear()
    device_role_sources.update({str(k): str(v) for k, v in raw_role_sources.items() if str(v).strip()})
  else:
    device_role_sources.clear()
  if dropped_ids:
    for device_id in dropped_ids:
      device_role_sources.pop(device_id, None)
  raw_roles = data.get("device_roles") or {}
  device_roles.clear()
  if isinstance(raw_roles, dict):
    for key, value in raw_roles.items():
      if dropped_ids and str(key) in dropped_ids:
        continue
      role_value = str(value).strip() if isinstance(value, str) else ""
      if not role_value:
        continue
      source = device_role_sources.get(str(key))
      if source in ("explicit", "override"):
        device_roles[str(key)] = role_value
  role_overrides = _load_role_overrides()
  if role_overrides:
    for device_id in role_overrides:
      device_role_sources[device_id] = "override"
    device_roles.update(role_overrides)
  if dropped_ids:
    for device_id in dropped_ids:
      device_roles.pop(device_id, None)
  _rebuild_node_hash_map()

  for device_id, state in devices.items():
    if not state.name and device_id in device_names:
      state.name = device_names[device_id]
    role_value = device_roles.get(device_id)
    state.role = role_value if role_value else None


async def _state_saver() -> None:
  while True:
    if state.state_dirty:
      try:
        os.makedirs(STATE_DIR, exist_ok=True)
        tmp_path = f"{STATE_FILE}.tmp"
        with open(tmp_path, "w", encoding="utf-8") as handle:
          json.dump(_serialize_state(), handle)
        os.replace(tmp_path, STATE_FILE)
        state.state_dirty = False
      except Exception as exc:
        print(f"[state] failed to save {STATE_FILE}: {exc}")
    await asyncio.sleep(max(1.0, STATE_SAVE_INTERVAL))


def mqtt_on_connect(client, userdata, flags, reason_code, properties=None):
  topics_str = ", ".join(MQTT_TOPICS)
  print(f"[mqtt] connected reason_code={reason_code} subscribing topics={topics_str}")
  for topic in MQTT_TOPICS:
    client.subscribe(topic, qos=0)


def mqtt_on_disconnect(client, userdata, reason_code, properties=None, *args, **kwargs):
  print(f"[mqtt] disconnected reason_code={reason_code}")


def mqtt_on_message(client, userdata, msg: mqtt.MQTTMessage):
  stats["received_total"] += 1
  stats["last_rx_ts"] = time.time()
  stats["last_rx_topic"] = msg.topic
  topic_counts[msg.topic] = topic_counts.get(msg.topic, 0) + 1
  loop: asyncio.AbstractEventLoop = userdata["loop"]

  dev_guess = _device_id_from_topic(msg.topic)
  if dev_guess and _topic_marks_online(msg.topic):
    now = time.time()
    seen_devices[dev_guess] = now
    mqtt_seen[dev_guess] = now
    if dev_guess in devices:
      last_sent = last_seen_broadcast.get(dev_guess, 0)
      if now - last_sent >= MQTT_SEEN_BROADCAST_MIN_SECONDS:
        last_seen_broadcast[dev_guess] = now
        loop.call_soon_threadsafe(update_queue.put_nowait, {
          "type": "device_seen",
          "device_id": dev_guess,
          "last_seen_ts": now,
          "mqtt_seen_ts": now,
        })

  parsed, debug = _try_parse_payload(msg.topic, msg.payload)
  device_id_hint = parsed.get("device_id") if parsed else None
  if parsed and _coords_are_zero(parsed.get("lat", 0), parsed.get("lon", 0)):
    debug["result"] = "filtered_zero_coords"
    parsed = None
  if parsed and not _within_map_radius(parsed.get("lat"), parsed.get("lon")):
    debug["result"] = "filtered_radius"
    parsed = None
    if device_id_hint:
      loop.call_soon_threadsafe(update_queue.put_nowait, {
        "type": "device_remove",
        "device_id": device_id_hint,
        "reason": "radius",
      })
  origin_id = debug.get("origin_id") or _device_id_from_topic(msg.topic)
  decoder_meta = debug.get("decoder_meta") or {}
  result = debug.get("result") or "unknown"
  device_role = debug.get("device_role")
  role_target_id = origin_id
  if device_role and result.startswith("decoded"):
    role_target_id = None
    loc_meta = decoder_meta.get("location") if isinstance(decoder_meta, dict) else None
    loc_pubkey = loc_meta.get("pubkey") if isinstance(loc_meta, dict) else None
    if isinstance(loc_pubkey, str) and loc_pubkey.strip():
      role_target_id = loc_pubkey
    else:
      decoded_pubkey = debug.get("decoded_pubkey")
      if isinstance(decoded_pubkey, str) and decoded_pubkey.strip():
        role_target_id = decoded_pubkey
  debug_entry = {
    "ts": time.time(),
    "topic": msg.topic,
    "result": debug.get("result"),
    "found_path": debug.get("found_path"),
    "found_hint": debug.get("found_hint"),
    "decoder_meta": decoder_meta,
    "role_target_id": role_target_id,
    "packet_hash": debug.get("packet_hash"),
    "direction": debug.get("direction"),
    "json_keys": debug.get("json_keys"),
    "parse_error": debug.get("parse_error"),
    "origin_id": origin_id,
    "payload_preview": _safe_preview(msg.payload[:DEBUG_PAYLOAD_MAX]),
  }
  debug_last.append(debug_entry)
  if msg.topic.endswith("/status"):
    status_last.append({
      "ts": debug_entry["ts"],
      "topic": msg.topic,
      "device_name": debug.get("device_name"),
      "device_role": debug.get("device_role"),
      "origin_id": origin_id,
      "json_keys": debug_entry.get("json_keys"),
      "payload_preview": debug_entry["payload_preview"],
    })

  result_counts[result] = result_counts.get(result, 0) + 1

  device_name = debug.get("device_name")
  if device_name and origin_id:
    existing_name = device_names.get(origin_id)
    if existing_name != device_name:
      device_names[origin_id] = device_name
      state.state_dirty = True
      device_state = devices.get(origin_id)
      if device_state:
        device_state.name = device_name
        loop: asyncio.AbstractEventLoop = userdata["loop"]
        loop.call_soon_threadsafe(update_queue.put_nowait, {
          "type": "device_name",
          "device_id": origin_id,
        })
  if device_role and role_target_id:
    existing_role = device_roles.get(role_target_id)
    if existing_role != device_role:
      device_roles[role_target_id] = device_role
      device_role_sources[role_target_id] = "explicit"
      state.state_dirty = True
      device_state = devices.get(role_target_id)
      if device_state:
        device_state.role = device_role
        loop: asyncio.AbstractEventLoop = userdata["loop"]
        loop.call_soon_threadsafe(update_queue.put_nowait, {
          "type": "device_role",
          "device_id": role_target_id,
        })

  path_hashes = decoder_meta.get("pathHashes")
  payload_type = decoder_meta.get("payloadType")
  route_type = decoder_meta.get("routeType")
  message_hash = decoder_meta.get("messageHash") or debug.get("packet_hash")
  snr_values = decoder_meta.get("snrValues")
  path_header = decoder_meta.get("path")
  direction = debug.get("direction")
  receiver_id = _device_id_from_topic(msg.topic)
  route_origin_id = None
  loc_meta = decoder_meta.get("location") if isinstance(decoder_meta, dict) else None
  if isinstance(loc_meta, dict):
    decoded_pubkey = loc_meta.get("pubkey")
    if decoded_pubkey:
      route_origin_id = decoded_pubkey
  direction_value = str(direction or "").lower()
  if message_hash:
    cache = message_origins.get(message_hash)
    if not cache:
      cache = {"origin_id": None, "first_rx": None, "receivers": set(), "ts": time.time()}
      message_origins[message_hash] = cache
    cache["ts"] = time.time()
    origin_for_tx = origin_id or receiver_id
    if direction_value == "tx" and origin_for_tx:
      cache["origin_id"] = origin_for_tx
    if direction_value == "rx" and receiver_id:
      cache["receivers"].add(receiver_id)
      if not cache.get("first_rx"):
        cache["first_rx"] = receiver_id
    cached_origin = cache.get("origin_id")
    if not route_origin_id and cached_origin:
      route_origin_id = cached_origin
    if not route_origin_id and direction_value == "rx":
      first_rx = cache.get("first_rx")
      if first_rx and receiver_id and receiver_id != first_rx:
        route_origin_id = first_rx
  if not route_origin_id:
    route_origin_id = origin_id
  loop: asyncio.AbstractEventLoop = userdata["loop"]
  try:
    payload_type = int(payload_type) if payload_type is not None else None
  except (TypeError, ValueError):
    payload_type = None
  try:
    route_type = int(route_type) if route_type is not None else None
  except (TypeError, ValueError):
    route_type = None

  route_hashes = None
  if path_hashes and isinstance(path_hashes, list):
    route_hashes = path_hashes
  elif payload_type not in (8, 9) and isinstance(path_header, list):
    if route_type in (0, 1):
      route_hashes = path_header

  route_emitted = False
  if route_hashes and payload_type in ROUTE_PAYLOAD_TYPES_SET:
    loop.call_soon_threadsafe(update_queue.put_nowait, {
      "type": "route",
      "path_hashes": route_hashes,
      "payload_type": payload_type,
      "message_hash": message_hash,
      "origin_id": route_origin_id,
      "receiver_id": receiver_id,
      "snr_values": snr_values,
      "route_type": route_type,
      "ts": time.time(),
      "topic": msg.topic,
    })
    route_emitted = True
  elif message_hash and route_origin_id and receiver_id:
    if direction_value == "rx" and msg.topic.endswith("/packets"):
      loop.call_soon_threadsafe(update_queue.put_nowait, {
        "type": "route",
        "route_mode": "fanout",
        "route_id": f"{message_hash}-{receiver_id}",
        "origin_id": route_origin_id,
        "receiver_id": receiver_id,
        "message_hash": message_hash,
        "route_type": route_type,
        "payload_type": payload_type,
        "ts": time.time(),
        "topic": msg.topic,
      })
      route_emitted = True

  if (not route_emitted and direction_value == "rx" and msg.topic.endswith("/packets")
      and receiver_id and route_origin_id and receiver_id != route_origin_id
      and payload_type in ROUTE_PAYLOAD_TYPES_SET):
    fallback_id = message_hash or f"{route_origin_id}-{receiver_id}-{int(time.time() * 1000)}"
    loop.call_soon_threadsafe(update_queue.put_nowait, {
      "type": "route",
      "route_mode": "direct",
      "route_id": f"direct-{fallback_id}",
      "origin_id": route_origin_id,
      "receiver_id": receiver_id,
      "message_hash": message_hash,
      "route_type": route_type,
      "payload_type": payload_type,
      "ts": time.time(),
      "topic": msg.topic,
    })

  if not parsed:
    stats["unparsed_total"] += 1
    if DEBUG_PAYLOAD:
      print(f"[mqtt] UNPARSED result={result} topic={msg.topic} preview={debug_entry['payload_preview']!r}")
    return

  parsed["raw_topic"] = msg.topic
  stats["parsed_total"] += 1
  stats["last_parsed_ts"] = time.time()
  stats["last_parsed_topic"] = msg.topic

  if DEBUG_PAYLOAD:
    print(f"[mqtt] PARSED topic={msg.topic} device={parsed['device_id']} lat={parsed['lat']} lon={parsed['lon']}")

  loop.call_soon_threadsafe(update_queue.put_nowait, {"type": "device", "data": parsed})


# =========================
# Broadcaster / Reaper
# =========================
async def broadcaster():
  while True:
    event = await update_queue.get()

    if isinstance(event, dict) and event.get("type") in ("device_name", "device_role"):
      device_id = event.get("device_id")
      device_state = devices.get(device_id)
      if device_state:
        if device_id in device_names:
          device_state.name = device_names[device_id]
        if device_id in device_roles:
          device_state.role = device_roles[device_id]
        payload = {"type": "update", "device": _device_payload(device_id, device_state), "trail": trails.get(device_id, [])}
        dead = []
        for ws in list(clients):
          try:
            await ws.send_text(json.dumps(payload))
          except Exception:
            dead.append(ws)
        for ws in dead:
          clients.discard(ws)
      continue

    if isinstance(event, dict) and event.get("type") == "device_seen":
      device_id = event.get("device_id")
      device_state = devices.get(device_id)
      if device_state:
        seen_ts = event.get("last_seen_ts") or time.time()
        mqtt_ts = event.get("mqtt_seen_ts")
        seen_devices[device_id] = seen_ts
        if mqtt_ts:
          mqtt_seen[device_id] = mqtt_ts
        payload = {
          "type": "device_seen",
          "device_id": device_id,
          "last_seen_ts": seen_ts,
          "mqtt_seen_ts": mqtt_ts,
        }
        dead = []
        for ws in list(clients):
          try:
            await ws.send_text(json.dumps(payload))
          except Exception:
            dead.append(ws)
        for ws in dead:
          clients.discard(ws)
      continue

    if isinstance(event, dict) and event.get("type") == "device_remove":
      device_id = event.get("device_id")
      if device_id and _evict_device(device_id):
        payload = {"type": "stale", "device_ids": [device_id]}
        dead = []
        for ws in list(clients):
          try:
            await ws.send_text(json.dumps(payload))
          except Exception:
            dead.append(ws)
        for ws in dead:
          clients.discard(ws)
      continue

    if isinstance(event, dict) and event.get("type") == "route":
      route_mode = event.get("route_mode")
      points = event.get("points")
      used_hashes: List[str] = []
      point_ids: List[Optional[str]] = []

      if not points:
        path_hashes = event.get("path_hashes") or []
        points, used_hashes, point_ids = _route_points_from_hashes(
          list(path_hashes),
          event.get("origin_id"),
          event.get("receiver_id"),
          event.get("ts") or time.time(),
        )

      if not points and route_mode == "fanout":
        points = _route_points_from_device_ids(event.get("origin_id"), event.get("receiver_id"))
        if points and event.get("origin_id") and event.get("receiver_id") and len(points) == 2:
          point_ids = [event.get("origin_id"), event.get("receiver_id")]

      # Fallback: if path hashes are missing/unknown, draw a direct link when possible.
      if not points:
        points = _route_points_from_device_ids(event.get("origin_id"), event.get("receiver_id"))
        if points:
          route_mode = "direct"
          if event.get("origin_id") and event.get("receiver_id") and len(points) == 2:
            point_ids = [event.get("origin_id"), event.get("receiver_id")]

      if not points:
        continue

      if MAP_RADIUS_KM > 0:
        outside = any(
          not _within_map_radius(point[0], point[1])
          for point in points
          if isinstance(point, (list, tuple)) and len(point) >= 2
        )
        if outside:
          continue

      route_id = event.get("route_id") or event.get("message_hash") or f"{event.get('origin_id', 'route')}-{int(event.get('ts', time.time()) * 1000)}"
      expires_at = (event.get("ts") or time.time()) + ROUTE_TTL_SECONDS
      route = {
        "id": route_id,
        "points": points,
        "hashes": used_hashes,
        "point_ids": point_ids,
        "route_mode": route_mode or ("path" if used_hashes else "direct"),
        "ts": event.get("ts") or time.time(),
        "expires_at": expires_at,
        "origin_id": event.get("origin_id"),
        "receiver_id": event.get("receiver_id"),
        "payload_type": event.get("payload_type"),
        "message_hash": event.get("message_hash"),
        "snr_values": event.get("snr_values"),
        "topic": event.get("topic"),
      }
      _append_heat_points(points, route["ts"], event.get("payload_type"))
      routes[route_id] = route

      history_updates, history_removed = _record_route_history(route)

      payload = {"type": "route", "route": _route_payload(route)}
      dead = []
      for ws in list(clients):
        try:
          await ws.send_text(json.dumps(payload))
        except Exception:
          dead.append(ws)
      for ws in dead:
        clients.discard(ws)
      if history_updates or history_removed:
        history_payload = {}
        if history_updates:
          history_payload["type"] = "history_edges"
          history_payload["edges"] = [_history_edge_payload(edge) for edge in history_updates]
        if history_removed:
          history_payload_remove = {"type": "history_edges_remove", "edge_ids": history_removed}
        else:
          history_payload_remove = None
        dead = []
        for ws in list(clients):
          try:
            if history_updates:
              await ws.send_text(json.dumps(history_payload))
            if history_payload_remove:
              await ws.send_text(json.dumps(history_payload_remove))
          except Exception:
            dead.append(ws)
        for ws in dead:
          clients.discard(ws)
      continue

    upd = event.get("data") if isinstance(event, dict) and event.get("type") == "device" else event

    device_id = upd["device_id"]
    if not _within_map_radius(upd.get("lat"), upd.get("lon")):
      if _evict_device(device_id):
        payload = {"type": "stale", "device_ids": [device_id]}
        dead = []
        for ws in list(clients):
          try:
            await ws.send_text(json.dumps(payload))
          except Exception:
            dead.append(ws)
        for ws in dead:
          clients.discard(ws)
      continue
    is_new_device = device_id not in devices
    device_state = DeviceState(
      device_id=device_id,
      lat=upd["lat"],
      lon=upd["lon"],
      ts=upd.get("ts", time.time()),
      heading=upd.get("heading"),
      speed=upd.get("speed"),
      rssi=upd.get("rssi"),
      snr=upd.get("snr"),
      name=upd.get("name") or device_names.get(device_id),
      role=upd.get("role") or device_roles.get(device_id),
      raw_topic=upd.get("raw_topic"),
    )
    devices[device_id] = device_state
    seen_devices[device_id] = time.time()
    state.state_dirty = True
    if is_new_device:
      _rebuild_node_hash_map()
    if device_state.name:
      device_names[device_id] = device_state.name
    if device_state.role:
      device_roles[device_id] = device_state.role

    if TRAIL_LEN > 0 and not _coords_are_zero(device_state.lat, device_state.lon):
      trails.setdefault(device_id, [])
      trails[device_id].append([device_state.lat, device_state.lon, device_state.ts])
      if len(trails[device_id]) > TRAIL_LEN:
        trails[device_id] = trails[device_id][-TRAIL_LEN:]
    elif device_id in trails:
      trails.pop(device_id, None)

    payload = {"type": "update", "device": _device_payload(device_id, device_state), "trail": trails.get(device_id, [])}

    dead = []
    for ws in list(clients):
      try:
        await ws.send_text(json.dumps(payload))
      except Exception:
        dead.append(ws)
    for ws in dead:
      clients.discard(ws)


async def reaper():
  while True:
    now = time.time()

    if DEVICE_TTL_SECONDS > 0:
      stale = [dev_id for dev_id, st in list(devices.items()) if now - st.ts > DEVICE_TTL_SECONDS]
      if stale:
        payload = {"type": "stale", "device_ids": stale}
        dead = []
        for ws in list(clients):
          try:
            await ws.send_text(json.dumps(payload))
          except Exception:
            dead.append(ws)
        for ws in dead:
          clients.discard(ws)

        for dev_id in stale:
          devices.pop(dev_id, None)
          trails.pop(dev_id, None)
          state.state_dirty = True
        _rebuild_node_hash_map()

    if routes:
      bad_routes = []
      for route_id, route in list(routes.items()):
        points = route.get("points") if isinstance(route, dict) else None
        if not isinstance(points, list):
          continue
        if any(_coords_are_zero(p[0], p[1]) for p in points if isinstance(p, list) and len(p) >= 2):
          bad_routes.append(route_id)
      if bad_routes:
        payload = {"type": "route_remove", "route_ids": bad_routes}
        dead = []
        for ws in list(clients):
          try:
            await ws.send_text(json.dumps(payload))
          except Exception:
            dead.append(ws)
        for ws in dead:
          clients.discard(ws)
        for route_id in bad_routes:
          routes.pop(route_id, None)

    stale_routes = [route_id for route_id, route in list(routes.items()) if now > route.get("expires_at", 0)]
    if stale_routes:
      payload = {"type": "route_remove", "route_ids": stale_routes}
      dead = []
      for ws in list(clients):
        try:
          await ws.send_text(json.dumps(payload))
        except Exception:
          dead.append(ws)
      for ws in dead:
        clients.discard(ws)
      for route_id in stale_routes:
        routes.pop(route_id, None)

    history_updates, history_removed = _prune_route_history()
    if history_updates or history_removed:
      dead = []
      for ws in list(clients):
        try:
          if history_updates:
            await ws.send_text(json.dumps({"type": "history_edges", "edges": history_updates}))
          if history_removed:
            await ws.send_text(json.dumps({"type": "history_edges_remove", "edge_ids": history_removed}))
        except Exception:
          dead.append(ws)
      for ws in dead:
        clients.discard(ws)

    if HEAT_TTL_SECONDS > 0 and heat_events:
      cutoff = now - HEAT_TTL_SECONDS
      heat_events[:] = [entry for entry in heat_events if entry.get("ts", 0) >= cutoff]

    if message_origins:
      for msg_hash, info in list(message_origins.items()):
        if now - info.get("ts", 0) > MESSAGE_ORIGIN_TTL_SECONDS:
          message_origins.pop(msg_hash, None)

    prune_after = max(DEVICE_TTL_SECONDS * 3, 900) if DEVICE_TTL_SECONDS > 0 else 86400
    for dev_id, last in list(seen_devices.items()):
      if now - last > prune_after:
        seen_devices.pop(dev_id, None)

    await asyncio.sleep(5)


# =========================
# FastAPI routes
# =========================
@app.get("/")
def root():
  html_path = os.path.join(APP_DIR, "static", "index.html")
  try:
    with open(html_path, "r", encoding="utf-8") as handle:
      content = handle.read()
  except Exception:
    return FileResponse("static/index.html")

  og_image_tag = ""
  twitter_image_tag = ""
  if SITE_OG_IMAGE:
    safe_image = html.escape(str(SITE_OG_IMAGE), quote=True)
    og_image_tag = f'<meta property="og:image" content="{safe_image}" />'
    twitter_image_tag = f'<meta name="twitter:image" content="{safe_image}" />'

  content = content.replace("{{OG_IMAGE_TAG}}", og_image_tag)
  content = content.replace("{{TWITTER_IMAGE_TAG}}", twitter_image_tag)

  trail_info_suffix = ""
  if TRAIL_LEN > 0:
    trail_info_suffix = f" Trails show last ~{TRAIL_LEN} points."

  replacements = {
    "SITE_TITLE": SITE_TITLE,
    "SITE_DESCRIPTION": SITE_DESCRIPTION,
    "SITE_URL": SITE_URL,
    "SITE_ICON": SITE_ICON,
    "SITE_FEED_NOTE": SITE_FEED_NOTE,
    "DISTANCE_UNITS": DISTANCE_UNITS,
    "NODE_MARKER_RADIUS": NODE_MARKER_RADIUS,
    "HISTORY_LINK_SCALE": HISTORY_LINK_SCALE,
    "TRAIL_INFO_SUFFIX": trail_info_suffix,
    "PROD_MODE": str(PROD_MODE).lower(),
    "PROD_TOKEN": PROD_TOKEN,
    "MAP_START_LAT": MAP_START_LAT,
    "MAP_START_LON": MAP_START_LON,
    "MAP_START_ZOOM": MAP_START_ZOOM,
    "MAP_RADIUS_KM": MAP_RADIUS_KM,
    "MAP_RADIUS_SHOW": str(MAP_RADIUS_SHOW).lower(),
    "MAP_DEFAULT_LAYER": MAP_DEFAULT_LAYER,
    "LOS_ELEVATION_URL": LOS_ELEVATION_URL,
    "LOS_SAMPLE_MIN": LOS_SAMPLE_MIN,
    "LOS_SAMPLE_MAX": LOS_SAMPLE_MAX,
    "LOS_SAMPLE_STEP_METERS": LOS_SAMPLE_STEP_METERS,
    "LOS_PEAKS_MAX": LOS_PEAKS_MAX,
    "MQTT_ONLINE_SECONDS": MQTT_ONLINE_SECONDS,
  }
  for key, value in replacements.items():
    safe_value = html.escape(str(value), quote=True)
    content = content.replace(f"{{{{{key}}}}}", safe_value)

  return HTMLResponse(content)


@app.get("/manifest.webmanifest")
def manifest():
  icons = []
  if SITE_ICON:
    icons = [
      {
        "src": SITE_ICON,
        "sizes": "192x192",
        "type": "image/png",
        "purpose": "any"
      },
      {
        "src": SITE_ICON,
        "sizes": "512x512",
        "type": "image/png",
        "purpose": "any maskable"
      }
    ]
  short_name = SITE_TITLE if len(SITE_TITLE) <= 12 else SITE_TITLE[:12]
  return JSONResponse(
    {
      "name": SITE_TITLE,
      "short_name": short_name,
      "description": SITE_DESCRIPTION,
      "start_url": "/",
      "scope": "/",
      "display": "standalone",
      "display_override": ["standalone", "minimal-ui"],
      "background_color": "#0f172a",
      "theme_color": "#0f172a",
      "icons": icons
    },
    media_type="application/manifest+json",
  )


@app.get("/sw.js")
def service_worker():
  return FileResponse("static/sw.js", media_type="application/javascript")


@app.get("/snapshot")
def snapshot(request: Request):
  _require_prod_token(request)
  return {
    "devices": {k: _device_payload(k, v) for k, v in devices.items()},
    "trails": trails,
    "routes": [_route_payload(r) for r in routes.values()],
    "history_edges": [_history_edge_payload(e) for e in route_history_edges.values()],
    "history_window_seconds": int(max(0, ROUTE_HISTORY_HOURS * 3600)),
    "heat": _serialize_heat_events(),
    "server_time": time.time(),
  }


@app.get("/stats")
def get_stats():
  if PROD_MODE:
    return {
      "stats": {
        "received_total": stats.get("received_total"),
        "parsed_total": stats.get("parsed_total"),
        "unparsed_total": stats.get("unparsed_total"),
        "last_rx_ts": stats.get("last_rx_ts"),
        "last_parsed_ts": stats.get("last_parsed_ts"),
      },
      "result_counts": result_counts,
      "mapped_devices": len(devices),
      "route_count": len(routes),
      "history_edge_count": len(route_history_edges),
      "seen_devices": len(seen_devices),
      "server_time": time.time(),
    }

  top_topics = sorted(topic_counts.items(), key=lambda kv: kv[1], reverse=True)[:20]
  return {
    "stats": stats,
    "result_counts": result_counts,
    "mapped_devices": len(devices),
    "route_count": len(routes),
    "history_edge_count": len(route_history_edges),
    "history_segments": len(route_history_segments),
    "seen_devices": len(seen_devices),
    "seen_recent": sorted(seen_devices.items(), key=lambda kv: kv[1], reverse=True)[:20],
    "top_topics": top_topics,
    "decoder": {
      "decode_with_node": DECODE_WITH_NODE,
      "node_ready": _node_ready_once,
      "node_unavailable": _node_unavailable_once,
    },
    "route_payload_types": sorted(ROUTE_PAYLOAD_TYPES_SET),
    "direct_coords": {
      "mode": DIRECT_COORDS_MODE,
      "topic_regex": DIRECT_COORDS_TOPIC_REGEX,
      "regex_valid": DIRECT_COORDS_TOPIC_RE is not None,
      "allow_zero": DIRECT_COORDS_ALLOW_ZERO,
    },
    "server_time": time.time(),
  }


@app.get("/api/nodes")
def api_nodes(request: Request, updated_since: Optional[str] = None, mode: Optional[str] = None, format: Optional[str] = None):
  _require_prod_token(request)
  cutoff = _parse_updated_since(updated_since)
  mode_value = (mode or "").strip().lower()
  apply_delta = mode_value in ("delta", "updates", "since")
  format_value = (format or "").strip().lower()
  format_flat = format_value in ("flat", "list", "legacy", "v1")
  nodes: List[Dict[str, Any]] = []
  all_nodes: List[Dict[str, Any]] = []
  max_last_seen = 0.0
  for device_id, state in devices.items():
    payload = _node_api_payload(device_id, state)
    last_seen = payload.get("last_seen_ts") or 0
    if float(last_seen) > max_last_seen:
      max_last_seen = float(last_seen)
    all_nodes.append(payload)
    if apply_delta and cutoff is not None and float(last_seen) < cutoff:
      continue
    nodes.append(payload)
  nodes.sort(key=lambda item: item.get("public_key") or "")
  if not apply_delta:
    all_nodes.sort(key=lambda item: item.get("public_key") or "")
    nodes = all_nodes
  payload: Dict[str, Any] = {
    "server_time": time.time(),
    "max_last_seen_ts": max_last_seen or None,
    "updated_since_applied": bool(apply_delta and cutoff is not None),
    "updated_since_ignored": bool(updated_since and not apply_delta),
  }
  if format_flat:
    payload["data"] = nodes
  else:
    payload["data"] = {"nodes": nodes}
  return payload


@app.get("/peers/{device_id}")
def get_peers(device_id: str, request: Request, limit: int = 8):
  _require_prod_token(request)
  if not device_id:
    raise HTTPException(status_code=400, detail="device_id required")
  limit_value = max(1, min(int(limit or 8), 50))
  payload = _peer_stats_for_device(device_id, limit_value)
  state = devices.get(device_id)
  if state and not _coords_are_zero(state.lat, state.lon):
    payload["lat"] = float(state.lat)
    payload["lon"] = float(state.lon)
  payload["name"] = (state.name if state else None) or device_names.get(device_id) or ""
  payload["role"] = (state.role if state else None) or device_roles.get(device_id)
  payload["last_seen_ts"] = seen_devices.get(device_id) or (state.ts if state else None)
  payload["server_time"] = time.time()
  return payload


def _peer_device_payload(peer_id: str, count: int, total: int, last_ts: Optional[float]) -> Dict[str, Any]:
  state = devices.get(peer_id)
  name = None
  role = None
  lat = None
  lon = None
  if state:
    name = state.name or device_names.get(peer_id)
    role = state.role or device_roles.get(peer_id)
    if not _coords_are_zero(state.lat, state.lon):
      lat = float(state.lat)
      lon = float(state.lon)
  if not name:
    name = device_names.get(peer_id)
  percent = (count / total * 100.0) if total > 0 else 0.0
  return {
    "peer_id": peer_id,
    "name": name or "",
    "role": role,
    "lat": lat,
    "lon": lon,
    "count": int(count),
    "percent": round(percent, 1),
    "last_seen_ts": last_ts,
  }


def _peer_is_excluded(peer_id: str) -> bool:
  if not MQTT_ONLINE_FORCE_NAMES_SET:
    return False
  state = devices.get(peer_id)
  name_value = ""
  if state and state.name:
    name_value = state.name
  if not name_value:
    name_value = device_names.get(peer_id) or ""
  if not name_value:
    return False
  return name_value.strip().lower() in MQTT_ONLINE_FORCE_NAMES_SET


def _peer_stats_for_device(device_id: str, limit: int) -> Dict[str, Any]:
  inbound: Dict[str, int] = {}
  outbound: Dict[str, int] = {}
  inbound_last: Dict[str, float] = {}
  outbound_last: Dict[str, float] = {}
  for entry in route_history_segments:
    if not isinstance(entry, dict):
      continue
    a_id = entry.get("a_id")
    b_id = entry.get("b_id")
    if not a_id or not b_id:
      continue
    ts = entry.get("ts") or 0
    if a_id == device_id and b_id != device_id:
      if _peer_is_excluded(b_id):
        continue
      outbound[b_id] = outbound.get(b_id, 0) + 1
      outbound_last[b_id] = max(outbound_last.get(b_id, 0), float(ts))
    if b_id == device_id and a_id != device_id:
      if _peer_is_excluded(a_id):
        continue
      inbound[a_id] = inbound.get(a_id, 0) + 1
      inbound_last[a_id] = max(inbound_last.get(a_id, 0), float(ts))

  inbound_total = sum(inbound.values())
  outbound_total = sum(outbound.values())

  inbound_items = [
    _peer_device_payload(peer_id, count, inbound_total, inbound_last.get(peer_id))
    for peer_id, count in inbound.items()
  ]
  outbound_items = [
    _peer_device_payload(peer_id, count, outbound_total, outbound_last.get(peer_id))
    for peer_id, count in outbound.items()
  ]
  inbound_items.sort(key=lambda item: item.get("count", 0), reverse=True)
  outbound_items.sort(key=lambda item: item.get("count", 0), reverse=True)

  if limit > 0:
    inbound_items = inbound_items[:limit]
    outbound_items = outbound_items[:limit]

  return {
    "device_id": device_id,
    "incoming_total": inbound_total,
    "outgoing_total": outbound_total,
    "incoming": inbound_items,
    "outgoing": outbound_items,
    "window_hours": ROUTE_HISTORY_HOURS,
  }


@app.get("/los")
def line_of_sight(lat1: float, lon1: float, lat2: float, lon2: float, profile: bool = False):
  include_points = bool(profile)
  start = _normalize_lat_lon(lat1, lon1)
  end = _normalize_lat_lon(lat2, lon2)
  if not start or not end:
    return {"ok": False, "error": "invalid_coords"}

  points = _sample_los_points(start[0], start[1], end[0], end[1])
  elevations, error = _fetch_elevations(points)
  if error:
    return {"ok": False, "error": error}

  distance_m = _haversine_m(start[0], start[1], end[0], end[1])
  if distance_m <= 0:
    return {"ok": False, "error": "zero_distance"}

  start_elev = elevations[0]
  end_elev = elevations[-1]
  max_obstruction = _los_max_obstruction(points, elevations, 0, len(points) - 1)
  max_terrain = max(elevations)
  blocked = max_obstruction > 0.0
  suggestion = _find_los_suggestion(points, elevations) if blocked else None
  profile_samples = []
  if distance_m > 0:
    for (lat, lon, t), elev in zip(points, elevations):
      line_elev = start_elev + (end_elev - start_elev) * t
      profile_samples.append([
        round(distance_m * t, 2),
        round(float(elev), 2),
        round(float(line_elev), 2),
      ])
  peaks = _find_los_peaks(points, elevations, distance_m)

  response = {
    "ok": True,
    "blocked": blocked,
    "max_obstruction_m": round(max_obstruction, 2),
    "distance_m": round(distance_m, 2),
    "distance_km": round(distance_m / 1000.0, 3),
    "distance_mi": round(distance_m / 1609.344, 3),
    "samples": len(points),
    "elevation_m": {
      "start": round(start_elev, 2),
      "end": round(end_elev, 2),
      "max_terrain": round(max_terrain, 2),
    },
    "provider": LOS_ELEVATION_URL,
    "note": "Straight-line LOS using SRTM90m. No curvature/refraction.",
    "suggested": suggestion,
    "profile": profile_samples,
    "peaks": peaks,
  }
  if include_points:
    response["profile_points"] = [
      [round(lat, 6), round(lon, 6), round(t, 4), round(float(elev), 2)]
      for (lat, lon, t), elev in zip(points, elevations)
    ]
  return response


@app.get("/coverage")
async def get_coverage():
  if not COVERAGE_API_URL:
    raise HTTPException(status_code=503, detail="coverage_api_not_configured: Set COVERAGE_API_URL in .env (e.g., http://localhost:3000)")
  try:
    url = f"{COVERAGE_API_URL}/get-samples"
    print(f"[coverage] Fetching from {url}")
    async with httpx.AsyncClient(timeout=10.0) as client:
      response = await client.get(url)
      response.raise_for_status()
      data = response.json()
      # /get-samples returns { keys: [...] }, extract the keys array
      samples = data.get("keys", []) if isinstance(data, dict) else (data if isinstance(data, list) else [])
      print(f"[coverage] Received {len(samples) if isinstance(samples, list) else 'non-list'} items from coverage API")
      if isinstance(samples, list) and len(samples) > 0:
        print(f"[coverage] Sample item keys: {list(samples[0].keys()) if samples[0] else 'N/A'}")
      return samples
  except httpx.TimeoutException:
    raise HTTPException(status_code=504, detail="coverage_api_timeout")
  except httpx.HTTPStatusError as e:
    raise HTTPException(status_code=502, detail=f"coverage_api_error: HTTP {e.response.status_code} from {COVERAGE_API_URL}")
  except httpx.HTTPError as e:
    raise HTTPException(status_code=502, detail=f"coverage_api_error: {str(e)}")
  except Exception as e:
    raise HTTPException(status_code=500, detail=f"coverage_fetch_error: {str(e)}")


@app.get("/debug/last")
def debug_last_entries():
  if PROD_MODE:
    raise HTTPException(status_code=404, detail="not_found")
  return {
    "count": len(debug_last),
    "items": list(reversed(list(debug_last))),
    "server_time": time.time(),
  }


@app.get("/debug/status")
def debug_status_entries():
  if PROD_MODE:
    raise HTTPException(status_code=404, detail="not_found")
  return {
    "count": len(status_last),
    "items": list(reversed(list(status_last))),
    "server_time": time.time(),
  }


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
  if not _ws_authorized(ws):
    await ws.accept()
    await ws.close(code=1008)
    return
  await ws.accept()
  clients.add(ws)

  await ws.send_text(json.dumps({
    "type": "snapshot",
    "devices": {k: _device_payload(k, v) for k, v in devices.items()},
    "trails": trails,
    "routes": [_route_payload(r) for r in routes.values()],
    "history_edges": [_history_edge_payload(e) for e in route_history_edges.values()],
    "history_window_seconds": int(max(0, ROUTE_HISTORY_HOURS * 3600)),
    "heat": _serialize_heat_events(),
  }))

  try:
    while True:
      await ws.receive_text()
  except WebSocketDisconnect:
    pass
  except RuntimeError:
    pass
  finally:
    clients.discard(ws)


# =========================
# Startup / Shutdown
# =========================
@app.on_event("startup")
async def startup():
  global mqtt_client

  _load_state()
  _load_route_history()
  _ensure_node_decoder()

  loop = asyncio.get_event_loop()
  transport = "websockets" if MQTT_TRANSPORT == "websockets" else "tcp"

  topics_str = ", ".join(MQTT_TOPICS)
  print(
    f"[mqtt] connecting host={MQTT_HOST} port={MQTT_PORT} tls={MQTT_TLS} transport={transport} ws_path={MQTT_WS_PATH if transport=='websockets' else '-'} topics={topics_str}"
  )

  mqtt_client = mqtt.Client(
    mqtt.CallbackAPIVersion.VERSION2,
    client_id=(MQTT_CLIENT_ID or None),
    userdata={"loop": loop},
    transport=transport,
  )

  if transport == "websockets":
    mqtt_client.ws_set_options(path=MQTT_WS_PATH)

  if MQTT_USERNAME:
    mqtt_client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)

  if MQTT_TLS:
    if MQTT_CA_CERT:
      mqtt_client.tls_set(ca_certs=MQTT_CA_CERT)
    else:
      mqtt_client.tls_set()
    if MQTT_TLS_INSECURE:
      mqtt_client.tls_insecure_set(True)

  mqtt_client.on_connect = mqtt_on_connect
  mqtt_client.on_disconnect = mqtt_on_disconnect
  mqtt_client.on_message = mqtt_on_message

  mqtt_client.reconnect_delay_set(min_delay=1, max_delay=30)
  mqtt_client.connect_async(MQTT_HOST, MQTT_PORT, keepalive=30)
  mqtt_client.loop_start()

  asyncio.create_task(broadcaster())
  asyncio.create_task(reaper())
  asyncio.create_task(_state_saver())
  asyncio.create_task(_route_history_saver())


@app.on_event("shutdown")
async def shutdown():
  global mqtt_client
  if mqtt_client is not None:
    try:
      mqtt_client.loop_stop()
      mqtt_client.disconnect()
    except Exception:
      pass
    mqtt_client = None
