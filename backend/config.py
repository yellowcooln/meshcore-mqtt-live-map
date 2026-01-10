import os

# =========================
# Env / Config
# =========================
MQTT_HOST = os.getenv("MQTT_HOST", "localhost")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_USERNAME = os.getenv("MQTT_USERNAME", "")
MQTT_PASSWORD = os.getenv("MQTT_PASSWORD", "")

MQTT_TOPIC = os.getenv("MQTT_TOPIC", "meshcore/#")
MQTT_TOPICS = [t.strip() for t in MQTT_TOPIC.split(",") if t.strip()]

MQTT_TLS = os.getenv("MQTT_TLS", "false").lower() == "true"
MQTT_TLS_INSECURE = os.getenv("MQTT_TLS_INSECURE", "false").lower() == "true"
MQTT_CA_CERT = os.getenv("MQTT_CA_CERT", "")  # optional path to CA bundle

MQTT_TRANSPORT = os.getenv("MQTT_TRANSPORT", "tcp").strip().lower()  # tcp | websockets
MQTT_WS_PATH = os.getenv("MQTT_WS_PATH", "/mqtt")  # often "/" or "/mqtt"

MQTT_CLIENT_ID = os.getenv("MQTT_CLIENT_ID", "")

STATE_DIR = os.getenv("STATE_DIR", "/data")
STATE_FILE = os.getenv("STATE_FILE", os.path.join(STATE_DIR, "state.json"))
DEVICE_ROLES_FILE = os.getenv("DEVICE_ROLES_FILE", os.path.join(STATE_DIR, "device_roles.json"))
STATE_SAVE_INTERVAL = float(os.getenv("STATE_SAVE_INTERVAL", "5"))

DEVICE_TTL_SECONDS = int(os.getenv("DEVICE_TTL_SECONDS", "300"))
TRAIL_LEN = int(os.getenv("TRAIL_LEN", "30"))
ROUTE_TTL_SECONDS = int(os.getenv("ROUTE_TTL_SECONDS", "120"))
ROUTE_PAYLOAD_TYPES = os.getenv("ROUTE_PAYLOAD_TYPES", "8,9,2,5,4")
ROUTE_PATH_MAX_LEN = int(os.getenv("ROUTE_PATH_MAX_LEN", "16"))
ROUTE_HISTORY_ENABLED = os.getenv("ROUTE_HISTORY_ENABLED", "true").lower() == "true"
ROUTE_HISTORY_HOURS = float(os.getenv("ROUTE_HISTORY_HOURS", "24"))
ROUTE_HISTORY_MAX_SEGMENTS = int(os.getenv("ROUTE_HISTORY_MAX_SEGMENTS", "40000"))
ROUTE_HISTORY_FILE = os.getenv("ROUTE_HISTORY_FILE", os.path.join(STATE_DIR, "route_history.jsonl"))
ROUTE_HISTORY_PAYLOAD_TYPES = os.getenv("ROUTE_HISTORY_PAYLOAD_TYPES", ROUTE_PAYLOAD_TYPES)
ROUTE_HISTORY_ALLOWED_MODES = os.getenv("ROUTE_HISTORY_ALLOWED_MODES", "path")
ROUTE_HISTORY_COMPACT_INTERVAL = float(os.getenv("ROUTE_HISTORY_COMPACT_INTERVAL", "120"))
HISTORY_EDGE_SAMPLE_LIMIT = 3
MESSAGE_ORIGIN_TTL_SECONDS = int(os.getenv("MESSAGE_ORIGIN_TTL_SECONDS", "300"))
HEAT_TTL_SECONDS = int(os.getenv("HEAT_TTL_SECONDS", "600"))
MQTT_ONLINE_SECONDS = int(os.getenv("MQTT_ONLINE_SECONDS", "300"))
MQTT_SEEN_BROADCAST_MIN_SECONDS = float(os.getenv("MQTT_SEEN_BROADCAST_MIN_SECONDS", "5"))
MQTT_ONLINE_TOPIC_SUFFIXES = tuple(
  s.strip() for s in os.getenv("MQTT_ONLINE_TOPIC_SUFFIXES", "/status,/internal").split(",") if s.strip()
)
MQTT_ONLINE_FORCE_NAMES = tuple(
  s.strip() for s in os.getenv("MQTT_ONLINE_FORCE_NAMES", "").split(",") if s.strip()
)
MQTT_ONLINE_FORCE_NAMES_SET = {s.lower() for s in MQTT_ONLINE_FORCE_NAMES}

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

