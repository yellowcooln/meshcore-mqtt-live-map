import base64
import json
import os
import re
import select
import subprocess
import threading
import time
from typing import Any, Dict, List, Optional, Set, Tuple

from config import (
  APP_DIR,
  CHANNEL_SECRETS_FILE,
  DECODE_WITH_NODE,
  DIRECT_COORDS_ALLOW_ZERO,
  DIRECT_COORDS_MODE,
  DIRECT_COORDS_TOPIC_REGEX,
  HEAT_TTL_SECONDS,
  MQTT_ONLINE_TOPIC_SUFFIXES,
  NODE_DECODE_TIMEOUT_SECONDS,
  NODE_SCRIPT_PATH,
  PAYLOAD_PREVIEW_MAX,
  ROUTE_PATH_MAX_LEN,
  ROUTE_MAX_HOP_DISTANCE,
  ROUTE_NEIGHBOR_DEBUG,
  ROUTE_INFRA_ONLY,
  ROUTE_ALLOW_AMBIGUOUS_ONE_BYTE_FALLBACK,
  ROUTE_PAYLOAD_TYPES,
)
from state import (
  devices,
  heat_events,
  node_hash_candidates,
  node_hash_collisions,
  node_hash_to_device,
  neighbor_edges,
  seen_devices,
)
from los import _haversine_m

LATLON_KEYS_LAT = ("lat", "latitude")
LATLON_KEYS_LON = ("lon", "lng", "longitude")

# e.g. "lat 42.3601 lon -71.0589" or "lat=42.36 lon=-71.05"
RE_LAT_LON = re.compile(
  r"\blat(?:itude)?\b\s*[:=]?\s*(-?\d+(?:\.\d+)?)\s*[, ]+\s*\b(?:lon|lng|longitude)\b\s*[:=]?\s*(-?\d+(?:\.\d+)?)",
  re.IGNORECASE,
)

# e.g. "42.3601 -71.0589" (two floats)
RE_TWO_FLOATS = re.compile(r"(-?\d{1,2}\.\d+)\s*[,\s]+\s*(-?\d{1,3}\.\d+)")

BASE64_LIKE = re.compile(r"^[A-Za-z0-9+/]+={0,2}$")
NODE_HASH_RE = re.compile(r"^[0-9a-fA-F]+$")
NODE_HASH_LENGTHS = (2, 4, 6)

_node_ready_once = False
_node_unavailable_once = False
_node_worker_proc: Optional[subprocess.Popen[str]] = None
_node_worker_lock = threading.Lock()
_channel_secrets_cache: List[str] = []
_channel_secrets_mtime: Optional[float] = None
_channel_secrets_path: Optional[str] = None


def _load_channel_secrets() -> List[str]:
  global _channel_secrets_cache, _channel_secrets_mtime, _channel_secrets_path
  path = (CHANNEL_SECRETS_FILE or "").strip()
  if not path or not os.path.exists(path):
    _channel_secrets_cache = []
    _channel_secrets_mtime = None
    _channel_secrets_path = path or None
    return []
  try:
    mtime = os.path.getmtime(path)
  except OSError:
    mtime = None
  if (
    _channel_secrets_path == path and
    _channel_secrets_mtime is not None and
    mtime == _channel_secrets_mtime
  ):
    return list(_channel_secrets_cache)
  try:
    with open(path, "r", encoding="utf-8") as handle:
      payload = json.load(handle)
  except Exception as exc:
    print(f"[decode] failed to load channel secrets file {path}: {exc}")
    return list(_channel_secrets_cache)

  values: List[Any]
  if isinstance(payload, dict):
    values = list(payload.values())
  elif isinstance(payload, list):
    values = list(payload)
  else:
    print(f"[decode] invalid channel secrets file format {path}")
    return []

  secrets: List[str] = []
  seen: Set[str] = set()
  for value in values:
    if not isinstance(value, str):
      continue
    normalized = value.strip()
    if not normalized:
      continue
    normalized = normalized.lower()
    if not re.fullmatch(r"[0-9a-f]{32}", normalized):
      continue
    if normalized in seen:
      continue
    seen.add(normalized)
    secrets.append(normalized)
  _channel_secrets_cache = list(secrets)
  _channel_secrets_mtime = mtime
  _channel_secrets_path = path
  return secrets

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
  "hex",
  "raw",
  "packet",
  "packet_hex",
  "frame",
  "data",
  "payload",
  "mesh_packet",
  "meshcore_packet",
  "rx_packet",
  "bytes",
  "packet_bytes",
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


