import asyncio
import json
import os
import html
import time
import subprocess
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from dataclasses import asdict
from typing import Any, Dict, Optional, Set, List, Tuple

import httpx
import paho.mqtt.client as mqtt
from fastapi import (
  FastAPI,
  WebSocket,
  WebSocketDisconnect,
  Request,
  HTTPException,
  Query,
)
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from urllib.parse import urlencode
from io import BytesIO
from PIL import Image, ImageDraw
import math

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
from weather import create_weather_router
from turnstile import TurnstileVerifier
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
  DEVICE_COORDS_FILE,
  NEIGHBOR_OVERRIDES_FILE,
  STATE_SAVE_INTERVAL,
  DEVICE_TTL_WINDOW_SECONDS,
  PATH_TTL_SECONDS,
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
  MQTT_ONLINE_STATUS_TTL_SECONDS,
  MQTT_ONLINE_INTERNAL_TTL_SECONDS,
  MQTT_ACTIVITY_PACKETS_TTL_SECONDS,
  MQTT_SEEN_BROADCAST_MIN_SECONDS,
  MQTT_ONLINE_FORCE_NAMES_SET,
  MQTT_STATUS_OFFLINE_VALUES_SET,
  DEBUG_PAYLOAD,
  DEBUG_PAYLOAD_MAX,
  TURNSTILE_ENABLED,
  TURNSTILE_SITE_KEY,
  TURNSTILE_SECRET_KEY,
  TURNSTILE_API_URL,
  TURNSTILE_TOKEN_TTL_SECONDS,
  TURNSTILE_BOT_BYPASS,
  TURNSTILE_BOT_ALLOWLIST,
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
  CUSTOM_LINK_URL,
  GIT_CHECK_ENABLED,
  GIT_CHECK_FETCH,
  GIT_CHECK_PATH,
  GIT_CHECK_INTERVAL_SECONDS,
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
  LOS_ELEVATION_PROXY_URL,
  LOS_SAMPLE_MIN,
  LOS_SAMPLE_MAX,
  LOS_SAMPLE_STEP_METERS,
  ELEVATION_CACHE_TTL,
  LOS_PEAKS_MAX,
  COVERAGE_API_URL,
  WEATHER_RADAR_ENABLED,
  WEATHER_RADAR_COUNTRY_BOUNDS_ENABLED,
  WEATHER_RADAR_COUNTRY_LOOKUP_URL,
  WEATHER_WIND_ENABLED,
  WEATHER_WIND_API_URL,
  WEATHER_WIND_GRID_SIZE,
  WEATHER_WIND_REFRESH_SECONDS,
  APP_DIR,
  NODE_SCRIPT_PATH,
)
from state import (
  DeviceState,
  stats,
  result_counts,
  seen_devices,
  mqtt_seen,
  mqtt_online_source,
  mqtt_status_seen,
  mqtt_status_values,
  mqtt_internal_seen,
  mqtt_packets_seen,
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
  device_coords,
  neighbor_edges,
  first_seen_devices,
  last_seen_in_advert,
)

# =========================
# App / State
# =========================
mqtt_client: Optional[mqtt.Client] = None
background_tasks: Set[asyncio.Task[Any]] = set()
clients: Set[WebSocket] = set()
update_queue: asyncio.Queue[Dict[str, Any]] = asyncio.Queue()
git_update_info = {
  "available": False,
  "local": None,
  "remote": None,
  "local_short": None,
  "remote_short": None,
  "error": None,
}
mqtt_presence_last_summary: Dict[str, int] = {}


