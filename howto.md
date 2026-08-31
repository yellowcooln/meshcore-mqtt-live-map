# How-To: MQTT Broker + Live Map

This guide covers two parts: stand up a MeshCore MQTT broker and point the live map at it.
Current version: `1.9.7` (see `VERSIONS.md`).

Useful UI defaults in the live map `.env`:
- `HEAT_DEFAULT_ON=true|false` sets the default Heat toggle state for first load.
- `NODE_MARKER_RADIUS=<pixels>` sets the default node marker size before browser overrides.

## 1) MQTT broker (meshcore-mqtt-broker)

Use the broker repo from Michael Hart.

Install dependencies:

```bash
apt install git curl npm
```

Clone the repo:

```bash
git clone https://github.com/michaelhart/meshcore-mqtt-broker
cd meshcore-mqtt-broker
```

Create the data folder:

```bash
mkdir data
```

Create your `.env`:

```bash
cp .env.example .env
```

Edit `.env` and update the database path (use an absolute path that matches your checkout). While you are there, fill out the rest of the `.env` to your liking, and make sure `AUTH_EXPECTED_AUDIENCE` is set to the hostname of your MQTT server:

```bash
# Abuse Detection - Persistence
ABUSE_PERSISTENCE_PATH=/home/user/meshcore-mqtt-broker/data/abuse-detection.db
```

For the live map, the easiest broker auth setup is a dedicated read-only
subscriber account. Add at least one `SUBSCRIBER_N` entry to the broker
`.env`:

```bash
# Format: SUBSCRIBER_N=username:password:role
# Role 1 = admin (includes /internal + $SYS)
# Role 2 = full_access (recommended for most maps)
# Role 3 = limited (filtered payload fields)
SUBSCRIBER_1=meshmap:change-this-password:2
```

Recommended role:
- Use role `2` for most live maps.
- Use role `1` only if you explicitly want `/internal` topics or admin-only
  broker visibility.

Important:
- The live map does **not** generate MeshCore signed auth tokens on its own.
- Do **not** put a node-style username like `v1_<PUBLIC_KEY>` in the map
  unless you are also handling JWT token generation and rotation elsewhere.
- For normal map deployments against `meshcore-mqtt-broker`, use a
  `SUBSCRIBER_N` username/password pair instead.

Build and run:

```bash
npm install
npm run build
npm start
```

---

### Run it as a systemd service (optional)

Create `/etc/systemd/system/meshcore-mqtt.service`:

```bash
[Unit]
Description=MeshCore MQTT Broker
After=network.target

[Service]
Type=simple
User=user
WorkingDirectory=/home/user/meshcore-mqtt-broker

# Start the broker with node + tsx directly
ExecStart=/home/user/.nvm/versions/node/v22.21.1/bin/node /home/user/meshcore-mqtt-broker/node_modules/.bin/tsx src/server.ts

Restart=always
RestartSec=5
Environment=NODE_ENV=production

# Optional logging to files (you can drop these if you prefer journalctl only)
StandardOutput=append:/var/log/meshcore-mqtt.log
StandardError=append:/var/log/meshcore-mqtt-error.log

[Install]
WantedBy=multi-user.target
```

Enable and start:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now meshcore-mqtt
```

---

### Cloudflare Tunnel for MQTT over TLS (optional)

Follow the broker docs for Cloudflare Tunnel setup:

https://github.com/michaelhart/meshcore-mqtt-broker/blob/main/docs/cloudflare-tunnels.md

Note: You can run plain TCP on port 1883, but using a tunnel (or another TLS front) avoids exposing the port on the host. If you do use TCP, make sure you lock it down.

## 2) Configure the live map

Clone the repo and enter it:

```bash
git clone https://github.com/yellowcooln/meshcore-mqtt-live-map
cd meshcore-mqtt-live-map
```

Copy `.env.example` to `.env` and update MQTT settings. The map expects MQTT over WebSockets by default:

```env
MQTT_HOST=your-mqtt-host
MQTT_PORT=443
MQTT_USERNAME=meshmap
MQTT_PASSWORD=change-this-password
MQTT_TRANSPORT=websockets
MQTT_WS_PATH=/
MQTT_TLS=true
# Comma-separated list supported, e.g. meshcore/BOS/#,meshcore/CON/#
MQTT_TOPIC=meshcore/#

# Optional: if you publish the map under a subpath such as
# https://example.com/livemap/, set:
# APP_BASE_PATH=/livemap