def _coords_are_zero(lat: Any, lon: Any) -> bool:
  try:
    lat_val = float(lat)
    lon_val = float(lon)
  except (TypeError, ValueError):
    return False
  return abs(lat_val) < 1e-6 and abs(lon_val) < 1e-6


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
    if value < 0:
      return None
    if value <= 0xFF:
      return f"{value:02X}"
    if value <= 0xFFFF:
      return f"{value:04X}"
    if value <= 0xFFFFFF:
      return f"{value:06X}"
    return None
  if isinstance(value, (bytes, bytearray)):
    value = bytes(value).hex()
  s = str(value).strip()
  if s.lower().startswith("0x"):
    s = s[2:]
  s = s.replace(" ", "")
  if not s:
    return None
  if len(s) % 2 == 1:
    s = f"0{s}"
  if len(s) not in NODE_HASH_LENGTHS or not NODE_HASH_RE.match(s):
    return None
  return s.upper()


def _node_hashes_from_device_id(device_id: str) -> List[str]:
  if not device_id:
    return []
  value = str(device_id).strip()
  if value.lower().startswith("0x"):
    value = value[2:]
  value = value.replace(" ", "")
  if not value:
    return []
  out: List[str] = []
  for length in NODE_HASH_LENGTHS:
    if len(value) < length:
      continue
    key = _normalize_node_hash(value[:length])
    if key and key not in out:
      out.append(key)
  return out


def _rebuild_node_hash_map() -> None:
  candidates: Dict[str, List[str]] = {}
  collisions: Set[str] = set()
  device_ids = devices.copy()
  for device_id in device_ids:
    node_hashes = _node_hashes_from_device_id(device_id)
    if not node_hashes:
      continue
    for node_hash in node_hashes:
      bucket = candidates.setdefault(node_hash, [])
      if device_id not in bucket:
        bucket.append(device_id)
  mapping: Dict[str, str] = {}
  for node_hash, ids in candidates.items():
    if len(ids) == 1:
      mapping[node_hash] = ids[0]
    else:
      collisions.add(node_hash)
  node_hash_candidates.clear()
  node_hash_candidates.update(candidates)
  node_hash_collisions.clear()
  node_hash_collisions.update(collisions)
  node_hash_to_device.clear()
  node_hash_to_device.update(mapping)


def _choose_closest_device(
  node_hash: str, ref_lat: float, ref_lon: float, ts: float
) -> Optional[str]:
  """
    If we have multiple candidates for a hash, pick the one physically closest
    to (ref_lat, ref_lon). If only one, return it.
    """
  candidates = node_hash_candidates.get(node_hash)
  if not candidates:
    return None
  best_id = None
  best_dist = None

  for device_id in candidates:
    state = devices.get(device_id)
    if not state:
      continue

    # If infrastructure-only mode is active, only allow repeaters and rooms
    if ROUTE_INFRA_ONLY and (
      not state.role or state.role not in ("repeater", "room")
    ):
      continue

    # skip invalid coords
    if _coords_are_zero(state.lat, state.lon):
      continue

    # ensure we have floats for calculation
    try:
      s_lat = float(state.lat)
      s_lon = float(state.lon)
    except (TypeError, ValueError):
      continue

    dist = _haversine_m(ref_lat, ref_lon, s_lat, s_lon)

    # Explicitly ignore candidates that are too far, even if they are the "closest"
    # because a hop > ROUTE_MAX_HOP_DISTANCE is physically unlikely/bogus.
    if dist > (ROUTE_MAX_HOP_DISTANCE * 1000.0):
      continue

    if best_dist is None or dist < best_dist:
      best_dist = dist
      best_id = device_id

  return best_id


def _choose_device_for_hash(node_hash: str, ts: float) -> Optional[str]:
  candidates = node_hash_candidates.get(node_hash)
  if not candidates:
    return None
  best_id = None
  best_delta = None
  for device_id in candidates:
    state = devices.get(device_id)
    if not state:
      continue

    # If infrastructure-only mode is active, only allow repeaters and rooms
    if ROUTE_INFRA_ONLY and (
      not state.role or state.role not in ("repeater", "room")
    ):
      continue

    if _coords_are_zero(state.lat, state.lon):
      continue
    last_seen = seen_devices.get(device_id) or state.ts or 0.0
    try:
      delta = abs(float(last_seen) - float(ts))
    except (TypeError, ValueError):
      delta = None
    if delta is None:
      continue
    if best_delta is None or delta < best_delta:
      best_delta = delta
      best_id = device_id
  return best_id


def _choose_neighbor_device(
  prev_id: str,
  candidates: List[str],
  ref_lat: float,
  ref_lon: float,
  ts: float,
) -> Optional[str]:
  edges = neighbor_edges.get(prev_id) if prev_id else None
  if not edges:
    return None
  best_id = None
  best_score = None
  for device_id in candidates:
    edge = edges.get(device_id)
    if not edge:
      continue
    state = devices.get(device_id)
    if not state:
      continue

    # If infrastructure-only mode is active, only allow repeaters and rooms
    if ROUTE_INFRA_ONLY and (
      not state.role or state.role not in ("repeater", "room")
    ):
      continue

    if _coords_are_zero(state.lat, state.lon):
      continue

    try:
      s_lat = float(state.lat)
      s_lon = float(state.lon)
    except (TypeError, ValueError):
      continue

    dist = _haversine_m(ref_lat, ref_lon, s_lat, s_lon)
    if dist > (ROUTE_MAX_HOP_DISTANCE * 1000.0):
      continue

    manual = bool(edge.get("manual"))
    auto = bool(edge.get("auto"))
    count = int(edge.get("count", 0) or 0)
    last_seen = float(edge.get("last_seen", 0.0) or 0.0)
    priority = 2 if manual else (1 if auto else 0)
    score = (priority, count, last_seen)
    if best_score is None or score > best_score:
      best_score = score
      best_id = device_id

  return best_id