ROUTE_HISTORY_ALLOWED_MODES_SET = {s.strip() for s in ROUTE_HISTORY_ALLOWED_MODES.split(",") if s.strip()}

SITE_TITLE = os.getenv("SITE_TITLE", "Greater Boston Mesh Live Map")
SITE_DESCRIPTION = os.getenv("SITE_DESCRIPTION", "Live view of Greater Boston Mesh nodes, message routes, and advert paths.")
SITE_OG_IMAGE = os.getenv("SITE_OG_IMAGE", "")
SITE_URL = os.getenv("SITE_URL", "/")
SITE_ICON = os.getenv("SITE_ICON", "/static/logo.png")
SITE_FEED_NOTE = os.getenv("SITE_FEED_NOTE", "Feed: Boston MQTT.")
DISTANCE_UNITS = os.getenv("DISTANCE_UNITS", "km").strip().lower()
if DISTANCE_UNITS not in ("km", "mi"):
  DISTANCE_UNITS = "km"
try:
  NODE_MARKER_RADIUS = float(os.getenv("NODE_MARKER_RADIUS", "8"))
except ValueError:
  NODE_MARKER_RADIUS = 8.0
if NODE_MARKER_RADIUS <= 0:
  NODE_MARKER_RADIUS = 8.0
try:
  HISTORY_LINK_SCALE = float(os.getenv("HISTORY_LINK_SCALE", "1"))
except ValueError:
  HISTORY_LINK_SCALE = 1.0
if HISTORY_LINK_SCALE <= 0:
  HISTORY_LINK_SCALE = 1.0
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
MAP_DEFAULT_LAYER = os.getenv("MAP_DEFAULT_LAYER", "light").strip().lower()
try:
  MAP_RADIUS_KM = float(os.getenv("MAP_RADIUS_KM", "0"))
except ValueError:
  MAP_RADIUS_KM = 0.0
if MAP_RADIUS_KM < 0:
  MAP_RADIUS_KM = 0.0
MAP_RADIUS_SHOW = os.getenv("MAP_RADIUS_SHOW", "false").lower() == "true"

PROD_MODE = os.getenv("PROD_MODE", "false").lower() == "true"
PROD_TOKEN = os.getenv("PROD_TOKEN", "").strip()

LOS_ELEVATION_URL = os.getenv("LOS_ELEVATION_URL", "https://api.opentopodata.org/v1/srtm90m")
LOS_SAMPLE_MIN = int(os.getenv("LOS_SAMPLE_MIN", "10"))
LOS_SAMPLE_MAX = int(os.getenv("LOS_SAMPLE_MAX", "80"))
LOS_SAMPLE_STEP_METERS = int(os.getenv("LOS_SAMPLE_STEP_METERS", "250"))
ELEVATION_CACHE_TTL = int(os.getenv("ELEVATION_CACHE_TTL", "21600"))
LOS_PEAKS_MAX = int(os.getenv("LOS_PEAKS_MAX", "4"))

COVERAGE_API_URL = os.getenv("COVERAGE_API_URL", "").strip()

APP_DIR = os.path.dirname(os.path.abspath(__file__))
NODE_SCRIPT_PATH = os.path.join(APP_DIR, "meshcore_decode.mjs")
