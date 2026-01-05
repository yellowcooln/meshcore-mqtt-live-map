# Repository Guidelines

## Project Structure & Module Organization
- `backend/app.py` wires FastAPI routes, MQTT lifecycle, and websocket broadcast flow.
- `backend/config.py` centralizes env configuration.
- `backend/state.py` holds shared in-memory state + dataclasses.
- `backend/decoder.py` contains payload parsing, MeshCore decoding, and route helpers.
- `backend/los.py` contains LOS math + elevation fetch helpers.
- `backend/history.py` handles 24h route history persistence/cleanup.
- `backend/static/index.html` is the HTML shell + template placeholders.
- `backend/static/styles.css` holds all UI styles.
- `backend/static/app.js` holds all client-side map logic.
- `backend/static/sw.js` is the PWA service worker.
- `backend/requirements.txt` and `backend/Dockerfile` define Python and Node dependencies.
- `docker-compose.yaml` runs the service as `meshmap-live`.
- `data/` stores persisted state (`state.json`), route history (`route_history.jsonl`), and optional role overrides (`device_roles.json`).
- `.env` holds dev runtime settings; `.env.example` mirrors template defaults.

## Build, Test, and Development Commands
- `docker compose up -d --build` rebuilds and restarts the backend (preferred workflow).
- `docker compose logs -f meshmap-live` follows server logs for MQTT activity.
- `curl -s http://localhost:8080/snapshot` checks current device state.
- `curl -s http://localhost:8080/stats` shows ingest/route counters.
- `curl -s http://localhost:8080/debug/last` inspects recent decoded packets.

## Coding Style & Naming Conventions
- Python in `backend/*.py` uses **2-space indentation**; keep it consistent.
- HTML/CSS/JS in `backend/static/index.html` uses 2 spaces as well.
- Use lowercase, underscore-separated names for Python variables/functions.
- Prefer small helper functions for parsing/normalization; keep logging concise.

## Testing Guidelines
- No automated test suite is present.
- Validate changes manually with the `/snapshot`, `/stats`, and `/debug/last` endpoints.

## Commit & Pull Request Guidelines
- No git history is available in this workspace, so there is no established commit convention.
- If you add git later, use short, imperative commit messages and describe behavioral changes in PRs.

## Configuration & Operations
- Most behavior is controlled by `.env` (MQTT host, TLS, topics, TTLs, map start lat/lon/zoom, MQTT online window, default map layer).
- Current dev defaults: `DEVICE_TTL_SECONDS=259200`, `MQTT_ONLINE_SECONDS=600`, `ROUTE_TTL_SECONDS=60`, `TRAIL_LEN=0`, `DISTANCE_UNITS=km`.
- Node size default is `NODE_MARKER_RADIUS` (pixels); users can override via the HUD slider.
- History link size default is `HISTORY_LINK_SCALE`; users can override via the History panel slider.
- Map radius filter: `MAP_RADIUS_KM=241.4` (150mi). Set `0` to disable; applies to nodes, trails, routes, and history edges.
- `MAP_RADIUS_SHOW=true` draws a debug circle centered on `MAP_START_LAT/LON`.
- Set `TRAIL_LEN=0` to disable trails entirely; the HUD trail hint is removed when trails are off.
- Route history modes default to `path,direct,fanout` via `ROUTE_HISTORY_ALLOWED_MODES`.
- `ROUTE_PATH_MAX_LEN` caps oversized path-hash lists (prevents bogus long routes).
- Persisted state in `data/state.json` is loaded on startup; edit with care.
- After editing `backend/*.py` or `backend/static/*`, rebuild with `docker compose up -d --build`.
- History tool visibility is not persisted; it always loads off unless `history=on` is in the URL.

## Feature Notes
- MQTT is WSS/TLS with meshcore-decoder in a Node helper for advert/location parsing.
- Routes are rendered as trace/message/advert lines with TTL cleanup; 0,0 coords (including stringy zeros) are filtered from trails/routes.
- Route hash collisions are ignored (unique-only mapping); long path lists are skipped via `ROUTE_PATH_MAX_LEN`.
- Heatmap shows recent traffic points (TTL controlled).
- LOS tool runs **server-side only** via `/los`, returning the elevation profile + peaks.
- LOS UI includes peak markers, a relay suggestion marker, elevation profile hover, and map-line hover sync.
- LOS legend items (clear/blocked/peaks/relay) are hidden until the LOS tool is active.
- Mobile LOS supports long-press on nodes (Shift+click on desktop).
- MQTT online status uses `mqtt_seen_ts` from `MQTT_ONLINE_TOPIC_SUFFIXES` (default `/status,/packets`); markers get a green outline + popup status.
- Service worker fetches navigations with `no-store` to avoid stale UI/env toggles (e.g., radius debug ring).
- Node search + labels toggle (persisted in localStorage) and a GitHub link in the HUD.
- Hide-nodes toggle hides markers, trails, heat, routes, and history layers.
- Heat toggle hides the heatmap; it defaults on and the button turns green when heat is off.
- History line weight was reduced for a lighter map overlay.
- HUD logo uses `SITE_ICON`; if missing/invalid it falls back to a small "Map" badge to keep the toggle usable.
- Route styling now keys off payload type: 2/5 = Message (blue), 8/9 = Trace (orange), 4 = Advert (green).
- 24h route history persists to `data/route_history.jsonl`, renders as a volume heatline, and defaults off (History tool panel).
- History tool opens a right-side panel with a 5-step heat filter slider: All, Blue, Yellow, Yellow+Red, Red; legend swatch hides unless active.
- History records routes for `path`, `direct`, and `fanout` modes by default; adjust with `ROUTE_HISTORY_ALLOWED_MODES`.
- Propagation render stays visible until a new render; origin changes only mark it dirty.
- Units toggle (km/mi) is stored in localStorage and defaults to `DISTANCE_UNITS`.
- PWA support is enabled via `/manifest.webmanifest` + `/sw.js` so mobile browsers can install the app.
- Clicking the logo toggles the left HUD panel while LOS/Propagation panels remain open.
- MQTT disconnect handler tolerates extra Paho args so the loop doesn’t crash; reconnects resume ingest.
- Share button copies a URL with `lat`, `lon`, `zoom`, `layer`, `history`, `heat`, `labels`, `nodes`, `legend`, `units`, and `history_filter` params.
- URL params override localStorage on load (`history=on` is the only way to load History open).
- Node size slider persists in localStorage (`meshmapNodeRadius`) and can be reset by clearing site data.
