import asyncio
import base64
import json
import os
import re
import html
import math
import subprocess
import time
import urllib.parse
import urllib.request
from collections import deque
from dataclasses import dataclass, asdict
from typing import Any, Dict, Optional, Set, Tuple, List

import paho.mqtt.client as mqtt
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

# =========================
# Env / Config
# =========================
MQTT_HOST = os.getenv("MQTT_HOST", "localhost")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_USERNAME = os.getenv("MQTT_USERNAME", "")
MQTT_PASSWORD = os.getenv("MQTT_PASSWORD", "")

MQTT_TOPIC = os.getenv("MQTT_TOPIC", "meshcore/#")

MQTT_TLS = os.getenv("MQTT_TLS", "false").lower() == "true"
MQTT_TLS_INSECURE = os.getenv("MQTT_TLS_INSECURE", "false").lower() == "true"
MQTT_CA_CERT = os.getenv("MQTT_CA_CERT", "")  # optional path to CA bundle

MQTT_TRANSPORT = os.getenv("MQTT_TRANSPORT", "tcp").strip().lower()  # tcp | websockets
MQTT_WS_PATH = os.getenv("MQTT_WS_PATH", "/mqtt")  # often "/" or "/mqtt"

MQTT_CLIENT_ID = os.getenv("MQTT_CLIENT_ID", "")

DEVICE_TTL_SECONDS = int(os.getenv("DEVICE_TTL_SECONDS", "300"))
TRAIL_LEN = int(os.getenv("TRAIL_LEN", "30"))
ROUTE_TTL_SECONDS = int(os.getenv("ROUTE_TTL_SECONDS", "120"))
ROUTE_PAYLOAD_TYPES = os.getenv("ROUTE_PAYLOAD_TYPES", "8,9,2,5,4")
MESSAGE_ORIGIN_TTL_SECONDS = int(os.getenv("MESSAGE_ORIGIN_TTL_SECONDS", "300"))
HEAT_TTL_SECONDS = int(os.getenv("HEAT_TTL_SECONDS", "600"))

DEBUG_PAYLOAD = os.getenv("DEBUG_PAYLOAD", "false").lower() == "true"
DEBUG_PAYLOAD_MAX = int(os.getenv("DEBUG_PAYLOAD_MAX", "400"))

DECODE_WITH_NODE = os.getenv("DECODE_WITH_NODE", "true").lower() == "true"
NODE_DECODE_TIMEOUT_SECONDS = float(os.getenv("NODE_DECODE_TIMEOUT_SECONDS", "2.0"))
DEBUG_LAST_MAX = int(os.getenv("DEBUG_LAST_MAX", "50"))
DEBUG_STATUS_MAX = int(os.getenv("DEBUG_STATUS_MAX", "50"))
PAYLOAD_PREVIEW_MAX = int(os.getenv("PAYLOAD_PREVIEW_MAX", "800"))
DIRECT_COORDS_MODE = os.getenv("DIRECT_COORDS_MODE", "topic").strip().lower()
DIRECT_COORDS_TOPIC_REGEX = os.getenv("DIRECT_COORDS_TOPIC_REGEX", r"(position|location|gps|coords)")
DIRECT_COORDS_ALLOW_ZERO = os.getenv("DIRECT_COORDS_ALLOW_ZERO", "false").lower() == "true"
STATE_DIR = os.getenv("STATE_DIR", "/data")
STATE_FILE = os.getenv("STATE_FILE", os.path.join(STATE_DIR, "state.json"))
DEVICE_ROLES_FILE = os.getenv("DEVICE_ROLES_FILE", os.path.join(STATE_DIR, "device_roles.json"))
STATE_SAVE_INTERVAL = float(os.getenv("STATE_SAVE_INTERVAL", "5"))

SITE_TITLE = os.getenv("SITE_TITLE", "Greater Boston Mesh Live Map")
SITE_DESCRIPTION = os.getenv("SITE_DESCRIPTION", "Live view of Greater Boston Mesh nodes, message routes, and advert paths.")
SITE_OG_IMAGE = os.getenv("SITE_OG_IMAGE", "")
SITE_URL = os.getenv("SITE_URL", "/")
SITE_ICON = os.getenv("SITE_ICON", "/static/logo.png")
SITE_FEED_NOTE = os.getenv("SITE_FEED_NOTE", "Feed: Boston MQTT.")
try:
  MAP_START_LAT = float(os.getenv("MAP_START_LAT", "42.3601"))
except ValueError:
  MAP_START_LAT = 42.3601
try:
  MAP_START_LON = float(os.getenv("MAP_START_LON", "-71.1500"))
except ValueError:
  MAP_START_LON = -71.1500
try:
  MAP_START_ZOOM = float(os.getenv("MAP_START_ZOOM", "10"))
except ValueError:
  MAP_START_ZOOM = 10

LOS_ELEVATION_URL = os.getenv("LOS_ELEVATION_URL", "https://api.opentopodata.org/v1/srtm90m")
LOS_SAMPLE_MIN = int(os.getenv("LOS_SAMPLE_MIN", "10"))
LOS_SAMPLE_MAX = int(os.getenv("LOS_SAMPLE_MAX", "80"))
LOS_SAMPLE_STEP_METERS = int(os.getenv("LOS_SAMPLE_STEP_METERS", "250"))
ELEVATION_CACHE_TTL = int(os.getenv("ELEVATION_CACHE_TTL", "21600"))
LOS_PEAKS_MAX = int(os.getenv("LOS_PEAKS_MAX", "4"))

APP_DIR = os.path.dirname(os.path.abspath(__file__))
NODE_SCRIPT_PATH = os.path.join(APP_DIR, "meshcore_decode.mjs")

# =========================
# App / State
# =========================
app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")

mqtt_client: Optional[mqtt.Client] = None
clients: Set[WebSocket] = set()
update_queue: asyncio.Queue[Dict[str, Any]] = asyncio.Queue()

# Stats + presence (even if no coords yet)
stats = {
  "received_total": 0,
  "parsed_total": 0,
  "unparsed_total": 0,
  "last_rx_ts": None,
  "last_rx_topic": None,
  "last_parsed_ts": None,
  "last_parsed_topic": None,
}
result_counts: Dict[str, int] = {}
seen_devices: Dict[str, float] = {}  # device_id -> last_seen_ts
topic_counts: Dict[str, int] = {}    # topic -> count

debug_last = deque(maxlen=DEBUG_LAST_MAX)
status_last = deque(maxlen=DEBUG_STATUS_MAX)