def _route_points_from_hashes(
  path_hashes: List[Any],
  origin_id: Optional[str],
  receiver_id: Optional[str],
  ts: float,
) -> Tuple[Optional[List[List[float]]], List[str], List[Optional[str]]]:
  normalized: List[str] = []
  for raw in path_hashes:
    key = _normalize_node_hash(raw)
    if key:
      normalized.append(key)
  if ROUTE_PATH_MAX_LEN > 0 and len(normalized) > ROUTE_PATH_MAX_LEN:
    return None, [], []

  receiver_hashes = (
    set(_node_hashes_from_device_id(receiver_id)) if receiver_id else set()
  )
  origin_hashes = (
    set(_node_hashes_from_device_id(origin_id)) if origin_id else set()
  )

  if normalized and receiver_hashes:
    if normalized[0] in receiver_hashes and normalized[-1] not in receiver_hashes:
      normalized.reverse()
  elif normalized and origin_hashes:
    if normalized[-1] in origin_hashes and normalized[0] not in origin_hashes:
      normalized.reverse()

  points: List[List[float]] = []
  used_hashes: List[str] = []
  point_ids: List[Optional[str]] = []

  # We need a reference point to start "walking" the path spatially.
  # Best bet is the origin, if known.
  current_lat = None
  current_lon = None
  current_id: Optional[str] = None

  if origin_id:
    origin_state = devices.get(origin_id)
    if origin_state and not _coords_are_zero(
      origin_state.lat, origin_state.lon
    ):
      try:
        current_lat = float(origin_state.lat)
        current_lon = float(origin_state.lon)
        current_id = origin_id
      except (TypeError, ValueError):
        pass

  # Build the path
  for key in normalized:
    device_id = None
    candidates = node_hash_candidates.get(key) or []
    ambiguous_single_byte = (
      len(key) == 2 and len(candidates) > 1 and
      not ROUTE_ALLOW_AMBIGUOUS_ONE_BYTE_FALLBACK
    )

    if current_id and current_lat is not None and current_lon is not None:
      if len(candidates) > 1:
        # For the first hop, prefer the closest candidate to the origin.
        if not points and not ambiguous_single_byte:
          device_id = _choose_closest_device(key, current_lat, current_lon, ts)
        if not device_id:
          neighbor_id = _choose_neighbor_device(
            current_id,
            candidates,
            current_lat,
            current_lon,
            ts,
          )
          if neighbor_id:
            device_id = neighbor_id
            edge = neighbor_edges.get(current_id, {}).get(neighbor_id, {})
            manual = " manual" if edge.get("manual") else ""
            if ROUTE_NEIGHBOR_DEBUG:
              print(
                f"[route] neighbor pick{manual} hash={key} "
                f"{current_id[:8]} -> {neighbor_id[:8]}"
              )

    # If we have a location fix, try to find the "closest" candidate for this hash
    if (
      not device_id and
      current_lat is not None and
      current_lon is not None and
      not ambiguous_single_byte
    ):
      device_id = _choose_closest_device(key, current_lat, current_lon, ts)

    if not device_id and not ambiguous_single_byte:
      # Fallback to older time-based logic or just picking first valid
      device_id = _choose_device_for_hash(key, ts)
      if not device_id:
        # fallback: just pick *any* mapping if available
        device_id = node_hash_to_device.get(key)

    if not device_id:
      continue

    state = devices.get(device_id)
    if not state:
      continue
    if _coords_are_zero(state.lat, state.lon):
      continue

    try:
      p_lat = float(state.lat)
      p_lon = float(state.lon)
    except (TypeError, ValueError):
      continue

    # Safety check: enforce max distance even for fallback selections
    if current_lat is not None and current_lon is not None:
      dist = _haversine_m(current_lat, current_lon, p_lat, p_lon)
      if dist > (ROUTE_MAX_HOP_DISTANCE * 1000.0):
        continue

    point = [p_lat, p_lon]
    # Update our "current" reference for the next hop
    current_lat = p_lat
    current_lon = p_lon
    current_id = device_id

    if points and point == points[-1]:
      continue

    points.append(point)
    used_hashes.append(key)
    point_ids.append(device_id)

  # Prepend origin if missing
  origin_point = None
  if origin_id:
    origin_state = devices.get(origin_id)
    if origin_state and not _coords_are_zero(
      origin_state.lat, origin_state.lon
    ):
      # If infrastructure-only, only add infra nodes
      if ROUTE_INFRA_ONLY and (
        not origin_state.role or origin_state.role not in ("repeater", "room")
      ):
        pass  # skip
      else:
        try:
          origin_point = [float(origin_state.lat), float(origin_state.lon)]
          if not points or points[0] != origin_point:
            points.insert(0, origin_point)
            point_ids.insert(0, origin_id)
          elif point_ids:
            point_ids[0] = origin_id
        except (TypeError, ValueError):
          pass

  # Append receiver if missing
  receiver_point = None
  if receiver_id:
    receiver_state = devices.get(receiver_id)
    if receiver_state and not _coords_are_zero(
      receiver_state.lat, receiver_state.lon
    ):
      # If infrastructure-only, only add infra nodes
      if ROUTE_INFRA_ONLY and (
        not receiver_state.role or
        receiver_state.role not in ("repeater", "room")
      ):
        pass  # skip
      else:
        try:
          receiver_point = [
            float(receiver_state.lat),
            float(receiver_state.lon),
          ]
          if points and receiver_point != points[-1]:
            dist = _haversine_m(points[-1][0], points[-1][1],
                                receiver_point[0], receiver_point[1])
            if dist <= (ROUTE_MAX_HOP_DISTANCE * 1000.0):
              points.append(receiver_point)
              point_ids.append(receiver_id)
          elif point_ids:
            point_ids[-1] = receiver_id
        except (TypeError, ValueError):
          pass

  if len(points) < 2:
    return None, used_hashes, point_ids

  return points, used_hashes, point_ids


