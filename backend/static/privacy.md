# Privacy Policy

Last updated: July 8, 2026

This privacy policy describes the default behavior of MeshCore Live Map. Individual deployments may be operated by different people or organizations and may use different configuration, logs, reverse proxies, analytics, authentication, and third-party services.

## Information displayed by the map

MeshCore Live Map displays information received from MeshCore/MQTT feeds, which may include:

- Node names and device identifiers
- Public keys or shortened public-key prefixes
- Reported node locations and trails
- Route, hop, peer, and neighbor relationships
- Packet metadata such as packet type, timestamps, signal details, and observer/receiver information
- Device status fields published by connected MeshCore tools

This information is shown to users of the deployment so the mesh network can be monitored and debugged.

## Information processed by the server

Depending on deployment settings, the server may process:

- HTTP requests and WebSocket connections
- IP addresses, user agents, timestamps, and request paths in normal server, container, reverse-proxy, or CDN logs
- Authentication or anti-abuse state when production protection is enabled
- Map snapshots, route history, peer-history buckets, and cached device state

Default route-history data is intended to be short-lived and is controlled by deployment configuration.

## Browser storage

The web app stores map preferences locally in the browser, such as selected layer, units, filters, labels, node size, and panel state. This local storage stays on the user's device unless the user clears site data.

## Cookies and authentication

If Turnstile protection is enabled, the deployment may use an authentication cookie or URL token to remember that a browser passed the challenge. If protection is disabled, the default app does not require a login cookie.

## Third-party services

A deployment may contact third-party services, including:

- Map providers such as OpenStreetMap, OpenFreeMap/OpenMapTiles, CARTO, OpenTopoMap, and EOX Sentinel-2 cloudless imagery
- Cloudflare Turnstile when production protection is enabled
- MeshMapper coverage/wardriving services when coverage features are enabled; MeshMapper has its own privacy policy at https://wiki.meshmapper.net/privacy/
- Optional weather, radar, coverage, elevation, packet-analyzer, or CoreScope services when configured by the operator

Those services may receive normal browser request information such as IP address, user agent, referrer, and requested tile/API URL. The keyless Dark map requests OpenFreeMap vector tiles, styles, fonts, and sprites. When optional CARTO satellite labels are enabled, its per-project key is included in browser tile-request URLs as required by CARTO's documented Leaflet integration; operators must not commit or reuse that key for unrelated projects.

## Sale or sharing of personal information

The default project does not sell personal information. It displays mesh telemetry supplied to the configured MQTT feed and uses third-party services only to provide map, security, weather, coverage, elevation, or analysis features.

## Removal and privacy requests

For a specific public deployment, contact that deployment's operator to request removal or correction of node data, logs, or related information. Because deployments may be independently operated, the open-source project maintainers may not control data shown by every public instance.

## California privacy note

California residents may have privacy rights under laws such as CalOPPA, CCPA, or CPRA depending on who operates a deployment, whether it is commercial, what information it collects, and whether legal thresholds are met. Deployment operators should review their own configuration and legal obligations.

## Changes

This policy may be updated as the project adds features or as deployment practices change.