_node_ready_once = False
_node_unavailable_once = False


@dataclass
class DeviceState:
  device_id: str
  lat: float
  lon: float
  ts: float
  heading: Optional[float] = None
  speed: Optional[float] = None
  rssi: Optional[float] = None
  snr: Optional[float] = None
  name: Optional[str] = None
  role: Optional[str] = None
  raw_topic: Optional[str] = None


devices: Dict[str, DeviceState] = {}
trails: Dict[str, list] = {}
routes: Dict[str, Dict[str, Any]] = {}
heat_events: List[Dict[str, float]] = []
node_hash_to_device: Dict[str, str] = {}
elevation_cache: Dict[str, Tuple[float, float]] = {}
device_names: Dict[str, str] = {}
message_origins: Dict[str, Dict[str, Any]] = {}
device_roles: Dict[str, str] = {}
device_role_sources: Dict[str, str] = {}
state_dirty = False

# =========================
# Helpers: coordinate hunting
# =========================
LATLON_KEYS_LAT = ("lat", "latitude")
LATLON_KEYS_LON = ("lon", "lng", "longitude")

# e.g. "lat 42.3601 lon -71.0589" or "lat=42.36 lon=-71.05"
RE_LAT_LON = re.compile(
  r"\blat(?:itude)?\b\s*[:=]?\s*(-?\d+(?:\.\d+)?)\s*[, ]+\s*\b(?:lon|lng|longitude)\b\s*[:=]?\s*(-?\d+(?:\.\d+)?)",
  re.IGNORECASE,
)

# e.g. "42.3601 -71.0589" (two floats)
RE_TWO_FLOATS = re.compile(
  r"(-?\d{1,2}\.\d+)\s*[,\s]+\s*(-?\d{1,3}\.\d+)"
)

BASE64_LIKE = re.compile(r"^[A-Za-z0-9+/]+={0,2}$")
NODE_HASH_RE = re.compile(r"^[0-9a-fA-F]{2}$")

ROUTE_PAYLOAD_TYPES_SET: Set[int] = set()
for _part in ROUTE_PAYLOAD_TYPES.split(","):
  _part = _part.strip()
  if not _part:
    continue
  try:
    ROUTE_PAYLOAD_TYPES_SET.add(int(_part))
  except ValueError:
    pass

LIKELY_PACKET_KEYS = (
  "hex", "raw", "packet", "packet_hex", "frame", "data", "payload",
  "mesh_packet", "meshcore_packet", "rx_packet", "bytes", "packet_bytes",
)

try:
  DIRECT_COORDS_TOPIC_RE = re.compile(DIRECT_COORDS_TOPIC_REGEX, re.IGNORECASE)
except re.error:
  DIRECT_COORDS_TOPIC_RE = None


def _valid_lat_lon(lat: float, lon: float) -> bool:
  return -90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0


def _normalize_lat_lon(lat: Any, lon: Any) -> Optional[Tuple[float, float]]:
  try:
    latf = float(lat)
    lonf = float(lon)
  except Exception:
    return None

  if _valid_lat_lon(latf, lonf):
    return latf, lonf

  for scale in (1e7, 1e6, 1e5, 1e4):
    lat2 = latf / scale
    lon2 = lonf / scale
    if _valid_lat_lon(lat2, lon2):
      return lat2, lon2

  return None


def _find_lat_lon_in_json(obj: Any) -> Optional[Tuple[float, float]]:
  """
  Recursively walk JSON objects/lists looking for lat/lon keys.
  """
  if isinstance(obj, dict):
    lat = None
    lon = None
    for k in LATLON_KEYS_LAT:
      if k in obj:
        lat = obj.get(k)
        break
    for k in LATLON_KEYS_LON:
      if k in obj:
        lon = obj.get(k)
        break
    if lat is not None and lon is not None:
      normalized = _normalize_lat_lon(lat, lon)
      if normalized:
        return normalized

    for v in obj.values():
      found = _find_lat_lon_in_json(v)
      if found:
        return found

  elif isinstance(obj, list):
    for v in obj:
      found = _find_lat_lon_in_json(v)
      if found:
        return found

  return None


def _strings_from_json(obj: Any) -> List[str]:
  """
  Collect all string leaves from a JSON-like structure.
  """
  out: List[str] = []
  if isinstance(obj, str):
    out.append(obj)
  elif isinstance(obj, dict):
    for v in obj.values():
      out.extend(_strings_from_json(v))
  elif isinstance(obj, list):
    for v in obj:
      out.extend(_strings_from_json(v))
  return out


def _find_lat_lon_in_text(text: str) -> Optional[Tuple[float, float]]:
  """
  Try to extract coordinates from a text blob.
  """
  m = RE_LAT_LON.search(text)
  if m:
    normalized = _normalize_lat_lon(m.group(1), m.group(2))
    if normalized:
      return normalized

  for m2 in RE_TWO_FLOATS.finditer(text):
    normalized = _normalize_lat_lon(m2.group(1), m2.group(2))
    if normalized:
      return normalized

  return None


def _maybe_base64_decode_to_text(s: str) -> Optional[str]:
  """
  Best-effort: if a string looks base64-ish, try decoding to UTF-8-ish text.
  """
  s_stripped = s.strip()
  if len(s_stripped) < 24:
    return None
  if not BASE64_LIKE.match(s_stripped):
    return None

  try:
    raw = base64.b64decode(s_stripped, validate=False)
    return raw.decode("utf-8", errors="ignore")
  except Exception:
    return None


def _looks_like_hex(s: str) -> bool:
  s2 = s.strip()
  if len(s2) < 20:
    return False
  if len(s2) % 2 != 0:
    return False
  return bool(re.fullmatch(r"[0-9a-fA-F]+", s2))


def _try_base64_to_hex(s: str) -> Optional[str]:
  s2 = s.strip()
  if len(s2) < 24:
    return None
  if not any(c in s2 for c in "+/="):
    return None
  try:
    raw = base64.b64decode(s2, validate=False)
    if len(raw) < 10:
      return None
    return raw.hex()
  except Exception:
    return None


def _is_probably_binary(data: bytes) -> bool:
  if not data:
    return False
  printable = 0
  for b in data[:200]:
    if 32 <= b <= 126 or b in (9, 10, 13):
      printable += 1
  return printable / min(len(data), 200) < 0.6


def _safe_preview(data: bytes) -> str:
  try:
    text = data.decode("utf-8", errors="replace")
  except Exception:
    text = repr(data)
  if len(text) > PAYLOAD_PREVIEW_MAX:
    return text[:PAYLOAD_PREVIEW_MAX] + "..."
  return text


