import asyncio
import json
import os
import time
from typing import Any, Dict, List, Optional, Set, Tuple

import state
from persistence import FileWriter
from boundary import within_map_boundary
from config import (
  HISTORY_EDGE_SAMPLE_LIMIT,
  ROUTE_HISTORY_ALLOWED_MODES_SET,
  ROUTE_HISTORY_COMPACT_INTERVAL,
  ROUTE_HISTORY_ENABLED,
  ROUTE_HISTORY_FILE,
  ROUTE_HISTORY_HOURS,
  ROUTE_HISTORY_MAX_SEGMENTS,
  ROUTE_HISTORY_PAYLOAD_TYPES,
)
from decoder import _coords_are_zero

ROUTE_HISTORY_PAYLOAD_TYPES_SET: Set[int] = set()
for _part in ROUTE_HISTORY_PAYLOAD_TYPES.split(","):
  _part = _part.strip()
  if not _part:
    continue
  try:
    ROUTE_HISTORY_PAYLOAD_TYPES_SET.add(int(_part))
  except ValueError:
    pass

PEER_HISTORY_BUCKET_SECONDS = 300
_history_file_writer = FileWriter()


def _peer_history_cutoff(now: Optional[float] = None) -> float:
  current = time.time() if now is None else float(now)
  return current - (ROUTE_HISTORY_HOURS * 3600)


