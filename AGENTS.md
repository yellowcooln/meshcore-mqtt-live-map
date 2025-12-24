# Repository Guidelines

## Project Structure & Module Organization
- `backend/app.py`: FastAPI server, MQTT ingest, decoder integration, and state persistence.
- `backend/static/index.html`: Leaflet UI with inline CSS/JS for map rendering.
- `docker-compose.yaml`: container runtime configuration (reads `.env`).
- `data/`: runtime state such as `state.json` and optional `device_roles.json`.
- `README.md` and `docs.md`: usage notes and implementation details.

## Build, Test, and Development Commands
- `cp .env.example .env`: create local configuration (edit MQTT and site metadata).
- `docker compose up -d --build`: build and run the service in the background.
- `docker compose logs -f meshmap-live`: stream backend logs (MQTT + decode output).
- `curl -s http://localhost:8080/snapshot`: verify current device map JSON.
- `curl -s http://localhost:8080/stats`: confirm counters and last-received timestamps.
- `curl -s http://localhost:8080/debug/last`: inspect recent decode entries.

Note: changes to backend or frontend files require a container rebuild (`docker compose up -d --build`).

## Coding Style & Naming Conventions
- Python in `backend/app.py` uses 2-space indentation, `snake_case` for vars/functions, and `SCREAMING_SNAKE_CASE` for env-backed constants.
- Frontend HTML/CSS/JS in `backend/static/index.html` uses 2-space indentation; keep inline styles and JS blocks consistent.
- Environment variables are uppercase with underscores (e.g., `MQTT_WS_PATH`, `SITE_TITLE`).

## Testing Guidelines
- No automated test suite is configured. Validate manually by running the container and checking `/snapshot`, `/stats`, and map behavior.
- If you introduce tests, document the runner in `README.md` and place them under `backend/tests/` with `test_*.py` naming.

## Commit & Pull Request Guidelines
- Commit messages are short, imperative, and sentence-cased (e.g., "Add LOS tool to template").
- PRs should include a clear summary, how you validated changes, and any new/updated env vars.
- UI changes should include a screenshot or brief GIF; data/role changes should call out impacts to `data/state.json`.

## Security & Configuration Tips
- `.env` contains credentials; do not commit it.
- Resetting state or fixing stale roles may require deleting `data/state.json`.
