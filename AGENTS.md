# Repository Guidelines

Current version: `1.9.6` (see `VERSIONS.md`).

## Project Structure & Module Organization
- `backend/app.py` wires FastAPI routes, MQTT lifecycle, and websocket broadcast flow.
- `backend/config.py` centralizes env configuration.
- `backend/state.py` holds shared in-memory state + dataclasses.
- `backend/decoder.py` contains payload parsing, multibyte MeshCore decoding, and route helpers.
- `backend/los.py` contains LOS math + elevation fetch helpers.
- `backend/history.py` handles 24h route history persistence/cleanup.
- `backend/static/index.html` is the HTML shell + template placeholders.
- `backend/static/styles.css` holds all UI styles.
- `backend/static/app.js` holds all client-side map logic.
- `backend/static/sw.js` is the PWA service worker.
- `backend/requirements.txt` and `backend/Dockerfile` define Python and Node dependencies.
- `docker-compose.yaml` runs the service as `meshmap-live`.
- `.github/workflows/docker-publish.yml` publishes the prebuilt DockerHub image.
- `deploy/` contains image-based examples for compose, Swarm, and Kubernetes.
- `data/` stores persisted state (`state.json`), route history (`route_history.jsonl`), role overrides (`device_roles.json`), and optional neighbor overrides (`neighbor_overrides.json`).
- `.env` holds dev runtime settings; `.env.example` mirrors template defaults.
- `VERSION.txt` tracks the current version (now `1.9.8`); append changes in `VERSIONS.md`.

## Build, Test, and Development Commands
- `docker compose up -d --build` rebuilds and restarts the backend (preferred workflow).
- `docker compose logs -f meshmap-live` follows server logs for MQTT activity.
- `curl -s http://localhost:8080/snapshot` checks current device state.
- `curl -s http://localhost:8080/stats` shows ingest/route counters.
- `curl -s http://localhost:8080/debug/last` inspects recent decoded packets.

## Coding Style & Naming Conventions
- Python in `backend/*.py` uses **2-space indentation**; keep it consistent.
- The project enforces an **80-character column limit** for Python code to maintain readability.
- Formatting is handled by `yapf` using the config in `backend/.style.yapf`.
  - To format code manually: `yapf --in-place --recursive --style backend/.style.yapf backend/`
- HTML/CSS/JS in `backend/static/index.html` uses 2 spaces as well.
- Use lowercase, underscore-separated names for Python variables/functions.
- Prefer small helper functions for parsing/normalization; keep logging concise.

## Testing Guidelines
- Run automated tests with `pip install -r requirements-dev.txt && pytest -q`.
- Validate runtime behavior manually with `/snapshot`, `/stats`, and `/debug/last`.

## Commit & Pull Request Guidelines
- No git history is available in this workspace, so there is no established commit convention.
- If you add git later, use short, imperative commit messages and describe behavioral changes in PRs.

