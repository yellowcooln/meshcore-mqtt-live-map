// MapLibre 6 is ESM-only. Load its namespace before the classic Leaflet bridge.
// The adjacent module worker is same-origin: no blob: or unsafe-eval needed.
function supported() {
  const canvas = document.createElement('canvas');
  const context = canvas.getContext('webgl2');
  context?.getExtension('WEBGL_lose_context')?.loseContext();
  return Boolean(context);
}

try {
  const maplibregl = await import('./vendor/maplibre/maplibre-gl.mjs');
  window.maplibregl = { ...maplibregl, supported };
  await import('./vendor/maplibre-leaflet/leaflet-maplibre-gl.js');
} catch {
  // The optional vector renderer must never prevent HTTP/WebSocket startup.
  window.maplibregl = null;
}

// Keep app.js classic so its existing scripts/global behavior is unchanged.
const appScript = document.createElement('script');
const appUrl = new URL('./app.js', import.meta.url);
appUrl.search = new URL(import.meta.url).search;
appScript.src = appUrl.href;
document.body.appendChild(appScript);
