# Versions

## v1.9.7 (08-30-2026)
- Updated FastAPI to `0.142.2`, Uvicorn to `0.54.0`, and the development HTTPX2 client to `2.13.1`. Retained the Python `3.14.7-slim` runtime.
- Fixed `MQTT_TLS_INSECURE=true` so it disables certificate verification as well as hostname checking, allowing explicitly insecure TLS connections to brokers with expired or self-signed certificates. Verified TLS remains the default and still supports custom CA bundles. Added real expired-certificate TLS handshake regression tests.
- Replaced the browser's CARTO Dark Matter raster layer with the keyless OpenFreeMap Dark vector style rendered through pinned MapLibre GL JS and MapLibre GL Leaflet releases. Dark mode is now available to every deployment without `CARTO_BASEMAP_KEY`, with OpenFreeMap, OpenMapTiles, and OpenStreetMap attribution shown in the map footer.
- Kept `CARTO_BASEMAP_KEY` as an optional integration for CARTO satellite labels and server-generated dark social preview tiles; without a key, satellite imagery remains available without labels and dark previews continue to fall back to OpenStreetMap.

## v1.9.6 (08-26-2026)
- Added `CARTO_BASEMAP_KEY` support for Dark Matter tiles, satellite labels, and dark social preview images. CARTO's free key covers up to 5 million tile requests per calendar month. The documented browser-direct integration keeps the key out of Git and logs but leaves it visible in tile requests, so it must remain scoped to this project and not be reused elsewhere. Deployments without a key hide the dark-mode control, fall previews back to OpenStreetMap, and keep satellite imagery available without the CARTO label overlay. See [Get and configure a CARTO API key for dark mode](howto.md#get-and-configure-a-carto-api-key-for-dark-mode).
- Added comma-separated `COVERAGE_API_KEYS` through [PR #94](https://github.com/yellowcooln/meshcore-mqtt-live-map/pull/94) by [@Littleaton](https://github.com/Littleaton). MeshMapper coverage now fetches each key independently, merges and de-duplicates grid squares, preserves the existing single-key setting, and isolates rate-limit cooldowns per configured key.
- Fixed the PR #94 partial-refresh path by persisting per-key snapshots and hashed per-key cooldowns, so a failed key retains its last successful coverage while successful empty responses still remove obsolete squares. Partial failures remain visible across restarts, and API keys are redacted from coverage request logs. Compose now passes the complete required deployment `.env` into the container instead of maintaining a setting allowlist that can drift from the application.
- Updated the Docker runtime from Python `3.12.14-slim` to `3.14.7-slim` through [PR #95](https://github.com/yellowcooln/meshcore-mqtt-live-map/pull/95).
- Updated FastAPI from `0.139.2` to `0.141.1`, Uvicorn from `0.52.3` to the WebSocket handshake fix in `0.52.4`, and the development HTTPX2 client from `2.10.0` to `2.12.0`.
- Hardened live WebSocket delivery with concurrent per-client sends, a configurable 10-second default send timeout that allows JWT authentication swaps, failed-client isolation, crash logging, and an internal broadcaster supervisor. `/health` and `/stats` now expose broadcaster task state, queue depth, connected clients, send failures, restart count, and last activity/error timestamps.
- Added Docker Compose healthchecks for source and prebuilt-image deployments. Documented that Compose only marks unhealthy containers—it does not restart them by itself—and that bind-mounting a copied `app.py` masks backend fixes from future image upgrades.
- Fixed device reaping so TTL decisions use the newest coordinate, direct observation, or advert timestamp, while retaining the existing MQTT-presence and route-path freshness checks. Nodes with fresh non-coordinate activity are no longer deleted because their last coordinate is old.

## v1.9.5 (08-14-2026)
- Promoted the tested v1.9.4.1 through v1.9.4.4 development track to the v1.9.5 release while retaining the incremental entries below as the detailed working history.
- Added deployment-neutral fallback metadata, split trails across implausible coordinate jumps, added configurable role visibility and defaults, improved live-route filtering, and kept Peers rankings stable while filtering or changing units.
- Hardened MQTT shared-state access and listener error handling, exposed listener health through `/health` and `/stats`, and made high-volume collided-neighbor diagnostics opt-in through `ROUTE_NEIGHBOR_DEBUG`.
- Refreshed the tested Python, Docker, decoder, and GitHub Actions dependencies; added Dependabot updates targeting `dev`; and made published multi-architecture images reproducible and version-aware.

## v1.9.4.4 (08-14-2026)
- Added `ROUTE_NEIGHBOR_DEBUG`, disabled by default, so high-volume collided-neighbor route selections no longer flood stdout. Compose deployments can opt back into the diagnostic log, and both silent-default and enabled-output behavior are covered by regression tests.
- Updated FastAPI from `0.139.0` to the thread-safety fix in `0.139.2` while keeping the existing `0.139` release line.
- Updated Uvicorn from `0.50.2` to `0.52.3`, pinned the Docker runtime to Python `3.12.14-slim`, and pinned the MeshCore decoder package to `0.3.0` for reproducible builds.
- Updated the development test client `httpx2` from `2.5.0` to `2.10.0`.
- Added weekly Dependabot checks for Python, Docker, and GitHub Actions with update pull requests targeting `dev`.
- Updated the CI and Docker publishing actions to their Node 24-backed releases: `actions/checkout` and `actions/setup-python` v7, `docker/setup-qemu-action`, `docker/setup-buildx-action`, and `docker/login-action` v4, `docker/metadata-action` v6, and `docker/build-push-action` v7.
- Published Docker images now receive the release version at build time instead of reporting `dev` when the source tree is not mounted.

## v1.9.4.3 (08-07-2026)
- Fixed issue #79: MQTT presence, snapshot, stats, peer-history, route-hash, and persisted-state readers now iterate stable copies of shared dictionaries instead of racing Paho's network thread. Unexpected message-handler exceptions are logged and counted without terminating MQTT processing, while `/health` and `/stats` expose MQTT connection and network-loop health.
- Fixed role visibility filtering so hiding Companion or Room Server removes only route sections connected through those hidden roles while preserving contiguous Repeater-to-Repeater sections; also corrected the `Room Server` label capitalization.
- Renamed `Route Nodes` to `Filter Live Routes` so the control clearly describes its scope. Fixed its autocomplete so the menu stays inside the viewport without expanding the scrollable HUD, current device names match routes whose cached labels are stale, and typing updates existing route layers without destroying and recreating them. The menu now also closes on Escape or outside clicks.
- Added independent fixed ranks to the Peers panel Incoming/Rx and Outgoing/Tx lists. Filtering preserves each peer's position from the complete sorted list instead of renumbering matching rows, and changing distance units no longer clears an active peer filter.

## v1.9.4.2 (07-11-2026)
- Added a live route node filter below `Path bytes`. Clicking the empty/current entry opens an alphabetical list of nodes participating in current live routes; typing narrows that list, and choosing a node inserts it with comma separation before reopening the remaining choices. Route lines, hop markers, Route Details, and visible route counts stay aligned.
- Added `Shown`/`Hidden` controls beside Repeater, Companion, Room server, and Unknown legend entries. Hiding a role also hides live route, hop, trail, and peer lines connected to those nodes; role choices persist in the browser and are included in share URLs.
- Added `SHOW_REPEATERS_DEFAULT`, `SHOW_COMPANIONS_DEFAULT`, `SHOW_ROOM_SERVERS_DEFAULT`, and `SHOW_UNKNOWN_DEFAULT` so deployments can hide selected node roles for first-time visitors while keeping every role enabled by default.

## v1.9.4.1 (07-09-2026)
- Replaced Boston/New England-specific fallback site metadata with generic MeshCore defaults for the site title, description, and feed note so fresh deployments start neutral.
- Added `TRAIL_MAX_SEGMENT_KM` with a 10 km default so visual device trails split across large coordinate jumps without hiding legitimate long route/hop links.

## v1.9.4 (07-07-2026)
- Changed live and History `Path bytes` controls to checkbox selectors so users can keep `All` or combine specific byte widths such as `2-byte + 3-byte`.
- Fixed Route Details prefix display for multibyte paths so 2-byte/3-byte route hops show the matching path-hash width instead of falling back to 1-byte node prefixes.
- Added optional `CORESCOPE_URL` support so Route Details hop names can deep-link to CoreScope node pages (`#/nodes/<pubkey>`), with packet-hash fallback links to `#/packets/<hash>` when `PACKET_ANALYZER_URL` is not set.
- Added `BLOCKED_NAME_SYMBOL_FILTER_ENABLED` so deployments can hide nodes whose names contain `⛔`, `🛑`, or `🚫` from map snapshots, trails, and routes.
- Guarded CoreScope link generation against unreplaced template placeholders so routes never point at local `/%7B%7BCORESCOPE_URL%7D%7D/` paths, and added a New England map fallback to `https://analyzer.newenglandme.sh`.
- Made `ROUTE_HISTORY_ENABLED` parsing tolerant of surrounding whitespace so a `true` value with deployment formatting does not accidentally hide the History button.
- Marked the map HTML shell responses as `Cache-Control: no-store` so stale cached pages cannot keep unreplaced template placeholders such as `{{ROUTE_HISTORY_ENABLED}}` after an image update.
- Fixed Discord/social embeds for `/map?lat=...&lon=...` links so they include the same generated map preview image as root `/?lat=...&lon=...` links.
- Docker image publishing now runs on `dev` pushes as well as `main`; `dev` publishes the `dev` and short-SHA tags, while only `main` publishes the `latest` tag.
- Added `ROUTE_BYTE_FILTER_DEFAULT` and `HISTORY_BYTE_FILTER_DEFAULT` env defaults. Browser selections persist locally, while share links can carry comma-separated byte filters such as `route_bytes=2b,3b` and `history_bytes=1b,2b`.
- Updated dependency pins: `fastapi==0.139.0`, `uvicorn[standard]==0.50.2`, `Pillow==12.3.0`, `httpx2==2.5.0`, and `pytest==9.1.1`.
- Route History now records path-hash byte-width metadata for newly ingested history samples and exposes per-edge byte counts to the frontend. Older history records remain visible in `All` after upgrade, while byte-specific filters start showing those links as new byte-aware traffic arrives.
- Added a Peers panel filter box that live-filters incoming/outgoing peers by node name, public-key prefix, or role, and keeps the peer lines aligned with the visible filtered rows.
- Fixed stale duplicate-node cleanup so older same-name/public-key-prefix records without peer activity no longer render in front of the newer connected node record.
- Added a third `Satellite` base-map option. The existing Standard/Topo map button now cycles through Standard, Topo, and Satellite; Satellite uses open EOX Sentinel-2 cloudless imagery with OpenStreetMap/CARTO labels, borders, and road context overlaid.
- Added a deployment privacy policy page and a `Privacy` link in the Leaflet attribution/footer area, keeping it out of the main HUD buttons.
- Tightened HUD/header styling so long site titles and action buttons stay compact and legible over light, topo, and satellite map backgrounds.
- Fixed the route/history byte dropdown positioning so multi-select menus stay contained in the HUD/tool panel instead of spilling off the edge after the HUD styling updates.

## v1.9.3 (06-06-2026)
- Fixed issue #74: hardened frontend rendering against stored XSS from untrusted MeshCore/MQTT fields such as node names, peer names, route labels, and coverage metadata.
- Node popups, permanent labels, search results, Peers rows, Route Details, History popups, and Coverage popups now escape display HTML before rendering user-supplied values.
- Kept map behavior unchanged: device IDs, coordinates, QR payloads, copy actions, route resolution, peer selection, and filters continue to use the original data while only the displayed HTML is sanitized.
- Updated backend dependencies to current tested pins: `fastapi==0.136.3`, `uvicorn[standard]==0.49.0`, and `httpx==0.28.1`.
- Added `httpx2==2.3.0` to dev requirements so FastAPI/Starlette `TestClient` tests run without the deprecated-`httpx` warning.

## v1.9.2 (05-23-2026)
- Fixed the remaining issue #68 Docker Compose gap by passing the Route History envs into the container: `ROUTE_HISTORY_ENABLED`, `ROUTE_HISTORY_HOURS`, `ROUTE_HISTORY_MAX_SEGMENTS`, `ROUTE_HISTORY_FILE`, `ROUTE_HISTORY_PAYLOAD_TYPES`, and `ROUTE_HISTORY_COMPACT_INTERVAL`.
- Compose-based deployments can now actually disable Route History from `.env`; previous `1.9.1` installs could still behave as if history was enabled because the container was falling back to backend defaults.
- Fixed the follow-up issue #68 peer regression where disabling Route History eventually caused the Peers tool counts to go empty after older peer buckets expired.
- Peer-history buckets now continue recording from live routes even when Route History is disabled, so the History tool can stay off without disabling incoming/outgoing peer counts.
- Route History remains disabled as intended: no History button/panel, no history payloads in `/snapshot` or WebSocket snapshots, and no route-history file growth from live traffic.
- Added issue #71: the LOS panel now supports direct latitude/longitude pin entry so operators can add LOS points without placing every pin from the map view first.
- Added a per-pin LOS height field to the coordinate editor, making it explicit that entered heights are above ground level at the selected pin and not one shared route-wide value.
- LOS pin editing now works from either workflow: add or drag pins on the map, or select a pin and move it from the coordinate editor while recomputing the affected LOS segments.
- LOS and Propagation remain separate tools on the same map, which keeps path-obstruction checks and RF-coverage planning independent while still supporting deployment planning side by side.
- Added issue #72 from Stormlove / [@beachmiles](https://github.com/beachmiles): the Peers panel now places `Clear peers` in the header next to `Minimize`, uses capped incoming/outgoing list scrolling, and shows unique peer counts directly in the Incoming/Outgoing headings.
- Added `PEERS_DEFAULT_OPEN=false` so deployments can choose whether the Peers tool opens active on initial page load without forcing that behavior for existing installs.
- Condensed the issue #72 Peers panel cleanup ideas from Stormlove / [@beachmiles](https://github.com/beachmiles) by moving the selected node name into the title, moving Rx/Tx packet totals and line-color hints into compact section headings, and ordering peer row stats as count, percent, then distance.
- Tuned the issue #72 Peers panel follow-up so small incoming/outgoing peer lists shrink to their content instead of leaving large empty gaps, while long peer lists scroll inside capped sections without forcing the whole panel to full height on mobile.
- Added a legend-side MQTT-only filter button that temporarily shows only MQTT-online nodes while hiding non-MQTT markers, trails, routes, hop markers, route details, and peer lines. This view filter is intentionally not saved to browser storage and is not included in share links.

## v1.9.1 (05-08-2026)
- Fixed issue #68: `ROUTE_HISTORY_ENABLED=false` now fully disables Route History instead of only stopping new history recording.
- When Route History is disabled, the History button and panel are removed from the frontend, `history=on` no longer re-enables it, and the API/WebSocket snapshot stop publishing history edges and history window metadata.
- The `ROUTE_HISTORY_ENABLED` env now behaves as an actual feature toggle for both backend payloads and the History tool UI, which makes it viable for lower-memory or high-volume map deployments that do not want route-history state at all.

## v1.9.0 (05-06-2026)
- Added `APP_BASE_PATH` so the live map can be hosted under a subpath such as `/livemap` instead of only at `/` via [PR #65](https://github.com/yellowcooln/meshcore-mqtt-live-map/pull/65) by [@chrisdavis2110](https://github.com/chrisdavis2110).
- Subpath hosting now rewrites the app shell, static assets, WebSocket path, service worker registration, manifest URLs, Turnstile verification flow, and auth cookie scope so the frontend continues to work correctly when a path prefix is configured.
- Fixed preview/OG image URL generation so shared links and social embeds keep working correctly with `APP_BASE_PATH` and public site URLs.
- Node popups now include a direct map-link action that copies a URL with `node=<public-key>`; loading that link focuses and zooms to the matching node/repeater, with `repeater`, `device`, `device_id`, `public_key`, and `pubkey` accepted as aliases via [PR #66](https://github.com/yellowcooln/meshcore-mqtt-live-map/pull/66) by [@mitchellmoss](https://github.com/mitchellmoss).
- The Peers tool now includes peer distance in the selected km/mi units when both the selected node and peer have coordinates, and the backend `/peers/{device_id}` payload now exposes that value as `distance_m` via [PR #66](https://github.com/yellowcooln/meshcore-mqtt-live-map/pull/66) by [@mitchellmoss](https://github.com/mitchellmoss).

## v1.8.6 (05-02-2026)
- Added issue #59: a new `Path bytes` HUD filter for live routes so the map can switch between `All`, `1-byte`, `2-byte`, and `3-byte` path-hash views without changing ingest or decode behavior.
- The new route-byte filter applies to route lines, hop markers, Route Details, and the HUD route count so the visible map stays consistent while filtering.
- Mixed-width paths remain visible in the matching byte view whenever a route contains at least one hop of that width, which keeps upgraded mixed meshes usable during rollout.
- The selected route-byte filter can be shared with `route_bytes=all|1b|2b|3b`, but it resets to `All` on normal reloads so stale browser state does not hide routes unexpectedly.
- Added `HEAT_DEFAULT_ON` so deployments can choose whether the Heat layer loads on or off by default before any browser-local overrides exist.

## v1.8.5 (04-30-2026)
- Added a DockerHub publish workflow at `.github/workflows/docker-publish.yml` that builds the app from `backend/Dockerfile` and pushes multi-arch `linux/amd64` and `linux/arm64` images.
- The publish flow targets `yellowcooln/meshcore-mqtt-live-map` and tags `latest` from `main`, plus branch, tag, and short-SHA image tags.
- Added image-based deployment examples so users can run the app without cloning and building locally:
  - `deploy/docker-compose.image.yaml`
  - `deploy/swarm-stack.yaml`
  - `deploy/kubernetes-meshmap.yaml`
- Documented the DockerHub image flow and required GitHub Actions secrets for automatic publishing.

## v1.8.4 (04-17-2026)
- Fixed the post-`v1.7.0` route regression where some meshes stopped showing routes that previously rendered in `v1.6.6`.
- Added `ROUTE_ALLOW_AMBIGUOUS_ONE_BYTE_FALLBACK` so operators can restore the legacy closest/time-based fallback for colliding 1-byte hop prefixes when conservative prefix handling is too strict for their network.
- Kept conservative ambiguous 1-byte routing as the default, but made the legacy fallback opt-in for deployments that need the older route rendering behavior.
- Passed `ROUTE_ALLOW_AMBIGUOUS_ONE_BYTE_FALLBACK` through `docker-compose.yaml` and documented the new routing toggle in the setup docs.
- Added issue #55: LOS and Propagation panels can now be minimized on mobile without turning the tool off, making it easier to interact with the map while the tool stays active.
- Extended the issue #55 minimize/expand control to History, Peers, and Route Details so side panels can be collapsed instead of closed with a separate `×` flow.
- Added issue #56: the LOS elevation profile now renders upper and lower Fresnel-zone lines similar to the MeshCore app.
- LOS profile hover now reports Fresnel radius along with terrain and LOS height, and Fresnel rendering stays segment-local for multi-pin LOS routes so chained paths do not get incorrect full-route curves.
- Fixed the issue #55 panel-regression fallout so History sliders, Peers, Route Details clearing, LOS point selection, and Propagation opening continue to work correctly.

## v1.8.3 (04-16-2026)
- Fixed issue #53: the LOS tool now accounts for Earth curvature instead of using a purely straight terrain-vs-line check.
- Added LOS curvature controls `LOS_CURVATURE_ENABLED` and `LOS_CURVATURE_FACTOR`, both defaulting to enabled curvature with a `1.333333` effective Earth radius factor when unset.
- Applied the same curvature math to both the frontend realtime LOS path and the backend `/los` fallback so live interaction and server responses stay consistent.
- Updated the LOS profile and blockage calculation to use curvature-adjusted terrain samples, which can correctly mark longer paths as blocked where the old LOS tool showed clear.
- Clarified MQTT broker authentication docs for `meshcore-mqtt-broker`: the map normally uses a broker `SUBSCRIBER_N` username/password pair instead of node-style signed publisher auth.

## v1.8.2 (04-07-2026)
- Added issue #48: node popups now let users click the short key under the node name to copy the full public key without adding a duplicate full-key line to the popup body.
- Added optional MeshCore-compatible contact QR generation for node popups via `QR_CODE_BUTTON_ENABLED=true`.
- Changed the QR action to open an in-page modal instead of navigating to a separate browser tab, and made the modal follow the active light/dark map theme.
- Tuned the QR modal and generator for better on-screen scanning by enlarging the modal presentation and reducing QR density to better match the official app export.
- The QR modal now uses the node name as its title and shows a clickable truncated public key line that still copies the full key.
- Added a local `/qr` PNG endpoint for popup QR generation and protected it with the existing prod token flow.
- Fixed `docker-compose.yaml` so `QR_CODE_BUTTON_ENABLED` is passed into the container and the feature can actually be enabled from `.env`.
- Improved MeshMapper coverage performance by caching the expanded rectangle set and only toggling visible squares on pan/zoom instead of rebuilding every rectangle each viewport change.
- Fixed peer-history accounting so `/peers/{device_id}` still counts adjacent route hops from `point_ids` even when a route segment cannot be drawn because its coordinates are missing, zeroed, or otherwise filtered out.
- Fixed stale-node cleanup so nodes that are still MQTT-online keep their last known map position instead of disappearing while `/status` or `/internal` presence is still active.

## v1.8.1 (04-06-2026)
- Fixed issue #43: location updates now key devices from the advert owner pubkey only, avoiding bogus ghost nodes created from unrelated decoded `publicKey` fields.
- Added a startup/state cleanup pass that removes exact same-name/same-location duplicate device entries so already-persisted ghost markers disappear after restart instead of lingering until TTL expiry.
- Fixed issue #45: MeshMapper coverage now rebuilds the visible square set from cached source data on zoom and pan, so tiles no longer change incorrectly when the viewport scale changes.
- Fixed issue #46: peer-list limits no longer use a hardcoded maximum, so `/peers/{device_id}?limit=` can request any positive count.
- Added issue #44: upstream-style hidden arcade Pacman mode that animates a flow marker along live route direction and can be enabled with the Konami sequence or `/waka` in search.

## v1.8.0 (03-28-2026)
- Switched the runtime decoder back to the official `@michaelhart/meshcore-decoder` package now that the published decoder supports multibyte path decoding needed by the map.
- Added issue #41: the LOS tool now supports multiple chained pins so you can build a proposed relay path one segment at a time instead of being limited to a single two-point LOS check.
- LOS elevation profile now spans the chained path instead of only the active two-point segment.
- Removed the old `Keep A` LOS workflow and updated the LOS panel copy/labels to match chained pins instead of fixed A/B endpoints.
- LOS height inputs are now stored per pin instead of as a single shared A/B pair, so changing segment heights no longer overwrites unrelated segments in a chained LOS path.
- Simplified the LOS helper copy so the selected-segment height controls read more directly.
- Added `Remove last pin` to the LOS tool so chained paths can be trimmed without clearing the whole route.
- Fixed chained LOS recomputation when moving an intermediate pin so both adjacent segments are recalculated instead of leaving the earlier segment stale.
- Added automatic runtime backups as timestamped `.tar.gz` archives.
- MeshMapper coverage rendering now expands each returned square to match MeshMapper's displayed neighboring coverage fill, so the live map matches the MeshMapper site more closely instead of showing only the center square.
- Softened the expanded MeshMapper coverage fill so the map keeps the fuller coverage footprint without the grid looking overly harsh.
- Tuned MeshMapper coverage styling again with slightly brighter fill and subtle grid lines restored for readability.
- Backups now collect existing live-state files such as `state.json`, `device_roles.json`, `device_coords.json`, `neighbor_overrides.json`, `channel_secrets.json`, `map_boundary.json`, `route_history.jsonl`, and `coverage_cache.json`.
- Added new backup envs: `BACKUP_ENABLED`, `BACKUP_INTERVAL_SECONDS`, `BACKUP_DIR`, and `BACKUP_RETENTION_DAYS`.
- Backup archives now default to `/backup` instead of `/data`, so live state and archives stay separate.
- Backup interval now defaults to `43200` seconds (12 hours).
- Added retention pruning for old backup archives based on `BACKUP_RETENTION_DAYS`.
- Added `./backup:/backup` to `docker-compose.yaml` and ignored `/backup/` in git so local backup archives stay out of the repo.
- Added backup tests covering archive creation and retention pruning.

## v1.7.8.1 (03-24-2026)
- Fixed issue #38: the Peers tool `Clear peers` action now removes both incoming and outgoing lines even when the same peer appears in both directions.
- Fixed a follow-on Peers tool bug where clearing peers could leave a stale in-flight lookup active, preventing a new node selection from taking over until the tool was reopened.
- Made peer lines non-interactive so the Peers tool no longer blocks node clicks while peer links are displayed.
- Moved peer lines into a dedicated non-interactive pane so repeated node selections keep working while the Peers tool is open.

## v1.7.8 (03-24-2026)
- Adjusted MeshMapper coverage rendering to match the native MeshMapper look more closely by removing visible square borders and increasing fill density.
- Legacy coverage rendering is unchanged; the visual change applies only to MeshMapper `grid_squares`.
- Added a MeshMapper coverage legend in the HUD that appears only while the Coverage layer is active, using the native MeshMapper categories: `BIDIR`, `DISC / TRACE`, `TX`, `RX`, `DEAD`, and `DROP`.
- Enabled Leaflet canvas rendering for the main map and moved node, history, and coverage drawing onto canvas-backed rendering while keeping animated route/trail lines on SVG so visuals stay unchanged.
- Added viewport culling for nodes and coverage tiles so off-screen markers and coverage squares are not rendered until they are near the visible map area.
- Batched realtime websocket updates onto `requestAnimationFrame` so bursts of node/route/history events no longer force repeated synchronous redraws and stats recalculations in a single frame.

## v1.7.7 (03-22-2026)
- Added `PEERS_DEFAULT_LIMIT` so the Peers tool default list size is configurable from env instead of being hardcoded to `8`.
- `/peers/{device_id}` still allows `?limit=` overrides, and both the env default and query override are clamped to a max of `50`.
- Added optional boundary mode support with `MAP_BOUNDARY_MODE=polygon`, `MAP_BOUNDARY_FILE`, and `MAP_BOUNDARY_SHOW`; default behavior remains radius mode.
- Polygon boundaries now filter devices, routes, and history consistently, and the frontend can render the active polygon overlay from backend-injected JSON.
- Added `map_boundary.example.json` plus a standalone builder at `tools/map-boundary-builder.html` for generating polygon JSON files outside the live app; hosted copy: [https://yellowcooln.com/map-boundary-builder/](https://yellowcooln.com/map-boundary-builder/).

## v1.7.5 (03-22-2026)
- Added independent scrollable incoming/outgoing peer lists so the Peers panel can show the full peer set without truncating the panel content.
- Route Details now preserves companion endpoints in the popup when the route line itself begins or ends at infrastructure nodes, including non-spatial endpoint rows for companions without GPS coordinates.
- Route Details can now show a display-only sender-name row as hop 0 when the packet decode includes a message sender name but not a stable sender identity.
- Route Details hop counts now match the visible list when a display-only sender companion row is present, and that sender row is labeled with role `Companion`.
- Added optional `PACKET_ANALYZER_URL` so Route Details hashes can link directly to an external packet analyzer.
- Route Details now shows the full packet hash in the header instead of truncating it.
- Route Details now prefers the MQTT packet hash for route identity and analyzer links instead of a shorter decoder `messageHash` when both are present.
- Fixed the prod route payload so Route Details keeps the packet hash and sender name instead of falling back to the internal `hash:receiver` route id in the title.
- Added `CHANNEL_SECRETS_FILE` support and a shipped `channel_secrets.example.json` so group-text sender names can be decrypted without using a long env var list.
- Made the node popup `Location:` line clickable so it copies the displayed `Location: <lat>, <lon>` text directly to the clipboard.

## v1.7.0 (03-20-2026)
- Added dual coverage API support so the Coverage button now works with both the legacy `/get-samples` API and the new MeshMapper Coverage API.
- Added MeshMapper API detection for the documented `https://meshmapper.net/coverage.php` endpoint, with automatic requests to `coverage.php`.
- Added optional `COVERAGE_API_KEY` support for MeshMapper coverage requests without changing the legacy coverage integration.
- Coverage rendering now supports MeshMapper `grid_squares` directly, preserving server-provided bounds and colors instead of forcing the legacy geohash tile aggregation.
- Added MeshMapper-only server-side sync that stores coverage in a local cache file and serves users from that file instead of refetching `coverage.php` per request.
- Added MeshMapper rate-limit cooldown handling for HTTP 429 responses, using `resets_in_hours` when provided and falling back to a local cooldown value otherwise.
- When MeshMapper is rate-limited and cached coverage exists, the app now serves the last successful coverage payload instead of failing immediately.
- Added coverage age filtering with `COVERAGE_MAX_AGE_DAYS` (default `30`) so the map only shows recent coverage while MeshMapper can still cache the full upstream dataset locally.
- Added new MeshMapper-only coverage envs: `COVERAGE_API_KEY`, `COVERAGE_MAX_AGE_DAYS`, `COVERAGE_RATE_LIMIT_COOLDOWN_SECONDS`, `COVERAGE_CACHE_FILE`, and `COVERAGE_SYNC_INTERVAL_SECONDS` (these are not used by legacy coverage maps).
- MeshMapper coverage now preserves the API `region` code in the local cache and response headers, and the map shows a bottom-right `MeshMapper` link to `https://<region>.meshmapper.net` when the Coverage layer is active.
- Added regression tests covering legacy coverage fetches, MeshMapper URL building, local cache-file serving/writes, and 429 fallback behavior.
- Fixed route snapshot handling so nearly expired routes are not sent to newly loaded clients and immediately removed on page load.
- Fixed route expiry timing in the frontend to use server-relative time instead of raw browser clock time, reducing premature route disappearance on clients with clock skew.
- Fixed MQTT online marker styling to use the same server-relative time source, restoring the green outline on MQTT-connected nodes when the browser clock is ahead of the server.
- Tightened ambiguous 1-byte hop resolution so colliding first-byte prefixes are no longer guessed from generic closest/time-based fallbacks.
- Ambiguous 1-byte hops now resolve only when there is stronger evidence such as a unique candidate or neighbor/manual adjacency, reducing impossible long-distance links on large meshes.
- Added websocket snapshot regression coverage for server time injection and near-expired route filtering.

## v1.6.6 (03-19-2026)
- Fixed the Peers tool 24h counts on large meshes by moving peer statistics off raw `route_history_segments` and onto dedicated rolling peer-history buckets.
- Peer counts are now time-windowed independently of `ROUTE_HISTORY_MAX_SEGMENTS`, so high traffic no longer causes the effective 24h window to shrink to a few hours.
- Added peer-history bucket pruning/state persistence so `/peers/{device_id}` survives restarts and keeps the expected rolling window behavior.
- Added regression tests covering peer counts after segment-cap pruning and peer-history state round trips.

## v1.6.5 (03-14-2026)
- Made MQTT role detection conservative for accuracy: the map now only assigns roles from explicit role fields and numeric MeshCore role codes.
- Stopped inferring device roles from weak MQTT name/model/client/origin/description hints that could mislabel normal nodes as room servers.
- Added regression coverage to ensure model/origin strings like `PyMC-Repeater` or `PR-Room-Server` no longer assign a role by themselves.
- Added runtime version logging on startup in both the server logs and browser console so the running map version is visible without checking docs.
- Fixed backend route hash normalization to respect decoder `pathLength` for low-range multibyte repeater IDs, so 2-byte and 3-byte integer hashes like `0x00AB` and `0x0000AB` do not collapse to shorter prefixes.
- Added regression tests covering low-range 2-byte and 3-byte path-hash padding before route resolution.

## v1.6.2 (03-11-2026)
- Fixed route-details hop ordering in the UI by using backend route order and `point_ids` directly instead of frontend reversal/name heuristics.
- Fixed hop-prefix display in the route details panel so 1-byte (`AB`), 2-byte (`ABCD`), and 3-byte (`ABCDEF`) prefixes all render correctly.
- Improved device role detection from MQTT payloads by accepting nested role fields, numeric role codes, and common model/client hints from status and decoded packet data.
- Added decoder role tests covering nested MQTT role hints and numeric-string MeshCore role codes.
- Dev route debugging now includes resolved `point_id` / `point_label` data to make hop attribution issues easier to verify.
- Fixed the Show Hops panel to display each matched node's true prefix from `point_id` instead of showing the incoming path token on the wrong row.

## v1.6.1 (03-11-2026)
- Replaced the official `@michaelhart/meshcore-decoder` package with [`meshcore-decoder-multibyte-patch`](https://www.npmjs.com/package/meshcore-decoder-multibyte-patch) in the container runtime.
- Expanded route prefix normalization and matching to support 1-byte (`AB`), 2-byte (`ABCD`), and 3-byte (`ABCDEF`) path segments.
- Updated route resolution tests to cover mixed 1/2/3-byte paths and exact-prefix matching behavior.
- Live dev validation now shows multibyte path strings arriving from the mesh feed; this release is intended to be ready for upcoming multibyte repeater rollouts.
- Multibyte path ingest and resolution are now supported in the map, but full field validation across all mixed-network scenarios is still ongoing.

## v1.6.0 (03-07-2026)
- Refactored weather backend logic into `backend/weather.py` and mounted it as a router (`/weather/radar/country-bounds`) to match the module layout used by LOS/history.
- Weather is now treated as a right-side tool panel with independent `Radar` and `Wind` layer toggles.
- Added share-link support for per-layer weather state via `weather_radar` and `weather_wind` URL params.
- Added browser persistence for Weather layer toggles (`Radar`/`Wind`) via local storage.
- Added backend weather endpoint tests for invalid coords, prod token enforcement, and cache behavior.
- Expanded backend test coverage to 44 passing tests with new cases for websocket auth, prefix routing, neighbor pruning/priority, weather flags, and persistence robustness.
- Hardened `/coverage` parsing for invalid upstream schemas (non-list `keys` now returns `[]`).
- Replaced deprecated FastAPI startup/shutdown event decorators with a lifespan handler.
- Expanded docs for all weather env settings and what each one controls.
- New env controls documented for this release line:
  - `WEATHER_RADAR_ENABLED`
  - `WEATHER_RADAR_COUNTRY_BOUNDS_ENABLED`
  - `WEATHER_RADAR_COUNTRY_LOOKUP_URL`
  - `WEATHER_WIND_ENABLED`
  - `WEATHER_WIND_API_URL`
  - `WEATHER_WIND_GRID_SIZE`
  - `WEATHER_WIND_REFRESH_SECONDS`
  - `MQTT_ONLINE_STATUS_TTL_SECONDS`
  - `MQTT_ONLINE_INTERNAL_TTL_SECONDS`
  - `MQTT_ACTIVITY_PACKETS_TTL_SECONDS`
  - `MQTT_STATUS_OFFLINE_VALUES`

## v1.5.0 (03-06-2026)
- Reworked MQTT presence tracking to follow MeshCore topic semantics:
  - MQTT connectivity now derives from `/status` and `/internal` heartbeats.
  - Explicit status values in `MQTT_STATUS_OFFLINE_VALUES` force offline quickly.
  - `/packets` activity is tracked separately from connectivity.
- Added MQTT presence summary counters in `/snapshot`, `/stats`, and WebSocket updates so the UI can show total MQTT-connected nodes (including nodes without map coordinates).
- Updated the HUD stats line to show MQTT-connected totals vs on-map MQTT-connected counts.
- Popup cleanup: nodes now only show `MQTT: Online` when online; offline labels were removed.
- Added new env controls:
  - `MQTT_ONLINE_STATUS_TTL_SECONDS`
  - `MQTT_ONLINE_INTERNAL_TTL_SECONDS`
  - `MQTT_ACTIVITY_PACKETS_TTL_SECONDS`
  - `MQTT_STATUS_OFFLINE_VALUES`
- Passed new MQTT presence envs through `docker-compose.yaml` and expanded regression coverage with `tests/test_mqtt_online_presence.py`.

## v1.4.2 (03-05-2026)
- Migrated app lifecycle from deprecated FastAPI `@app.on_event("startup"/"shutdown")` handlers to a lifespan context manager.
- Kept MQTT connect/disconnect and background task startup behavior equivalent under the new lifespan flow.
- Added `.venv/` to `.gitignore` for local developer test environments.

## v1.4.1 (03-05-2026)
- Fixed route payload serialization in `PROD_MODE` so hop metadata needed by the Show Hops UI is included (`hashes`, `point_ids`, `origin_id`, `receiver_id`).
- Added regression coverage to ensure prod route payloads keep hop hashes for prefix display.
- Added tests for neighbor-priority route resolution and `/api/nodes` format/delta modes.
- Reworked `.env.example` into grouped sections with clearer defaults and full key coverage to make setup easier.

## v1.4.0 (03-05-2026)
- Added mixed hop prefix support in route parsing/resolution so paths can include both 1-byte (`AB`) and 2-byte (`ABCD`) repeater prefixes.
- Route hash candidate mapping now indexes both prefix widths per device to reduce collisions/phantom hops on larger networks.
- Show Hops now labels prefixes as `Prefix: AB` or `Prefix: ABCD` (no `0x`) and aligns prefix display with the rendered route direction.
- 2-byte prefix support is implemented and expected to be ready, but has not been fully field-tested yet.
- Added a pytest suite + CI workflow covering prefix parsing, route resolution, API auth/modes, LOS endpoints, coverage endpoint behavior, neighbor override loading, websocket snapshot payloads, and state/history persistence round-trips.

## v1.3.5 (02-06-2026)
- Added dual stale-window support so `DEVICE_TTL_HOURS` and `PATH_TTL_SECONDS` work together instead of replacing each other.
- Node pruning now supports both windows at once (with 4-day device defaults and 48-hour path defaults in examples/compose).
- Environment docs and examples now describe the `DEVICE_TTL_HOURS` + `PATH_TTL_SECONDS` model and default values.
- Added `DEVICE_COORDS_FILE` config path support (default: `/data/device_coords.json`) in compose and env docs.
- Credit: `PATH_TTL_SECONDS` flow by https://github.com/djp3.
- Credit: `DEVICE_TTL_HOURS` flow by https://github.com/chrisdavis2110.

## v1.3.1 (02-03-2026)
- Propagation tool now includes an adjustable **TX antenna gain (dBi)** field that feeds directly into range and coverage calculations.
- Propagation defaults now start with **Rx AGL = 1m** (previously 5m).
- Credit: C2D.

## v1.3.0 (02-03-2026)
- LOS tool now supports realtime endpoint dragging with throttled live recompute for smoother interaction (PR #18, credit: https://github.com/mitchellmoss).
- Added elevation fetch proxy endpoint (`/los/elevations`) with frontend caching/backoff to reduce API spam and avoid elevation rate-limit failures while dragging.
- Added `LOS_ELEVATION_PROXY_URL` env/config support so LOS elevation requests can be routed through the backend.
- Fixed LOS point repositioning so you can click/select point A/B and click the map to move that specific point (plus visual selected-point highlight).
- Updated LOS docs and feature notes for the new realtime drag + proxy workflow.

## v1.2.6 (02-02-2026)
- API compatibility update for MeshBuddy and similar clients:
  - `/api/nodes` now defaults to a flat payload (`"data": [...]`).
  - Added top-level `"nodes": [...]` alias for legacy consumers.
  - `updated_since` now applies delta filtering automatically.
  - `mode=full` (or `all`/`snapshot`) forces full list responses.
  - `format=nested` returns wrapped payloads (`"data":{"nodes":[...]}`).

## v1.2.5 (02-02-2026)
- Route line IDs are now observer-aware (`message_hash:receiver_id`) so simultaneous receptions from multiple MQTT observers do not overwrite each other.
- WebSocket auth now accepts `?auth=<turnstile_token>` in addition to cookie/header auth, reducing reconnect loops during Turnstile-gated sessions.
- PROD token checks now always require `PROD_TOKEN` for protected API routes; Turnstile session auth no longer bypasses API token requirements.
- `ROUTE_INFRA_ONLY` endpoint logic was relaxed so direct routes can still render when at least one endpoint is infrastructure (repeater/room).

## v1.2.4 (01-29-2026)
- Turnstile auth now grants access to `/snapshot`, `/stats`, `/peers`, and WebSocket without requiring a PROD token (prevents WS reconnect spam).
- Show Hops panel now includes total route distance (sum of hop-to-hop segments) and updates live with unit toggles.

## v1.2.2 (01-29-2026)
- Fix: Route lines now rely only on decoded packet paths, avoiding MQTT observer/receiver fallback links.
- Fix: Turnstile can enable when `PROD_MODE=true` by passing `PROD_MODE`/`PROD_TOKEN` into the container.
- UI: Added `darkreader-lock` meta on the map + landing pages to prevent Dark Reader overrides.

## v1.2.1 (01-29-2026)
- Feature: Display hop numbers on route paths with a toggle button (credit: https://github.com/slack-t).
- Feature: Consistent hop coloring based on route hash (credit: https://github.com/slack-t).
- Feature: Route details panel with hop list, hash byte IDs, and per-hop/cumulative distance (credit: https://github.com/slack-t).
- Fix: Route details updates live when hops arrive and respects km/mi unit toggles.
- Fix: Route details panel now stacks with other tools (no overlap); LOS panel is scrollable.

## v1.2.0 (01-27-2026)
- Add Cloudflare Turnstile protection with a landing/verification flow and auth cookie.
- Turnstile now only activates when `PROD_MODE=true` (even if `TURNSTILE_ENABLED=true`).
- Preserve Discord/social embeds by allowlisting common bots via user-agent bypass.
- Hide the Turnstile site key from the page while still providing it to the widget.
- Credit: Nasticator (PR #13).
- New envs:
  - `TURNSTILE_ENABLED`
  - `TURNSTILE_SITE_KEY`
  - `TURNSTILE_SECRET_KEY`
  - `TURNSTILE_API_URL`
  - `TURNSTILE_TOKEN_TTL_SECONDS`
  - `TURNSTILE_BOT_BYPASS`
  - `TURNSTILE_BOT_ALLOWLIST`

## v1.1.2 (01-27-2026)
- Dev route debug: route lines are now clickable (when `PROD_MODE=false`) and log rich hop-by-hop details to the browser console (distance, hops, hashes, origin/receiver, timestamps). Credit: https://github.com/sefator (PR #14).

## v1.1.1 (01-26-2026)
- Fix: First-hop route selection now prefers the closest repeater/room to the origin when short-hash collisions occur, preventing cross-city mis-picks (Issue: https://github.com/yellowcooln/meshcore-mqtt-live-map/issues/11).

## v1.1.0 (01-21-2026)
- History panel can be dismissed with an X while keeping history lines visible (re-open via History tool).
- Bump service worker cache and asset version to ensure the new History panel behavior loads.

## v1.0.9 (01-16-2026)
- Enforce `ROUTE_MAX_HOP_DISTANCE` for fallback-selected hops to prevent unrealistic jumps (credit: https://github.com/sefator).

## v1.0.8 (01-14-2026)
- Enforce `ROUTE_MAX_HOP_DISTANCE` across fallback hops, direct routes, and receiver appends to prevent cross-region path jumps.

## v1.0.7 (01-14-2026)
- Route hash collisions now prefer known neighbor pairs before falling back to closest-hop selection.
- Add optional neighbor override map via `NEIGHBOR_OVERRIDES_FILE` (default `data/neighbor_overrides.json`).
- Neighbor edges auto-expire using `DEVICE_TTL_SECONDS` (legacy env name, now `DEVICE_TTL_HOURS`) to prevent stale adjacency picks.

## v1.0.6 (01-13-2026)
- Peers panel now labels line colors (blue = incoming, purple = outgoing).
- Propagation origins can be removed individually by clicking their markers.
- HUD scrollbars styled in Chromium for a cleaner look.
- Bump PWA cache version to force asset refresh.
- Suggestions from Zaos.

## v1.0.5 (01-13-2026)
- Resolve short-hash collisions by choosing the closest node in the route chain (credit: https://github.com/sefator)
- Drop hops that exceed `ROUTE_MAX_HOP_DISTANCE` to avoid unrealistic jumps
- Add `ROUTE_INFRA_ONLY` to restrict route lines to repeaters/rooms
- Document new route env defaults in `.env.example`

## v1.0.4 (01-13-2026)
- Open Graph preview URL no longer double-slashes the `/preview.png` path (credit: https://github.com/chrisdavis2110)
- Preview image now renders in-bounds device dots (not just the center pin; credit: https://github.com/chrisdavis2110)
- Fix preview renderer NameError by importing `Tuple`

## v1.0.3 (01-12-2026)
- Fix route decoding to return the correct tuple when paths exceed max length (credit: https://github.com/sefator)

## v1.0.2 (01-11-2026)
- Fix update banner Hide action by honoring the hidden state in CSS
- Remove update banner debug logging after verification

## v1.0.1 (01-11-2025)
- Update check banner (git local vs upstream) with dismiss + auto recheck every 12 hours
- Custom HUD link button (configurable via env, hidden when unset)
- Update banner rendered from HTML dataset to avoid JS/token fetch issues
- Git repo mounted into container for update checks; safe.directory configured automatically
- Update banner Hide button styled to match HUD controls
- New envs: `CUSTOM_LINK_URL`, `MQTT_ONLINE_FORCE_NAMES`, `GIT_CHECK_ENABLED`, `GIT_CHECK_FETCH`, `GIT_CHECK_PATH`, `GIT_CHECK_INTERVAL_SECONDS`

## v1.0.0 (01-10-2025)
- Live MeshCore node map with MQTT ingest, websocket updates, and Leaflet UI
- Node markers with roles, names, and MQTT online ring
- Trace/path, message, and advert route lines with animations
- Heatmap for recent activity (toggle + intensity slider)
- 24h history tool with heat filter + link weight slider
- Peers tool showing inbound/outbound neighbors with map lines
- LOS tool with elevation profile, peaks, relay suggestion, and mobile support
- Propagation tool with right-side panel and map overlay
- Search, labels toggle, hide nodes, map layer toggles, and shareable URL params
- Distance unit toggle (km/mi) with per-user preference
- PWA install support (manifest + service worker)
- Persistent state + route history on disk