# MQTT online presence tuning (v1.5+)
MQTT_ONLINE_SECONDS=300
MQTT_ONLINE_STATUS_TTL_SECONDS=300
MQTT_ONLINE_INTERNAL_TTL_SECONDS=300
MQTT_ACTIVITY_PACKETS_TTL_SECONDS=300
MQTT_STATUS_OFFLINE_VALUES=offline,disconnected
```

Those `MQTT_USERNAME` / `MQTT_PASSWORD` values should match the subscriber
account you created in the broker `.env`, for example:

```env
SUBSCRIBER_1=meshmap:change-this-password:2
```

Authentication summary:
- `meshcore-mqtt-broker` supports signed MeshCore node auth for publishers.
- This live map is normally a read-only subscriber, so it should use a broker
  subscriber account instead.
- If you use subscriber role `3`, some metadata fields are filtered out.
  Role `2` is the recommended default for maps.

<a id="get-and-configure-a-carto-api-key-for-dark-mode"></a>

### Optional CARTO key for satellite labels and dark previews

The browser's Dark map uses OpenFreeMap and does not require a CARTO key.
`CARTO_BASEMAP_KEY` remains optional for the CARTO label overlay on Satellite
and for server-generated dark social preview tiles. Without it, Satellite still
shows EOX Sentinel-2 imagery without labels and dark previews fall back to
OpenStreetMap.

To enable those optional CARTO surfaces:

1. Request a project key from
   [CARTO's basemap key form](https://carto.com/basemaps/apikey/) and register
   every deployment hostname, including `localhost` when needed for development.
2. Review the
   [CARTO Basemaps Terms](https://carto.com/legal/basemap-terms/) and retain the
   required CARTO and OpenStreetMap attribution.
3. Put the key in the deployment's untracked `.env`:

   ```env
   CARTO_BASEMAP_KEY=your-carto-key
   ```

4. Recreate the container so it receives the new environment:

   ```bash
   docker compose up -d --force-recreate
   ```

5. Verify Satellite labels and a shared `lat`/`lon`/`zoom` URL's generated dark
   preview. The normal Dark map should work with or without the key.

Keep the key per-project and out of Git. CARTO's documented browser integration
places it in satellite-label request URLs, so it is not a private server secret
and must not be reused for unrelated projects.

Presence behavior:
- `/status` + `/internal` determine whether a node is shown as **MQTT online**.
- `/packets` is tracked as feed activity and does not, by itself, mark a node online.
- The legend `MQTT online` row has an **Only** button for a temporary
  MQTT-online-only view. It is not saved to browser storage and is not included
  in share links.

Optional coordinate overrides (for fixed node placement):

```env
DEVICE_COORDS_FILE=/data/device_coords.json
```

Optional neighbor override controls (manual + auto):

```env
NEIGHBOR_OVERRIDES_FILE=/data/neighbor_overrides.json
AUTO_NEIGHBOR_OVERRIDES_ENABLED=false
AUTO_NEIGHBOR_OVERRIDES_FILE=/data/neighbor_overrides.auto.json
AUTO_NEIGHBOR_ACTIVE_DAYS=7
AUTO_NEIGHBOR_MIN_EDGE_COUNT=3
AUTO_NEIGHBOR_REFRESH_SECONDS=60
```

Optional channel secrets file (for decrypting sender names from supported group-text packets):

```env
CHANNEL_SECRETS_FILE=/data/channel_secrets.json
```

Copy `channel_secrets.example.json` to your chosen path and keep only the channels you want to ship.

Optional automatic backups:

```env
BACKUP_ENABLED=true
BACKUP_INTERVAL_SECONDS=43200
BACKUP_DIR=/backup
BACKUP_RETENTION_DAYS=7
```

Notes:
- backups are written as timestamped `.tar.gz` archives like `meshmap-backup-2026-03-28T21-15-00.tar.gz`
- only files that currently exist are included
- the default compose setup mounts `./backup:/backup`
- live state stays under `/data`; backups stay under `/backup`

Optional packet analyzer link base (used for Route Details hashes):

```env
PACKET_ANALYZER_URL=
CORESCOPE_URL=https://analyzer.newenglandme.sh
QR_CODE_BUTTON_ENABLED=false
PEERS_DEFAULT_LIMIT=8
PEERS_DEFAULT_OPEN=false
MAP_BOUNDARY_MODE=radius
MAP_BOUNDARY_FILE=/data/map_boundary.json
MAP_BOUNDARY_SHOW=false
LOS_CURVATURE_ENABLED=true
LOS_CURVATURE_FACTOR=1.333333
ROUTE_ALLOW_AMBIGUOUS_ONE_BYTE_FALLBACK=false
```

The Peers panel uses the selected node as the title, keeps the `24h window`
label under that title, and shows Rx/Tx packet totals plus peer counts in the
Incoming/Outgoing headings.

LOS note:
- The live map LOS tool now includes Earth curvature by default.
- Leave `LOS_CURVATURE_ENABLED` unset to keep the default `true`.
- Leave `LOS_CURVATURE_FACTOR` unset to keep the default `1.333333`.
- LOS pins can be added from the map or entered directly by latitude/longitude in the LOS panel, with height stored per pin above ground level.

Optional polygon boundary mode:
```env
MAP_BOUNDARY_MODE=polygon
MAP_BOUNDARY_FILE=/data/map_boundary.json
MAP_BOUNDARY_SHOW=true
```

Boundary files:
- Use `map_boundary.example.json` as the schema reference.
- Open `tools/map-boundary-builder.html` directly in a browser, or use the hosted copy at [https://yellowcooln.com/map-boundary-builder/](https://yellowcooln.com/map-boundary-builder/), to click out a polygon and export `map_boundary.json`.

Optional: enable the coverage layer by setting `COVERAGE_API_URL` (the Coverage button hides itself when blank):

```env
COVERAGE_API_URL=https://coverage.example.com
# The envs below are MeshMapper-only. The legacy coverage map does not use them.
# Optional for MeshMapper coverage.php requests
COVERAGE_API_KEY=
# Show only the last N days on the map. Default 30. Set 0 to disable age filtering.
COVERAGE_MAX_AGE_DAYS=30
# MeshMapper only: fallback cooldown after HTTP 429 if the API does not report resets_in_hours
COVERAGE_RATE_LIMIT_COOLDOWN_SECONDS=3600
# MeshMapper only: local file used to serve cached coverage to users
COVERAGE_CACHE_FILE=/data/coverage_cache.json
# MeshMapper only: server-side refresh interval; default hourly
COVERAGE_SYNC_INTERVAL_SECONDS=3600
#
# Routing note: on large meshes, ambiguous 1-byte prefixes are handled
# conservatively by default. If your network lost routes after v1.7.0 and you
# need the older behavior back, set:
# ROUTE_ALLOW_AMBIGUOUS_ONE_BYTE_FALLBACK=true
# That restores the legacy closest/time-based fallback for colliding 1-byte
# prefixes.
#
# MeshMapper uses the documented domain:
# COVERAGE_API_URL=https://meshmapper.net
WEATHER_RADAR_COUNTRY_BOUNDS_ENABLED=true
# Optional override. Default is /weather/radar/country-bounds on this app.
# This is an HTTP URL path, not a filesystem directory.
WEATHER_RADAR_COUNTRY_LOOKUP_URL=/weather/radar/country-bounds
WEATHER_WIND_ENABLED=true
WEATHER_WIND_API_URL=https://api.open-meteo.com/v1/forecast
WEATHER_WIND_GRID_SIZE=3
WEATHER_WIND_REFRESH_SECONDS=180
```

Optional: configure Weather (Radar + Wind) behavior:

```env
# Master radar feature flag.
WEATHER_RADAR_ENABLED=true
# Keep radar clipped to the active country bounds around map center.
WEATHER_RADAR_COUNTRY_BOUNDS_ENABLED=true
# Keep default unless you run your own lookup endpoint.
WEATHER_RADAR_COUNTRY_LOOKUP_URL=/weather/radar/country-bounds

