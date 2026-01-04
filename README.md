# Mesh Live Map

Live MeshCore traffic map that renders nodes, routes, and activity in real time on a Leaflet map. The backend subscribes to MQTT over WebSockets + TLS, decodes MeshCore packets with `@michaelhart/meshcore-decoder`, and streams updates to the browser via WebSockets.

Live example sites: 
 - https://live.bostonme.sh/
 - https://meshmap.nastic.icu/


![Live map preview](example.gif)
---
![Live map preview](backend/example2.gif)

## Features
- Live node markers with roles (Repeater, Companion, Room Server, Unknown)
- MQTT online indicator (green outline + popup status)
- Animated route/trace lines and message fanout
- Heat map for the last 10 minutes of message activity (includes adverts)
- Persistent device state and optional trails (disable with `TRAIL_LEN=0`)
- 24-hour route history overlay (toggle) with volume-based coloring and click-to-view packet details
- UI controls: legend toggle, dark map, topo map, units toggle (km/mi), labels toggle, hide nodes, heat toggle
- Node search by name or public key
- LOS tool with elevation profile + peak markers and hover sync (Shift+click or long‑press nodes)
- Embeddable metadata (Open Graph/Twitter tags) driven by env vars
- Propagation panel lives on the right and keeps the last render until you generate a new one
- Installable PWA (manifest + service worker) for Add to Home Screen
- Click the logo to hide/show the left HUD panel while tools stay open

## Project Structure
- `backend/app.py`: FastAPI server wiring, MQTT lifecycle, WS broadcast
- `backend/config.py`: environment configuration
- `backend/state.py`: shared in-memory state + dataclasses
- `backend/decoder.py`: payload parsing + meshcore-decoder integration
- `backend/los.py`: LOS math + elevation helpers
- `backend/history.py`: route history persistence + pruning
- `backend/static/index.html`: HTML shell + template placeholders
- `backend/static/styles.css`: UI styles
- `backend/static/app.js`: map logic + UI controls
- `backend/static/sw.js`: PWA service worker
- `docker-compose.yaml`: runtime configuration (reads from `.env`)
- `data/`: runtime state (created at first run)

## Quick Start
1) Clone the repo and enter it:
```bash
git clone https://github.com/yellowcooln/meshcore-mqtt-live-map
cd meshcore-mqtt-live-map
```
2) Copy env template:
```bash
cp .env.example .env
```
3) Edit `.env` with your MQTT broker and site metadata.
4) Build and run:
```bash
docker compose up -d --build
```
5) Open: `http://localhost:8080/` (or your `WEB_PORT`)

## Configuration (.env)
Debugging:
- `DEBUG_PAYLOAD` (verbose decode logs)
- `DEBUG_PAYLOAD_MAX` / `PAYLOAD_PREVIEW_MAX` (log truncation limits)

Storage + server:
- `STATE_DIR` (persisted state path)
- `STATE_SAVE_INTERVAL` (seconds between state saves)
- `WEB_PORT` (host port for the web UI)
- `PROD_MODE` (true to require a token for API + WS)
- `PROD_TOKEN` (required token; send via `?token=` or `Authorization: Bearer`)

Site metadata (page title + embeds):
- `SITE_TITLE`
- `SITE_DESCRIPTION`
- `SITE_OG_IMAGE` (optional; leave blank to omit embed image)
- `SITE_URL` (public URL)
- `SITE_ICON`
- `SITE_FEED_NOTE`
- `DISTANCE_UNITS` (`km` or `mi`, default display units)

MQTT:
- `MQTT_HOST`
- `MQTT_PORT`
- `MQTT_USERNAME`
- `MQTT_PASSWORD`
- `MQTT_TRANSPORT` (`websockets`)
- `MQTT_WS_PATH` (usually `/` or `/mqtt`)
- `MQTT_TLS` (`true`)
- `MQTT_TOPIC` (e.g. `meshcore/#`)

Device + route tuning:
- `DEVICE_TTL_SECONDS` (node expiry)
- `TRAIL_LEN` (points per device trail; `0` disables trails)
- `ROUTE_TTL_SECONDS`
- `ROUTE_PATH_MAX_LEN` (skip oversized path-hash lists)
- `ROUTE_PAYLOAD_TYPES` (packet types used for live routes)
- `MESSAGE_ORIGIN_TTL_SECONDS`

