# Mesh Live Map

Version: `1.9.7` (see [VERSIONS.md](VERSIONS.md))

Live MeshCore traffic map that renders nodes, routes, and activity in real time on a Leaflet map. The backend subscribes to MQTT over WebSockets+TLS or TCP, decodes MeshCore packets with the official [`@michaelhart/meshcore-decoder`](https://www.npmjs.com/package/@michaelhart/meshcore-decoder), and streams updates to the browser via WebSockets.

Latest version example sites:
 - https://live.bostonme.sh/ - Greater Boston Mesh Map
 - https://map.newenglandme.sh/ - New England Mesh

Other community maps (versions may differ):
- https://meshcore-map.ctmesh.org/ - CTMesh Map Live Map
- https://livemap.wcmesh.com/ - West Coast Mesh Live Map
- https://map.mwmesh.com/ - Utah Mesh Live Map
- https://map.eastmesh.au/ - Aus Eastern Mesh Live Map
- https://mapa.meshcore.cz/ - Czech Republic Live Map
- https://map.meshcorebayreuth.de/ - Bayreuth Live Map
- https://mcmap.cheaterenator.trade/ - Southern Poland

![Live map preview](example.gif)
---
![Live map preview](example2.gif)

## Features
- Live node markers with roles (Repeater, Companion, Room Server, Unknown)
- MQTT online indicator (green outline + popup status) based on MQTT `status`/`internal` topics, with a temporary legend-side MQTT-only map filter and conservative role detection from explicit MQTT role fields only
- Animated route/trace lines
- Hidden arcade Pacman route visualization mode for live route direction
- Dev route inspection: click a route line in dev (`PROD_MODE=false`) to log hop-by-hop details in the browser console, including resolved `point_id` / `point_label` data (PR #14, credit: https://github.com/sefator)
- Heat map for the last 10 minutes of message activity (includes adverts)
- Persistent device state and optional trails (disable with `TRAIL_LEN=0`)
- 24-hour route history tool with volume-based coloring, click-to-view packet details, a heat-band slider, and a link-size slider
- History panel can be dismissed with an X without hiding history lines (re-open via History tool)
- Peers tool showing incoming/outgoing neighbors with on-map lines, compact Rx/Tx headings, peer counts, packet totals, and per-peer count/percent/distance stats
- Coverage layer from the legacy [coverage map API](https://github.com/nullrouten0/meshcore-coverage-map) or the new [MeshMapper Coverage API](https://github.com/MeshMapper/MeshMapper_Wiki/blob/main/docs/coverage-api.md) (button hidden when not configured)
- MeshMapper coverage viewport sync reuses cached rectangles instead of recreating every visible square on each pan/zoom, which keeps the coverage layer responsive on larger meshes
- Weather tool panel with independent Radar and Wind toggles
- Update available banner (git local vs upstream) with dismiss
- UI controls: legend toggle, dark map, topo map, units toggle (km/mi), labels toggle, hide nodes, heat toggle, temporary MQTT-only filter
- Route path-byte filter for `All`, `1-byte`, `2-byte`, or `3-byte` live route views, with matching hop markers and Route Details
- Share button that copies a URL with current view + settings
- Optional `APP_BASE_PATH` support for hosting the map under a subpath such as `/livemap`
- URL parameters to open the map at a specific view (center, zoom, toggles)
- Node search by name or public key
- Node popups can copy the full public key from the short key shown under the node name, copy a direct `node=` map link, and optionally expose a MeshCore contact QR modal that shows the node name plus a clickable truncated key
- Adjustable node size slider (defaults from env, saves locally)
- LOS tool with elevation profile + peak markers, hover sync, direct lat/lon pin entry, realtime draggable endpoints (Shift+click or long‑press nodes), and Earth-curvature-aware blockage checks
- Embeddable metadata (Open Graph/Twitter tags) driven by env vars
- Preview image renders in-bounds device dots for shared links
- Route pruning via neighbor-aware closest-hop selection + max hop distance (configurable)
- Route lines are derived from decoded packet paths only (no MQTT observer/receiver fallback)
- First-hop collision fix prefers the closest repeater/room to the sender (Issue #11)
- Mixed hop-prefix support for path decoding (`AB`, `ABCD`, and `ABCDEF`, including mixed networks during rollout)
- Optional legacy route fallback for colliding 1-byte hop prefixes via `ROUTE_ALLOW_AMBIGUOUS_ONE_BYTE_FALLBACK=true`
- Propagation panel lives on the right and keeps the last render until you generate a new one (click an origin marker to remove it)
- Propagation tool supports adjustable **TX antenna gain (dBi)**, and now defaults **Rx AGL** to **1m**
- Installable PWA (manifest + service worker) for Add to Home Screen
- Click the logo to hide/show the left HUD panel while tools stay open

## Project Structure
- `backend/app.py`: FastAPI server wiring, MQTT lifecycle, WS broadcast
- `backend/config.py`: environment configuration
- `backend/state.py`: shared in-memory state + dataclasses
- `backend/decoder.py`: payload parsing + multibyte MeshCore decoder integration
- `backend/los.py`: LOS math + elevation helpers
- `backend/history.py`: route history persistence + pruning
- `backend/weather.py`: weather radar country-bounds lookup API
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
   - See `howto.md` for a step-by-step guide to setting up the MQTT server and this live map.
4) Build and run:
```bash
docker compose up -d --build
```
5) Open: `http://localhost:8080/` (or your `WEB_PORT`)

## Prebuilt Image
If you do not want to clone the repo and build locally, use the published image:

```text
yellowcooln/meshcore-mqtt-live-map:latest
```

Example with Docker Compose / Portainer stack:

```yaml
services:
  meshmap:
    image: yellowcooln/meshcore-mqtt-live-map:latest
    ports:
      - "8080:8080"
    env_file:
      - .env
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/health', timeout=3).read()"]
      interval: 30s
      timeout: 5s
      retries: 3
      start_period: 30s
    restart: unless-stopped
    volumes:
      - ./data:/data
      - ./backup:/backup
```

Repo examples:
- `deploy/docker-compose.image.yaml`
- `deploy/swarm-stack.yaml`
- `deploy/kubernetes-meshmap.yaml`

Do not bind-mount a copied `app.py` over `/app/app.py`. A whole-file override
masks the application bundled in every newer image, so image upgrades cannot
deliver backend fixes. Keep custom behavior in configuration or upstream it;
if a temporary override is unavoidable, rebase and retest it for every image.

The Compose healthcheck marks the container unhealthy when MQTT or the
WebSocket broadcaster stops. Docker Compose does not restart an unhealthy
container by itself; use an orchestrator/autoheal policy if automatic recovery
from process-wide hangs is required.

## Configuration (.env)
Debugging:
- `DEBUG_PAYLOAD` (verbose decode logs)
- `DEBUG_PAYLOAD_MAX` / `PAYLOAD_PREVIEW_MAX` (log truncation limits)
- `DEBUG_LAST_MAX` / `DEBUG_STATUS_MAX` (debug endpoint entry caps)

Storage + server:
- `STATE_DIR` (persisted state path)
- `BACKUP_ENABLED` (enable automatic `.tar.gz` backups)
- `BACKUP_INTERVAL_SECONDS` (seconds between backups; default `43200` / 12 hours)
- `BACKUP_DIR` (backup archive directory; default `/backup`)
- `BACKUP_RETENTION_DAYS` (delete backup archives older than N days; `0` disables pruning)
- `STATE_FILE` (full state file path override)
- `DEVICE_ROLES_FILE` (optional role override JSON file)
- `DEVICE_COORDS_FILE` (optional coordinate override JSON file; default `/data/device_coords.json`)
- `NEIGHBOR_OVERRIDES_FILE` (optional JSON mapping for neighbor overrides)
- `CHANNEL_SECRETS_FILE` (optional JSON file of MeshCore channel secrets for decrypting sender names from group text packets)
- `STATE_SAVE_INTERVAL` (seconds between state saves)
- `WEBSOCKET_SEND_TIMEOUT_SECONDS` (per-client WebSocket send timeout; default `10`, allowing time for JWT authentication swaps)
- `WEB_PORT` (host port for the web UI)
- `PROD_MODE` (true to require a token for API + WS)
- `PROD_TOKEN` (required token; send via `?token=` or `Authorization: Bearer`)

Backups:
- when enabled, the server writes timestamped `meshmap-backup-YYYY-MM-DDTHH-MM-SS.tar.gz` archives to `BACKUP_DIR`
- backup archives are separate from `/data` by default; the compose file mounts `./backup:/backup`
- with the default backup settings (`12` hours, `7` days retention), expect under `30 MB` of backup storage on a network around `250` nodes

Turnstile protection (prod-only):
- `TURNSTILE_ENABLED` (requires `PROD_MODE=true`)
- `TURNSTILE_SITE_KEY`
- `TURNSTILE_SECRET_KEY`
- `TURNSTILE_API_URL`
- `TURNSTILE_TOKEN_TTL_SECONDS`
- `TURNSTILE_BOT_BYPASS` (allowlist embed bots like Discord)
- `TURNSTILE_BOT_ALLOWLIST` (comma-separated user-agent tokens; default: `discordbot,twitterbot,slackbot,facebookexternalhit,linkedinbot,telegrambot,whatsapp,skypeuripreview,redditbot`)

Site metadata (page title + embeds):
- `SITE_TITLE`
- `SITE_DESCRIPTION`
- `SITE_OG_IMAGE` (optional; leave blank to omit embed image)
- `SITE_URL` (public URL)
- `APP_BASE_PATH` (optional public subpath such as `/livemap`; leave blank for normal root hosting)
- `SITE_ICON`
- `SITE_FEED_NOTE`
- `CUSTOM_LINK_URL` (optional extra HUD link; hidden when blank)
- `PACKET_ANALYZER_URL` (optional legacy analyzer base URL for Route Details hashes; leave blank when using `CORESCOPE_URL`)
- `CORESCOPE_URL` (optional CoreScope base URL; e.g. `https://analyzer.newenglandme.sh`; Route Details hashes link to `#/packets/<hash>` when `PACKET_ANALYZER_URL` is blank, and hop names link to `#/nodes/<pubkey>`)
- `QR_CODE_BUTTON_ENABLED` (show a `Generate QR Code` button in node popups that opens a theme-aware MeshCore-compatible contact QR modal; default `false`)
- `PEERS_DEFAULT_LIMIT` (optional default number of incoming/outgoing peers returned by `/peers/{device_id}`; default `8`)
- `PEERS_DEFAULT_OPEN` (optional `true`/`false`; opens the Peers tool active on page load when `true`; default `false`)
- `MAP_BOUNDARY_MODE` (`radius` or `polygon`; default `radius`)
- `MAP_BOUNDARY_FILE` (JSON file used when `MAP_BOUNDARY_MODE=polygon`; default `/data/map_boundary.json`)
- `MAP_BOUNDARY_SHOW` (draw the active radius/polygon boundary overlay on the map)
- `DISTANCE_UNITS` (`km` or `mi`, default display units)
- `HEAT_DEFAULT_ON` (`true` or `false`, default first-load heat visibility before browser overrides)
- `NODE_MARKER_RADIUS` (default node marker size in pixels)

MQTT:
- `MQTT_HOST`
- `MQTT_PORT`
- `MQTT_USERNAME` (for `meshcore-mqtt-broker`, usually a broker-side `SUBSCRIBER_N` username, not `v1_<PUBLIC_KEY>`)
- `MQTT_PASSWORD` (matching subscriber password from the broker config)
- `MQTT_TRANSPORT` (`tcp` or `websockets`)
- `MQTT_WS_PATH` (usually `/` or `/mqtt`)
- `MQTT_TLS` (`true`)
- `MQTT_TLS_INSECURE` (default `false`; when `true`, disables certificate and hostname verification, allowing expired or self-signed certificates; ignores `MQTT_CA_CERT`. TLS remains encrypted, but the broker's identity is not authenticated. Prefer renewing the certificate or configuring a trusted CA.)
- `MQTT_CA_CERT` (custom CA bundle path)
- `MQTT_CLIENT_ID` (optional client id override)
- `MQTT_TOPIC` (e.g. `meshcore/#` or `meshcore/#,other/topic/+` for multiple topics)

Coverage layer:
- `COVERAGE_API_URL` (legacy coverage-map base URL, or `https://meshmapper.net`; button hidden when blank)
- `COVERAGE_API_KEY` (MeshMapper only; optional single key for `https://meshmapper.net/coverage.php`; not used by legacy coverage maps)
- `COVERAGE_API_KEYS` (MeshMapper only; optional comma-separated replacement for `COVERAGE_API_KEY`. Each key is fetched independently, then coverage squares are merged and duplicate squares are removed. Set `COVERAGE_API_URL=https://meshmapper.net` rather than embedding a key in the URL.)
- `COVERAGE_MAX_AGE_DAYS` (MeshMapper only; default `30`; only coverage from the last N days is sent to the map, while MeshMapper can still cache the full upstream dataset locally; not used by legacy coverage maps)
- `COVERAGE_RATE_LIMIT_COOLDOWN_SECONDS` (MeshMapper only; fallback cooldown after HTTP 429 if the API does not report `resets_in_hours`)
- `COVERAGE_CACHE_FILE` (MeshMapper only; local JSON file served to users after server-side sync)
- `COVERAGE_SYNC_INTERVAL_SECONDS` (MeshMapper only; how often the server refreshes the local coverage cache file, default hourly)

Routing accuracy:
- Ambiguous 1-byte hop prefixes are now handled conservatively on large meshes.
- If multiple nodes share the same first byte, the map no longer guesses from broad closest/time-based fallbacks.
- Colliding 1-byte hops only resolve when there is stronger evidence such as a unique candidate or known neighbor/manual adjacency.
- `ROUTE_ALLOW_AMBIGUOUS_ONE_BYTE_FALLBACK=true` restores the pre-`v1.7.0` fallback behavior for networks that need the older route rendering.

Weather overlay:
- `WEATHER_RADAR_ENABLED`:
  master switch for radar support. If both `WEATHER_RADAR_ENABLED=false` and `WEATHER_WIND_ENABLED=false`, the Weather button is hidden.
- `WEATHER_RADAR_COUNTRY_BOUNDS_ENABLED`:
  set `true` to keep radar inside the country around the map center; set `false` for unrestricted radar tiles.
- `WEATHER_RADAR_COUNTRY_LOOKUP_URL`:
  keep default (`/weather/radar/country-bounds`) unless you run your own country-bounds endpoint.
- `WEATHER_WIND_ENABLED`:
  set `true` to show Wind in the Weather panel, or `false` to disable wind entirely.
- `WEATHER_WIND_API_URL`:
  endpoint for wind data (default is Open-Meteo; custom APIs must provide current wind speed/direction).
- `WEATHER_WIND_GRID_SIZE`:
  number of wind samples per side (`1`-`5`); larger grid gives more arrows but increases API load.
- `WEATHER_WIND_REFRESH_SECONDS`:
  wind refresh interval (seconds, minimum `30`); increase this to reduce API calls.

Device + route tuning:
- `DEVICE_TTL_HOURS` (advert/device stale window; default `96`)
- `PATH_TTL_SECONDS` (path stale window; default `172800`)
- `TRAIL_LEN` (points per device trail; `0` disables trails)
- `TRAIL_MAX_SEGMENT_KM` (max drawn distance between consecutive trail points; default `10`, `0` disables splitting)
- `ROUTE_TTL_SECONDS`
- `ROUTE_PATH_MAX_LEN` (skip oversized path-hash lists)
- `ROUTE_PAYLOAD_TYPES` (packet types used for live routes)
- `ROUTE_MAX_HOP_DISTANCE` (km; prunes unrealistic hops)
- `ROUTE_INFRA_ONLY` (true = only repeaters/rooms in route lines)
- `ROUTE_NEIGHBOR_DEBUG` (logs collided-neighbor route selections; default `false` to avoid high-volume log noise)
- `ROUTE_BYTE_FILTER_DEFAULT` (default live Path bytes checkbox state; `all`, `1b`, `2b`, `3b`, or comma combos)
- `SHOW_REPEATERS_DEFAULT`, `SHOW_COMPANIONS_DEFAULT`, `SHOW_ROOM_SERVERS_DEFAULT`, and `SHOW_UNKNOWN_DEFAULT` (initial role visibility before browser/share overrides)
- `MESSAGE_ORIGIN_TTL_SECONDS`

History overlay:
- `ROUTE_HISTORY_ENABLED`
  - Set `false` to disable Route History entirely, including the History button/panel and history payloads.
  - Peer counts still continue working when this is `false`; the Peers tool uses separate rolling peer-history buckets.
- `ROUTE_HISTORY_HOURS`
- `ROUTE_HISTORY_MAX_SEGMENTS`
- `ROUTE_HISTORY_COMPACT_INTERVAL`
- `ROUTE_HISTORY_FILE`
- `ROUTE_HISTORY_PAYLOAD_TYPES`
- `ROUTE_HISTORY_ALLOWED_MODES` (comma-separated route modes; default `path`)
- `HISTORY_BYTE_FILTER_DEFAULT` (default History Path bytes checkbox state; `all`, `1b`, `2b`, `3b`, or comma combos)
- `HISTORY_LINK_SCALE` (default history line weight multiplier)

Heat + online status:
- `HEAT_DEFAULT_ON` (default Heat toggle state for first load; local browser preference or `?heat=` can still override it)
- `HEAT_TTL_SECONDS`
- `MQTT_ONLINE_SECONDS` (legacy/global fallback TTL for MQTT presence)
- `MQTT_ONLINE_STATUS_TTL_SECONDS` (how long `/status` keeps a node connected)
- `MQTT_ONLINE_INTERNAL_TTL_SECONDS` (how long `/internal` keeps a node connected)
- `MQTT_ACTIVITY_PACKETS_TTL_SECONDS` (how long `/packets` counts as feeding activity)
- `MQTT_STATUS_OFFLINE_VALUES` (comma-separated status values that force offline, even inside TTL)
- `MQTT_ONLINE_TOPIC_SUFFIXES` (legacy compatibility setting; primary online source is status/internal TTLs)
- `MQTT_SEEN_BROADCAST_MIN_SECONDS`
- `MQTT_ONLINE_FORCE_NAMES` (comma-separated names to force as MQTT online; also excluded from peers)

Update checks:
- `GIT_CHECK_ENABLED` (show update banner if repo is behind)
- `GIT_CHECK_FETCH` (fetch before comparing)
- `GIT_CHECK_PATH` (path to git repo in the container)
- `GIT_CHECK_INTERVAL_SECONDS` (defaults to 43200 = 12h)

Map + LOS:
- `MAP_START_LAT` / `MAP_START_LON` / `MAP_START_ZOOM` (default map view)
- `MAP_DEFAULT_LAYER` (`light`, `dark`, `topo`, or `satellite`; localStorage overrides)
  - `satellite` uses open Sentinel-2 cloudless imagery from EOX with OpenStreetMap/CARTO labels and borders overlaid.
- The `dark` layer uses the keyless OpenFreeMap Dark vector style through MapLibre GL Leaflet, with OpenFreeMap, OpenMapTiles, and OpenStreetMap attribution. No API key is required.
- `CARTO_BASEMAP_KEY` is optional and is used only for CARTO satellite labels and server-generated dark social preview tiles. Keep it per-project and out of Git. Without a key, satellite imagery remains available without the CARTO label overlay and dark previews fall back to OpenStreetMap. See [Configure an optional CARTO key](howto.md#optional-carto-key-for-satellite-labels-and-dark-previews).
- `MAP_RADIUS_KM` (`0` disables radius filtering; `.env.example` uses `241.4` km ≈ 150mi)
- `MAP_RADIUS_SHOW` (`true` draws the radius debug circle)
- `LOS_ELEVATION_URL` (elevation API for LOS tool)
- `LOS_ELEVATION_PROXY_URL` (server proxy for client-side LOS elevation fetches)
- `LOS_SAMPLE_MIN` / `LOS_SAMPLE_MAX` / `LOS_SAMPLE_STEP_METERS`
- `ELEVATION_CACHE_TTL` (seconds)
- `LOS_CURVATURE_ENABLED` (default `true`; include Earth curvature in LOS calculations)
- `LOS_CURVATURE_FACTOR` (default `1.333333`; effective Earth radius multiplier used by the LOS tool)
- `LOS_PEAKS_MAX` (max peaks shown on LOS profile)

Decoder helpers:
- `DECODE_WITH_NODE` (toggle Node-based MeshCore decoder usage)
- `NODE_DECODE_TIMEOUT_SECONDS`
- `DIRECT_COORDS_MODE` (`topic` or `payload`)
- `DIRECT_COORDS_TOPIC_REGEX` (topic matcher for direct coords)
- `DIRECT_COORDS_ALLOW_ZERO` (allow `0,0` coords if `true`)

## Common Commands
- Rebuild/restart: `docker compose up -d --build`
- Logs: `docker compose logs -f meshmap-live`
- Tests: `pip install -r requirements-dev.txt && pytest -q`
- Snapshot: `curl -s http://localhost:8080/snapshot`
- Stats: `curl -s http://localhost:8080/stats`
- Health: `curl -s http://localhost:8080/health`

## Production Token
Enable protection by setting:
```
PROD_MODE=true
PROD_TOKEN=<random-string>
```

Turnstile protection is also gated by `PROD_MODE=true`. If `PROD_MODE=false`,
Turnstile stays off even when `TURNSTILE_ENABLED=true`.
When Turnstile is enabled, browser sessions can authenticate the map + WebSocket
with a Turnstile auth token (`meshmap_auth` cookie or `?auth=` on `/ws`), but
protected API routes (`/snapshot`, `/api/nodes`, `/peers/{id}`) still require
`PROD_TOKEN`.
Ensure `PROD_MODE`/`PROD_TOKEN` are set in `.env` (docker-compose passes them through).

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
- To see full paths, the feed must include Path/Trace packets (payload types 8/9).
- Runtime state is persisted to `data/state.json`.
- MQTT disconnects are handled; the client will reconnect when the broker returns.
- When using Michael Hart's `meshcore-mqtt-broker`, the map should usually log
  in with a broker `SUBSCRIBER_N` account such as
  `SUBSCRIBER_1=meshmap:change-this-password:2`.
- The map does not mint MeshCore JWT auth tokens by itself, so node-style
  publisher auth (`v1_<PUBLIC_KEY>`) is not the normal setup for this app.
- Subscriber role `2` is the recommended broker role for most maps; role `1`
  is only needed if you explicitly want `/internal` topics or other admin-only
  broker visibility.
- MQTT connectivity (`MQTT online`) is based on `/status` + `/internal`; `/packets` is treated as feed activity and does not by itself mark a node online.
- If a node is still MQTT-online but has stopped sending fresh location packets, the map keeps its last known position visible until MQTT presence expires.
- The legend `MQTT online` row includes an `Only` filter that temporarily hides non-MQTT markers, trails, routes, hop markers, route details, and peer lines. This filter is local to the current page view only; it is not saved in browser storage and is not added to share links.
- Live route IDs are observer-aware (`message_hash:receiver_id`) so the same
  message seen by multiple MQTT observers does not overwrite active lines.
- Line-of-sight tool: click **LOS tool** and add pins to build a chained path, or **Shift+click** nodes to place LOS pins from existing nodes. You can also add pins directly from the LOS panel with latitude/longitude + pin height inputs. Drag endpoints or click a pin and then click the map to move that specific point, or update its coordinates from the panel. Heights are stored per pin.
- On mobile, long‑press a node to select it for LOS.
- LOS elevations are fetched via `/los/elevations` and LOS/relay math runs client-side (with `/los` fallback).
- LOS now includes Earth curvature by default using an effective Earth radius factor of `1.333333`, unless you override the LOS curvature envs.
- LOS and Propagation stay as separate tools on the same map so path obstruction checks and RF coverage planning can be used together without combining their controls into one panel.
- History tool always loads off (use the button or `history=on` in the URL).
- Peers tool uses dedicated rolling peer-history buckets so 24h counts stay accurate even on high-volume meshes; peer links are still counted from route `point_ids` even when a hop could not be drawn on the map, distances are shown in the selected km/mi units when both endpoints have coordinates, compact headings show Rx/Tx packet totals and unique peer counts, and forced MQTT listeners are excluded from peer lists.
- Route History and Peers are now independent: `ROUTE_HISTORY_ENABLED=false` disables the History tool and history payloads, but peer counts continue updating from live routes.
- URL params override stored settings: `lat`, `lon`/`lng`/`long`, `zoom`, `layer`, `history`, `heat`, `coverage`, `weather`, `weather_radar`, `weather_wind`, `labels`, `nodes`, `legend`, `menu`, `units`, `history_filter`, `route_bytes`, `route_nodes`, `history_bytes`, `roles`, and direct node focus via `node`/`repeater`/`device_id`.
- Dark map also darkens node popups for readability.
- Route styling uses payload type: 2/5 = Message (blue), 8/9 = Trace (orange), 4 = Advert (green).
- Turnstile browser auth (`meshmap_auth`/`?auth=`) is for map + WS session flow;
  protected API endpoints still require `PROD_TOKEN`.
- If hop hashes collide, the backend prefers known neighbors (or overrides) before picking the closest hop and pruning beyond `ROUTE_MAX_HOP_DISTANCE`.
- Route hop prefixes can now be 1-byte, 2-byte, or 3-byte; Show Hops displays `Prefix: AB` / `Prefix: ABCD` / `Prefix: ABCDEF`.
- Device pruning can use both stale windows together (`DEVICE_TTL_HOURS` and `PATH_TTL_SECONDS`).
- Coordinates at `0,0` (including string values) are filtered from devices, trails, and routes.
- With Turnstile enabled, common embed bots (Discord, Slack, etc.) can be
  allowlisted via `TURNSTILE_BOT_BYPASS` and `TURNSTILE_BOT_ALLOWLIST`.

## API
The backend exposes a nodes API for external tools (e.g. MeshBuddy):

- `GET /api/nodes?token=YOUR_TOKEN`
  - Default response: `{"data":[...], "nodes":[...]}`
  - Optional: `format=nested` returns `{"data":{"nodes":[...]}}`
  - `updated_since` applies delta filtering automatically
  - Optional: `mode=full` (or `all`/`snapshot`) forces full-list response

Example:
```
https://your-host/api/nodes?token=YOUR_TOKEN
https://your-host/api/nodes?token=YOUR_TOKEN&updated_since=2025-01-01T12:00:00Z
https://your-host/api/nodes?token=YOUR_TOKEN&format=nested
https://your-host/api/nodes?token=YOUR_TOKEN&mode=full
```

Each node includes:
`public_key`, `name`, `device_role` (1/2/3), `last_seen` (ISO), `timestamp` (epoch), and `location` with `latitude`/`longitude`.

Peer summary:
- `GET /peers/{device_id}?token=YOUR_TOKEN`
  - Returns incoming/outgoing neighbors with counts/percentages from route history and `distance_m` when both endpoints have coordinates.

Boundary mode:
- Default behavior remains radius-based filtering.
- Set `MAP_BOUNDARY_MODE=polygon` to filter nodes, routes, and history against a polygon from `MAP_BOUNDARY_FILE`.
- Use `map_boundary.example.json` as the file format reference.
- The repo includes a standalone builder at `tools/map-boundary-builder.html`; a hosted copy is available at [https://yellowcooln.com/map-boundary-builder/](https://yellowcooln.com/map-boundary-builder/).
- Use either copy to click points on the map and export `map_boundary.json`.
  - Returns incoming/outgoing neighbors with counts/percentages from route history.

## License
[GPL-3.0](https://github.com/yellowcooln/meshcore-mqtt-live-map?tab=License-1-ov-file#).

---

This project was vibe-coded with Codex—please expect rough edges and the occasional bug.

## Star History

<a href="https://www.star-history.com/?repos=yellowcooln%2Fmeshcore-mqtt-live-map&type=date&legend=top-left">
 <picture>
   <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/chart?repos=yellowcooln/meshcore-mqtt-live-map&type=date&theme=dark&legend=top-left" />
   <source media="(prefers-color-scheme: light)" srcset="https://api.star-history.com/chart?repos=yellowcooln/meshcore-mqtt-live-map&type=date&legend=top-left" />
   <img alt="Star History Chart" src="https://api.star-history.com/chart?repos=yellowcooln/meshcore-mqtt-live-map&type=date&legend=top-left" />
 </picture>
</a>