def _peer_history_bucket_start(ts: float) -> int:
  return int(float(ts) // PEER_HISTORY_BUCKET_SECONDS) * PEER_HISTORY_BUCKET_SECONDS


def _peer_history_pair_key(a_id: str, b_id: str) -> str:
  return f"{a_id}|{b_id}"


def _record_peer_history_segment(a_id: Any, b_id: Any, ts: float) -> bool:
  if ROUTE_HISTORY_HOURS <= 0:
    return False
  if not isinstance(a_id, str) or not a_id.strip():
    return False
  if not isinstance(b_id, str) or not b_id.strip():
    return False
  a_id = a_id.strip()
  b_id = b_id.strip()
  if a_id == b_id:
    return False
  bucket_start = _peer_history_bucket_start(ts)
  pair_key = _peer_history_pair_key(a_id, b_id)
  entry = state.peer_history_pairs.get(pair_key)
  if not entry:
    entry = {
      "a_id": a_id,
      "b_id": b_id,
      "buckets": {},
      "last_ts": float(ts),
    }
    state.peer_history_pairs[pair_key] = entry
  buckets = entry.get("buckets")
  if not isinstance(buckets, dict):
    buckets = {}
    entry["buckets"] = buckets
  bucket_key = str(bucket_start)
  buckets[bucket_key] = int(buckets.get(bucket_key, 0)) + 1
  entry["last_ts"] = max(float(entry.get("last_ts", 0.0)), float(ts))
  return True


def _prune_peer_history(
  now: Optional[float] = None,
  pair_keys: Optional[List[str]] = None,
) -> bool:
  if not state.peer_history_pairs:
    return False
  cutoff = _peer_history_cutoff(now)
  changed = False
  pairs_snapshot = (
    state.peer_history_pairs.copy() if pair_keys is None else {
      key: state.peer_history_pairs[key]
      for key in pair_keys if key in state.peer_history_pairs
    }
  )
  for pair_key, entry in pairs_snapshot.items():
    if not isinstance(entry, dict):
      state.peer_history_pairs.pop(pair_key, None)
      changed = True
      continue
    buckets = entry.get("buckets")
    if not isinstance(buckets, dict):
      state.peer_history_pairs.pop(pair_key, None)
      changed = True
      continue
    buckets_snapshot = buckets.copy()
    new_buckets: Dict[str, int] = {}
    last_ts = 0.0
    for bucket_key, count in buckets_snapshot.items():
      try:
        bucket_start = float(bucket_key)
        bucket_count = int(count)
      except (TypeError, ValueError):
        changed = True
        continue
      if bucket_count <= 0:
        changed = True
        continue
      bucket_end = bucket_start + PEER_HISTORY_BUCKET_SECONDS
      if bucket_end < cutoff:
        changed = True
        continue
      new_buckets[str(int(bucket_start))] = bucket_count
      last_ts = max(last_ts, bucket_end)
    if not new_buckets:
      state.peer_history_pairs.pop(pair_key, None)
      changed = True
      continue
    if len(new_buckets) != len(buckets):
      changed = True
    entry["buckets"] = new_buckets
    entry["last_ts"] = max(last_ts, float(entry.get("last_ts", 0.0)))
  return changed


async def _prune_peer_history_background(now: Optional[float] = None) -> bool:
  """Bound each maintenance turn; routes never sweep unrelated buckets."""
  keys = list(state.peer_history_pairs)
  changed = False
  batch_size = 128
  for offset in range(0, len(keys), batch_size):
    batch_changed = _prune_peer_history(
      now, pair_keys=keys[offset:offset + batch_size]
    )
    changed = batch_changed or changed
    if offset + batch_size < len(keys):
      await asyncio.sleep(0)
  return changed


def _rebuild_peer_history_from_segments() -> bool:
  state.peer_history_pairs.clear()
  changed = False
  for entry in state.route_history_segments:
    if not isinstance(entry, dict):
      continue
    a_id = entry.get("a_id")
    b_id = entry.get("b_id")
    ts = entry.get("ts")
    if not isinstance(ts, (int, float)):
      continue
    if _record_peer_history_segment(a_id, b_id, float(ts)):
      changed = True
  _prune_peer_history()
  return changed


def _history_payload_allowed(payload_type: Optional[int]) -> bool:
  if not ROUTE_HISTORY_ENABLED or ROUTE_HISTORY_HOURS <= 0:
    return False
  if not ROUTE_HISTORY_PAYLOAD_TYPES_SET:
    return True
  if payload_type is None:
    return False
  return payload_type in ROUTE_HISTORY_PAYLOAD_TYPES_SET


def _peer_history_payload_allowed(payload_type: Optional[int]) -> bool:
  if ROUTE_HISTORY_HOURS <= 0:
    return False
  if not ROUTE_HISTORY_PAYLOAD_TYPES_SET:
    return True
  if payload_type is None:
    return False
  return payload_type in ROUTE_HISTORY_PAYLOAD_TYPES_SET


def _within_map_radius(lat: float, lon: float) -> bool:
  return within_map_boundary(lat, lon)


def _normalize_history_point(point: Any) -> Optional[Tuple[float, float]]:
  if not isinstance(point, (list, tuple)) or len(point) < 2:
    return None
  try:
    lat_val = float(point[0])
    lon_val = float(point[1])
  except (TypeError, ValueError):
    return None
  if _coords_are_zero(lat_val, lon_val):
    return None
  if not _within_map_radius(lat_val, lon_val):
    return None
  return (round(lat_val, 6), round(lon_val, 6))


def _history_edge_key(
  a: Tuple[float, float], b: Tuple[float, float]
) -> Tuple[str, Tuple[float, float], Tuple[float, float]]:
  if a <= b:
    key = f"{a[0]:.6f},{a[1]:.6f}|{b[0]:.6f},{b[1]:.6f}"
    return key, a, b
  key = f"{b[0]:.6f},{b[1]:.6f}|{a[0]:.6f},{a[1]:.6f}"
  return key, b, a


def _history_sample_from_route(route: Dict[str, Any],
                               ts: float) -> Dict[str, Any]:
  route_byte_widths = _route_hash_byte_widths(route)
  return {
    "ts": float(ts),
    "message_hash": route.get("message_hash"),
    "payload_type": route.get("payload_type"),
    "origin_id": route.get("origin_id"),
    "receiver_id": route.get("receiver_id"),
    "route_mode": route.get("route_mode"),
    "topic": route.get("topic"),
    "route_byte_widths": route_byte_widths,
  }


def _route_hash_byte_widths(route: Dict[str, Any]) -> List[int]:
  widths: Set[int] = set()
  hashes = route.get("hashes")
  if not isinstance(hashes, list):
    return []
  for value in hashes:
    text = str(value or "").strip().lower()
    if text.startswith("0x"):
      text = text[2:]
    width = len(text) // 2 if len(text) in (2, 4, 6) else 0
    if width in (1, 2, 3):
      widths.add(width)
  return sorted(widths)


def _clean_route_byte_widths(value: Any) -> List[int]:
  if not isinstance(value, list):
    return []
  widths: Set[int] = set()
  for item in value:
    try:
      width = int(item)
    except (TypeError, ValueError):
      continue
    if width in (1, 2, 3):
      widths.add(width)
  return sorted(widths)


def _increment_history_byte_counts(edge: Dict[str, Any], widths: List[int]) -> None:
  if not widths:
    return
  byte_counts = edge.get("byte_counts")
  if not isinstance(byte_counts, dict):
    byte_counts = {}
  for width in widths:
    key = str(width)
    byte_counts[key] = int(byte_counts.get(key, 0)) + 1
  edge["byte_counts"] = byte_counts


def _decrement_history_byte_counts(edge: Dict[str, Any], widths: List[int]) -> None:
  byte_counts = edge.get("byte_counts")
  if not widths or not isinstance(byte_counts, dict):
    return
  for width in widths:
    key = str(width)
    next_count = int(byte_counts.get(key, 0)) - 1
    if next_count > 0:
      byte_counts[key] = next_count
    else:
      byte_counts.pop(key, None)
  if byte_counts:
    edge["byte_counts"] = byte_counts
  else:
    edge.pop("byte_counts", None)


def _update_history_edge_recent(
  edge: Dict[str, Any], sample: Dict[str, Any]
) -> None:
  if not edge or not sample:
    return
  recent = edge.get("recent")
  if not isinstance(recent, list):
    recent = []
  recent.append(sample)
  recent.sort(key=lambda s: s.get("ts", 0), reverse=True)
  if len(recent) > HISTORY_EDGE_SAMPLE_LIMIT:
    recent = recent[:HISTORY_EDGE_SAMPLE_LIMIT]
  edge["recent"] = recent


def _record_route_history(
  route: Dict[str, Any],
  *,
  pending_entries: Optional[List[Dict[str, Any]]] = None,
) -> Tuple[List[Dict[str, Any]], List[str]]:
  if ROUTE_HISTORY_ALLOWED_MODES_SET:
    route_mode = route.get("route_mode")
    if not route_mode or route_mode not in ROUTE_HISTORY_ALLOWED_MODES_SET:
      return [], []
  payload_type = route.get("payload_type")
  if not _peer_history_payload_allowed(payload_type):
    return [], []
  points = route.get("points")
  point_ids = route.get("point_ids"
                       ) if isinstance(route.get("point_ids"), list) else None
  if (
    (not isinstance(points, list) or len(points) < 2) and
    (not point_ids or len(point_ids) < 2)
  ):
    return [], []

  ts = route.get("ts") or time.time()
  sample = _history_sample_from_route(route, ts)
  updated_keys: Set[str] = set()
  new_entries: List[Dict[str, Any]] = []
  peer_recorded = False

  if point_ids and len(point_ids) >= 2:
    for idx in range(len(point_ids) - 1):
      if _record_peer_history_segment(
        point_ids[idx], point_ids[idx + 1], float(ts)
      ):
        peer_recorded = True

  if not ROUTE_HISTORY_ENABLED:
    if peer_recorded:
      state.state_dirty = True
    return [], []
  if not _history_payload_allowed(payload_type):
    return [], []

  if not isinstance(points, list) or len(points) < 2:
    if peer_recorded:
      state.state_dirty = True
    return [], []

  for idx in range(len(points) - 1):
    a = _normalize_history_point(points[idx])
    b = _normalize_history_point(points[idx + 1])
    if not a or not b:
      continue
    a_id = None
    b_id = None
    if point_ids and idx < len(point_ids) - 1:
      a_id = point_ids[idx]
      b_id = point_ids[idx + 1]
    key, first, second = _history_edge_key(a, b)
    new_entries.append(
      {
        "ts": float(ts),
        "a": [first[0], first[1]],
        "b": [second[0], second[1]],
        "a_id": a_id,
        "b_id": b_id,
        "message_hash": sample.get("message_hash"),
        "payload_type": sample.get("payload_type"),
        "origin_id": sample.get("origin_id"),
        "receiver_id": sample.get("receiver_id"),
        "route_mode": sample.get("route_mode"),
        "topic": sample.get("topic"),
        "route_byte_widths": sample.get("route_byte_widths"),
      }
    )
    edge = state.route_history_edges.get(key)
    if not edge:
      edge = {
        "id": key,
        "a": [first[0], first[1]],
        "b": [second[0], second[1]],
        "count": 0,
        "last_ts": float(ts),
      }
      state.route_history_edges[key] = edge
    edge["count"] = int(edge.get("count", 0)) + 1
    edge["last_ts"] = max(edge.get("last_ts", float(ts)), float(ts))
    _increment_history_byte_counts(edge, sample.get("route_byte_widths") or [])
    _update_history_edge_recent(edge, sample)
    updated_keys.add(key)

  if not new_entries:
    if peer_recorded:
      state.state_dirty = True
    return [], []

  state.route_history_segments.extend(new_entries)
  if pending_entries is None:
    if not _append_route_history_file(new_entries):
      state.route_history_compact = True
  else:
    pending_entries.extend(new_entries)
  if new_entries or peer_recorded:
    state.state_dirty = True

  updates = [
    state.route_history_edges[key]
    for key in updated_keys if key in state.route_history_edges
  ]
  removed: List[str] = []
  if ROUTE_HISTORY_MAX_SEGMENTS > 0 and len(
    state.route_history_segments
  ) > ROUTE_HISTORY_MAX_SEGMENTS:
    extra_updates, extra_removed = _prune_route_history(force_limit=True)
    updates.extend(extra_updates)
    removed.extend(extra_removed)

  return updates, removed


def _prune_route_history(
  force_limit: bool = False
) -> Tuple[List[Dict[str, Any]], List[str]]:
  if not ROUTE_HISTORY_ENABLED or not state.route_history_segments:
    return [], []

  updated: Dict[str, Dict[str, Any]] = {}
  removed: List[str] = []
  now = time.time()
  cutoff = now - (ROUTE_HISTORY_HOURS * 3600)

  while state.route_history_segments:
    entry = state.route_history_segments[0]
    if not isinstance(entry, dict):
      state.route_history_segments.popleft()
      continue
    ts = entry.get("ts")
    if ts is None:
      state.route_history_segments.popleft()
      continue
    if not force_limit and ts >= cutoff:
      break
    if force_limit and ROUTE_HISTORY_MAX_SEGMENTS > 0 and len(
      state.route_history_segments
    ) <= ROUTE_HISTORY_MAX_SEGMENTS:
      break
    state.route_history_segments.popleft()
    a = entry.get("a")
    b = entry.get("b")
    a_point = _normalize_history_point(a) if a else None
    b_point = _normalize_history_point(b) if b else None
    if not a_point or not b_point:
      state.route_history_compact = True
      continue
    key, _, _ = _history_edge_key(a_point, b_point)
    edge = state.route_history_edges.get(key)
    if not edge:
      state.route_history_compact = True
      continue
    edge["count"] = int(edge.get("count", 0)) - 1
    _decrement_history_byte_counts(
      edge, _clean_route_byte_widths(entry.get("route_byte_widths"))
    )
    recent = edge.get("recent")
    if isinstance(recent, list):
      edge["recent"] = [s for s in recent if (s.get("ts") or 0) >= cutoff]
      if not edge["recent"]:
        edge.pop("recent", None)
    if edge["count"] <= 0:
      state.route_history_edges.pop(key, None)
      removed.append(key)
    else:
      updated[key] = edge
    state.route_history_compact = True

  return list(updated.values()), removed


async def _record_route_history_async(
  route: Dict[str, Any]
) -> Tuple[List[Dict[str, Any]], List[str]]:
  """Keep accepted evidence on-loop; serialize live file work off-loop."""
  entries: List[Dict[str, Any]] = []
  result = _record_route_history(route, pending_entries=entries)
  if entries:
    try:
      saved = await _history_file_writer.run(
        _append_route_history_file, entries
      )
    except BaseException:
      # Accepted segments may still be waiting for the file lock at shutdown.
      # The final atomic compaction recovers them from canonical memory.
      state.route_history_compact = True
      raise
    if not saved:
      state.route_history_compact = True
  return result


def _append_route_history_file(entries: List[Dict[str, Any]]) -> bool:
  if not ROUTE_HISTORY_ENABLED or not ROUTE_HISTORY_FILE:
    return True
  if not entries:
    return True
  try:
    os.makedirs(os.path.dirname(ROUTE_HISTORY_FILE), exist_ok=True)
    with open(ROUTE_HISTORY_FILE, "a", encoding="utf-8") as handle:
      for entry in entries:
        handle.write(json.dumps(entry) + "\n")
    return True
  except Exception as exc:
    print(f"[history] failed to append {ROUTE_HISTORY_FILE}: {exc}")
    return False


def _load_route_history() -> None:
  if not ROUTE_HISTORY_ENABLED or not ROUTE_HISTORY_FILE:
    return
  if not os.path.exists(ROUTE_HISTORY_FILE):
    return

  cutoff = time.time() - (ROUTE_HISTORY_HOURS * 3600)
  loaded_any = False

  try:
    with open(ROUTE_HISTORY_FILE, "r", encoding="utf-8") as handle:
      for line in handle:
        line = line.strip()
        if not line:
          continue
        try:
          entry = json.loads(line)
        except json.JSONDecodeError:
          state.route_history_compact = True
          continue
        if not isinstance(entry, dict):
          state.route_history_compact = True
          continue
        ts = entry.get("ts")
        if not isinstance(ts, (int, float)) or ts < cutoff:
          state.route_history_compact = True
          continue
        a_point = _normalize_history_point(entry.get("a"))
        b_point = _normalize_history_point(entry.get("b"))
        if not a_point or not b_point:
          state.route_history_compact = True
          continue
        sample = {
          "ts": float(ts),
          "message_hash": entry.get("message_hash"),
          "payload_type": entry.get("payload_type"),
          "origin_id": entry.get("origin_id"),
          "receiver_id": entry.get("receiver_id"),
          "route_mode": entry.get("route_mode"),
          "topic": entry.get("topic"),
          "route_byte_widths": _clean_route_byte_widths(
            entry.get("route_byte_widths")
          ),
        }
        key, first, second = _history_edge_key(a_point, b_point)
        state.route_history_segments.append(
          {
            "ts": float(ts),
            "a": [first[0], first[1]],
            "b": [second[0], second[1]],
            "a_id": entry.get("a_id"),
            "b_id": entry.get("b_id"),
            "message_hash": sample.get("message_hash"),
            "payload_type": sample.get("payload_type"),
            "origin_id": sample.get("origin_id"),
            "receiver_id": sample.get("receiver_id"),
            "route_mode": sample.get("route_mode"),
            "topic": sample.get("topic"),
            "route_byte_widths": sample.get("route_byte_widths"),
          }
        )
        edge = state.route_history_edges.get(key)
        if not edge:
          edge = {
            "id": key,
            "a": [first[0], first[1]],
            "b": [second[0], second[1]],
            "count": 0,
            "last_ts": float(ts),
          }
          state.route_history_edges[key] = edge
        edge["count"] = int(edge.get("count", 0)) + 1
        edge["last_ts"] = max(edge.get("last_ts", float(ts)), float(ts))
        _increment_history_byte_counts(edge, sample.get("route_byte_widths") or [])
        _update_history_edge_recent(edge, sample)
        loaded_any = True
  except Exception as exc:
    print(f"[history] failed to load {ROUTE_HISTORY_FILE}: {exc}")
    return

  if not loaded_any:
    return

  if not state.peer_history_pairs:
    _rebuild_peer_history_from_segments()

  if ROUTE_HISTORY_MAX_SEGMENTS > 0 and len(
    state.route_history_segments
  ) > ROUTE_HISTORY_MAX_SEGMENTS:
    _prune_route_history(force_limit=True)
    state.route_history_compact = True


def _write_route_history_snapshot(
  path: str, entries: Tuple[Dict[str, Any], ...]
) -> None:
  directory = os.path.dirname(path)
  if directory:
    os.makedirs(directory, exist_ok=True)
  tmp_path = f"{path}.tmp"
  with open(tmp_path, "w", encoding="utf-8") as handle:
    for entry in entries:
      if isinstance(entry, dict):
        handle.write(json.dumps(entry) + "\n")
  os.replace(tmp_path, path)


async def _flush_route_history() -> None:
  if (
    not ROUTE_HISTORY_ENABLED or not ROUTE_HISTORY_FILE or
    not state.route_history_compact
  ):
    return
  entries = tuple(state.route_history_segments)
  state.route_history_compact = False
  try:
    await _history_file_writer.run(
      _write_route_history_snapshot, ROUTE_HISTORY_FILE, entries
    )
    state.route_history_last_compact = time.time()
  except BaseException:
    state.route_history_compact = True
    raise


async def _route_history_saver() -> None:
  if not ROUTE_HISTORY_ENABLED or not ROUTE_HISTORY_FILE:
    return
  while True:
    await asyncio.sleep(max(5.0, ROUTE_HISTORY_COMPACT_INTERVAL))
    if not state.route_history_compact:
      continue
    now = time.time()
    if now - state.route_history_last_compact < ROUTE_HISTORY_COMPACT_INTERVAL:
      continue
    try:
      await _flush_route_history()
    except Exception as exc:
      print(f"[history] failed to compact {ROUTE_HISTORY_FILE}: {exc}")
