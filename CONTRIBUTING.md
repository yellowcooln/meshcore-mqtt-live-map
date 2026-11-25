# Contributing Guide

Thanks for helping improve the MeshCore Live Map. This repo is intentionally lightweight (no build step), so keep changes simple and readable.

## Quick Start
1) Copy `.env.example` to `.env` and set MQTT details.
2) Rebuild: `docker compose up -d --build`
3) Verify: `curl -s http://localhost:8080/snapshot`

## Versioning
- Current version: `1.10.0` (see `VERSIONS.md`).
- Update `VERSION.txt` when adding features.
- Append a new section to `VERSIONS.md` describing the change set.

## Project Layout
- `backend/app.py` handles MQTT ingest, decoding, routing, and API endpoints.
- `backend/static/index.html` is the HTML shell + template placeholders.
- `backend/static/styles.css` holds all UI styling.
- `backend/static/app.js` contains all client-side map logic (Leaflet, routes, LOS, propagation).
- `backend/static/sw.js` is the PWA service worker.

## Coding Style
- Use 2-space indentation everywhere (Python, HTML, CSS, JS).
- Keep helpers small and focused; prefer new helpers over huge functions.
- Avoid new dependencies unless they’re critical.

## Testing Checklist
- `docker compose up -d --build` after any change.
- `pip install -r requirements-dev.txt && pytest -q` for backend unit tests.
- `curl -s http://localhost:8080/stats` to confirm MQTT ingest.
- Open the map: confirm markers, LOS, and propagation behave as expected.
- Propagation check: verify TX antenna gain (dBi) changes range, and default Rx AGL is 1m.
- Turnstile only activates when `PROD_MODE=true`; if you are testing Turnstile,
  set `PROD_MODE=true` plus the `TURNSTILE_*` env vars.
- If `COVERAGE_API_URL` is blank, confirm the Coverage button is hidden.
- If `MAP_BOUNDARY_MODE=polygon`, verify `MAP_BOUNDARY_FILE` exists and that the polygon overlay/filter matches the file contents.
- Weather panel check:
  - `WEATHER_RADAR_COUNTRY_BOUNDS_ENABLED=true` keeps radar clipped to country bounds.
  - `WEATHER_WIND_ENABLED=false` disables wind and should mark wind as unavailable in the Weather panel.
  - If wind is enabled, validate `WEATHER_WIND_GRID_SIZE` (`1`-`5`) and `WEATHER_WIND_REFRESH_SECONDS` (>= `30`) behavior.
- Note: coordinates at `0,0` (even as strings) are filtered and won’t render.
- Radius filter: `MAP_RADIUS_KM=0` disables filtering; `.env.example` uses 241.4 km (150mi).
- `CUSTOM_LINK_URL` shows an extra HUD link when set; leave blank to hide.
- Update banner uses `GIT_CHECK_ENABLED` + `GIT_CHECK_PATH` to compare local vs upstream.
- Preview check: `/preview.png?lat=...&lon=...&zoom=...` shows tiles + device dots.
- Routing controls: `ROUTE_MAX_HOP_DISTANCE` (km) and `ROUTE_INFRA_ONLY` (repeaters/rooms only).
- Verify Show Hops prefix display stays plain hex (`AB`, `ABCD`, or `ABCDEF`) and matches route direction.
- Staleness controls: `DEVICE_TTL_HOURS` (device/adverts) and `PATH_TTL_SECONDS` (path activity).
- Coordinate overrides: `DEVICE_COORDS_FILE` (default `/data/device_coords.json`).
- Neighbor overrides: `NEIGHBOR_OVERRIDES_FILE` can force adjacency pairs for hash collisions.

## Large-map performance regression

Use `tools/benchmark-large-map.py` inside the production Python/Node runtime,
with frozen source, disposable state and no network except container loopback.
Never generate stress traffic against a production MQTT broker or map. Keep the
fixture and evidence outside Git; a private state fixture must never be committed.