# Enable/disable wind overlay in the Weather panel.
WEATHER_WIND_ENABLED=true
# Open-Meteo compatible wind API endpoint.
WEATHER_WIND_API_URL=https://api.open-meteo.com/v1/forecast
# Wind sampling density (1-5): higher = more arrows + more API load.
WEATHER_WIND_GRID_SIZE=3
# Wind refresh interval in seconds (minimum 30).
WEATHER_WIND_REFRESH_SECONDS=180
```

If both `WEATHER_RADAR_ENABLED=false` and `WEATHER_WIND_ENABLED=false`, the Weather button is hidden.

If you are using plain TCP MQTT, set:

```env
MQTT_TRANSPORT=tcp
MQTT_TLS=false
MQTT_PORT=1883
```

## 3) Run the map

Background (detached):

```bash
docker compose up -d --build
```

Foreground (watch logs):

```bash
docker compose up --build
```

Open the UI at `http://localhost:8080`.

## 3b) Use the prebuilt Docker image instead

If you do not want to clone the repo and build it yourself, use:

```text
yellowcooln/meshcore-mqtt-live-map:latest
```

Deployment examples in this repo:
- `deploy/docker-compose.image.yaml`
- `deploy/swarm-stack.yaml`
- `deploy/kubernetes-meshmap.yaml`

For Docker Compose / Portainer, the image-based service definition is:

```yaml
services:
  meshmap:
    image: yellowcooln/meshcore-mqtt-live-map:latest
    ports:
      - "8080:8080"
    env_file:
      - .env
    restart: unless-stopped
    volumes:
      - ./data:/data
      - ./backup:/backup
```

## 4) Verify data flow

- `/snapshot` should show devices once adverts arrive.
- `/stats` shows ingest totals.

Example:

```bash
curl -s http://localhost:8080/stats | jq
```

Notes:
- The map only places nodes once it decodes adverts that include a valid location.
- If no nodes appear, verify the MQTT topic and that the broker is sending `/packets` data with raw hex payloads.