@asynccontextmanager
async def _lifespan(_app: FastAPI):
  global mqtt_client

  _load_state()
  _load_route_history()
  _load_neighbor_overrides()
  _ensure_node_decoder()
  _check_git_updates()

  loop = asyncio.get_running_loop()
  transport = "websockets" if MQTT_TRANSPORT == "websockets" else "tcp"

  topics_str = ", ".join(MQTT_TOPICS)
  print(
    f"[mqtt] connecting host={MQTT_HOST} port={MQTT_PORT} tls={MQTT_TLS} transport={transport} ws_path={MQTT_WS_PATH if transport == 'websockets' else '-'} topics={topics_str}"
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

  background_tasks.clear()
  for coro in (
    broadcaster(),
    reaper(),
    _state_saver(),
    _route_history_saver(),
    _git_check_loop(),
  ):
    background_tasks.add(asyncio.create_task(coro))

  try:
    yield
  finally:
    for task in list(background_tasks):
      task.cancel()
    if background_tasks:
      await asyncio.gather(*background_tasks, return_exceptions=True)
    background_tasks.clear()

    if mqtt_client is not None:
      try:
        mqtt_client.loop_stop()
        mqtt_client.disconnect()
      except Exception:
        pass
      mqtt_client = None


app = FastAPI(lifespan=_lifespan)
app.mount("/static", StaticFiles(directory="static"), name="static")
# Initialize Turnstile verifier if enabled
turnstile_verifier: Optional[TurnstileVerifier] = None
if TURNSTILE_ENABLED and TURNSTILE_SECRET_KEY:
  turnstile_verifier = TurnstileVerifier(
    secret_key=TURNSTILE_SECRET_KEY,
    api_url=TURNSTILE_API_URL,
    token_ttl_seconds=TURNSTILE_TOKEN_TTL_SECONDS,
  )
  print(f"[startup] Turnstile authentication enabled")
else:
  print(f"[startup] Turnstile authentication disabled")
def _compute_asset_version() -> str:
  paths = [
    os.path.join(APP_DIR, "static", "app.js"),
    os.path.join(APP_DIR, "static", "styles.css"),
    os.path.join(APP_DIR, "static", "sw.js"),
  ]
  mtimes = []
  for path in paths:
    try:
      mtimes.append(int(os.path.getmtime(path)))
    except Exception:
      continue
  return str(max(mtimes)) if mtimes else "1"


ASSET_VERSION = _compute_asset_version()


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


def _load_coord_overrides() -> Dict[str, Dict[str, float]]:
  if not DEVICE_COORDS_FILE or not os.path.exists(DEVICE_COORDS_FILE):
    return {}
  try:
    with open(DEVICE_COORDS_FILE, "r", encoding="utf-8") as handle:
      data = json.load(handle)
  except Exception:
    return {}
  if not isinstance(data, dict):
    return {}
  coords: Dict[str, Dict[str, float]] = {}
  for key, value in data.items():
    if not isinstance(key, str) or not isinstance(value, dict):
      continue
    lat = value.get("lat")
    lon = value.get("lon")
    if isinstance(lat, (int, float)) and isinstance(lon, (int, float)):
      coords[key.strip()] = {"lat": float(lat), "lon": float(lon)}
  return coords


def _neighbor_override_pairs(data: Any) -> List[Tuple[str, str]]:
  pairs: List[Tuple[str, str]] = []
  if isinstance(data, dict):
    for src, targets in data.items():
      if not isinstance(src, str):
        continue
      src_id = src.strip()
      if isinstance(targets, list):
        for dst in targets:
          if not isinstance(dst, str):
            continue
          dst_id = dst.strip()
          if src_id and dst_id and src_id != dst_id:
            pairs.append((src_id, dst_id))
      elif isinstance(targets, str):
        dst_id = targets.strip()
        if src_id and dst_id and src_id != dst_id:
          pairs.append((src_id, dst_id))
  elif isinstance(data, list):
    for item in data:
      if (
        isinstance(item, (list, tuple)) and len(item) >= 2 and
        isinstance(item[0], str) and isinstance(item[1], str)
      ):
        src_id = item[0].strip()
        dst_id = item[1].strip()
      elif isinstance(item, dict):
        src = item.get("from") or item.get("src") or item.get("a")
        dst = item.get("to") or item.get("dst") or item.get("b")
        if not isinstance(src, str) or not isinstance(dst, str):
          continue
        src_id = src.strip()
        dst_id = dst.strip()
      else:
        continue
      if src_id and dst_id and src_id != dst_id:
        pairs.append((src_id, dst_id))
  return pairs


def _load_neighbor_overrides() -> None:
  if not NEIGHBOR_OVERRIDES_FILE or not os.path.exists(NEIGHBOR_OVERRIDES_FILE):
    return
  try:
    with open(NEIGHBOR_OVERRIDES_FILE, "r", encoding="utf-8") as handle:
      data = json.load(handle)
  except Exception as exc:
    print(f"[neighbors] failed to load {NEIGHBOR_OVERRIDES_FILE}: {exc}")
    return
  now = time.time()
  added = 0
  for src_id, dst_id in _neighbor_override_pairs(data):
    _touch_neighbor(src_id, dst_id, now, manual=True)
    _touch_neighbor(dst_id, src_id, now, manual=True)
    added += 1
  if added:
    print(
      f"[neighbors] loaded {added} override pairs from {NEIGHBOR_OVERRIDES_FILE}"
    )


def _touch_neighbor(
  src_id: str,
  dst_id: str,
  ts: float,
  manual: bool = False,
) -> None:
  if not src_id or not dst_id or src_id == dst_id:
    return
  neighbors = neighbor_edges.setdefault(src_id, {})
  entry = neighbors.get(dst_id)
  if entry is None:
    entry = {"count": 0, "last_seen": 0.0, "manual": False}
    neighbors[dst_id] = entry
  if manual:
    entry["manual"] = True
  else:
    entry["count"] = int(entry.get("count", 0)) + 1
  entry["last_seen"] = max(float(entry.get("last_seen", 0.0)), float(ts))


def _record_neighbors(point_ids: List[Optional[str]], ts: float) -> None:
  if not point_ids or len(point_ids) < 2:
    return
  for idx in range(len(point_ids) - 1):
    src_id = point_ids[idx]
    dst_id = point_ids[idx + 1]
    if not src_id or not dst_id or src_id == dst_id:
      continue
    _touch_neighbor(src_id, dst_id, ts, manual=False)
    _touch_neighbor(dst_id, src_id, ts, manual=False)


def _update_path_timestamps(point_ids: List[Optional[str]], ts: float) -> None:
  """Update last_seen_in_path for all devices in a path."""
  if not point_ids:
    return
  for device_id in point_ids:
    if device_id:
      state.last_seen_in_path[device_id] = max(
        state.last_seen_in_path.get(device_id, 0.0), float(ts)
      )


def _prune_neighbors(now: float) -> None:
  ttl_seconds = PATH_TTL_SECONDS if PATH_TTL_SECONDS > 0 else DEVICE_TTL_WINDOW_SECONDS
  if ttl_seconds <= 0 or not neighbor_edges:
    return
  cutoff = now - ttl_seconds
  for src_id, edges in list(neighbor_edges.items()):
    for dst_id, entry in list(edges.items()):
      if entry.get("manual"):
        continue
      if entry.get("last_seen", 0.0) < cutoff:
        edges.pop(dst_id, None)
    if not edges:
      neighbor_edges.pop(src_id, None)


def _serialize_state() -> Dict[str, Any]:
  return {
    "version": 1,
    "saved_at": time.time(),
    "devices": {
      k: asdict(v)
      for k, v in devices.items()
    },
    "trails": trails,
    "seen_devices": seen_devices,
    "device_names": device_names,
    "device_roles": device_roles,
    "device_role_sources": device_role_sources,
    "last_seen_in_path": state.last_seen_in_path,
    "first_seen_devices": first_seen_devices,
    "last_seen_in_advert": last_seen_in_advert,
  }


def _check_git_updates() -> None:
  if not GIT_CHECK_ENABLED:
    return

  if not GIT_CHECK_PATH or not os.path.isdir(GIT_CHECK_PATH):
    git_update_info["error"] = "git_path_missing"
    return

  def _run_git(args: List[str]) -> str:
    result = subprocess.run(
      args,
      check=True,
      stdout=subprocess.PIPE,
      stderr=subprocess.PIPE,
      text=True,
    )
    return result.stdout.strip()

  try:
    subprocess.run(
      ["git", "config", "--global", "--add", "safe.directory", GIT_CHECK_PATH],
      check=False,
      stdout=subprocess.DEVNULL,
      stderr=subprocess.DEVNULL,
    )
    inside = _run_git(
      ["git", "-C", GIT_CHECK_PATH, "rev-parse", "--is-inside-work-tree"]
    )
    if inside.lower() != "true":
      git_update_info["error"] = "not_git_repo"
      return
  except Exception:
    git_update_info["error"] = "git_unavailable"
    return

  try:
    if GIT_CHECK_FETCH:
      subprocess.run(
        ["git", "-C", GIT_CHECK_PATH, "fetch", "--quiet", "--prune"],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
      )

    local_sha = _run_git(["git", "-C", GIT_CHECK_PATH, "rev-parse", "HEAD"])
    remote_sha = _run_git(["git", "-C", GIT_CHECK_PATH, "rev-parse", "@{u}"])
    git_update_info["local"] = local_sha
    git_update_info["remote"] = remote_sha
    git_update_info["local_short"] = local_sha[:7]
    git_update_info["remote_short"] = remote_sha[:7]
    git_update_info["available"] = local_sha != remote_sha
    if git_update_info["available"]:
      print(
        f"[update] available {git_update_info['local_short']} -> {git_update_info['remote_short']}"
      )
  except Exception:
    git_update_info["error"] = "git_compare_failed"


async def _git_check_loop() -> None:
  if not GIT_CHECK_ENABLED:
    return
  if GIT_CHECK_INTERVAL_SECONDS <= 0:
    return
  while True:
    await asyncio.sleep(GIT_CHECK_INTERVAL_SECONDS)
    _check_git_updates()


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
  mqtt_source = mqtt_online_source.get(device_id)
  if mqtt_source:
    payload["mqtt_online_source"] = mqtt_source
  mqtt_status_ts = mqtt_status_seen.get(device_id)
  if mqtt_status_ts:
    payload["mqtt_status_ts"] = mqtt_status_ts
  mqtt_status_value = mqtt_status_values.get(device_id)
  if mqtt_status_value:
    payload["mqtt_status_value"] = mqtt_status_value
  mqtt_internal_ts = mqtt_internal_seen.get(device_id)
  if mqtt_internal_ts:
    payload["mqtt_internal_ts"] = mqtt_internal_ts
  mqtt_packets_ts = mqtt_packets_seen.get(device_id)
  if mqtt_packets_ts:
    payload["mqtt_packets_ts"] = mqtt_packets_ts
  if MQTT_ONLINE_FORCE_NAMES_SET:
    name_value = (state.name or device_names.get(device_id) or
                  "").strip().lower()
    if name_value and name_value in MQTT_ONLINE_FORCE_NAMES_SET:
      payload["mqtt_forced"] = True
  if PROD_MODE:
    payload.pop("raw_topic", None)
  return payload


def _iso_from_ts(ts: Optional[float]) -> Optional[str]:
  if ts is None:
    return None
  try:
    return datetime.fromtimestamp(float(ts), tz=timezone.utc
                                 ).strftime("%Y-%m-%dT%H:%M:%SZ")
  except Exception:
    return None


def _parse_meshcore_topic(
  topic: str
) -> Tuple[Optional[str], Optional[str], Optional[str]]:
  parts = topic.split("/")
  if len(parts) < 4 or parts[0] != "meshcore":
    return (None, None, None)
  iata = parts[1].strip() or None
  node_id = parts[2].strip() or None
  kind = parts[3].strip().lower() or None
  return (iata, node_id, kind)


def _parse_json_dict(payload_bytes: bytes) -> Optional[Dict[str, Any]]:
  try:
    obj = json.loads(payload_bytes.decode("utf-8", errors="strict"))
  except Exception:
    return None
  if isinstance(obj, dict):
    return obj
  return None


def _extract_status_value(obj: Optional[Dict[str, Any]]) -> Optional[str]:
  if not isinstance(obj, dict):
    return None
  for key in (
    "status",
    "state",
    "mqtt_status",
    "mqttStatus",
    "connection",
    "connection_state",
  ):
    value = obj.get(key)
    if isinstance(value, str) and value.strip():
      return value.strip().lower()
  return None


def _select_mqtt_online_source(
  device_id: str, now: float
) -> Tuple[Optional[str], Optional[float]]:
  status_ts = mqtt_status_seen.get(device_id)
  internal_ts = mqtt_internal_seen.get(device_id)
  status_recent = (
    bool(status_ts) and MQTT_ONLINE_STATUS_TTL_SECONDS > 0 and
    (now - status_ts <= MQTT_ONLINE_STATUS_TTL_SECONDS)
  )
  internal_recent = (
    bool(internal_ts) and MQTT_ONLINE_INTERNAL_TTL_SECONDS > 0 and
    (now - internal_ts <= MQTT_ONLINE_INTERNAL_TTL_SECONDS)
  )

  status_value = (mqtt_status_values.get(device_id) or "").strip().lower()
  if status_recent and status_value in MQTT_STATUS_OFFLINE_VALUES_SET:
    return (None, None)
  if internal_recent:
    return ("internal", internal_ts)
  if status_recent:
    return ("status", status_ts)
  return (None, None)


def _mqtt_presence_payload(
  device_id: str,
  last_seen_ts: Optional[float] = None,
  now: Optional[float] = None,
) -> Dict[str, Any]:
  now = now or time.time()
  return {
    "type": "device_seen",
    "device_id": device_id,
    "last_seen_ts": last_seen_ts,
    "mqtt_seen_ts": mqtt_seen.get(device_id),
    "mqtt_online_source": mqtt_online_source.get(device_id),
    "mqtt_status_ts": mqtt_status_seen.get(device_id),
    "mqtt_status_value": mqtt_status_values.get(device_id),
    "mqtt_internal_ts": mqtt_internal_seen.get(device_id),
    "mqtt_packets_ts": mqtt_packets_seen.get(device_id),
    "mqtt_presence": _mqtt_presence_summary(now),
  }


def _is_packets_active(ts: Optional[float], now: float) -> bool:
  if not ts or MQTT_ACTIVITY_PACKETS_TTL_SECONDS <= 0:
    return False
  return (now - ts) <= MQTT_ACTIVITY_PACKETS_TTL_SECONDS


def _refresh_mqtt_presence(now: Optional[float] = None) -> None:
  now = now or time.time()
  candidate_ids = (
    set(mqtt_seen.keys()) |
    set(mqtt_online_source.keys()) |
    set(mqtt_status_seen.keys()) |
    set(mqtt_internal_seen.keys())
  )
  for device_id in list(candidate_ids):
    source, source_ts = _select_mqtt_online_source(device_id, now)
    if source and source_ts:
      mqtt_seen[device_id] = source_ts
      mqtt_online_source[device_id] = source
      continue
    mqtt_seen.pop(device_id, None)
    mqtt_online_source.pop(device_id, None)


def _mqtt_presence_summary(now: Optional[float] = None) -> Dict[str, int]:
  now = now or time.time()
  _refresh_mqtt_presence(now)
  connected_total = len(mqtt_seen)
  connected_on_map = sum(1 for device_id in mqtt_seen if device_id in devices)
  feeding_total = sum(
    1 for ts in mqtt_packets_seen.values() if _is_packets_active(ts, now)
  )
  feeding_on_map = sum(
    1
    for device_id, ts in mqtt_packets_seen.items()
    if device_id in devices and _is_packets_active(ts, now)
  )
  return {
    "connected_total": connected_total,
    "connected_on_map": connected_on_map,
    "connected_off_map": max(0, connected_total - connected_on_map),
    "feeding_total": feeding_total,
    "feeding_on_map": feeding_on_map,
    "feeding_off_map": max(0, feeding_total - feeding_on_map),
  }


def _record_mqtt_presence(
  topic: str, payload_bytes: bytes, now: float
) -> Optional[Dict[str, Any]]:
  _, device_id, topic_kind = _parse_meshcore_topic(topic)
  if not device_id or topic_kind not in ("status", "internal", "packets"):
    return None

  was_online = device_id in mqtt_seen

  if topic_kind == "status":
    mqtt_status_seen[device_id] = now
    status_value = _extract_status_value(_parse_json_dict(payload_bytes))
    if status_value:
      mqtt_status_values[device_id] = status_value
  elif topic_kind == "internal":
    mqtt_internal_seen[device_id] = now
  elif topic_kind == "packets":
    mqtt_packets_seen[device_id] = now

  source, source_ts = _select_mqtt_online_source(device_id, now)
  if source and source_ts:
    mqtt_seen[device_id] = source_ts
    mqtt_online_source[device_id] = source
    seen_devices[device_id] = now
  else:
    mqtt_seen.pop(device_id, None)
    mqtt_online_source.pop(device_id, None)

  event = _mqtt_presence_payload(
    device_id, seen_devices.get(device_id) if source else None, now=now
  )
  event["topic_kind"] = topic_kind
  if not was_online and source:
    event["presence_transition"] = "online"
  elif was_online and not source:
    event["presence_transition"] = "offline"
  else:
    event["presence_transition"] = "stable"
  return event


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
  state.last_seen_in_path.pop(device_id, None)
  first_seen_devices.pop(device_id, None)
  last_seen_in_advert.pop(device_id, None)
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
    "hashes": route.get("hashes"),
    "point_ids": route.get("point_ids"),
    "route_mode": route.get("route_mode"),
    "ts": route.get("ts"),
    "expires_at": route.get("expires_at"),
    "origin_id": route.get("origin_id"),
    "receiver_id": route.get("receiver_id"),
    "payload_type": route.get("payload_type"),
  }