## Configuration & Operations
- Most behavior is controlled by `.env` (MQTT host, TLS, topics, TTLs, map start lat/lon/zoom, MQTT online window, default map layer).
- Current dev defaults: `DEVICE_TTL_HOURS=96`, `PATH_TTL_SECONDS=172800`, `MQTT_ONLINE_SECONDS=600`, `ROUTE_TTL_SECONDS=60`, `TRAIL_LEN=0`, `DISTANCE_UNITS=mi`.
- Node size default is `NODE_MARKER_RADIUS` (pixels); users can override via the HUD slider.
- History link size default is `HISTORY_LINK_SCALE`; users can override via the History panel slider.
- Map radius filter: `MAP_RADIUS_KM=0` disables filtering; `.env.example` uses `241.4` km (150mi). Applies to nodes, trails, routes, and history edges.
- `MAP_RADIUS_SHOW=true` draws a debug circle centered on `MAP_START_LAT/LON`.
- Set `TRAIL_LEN=0` to disable trails entirely; the HUD trail hint is removed when trails are off.
- Coverage button only appears when `COVERAGE_API_URL` is set.
- `QR_CODE_BUTTON_ENABLED=true` adds a `Generate QR Code` button to node popups that opens a theme-aware MeshCore-compatible contact QR modal; default is off.
- `APP_BASE_PATH` lets the site run under a public subpath such as `/livemap`; when unset, the app remains rooted at `/`.
- Geographic filtering defaults to radius mode; polygon mode is optional via `MAP_BOUNDARY_MODE=polygon` and `MAP_BOUNDARY_FILE`.
- Standalone boundary builder: `tools/map-boundary-builder.html` outputs the JSON consumed by `MAP_BOUNDARY_FILE`; hosted copy: [https://yellowcooln.com/map-boundary-builder/](https://yellowcooln.com/map-boundary-builder/).
- Radar country-bounds controls:
  `WEATHER_RADAR_COUNTRY_BOUNDS_ENABLED` and
  `WEATHER_RADAR_COUNTRY_LOOKUP_URL`.
  `WEATHER_RADAR_COUNTRY_LOOKUP_URL` defaults to
  `/weather/radar/country-bounds` and is an HTTP route path, not a
  filesystem directory.
- Weather wind controls:
  `WEATHER_WIND_ENABLED`, `WEATHER_WIND_API_URL`,
  `WEATHER_WIND_GRID_SIZE`, `WEATHER_WIND_REFRESH_SECONDS`.
- LOS curvature controls:
  `LOS_CURVATURE_ENABLED` and `LOS_CURVATURE_FACTOR`.
  When unset, LOS curvature defaults to `true` with factor `1.333333`.
- `DEVICE_COORDS_FILE` points to optional coordinate overrides (default `/data/device_coords.json`).
- `NEIGHBOR_OVERRIDES_FILE` can point at a JSON map/list of neighbor pairs to resolve hash collisions.
- Auto-neighbor overrides are controlled by:
  `AUTO_NEIGHBOR_OVERRIDES_ENABLED`, `AUTO_NEIGHBOR_OVERRIDES_FILE`,
  `AUTO_NEIGHBOR_ACTIVE_DAYS`, `AUTO_NEIGHBOR_MIN_EDGE_COUNT`, and
  `AUTO_NEIGHBOR_REFRESH_SECONDS`.
- Optional custom HUD link appears when `CUSTOM_LINK_URL` is set.
- Update banner uses `GIT_CHECK_ENABLED` (compare local vs upstream) with `GIT_CHECK_PATH` pointing at a git repo.
- `GIT_CHECK_FETCH` controls whether the server fetches before comparing; `GIT_CHECK_INTERVAL_SECONDS` sets the recheck interval.
- Route history modes default to `path` via `ROUTE_HISTORY_ALLOWED_MODES`.
- `ROUTE_PATH_MAX_LEN` caps oversized path-hash lists (prevents bogus long routes).
- `ROUTE_ALLOW_AMBIGUOUS_ONE_BYTE_FALLBACK=true` restores pre-`v1.7.0` closest/time-based fallback for colliding 1-byte route prefixes; default is conservative `false`.
- Persisted state in `data/state.json` is loaded on startup; edit with care.
- After editing `backend/*.py` or `backend/static/*`, rebuild with `docker compose up -d --build`.
- History tool visibility is not persisted; it always loads off unless `history=on` is in the URL.
- `ROUTE_HISTORY_ENABLED=false` disables Route History completely, including the History button/panel and history payloads in API/WebSocket snapshots.
- Peer-history buckets remain active when `ROUTE_HISTORY_ENABLED=false`, so the Peers tool keeps live counts even with Route History disabled.

## Feature Notes
- MQTT supports WSS/TLS or TCP; the official `@michaelhart/meshcore-decoder` runs via a Node helper for advert/location parsing, 1/2/3-byte path decoding, and conservative MQTT role extraction.
- Routes are rendered as trace/message/advert lines with TTL cleanup; 0,0 coords (including stringy zeros) are filtered from trails/routes.
- Route IDs are observer-aware (`message_hash:receiver_id`) so multi-observer receptions do not overwrite each other.
- Dev route debug: in non-prod mode (`PROD_MODE=false`), clicking a route line logs hop-by-hop details to the browser console (distance, hashes, origin/receiver, timestamps).
- Turnstile protection only activates when `PROD_MODE=true` and requires
  `TURNSTILE_ENABLED`, `TURNSTILE_SITE_KEY`, and `TURNSTILE_SECRET_KEY`.
- Turnstile browser auth (`meshmap_auth`/`?auth=`) is used for map + WebSocket sessions; protected API routes still require `PROD_TOKEN`.
- Discord/social embeds can be allowlisted under Turnstile via
  `TURNSTILE_BOT_BYPASS` and `TURNSTILE_BOT_ALLOWLIST`.
- Route hash collisions prefer known neighbors (and optional overrides); long path lists are skipped via `ROUTE_PATH_MAX_LEN`.
- Route collisions fall back to closest-hop selection and drop hops beyond `ROUTE_MAX_HOP_DISTANCE`.
- `ROUTE_INFRA_ONLY` restricts route lines to repeaters/rooms (companions still show as markers).
- Heatmap shows recent traffic points (TTL controlled).
- LOS uses `/los/elevations` for client-side realtime updates (with `/los` fallback).
- LOS uses Earth-curvature-aware obstruction checks by default in both the frontend realtime path and the backend `/los` fallback.
- LOS UI includes peak markers, a relay suggestion marker, elevation profile hover, and map-line hover sync.
- LOS legend items (clear/blocked/peaks/relay) are hidden until the LOS tool is active.
- Mobile LOS supports long-press on nodes (Shift+click on desktop); endpoints can be dragged or click-selected and moved via map click.
- LOS also supports direct latitude/longitude pin entry in the panel, including a per-pin height field for above-ground-level input at that pin.
- MQTT online status is derived from `/status` + `/internal` TTL windows; `/packets` is tracked as feed activity.
- Devices that remain MQTT-online keep their last known coordinates on the map until MQTT presence expires, even if fresh location packets stop.
- `MQTT_ONLINE_FORCE_NAMES` (comma-separated device names) forces selected nodes to always appear MQTT online.
- Legend MQTT-only filter temporarily hides non-MQTT markers, trails, routes, hop markers, route details, and peer lines; it is not persisted and is not included in share links.
- Service worker fetches navigations with `no-store` to avoid stale UI/env toggles (e.g., radius debug ring).
- Node search + labels toggle (persisted in localStorage) and a GitHub link in the HUD.
- Hide-nodes toggle hides markers, trails, heat, routes, and history layers.
- Heat toggle hides the heatmap; it defaults on and the button turns green when heat is off.
- History line weight was reduced for a lighter map overlay.
- HUD logo uses `SITE_ICON`; if missing/invalid it falls back to a small "Map" badge to keep the toggle usable.
- Route styling now keys off payload type: 2/5 = Message (blue), 8/9 = Trace (orange), 4 = Advert (green).
- 24h route history persists to `data/route_history.jsonl`, renders as a volume heatline, and defaults off (History tool panel).
- History tool opens a right-side panel with a 5-step heat filter slider: All, Blue, Yellow, Yellow+Red, Red; legend swatch hides unless active.
- History panel can be dismissed with the X button while leaving history lines visible (History tool brings it back).
- History records route modes from `ROUTE_HISTORY_ALLOWED_MODES` (default: `path`).
- Propagation render stays visible until a new render; origin changes only mark it dirty.
- Propagation now has an adjustable TX antenna gain (dBi) control, and Rx AGL defaults to 1m.
- LOS and Propagation remain separate tools on the same map so route obstruction checks and RF coverage planning can be used together without sharing one combined panel state.
- Preview image endpoint renders in-bounds device dots for shared links.
- Peers tool opens a right-side panel showing incoming/outgoing neighbors (counts + %) based on rolling peer-history buckets; selecting a node draws peer lines on the map.
- Peers panel title uses the selected node name, keeps `24h window` under the title, and compact Incoming/Outgoing headings show Rx/Tx packet totals, unique peer counts, and blue/purple line hints; `PEERS_DEFAULT_OPEN=true` starts the Peers tool active on page load.
- Peer-history buckets are also updated from route `point_ids` when a hop cannot be drawn as a visible segment, so peer counts still reflect real adjacency for non-drawable hops.
- Peers tool ignores nodes listed in `MQTT_ONLINE_FORCE_NAMES` (used for observer listeners).
- Units toggle (km/mi) is stored in localStorage and defaults to `DISTANCE_UNITS`.
- PWA support is enabled via `/manifest.webmanifest` + `/sw.js` so mobile browsers can install the app.
- Clicking the logo toggles the left HUD panel while LOS/Propagation panels remain open.
- Node popups do not auto-pan; dragging the map won’t snap back to keep a popup in view.
- Node popups let users click the short key under the node name to copy the full public key, copy a direct node/repeater map link, and can optionally show a MeshCore-compatible contact QR modal for that node with the node name plus a clickable truncated key that still copies the full public key.
- MQTT disconnect handler tolerates extra Paho args so the loop doesn’t crash; reconnects resume ingest.
- Share button copies a URL with `lat`, `lon`, `zoom`, `layer`, `history`, `heat`, `coverage`, `weather`, `labels`, `nodes`, `legend`, `menu`, `units`, `history_filter`, `route_bytes`, and `history_bytes` params.
- Route display can now be filtered from the HUD by path-hash byte width (`All`, `1-byte`, `2-byte`, `3-byte`, or checkbox combinations), and the same filter applies to route lines, hop markers, and Route Details.
- Weather state is not persisted in localStorage; it defaults off unless `weather=on` is in the URL.
- URL params override localStorage on load (`history=on` is the only way to load History open), and direct node focus supports `node`, `repeater`, `device`, `device_id`, `public_key`, and `pubkey`.
- Node size slider persists in localStorage (`meshmapNodeRadius`) and can be reset by clearing site data.
- MeshMapper coverage viewport sync reuses cached rectangles instead of rebuilding all visible squares on every pan/zoom, which keeps the Coverage layer responsive on busy maps.
