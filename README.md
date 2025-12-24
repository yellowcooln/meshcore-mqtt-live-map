# Mesh Live Map

Live MeshCore traffic map that renders nodes, routes, and activity in real time on a Leaflet map. The backend subscribes to MQTT over WebSockets + TLS, decodes MeshCore packets with `@michaelhart/meshcore-decoder`, and streams updates to the browser via WebSockets.

Live example: https://live.bostonme.sh/

## Features
- Live node markers with roles (Repeater, Companion, Room Server, Unknown)
- Animated route/trace lines and message fanout
- Heat map for the last 10 minutes of message activity
- Persistent device state and trails
- UI controls: legend toggle, dark map, topo map
- Embeddable metadata (Open Graph/Twitter tags) driven by env vars

## Project Structure
- `backend/app.py`: FastAPI server, MQTT ingest, MeshCore decoding, persistence
- `backend/static/index.html`: Leaflet UI, map rendering, route/heat display
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
Required MQTT settings:
- `MQTT_HOST`
- `MQTT_PORT`
- `MQTT_USERNAME`
- `MQTT_PASSWORD`
- `MQTT_TRANSPORT` (`websockets`)
- `MQTT_WS_PATH` (usually `/` or `/mqtt`)
- `MQTT_TLS` (`true`)
- `MQTT_TOPIC` (e.g. `meshcore/#`)

Site metadata (used in page title + embeds):
- `SITE_TITLE`
- `SITE_DESCRIPTION`
- `SITE_OG_IMAGE` (optional; leave blank to omit embed image)
- `SITE_URL` (public URL)
- `SITE_ICON`
- `SITE_FEED_NOTE`

Runtime tuning:
- `WEB_PORT` (host port for the web UI)
- `DEVICE_TTL_SECONDS` (node expiry)
- `TRAIL_LEN` (points per device trail)
- `ROUTE_TTL_SECONDS`
- `HEAT_TTL_SECONDS`
- `MESSAGE_ORIGIN_TTL_SECONDS`
- `DEBUG_PAYLOAD` (verbose decoding logs)
- `LOS_ELEVATION_URL` (elevation API for LOS tool)
- `LOS_SAMPLE_MIN` / `LOS_SAMPLE_MAX` / `LOS_SAMPLE_STEP_METERS`
- `ELEVATION_CACHE_TTL` (seconds)

## Common Commands
- Rebuild/restart: `docker compose up -d --build`
- Logs: `docker compose logs -f meshmap-live`
- Snapshot: `curl -s http://localhost:8080/snapshot`
- Stats: `curl -s http://localhost:8080/stats`

## Notes
- The map can only draw routes for hops that appear in your MQTT feed.
- To see full paths, the feed must include Path/Trace packets (payload types 8/9) or multiple observers for fanout.
- Runtime state is persisted to `data/state.json`.
- Line-of-sight tool: click **LOS tool** and pick two points, or **Shift+click** two nodes to measure LOS between them.

## License
[GPL-3.0](https://github.com/yellowcooln/meshcore-mqtt-live-map?tab=License-1-ov-file#).

---

This project was entirely vibe coded with Codex so always expect issues and bugs.