def _route_points_from_device_ids(
  origin_id: Optional[str], receiver_id: Optional[str]
) -> Optional[List[List[float]]]:
  if not origin_id or not receiver_id or origin_id == receiver_id:
    return None
  origin_state = devices.get(origin_id)
  receiver_state = devices.get(receiver_id)
  if not origin_state or not receiver_state:
    return None

  # If infrastructure-only mode is active, only allow repeaters and rooms
  if ROUTE_INFRA_ONLY and (
    (not origin_state.role or origin_state.role not in ("repeater", "room")) or
    (
      not receiver_state.role or
      receiver_state.role not in ("repeater", "room")
    )
  ):
    return None

  if _coords_are_zero(origin_state.lat, origin_state.lon) or _coords_are_zero(
    receiver_state.lat, receiver_state.lon
  ):
    return None
  points = [
    [origin_state.lat, origin_state.lon],
    [receiver_state.lat, receiver_state.lon],
  ]
  dist = _haversine_m(points[0][0], points[0][1], points[1][0], points[1][1])
  if dist > (ROUTE_MAX_HOP_DISTANCE * 1000.0):
    return None
  if points[0] == points[1]:
    return None
  return points


def _append_heat_points(
  points: List[List[float]], ts: float, payload_type: Optional[int]
) -> None:
  if HEAT_TTL_SECONDS <= 0:
    return
  for point in points:
    heat_events.append(
      {
        "lat": float(point[0]),
        "lon": float(point[1]),
        "ts": float(ts),
        "weight": 0.7,
      }
    )


def _serialize_heat_events() -> List[List[float]]:
  if HEAT_TTL_SECONDS <= 0:
    return []
  cutoff = time.time() - HEAT_TTL_SECONDS
  return [
    [
      entry.get("lat"),
      entry.get("lon"),
      entry.get("ts"),
      entry.get("weight", 0.7)
    ] for entry in heat_events if entry.get("ts", 0) >= cutoff
  ]


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
  if (
    "companion" in s or
    "chat node" in s or
    "chatnode" in s or
    "chat-node" in s or
    s == "chat"
  ):
    return "companion"
  if "room server" in s or "roomserver" in s or s == "room":
    return "room"
  return None


def _normalize_role_code(value: Any) -> Optional[str]:
  try:
    num = int(str(value).strip())
  except (TypeError, ValueError):
    return None
  if num == 2:
    return "repeater"
  if num == 3:
    return "room"
  if num == 1:
    return "companion"
  return None


def _extract_role_from_hint(value: Any) -> Optional[str]:
  if isinstance(value, str):
    role = _normalize_role(value)
    if role:
      return role
    return _normalize_role_code(value)
  if isinstance(value, (int, float)) and not isinstance(value, bool):
    return _normalize_role_code(value)
  return None


def _extract_device_role(obj: Any, topic: str) -> Optional[str]:
  del topic
  role_keys = (
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
  )

  def walk(value: Any) -> Optional[str]:
    if isinstance(value, dict):
      for key in role_keys:
        if key in value:
          role = _extract_role_from_hint(value.get(key))
          if role:
            return role
      for child in value.values():
        role = walk(child)
        if role:
          return role
    elif isinstance(value, list):
      for child in value:
        role = walk(child)
        if role:
          return role
    return None

  return walk(obj)


