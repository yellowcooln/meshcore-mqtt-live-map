# Mesh Live Map Reference

Feature behavior, configuration, and API details for Mesh Live Map.
Start with the [README quick start](./README.md#quick-start) or the
[deployment guide](./howto.md). See [VERSIONS.md](./VERSIONS.md) for releases.

## Contents

- [Overview](#overview)
- [Runtime and frontend assets](#runtime-and-frontend-asset-maintenance)
- [Feature behavior](#frontend-ui)
- [Line of sight](#los-line-of-sight-tool)
- [Persistence](#persistence)
- [Configuration reference](#configuration-reference)
- [Production token](#production-token)
- [API](#api)

## Overview
This project renders live MeshCore traffic on a Leaflet + OpenStreetMap map. A FastAPI backend subscribes to MQTT (WSS/TLS or TCP), decodes MeshCore packets using the official [`@michaelhart/meshcore-decoder`](https://www.npmjs.com/package/@michaelhart/meshcore-decoder), and broadcasts device updates and routes over WebSockets to the frontend. Core logic is split into config/state/decoder/LOS/history modules so changes are localized. The UI includes heatmap, LOS tools, map mode toggles, and a 24-hour route history layer.

## Runtime and frontend asset maintenance

Docker uses Python `3.15.1-slim` and official Node `24.22.1` on Debian trixie.
Node's npm 11 is used only in the build stage; the runtime contains the Node
executable, required shared libraries, and the lockfile-resolved decoder.
PyYAML `6.0.3` currently falls back to its pure-Python build on Python 3.15
(no cp315 wheel); do not assume LibYAML acceleration is present.

For non-Docker development, use Node 24 and run `npm ci --prefix backend`
then `npm run build:assets --prefix backend` before serving the app. Generated
`backend/static/vendor/` files are ignored; `backend/package-lock.json` is the
authoritative integrity-checked source. Docker performs these steps itself.
MapLibre `6.16.0` is ESM-only: `map-renderer.mjs` imports its namespace, then the
Leaflet bridge, then starts the existing classic `app.js`. Keep its entry,
shared module, and module worker together. The worker is same-origin and the
page's CSP restricts `worker-src` to `'self'` without `blob:` or `unsafe-eval`.
This worker policy is not a complete script/connect-source allowlist.

MapLibre requires WebGL2. Missing assets or unsupported/failed vector setup
fall back to the light raster map without blocking the dashboard/WebSocket;
selected-layer storage and body theme reflect that actual fallback. Keep
OpenFreeMap, OpenMapTiles and OpenStreetMap attribution visible. Leaflet Heat
is pinned to `0.2.0` with SRI. When renderer assets change, update the CSS SRI
and service-worker cache generation together. OpenFreeMap remains an external
no-SLA provider. Server Pillow previews retain their separate documented
CARTO-key / OpenStreetMap behavior; the interactive renderer is not reused
for those images.

CI builds and runs the test suite in the actual production image, including
the pinned Node decoder. Local amd64 verification does not prove arm64
runtime or hosted publication; verify those independently before release.

## Node identity and historical records

Device records are keyed by their complete device ID. Live updates for the same
ID replace that record in place and preserve its existing peer history. Different
IDs remain separate even when names, abbreviated key prefixes, and coordinates
match; activity counts are not evidence that two identities are the same. Route
hash collisions remain collisions and retain their normal ambiguity safeguards.

Loading persisted state follows the same identity rule. The upgrade does not
retroactively authenticate old metadata, restore records already lost by an older
heuristic, or delete historical corrupt nodes. Continue to use configured
retention for inactive records; any immediate historical cleanup needs verified
complete IDs and a backed-up, explicitly scoped procedure.

## Browser update scheduling

Realtime updates remain FIFO and are not coalesced or dropped to meet a frame
budget. Each drain targets 4 ms of handler work with a 128-message ceiling; one
expensive handler or browser GC can exceed that target. Pending work continues
on later animation frames, with the 1-second timer fallback preserved when
frames do not run. This trades longer total catch-up time for responsiveness
during very large bursts; ordinary low-rate updates still use the next frame.

Hidden pages, including those initially hidden, pause their WebSocket after
60 seconds. Disconnects and replacement snapshots cancel old queued work and
reset the queue cursor; reconnect snapshots remain authoritative. The snapshot
itself is not time-sliced. A short heap sample is not proof of long-session
memory stability, and external basemap/heat/animation costs require separate
profiling before changing their rendering or retention semantics.

After the first accepted WebSocket snapshot, a late startup HTTP response is
ignored before any state mutation, even if the socket has since disconnected.
Socket-open alone does not disable HTTP fallback; HTTP-first loading and normal
WebSocket reconciliation remain supported. Snapshot server time is not a total
ordering/version protocol. The HTTP fallback batches HUD scans while applying
data and restores normal stats updates with `finally`, including on render
errors; it does not time-slice or shrink the snapshot payload.

Node popups use Leaflet content callbacks so closed markers do not format or
retain eagerly rebuilt popup HTML. The callback reads the current device record
on opening; visible popups also refresh on live updates and the periodic status
refresh. Keep the popup content-update action binding: replacing visible content
must not break copy/location/link/QR buttons or attach duplicate handlers. Marker
styles, online expiry and viewport membership still refresh independently of
popup visibility.

Refresh the service-worker cache generation when shipping changed static
assets, including same-version dev builds. Static lookups must use the current
cache name: a retired worker can finish a write after activation cleanup, so a
global cross-generation lookup can resurrect old frontend code. Already-open
pages keep their running JavaScript until reloaded; updated assets remain
cache-first/offline-capable after the new worker takes control.

## Versioning
- `VERSION.txt` holds the current version string; avoid maintaining a second version value in this guide.
- `VERSIONS.md` is an append-only changelog by version.

## Key Paths
- `backend/app.py`: FastAPI server + MQTT lifecycle and websocket broadcasting.
- `backend/config.py`: environment/config constants (shared across backend modules).
- `backend/state.py`: shared runtime state (devices/routes/history) + dataclasses.
- `backend/decoder.py`: payload parsing, official decoder integration, route helpers.
- `backend/los.py`: LOS math + elevation sampling.
- `backend/history.py`: route history persistence + pruning.
- `backend/weather.py`: weather radar country-bounds lookup router.
- `backend/static/index.html`: HTML shell + template placeholders.
- `backend/static/styles.css`: UI styles.
- `backend/static/app.js`: Leaflet UI, markers, legends, routes, tools.
- `backend/static/sw.js`: PWA service worker.
- `docker-compose.yaml`: runtime configuration.
- `deploy/docker-compose.image.yaml`: image-based compose example for prebuilt DockerHub use.
- `deploy/swarm-stack.yaml`: Docker Swarm stack example using the published image.
- `deploy/kubernetes-meshmap.yaml`: Kubernetes deployment example using the published image.
- `data/state.json`: persisted device/trail/roles/names (loaded at startup).
- `data/route_history.jsonl`: rolling 24h route history segments (lines).
- `data/neighbor_overrides.json`: optional neighbor override pairs for route disambiguation.
- `.env`: dev configuration (mirrors template variables).

## Runtime Commands (Typical Workflow)
- Source build: `docker compose up -d --build meshmap`.
- Published-image updates: pull the image, then recreate `meshmap` with `--no-build`.
- After `.env` changes, recreate the service; a plain restart does not reload env-file values.
- `docker compose logs -f meshmap` (watch MQTT + decode logs).
- DockerHub publishing is handled by `.github/workflows/docker-publish.yml`.
- `curl -s http://localhost:8080/snapshot` (current device map).
- `curl -s http://localhost:8080/stats` (counters, route types).
- `curl -s http://localhost:8080/health` (HTTP and MQTT listener health).
- `curl -s http://localhost:8080/debug/last` (recent MQTT decode/debug entries).
- `curl -s http://localhost:8080/peers/<device_id>` (peer counts/distances from independent rolling peer-history buckets; add production authentication when enabled).

## Env Notes (Recent Additions)
- `CUSTOM_LINK_URL` adds a HUD link button; blank hides it.
- `APP_BASE_PATH` lets the map live under a public subpath such as `/livemap`; when blank, the app behaves as a normal root-hosted site.
- `PACKET_ANALYZER_URL` adds a legacy external link on Route Details hashes; leave it blank when using `CORESCOPE_URL`.
- `CORESCOPE_URL` adds CoreScope links in Route Details. Set it to a CoreScope site root such as `https://analyzer.newenglandme.sh`; route hashes use `#/packets/<hash>` when no packet analyzer URL is set, and hop names link to `#/nodes/<pubkey>`.
- `QR_CODE_BUTTON_ENABLED` shows a `Generate QR Code` button in node popups; it opens a theme-aware MeshCore-compatible contact QR modal and defaults to `false`.
- `PEERS_DEFAULT_LIMIT` controls the default number of peers returned by `/peers/{device_id}` when no `?limit=` is passed; default `8`.
- `PEERS_DEFAULT_OPEN` controls whether the Peers tool starts active on page load; default `false`.
- `ROUTE_HISTORY_ENABLED=false` now disables the History tool end-to-end: no History button/panel, no `history=on` activation, and no history payloads in `/snapshot` or the WebSocket snapshot.
- `ROUTE_HISTORY_ENABLED=false` no longer disables peer counts; the Peers tool keeps its own rolling buckets and continues updating from live routes.
- `MAP_BOUNDARY_MODE` switches geographic filtering between `radius` and `polygon`; default is `radius`.
- `MAP_BOUNDARY_FILE` points at the polygon JSON file used when `MAP_BOUNDARY_MODE=polygon`.
- `MAP_BOUNDARY_SHOW` controls whether the active radius/polygon boundary is drawn on the map.
- `MQTT_ONLINE_FORCE_NAMES` forces named nodes to show MQTT online and skips them in peers.
- `MQTT_ONLINE_STATUS_TTL_SECONDS` controls MQTT connected TTL from `/status`.
- `MQTT_ONLINE_INTERNAL_TTL_SECONDS` controls MQTT connected TTL from `/internal`.
- `MQTT_ACTIVITY_PACKETS_TTL_SECONDS` controls feed/activity TTL from `/packets`.
- `MQTT_STATUS_OFFLINE_VALUES` forces offline when recent status payloads report those values.
- `MQTT_ONLINE_TOPIC_SUFFIXES` remains for legacy compatibility; primary connected logic uses status/internal TTLs.
- `LOS_CURVATURE_ENABLED` controls whether LOS includes Earth curvature; default is `true`.
- `LOS_CURVATURE_FACTOR` controls the LOS effective Earth radius multiplier; default is `1.333333`.
- `GIT_CHECK_ENABLED`, `GIT_CHECK_FETCH`, `GIT_CHECK_PATH` enable update checks.
- `GIT_CHECK_INTERVAL_SECONDS` controls how often the server re-checks for updates.
- `ROUTE_MAX_HOP_DISTANCE` prunes hops longer than the configured km distance.
- `ROUTE_INFRA_ONLY` limits route lines to repeaters/rooms (companions excluded from routes).
- `ROUTE_ALLOW_AMBIGUOUS_ONE_BYTE_FALLBACK` restores the legacy route fallback for colliding 1-byte prefixes when conservative routing is too strict; default is `false`.
- `ROUTE_NEIGHBOR_DEBUG=true` logs collided-neighbor route selections for route-resolution diagnostics. It defaults to `false` to prevent high-volume MQTT feeds from flooding stdout.
- The live and History `Path bytes` filters can limit route rendering to `All`, `1-byte`, `2-byte`, `3-byte`, or checkbox combinations without affecting ingest. Browser choices persist locally, env defaults are `ROUTE_BYTE_FILTER_DEFAULT` / `HISTORY_BYTE_FILTER_DEFAULT`, and share links use `route_bytes` / `history_bytes` values such as `all` or `2b,3b`.
- `DEVICE_TTL_HOURS` controls advert/device staleness (default `96` hours).
- `PATH_TTL_SECONDS` controls path staleness (default `172800` seconds / 48h).
- `DEVICE_COORDS_FILE` points to optional coordinate overrides (`/data/device_coords.json` by default).
- `NEIGHBOR_OVERRIDES_FILE` points at an optional JSON file with neighbor pairs to resolve hash collisions.
- `CHANNEL_SECRETS_FILE` points at an optional JSON file of channel secrets used to decrypt sender names from compatible MeshCore group-text packets.
- `BACKUP_ENABLED` enables automatic `.tar.gz` backups of runtime state files.
- `BACKUP_INTERVAL_SECONDS` controls backup frequency; default `43200` seconds (12 hours).
- `BACKUP_DIR` controls where backup archives are written; default `/backup`.
- `BACKUP_RETENTION_DAYS` controls archive pruning; set `0` to disable retention pruning.
- Weather overlay settings:
  - `WEATHER_RADAR_ENABLED`: master switch for radar layer support.
  - `WEATHER_RADAR_COUNTRY_BOUNDS_ENABLED`: set `true` to clip radar tiles to resolved country bounds.
  - `WEATHER_RADAR_COUNTRY_LOOKUP_URL`: keep `/weather/radar/country-bounds` unless using a custom endpoint.
  - `WEATHER_WIND_ENABLED`: set `false` to disable wind in the Weather panel.
  - `WEATHER_WIND_API_URL`: wind data endpoint (Open-Meteo format by default).
  - `WEATHER_WIND_GRID_SIZE`: wind sample density per map view (`1`-`5`).
  - `WEATHER_WIND_REFRESH_SECONDS`: wind refresh interval in seconds (minimum `30`).
- Turnstile protection is gated by `PROD_MODE=true` and controlled by:
  `TURNSTILE_ENABLED`, `TURNSTILE_SITE_KEY`, `TURNSTILE_SECRET_KEY`,
  `TURNSTILE_API_URL`, and `TURNSTILE_TOKEN_TTL_SECONDS`.
- `PROD_MODE`/`PROD_TOKEN` must be passed into the container (compose now forwards them).
- Turnstile auth is used for the map page + WebSocket session flow
  (`meshmap_auth` cookie or `?auth=` on `/ws`), while protected API routes still
  require `PROD_TOKEN`.
- Discord/social embeds can be preserved under Turnstile with
  `TURNSTILE_BOT_BYPASS` and `TURNSTILE_BOT_ALLOWLIST`.

## MQTT + Decoder
- MQTT supports **WebSockets + TLS** or plain TCP. Typical deployments use `MQTT_TRANSPORT=websockets`, `MQTT_TLS=true`, and `MQTT_WS_PATH=/` or `/mqtt`.
- `MQTT_TOPIC` accepts a comma-separated list, so one map can subscribe to multiple topic trees such as `meshcore/BOS/#,meshcore/CON/#`.
- Against `meshcore-mqtt-broker`, the map should normally use a broker
  `SUBSCRIBER_N` username/password pair. Recommended role is `2`
  (`full_access`); role `1` is only needed when you explicitly want
  `/internal` topics or admin-only broker visibility.
- The map does not generate or rotate MeshCore JWT auth tokens on its own, so
  node-style publisher auth (`v1_<PUBLIC_KEY>`) is not the normal credential
  flow for this app.
- Decoder uses Node + the official [`@michaelhart/meshcore-decoder`](https://www.npmjs.com/package/@michaelhart/meshcore-decoder) installed in the container.
- The official package now handles 1-byte, 2-byte, and 3-byte repeater prefixes used by the map.
- `backend/decoder.py` writes a small Node helper and calls it to decode MeshCore packets.
- Route path decoding now accepts mixed hop prefixes: 1-byte (`AB`), 2-byte (`ABCD`), and 3-byte (`ABCDEF`) values in the same path during upgrade rollouts.
- Ambiguous 1-byte prefixes are now handled conservatively: if multiple nodes share the same first byte, the map skips broad closest/time-based guesses and only keeps the hop when there is stronger evidence such as a unique match or neighbor/manual adjacency.

## Frontend UI
- A hidden Pacman route visualization mode is available for live route direction.
- Header includes a GitHub link icon and HUD summary (stats, feed note).
- Base map toggle: Light/Dark/Topo; persisted to localStorage.
- Dark map also darkens node popups for readability.
- Node popups do not auto-pan; dragging the map won’t snap back to keep a popup in view.
- Node popups now let users click the short key under the node name to copy the full public key, copy a direct `node=` map link, and can optionally expose a MeshCore-compatible contact QR modal that shows the node name plus a clickable truncated key that still copies the full public key.
- Legend is collapsible and persisted to localStorage.
- HUD is capped to `90vh` and scrolls to avoid running off-screen.
- Map start position is configurable with `MAP_START_LAT`, `MAP_START_LON`, `MAP_START_ZOOM`.
- Radius filter: `MAP_RADIUS_KM=0` disables filtering; `.env.example` uses `241.4` km (150mi). `MAP_RADIUS_SHOW=true` draws a debug circle.
- Default base layer can be set with `MAP_DEFAULT_LAYER` (`light`, `dark`, `topo`, or `satellite`; localStorage overrides).
- The `satellite` layer uses open Sentinel-2 cloudless imagery from EOX with OpenStreetMap/CARTO labels and borders overlaid.
- The `dark` layer uses the keyless OpenFreeMap Dark vector style through MapLibre GL Leaflet and displays the required OpenFreeMap, OpenMapTiles, and OpenStreetMap attribution.
- `CARTO_BASEMAP_KEY` is optional and is used only for CARTO satellite labels and server-generated dark social preview tiles. Without it, satellite imagery remains available without labels and dark previews fall back to OpenStreetMap.
- Units toggle (km/mi) is site-wide; default from `DISTANCE_UNITS` and stored in localStorage.
- Heat toggle defaults from `HEAT_DEFAULT_ON` on first load before any browser-local override exists.
- Node size slider defaults from `NODE_MARKER_RADIUS` and persists in localStorage.
- History link size slider defaults from `HISTORY_LINK_SCALE` and persists in localStorage.
- Node search (name or key) and a labels toggle (persisted to localStorage).
- The MQTT legend row has an `Only` button for a temporary MQTT-online-only view; it hides non-MQTT markers, trails, routes, hop markers, route details, and peer lines without persisting to localStorage or share links.
- History tool defaults off and opens a right-side panel with a heat filter slider (visibility is not persisted).
- History panel can be dismissed with the X button while keeping history lines visible (toggle History tool to show it again).
- History slider modes: 0 = All, 1 = Blue only, 2 = Yellow only, 3 = Yellow + Red, 4 = Red only.
- History legend swatch is hidden unless the History tool is active.
- Peers tool shows incoming/outgoing neighbors for a selected node, with counts and percentages pulled from dedicated rolling peer-history buckets instead of raw route-history segments. When both endpoints have coordinates, it also shows peer distance in the selected km/mi units.
- The Peers panel title uses the selected node name, the `24h window` label stays under the title, and compact Incoming/Outgoing headings show Rx/Tx packet totals, unique peer counts, and the blue/purple line hint.
- Those peer-history buckets continue recording even when Route History is disabled, so turning off the History tool does not blank the Peers panel after the old window ages out.
- Peer-history buckets are also updated from adjacent route `point_ids` when a hop cannot be rendered as a visible map segment, so peer counts do not drop to zero just because a route endpoint lacked usable coordinates.
- Peers tool skips nodes listed in `MQTT_ONLINE_FORCE_NAMES` (observer listeners).
- Peers row stats are ordered as count, percent, then distance when coordinates are available.
- Coverage tool only appears when `COVERAGE_API_URL` is set; it supports both the legacy `/get-samples` format and MeshMapper `coverage.php` grid-square responses.
- Polygon boundary mode uses the same filter for devices, routes, and history, so the visible map and stored history window stay consistent.
- Use `map_boundary.example.json` for the file format and either `tools/map-boundary-builder.html` or [https://yellowcooln.com/map-boundary-builder/](https://yellowcooln.com/map-boundary-builder/) to generate a polygon JSON file outside the live app.
- MeshMapper-only coverage envs are `COVERAGE_API_KEY`, `COVERAGE_MAX_AGE_DAYS`, `COVERAGE_RATE_LIMIT_COOLDOWN_SECONDS`, `COVERAGE_CACHE_FILE`, and `COVERAGE_SYNC_INTERVAL_SECONDS`; the legacy coverage map does not use them.
- MeshMapper coverage is synced server-side into a local cache file and served from that file to users; it also uses a cooldown after HTTP 429 rate-limit responses.
- MeshMapper viewport refresh now reuses the cached expanded rectangles and only attaches or detaches visible ones, which avoids the old lag from rebuilding the full visible coverage set on every map move.
- Coverage responses are filtered by `COVERAGE_MAX_AGE_DAYS` before they reach the map; default is `30` days, while MeshMapper can still keep the full downloaded dataset in its local cache file.
- Weather is a right-side tool panel with per-layer toggles:
  - Radar toggle controls RainViewer tile layer visibility.
  - Wind toggle controls arrow sampling/rendering and refresh polling.
  - If both radar and wind are disabled by env (`WEATHER_RADAR_ENABLED=false` and `WEATHER_WIND_ENABLED=false`), the Weather button is hidden.
- Trail text in the HUD is only shown when `TRAIL_LEN > 0`; `TRAIL_LEN=0` disables trails entirely. `TRAIL_MAX_SEGMENT_KM` splits visual trails across large coordinate jumps so moved repeaters do not draw stale cross-map lines.
- Hide Nodes toggle hides markers, trails, heat, routes, and history layers.
- Heat toggle can hide the heatmap; it defaults on and the button turns green when heat is off.
- HUD logo uses `SITE_ICON`; if unset or broken it falls back to a small “Map” badge so the toggle still works.
- History line weight was reduced for improved readability.
- Propagation overlay keeps heat/routes/trails/markers above it after render; the panel lives on the right and retains the last render until you generate a new one.
- Propagation origin markers can be removed individually by clicking them.
- Propagation now supports adjustable TX antenna gain (dBi), and defaults Rx AGL to 1m.
- Heatmap includes all route payload types (adverts are no longer skipped).
- MQTT online status shows as a green marker outline and popup status; connected state is derived from `/status` and `/internal` timestamps, while `/packets` is feed activity only. Role detection is now conservative and only trusts explicit role fields and numeric role codes.
- Devices that remain MQTT-online keep their last known map position until MQTT presence expires, even if fresh location packets stop arriving.
- `MQTT_ONLINE_FORCE_NAMES` can force named nodes to show as MQTT online regardless of last seen.
- PWA install support is enabled via `/manifest.webmanifest` and a service worker at `/sw.js`.
- Preview image (`/preview.png`) renders in-bounds device dots for shared links.
- Route lines prefer known neighbor pairs (including overrides) before falling back to closest-hop selection.
- Clicking the HUD logo hides/shows the left panel while tool panels stay open.
- Share button copies a URL with the current view + toggles (including HUD visibility).
- Direct node links can target a specific node/repeater with `node`, `repeater`, `device`, `device_id`, `public_key`, or `pubkey` in the URL.
- Optional custom HUD link appears when `CUSTOM_LINK_URL` is set.
- Update banner shows when `GIT_CHECK_ENABLED=true` and the repo is behind; users can dismiss it per remote SHA.
- Update banner dismissal relies on `.hud-update[hidden]` to ensure the banner actually disappears.
- URL params override stored settings: `lat`, `lon`/`lng`/`long`, `zoom`, `layer`, `history`, `heat`, `coverage`, `weather`, `weather_radar`, `weather_wind`, `labels`, `nodes`, `legend`, `menu`, `units`, `history_filter`, `route_bytes`, `history_bytes`, and direct node focus via `node`/`repeater`/`device_id`.
- Service worker uses `no-store` for navigation requests so env-driven UI toggles (like the radius ring) update without clearing site data.
- HUD scrollbars are custom styled in Chromium for a cleaner look.

## LOS (Line of Sight) Tool
- LOS elevations are fetched via `/los/elevations` (proxy for `LOS_ELEVATION_URL`) and the LOS/relay/profile math runs client-side for realtime updates (fallbacks still use `/los`).
- UI draws an LOS line (green clear / red blocked), renders an elevation profile, and marks peaks.
- LOS now applies Earth curvature by default in both the frontend realtime path and the backend `/los` fallback, using an effective Earth radius factor of `1.333333` unless overridden by env.
- When blocked, a relay suggestion marker (amber/green) highlights a potential mid-point.
- Peak markers show coords + elevation and copy coords on click.
- Hovering the profile or the LOS line syncs a cursor tooltip on the profile.
- Hovering the LOS profile also tracks a cursor on the map and highlights nearby peaks.
- LOS legend items (clear/blocked/peaks/relay) are hidden unless the LOS tool is active.
- Shift+click nodes (or long‑press on mobile) or click the map repeatedly to add LOS pins and build a chained path segment-by-segment.
- The LOS panel also supports direct latitude/longitude pin entry, including a per-pin height field for above-ground-level entry at that pin.
- Drag endpoints to update LOS in realtime. Click a point marker to select it, then click the map to reposition that specific point, or move it from the LOS coordinate editor. LOS heights are stored per pin, not as one shared A/B pair.
- LOS and Propagation stay as separate right-side tools on the same map so path clearance and RF coverage can be planned side by side without merging their controls.

## Device Names + Roles
- Names come from advert payloads or status messages when available.
- Roles are only accepted from explicit decoder fields:
  - `deviceRole`/`deviceRoleName` (MeshCore advert flags), or `role` fields in payload.
  - Name-based role heuristics were removed to avoid mislabels.
- Roles are **not** assigned to the receiver of a packet. For decoded packets, the role applies to the **advertised pubkey** (decoded `location.pubkey` or `decoded_pubkey`).
- Roles persist to `data/state.json` with `device_role_sources`. Only explicit/override roles are restored on load.
- Optional overrides: `data/device_roles.json` can force roles per device_id.

## Routes / Message Paths
Routes are drawn when a packet contains a path list (decoder `pathHashes` or `path`).
Hop prefixes may be 1-byte, 2-byte, or 3-byte, and mixed lists are supported.
When a hop hash collides, the backend prefers neighbor pairs (or overrides) before falling back to closest-hop selection; oversized path lists are ignored via `ROUTE_PATH_MAX_LEN`.
All route hops enforce `ROUTE_MAX_HOP_DISTANCE` to prevent cross‑region jumps.

### 24h History Layer
- Every route segment is persisted to `data/route_history.jsonl` and kept for the last `ROUTE_HISTORY_HOURS`.
- History lines are color‑coded by volume (blue = low, orange = mid, red = high) and weight scales with counts.
- History is hidden by default; the History tool opens a right panel with a slider to filter by heat band.
- The History tool also includes a link size slider; it scales line weight without changing counts.
- History records route modes from `ROUTE_HISTORY_ALLOWED_MODES` (default: `path`).

If routes aren’t visible:
- The packet may only include a single hop (`path: ["24"]`).
- Other repeaters might not be publishing Path/Trace packets, so a message may not include hops.
- Routes and trails drop any `0,0` coordinates (including string values) and will purge bad entries on load.
- Route styling uses payload type: 2/5 = Message (blue), 8/9 = Trace (orange), 4 = Advert (green).
- If history is empty but routes show, confirm `ROUTE_HISTORY_ALLOWED_MODES` includes the active route mode.

## Frontend Map UI
- Legend includes Trace/Message/Advert line styles and Repeater/Companion/Room/Unknown dot colors.
- Unknown markers were made more visible (larger, higher contrast gray).
- Zoom control moved to bottom-right.
- Route lines are thicker/bolder for large screens.
- LOS + Propagation panels appear on the right; on mobile they stack to avoid overlap.

## Persistence
- Devices, trails, names, and roles are saved to `data/state.json`.
- On restart, devices should stay visible if `state.json` exists.
- Route history is persisted separately to `data/route_history.jsonl` (rolling window).
- If roles appear wrong, inspect their source and configured role overrides first. Back up state before any explicitly scoped correction; deleting `state.json` also discards unrelated saved state.
- State load now removes any `0,0` coordinates from devices/trails (including string values).
- When `TRAIL_LEN=0`, stored trails are cleared on load and no new trails are written.

## Troubleshooting Notes
- If map is empty but MQTT is connected, check `/debug/last` for decoded payloads and `payloadType`.
- If markers appear in the wrong place, inspect `decoder_meta` and location fields.
- If roles flip incorrectly, verify `role_target_id` in `/debug/last`.
- If routes don’t show, verify message hashes appear under multiple receivers in MQTT.
- If MQTT online looks wrong, verify `/status` and `/internal` topics are flowing and tune `MQTT_ONLINE_STATUS_TTL_SECONDS` / `MQTT_ONLINE_INTERNAL_TTL_SECONDS`.

## Recent Fixes / Changes Summary
- Added full WSS support and TLS options.
- Integrated meshcore-decoder for advert/location + role parsing.
- Added `/stats`, `/snapshot`, `/debug/last`, `/debug/status` endpoints.
- Added persistence and state reload logic; safer role restore rules.
- Added route drawing for traces/paths/messages with TTL cleanup.
- UI: route legend, role legend, and improved marker styles.
- Roles now apply to advertised pubkey, not receiver.
- Source changes require rebuilding the image and recreating the service. Env-file changes require recreation, not a plain restart.
- LOS elevations are proxied via `/los/elevations` and LOS/relay computations run client-side (with `/los` fallback).
- MQTT online presence now separates connected state (`/status` + `/internal`) from feed activity (`/packets`) with dedicated TTL envs.
- Filters out `0,0` GPS points from devices, trails, and routes (including string values).
- Added 24h route history storage + history toggle with volume-based colors.
- Weather backend logic moved out of `app.py` into `backend/weather.py` and mounted as a router.
- Weather tool now uses its own right-side panel with separate Radar and Wind layer toggles.
- Hide nodes now hides heat/routes/history along with markers/trails.
- Fixed MQTT disconnect callback signature so broker drops don’t crash the MQTT loop.
- Route hash collisions prefer known neighbors (or overrides) before closest-hop selection; long path lists are skipped (`ROUTE_PATH_MAX_LEN`).
- First-hop hash collisions now prefer the closest node to the origin to avoid cross-city mis-picks (Issue #11).
- Show Hops now displays plain prefix values (`Prefix: AB` / `Prefix: ABCD` / `Prefix: ABCDEF`) and follows backend route order directly instead of frontend reversal heuristics.
- Dev-only route debugging: clicking a route line logs hop-by-hop metadata (distances, hashes, origin/receiver) to the browser console when `PROD_MODE=false` (PR #14, credit: https://github.com/sefator).
- Trails can be disabled by setting `TRAIL_LEN=0` (HUD trail text is removed).
- Node marker size can be tuned via `NODE_MARKER_RADIUS` (users can override locally).
- Heat visibility can default on or off via `HEAT_DEFAULT_ON` before local browser state takes over.
- Units toggle defaults from `DISTANCE_UNITS` and persists in localStorage.
- Mobile LOS selection supports long-press on nodes.
- History tool visibility no longer persists (always off unless `history=on` in the URL).
- WebSocket auth accepts `?auth=<turnstile_token>` for Turnstile-gated sessions.
- Protected API routes keep requiring `PROD_TOKEN` even when Turnstile auth is active.
- `/api/nodes` now defaults to flat `data` arrays with a top-level `nodes` alias for client compatibility.
- `/api/nodes` now applies `updated_since` automatically (use `mode=full` to force full snapshots).
- Route IDs are observer-aware (`message_hash:receiver_id`) so multi-observer receptions do not overwrite each other.
- `ROUTE_INFRA_ONLY` direct-route checks now allow rendering when at least one endpoint is infrastructure.
- Propagation range math now uses a user-set TX antenna gain field; Rx AGL default lowered to 1m (credit: C2D).
- Device staleness now supports a dual TTL model using both `DEVICE_TTL_HOURS` and `PATH_TTL_SECONDS` together.
- Multibyte repeater-prefix support (1/2/3-byte) is in place and expected to work, but is not fully field-tested yet.

## Configuration reference

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
- backup size depends on retained state and traffic; monitor disk use rather than assuming a fixed storage budget

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
