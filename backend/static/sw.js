const MESHMAP_APP_BASE = __MESHMAP_APP_BASE__;
const meshmapHomePath = MESHMAP_APP_BASE ? `${MESHMAP_APP_BASE}/` : '/';
const meshmapManifestPath = MESHMAP_APP_BASE
  ? `${MESHMAP_APP_BASE}/manifest.webmanifest`
  : '/manifest.webmanifest';
const CACHE_NAME = 'meshmap-pwa-v7-maplibre6';
const CORE_ASSETS = [meshmapHomePath, meshmapManifestPath];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(CORE_ASSETS))
  );
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key)))
    )
  );
  self.clients.claim();
});

async function cacheFirst(request) {
  const cached = await caches.match(request);
  if (cached) return cached;
  const response = await fetch(request);
  const cache = await caches.open(CACHE_NAME);
  cache.put(request, response.clone());
  return response;
}

async function networkFirst(request) {
  try {
    const response = await fetch(new Request(request, { cache: 'no-store' }));
    const cache = await caches.open(CACHE_NAME);
    cache.put(request, response.clone());
    return response;
  } catch (err) {
    const cached = await caches.match(request);
    if (cached) return cached;
    return caches.match(meshmapHomePath);
  }
}

self.addEventListener('fetch', (event) => {
  if (event.request.method !== 'GET') return;
  const url = new URL(event.request.url);
  if (url.origin !== self.location.origin) return;

  if (event.request.mode === 'navigate') {
    event.respondWith(networkFirst(event.request));
    return;
  }

  const staticPrefix = MESHMAP_APP_BASE ? `${MESHMAP_APP_BASE}/static/` : '/static/';
  if (
    url.pathname.startsWith(staticPrefix) ||
    url.pathname === meshmapManifestPath
  ) {
    event.respondWith(cacheFirst(event.request));
  }
});