History overlay:
- `ROUTE_HISTORY_ENABLED`
- `ROUTE_HISTORY_HOURS`
- `ROUTE_HISTORY_MAX_SEGMENTS`
- `ROUTE_HISTORY_COMPACT_INTERVAL`
- `ROUTE_HISTORY_FILE`
- `ROUTE_HISTORY_PAYLOAD_TYPES`

Heat + online status:
- `HEAT_TTL_SECONDS`
- `MQTT_ONLINE_SECONDS` (online window for status ring)
- `MQTT_ONLINE_TOPIC_SUFFIXES` (comma-separated topics that count as “online”)
- `MQTT_SEEN_BROADCAST_MIN_SECONDS`

Map + LOS:
- `MAP_START_LAT` / `MAP_START_LON` / `MAP_START_ZOOM` (default map view)
- `MAP_DEFAULT_LAYER` (`light`, `dark`, or `topo`; localStorage overrides)
- `MAP_RADIUS_KM` (default `241.4` km ≈ 150mi; `0` disables radius filtering)
- `MAP_RADIUS_SHOW` (`true` draws the radius debug circle)
- `LOS_ELEVATION_URL` (elevation API for LOS tool)
- `LOS_SAMPLE_MIN` / `LOS_SAMPLE_MAX` / `LOS_SAMPLE_STEP_METERS`
- `ELEVATION_CACHE_TTL` (seconds)
- `LOS_PEAKS_MAX` (max peaks shown on LOS profile)

## Common Commands
- Rebuild/restart: `docker compose up -d --build`
- Logs: `docker compose logs -f meshmap-live`
- Snapshot: `curl -s http://localhost:8080/snapshot`
- Stats: `curl -s http://localhost:8080/stats`

## Production Token
Enable protection by setting:
```
PROD_MODE=true
PROD_TOKEN=<random-string>
```

Generate a token:
```
openssl rand -hex 32
```

Use it:
- HTTP: `http://host:8080/snapshot?token=YOUR_TOKEN`
- WS: `ws://host:8080/ws?token=YOUR_TOKEN`
- Or send `Authorization: Bearer YOUR_TOKEN`

## Notes
- The map can only draw routes for hops that appear in your MQTT feed.
- To see full paths, the feed must include Path/Trace packets (payload types 8/9) or multiple observers for fanout.
- Runtime state is persisted to `data/state.json`.
- MQTT disconnects are handled; the client will reconnect when the broker returns.
- Line-of-sight tool: click **LOS tool** and pick two points, or **Shift+click** two nodes to measure LOS between them.
- On mobile, long‑press a node to select it for LOS.
- LOS runs server-side via `/los` (no client-side elevation fetch).
- Dark map also darkens node popups for readability.
- Route styling uses payload type: 2/5 = Message (blue), 8/9 = Trace (orange), 4 = Advert (green).
- If hop hashes collide, the backend skips those hashes (unique-only mapping).
- Coordinates at `0,0` (including string values) are filtered from devices, trails, and routes.

## API
The backend exposes a nodes API for external tools (e.g. MeshBuddy):

- `GET /api/nodes?token=YOUR_TOKEN`
  - Default response: `{"data":{"nodes":[...]}}`
  - Optional: `format=flat` returns `{"data":[...]}`
  - Optional: `mode=delta` applies `updated_since` filtering

Example:
```
https://your-host/api/nodes?token=YOUR_TOKEN
https://your-host/api/nodes?token=YOUR_TOKEN&mode=delta&updated_since=2025-01-01T12:00:00Z
https://your-host/api/nodes?token=YOUR_TOKEN&format=flat
```

Each node includes:
`public_key`, `name`, `device_role` (1/2/3), `last_seen` (ISO), `timestamp` (epoch), and `location` with `latitude`/`longitude`.

## License
[GPL-3.0](https://github.com/yellowcooln/meshcore-mqtt-live-map?tab=License-1-ov-file#).

---

This project was vibe-coded with Codex—please expect rough edges and the occasional bug.
