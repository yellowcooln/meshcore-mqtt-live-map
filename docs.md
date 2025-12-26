# Mesh Map Live: Implementation Notes

This document captures the state of the project and the key changes made so far, so a new Codex session can pick up without losing context.

## Overview
This project renders live MeshCore traffic on a Leaflet + OpenStreetMap map. A FastAPI backend subscribes to MQTT (WSS/TLS), decodes MeshCore packets using `@michaelhart/meshcore-decoder`, and broadcasts device updates and routes over WebSockets to the frontend. The UI includes heatmap, LOS tools, and map mode toggles.

## Key Paths
- `backend/app.py`: FastAPI server, MQTT client, decoder integration, persistence, routing, role/name logic.
- `backend/static/index.html`: Leaflet UI, markers, legends, routes, styles.
- `docker-compose.yaml`: runtime configuration.
- `data/state.json`: persisted device/trail/roles/names/routes (loaded at startup).
- `.env`: dev configuration (mirrors template variables).

## Runtime Commands (Typical Workflow)
- `docker compose up -d --build` (run after any file changes).
- `docker compose logs -f meshmap-live` (watch MQTT + decode logs).
- `curl -s http://localhost:8080/snapshot` (current device map).
- `curl -s http://localhost:8080/stats` (counters, route types).
- `curl -s http://localhost:8080/debug/last` (recent MQTT decode/debug entries).

## MQTT + Decoder
- MQTT is **WebSockets + TLS** (`MQTT_TRANSPORT=websockets`, `MQTT_TLS=true`, `MQTT_WS_PATH=/` or `/mqtt`).
- Decoder uses Node + `@michaelhart/meshcore-decoder` installed in the container.
- `app.py` writes a small Node helper and calls it to decode MeshCore packets.

## Frontend UI
- Header includes a GitHub link icon and HUD summary (stats, feed note).
- Base map toggle: Light/Dark/Topo; persisted to localStorage.
- Dark map also darkens node popups for readability.
- Legend is collapsible and persisted to localStorage.
- HUD is capped to `90vh` and scrolls to avoid running off-screen.
- Map start position is configurable with `MAP_START_LAT`, `MAP_START_LON`, `MAP_START_ZOOM`.
- Node search (name or key) and a labels toggle (persisted to localStorage).
- Hide Nodes toggle hides markers and trails; routes remain visible.
- Propagation overlay keeps heat/routes/trails/markers above it after render.
- Heatmap includes all route payload types (adverts are no longer skipped).
- MQTT online status shows as a green marker outline and popup status; legend includes the online window.

## LOS (Line of Sight) Tool
- LOS runs **server-side only** via `/los` (no client-side elevation fetch).
- UI draws an LOS line (green clear / red blocked), renders an elevation profile, and marks peaks.
- Peak markers show coords + elevation and copy coords on click.
- Hovering the profile or the LOS line syncs a cursor tooltip on the profile.
- Shift+click nodes or click two points on the map to run LOS.

## Device Names + Roles
- Names come from advert payloads or status messages when available.
- Roles are only accepted from explicit decoder fields:
  - `deviceRole`/`deviceRoleName` (MeshCore advert flags), or `role` fields in payload.
  - Name-based role heuristics were removed to avoid mislabels.
- Roles are **not** assigned to the receiver of a packet. For decoded packets, the role applies to the **advertised pubkey** (decoded `location.pubkey` or `decoded_pubkey`).
- Roles persist to `data/state.json` with `device_role_sources`. Only explicit/override roles are restored on load.
- Optional overrides: `data/device_roles.json` can force roles per device_id.

## Routes / Message Paths
Routes are drawn when:
- A packet contains a path list (decoder `pathHashes` or `path`), or
- Multiple observers see the same message hash (fanout), or
- As a fallback, when one hash maps to a known device, a direct line is drawn to the receiver.

If routes aren’t visible:
- The packet may only include a single hop (`path: ["24"]`).
- Other repeaters might not be publishing to MQTT, so the message is only seen by one observer.
- Routes and trails drop any `0,0` coordinates and will purge bad entries on load.

## Frontend Map UI
- Legend includes Trace/Message/Advert line styles and Repeater/Companion/Room/Unknown dot colors.
- Unknown markers were made more visible (larger, higher contrast gray).
- Zoom control moved to bottom-right.
- Route lines are thicker/bolder for large screens.
- LOS profile panel appears under the LOS status while active.

## Persistence
- Devices, trails, names, roles, and routes are saved to `data/state.json`.
- On restart, devices should stay visible if `state.json` exists.
- If stale/mis-labeled roles appear, delete `data/state.json` or remove role entries.
- State load now removes any `0,0` coordinates from devices/trails.

## Troubleshooting Notes
- If map is empty but MQTT is connected, check `/debug/last` for decoded payloads and `payloadType`.
- If markers appear in the wrong place, inspect `decoder_meta` and location fields.
- If roles flip incorrectly, verify `role_target_id` in `/debug/last`.
- If routes don’t show, verify message hashes appear under multiple receivers in MQTT.

## Recent Fixes / Changes Summary
- Added full WSS support and TLS options.
- Integrated meshcore-decoder for advert/location + role parsing.
- Added `/stats`, `/snapshot`, `/debug/last`, `/debug/status` endpoints.
- Added persistence and state reload logic; safer role restore rules.
- Added route drawing for traces/paths/messages with TTL cleanup.
- Added fallback route when only one hop is known.
- UI: route legend, role legend, and improved marker styles.
- Roles now apply to advertised pubkey, not receiver.
- Docker restarts are required after file changes (always run `docker compose up -d --build`).
- LOS is server-side only; elevation profile/peaks are returned by `/los`.
- MQTT online indicator (green outline + legend) and configurable online window.
- Filters out `0,0` GPS points from devices, trails, and routes.