def _history_edge_payload(edge: Dict[str, Any]) -> Dict[str, Any]:
  return {
    "id":
      edge.get("id"),
    "a":
      edge.get("a"),
    "b":
      edge.get("b"),
    "count":
      edge.get("count"),
    "last_ts":
      edge.get("last_ts"),
    "recent":
      edge.get("recent") if isinstance(edge.get("recent"), list) else [],
  }


def _extract_token(headers: Dict[str, str]) -> Optional[str]:
  auth = headers.get("authorization")
  if auth:
    parts = auth.strip().split()
    if len(parts) == 2 and parts[0].lower() == "bearer":
      return parts[1]
    return auth.strip()
  return headers.get("x-access-token") or headers.get("x-token")


def _extract_cookie_token(headers: Dict[str, str], key: str) -> Optional[str]:
  cookie = headers.get("cookie")
  if not cookie:
    return None
  for part in cookie.split(";"):
    part = part.strip()
    if not part:
      continue
    if part.startswith(f"{key}="):
      return part[len(key) + 1 :]
  return None


def _require_prod_token(request: Request) -> None:
  if not PROD_MODE:
    return
  if not PROD_TOKEN:
    raise HTTPException(status_code=503, detail="prod_token_not_set")
  token = request.query_params.get("token"
                                  ) or request.query_params.get("access_token")
  if not token:
    token = _extract_token(request.headers)
  if token != PROD_TOKEN:
    raise HTTPException(status_code=401, detail="unauthorized")


app.include_router(create_weather_router(_require_prod_token))


def _ws_authorized(ws: WebSocket) -> bool:
  if TURNSTILE_ENABLED and turnstile_verifier:
    auth_token = _extract_cookie_token(ws.headers, "meshmap_auth") or \
                 ws.query_params.get("auth") or \
                 _extract_token(ws.headers)
    if auth_token and turnstile_verifier.verify_auth_token(auth_token):
      return True
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
      loaded_state = DeviceState(**value)
    except Exception:
      continue
    if _coords_are_zero(loaded_state.lat, loaded_state.lon
                       ) or not _within_map_radius(loaded_state.lat, loaded_state.lon):
      dropped_ids.add(str(key))
      continue
    loaded_devices[key] = loaded_state

  devices.clear()
  devices.update(loaded_devices)
  trails.clear()
  trails.update(data.get("trails") or {})
  seen_devices.clear()
  seen_devices.update(data.get("seen_devices") or {})
  first_seen_devices.clear()
  raw_first_seen = data.get("first_seen_devices") or {}
  if isinstance(raw_first_seen, dict):
    for key, value in raw_first_seen.items():
      try:
        first_seen_devices[str(key)] = float(value)
      except (TypeError, ValueError):
        continue
  else:
    raw_first_seen = {}
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
      if _coords_are_zero(lat_val,
                          lon_val) or not _within_map_radius(lat_val, lon_val):
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
    device_names.update(
      {
        str(k): str(v)
        for k, v in raw_names.items() if str(v).strip()
      }
    )
  else:
    device_names.clear()
  if dropped_ids:
    for device_id in dropped_ids:
      device_names.pop(device_id, None)
  raw_role_sources = data.get("device_role_sources") or {}
  if isinstance(raw_role_sources, dict):
    device_role_sources.clear()
    device_role_sources.update(
      {
        str(k): str(v)
        for k, v in raw_role_sources.items() if str(v).strip()
      }
    )
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
  raw_path_timestamps = data.get("last_seen_in_path") or {}
  state.last_seen_in_path.clear()
  if isinstance(raw_path_timestamps, dict):
    for key, value in raw_path_timestamps.items():
      if dropped_ids and str(key) in dropped_ids:
        continue
      try:
        state.last_seen_in_path[str(key)] = float(value)
      except (TypeError, ValueError):
        continue
  raw_advert_seen = data.get("last_seen_in_advert") or {}
  last_seen_in_advert.clear()
  if isinstance(raw_advert_seen, dict):
    for key, value in raw_advert_seen.items():
      if dropped_ids and str(key) in dropped_ids:
        continue
      try:
        last_seen_in_advert[str(key)] = float(value)
      except (TypeError, ValueError):
        continue
  # If first_seen data is missing, fall back to loaded last_seen values.
  if not raw_first_seen:
    for device_id, seen_ts in seen_devices.items():
      try:
        first_seen_devices[device_id] = float(seen_ts)
      except (TypeError, ValueError):
        continue
  # Load and apply coordinate overrides
  coord_overrides = _load_coord_overrides()
  if coord_overrides:
    device_coords.clear()
    device_coords.update(coord_overrides)
  if dropped_ids:
    for device_id in dropped_ids:
      device_coords.pop(device_id, None)
      first_seen_devices.pop(device_id, None)
      last_seen_in_advert.pop(device_id, None)
  _rebuild_node_hash_map()

  for device_id, dev_state in devices.items():
    if not dev_state.name and device_id in device_names:
      dev_state.name = device_names[device_id]
    role_value = device_roles.get(device_id)
    dev_state.role = role_value if role_value else None
    # Apply coordinate overrides to loaded devices
    coord_override = device_coords.get(device_id)
    if coord_override:
      dev_state.lat = coord_override["lat"]
      dev_state.lon = coord_override["lon"]


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
  print(
    f"[mqtt] connected reason_code={reason_code} subscribing topics={topics_str}"
  )
  for topic in MQTT_TOPICS:
    client.subscribe(topic, qos=0)


def mqtt_on_disconnect(
  client, userdata, reason_code, properties=None, *args, **kwargs
):
  print(f"[mqtt] disconnected reason_code={reason_code}")