def _reject_invalid_packet(debug: Dict[str, Any], meta: Dict[str, Any]) -> bool:
  if meta.get("invalid_packet") is not True:
    return False
  debug["invalid_packet"] = True
  debug["result"] = "invalid_packet"
  debug["decoder_meta"] = meta
  # Envelope hints are not authoritative when its RF packet is rejected.
  for key in ("decoded_pubkey", "origin_id", "device_name", "device_role",
              "packet_hash", "packet_type"):
    debug[key] = None
  return True


def _apply_meta_role(
  debug: Dict[str, Any], meta: Optional[Dict[str, Any]]
) -> None:
  if debug.get("device_role"):
    return
  if not isinstance(meta, dict):
    return
  for key in ("role", "deviceRoleName", "deviceRole"):
    if key not in meta:
      continue
    normalized = _extract_role_from_hint(meta.get(key))
    if normalized:
      debug["device_role"] = normalized
      return


def _has_location_hints(obj: Any) -> bool:
  if isinstance(obj, dict):
    for k, v in obj.items():
      key = str(k).lower()
      if key in (
        "location",
        "gps",
        "position",
        "coords",
        "coordinate",
        "geo",
        "geolocation",
        "latlon",
      ):
        return True
      if isinstance(v, (dict, list)) and _has_location_hints(v):
        return True
  elif isinstance(obj, list):
    for v in obj:
      if _has_location_hints(v):
        return True
  return False