def _normalize_node_hash(value: Any) -> Optional[str]:
  if value is None:
    return None
  if isinstance(value, int):
    return f"{value:02X}"
  s = str(value).strip()
  if s.lower().startswith("0x"):
    s = s[2:]
  if len(s) == 1:
    s = f"0{s}"
  if len(s) != 2 or not NODE_HASH_RE.match(s):
    return None
  return s.upper()


def _node_hash_from_device_id(device_id: str) -> Optional[str]:
  if not device_id or len(device_id) < 2:
    return None
  return _normalize_node_hash(device_id[:2])


def _route_points_from_hashes(path_hashes: List[Any], receiver_id: Optional[str]) -> Tuple[Optional[List[List[float]]], List[str]]:
  points: List[List[float]] = []
  used_hashes: List[str] = []

  for raw in path_hashes:
    key = _normalize_node_hash(raw)
    if not key:
      continue
    device_id = node_hash_to_device.get(key)
    if not device_id:
      continue
    state = devices.get(device_id)
    if not state:
      continue
    point = [state.lat, state.lon]
    if points and point == points[-1]:
      continue
    points.append(point)
    used_hashes.append(key)

  if len(points) < 2:
    if points and receiver_id:
      receiver_state = devices.get(receiver_id)
      if receiver_state:
        receiver_point = [receiver_state.lat, receiver_state.lon]
        if receiver_point != points[0]:
          points.append(receiver_point)
          return points, used_hashes
    return None, used_hashes

  return points, used_hashes


def _route_points_from_device_ids(origin_id: Optional[str], receiver_id: Optional[str]) -> Optional[List[List[float]]]:
  if not origin_id or not receiver_id or origin_id == receiver_id:
    return None
  origin_state = devices.get(origin_id)
  receiver_state = devices.get(receiver_id)
  if not origin_state or not receiver_state:
    return None
  points = [
    [origin_state.lat, origin_state.lon],
    [receiver_state.lat, receiver_state.lon],
  ]
  if points[0] == points[1]:
    return None
  return points


def _append_heat_points(points: List[List[float]], ts: float, payload_type: Optional[int]) -> None:
  if HEAT_TTL_SECONDS <= 0:
    return
  if payload_type == 4:
    return
  for point in points:
    heat_events.append({
      "lat": float(point[0]),
      "lon": float(point[1]),
      "ts": float(ts),
      "weight": 0.7,
    })


def _serialize_heat_events() -> List[List[float]]:
  if HEAT_TTL_SECONDS <= 0:
    return []
  cutoff = time.time() - HEAT_TTL_SECONDS
  return [
    [entry.get("lat"), entry.get("lon"), entry.get("ts"), entry.get("weight", 0.7)]
    for entry in heat_events
    if entry.get("ts", 0) >= cutoff
  ]


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
  radius = 6371000.0
  phi1 = math.radians(lat1)
  phi2 = math.radians(lat2)
  dphi = math.radians(lat2 - lat1)
  dlambda = math.radians(lon2 - lon1)
  a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
  c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
  return radius * c


def _elevation_cache_key(lat: float, lon: float) -> str:
  return f"{lat:.5f},{lon:.5f}"


def _chunked(seq: List[Any], size: int) -> List[List[Any]]:
  return [seq[i:i + size] for i in range(0, len(seq), size)]


def _fetch_elevations(points: List[Tuple[float, float, float]]) -> Tuple[Optional[List[float]], Optional[str]]:
  now = time.time()
  results: List[Optional[float]] = [None] * len(points)
  missing: List[Tuple[int, float, float, str]] = []

  for idx, (lat, lon, _) in enumerate(points):
    key = _elevation_cache_key(lat, lon)
    cached = elevation_cache.get(key)
    if cached and now - cached[1] <= ELEVATION_CACHE_TTL:
      results[idx] = cached[0]
    else:
      missing.append((idx, lat, lon, key))

  if not missing:
    if any(val is None for val in results):
      return None, "elevation_fetch_failed: incomplete_cache"
    return [float(val) for val in results], None

  for chunk in _chunked(missing, 100):
    locations = "|".join(f"{lat},{lon}" for _, lat, lon, _ in chunk)
    query = urllib.parse.urlencode({"locations": locations})
    url = f"{LOS_ELEVATION_URL}?{query}"
    try:
      with urllib.request.urlopen(url, timeout=6) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
      return None, f"elevation_fetch_failed: {exc}"

    if payload.get("status") not in (None, "OK"):
      return None, f"elevation_fetch_failed: {payload.get('status')}"

    elev_results = payload.get("results", [])
    if len(elev_results) != len(chunk):
      return None, "elevation_fetch_failed: unexpected_result_length"

    for (idx, _, _, key), entry in zip(chunk, elev_results):
      elev = entry.get("elevation")
      if elev is None:
        return None, "elevation_fetch_failed: missing_elevation"
      elevation_cache[key] = (float(elev), now)
      results[idx] = float(elev)

  if any(val is None for val in results):
    return None, "elevation_fetch_failed: incomplete_results"
  return [float(val) for val in results], None


def _sample_los_points(lat1: float, lon1: float, lat2: float, lon2: float) -> List[Tuple[float, float, float]]:
  distance_m = _haversine_m(lat1, lon1, lat2, lon2)
  if distance_m <= 0:
    return [(lat1, lon1, 0.0), (lat2, lon2, 1.0)]

  samples = int(distance_m / max(1.0, LOS_SAMPLE_STEP_METERS)) + 1
  samples = max(LOS_SAMPLE_MIN, min(LOS_SAMPLE_MAX, samples))
  if samples < 2:
    samples = 2

  points: List[Tuple[float, float, float]] = []
  for i in range(samples):
    t = i / (samples - 1)
    lat = lat1 + (lat2 - lat1) * t
    lon = lon1 + (lon2 - lon1) * t
    points.append((lat, lon, t))
  return points


def _los_max_obstruction(points: List[Tuple[float, float, float]], elevations: List[float], start_idx: int, end_idx: int) -> float:
  if end_idx <= start_idx + 1:
    return 0.0
  start_t = points[start_idx][2]
  end_t = points[end_idx][2]
  if end_t <= start_t:
    return 0.0
  start_elev = elevations[start_idx]
  end_elev = elevations[end_idx]
  max_obstruction = 0.0
  for idx in range(start_idx + 1, end_idx):
    frac = (points[idx][2] - start_t) / (end_t - start_t)
    line_elev = start_elev + (end_elev - start_elev) * frac
    clearance = elevations[idx] - line_elev
    if clearance > max_obstruction:
      max_obstruction = clearance
  return max_obstruction