def mqtt_on_message(client, userdata, msg: mqtt.MQTTMessage):
  stats["received_total"] += 1
  stats["last_rx_ts"] = time.time()
  stats["last_rx_topic"] = msg.topic
  topic_counts[msg.topic] = topic_counts.get(msg.topic, 0) + 1
  loop: asyncio.AbstractEventLoop = userdata["loop"]

  now = time.time()
  mqtt_presence_event = _record_mqtt_presence(msg.topic, msg.payload, now)
  if mqtt_presence_event:
    device_id = mqtt_presence_event["device_id"]
    should_broadcast = False
    transition = mqtt_presence_event.get("presence_transition")
    if transition in ("online", "offline"):
      should_broadcast = True
    elif mqtt_presence_event.get("mqtt_seen_ts") and device_id in devices:
      last_sent = last_seen_broadcast.get(device_id, 0)
      if now - last_sent >= MQTT_SEEN_BROADCAST_MIN_SECONDS:
        should_broadcast = True
    if should_broadcast:
      last_seen_broadcast[device_id] = now
      loop.call_soon_threadsafe(update_queue.put_nowait, mqtt_presence_event)

  parsed, debug = _try_parse_payload(msg.topic, msg.payload)
  device_id_hint = parsed.get("device_id") if parsed else None
  # Also try to get device_id from topic if parsing failed or no device_id in parsed data
  topic_device_id = _device_id_from_topic(msg.topic)

  # Priority: decoded_pubkey (origin/repeater that sent packet) > parsed device_id > topic device_id (receiver)
  decoded_pubkey = debug.get("decoded_pubkey")
  if isinstance(decoded_pubkey, str) and decoded_pubkey.strip():
    decoded_pubkey = decoded_pubkey.strip()
  else:
    decoded_pubkey = None

  # Check if device has coordinate override - prioritize decoded packet public key (origin)
  coord_override = None
  matched_device_id = None

  # Try 1: decoded_pubkey (origin/repeater that sent the packet) - this is what we want!
  if decoded_pubkey and decoded_pubkey in device_coords:
    coord_override = device_coords[decoded_pubkey]
    matched_device_id = decoded_pubkey
  # Try 2: device_id_hint from parsed data (should also be decoded_pubkey if available)
  elif device_id_hint and device_id_hint in device_coords:
    coord_override = device_coords[device_id_hint]
    matched_device_id = device_id_hint
  # Try 3: Check if decoded_pubkey matches any override via substring (for partial matches)
  elif decoded_pubkey:
    for override_id in device_coords.keys():
      if override_id in decoded_pubkey or decoded_pubkey in override_id:
        coord_override = device_coords[override_id]
        matched_device_id = override_id
        break
  # Try 4: topic_device_id (receiver/observer) - only as fallback
  if not coord_override and topic_device_id and topic_device_id in device_coords:
    coord_override = device_coords[topic_device_id]
    matched_device_id = topic_device_id
  # Try 5: Check all parts of the topic path (receiver/observer)
  if not coord_override:
    topic_parts = msg.topic.split("/")
    for part in topic_parts:
      if part and len(part) > 10 and part in device_coords:  # Only check parts that look like device IDs (long hex strings)
        coord_override = device_coords[part]
        matched_device_id = part
        break
    # Try 6: Check if any device_id in override file is a substring of any topic part (for partial matches)
    if not coord_override:
      for part in topic_parts:
        if part and len(part) > 10:
          # Check if any override key is contained in this topic part or vice versa
          for override_id in device_coords.keys():
            if override_id in part or part in override_id:
              coord_override = device_coords[override_id]
              matched_device_id = override_id
              break
          if coord_override:
            break

  has_coord_override = coord_override is not None
  # Initialize check_lat and check_lon - will be set from override or parsed data
  check_lat = None
  check_lon = None

  if has_coord_override and matched_device_id:
    # Use override coordinates for filtering checks and inject into parsed data
    check_lat = coord_override["lat"]
    check_lon = coord_override["lon"]
    # Normalize timestamp: if it's too far in the future (> 1 hour), use current time
    now_ts = time.time()
    parsed_ts = parsed.get("ts") if parsed else None
    if parsed_ts and parsed_ts > now_ts + 3600:  # More than 1 hour in future
      parsed_ts = now_ts
      if DEBUG_PAYLOAD:
        print(f"[mqtt] Normalized future timestamp: device={matched_device_id} future_ts={parsed.get('ts')} -> now={now_ts}")
    # If parsing failed or has no location, create/update parsed data with override coords
    # Use decoded_pubkey as device_id if available (origin), otherwise use matched_device_id
    target_device_id = decoded_pubkey or matched_device_id
    if not parsed:
      parsed = {
        "device_id": target_device_id,
        "lat": coord_override["lat"],
        "lon": coord_override["lon"],
        "ts": now_ts,
      }
      device_id_hint = target_device_id
      debug["result"] = "coord_override_created"
      if DEBUG_PAYLOAD:
        print(f"[mqtt] Created parsed data from coord override: device_id={target_device_id} (matched_override={matched_device_id}) lat={coord_override['lat']} lon={coord_override['lon']}")
    elif parsed:
      # If parsing succeeded but no location, inject override coordinates
      if not parsed.get("lat") or not parsed.get("lon") or _coords_are_zero(parsed.get("lat", 0), parsed.get("lon", 0)):
        parsed["lat"] = coord_override["lat"]
        parsed["lon"] = coord_override["lon"]
        # Ensure device_id is set to the decoded_pubkey (origin) if available
        if decoded_pubkey:
          parsed["device_id"] = decoded_pubkey
          device_id_hint = decoded_pubkey
        elif not device_id_hint:
          parsed["device_id"] = matched_device_id
          device_id_hint = matched_device_id
        debug["result"] = debug.get("result") or "coord_override_applied"
        if DEBUG_PAYLOAD:
          print(f"[mqtt] Applied coord override to parsed data: device_id={parsed.get('device_id')} (matched_override={matched_device_id}) lat={coord_override['lat']} lon={coord_override['lon']}")
      # Always normalize timestamp if it's in the future
      if parsed_ts:
        parsed["ts"] = parsed_ts

  # Set check_lat/check_lon from parsed data if not already set from override
  if check_lat is None and check_lon is None:
    check_lat = parsed.get("lat") if parsed else None
    check_lon = parsed.get("lon") if parsed else None

  # Don't filter 0,0 coordinates if device has a coordinate override
  if parsed and _coords_are_zero(parsed.get("lat", 0), parsed.get("lon", 0)) and not has_coord_override:
    debug["result"] = "filtered_zero_coords"
    parsed = None
  # Check radius using override coordinates if available
  if parsed and check_lat is not None and check_lon is not None and not _within_map_radius(check_lat, check_lon):
    debug["result"] = "filtered_radius"
    if DEBUG_PAYLOAD:
      device_id_for_log = matched_device_id or decoded_pubkey or device_id_hint or topic_device_id or parsed.get("device_id")
      print(f"[mqtt] Filtered device by radius: device_id={device_id_for_log} lat={check_lat} lon={check_lon} (radius={MAP_RADIUS_KM}km)")
    parsed = None
    if matched_device_id or decoded_pubkey or device_id_hint:
      remove_id = matched_device_id or decoded_pubkey or device_id_hint
      loop.call_soon_threadsafe(
        update_queue.put_nowait,
        {
          "type": "device_remove",
          "device_id": remove_id,
          "reason": "radius",
        },
      )
  origin_id = debug.get("origin_id") or _device_id_from_topic(msg.topic)
  decoder_meta = debug.get("decoder_meta") or {}
  result = debug.get("result") or "unknown"
  device_role = debug.get("device_role")
  role_target_id = origin_id
  if device_role and result.startswith("decoded"):
    role_target_id = None
    loc_meta = (
      decoder_meta.get("location") if isinstance(decoder_meta, dict) else None
    )
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
    status_last.append(
      {
        "ts": debug_entry["ts"],
        "topic": msg.topic,
        "device_name": debug.get("device_name"),
        "device_role": debug.get("device_role"),
        "origin_id": origin_id,
        "json_keys": debug_entry.get("json_keys"),
        "payload_preview": debug_entry["payload_preview"],
      }
    )

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
        loop.call_soon_threadsafe(
          update_queue.put_nowait,
          {
            "type": "device_name",
            "device_id": origin_id,
          },
        )
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
        loop.call_soon_threadsafe(
          update_queue.put_nowait,
          {
            "type": "device_role",
            "device_id": role_target_id,
          },
        )

  path_hashes = decoder_meta.get("pathHashes")
  payload_type = decoder_meta.get("payloadType")
  route_type = decoder_meta.get("routeType")
  message_hash = decoder_meta.get("messageHash") or debug.get("packet_hash")
  snr_values = decoder_meta.get("snrValues")
  path_header = decoder_meta.get("path")
  path_length = decoder_meta.get("pathLength")
  direction = debug.get("direction")
  receiver_id = _device_id_from_topic(msg.topic)
  route_origin_id = None
  loc_meta = decoder_meta.get("location"
                             ) if isinstance(decoder_meta, dict) else None
  if isinstance(loc_meta, dict):
    decoded_pubkey = loc_meta.get("pubkey")
    if decoded_pubkey:
      route_origin_id = decoded_pubkey
  direction_value = str(direction or "").lower()
  if message_hash:
    cache = message_origins.get(message_hash)
    if not cache:
      cache = {
        "origin_id": None,
        "first_rx": None,
        "receivers": set(),
        "ts": time.time(),
      }
      message_origins[message_hash] = cache
    cache["ts"] = time.time()
    origin_for_tx = origin_id or receiver_id
    if direction_value == "tx" and origin_for_tx:
      cache["origin_id"] = origin_for_tx
    if direction_value == "rx" and receiver_id:
      cache["receivers"].add(receiver_id)
      if not cache.get("first_rx"):
        cache["first_rx"] = receiver_id
  loop: asyncio.AbstractEventLoop = userdata["loop"]
  try:
    payload_type = int(payload_type) if payload_type is not None else None
  except (TypeError, ValueError):
    payload_type = None
  try:
    route_type = int(route_type) if route_type is not None else None
  except (TypeError, ValueError):
    route_type = None

  if payload_type == 4:
    advert_device_id = route_origin_id or origin_id or receiver_id
    if advert_device_id:
      last_seen_in_advert[advert_device_id] = time.time()
      state.state_dirty = True

  route_hashes = None
  if path_hashes and isinstance(path_hashes, list):
    route_hashes = path_hashes
  elif payload_type not in (8, 9) and isinstance(path_header, list):
    if route_type in (0, 1):
      route_hashes = path_header

  # When the decoder reports 2-byte path IDs, integer hashes in the range
  # 0-255 must be padded to 4-char hex (e.g., 0x00AB → "00AB") instead of
  # collapsing to 2-char ("AB"), which would mismatch the device hash index.
  try:
    path_length_int = int(path_length) if path_length is not None else None
  except (TypeError, ValueError):
    path_length_int = None
  if route_hashes and path_length_int == 2:
    route_hashes = [
      f"{h:04X}" if isinstance(h, int) else h
      for h in route_hashes
    ]

  route_emitted = False
  if route_hashes and payload_type in ROUTE_PAYLOAD_TYPES_SET:
    loop.call_soon_threadsafe(
      update_queue.put_nowait,
      {
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
      },
    )
    route_emitted = True

  if not parsed:
    stats["unparsed_total"] += 1
    if DEBUG_PAYLOAD:
      print(
        f"[mqtt] UNPARSED result={result} topic={msg.topic} preview={debug_entry['payload_preview']!r}"
      )
    return

  parsed["raw_topic"] = msg.topic
  stats["parsed_total"] += 1
  stats["last_parsed_ts"] = time.time()
  stats["last_parsed_topic"] = msg.topic

  if DEBUG_PAYLOAD:
    print(
      f"[mqtt] PARSED topic={msg.topic} device={parsed['device_id']} lat={parsed['lat']} lon={parsed['lon']}"
    )

  loop.call_soon_threadsafe(
    update_queue.put_nowait, {
      "type": "device",
      "data": parsed
    }
  )