def _topic_marks_online(topic: str) -> bool:
  if not MQTT_ONLINE_TOPIC_SUFFIXES:
    return False
  return any(topic.endswith(suffix) for suffix in MQTT_ONLINE_TOPIC_SUFFIXES)


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
    subprocess.run(
      ["node", "-v"],
      check=True,
      stdout=subprocess.DEVNULL,
      stderr=subprocess.DEVNULL,
    )
  except Exception:
    _node_unavailable_once = True
    print("[decode] node not found in container")
    return False

  try:
    subprocess.run(
      [
        "node",
        "--input-type=module",
        "-e",
        "import('@michaelhart/meshcore-decoder')",
      ],
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
import { MeshCorePacketDecoder, getDeviceRoleName } from '@michaelhart/meshcore-decoder';
import readline from 'node:readline';

let keyStore = undefined;
let keySignature = '';

function normalizePubkey(value) {
  if (typeof value !== 'string') return null;
  const normalized = value.trim().toUpperCase();
  return /^[0-9A-F]{64}$/.test(normalized) ? normalized : null;
}

function pickAdvertPayload(decodedPacket) {
  const payloadDecoded = decodedPacket?.payload?.decoded ?? null;
  const payloadRoot = decodedPacket?.payload ?? null;
  if (payloadDecoded?.type === 4) return payloadDecoded;
  if (payloadRoot?.type === 4) return payloadRoot;
  return null;
}

function pickLocation(decodedPacket) {
  const advert = pickAdvertPayload(decodedPacket);
  const appData = advert?.appData ?? advert?.appdata ?? null;
  const loc = appData?.location ?? advert?.location ?? null;
  const lat = loc?.latitude ?? loc?.lat ?? null;
  const lon = loc?.longitude ?? loc?.lon ?? null;
  const name = appData?.name ?? advert?.name ?? null;
  const pubkey =
    normalizePubkey(advert?.publicKey) ??
    normalizePubkey(advert?.publickey) ??
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

function syncKeyStore(channelSecrets) {
  const normalized = Array.isArray(channelSecrets)
    ? channelSecrets
      .filter((value) => typeof value === 'string' && /^[0-9a-f]{32}$/i.test(value))
      .map((value) => value.toLowerCase())
      .sort()
    : [];
  const nextSignature = normalized.join(',');
  if (nextSignature === keySignature) return;
  keySignature = nextSignature;
  keyStore = normalized.length
    ? MeshCorePacketDecoder.createKeyStore({ channelSecrets: normalized })
    : undefined;
}

async function decodeHex(hex, channelSecrets) {
  syncKeyStore(channelSecrets);
  const decoded = await MeshCorePacketDecoder.decodeWithVerification(hex, keyStore ? { keyStore } : undefined);
  const advert = pickAdvertPayload(decoded);
  const isAdvert = decoded?.payloadType === 4 || advert !== null;
  if (decoded?.isValid !== true || (isAdvert &&
      (advert?.isValid !== true || advert?.signatureValid !== true))) {
    // Fixed, bounded diagnostics only: decoder errors may contain raw input.
    return {
      ok: false,
      invalid_packet: true,
      error: isAdvert ? 'invalid_advert' : 'invalid_packet',
      isValid: decoded?.isValid === true,
      signatureValid: isAdvert ? advert?.signatureValid === true : null,
    };
  }
  const loc = pickLocation(decoded);
  const payloadDecoded = decoded?.payload?.decoded ?? decoded?.payload ?? null;
  const payloadRoot = decoded?.payload ?? null;
  const appData = payloadDecoded?.appData ?? payloadDecoded?.appdata ?? payloadRoot?.appData ?? payloadRoot?.appdata ?? null;
  const senderName =
    payloadDecoded?.decrypted?.sender ??
    payloadRoot?.decrypted?.sender ??
    null;
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
    isValid: true,
    signatureValid: isAdvert ? true : null,
    payloadType: decoded?.payloadType ?? null,
    routeType: decoded?.routeType ?? null,
    messageHash: decoded?.messageHash ?? null,
    location: loc,
    role,
    deviceRole,
    deviceRoleName,
    senderName,
    payloadKeys,
    appDataKeys,
    pathHashes,
    snrValues,
    path,
    pathLength,
  };
  return out;
}

const rl = readline.createInterface({
  input: process.stdin,
  crlfDelay: Infinity,
});

// Await each request before consuming the next: Python uses ordered readline.
for await (const line of rl) {
  let request;
  try {
    request = JSON.parse(line);
  } catch (e) {
    process.stdout.write(JSON.stringify({ ok: false, error: 'invalid_request_json' }) + '\\n');
    continue;
  }
  try {
    const hex = typeof request?.hex === 'string' ? request.hex.trim() : '';
    if (!hex) {
      process.stdout.write(JSON.stringify({ ok: false, error: 'missing_hex' }) + '\\n');
      continue;
    }
    const channelSecrets = Array.isArray(request?.channelSecrets) ? request.channelSecrets : [];
    process.stdout.write(JSON.stringify(await decodeHex(hex, channelSecrets)) + '\\n');
  } catch (e) {
    process.stdout.write(JSON.stringify({ ok: false, invalid_packet: true, error: 'packet_decode_error' }) + '\\n');
  }
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


def _stop_node_decoder_worker() -> None:
  global _node_worker_proc
  proc = _node_worker_proc
  _node_worker_proc = None
  if not proc:
    return
  try:
    if proc.stdin:
      proc.stdin.close()
  except Exception:
    pass
  try:
    proc.terminate()
    proc.wait(timeout=1.0)
  except Exception:
    try:
      proc.kill()
      proc.wait(timeout=1.0)
    except Exception:
      pass


def _start_node_decoder_worker() -> Optional[subprocess.Popen[str]]:
  global _node_worker_proc, _node_unavailable_once
  proc = _node_worker_proc
  if proc and proc.poll() is None:
    return proc
  _stop_node_decoder_worker()
  try:
    proc = subprocess.Popen(
      ["node", NODE_SCRIPT_PATH],
      stdin=subprocess.PIPE,
      stdout=subprocess.PIPE,
      stderr=subprocess.PIPE,
      text=True,
      cwd=APP_DIR,
      bufsize=1,
      env=os.environ.copy(),
    )
  except Exception as exc:
    _node_unavailable_once = True
    print(f"[decode] failed starting node worker: {exc}")
    return None
  _node_worker_proc = proc
  return proc


def _restart_node_decoder_worker() -> Optional[subprocess.Popen[str]]:
  _stop_node_decoder_worker()
  return _start_node_decoder_worker()


def _node_worker_error(proc: Optional[subprocess.Popen[str]]) -> str:
  if not proc or not proc.stderr:
    return "node_worker_failed"
  try:
    err = proc.stderr.read().strip()
  except Exception:
    err = ""
  return err or "node_worker_failed"


def _decode_meshcore_hex(
  hex_str: str,
) -> Tuple[Optional[float], Optional[float], Optional[str], Optional[str], Dict[
  str, Any]]:
  if not _ensure_node_decoder():
    return (
      None,
      None,
      None,
      None,
      {
        "ok": False,
        "error": "node_decoder_unavailable"
      },
    )

  request = {
    "hex": hex_str,
    "channelSecrets": _load_channel_secrets(),
  }
  out = ""
  last_error = "node_worker_failed"
  with _node_worker_lock:
    for attempt in range(2):
      proc = _start_node_decoder_worker() if attempt == 0 else _restart_node_decoder_worker()
      if not proc or not proc.stdin or not proc.stdout:
        last_error = "node_worker_unavailable"
        continue
      try:
        proc.stdin.write(json.dumps(request) + "\n")
        proc.stdin.flush()
      except Exception as exc:
        last_error = str(exc)
        _stop_node_decoder_worker()
        continue
      try:
        ready, _, _ = select.select([proc.stdout], [], [], NODE_DECODE_TIMEOUT_SECONDS)
      except Exception as exc:
        last_error = str(exc)
        _stop_node_decoder_worker()
        continue
      if not ready:
        last_error = "node_worker_timeout"
        _stop_node_decoder_worker()
        continue
      try:
        out = (proc.stdout.readline() or "").strip()
      except Exception as exc:
        last_error = str(exc)
        _stop_node_decoder_worker()
        continue
      if out:
        break
      if proc.poll() is not None:
        last_error = _node_worker_error(proc)
      else:
        last_error = "empty_decoder_output"
        _stop_node_decoder_worker()
    else:
      return (None, None, None, None, {"ok": False, "error": last_error})

  if not out:
    return (
      None, None, None, None, {
        "ok": False,
        "error": last_error or "empty_decoder_output"
      }
    )

  try:
    data = json.loads(out)
  except Exception:
    return (
      None,
      None,
      None,
      None,
      {
        "ok": False,
        "error": "decoder_output_not_json",
        "output": out
      },
    )

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

  return (
    None,
    None,
    pubkey,
    name,
    {
      "ok": True,
      **data, "note": "decoded_no_location"
    },
  )


# =========================
# Parsing: MeshCore-ish payloads
# =========================


def _device_id_from_topic(topic: str) -> Optional[str]:
  parts = topic.split("/")
  if len(parts) >= 3 and parts[0] == "meshcore":
    return parts[2]
  return None


def _find_packet_blob(
  obj: Any,
  path: str = "root"
) -> Tuple[Optional[str], Optional[str], Optional[str]]:
  if isinstance(obj, str):
    if _looks_like_hex(obj):
      return (obj.strip(), path, "hex")
    b64hex = _try_base64_to_hex(obj)
    if b64hex:
      return (b64hex, path, "base64")
    return (None, None, None)

  if isinstance(obj, list):
    if obj and all(isinstance(x, int) for x in obj[:min(20, len(obj))]):
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
      if (
        isinstance(v, list) and v and
        all(isinstance(x, int) for x in v[:min(20, len(v))])
      ):
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


def _find_rf_packet_blob(obj: Any) -> Tuple[Optional[str], Optional[str], Optional[str]]:
  """Find explicit RF fields without treating observer public keys as packets."""
  if isinstance(obj, dict):
    for key, value in obj.items():
      if key in LIKELY_PACKET_KEYS:
        found = _find_packet_blob(value, f"root.{key}")
        if found[0]:
          return found
    for value in obj.values():
      if isinstance(value, (dict, list)):
        found = _find_rf_packet_blob(value)
        if found[0]:
          return found
  elif isinstance(obj, list):
    for value in obj:
      found = _find_rf_packet_blob(value)
      if found[0]:
        return found
  return (None, None, None)


def _extract_device_id(
  obj: Any, topic: str, decoded_pubkey: Optional[str]
) -> str:
  if decoded_pubkey:
    return str(decoded_pubkey)
  if isinstance(obj, dict):
    device_id = (
      obj.get("device_id") or obj.get("id") or obj.get("from") or
      obj.get("origin_id")
    )
    if device_id:
      return str(device_id)
    jwt = obj.get("jwt_payload")
    if isinstance(jwt, dict) and jwt.get("publickey"):
      return str(jwt.get("publickey"))
  return _device_id_from_topic(topic) or topic.split("/")[-1]


def _try_parse_payload(
  topic: str, payload_bytes: bytes
) -> Tuple[Optional[Dict[str, Any]], Dict[str, Any]]:
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
        debug["packet_hash"] = (
          obj.get("hash") or obj.get("message_hash") or obj.get("messageHash")
        )
        debug["packet_type"] = (
          obj.get("packet_type") or obj.get("packetType") or obj.get("type")
        )
    except Exception as exc:
      debug["parse_error"] = str(exc)

  if obj is not None:
    packet_hex, packet_where, packet_hint = _find_rf_packet_blob(obj)
    packet_decoded = None
    if packet_hex:
      packet_decoded = _decode_meshcore_hex(packet_hex)
      debug["found_path"] = packet_where
      debug["found_hint"] = packet_hint
      if _reject_invalid_packet(debug, packet_decoded[4]):
        return (None, debug)
    # Explicit RF envelopes must use verified RF metadata, not coordinate hints.
    found = None if packet_hex else _find_lat_lon_in_json(obj)
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
      return (
        {
          "device_id": device_id,
          "lat": found[0],
          "lon": found[1],
          "ts": ts,
          "heading": obj.get("heading") if isinstance(obj, dict) else None,
          "speed": obj.get("speed") if isinstance(obj, dict) else None,
          "rssi": obj.get("rssi") if isinstance(obj, dict) else None,
          "snr": obj.get("snr") if isinstance(obj, dict) else None,
          "role": debug.get("device_role"),
        },
        debug,
      )

    for s in ([] if packet_hex else _strings_from_json(obj)):
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
        return (
          {
            "device_id": device_id,
            "lat": got[0],
            "lon": got[1],
            "ts": time.time(),
            "role": debug.get("device_role"),
          },
          debug,
        )

      decoded = _maybe_base64_decode_to_text(s)
      if decoded:
        got2 = _find_lat_lon_in_text(decoded)
        if got2:
          if not _direct_coords_allowed(topic, obj):
            debug["result"] = "direct_blocked"
            return (None, debug)
          if not DIRECT_COORDS_ALLOW_ZERO and _coords_are_zero(
            got2[0], got2[1]
          ):
            debug["result"] = "direct_zero_coords"
            return (None, debug)
          device_id = _extract_device_id(obj, topic, None)
          debug["result"] = "direct_text_json_base64"
          return (
            {
              "device_id": device_id,
              "lat": got2[0],
              "lon": got2[1],
              "ts": time.time(),
              "role": debug.get("device_role"),
            },
            debug,
          )

    # Status identities (including JWT public keys) are not RF packet blobs.
    if topic.endswith("/status") and not packet_hex:
      debug["result"] = "json_no_packet_blob"
      return (None, debug)

    hex_str, where, hint = ((packet_hex, packet_where, packet_hint)
                            if packet_hex else _find_packet_blob(obj))
    debug["found_path"] = where
    debug["found_hint"] = hint
    if hex_str:
      lat, lon, decoded_pubkey, name, meta = (
        packet_decoded if packet_decoded is not None else _decode_meshcore_hex(hex_str)
      )
      if _reject_invalid_packet(debug, meta):
        return (None, debug)
      debug["decoded_pubkey"] = decoded_pubkey
      debug["decoder_meta"] = meta
      _apply_meta_role(debug, meta)
      if lat is not None and lon is not None:
        device_id = _extract_device_id(obj, topic, decoded_pubkey)
        debug["result"] = "decoded"
        return (
          {
            "device_id": device_id,
            "lat": lat,
            "lon": lon,
            "ts": time.time(),
            "rssi": obj.get("rssi") if isinstance(obj, dict) else None,
            "snr": obj.get("snr") if isinstance(obj, dict) else None,
            "name": name,
            "role": debug.get("device_role"),
          },
          debug,
        )
      debug["result"] = (
        "decoded_no_location" if meta.get("ok") else "decode_failed"
      )
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
      return (
        {
          "device_id": _extract_device_id(None, topic, None),
          "lat": got[0],
          "lon": got[1],
          "ts": time.time(),
          "role": debug.get("device_role"),
        },
        debug,
      )

    if _looks_like_hex(text):
      debug["found_path"] = "payload"
      debug["found_hint"] = "hex"
      lat, lon, decoded_pubkey, name, meta = _decode_meshcore_hex(text.strip())
      if _reject_invalid_packet(debug, meta):
        return (None, debug)
      debug["decoded_pubkey"] = decoded_pubkey
      debug["decoder_meta"] = meta
      _apply_meta_role(debug, meta)
      if lat is not None and lon is not None:
        debug["result"] = "decoded"
        return (
          {
            "device_id": _extract_device_id(None, topic, decoded_pubkey),
            "lat": lat,
            "lon": lon,
            "ts": time.time(),
            "name": name,
            "role": debug.get("device_role"),
          },
          debug,
        )
      debug["result"] = (
        "decoded_no_location" if meta.get("ok") else "decode_failed"
      )
      return (None, debug)

    b64hex = _try_base64_to_hex(text)
    if b64hex:
      debug["found_path"] = "payload"
      debug["found_hint"] = "base64"
      lat, lon, decoded_pubkey, name, meta = _decode_meshcore_hex(b64hex)
      if _reject_invalid_packet(debug, meta):
        return (None, debug)
      debug["decoded_pubkey"] = decoded_pubkey
      debug["decoder_meta"] = meta
      _apply_meta_role(debug, meta)
      if lat is not None and lon is not None:
        debug["result"] = "decoded"
        return (
          {
            "device_id": _extract_device_id(None, topic, decoded_pubkey),
            "lat": lat,
            "lon": lon,
            "ts": time.time(),
            "name": name,
            "role": debug.get("device_role"),
          },
          debug,
        )
      debug["result"] = (
        "decoded_no_location" if meta.get("ok") else "decode_failed"
      )
      return (None, debug)

  if _is_probably_binary(payload_bytes) and len(payload_bytes) >= 10:
    debug["found_path"] = "payload_bytes"
    debug["found_hint"] = "raw_bytes"
    lat, lon, decoded_pubkey, name, meta = _decode_meshcore_hex(
      payload_bytes.hex()
    )
    if _reject_invalid_packet(debug, meta):
      return (None, debug)
    debug["decoded_pubkey"] = decoded_pubkey
    debug["decoder_meta"] = meta
    _apply_meta_role(debug, meta)
    if lat is not None and lon is not None:
      debug["result"] = "decoded"
      return (
        {
          "device_id": _extract_device_id(None, topic, decoded_pubkey),
          "lat": lat,
          "lon": lon,
          "ts": time.time(),
          "name": name,
          "role": debug.get("device_role"),
        },
        debug,
      )
    debug["result"] = "decoded_no_location" if meta.get(
      "ok"
    ) else "decode_failed"
    return (None, debug)

  return (None, debug)