def _find_los_suggestion(points: List[Tuple[float, float, float]], elevations: List[float]) -> Optional[Dict[str, Any]]:
  if len(points) < 3:
    return None
  best_idx = None
  best_score = None
  best_clear = False
  for idx in range(1, len(points) - 1):
    obst_a = _los_max_obstruction(points, elevations, 0, idx)
    obst_b = _los_max_obstruction(points, elevations, idx, len(points) - 1)
    score = max(obst_a, obst_b)
    clear = score <= 0.0
    if clear and not best_clear:
      best_idx = idx
      best_score = score
      best_clear = True
    elif clear and best_clear:
      if elevations[idx] > elevations[best_idx]:
        best_idx = idx
        best_score = score
    elif not best_clear:
      if best_score is None or score < best_score:
        best_idx = idx
        best_score = score
  if best_idx is None:
    return None
  return {
    "lat": round(points[best_idx][0], 6),
    "lon": round(points[best_idx][1], 6),
    "elevation_m": round(float(elevations[best_idx]), 2),
    "clear": best_clear,
    "max_obstruction_m": round(float(best_score), 2) if best_score is not None else None,
  }


def _find_los_peaks(
  points: List[Tuple[float, float, float]],
  elevations: List[float],
  distance_m: float,
) -> List[Dict[str, Any]]:
  if len(points) < 3:
    return []

  peak_indices = []
  for idx in range(1, len(elevations) - 1):
    elev = elevations[idx]
    if elev >= elevations[idx - 1] and elev >= elevations[idx + 1]:
      peak_indices.append(idx)

  if not peak_indices:
    try:
      peak_indices = [max(range(1, len(elevations) - 1), key=lambda i: elevations[i])]
    except ValueError:
      return []

  peak_indices = sorted(peak_indices, key=lambda i: elevations[i], reverse=True)[:LOS_PEAKS_MAX]
  peak_indices = sorted(peak_indices, key=lambda i: points[i][2])

  peaks = []
  for i, idx in enumerate(peak_indices, start=1):
    t = points[idx][2]
    peaks.append({
      "index": i,
      "lat": round(points[idx][0], 6),
      "lon": round(points[idx][1], 6),
      "elevation_m": round(float(elevations[idx]), 2),
      "distance_m": round(distance_m * t, 2),
    })
  return peaks


def _extract_device_name(obj: Any, topic: str) -> Optional[str]:
  if not isinstance(obj, dict):
    return None

  for key in (
    "name",
    "device_name",
    "deviceName",
    "node_name",
    "nodeName",
    "display_name",
    "displayName",
    "callsign",
    "label",
  ):
    value = obj.get(key)
    if isinstance(value, str) and value.strip():
      return value.strip()

  if topic.endswith("/status"):
    origin = obj.get("origin")
    if isinstance(origin, str) and origin.strip():
      return origin.strip()

  return None


def _normalize_role(value: str) -> Optional[str]:
  s = value.strip().lower()
  if not s:
    return None
  if "repeater" in s or s in ("repeat", "relay"):
    return "repeater"
  if "companion" in s or "chat node" in s or "chatnode" in s or s == "chat":
    return "companion"
  if "room server" in s or "roomserver" in s or "room" in s:
    return "room"
  return None


def _extract_device_role(obj: Any, topic: str) -> Optional[str]:
  if not isinstance(obj, dict):
    return None

  for key in (
    "role",
    "device_role",
    "deviceRole",
    "node_role",
    "nodeRole",
    "node_type",
    "nodeType",
    "device_type",
    "deviceType",
    "class",
    "profile",
  ):
    value = obj.get(key)
    if isinstance(value, str):
      role = _normalize_role(value)
      if role:
        return role

  return None


def _apply_meta_role(debug: Dict[str, Any], meta: Optional[Dict[str, Any]]) -> None:
  if debug.get("device_role"):
    return
  if not isinstance(meta, dict):
    return
  role_value = meta.get("role") or meta.get("deviceRoleName")
  if role_value is None:
    device_role_code = meta.get("deviceRole")
    if isinstance(device_role_code, int):
      if device_role_code == 2:
        role_value = "repeater"
      elif device_role_code == 3:
        role_value = "room"
      elif device_role_code == 1:
        role_value = "companion"
  if isinstance(role_value, str):
    normalized = _normalize_role(role_value)
    if normalized:
      debug["device_role"] = normalized


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


def _load_state() -> None:
  global devices, trails, seen_devices, node_hash_to_device, device_names, device_roles, device_role_sources

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
  for key, value in raw_devices.items():
    if not isinstance(value, dict):
      continue
    try:
      loaded_devices[key] = DeviceState(**value)
    except Exception:
      continue

  devices = loaded_devices
  trails = data.get("trails") or {}
  seen_devices = data.get("seen_devices") or {}
  raw_names = data.get("device_names") or {}
  if isinstance(raw_names, dict):
    device_names = {str(k): str(v) for k, v in raw_names.items() if str(v).strip()}
  else:
    device_names = {}
  raw_role_sources = data.get("device_role_sources") or {}
  if isinstance(raw_role_sources, dict):
    device_role_sources = {str(k): str(v) for k, v in raw_role_sources.items() if str(v).strip()}
  else:
    device_role_sources = {}
  raw_roles = data.get("device_roles") or {}
  device_roles = {}
  if isinstance(raw_roles, dict):
    for key, value in raw_roles.items():
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
  node_hash_to_device = {}
  for device_id in devices.keys():
    node_hash = _node_hash_from_device_id(device_id)
    if node_hash:
      node_hash_to_device[node_hash] = device_id

  for device_id, state in devices.items():
    if not state.name and device_id in device_names:
      state.name = device_names[device_id]
    role_value = device_roles.get(device_id)
    state.role = role_value if role_value else None


async def _state_saver() -> None:
  global state_dirty
  while True:
    if state_dirty:
      try:
        os.makedirs(STATE_DIR, exist_ok=True)
        tmp_path = f"{STATE_FILE}.tmp"
        with open(tmp_path, "w", encoding="utf-8") as handle:
          json.dump(_serialize_state(), handle)
        os.replace(tmp_path, STATE_FILE)
        state_dirty = False
      except Exception as exc:
        print(f"[state] failed to save {STATE_FILE}: {exc}")
    await asyncio.sleep(max(1.0, STATE_SAVE_INTERVAL))