# =========================
# Broadcaster / Reaper
# =========================
async def broadcaster():
  while True:
    event = await update_queue.get()

    if isinstance(event, dict) and event.get("type") in (
      "device_name",
      "device_role",
    ):
      device_id = event.get("device_id")
      device_state = devices.get(device_id)
      if device_state:
        if device_id in device_names:
          device_state.name = device_names[device_id]
        if device_id in device_roles:
          device_state.role = device_roles[device_id]
        payload = {
          "type": "update",
          "device": _device_payload(device_id, device_state),
          "trail": trails.get(device_id, []),
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

    if isinstance(event, dict) and event.get("type") == "device_seen":
      device_id = event.get("device_id")
      if not device_id:
        continue

      seen_ts = event.get("last_seen_ts")
      if seen_ts:
        seen_devices[device_id] = seen_ts
      mqtt_ts_present = "mqtt_seen_ts" in event
      if mqtt_ts_present:
        mqtt_ts = event.get("mqtt_seen_ts")
        if mqtt_ts:
          mqtt_seen[device_id] = mqtt_ts
        else:
          mqtt_seen.pop(device_id, None)
      if "mqtt_online_source" in event:
        source = event.get("mqtt_online_source")
        if source:
          mqtt_online_source[device_id] = source
        else:
          mqtt_online_source.pop(device_id, None)
      if "mqtt_status_ts" in event:
        status_ts = event.get("mqtt_status_ts")
        if status_ts:
          mqtt_status_seen[device_id] = status_ts
      if "mqtt_status_value" in event:
        status_value = event.get("mqtt_status_value")
        if isinstance(status_value, str) and status_value.strip():
          mqtt_status_values[device_id] = status_value.strip().lower()
      if "mqtt_internal_ts" in event:
        internal_ts = event.get("mqtt_internal_ts")
        if internal_ts:
          mqtt_internal_seen[device_id] = internal_ts
      if "mqtt_packets_ts" in event:
        packets_ts = event.get("mqtt_packets_ts")
        if packets_ts:
          mqtt_packets_seen[device_id] = packets_ts

      payload = _mqtt_presence_payload(device_id, seen_devices.get(device_id))
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
        points = _route_points_from_device_ids(
          event.get("origin_id"), event.get("receiver_id")
        )
        if (
          points and event.get("origin_id") and event.get("receiver_id") and
          len(points) == 2
        ):
          point_ids = [event.get("origin_id"), event.get("receiver_id")]

      # Fallback: if path hashes are missing/unknown, draw a direct link when possible.
      if not points:
        points = _route_points_from_device_ids(
          event.get("origin_id"), event.get("receiver_id")
        )
        if points:
          route_mode = "direct"
          if (
            event.get("origin_id") and event.get("receiver_id") and
            len(points) == 2
          ):
            point_ids = [event.get("origin_id"), event.get("receiver_id")]

      if not points:
        continue

      if MAP_RADIUS_KM > 0:
        outside = any(
          not _within_map_radius(point[0], point[1]) for point in points
          if isinstance(point, (list, tuple)) and len(point) >= 2
        )
        if outside:
          continue

      route_id = event.get("route_id")
      if not route_id:
        message_hash = event.get("message_hash")
        receiver_key = event.get("receiver_id") or "observer"
        if message_hash:
          # Keep one active line per (message, observer) so multi-observer
          # receptions do not overwrite each other.
          route_id = f"{message_hash}:{receiver_key}"
        else:
          route_id = (
            f"{event.get('origin_id', 'route')}:{receiver_key}:"
            f"{int((event.get('ts') or time.time()) * 1000)}"
          )
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

      if point_ids and used_hashes:
        _record_neighbors(point_ids, route["ts"])
      _update_path_timestamps(point_ids, route["ts"])

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
          history_payload["edges"] = [
            _history_edge_payload(edge) for edge in history_updates
          ]
        if history_removed:
          history_payload_remove = {
            "type": "history_edges_remove",
            "edge_ids": history_removed,
          }
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

    upd = (
      event.get("data")
      if isinstance(event, dict) and event.get("type") == "device" else event
    )

    device_id = upd["device_id"]
    # Check if device has coordinate override before filtering by radius
    coord_override = device_coords.get(device_id)
    if coord_override:
      # Use override coordinates for radius check
      check_lat = coord_override["lat"]
      check_lon = coord_override["lon"]
    else:
      check_lat = upd.get("lat")
      check_lon = upd.get("lon")
    if not _within_map_radius(check_lat, check_lon):
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
    # Normalize timestamp: if it's too far in the future (> 1 hour), use current time
    now_ts = time.time()
    device_ts = upd.get("ts", now_ts)
    if device_ts > now_ts + 3600:  # More than 1 hour in future
      if DEBUG_PAYLOAD:
        print(f"[mqtt] Normalized future timestamp in device state: device={device_id} future_ts={device_ts} -> now={now_ts}")
      device_ts = now_ts
    device_state = DeviceState(
      device_id=device_id,
      lat=upd["lat"],
      lon=upd["lon"],
      ts=device_ts,
      heading=upd.get("heading"),
      speed=upd.get("speed"),
      rssi=upd.get("rssi"),
      snr=upd.get("snr"),
      name=upd.get("name") or device_names.get(device_id),
      role=upd.get("role") or device_roles.get(device_id),
      raw_topic=upd.get("raw_topic"),
    )
    # Apply coordinate overrides
    coord_override = device_coords.get(device_id)
    if coord_override:
      device_state.lat = coord_override["lat"]
      device_state.lon = coord_override["lon"]
    devices[device_id] = device_state
    now_seen = time.time()
    seen_devices[device_id] = now_seen
    if device_id not in first_seen_devices:
      first_seen_devices[device_id] = now_seen
    state.state_dirty = True
    if is_new_device:
      _rebuild_node_hash_map()
    if device_state.name:
      device_names[device_id] = device_state.name
    if device_state.role:
      device_roles[device_id] = device_state.role

    if TRAIL_LEN > 0 and not _coords_are_zero(
      device_state.lat, device_state.lon
    ):
      trails.setdefault(device_id, [])
      trails[device_id].append(
        [device_state.lat, device_state.lon, device_state.ts]
      )
      if len(trails[device_id]) > TRAIL_LEN:
        trails[device_id] = trails[device_id][-TRAIL_LEN:]
    elif device_id in trails:
      trails.pop(device_id, None)

    payload = {
      "type": "update",
      "device": _device_payload(device_id, device_state),
      "trail": trails.get(device_id, []),
    }

    dead = []
    for ws in list(clients):
      try:
        await ws.send_text(json.dumps(payload))
      except Exception:
        dead.append(ws)
    for ws in dead:
      clients.discard(ws)


async def reaper():
  global mqtt_presence_last_summary
  while True:
    now = time.time()

    if DEVICE_TTL_WINDOW_SECONDS > 0 or PATH_TTL_SECONDS > 0:
      stale = []
      for dev_id, st in list(devices.items()):
        device_stale = (
          DEVICE_TTL_WINDOW_SECONDS > 0 and (now - st.ts > DEVICE_TTL_WINDOW_SECONDS)
        )
        last_path_ts = state.last_seen_in_path.get(dev_id, 0.0)
        path_stale = (
          PATH_TTL_SECONDS > 0 and
          (last_path_ts <= 0 or now - last_path_ts > PATH_TTL_SECONDS)
        )

        if DEVICE_TTL_WINDOW_SECONDS > 0 and PATH_TTL_SECONDS > 0:
          should_stale = device_stale and path_stale
        elif DEVICE_TTL_WINDOW_SECONDS > 0:
          should_stale = device_stale
        else:
          should_stale = path_stale

        if should_stale:
          stale.append(dev_id)
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
          state.last_seen_in_path.pop(dev_id, None)
          state.state_dirty = True
        _rebuild_node_hash_map()

    if routes:
      bad_routes = []
      for route_id, route in list(routes.items()):
        points = route.get("points") if isinstance(route, dict) else None
        if not isinstance(points, list):
          continue
        if any(
          _coords_are_zero(p[0], p[1])
          for p in points if isinstance(p, list) and len(p) >= 2
        ):
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

    stale_routes = [
      route_id for route_id, route in list(routes.items())
      if now > route.get("expires_at", 0)
    ]
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
            await ws.send_text(
              json.dumps({
                "type": "history_edges",
                "edges": history_updates
              })
            )
          if history_removed:
            await ws.send_text(
              json.dumps(
                {
                  "type": "history_edges_remove",
                  "edge_ids": history_removed,
                }
              )
            )
        except Exception:
          dead.append(ws)
      for ws in dead:
        clients.discard(ws)

    if HEAT_TTL_SECONDS > 0 and heat_events:
      cutoff = now - HEAT_TTL_SECONDS
      heat_events[:] = [
        entry for entry in heat_events if entry.get("ts", 0) >= cutoff
      ]

    if message_origins:
      for msg_hash, info in list(message_origins.items()):
        if now - info.get("ts", 0) > MESSAGE_ORIGIN_TTL_SECONDS:
          message_origins.pop(msg_hash, None)

    _prune_neighbors(now)

    presence_summary = _mqtt_presence_summary(now)
    if presence_summary != mqtt_presence_last_summary:
      mqtt_presence_last_summary = dict(presence_summary)
      payload = {"type": "mqtt_presence", "mqtt_presence": presence_summary}
      dead = []
      for ws in list(clients):
        try:
          await ws.send_text(json.dumps(payload))
        except Exception:
          dead.append(ws)
      for ws in dead:
        clients.discard(ws)

    retention_window = max(
      DEVICE_TTL_WINDOW_SECONDS if DEVICE_TTL_WINDOW_SECONDS > 0 else 0,
      PATH_TTL_SECONDS if PATH_TTL_SECONDS > 0 else 0,
    )
    prune_after = max(retention_window * 3, 900) if retention_window > 0 else 86400
    for dev_id, last in list(seen_devices.items()):
      if now - last > prune_after:
        seen_devices.pop(dev_id, None)
        first_seen_devices.pop(dev_id, None)
        last_seen_in_advert.pop(dev_id, None)
        state.last_seen_in_path.pop(dev_id, None)

    await asyncio.sleep(5)


# =========================
# Helpers: Turnstile auth
# =========================
TURNSTILE_BOT_TOKENS = [
  token.strip().lower()
  for token in TURNSTILE_BOT_ALLOWLIST.split(",")
  if token and token.strip()
]


def _is_allowlisted_bot(request: Request) -> bool:
  """Return True when the request looks like a known embed bot."""
  if not TURNSTILE_ENABLED or not TURNSTILE_BOT_BYPASS:
    return False
  user_agent = (request.headers.get("user-agent") or "").lower()
  if not user_agent:
    return False
  for token in TURNSTILE_BOT_TOKENS:
    if token in user_agent:
      return True
  return False


def _check_turnstile_auth(request: Request) -> bool:
  """Check if user has valid Turnstile auth token."""
  if not TURNSTILE_ENABLED or not turnstile_verifier:
    return True

  # Allowlist common embed bots (Discord, Slack, etc.)
  if _is_allowlisted_bot(request):
    ua = request.headers.get("user-agent", "-")
    print(f"[turnstile] bot bypass user-agent={ua}")
    return True

  # Check for auth token in cookies or headers
  auth_token = request.cookies.get("meshmap_auth") or \
               request.headers.get("Authorization", "").replace("Bearer ", "")

  if auth_token and turnstile_verifier.verify_auth_token(auth_token):
    return True

  return False


# =========================
# FastAPI routes
# =========================
@app.get("/")
def root(request: Request):
  # If Turnstile is enabled and user isn't authenticated, serve landing page
  if TURNSTILE_ENABLED and not _check_turnstile_auth(request):
    landing_path = os.path.join(APP_DIR, "static", "landing.html")
    try:
      with open(landing_path, "r", encoding="utf-8") as handle:
        content = handle.read()
    except Exception:
      return FileResponse("static/landing.html")

    # Replace template variables in landing page
    replacements = {
      "SITE_TITLE": SITE_TITLE,
      "SITE_DESCRIPTION": SITE_DESCRIPTION,
      "SITE_ICON": SITE_ICON,
      "TURNSTILE_SITE_KEY": TURNSTILE_SITE_KEY,
      "ASSET_VERSION": ASSET_VERSION,
    }
    for key, value in replacements.items():
      safe_value = html.escape(str(value), quote=True)
      content = content.replace(f"{{{{{key}}}}}", safe_value)

    return HTMLResponse(content)

  # Serve map page
  html_path = os.path.join(APP_DIR, "static", "index.html")
  try:
    with open(html_path, "r", encoding="utf-8") as handle:
      content = handle.read()
  except Exception:
    return FileResponse("static/index.html")

  # Check for lat/lon parameters for dynamic preview image
  query_params = request.query_params
  lat_param = query_params.get("lat") or query_params.get("latitude")
  lon_param = (
    query_params.get("lon") or query_params.get("lng") or
    query_params.get("long") or query_params.get("longitude")
  )
  zoom_param = query_params.get("zoom")

  og_image_tag = ""
  twitter_image_tag = ""
  og_url = SITE_URL

  # Generate dynamic preview image if coordinates are provided
  if lat_param and lon_param:
    try:
      lat = float(lat_param)
      lon = float(lon_param)
      zoom = int(zoom_param) if zoom_param and zoom_param.isdigit() else 13
      zoom = max(1, min(18, zoom))  # Clamp zoom between 1-18

      # Generate preview image URL pointing to our own server
      # Use absolute URL for better compatibility with Discord and other platforms
      base_url = str(request.url).split("?")[0].rstrip("/")
      preview_params = urlencode(
        {
          "lat": lat,
          "lon": lon,
          "zoom": zoom,
          "marker": "blue",
          "theme": "dark",
        }
      )
      preview_url = f"{base_url}/preview.png?{preview_params}"

      # Ensure absolute URL (use SITE_URL if available, otherwise construct from request)
      if SITE_URL and SITE_URL.startswith("http"):
        site_base = SITE_URL.rstrip("/")
        preview_url = f"{site_base}/preview.png?{preview_params}"
      elif not preview_url.startswith("http"):
        # Fallback: construct from request
        scheme = request.url.scheme
        host = request.headers.get("host", request.url.hostname or "localhost")
        preview_url = f"{scheme}://{host}/preview.png?{preview_params}"

      safe_image = html.escape(preview_url, quote=True)
      # Add image dimensions for better Discord/social media compatibility
      # Note: Preview image may fail if container can't reach external services
      # In that case, fall back to static SITE_OG_IMAGE if available
      og_image_tag = (
        f'<meta property="og:image" content="{safe_image}" />\n'
        f'  <meta property="og:image:width" content="1200" />\n'
        f'  <meta property="og:image:height" content="630" />\n'
        f'  <meta property="og:image:type" content="image/png" />'
      )
      twitter_image_tag = f'<meta name="twitter:image" content="{safe_image}" />'

      # If static image is configured, add it as a fallback
      if SITE_OG_IMAGE:
        safe_static_image = html.escape(str(SITE_OG_IMAGE), quote=True)
        og_image_tag += f'\n  <meta property="og:image:secure_url" content="{safe_static_image}" />'

      # Update og:url to include query parameters
      base_url = str(request.url).split("?")[0]
      og_url = f"{base_url}?lat={lat}&lon={lon}"
      if zoom_param:
        og_url += f"&zoom={zoom}"
    except (ValueError, TypeError):
      # Invalid coordinates, fall back to static image
      if SITE_OG_IMAGE:
        safe_image = html.escape(str(SITE_OG_IMAGE), quote=True)
        og_image_tag = f'<meta property="og:image" content="{safe_image}" />'
        twitter_image_tag = (
          f'<meta name="twitter:image" content="{safe_image}" />'
        )
  elif SITE_OG_IMAGE:
    safe_image = html.escape(str(SITE_OG_IMAGE), quote=True)
    og_image_tag = f'<meta property="og:image" content="{safe_image}" />'
    twitter_image_tag = f'<meta name="twitter:image" content="{safe_image}" />'

  content = content.replace("{{OG_IMAGE_TAG}}", og_image_tag)
  content = content.replace("{{TWITTER_IMAGE_TAG}}", twitter_image_tag)

  trail_info_suffix = ""
  if TRAIL_LEN > 0:
    trail_info_suffix = f" Trails show last ~{TRAIL_LEN} points."

  # Escape og_url for HTML
  SAFE_OG_URL = html.escape(str(og_url), quote=True)

  replacements = {
    "SITE_TITLE":
      SITE_TITLE,
    "SITE_DESCRIPTION":
      SITE_DESCRIPTION,
    "SITE_URL":
      SAFE_OG_URL,
    "SITE_ICON":
      SITE_ICON,
    "SITE_FEED_NOTE":
      SITE_FEED_NOTE,
    "CUSTOM_LINK_URL":
      CUSTOM_LINK_URL,
    "ASSET_VERSION":
      ASSET_VERSION,
    "DISTANCE_UNITS":
      DISTANCE_UNITS,
    "NODE_MARKER_RADIUS":
      NODE_MARKER_RADIUS,
    "HISTORY_LINK_SCALE":
      HISTORY_LINK_SCALE,
    "TRAIL_INFO_SUFFIX":
      trail_info_suffix,
    "PROD_MODE":
      str(PROD_MODE).lower(),
    "PROD_TOKEN":
      PROD_TOKEN,
    "MAP_START_LAT":
      MAP_START_LAT,
    "MAP_START_LON":
      MAP_START_LON,
    "MAP_START_ZOOM":
      MAP_START_ZOOM,
    "MAP_RADIUS_KM":
      MAP_RADIUS_KM,
    "MAP_RADIUS_SHOW":
      str(MAP_RADIUS_SHOW).lower(),
    "MAP_DEFAULT_LAYER":
      MAP_DEFAULT_LAYER,
    "LOS_ELEVATION_URL":
      LOS_ELEVATION_URL,
    "LOS_ELEVATION_PROXY_URL":
      LOS_ELEVATION_PROXY_URL,
    "LOS_SAMPLE_MIN":
      LOS_SAMPLE_MIN,
    "LOS_SAMPLE_MAX":
      LOS_SAMPLE_MAX,
    "LOS_SAMPLE_STEP_METERS":
      LOS_SAMPLE_STEP_METERS,
    "LOS_PEAKS_MAX":
      LOS_PEAKS_MAX,
    "MQTT_ONLINE_SECONDS":
      MQTT_ONLINE_SECONDS,
    "MQTT_ONLINE_STATUS_TTL_SECONDS":
      MQTT_ONLINE_STATUS_TTL_SECONDS,
    "MQTT_ONLINE_INTERNAL_TTL_SECONDS":
      MQTT_ONLINE_INTERNAL_TTL_SECONDS,
    "MQTT_ACTIVITY_PACKETS_TTL_SECONDS":
      MQTT_ACTIVITY_PACKETS_TTL_SECONDS,
    "COVERAGE_API_URL":
      COVERAGE_API_URL,
    "WEATHER_RADAR_ENABLED":
      str(WEATHER_RADAR_ENABLED).lower(),
    "WEATHER_RADAR_COUNTRY_BOUNDS_ENABLED":
      str(WEATHER_RADAR_COUNTRY_BOUNDS_ENABLED).lower(),
    "WEATHER_RADAR_COUNTRY_LOOKUP_URL":
      WEATHER_RADAR_COUNTRY_LOOKUP_URL,
    "WEATHER_WIND_ENABLED":
      str(WEATHER_WIND_ENABLED).lower(),
    "WEATHER_WIND_API_URL":
      WEATHER_WIND_API_URL,
    "WEATHER_WIND_GRID_SIZE":
      WEATHER_WIND_GRID_SIZE,
    "WEATHER_WIND_REFRESH_SECONDS":
      WEATHER_WIND_REFRESH_SECONDS,
    "UPDATE_AVAILABLE":
      str(bool(git_update_info.get("available"))).lower(),
    "UPDATE_LOCAL":
      git_update_info.get("local_short") or "",
    "UPDATE_REMOTE":
      git_update_info.get("remote_short") or "",
    "UPDATE_BANNER_HIDDEN":
       "" if git_update_info.get("available") else "hidden",
    "TURNSTILE_ENABLED":
       str(TURNSTILE_ENABLED).lower(),
    "TURNSTILE_SITE_KEY":
       TURNSTILE_SITE_KEY,
  }
  for key, value in replacements.items():
    safe_value = html.escape(str(value), quote=True)
    content = content.replace(f"{{{{{key}}}}}", safe_value)

  return HTMLResponse(content)


@app.get("/preview.png")
async def preview_image(
  lat: Optional[float] = Query(None, alias="lat"),
  lon: Optional[float] = Query(None, alias="lon"),
  zoom: Optional[int] = Query(13, alias="zoom"),
  marker: Optional[str] = Query("blue", alias="marker"),
  theme: Optional[str] = Query("dark", alias="theme"),
):
  """
    Generate a preview image of the map with a pin marker at the specified coordinates.
    Returns a PNG image suitable for Open Graph/Twitter card previews.

    Marker options:
    - red-pin, blue-pin, green-pin, yellow-pin, orange-pin, purple-pin, black-pin, white-pin
    - red, blue, green, yellow, orange, purple, black, white (simple circle markers)
    - Custom format: color-pin or color (e.g., "blue-pin", "green")
    """
  if lat is None or lon is None:
    # Return a default/error image if coordinates not provided
    return Response(content=b"", status_code=400, media_type="image/png")

  try:
    zoom_val = max(1, min(18, int(zoom) if zoom else 14))

    # Image dimensions for social media previews (Open Graph standard)
    width = 1200
    height = 630

    # Validate and sanitize marker option
    marker_str = str(marker).lower().strip() if marker else "blue"
    if not marker_str or marker_str == "none":
      marker_str = "blue"

    # Validate theme option (light or dark)
    theme_str = str(theme).lower().strip() if theme else "dark"
    if theme_str not in ("light", "dark"):
      theme_str = "dark"

    # Generate map image server-side using OSM tiles
    try:
      # Convert lat/lon to tile coordinates
      def deg2num(lat_deg, lon_deg, zoom_level):
        lat_rad = math.radians(lat_deg)
        n = 2.0**zoom_level
        xtile = int((lon_deg + 180.0) / 360.0 * n)
        ytile = int((1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * n)
        return (xtile, ytile)

      def num2deg(xtile, ytile, zoom_level):
        n = 2.0**zoom_level
        lon_deg = xtile / n * 360.0 - 180.0
        lat_rad = math.atan(math.sinh(math.pi * (1 - 2 * ytile / n)))
        lat_deg = math.degrees(lat_rad)
        return (lat_deg, lon_deg)

      # Calculate which tiles we need
      center_tile_x, center_tile_y = deg2num(lat, lon, zoom_val)
      tile_size = 256
      tiles_x = math.ceil(width / tile_size) + 2
      tiles_y = math.ceil(height / tile_size) + 2

      # Calculate pixel position of center point within its tile
      # Get the northwest corner of the center tile
      nw_lat, nw_lon = num2deg(center_tile_x, center_tile_y, zoom_val)
      # Get the southeast corner of the center tile
      se_lat, se_lon = num2deg(center_tile_x + 1, center_tile_y + 1, zoom_val)

      # Calculate pixel offset within the center tile
      center_tile_pixel_x = int((lon - nw_lon) / (se_lon - nw_lon) * tile_size)
      center_tile_pixel_y = int((nw_lat - lat) / (nw_lat - se_lat) * tile_size)

      # Calculate which tiles to fetch
      start_tile_x = center_tile_x - tiles_x // 2
      start_tile_y = center_tile_y - tiles_y // 2

      # Create blank image with theme-appropriate background
      bg_color = (
        (18, 18, 18) if theme_str == "dark" else (242, 239, 233)
      )  # Dark or light background
      final_image = Image.new("RGB", (width, height), bg_color)

      # Fetch and composite tiles
      tiles_fetched = 0
      tiles_failed = 0
      async with httpx.AsyncClient(timeout=10.0, verify=False) as client:
        for ty in range(tiles_y):
          for tx in range(tiles_x):
            tile_x = start_tile_x + tx
            tile_y = start_tile_y + ty

            # Use theme-appropriate tile server
            if theme_str == "dark":
              # CartoDB Dark Matter tiles
              tile_url = f"https://a.basemaps.cartocdn.com/dark_all/{zoom_val}/{tile_x}/{tile_y}.png"
            else:
              # Standard OSM light tiles
              tile_url = f"https://tile.openstreetmap.org/{zoom_val}/{tile_x}/{tile_y}.png"

            try:
              response = await client.get(tile_url)
              if response.status_code == 200:
                tile_img = Image.open(BytesIO(response.content))
                # Calculate position: center the marker at the center of the image
                # The center tile should place the marker at the center pixel position
                x_offset = (
                  (tx - tiles_x // 2) * tile_size + width // 2 -
                  center_tile_pixel_x
                )
                y_offset = (
                  (ty - tiles_y // 2) * tile_size + height // 2 -
                  center_tile_pixel_y
                )
                final_image.paste(
                  tile_img,
                  (x_offset, y_offset),
                  tile_img if tile_img.mode == "RGBA" else None,
                )
                tiles_fetched += 1
              else:
                tiles_failed += 1
                print(
                  f"[preview] Tile {tile_x}/{tile_y} returned status {response.status_code}"
                )
            except Exception as tile_error:
              tiles_failed += 1
              print(
                f"[preview] Failed to fetch tile {tile_x}/{tile_y} from {tile_url}: {tile_error}"
              )
              continue

      print(f"[preview] Fetched {tiles_fetched} tiles, {tiles_failed} failed")

      # Draw current devices (all in-bounds, no cap)
      def latlon_to_global_px(lat_deg: float, lon_deg: float,
                              zoom_level: int) -> Tuple[float, float]:
        lat_rad = math.radians(lat_deg)
        n = 2.0**zoom_level
        x_px = (lon_deg + 180.0) / 360.0 * n * tile_size
        y_px = (
          (1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * n * tile_size
        )
        return (x_px, y_px)

      draw = ImageDraw.Draw(final_image)
      center_px_x, center_px_y = latlon_to_global_px(lat, lon, zoom_val)
      node_radius = 5
      node_color = (86, 198, 255) if theme_str == "dark" else (25, 83, 170)
      node_outline = (15, 15, 15) if theme_str == "dark" else (255, 255, 255)
      for state in list(devices.values()):
        try:
          dev_lat = float(state.lat)
          dev_lon = float(state.lon)
        except Exception:
          continue
        if _coords_are_zero(dev_lat, dev_lon
                           ) or not _within_map_radius(dev_lat, dev_lon):
          continue
        dev_px_x, dev_px_y = latlon_to_global_px(dev_lat, dev_lon, zoom_val)
        img_x = width / 2 + (dev_px_x - center_px_x)
        img_y = height / 2 + (dev_px_y - center_px_y)
        if (
          img_x < -node_radius or img_x > width + node_radius or
          img_y < -node_radius or img_y > height + node_radius
        ):
          continue
        draw.ellipse(
          [
            (img_x - node_radius, img_y - node_radius),
            (img_x + node_radius, img_y + node_radius),
          ],
          fill=node_color,
          outline=node_outline,
          width=2,
        )

      # Draw marker
      marker_color_map = {
        "red": (220, 53, 69),
        "blue": (0, 123, 255),
        "green": (40, 167, 69),
        "yellow": (255, 193, 7),
        "orange": (255, 152, 0),
        "purple": (108, 117, 125),
        "black": (0, 0, 0),
        "white": (255, 255, 255),
      }
      marker_color = marker_color_map.get(
        marker_str, (0, 123, 255)
      )  # Default to blue

      # Calculate marker position (center of image)
      marker_x = width // 2
      marker_y = height // 2

      # Draw a circle marker
      marker_radius = 12
      draw.ellipse(
        [
          (marker_x - marker_radius, marker_y - marker_radius),
          (marker_x + marker_radius, marker_y + marker_radius),
        ],
        fill=marker_color,
        outline=(255, 255, 255),
        width=2,
      )

      # Convert to PNG bytes
      img_bytes = BytesIO()
      final_image.save(img_bytes, format="PNG")
      img_bytes.seek(0)

      return Response(
        content=img_bytes.getvalue(),
        media_type="image/png",
        headers={
          "Cache-Control": "public, max-age=3600",  # Cache for 1 hour
        },
      )

    except Exception as e:
      print(f"[preview] Error generating map image: {e}")
      import traceback

      traceback.print_exc()

      # Even if tile fetching fails, try to return a simple map with marker
      try:
        bg_color = (18, 18, 18) if theme_str == "dark" else (242, 239, 233)
        fallback_image = Image.new("RGB", (width, height), bg_color)
        draw = ImageDraw.Draw(fallback_image)

        # Draw marker
        marker_color_map = {
          "red": (220, 53, 69),
          "blue": (0, 123, 255),
          "green": (40, 167, 69),
          "yellow": (255, 193, 7),
          "orange": (255, 152, 0),
          "purple": (108, 117, 125),
          "black": (0, 0, 0),
          "white": (255, 255, 255),
        }
        marker_color = marker_color_map.get(marker_str, (0, 123, 255))
        marker_x = width // 2
        marker_y = height // 2
        marker_radius = 12
        draw.ellipse(
          [
            (marker_x - marker_radius, marker_y - marker_radius),
            (marker_x + marker_radius, marker_y + marker_radius),
          ],
          fill=marker_color,
          outline=(255, 255, 255),
          width=2,
        )

        img_bytes = BytesIO()
        fallback_image.save(img_bytes, format="PNG")
        img_bytes.seek(0)

        print(
          f"[preview] Returning fallback image with marker (tile fetch failed)"
        )
        return Response(
          content=img_bytes.getvalue(),
          media_type="image/png",
          headers={"Cache-Control": "public, max-age=300"},
        )
      except Exception as fallback_error:
        print(
          f"[preview] Fallback image generation also failed: {fallback_error}"
        )
        # Only redirect to static image if even fallback fails
        if SITE_OG_IMAGE and SITE_OG_IMAGE.startswith("http"):
          from fastapi.responses import RedirectResponse

          print(
            f"[preview] All image generation failed, redirecting to static OG image: {SITE_OG_IMAGE}"
          )
          return RedirectResponse(url=SITE_OG_IMAGE, status_code=302)

        # Return transparent PNG as last resort
        transparent_png = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xdb\x00\x00\x00\x00IEND\xaeB`\x82"
        return Response(
          content=transparent_png,
          media_type="image/png",
          headers={"Cache-Control": "public, max-age=300"},
        )
  except Exception as e:
    # Log error for debugging
    print(f"[preview] Error generating preview image: {e}")
    import traceback

    traceback.print_exc()
    # Return empty image on error
    return Response(content=b"", status_code=500, media_type="image/png")


@app.get("/map")
def map_page(request: Request):
  """Serve the map page (with Turnstile auth check)."""
  # If Turnstile is enabled and user isn't authenticated, redirect to landing
  if TURNSTILE_ENABLED and not _check_turnstile_auth(request):
    print("[map] Unauthenticated user accessing /map, redirecting to /")
    return HTMLResponse(
      "<script>window.location.href = '/';</script>",
      status_code=303,
    )

  # Otherwise serve the map page
  html_path = os.path.join(APP_DIR, "static", "index.html")
  try:
    with open(html_path, "r", encoding="utf-8") as handle:
      content = handle.read()
  except Exception:
    return FileResponse("static/index.html")

  # Include all the template replacements (same as root endpoint)
  # Generate OG image tags
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

  SAFE_OG_URL = html.escape(SITE_URL, quote=True)

  replacements = {
    "SITE_TITLE": SITE_TITLE,
    "SITE_DESCRIPTION": SITE_DESCRIPTION,
    "SITE_URL": SAFE_OG_URL,
    "SITE_ICON": SITE_ICON,
    "SITE_FEED_NOTE": SITE_FEED_NOTE,
    "CUSTOM_LINK_URL": CUSTOM_LINK_URL,
    "ASSET_VERSION": ASSET_VERSION,
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
    "LOS_ELEVATION_PROXY_URL": LOS_ELEVATION_PROXY_URL,
    "LOS_SAMPLE_MIN": LOS_SAMPLE_MIN,
    "LOS_SAMPLE_MAX": LOS_SAMPLE_MAX,
    "LOS_SAMPLE_STEP_METERS": LOS_SAMPLE_STEP_METERS,
    "LOS_PEAKS_MAX": LOS_PEAKS_MAX,
    "MQTT_ONLINE_SECONDS": MQTT_ONLINE_SECONDS,
    "MQTT_ONLINE_STATUS_TTL_SECONDS": MQTT_ONLINE_STATUS_TTL_SECONDS,
    "MQTT_ONLINE_INTERNAL_TTL_SECONDS": MQTT_ONLINE_INTERNAL_TTL_SECONDS,
    "MQTT_ACTIVITY_PACKETS_TTL_SECONDS": MQTT_ACTIVITY_PACKETS_TTL_SECONDS,
    "COVERAGE_API_URL": COVERAGE_API_URL,
    "WEATHER_RADAR_ENABLED": str(WEATHER_RADAR_ENABLED).lower(),
    "WEATHER_RADAR_COUNTRY_BOUNDS_ENABLED": str(WEATHER_RADAR_COUNTRY_BOUNDS_ENABLED).lower(),
    "WEATHER_RADAR_COUNTRY_LOOKUP_URL": WEATHER_RADAR_COUNTRY_LOOKUP_URL,
    "WEATHER_WIND_ENABLED": str(WEATHER_WIND_ENABLED).lower(),
    "WEATHER_WIND_API_URL": WEATHER_WIND_API_URL,
    "WEATHER_WIND_GRID_SIZE": WEATHER_WIND_GRID_SIZE,
    "WEATHER_WIND_REFRESH_SECONDS": WEATHER_WIND_REFRESH_SECONDS,
    "UPDATE_AVAILABLE": str(bool(git_update_info.get("available"))).lower(),
    "UPDATE_LOCAL": git_update_info.get("local_short") or "",
    "UPDATE_REMOTE": git_update_info.get("remote_short") or "",
    "UPDATE_BANNER_HIDDEN": "" if git_update_info.get("available") else "hidden",
    "TURNSTILE_ENABLED": str(TURNSTILE_ENABLED).lower(),
    "TURNSTILE_SITE_KEY": TURNSTILE_SITE_KEY,
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
        "purpose": "any",
      },
      {
        "src": SITE_ICON,
        "sizes": "512x512",
        "type": "image/png",
        "purpose": "any maskable",
      },
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
      "icons": icons,
    },
    media_type="application/manifest+json",
  )


@app.get("/sw.js")
def service_worker():
  return FileResponse("static/sw.js", media_type="application/javascript")


@app.get("/snapshot")
def snapshot(request: Request):
  _require_prod_token(request)
  now = time.time()
  return {
    "devices": {
      k: _device_payload(k, v)
      for k, v in devices.items()
    },
    "trails": trails,
    "routes": [_route_payload(r) for r in routes.values()],
    "history_edges":
      [_history_edge_payload(e) for e in route_history_edges.values()],
    "history_window_seconds": int(max(0, ROUTE_HISTORY_HOURS * 3600)),
    "heat": _serialize_heat_events(),
    "update": git_update_info,
    "mqtt_presence": _mqtt_presence_summary(now),
    "server_time": now,
  }


@app.get("/stats")
def get_stats():
  presence_summary = _mqtt_presence_summary()
  if PROD_MODE:
    return {
      "stats":
        {
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
      "mqtt_presence": presence_summary,
      "server_time": time.time(),
    }

  top_topics = sorted(topic_counts.items(), key=lambda kv: kv[1],
                      reverse=True)[:20]
  return {
    "stats":
      stats,
    "result_counts":
      result_counts,
    "mapped_devices":
      len(devices),
    "route_count":
      len(routes),
    "history_edge_count":
      len(route_history_edges),
    "history_segments":
      len(route_history_segments),
    "seen_devices":
      len(seen_devices),
    "seen_recent":
      sorted(seen_devices.items(), key=lambda kv: kv[1], reverse=True)[:20],
    "mqtt_presence":
      presence_summary,
    "top_topics":
      top_topics,
    "decoder":
      {
        "decode_with_node": DECODE_WITH_NODE,
        "node_ready": _node_ready_once,
        "node_unavailable": _node_unavailable_once,
      },
    "route_payload_types":
      sorted(ROUTE_PAYLOAD_TYPES_SET),
    "direct_coords":
      {
        "mode": DIRECT_COORDS_MODE,
        "topic_regex": DIRECT_COORDS_TOPIC_REGEX,
        "regex_valid": DIRECT_COORDS_TOPIC_RE is not None,
        "allow_zero": DIRECT_COORDS_ALLOW_ZERO,
      },
    "server_time":
      time.time(),
  }


@app.get("/api/nodes")
def api_nodes(
  request: Request,
  updated_since: Optional[str] = None,
  mode: Optional[str] = None,
  format: Optional[str] = None,
):
  _require_prod_token(request)
  cutoff = _parse_updated_since(updated_since)
  mode_value = (mode or "").strip().lower()
  force_full = mode_value in ("full", "all", "snapshot")
  apply_delta = bool(cutoff is not None and not force_full)
  format_value = (format or "").strip().lower()
  format_nested = format_value in ("nested", "object", "wrapped", "v2")
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
  if format_nested:
    payload["data"] = {"nodes": nodes}
  else:
    # Default to the flat list for MeshBuddy compatibility.
    payload["data"] = nodes
    payload["nodes"] = nodes
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
  payload["name"] = (
    (state.name if state else None) or device_names.get(device_id) or ""
  )
  payload["role"] = (state.role
                     if state else None) or device_roles.get(device_id)
  payload["last_seen_ts"] = seen_devices.get(device_id
                                            ) or (state.ts if state else None)
  payload["server_time"] = time.time()
  return payload


def _peer_device_payload(
  peer_id: str, count: int, total: int, last_ts: Optional[float]
) -> Dict[str, Any]:
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
    _peer_device_payload(
      peer_id, count, inbound_total, inbound_last.get(peer_id)
    ) for peer_id, count in inbound.items()
  ]
  outbound_items = [
    _peer_device_payload(
      peer_id, count, outbound_total, outbound_last.get(peer_id)
    ) for peer_id, count in outbound.items()
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
def line_of_sight(
  lat1: float,
  lon1: float,
  lat2: float,
  lon2: float,
  profile: bool = False,
  h1: float = 0.0,
  h2: float = 0.0,
):
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

  safe_h1 = h1 if math.isfinite(h1) else 0.0
  safe_h2 = h2 if math.isfinite(h2) else 0.0
  start_elev = elevations[0] + safe_h1
  end_elev = elevations[-1] + safe_h2
  adjusted = list(elevations)
  adjusted[0] = start_elev
  adjusted[-1] = end_elev
  max_obstruction = _los_max_obstruction(points, adjusted, 0, len(points) - 1)
  max_terrain = max(elevations)
  blocked = max_obstruction > 0.0
  suggestion = _find_los_suggestion(points, adjusted) if blocked else None
  profile_samples = []
  if distance_m > 0:
    for (lat, lon, t), elev in zip(points, elevations):
      line_elev = start_elev + (end_elev - start_elev) * t
      profile_samples.append(
        [
          round(distance_m * t, 2),
          round(float(elev), 2),
          round(float(line_elev), 2),
        ]
      )
  peaks = _find_los_peaks(points, elevations, distance_m)

  response = {
    "ok": True,
    "blocked": blocked,
    "max_obstruction_m": round(max_obstruction, 2),
    "distance_m": round(distance_m, 2),
    "distance_km": round(distance_m / 1000.0, 3),
    "distance_mi": round(distance_m / 1609.344, 3),
    "samples": len(points),
    "elevation_m":
      {
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
      [round(lat, 6),
       round(lon, 6),
       round(t, 4),
       round(float(elev), 2)]
      for (lat, lon, t), elev in zip(points, elevations)
    ]
  return response


@app.get("/los/elevations")
def los_elevations(locations: str = ""):
  raw = [loc for loc in (locations or "").split("|") if loc.strip()]
  if not raw:
    return {"status": "ERROR", "error": "missing_locations"}
  if len(raw) > 200:
    return {"status": "ERROR", "error": "too_many_locations"}
  points = []
  for loc in raw:
    parts = loc.split(",")
    if len(parts) != 2:
      return {"status": "ERROR", "error": "invalid_location"}
    try:
      lat = float(parts[0])
      lon = float(parts[1])
    except (ValueError, TypeError):
      return {"status": "ERROR", "error": "invalid_coords"}
    normalized = _normalize_lat_lon(lat, lon)
    if not normalized:
      return {"status": "ERROR", "error": "invalid_coords"}
    points.append((normalized[0], normalized[1], 0.0))

  elevations, error = _fetch_elevations(points)
  if error:
    return {"status": "ERROR", "error": error}
  return {
    "status": "OK",
    "results": [{"elevation": round(float(elev), 2)} for elev in elevations],
    "provider": LOS_ELEVATION_URL,
  }


@app.get("/coverage")
async def get_coverage():
  if not COVERAGE_API_URL:
    raise HTTPException(
      status_code=503,
      detail=
      "coverage_api_not_configured: Set COVERAGE_API_URL in .env (e.g., http://localhost:3000)",
    )
  try:
    url = f"{COVERAGE_API_URL}/get-samples"
    print(f"[coverage] Fetching from {url}")
    async with httpx.AsyncClient(timeout=10.0) as client:
      response = await client.get(url)
      response.raise_for_status()
      data = response.json()
      # /get-samples returns { keys: [...] }, extract the keys array
      samples_raw = (
        data.get("keys", []) if isinstance(data, dict) else
        (data if isinstance(data, list) else [])
      )
      samples = samples_raw if isinstance(samples_raw, list) else []
      print(
        f"[coverage] Received {len(samples) if isinstance(samples, list) else 'non-list'} items from coverage API"
      )
      if isinstance(samples, list) and len(samples) > 0:
        print(
          f"[coverage] Sample item keys: {list(samples[0].keys()) if samples[0] else 'N/A'}"
        )
      return samples
  except httpx.TimeoutException:
    raise HTTPException(status_code=504, detail="coverage_api_timeout")
  except httpx.HTTPStatusError as e:
    raise HTTPException(
      status_code=502,
      detail=
      f"coverage_api_error: HTTP {e.response.status_code} from {COVERAGE_API_URL}",
    )
  except httpx.HTTPError as e:
    raise HTTPException(status_code=502, detail=f"coverage_api_error: {str(e)}")
  except Exception as e:
    raise HTTPException(
      status_code=500, detail=f"coverage_fetch_error: {str(e)}"
    )


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


@app.post("/api/verify-turnstile")
async def verify_turnstile(request: Request):
  """Verify Cloudflare Turnstile token and issue auth token."""
  if not TURNSTILE_ENABLED or not turnstile_verifier:
    return JSONResponse(
      {"success": False, "error": "Turnstile is not enabled"},
      status_code=400,
    )

  try:
    body = await request.json()
    token = body.get("token", "").strip()

    if not token:
      return JSONResponse(
        {"success": False, "error": "Token is required"},
        status_code=400,
      )

    # Verify token with Cloudflare
    success, error = await turnstile_verifier.verify_turnstile_token(
      token,
      remote_ip=request.client.host if request.client else None,
    )

    if not success:
      print(f"[turnstile] Verification failed: {error}")
      return JSONResponse(
        {"success": False, "error": error or "Verification failed"},
        status_code=400,
      )

    # Issue auth token for client
    auth_token = turnstile_verifier.issue_auth_token()
    print(f"[turnstile] Verification successful, issued auth token")

    # Create response with auth token and set cookie
    response = JSONResponse(
      {
        "success": True,
        "auth_token": auth_token,
      },
      status_code=200,
    )

    # Set auth cookie (expires in TURNSTILE_TOKEN_TTL_SECONDS)
    response.set_cookie(
      key="meshmap_auth",
      value=auth_token,
      max_age=TURNSTILE_TOKEN_TTL_SECONDS,
      path="/",
      samesite="lax",
    )

    return response

  except json.JSONDecodeError:
    return JSONResponse(
      {"success": False, "error": "Invalid JSON"},
      status_code=400,
    )
  except Exception as e:
    print(f"[turnstile] Error verifying token: {e}")
    return JSONResponse(
      {"success": False, "error": str(e)},
      status_code=500,
    )


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
  if not _ws_authorized(ws):
    await ws.accept()
    await ws.close(code=1008)
    return
  await ws.accept()
  clients.add(ws)

  await ws.send_text(
    json.dumps(
      {
        "type": "snapshot",
        "devices": {
          k: _device_payload(k, v)
          for k, v in devices.items()
        },
        "trails": trails,
        "routes": [_route_payload(r) for r in routes.values()],
        "history_edges":
          [_history_edge_payload(e) for e in route_history_edges.values()],
        "history_window_seconds": int(max(0, ROUTE_HISTORY_HOURS * 3600)),
        "heat": _serialize_heat_events(),
        "update": git_update_info,
        "mqtt_presence": _mqtt_presence_summary(),
      }
    )
  )

  try:
    while True:
      await ws.receive_text()
  except WebSocketDisconnect:
    pass
  except RuntimeError:
    pass
  finally:
    clients.discard(ws)