The fixture is a saved `state.json` with a positive `saved_at`, device records and
nonempty peer buckets. The harness shifts a disposable copy uniformly by whole
bucket intervals; it does not rewrite the input. It also seeds explicitly
synthetic route-history segments, rather than claiming to replay recovered RF
packets. It verifies actual loaded and retained cardinality to avoid an empty,
expired fixture making a benchmark artificially cheap.

After building an image, an example bounded run is:

```sh
docker run --rm --network none --cpus 1 --memory 2g \
  -e PYTHONDONTWRITEBYTECODE=1 -e TMPDIR=/evidence \
  -v "$SOURCE:/source:ro" -v "$HARNESS:/harness:ro" \
  -v "$STATE_FIXTURE:/fixture.json:ro" -v "$EVIDENCE:/evidence" \
  --entrypoint python "$RUNTIME_IMAGE" \
  /harness/benchmark-large-map.py --source /source --fixture /fixture.json \
  --output /evidence/run-1 --duration-seconds 900 --events-per-second 28 \
  --receivers 1 --history on --min-history-compactions 2 \
  --min-devices 1600 --min-peer-pairs 7000 --min-peer-buckets 160000
```

`SOURCE` must be a frozen clean source copy without operator `.env` or runtime
data; `HARNESS` contains the frozen tool; `EVIDENCE` is an existing owner-only
directory with a fresh output name. Use an independent host timeout and record
the image ID and source/input hashes. Choose minimum cardinalities appropriate
to the fixture, but do not lower them merely to make an aged-out run pass.

Rates are **broadcaster events per second**, not MQTT messages. The actual
resolver, broadcaster, cleanup, persistence and loopback HTTP/WebSocket paths
execute; raw decoding, real MQTT/RF, browser rendering and WAN/proxy delivery do
not. Compare identical source-independent event mixes, runtime/resources and
loaded cardinality. Keep CPU, queue/oldest age, latency, completed observations,
physical persistence readback and any overload failures in the result. An empty
queue alone does not prove an event whose file/send work is still pending has
completed. Repeat controls with `--history off` and `--receivers 0`.

## UI Changes

### Browser layout regression

For HUD/Peers/attribution layout changes, start an isolated app without production
credentials or data, then use a separate test environment:

```sh
python -m pip install playwright
python -m playwright install chromium
python tools/check-frontend-layout.py http://127.0.0.1:8080/map --output layout-evidence
```

The check uses production markup, scripts, and CSS with synthetic peer rows and
mocked map-provider responses. It checks mouse and touch-emulated contexts,
including narrow/desktop widths, portrait/landscape and the touch breakpoint,
across standard, dark and satellite layers. It saves screenshots and geometry,
checks zoom visibility, panel/credit clearance and touch zoom interactions. It
does not verify real provider rendering, live MQTT traffic, or physical
Windows/mobile browsers. Keep generated evidence outside the repository when
preparing commits.

When adding UI controls:
- Wire the toggle into `app.js`.
- Add styles to `styles.css` (don’t inline).
- Keep HUD layout stable on mobile (test at narrow widths).
- If `SITE_ICON` is optional, include a text fallback for the HUD toggle.
- If you add view state, decide whether it should persist in localStorage or only via URL params (History tool defaults off).
- Node marker size defaults to `NODE_MARKER_RADIUS` and can be overridden by the HUD slider (persisted in localStorage).
- History link size defaults to `HISTORY_LINK_SCALE` and can be overridden in the History panel (persisted in localStorage).
- History panel supports a dismiss (X) button; hiding the panel should not remove history lines.
- Peers tool uses `/peers/{device_id}`; keep the response stable when modifying route history logic.

## API Changes
- Document new endpoints in `docs.md`.
- Keep payloads backward-compatible when possible.

## Commits
Use short, imperative commit messages, e.g. `Add LOS panel toggle`.