def _coords_are_zero(lat: float, lon: float) -> bool:
  return abs(lat) < 1e-6 and abs(lon) < 1e-6


def _has_location_hints(obj: Any) -> bool:
  if isinstance(obj, dict):
    for k, v in obj.items():
      key = str(k).lower()
      if key in ("location", "gps", "position", "coords", "coordinate", "geo", "geolocation", "latlon"):
        return True
      if isinstance(v, (dict, list)) and _has_location_hints(v):
        return True
  elif isinstance(obj, list):
    for v in obj:
      if _has_location_hints(v):
        return True
  return False


def _direct_coords_allowed(topic: str, obj: Any) -> bool:
  if DIRECT_COORDS_MODE == "off":
    return False
  if DIRECT_COORDS_MODE == "any":
    return True
  if DIRECT_COORDS_MODE in ("topic", "strict"):
    if DIRECT_COORDS_TOPIC_RE and DIRECT_COORDS_TOPIC_RE.search(topic):
      return True
    if DIRECT_COORDS_MODE == "topic":
      return False
    return _has_location_hints(obj)
  return True


# =========================
# MeshCore decoder via Node
# =========================

def _ensure_node_decoder() -> bool:
  global _node_ready_once, _node_unavailable_once

  if not DECODE_WITH_NODE:
    return False
  if _node_ready_once:
    return True
  if _node_unavailable_once:
    return False

  try:
    subprocess.run(["node", "-v"], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
  except Exception:
    _node_unavailable_once = True
    print("[decode] node not found in container")
    return False

  try:
    subprocess.run(
      ["node", "--input-type=module", "-e", "import('@michaelhart/meshcore-decoder')"],
      check=True,
      stdout=subprocess.DEVNULL,
      stderr=subprocess.DEVNULL,
      cwd=APP_DIR,
    )
  except Exception:
    _node_unavailable_once = True
    print("[decode] @michaelhart/meshcore-decoder not available")
    return False

  script = """#!/usr/bin/env node
import { MeshCoreDecoder, getDeviceRoleName } from '@michaelhart/meshcore-decoder';

const hex = (process.argv[2] || '').trim();

function pickLocation(decodedPacket) {
  const payloadDecoded = decodedPacket?.payload?.decoded ?? null;
  const payloadRoot = decodedPacket?.payload ?? null;
  const appData = payloadDecoded?.appData ?? payloadDecoded?.appdata ?? payloadRoot?.appData ?? payloadRoot?.appdata ?? null;
  const loc = appData?.location ?? payloadDecoded?.location ?? payloadRoot?.location ?? null;
  const lat = loc?.latitude ?? loc?.lat ?? null;
  const lon = loc?.longitude ?? loc?.lon ?? null;
  const name = appData?.name ?? payloadDecoded?.name ?? payloadRoot?.name ?? null;
  const pubkey =
    payloadDecoded?.publicKey ??
    payloadDecoded?.publickey ??
    payloadRoot?.publicKey ??
    payloadRoot?.publickey ??
    decodedPacket?.publicKey ??
    decodedPacket?.publickey ??
    null;
  return { lat, lon, name, pubkey };
}

function pickRole(decodedPacket) {
  const payloadDecoded = decodedPacket?.payload?.decoded ?? null;
  const payloadRoot = decodedPacket?.payload ?? null;
  const appData = payloadDecoded?.appData ?? payloadDecoded?.appdata ?? payloadRoot?.appData ?? payloadRoot?.appdata ?? null;
  const candidates = [
    appData?.role,
    appData?.deviceRole,
    appData?.nodeRole,
    appData?.deviceType,
    appData?.nodeType,
    appData?.class,
    appData?.profile,
    payloadDecoded?.role,
    payloadDecoded?.deviceRole,
    payloadDecoded?.nodeRole,
    payloadDecoded?.deviceType,
    payloadDecoded?.nodeType,
    payloadDecoded?.class,
    payloadDecoded?.profile,
    payloadRoot?.role,
    payloadRoot?.deviceRole,
    payloadRoot?.nodeRole,
    payloadRoot?.deviceType,
    payloadRoot?.nodeType,
    payloadRoot?.class,
    payloadRoot?.profile,
  ];
  for (const value of candidates) {
    if (typeof value === 'string' && value.trim()) return value.trim();
  }
  return null;
}

try {
  const decoded = MeshCoreDecoder.decode(hex);
  const loc = pickLocation(decoded);
  const payloadDecoded = decoded?.payload?.decoded ?? decoded?.payload ?? null;
  const payloadRoot = decoded?.payload ?? null;
  const appData = payloadDecoded?.appData ?? payloadDecoded?.appdata ?? payloadRoot?.appData ?? payloadRoot?.appdata ?? null;
  const deviceRole = appData?.deviceRole ?? payloadDecoded?.deviceRole ?? payloadRoot?.deviceRole ?? null;
  const deviceRoleName = typeof deviceRole === 'number' ? getDeviceRoleName(deviceRole) : null;
  const role = pickRole(decoded) || deviceRoleName;
  const payloadKeys = payloadDecoded && typeof payloadDecoded === 'object' ? Object.keys(payloadDecoded) : null;
  const appDataKeys = appData && typeof appData === 'object' ? Object.keys(appData) : null;
  const pathHashes = payloadDecoded?.pathHashes ?? null;
  const snrValues = payloadDecoded?.snrValues ?? null;
  const path = decoded?.path ?? null;
  const pathLength = decoded?.pathLength ?? null;
  const out = {
    ok: true,
    payloadType: decoded?.payloadType ?? null,
    routeType: decoded?.routeType ?? null,
    messageHash: decoded?.messageHash ?? null,
    location: loc,
    role,
    deviceRole,
    deviceRoleName,
    payloadKeys,
    appDataKeys,
    pathHashes,
    snrValues,
    path,
    pathLength,
  };
  console.log(JSON.stringify(out));
} catch (e) {
  console.log(JSON.stringify({ ok: false, error: String(e) }));
}
"""

  try:
    with open(NODE_SCRIPT_PATH, "w", encoding="utf-8") as handle:
      handle.write(script)
    os.chmod(NODE_SCRIPT_PATH, 0o755)
  except Exception as exc:
    _node_unavailable_once = True
    print(f"[decode] failed writing node helper: {exc}")
    return False

  _node_ready_once = True
  print("[decode] node decoder ready")
  return True


def _decode_meshcore_hex(hex_str: str) -> Tuple[Optional[float], Optional[float], Optional[str], Optional[str], Dict[str, Any]]:
  if not _ensure_node_decoder():
    return (None, None, None, None, {"ok": False, "error": "node_decoder_unavailable"})

  try:
    proc = subprocess.run(
      ["node", NODE_SCRIPT_PATH, hex_str],
      capture_output=True,
      text=True,
      timeout=NODE_DECODE_TIMEOUT_SECONDS,
      cwd=APP_DIR,
    )
  except Exception as exc:
    return (None, None, None, None, {"ok": False, "error": str(exc)})

  out = (proc.stdout or "").strip()
  if not out:
    return (None, None, None, None, {"ok": False, "error": "empty_decoder_output"})

  try:
    data = json.loads(out)
  except Exception:
    return (None, None, None, None, {"ok": False, "error": "decoder_output_not_json", "output": out})

  if not data.get("ok"):
    return (None, None, None, None, {"ok": False, **data})

  loc = data.get("location") or {}
  lat = loc.get("lat")
  lon = loc.get("lon")
  name = loc.get("name")
  pubkey = loc.get("pubkey")

  normalized = None
  if lat is not None and lon is not None:
    normalized = _normalize_lat_lon(lat, lon)

  if normalized:
    return (normalized[0], normalized[1], pubkey, name, {"ok": True, **data})

  return (None, None, pubkey, name, {"ok": True, **data, "note": "decoded_no_location"})


# =========================
# Parsing: MeshCore-ish payloads
# =========================

def _device_id_from_topic(topic: str) -> Optional[str]:
  parts = topic.split("/")
  if len(parts) >= 3 and parts[0] == "meshcore":
    return parts[2]
  return None


def _find_packet_blob(obj: Any, path: str = "root") -> Tuple[Optional[str], Optional[str], Optional[str]]:
  if isinstance(obj, str):
    if _looks_like_hex(obj):
      return (obj.strip(), path, "hex")
    b64hex = _try_base64_to_hex(obj)
    if b64hex:
      return (b64hex, path, "base64")
    return (None, None, None)

  if isinstance(obj, list):
    if obj and all(isinstance(x, int) for x in obj[: min(20, len(obj))]):
      try:
        raw = bytes(obj)
        if len(raw) >= 10:
          return (raw.hex(), path, "list[int]")
      except Exception:
        pass
    for idx, v in enumerate(obj):
      sub_path = f"{path}[{idx}]"
      hex_str, where, hint = _find_packet_blob(v, sub_path)
      if hex_str:
        return (hex_str, where, hint)
    return (None, None, None)

  if isinstance(obj, dict):
    keys = list(obj.keys())
    keys.sort(key=lambda k: 0 if k in LIKELY_PACKET_KEYS else 1)
    for k in keys:
      v = obj.get(k)
      sub_path = f"{path}.{k}"
      if isinstance(v, str):
        if _looks_like_hex(v):
          return (v.strip(), sub_path, "hex")
        b64hex = _try_base64_to_hex(v)
        if b64hex:
          return (b64hex, sub_path, "base64")
      if isinstance(v, list) and v and all(isinstance(x, int) for x in v[: min(20, len(v))]):
        try:
          raw = bytes(v)
          if len(raw) >= 10:
            return (raw.hex(), sub_path, "list[int]")
        except Exception:
          pass
      if isinstance(v, (dict, list)):
        hex_str, where, hint = _find_packet_blob(v, sub_path)
        if hex_str:
          return (hex_str, where, hint)

  return (None, None, None)


def _extract_device_id(obj: Any, topic: str, decoded_pubkey: Optional[str]) -> str:
  if decoded_pubkey:
    return str(decoded_pubkey)
  if isinstance(obj, dict):
    device_id = obj.get("device_id") or obj.get("id") or obj.get("from") or obj.get("origin_id")
    if device_id:
      return str(device_id)
    jwt = obj.get("jwt_payload")
    if isinstance(jwt, dict) and jwt.get("publickey"):
      return str(jwt.get("publickey"))
  return _device_id_from_topic(topic) or topic.split("/")[-1]


def _try_parse_payload(topic: str, payload_bytes: bytes) -> Tuple[Optional[Dict[str, Any]], Dict[str, Any]]:
  debug: Dict[str, Any] = {
    "result": "no_coords",
    "found_path": None,
    "found_hint": None,
    "decoder_meta": None,
    "json_keys": None,
    "parse_error": None,
    "origin_id": None,
    "device_name": None,
    "device_role": None,
    "decoded_pubkey": None,
    "packet_hash": None,
    "direction": None,
    "packet_type": None,
  }

  text = None
  try:
    text = payload_bytes.decode("utf-8", errors="strict").strip()
  except Exception:
    text = payload_bytes.decode("utf-8", errors="ignore").strip()

  obj = None
  if text and text.startswith("{") and text.endswith("}"):
    try:
      obj = json.loads(text)
      if isinstance(obj, dict):
        debug["json_keys"] = list(obj.keys())[:50]
        debug["origin_id"] = obj.get("origin_id") or obj.get("originId")
        debug["device_name"] = _extract_device_name(obj, topic)
        debug["device_role"] = _extract_device_role(obj, topic)
        debug["direction"] = obj.get("direction")
        debug["packet_hash"] = obj.get("hash") or obj.get("message_hash") or obj.get("messageHash")
        debug["packet_type"] = obj.get("packet_type") or obj.get("packetType") or obj.get("type")
    except Exception as exc:
      debug["parse_error"] = str(exc)

  if obj is not None:
    found = _find_lat_lon_in_json(obj)
    if found:
      if not _direct_coords_allowed(topic, obj):
        debug["result"] = "direct_blocked"
        return (None, debug)
      if not DIRECT_COORDS_ALLOW_ZERO and _coords_are_zero(found[0], found[1]):
        debug["result"] = "direct_zero_coords"
        return (None, debug)
      device_id = _extract_device_id(obj, topic, None)
      ts = time.time()
      if isinstance(obj, dict):
        tval = obj.get("ts") or obj.get("time") or obj.get("timestamp")
        if isinstance(tval, (int, float)):
          ts = float(tval)
      debug["result"] = "direct_json"
      return ({
        "device_id": device_id,
        "lat": found[0],
        "lon": found[1],
        "ts": ts,
        "heading": obj.get("heading") if isinstance(obj, dict) else None,
        "speed": obj.get("speed") if isinstance(obj, dict) else None,
        "rssi": obj.get("rssi") if isinstance(obj, dict) else None,
        "snr": obj.get("snr") if isinstance(obj, dict) else None,
        "role": debug.get("device_role"),
      }, debug)

    for s in _strings_from_json(obj):
      got = _find_lat_lon_in_text(s)
      if got:
        if not _direct_coords_allowed(topic, obj):
          debug["result"] = "direct_blocked"
          return (None, debug)
        if not DIRECT_COORDS_ALLOW_ZERO and _coords_are_zero(got[0], got[1]):
          debug["result"] = "direct_zero_coords"
          return (None, debug)
        device_id = _extract_device_id(obj, topic, None)
        debug["result"] = "direct_text_json"
        return ({
          "device_id": device_id,
          "lat": got[0],
          "lon": got[1],
          "ts": time.time(),
          "role": debug.get("device_role"),
        }, debug)

      decoded = _maybe_base64_decode_to_text(s)
      if decoded:
        got2 = _find_lat_lon_in_text(decoded)
        if got2:
          if not _direct_coords_allowed(topic, obj):
            debug["result"] = "direct_blocked"
            return (None, debug)
          if not DIRECT_COORDS_ALLOW_ZERO and _coords_are_zero(got2[0], got2[1]):
            debug["result"] = "direct_zero_coords"
            return (None, debug)
          device_id = _extract_device_id(obj, topic, None)
          debug["result"] = "direct_text_json_base64"
          return ({
            "device_id": device_id,
            "lat": got2[0],
            "lon": got2[1],
            "ts": time.time(),
            "role": debug.get("device_role"),
          }, debug)

    hex_str, where, hint = _find_packet_blob(obj)
    debug["found_path"] = where
    debug["found_hint"] = hint
    if hex_str:
      lat, lon, decoded_pubkey, name, meta = _decode_meshcore_hex(hex_str)
      debug["decoded_pubkey"] = decoded_pubkey
      debug["decoder_meta"] = meta
      _apply_meta_role(debug, meta)
      if lat is not None and lon is not None:
        device_id = _extract_device_id(obj, topic, decoded_pubkey)
        debug["result"] = "decoded"
        return ({
          "device_id": device_id,
          "lat": lat,
          "lon": lon,
          "ts": time.time(),
          "rssi": obj.get("rssi") if isinstance(obj, dict) else None,
          "snr": obj.get("snr") if isinstance(obj, dict) else None,
          "name": name,
          "role": debug.get("device_role"),
        }, debug)
      debug["result"] = "decoded_no_location" if meta.get("ok") else "decode_failed"
      return (None, debug)

    debug["result"] = "json_no_packet_blob"
    return (None, debug)

  if text:
    got = _find_lat_lon_in_text(text)
    if got:
      if not _direct_coords_allowed(topic, None):
        debug["result"] = "direct_blocked"
        return (None, debug)
      if not DIRECT_COORDS_ALLOW_ZERO and _coords_are_zero(got[0], got[1]):
        debug["result"] = "direct_zero_coords"
        return (None, debug)
      debug["result"] = "direct_text"
      return ({
        "device_id": _extract_device_id(None, topic, None),
        "lat": got[0],
        "lon": got[1],
        "ts": time.time(),
        "role": debug.get("device_role"),
      }, debug)

    if _looks_like_hex(text):
      debug["found_path"] = "payload"
      debug["found_hint"] = "hex"
      lat, lon, decoded_pubkey, name, meta = _decode_meshcore_hex(text.strip())
      debug["decoded_pubkey"] = decoded_pubkey
      debug["decoder_meta"] = meta
      _apply_meta_role(debug, meta)
      if lat is not None and lon is not None:
        debug["result"] = "decoded"
        return ({
          "device_id": _extract_device_id(None, topic, decoded_pubkey),
          "lat": lat,
          "lon": lon,
          "ts": time.time(),
          "name": name,
          "role": debug.get("device_role"),
        }, debug)
      debug["result"] = "decoded_no_location" if meta.get("ok") else "decode_failed"
      return (None, debug)

    b64hex = _try_base64_to_hex(text)
    if b64hex:
      debug["found_path"] = "payload"
      debug["found_hint"] = "base64"
      lat, lon, decoded_pubkey, name, meta = _decode_meshcore_hex(b64hex)
      debug["decoded_pubkey"] = decoded_pubkey
      debug["decoder_meta"] = meta
      _apply_meta_role(debug, meta)
      if lat is not None and lon is not None:
        debug["result"] = "decoded"
        return ({
          "device_id": _extract_device_id(None, topic, decoded_pubkey),
          "lat": lat,
          "lon": lon,
          "ts": time.time(),
          "name": name,
          "role": debug.get("device_role"),
        }, debug)
      debug["result"] = "decoded_no_location" if meta.get("ok") else "decode_failed"
      return (None, debug)

  if _is_probably_binary(payload_bytes) and len(payload_bytes) >= 10:
    debug["found_path"] = "payload_bytes"
    debug["found_hint"] = "raw_bytes"
    lat, lon, decoded_pubkey, name, meta = _decode_meshcore_hex(payload_bytes.hex())
    debug["decoded_pubkey"] = decoded_pubkey
    debug["decoder_meta"] = meta
    _apply_meta_role(debug, meta)
    if lat is not None and lon is not None:
      debug["result"] = "decoded"
      return ({
        "device_id": _extract_device_id(None, topic, decoded_pubkey),
        "lat": lat,
        "lon": lon,
        "ts": time.time(),
        "name": name,
        "role": debug.get("device_role"),
      }, debug)
    debug["result"] = "decoded_no_location" if meta.get("ok") else "decode_failed"
    return (None, debug)

  return (None, debug)


# =========================
# MQTT Callbacks (Paho v2)
# =========================

def mqtt_on_connect(client, userdata, flags, reason_code, properties=None):
  print(f"[mqtt] connected reason_code={reason_code} subscribing topic={MQTT_TOPIC}")
  client.subscribe(MQTT_TOPIC, qos=0)


def mqtt_on_disconnect(client, userdata, reason_code, properties=None):
  print(f"[mqtt] disconnected reason_code={reason_code}")


def mqtt_on_message(client, userdata, msg: mqtt.MQTTMessage):
  global state_dirty
  stats["received_total"] += 1
  stats["last_rx_ts"] = time.time()
  stats["last_rx_topic"] = msg.topic
  topic_counts[msg.topic] = topic_counts.get(msg.topic, 0) + 1

  dev_guess = _device_id_from_topic(msg.topic)
  if dev_guess:
    seen_devices[dev_guess] = time.time()

  parsed, debug = _try_parse_payload(msg.topic, msg.payload)
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
      state_dirty = True
      state = devices.get(origin_id)
      if state:
        state.name = device_name
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
      state_dirty = True
      state = devices.get(role_target_id)
      if state:
        state.role = device_role
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
  global state_dirty
  while True:
    event = await update_queue.get()

    if isinstance(event, dict) and event.get("type") in ("device_name", "device_role"):
      device_id = event.get("device_id")
      state = devices.get(device_id)
      if state:
        if device_id in device_names:
          state.name = device_names[device_id]
        if device_id in device_roles:
          state.role = device_roles[device_id]
        payload = {"type": "update", "device": asdict(state), "trail": trails.get(device_id, [])}
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

      if not points:
        path_hashes = event.get("path_hashes") or []
        points, used_hashes = _route_points_from_hashes(list(path_hashes), event.get("receiver_id"))

      if not points and route_mode == "fanout":
        points = _route_points_from_device_ids(event.get("origin_id"), event.get("receiver_id"))

      # Fallback: if path hashes are missing/unknown, draw a direct link when possible.
      if not points:
        points = _route_points_from_device_ids(event.get("origin_id"), event.get("receiver_id"))
        if points:
          route_mode = "direct"

      if not points:
        continue

      route_id = event.get("route_id") or event.get("message_hash") or f"{event.get('origin_id', 'route')}-{int(event.get('ts', time.time()) * 1000)}"
      expires_at = (event.get("ts") or time.time()) + ROUTE_TTL_SECONDS
      route = {
        "id": route_id,
        "points": points,
        "hashes": used_hashes,
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

      payload = {"type": "route", "route": route}
      dead = []
      for ws in list(clients):
        try:
          await ws.send_text(json.dumps(payload))
        except Exception:
          dead.append(ws)
      for ws in dead:
        clients.discard(ws)
      continue

    upd = event.get("data") if isinstance(event, dict) and event.get("type") == "device" else event

    device_id = upd["device_id"]
    state = DeviceState(
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
    devices[device_id] = state
    seen_devices[device_id] = time.time()
    state_dirty = True
    node_hash = _node_hash_from_device_id(device_id)
    if node_hash:
      node_hash_to_device[node_hash] = device_id
    if state.name:
      device_names[device_id] = state.name
    if state.role:
      device_roles[device_id] = state.role

    trails.setdefault(device_id, [])
    trails[device_id].append([state.lat, state.lon, state.ts])
    if len(trails[device_id]) > TRAIL_LEN:
      trails[device_id] = trails[device_id][-TRAIL_LEN:]

    payload = {"type": "update", "device": asdict(state), "trail": trails[device_id]}

    dead = []
    for ws in list(clients):
      try:
        await ws.send_text(json.dumps(payload))
      except Exception:
        dead.append(ws)
    for ws in dead:
      clients.discard(ws)


async def reaper():
  global state_dirty, heat_events
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
          state_dirty = True

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

    if HEAT_TTL_SECONDS > 0 and heat_events:
      cutoff = now - HEAT_TTL_SECONDS
      heat_events = [entry for entry in heat_events if entry.get("ts", 0) >= cutoff]

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

  replacements = {
    "SITE_TITLE": SITE_TITLE,
    "SITE_DESCRIPTION": SITE_DESCRIPTION,
    "SITE_URL": SITE_URL,
    "SITE_ICON": SITE_ICON,
    "SITE_FEED_NOTE": SITE_FEED_NOTE,
    "MAP_START_LAT": MAP_START_LAT,
    "MAP_START_LON": MAP_START_LON,
    "MAP_START_ZOOM": MAP_START_ZOOM,
    "LOS_ELEVATION_URL": LOS_ELEVATION_URL,
    "LOS_SAMPLE_MIN": LOS_SAMPLE_MIN,
    "LOS_SAMPLE_MAX": LOS_SAMPLE_MAX,
    "LOS_SAMPLE_STEP_METERS": LOS_SAMPLE_STEP_METERS,
    "LOS_PEAKS_MAX": LOS_PEAKS_MAX,
  }
  for key, value in replacements.items():
    safe_value = html.escape(str(value), quote=True)
    content = content.replace(f"{{{{{key}}}}}", safe_value)

  return HTMLResponse(content)


@app.get("/snapshot")
def snapshot():
  return {
    "devices": {k: asdict(v) for k, v in devices.items()},
    "trails": trails,
    "routes": list(routes.values()),
    "heat": _serialize_heat_events(),
    "server_time": time.time(),
  }


@app.get("/stats")
def get_stats():
  top_topics = sorted(topic_counts.items(), key=lambda kv: kv[1], reverse=True)[:20]
  return {
    "stats": stats,
    "result_counts": result_counts,
    "mapped_devices": len(devices),
    "route_count": len(routes),
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


@app.get("/los")
def line_of_sight(lat1: float, lon1: float, lat2: float, lon2: float, profile: bool = False):
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
  profile = []
  if distance_m > 0:
    for (lat, lon, t), elev in zip(points, elevations):
      line_elev = start_elev + (end_elev - start_elev) * t
      profile.append([
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
    "profile": profile,
    "peaks": peaks,
  }
  if profile:
    response["profile"] = [
      [round(lat, 6), round(lon, 6), round(t, 4), round(float(elev), 2)]
      for (lat, lon, t), elev in zip(points, elevations)
    ]
  return response


@app.get("/debug/last")
def debug_last_entries():
  return {
    "count": len(debug_last),
    "items": list(reversed(list(debug_last))),
    "server_time": time.time(),
  }


@app.get("/debug/status")
def debug_status_entries():
  return {
    "count": len(status_last),
    "items": list(reversed(list(status_last))),
    "server_time": time.time(),
  }


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
  await ws.accept()
  clients.add(ws)

  await ws.send_text(json.dumps({
    "type": "snapshot",
    "devices": {k: asdict(v) for k, v in devices.items()},
    "trails": trails,
    "routes": list(routes.values()),
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
  _ensure_node_decoder()

  loop = asyncio.get_event_loop()
  transport = "websockets" if MQTT_TRANSPORT == "websockets" else "tcp"

  print(
    f"[mqtt] connecting host={MQTT_HOST} port={MQTT_PORT} tls={MQTT_TLS} transport={transport} ws_path={MQTT_WS_PATH if transport=='websockets' else '-'} topic={MQTT_TOPIC}"
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
