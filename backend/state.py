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
  "callback_errors_total": 0,
  "last_callback_error_ts": None,
}
result_counts: Dict[str, int] = {}
seen_devices: Dict[str, float] = {}
mqtt_seen: Dict[str, float] = {}
mqtt_online_source: Dict[str, str] = {}
mqtt_status_seen: Dict[str, float] = {}
mqtt_status_values: Dict[str, str] = {}
mqtt_internal_seen: Dict[str, float] = {}
mqtt_packets_seen: Dict[str, float] = {}
last_seen_broadcast: Dict[str, float] = {}
topic_counts: Dict[str, int] = {}

debug_last: Deque[Dict[str, Any]] = deque(maxlen=config.DEBUG_LAST_MAX)
status_last: Deque[Dict[str, Any]] = deque(maxlen=config.DEBUG_STATUS_MAX)

devices: Dict[str, DeviceState] = {}
trails: Dict[str, list] = {}
routes: Dict[str, Dict[str, Any]] = {}
# Process-local live-route generations are not persisted across restarts.
route_generation = 0
heat_events: List[Dict[str, float]] = []
route_history_segments: Deque[Dict[str, Any]] = deque()
route_history_edges: Dict[str, Dict[str, Any]] = {}
peer_history_pairs: Dict[str, Dict[str, Any]] = {}
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
neighbor_edges: Dict[str, Dict[str, Dict[str, Any]]] = {}
last_seen_in_path: Dict[str, float] = {}
first_seen_devices: Dict[str, float] = {}
last_seen_in_advert: Dict[str, float] = {}
state_dirty = False
