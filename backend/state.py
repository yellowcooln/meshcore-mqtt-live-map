from collections import deque
from dataclasses import dataclass
from typing import Any, Deque, Dict, List, Optional, Set

import config


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
seen_devices: Dict[str, float] = {}
mqtt_seen: Dict[str, float] = {}
last_seen_broadcast: Dict[str, float] = {}
topic_counts: Dict[str, int] = {}

debug_last: Deque[Dict[str, Any]] = deque(maxlen=config.DEBUG_LAST_MAX)
status_last: Deque[Dict[str, Any]] = deque(maxlen=config.DEBUG_STATUS_MAX)

devices: Dict[str, DeviceState] = {}
trails: Dict[str, list] = {}
routes: Dict[str, Dict[str, Any]] = {}
heat_events: List[Dict[str, float]] = []
route_history_segments: Deque[Dict[str, Any]] = deque()
route_history_edges: Dict[str, Dict[str, Any]] = {}
route_history_compact = False
route_history_last_compact = 0.0
node_hash_to_device: Dict[str, str] = {}
node_hash_collisions: Set[str] = set()
node_hash_candidates: Dict[str, List[str]] = {}
elevation_cache: Dict[str, tuple] = {}
device_names: Dict[str, str] = {}
message_origins: Dict[str, Dict[str, Any]] = {}
device_roles: Dict[str, str] = {}
device_role_sources: Dict[str, str] = {}
device_coords: Dict[str, Dict[str, float]] = {}
state_dirty = False
