"""Old PWA clients must not keep serving the pre-patch app after activation."""
import json
from pathlib import Path
import subprocess

import pytest


SW_JS = Path(__file__).resolve().parents[1] / "backend/static/sw.js"


@pytest.mark.parametrize("base_path", ["", "/socal"])
@pytest.mark.parametrize("legacy_cache", [
  "meshmap-pwa-v7-maplibre6", "meshmap-pwa-v8-live-updates",
  "meshmap-pwa-v9-snapshot-startup"
])
@pytest.mark.parametrize("asset", ["app.js?v=1.9.9", "propagation-worker.js"])
@pytest.mark.parametrize("late_old_write", [False, True])
def test_service_worker_activation_retires_legacy_frontend_cache(
  base_path, legacy_cache, late_old_write, asset
):
  # Retire pre-fix generations used during v1.9.8/v1.9.9 development.
  script = r"""
const assert = require('node:assert/strict');
const vm = require('node:vm');
const legacy = LEGACY_CACHE;
const url = 'https://example.test' + BASE_PATH + '/static/' + ASSET;
const stores = new Map([[legacy, new Map([[url, new Response('old app')]])]]);
let fetches = 0;
const caches = {
  async keys() {return [...stores.keys()];},
  async delete(key) {return stores.delete(key);},
  async match(request, options = {}) {
    for (const [name, store] of stores) {
      if (options.cacheName && name !== options.cacheName) continue;
      const hit = store.get(request.url);
      if (hit) return hit.clone();
    }
  },
  async open(key) {
    if (!stores.has(key)) stores.set(key, new Map());
    return {async put(request, response) {
      stores.get(key).set(request.url, response.clone());
    }};
  },
};
const listeners = {};
const context = {
  __MESHMAP_APP_BASE__: BASE_PATH, URL, caches,
  self: {location: {origin: 'https://example.test'},
    addEventListener: (type, fn) => {listeners[type] = fn;},
    clients: {claim() {}}, skipWaiting() {}},
  fetch: async () => {fetches++; return new Response('updated app');},
};
vm.createContext(context);
vm.runInContext(SOURCE, context);
(async () => {
  let activation;
  listeners.activate({waitUntil: promise => {activation = promise;}});
  await activation;
  assert.equal(stores.has(legacy), false, 'old generation is retired');
  // A retired worker can finish a previously started write after deletion.
  if (LATE_OLD_WRITE) {
    stores.set(legacy, new Map([[url, new Response('old app')]]));
  }
  async function load() {
    let response;
    listeners.fetch({request: {url, method: 'GET', mode: 'cors'},
      respondWith: promise => {response = promise;}});
    return (await response).text();
  }
  assert.equal(await load(), 'updated app',
    'newly activated worker must not serve the old cached frontend');
  assert.equal(fetches, 1);
  assert.equal(await load(), 'updated app');
  assert.equal(fetches, 1, 'fresh assets retain the normal cache-first path');
})().catch(error => {console.error(error); process.exitCode = 1;});
"""
  script = script.replace("ASSET", json.dumps(asset))
  script = script.replace("BASE_PATH", json.dumps(base_path))
  script = script.replace("LEGACY_CACHE", json.dumps(legacy_cache), 1)
  script = script.replace("LATE_OLD_WRITE", json.dumps(late_old_write), 1)
  script = script.replace("SOURCE", json.dumps(SW_JS.read_text()), 1)
  result = subprocess.run(
    ["node", "-e", script], capture_output=True, text=True, timeout=10
  )
  assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("base_path", ["", "/socal"])
def test_worker_http_failure_is_not_cached_so_retry_can_succeed(base_path):
  script = r"""
const assert = require('node:assert/strict');
const vm = require('node:vm');
const stored = new Map();
let attempts = 0;
const request = {url: 'https://example.test' + BASE_PATH + '/static/propagation-worker.js'};
const context = {
  __MESHMAP_APP_BASE__: BASE_PATH,
  self: {addEventListener() {}},
  caches: {
    async match(req) {return stored.get(req.url)?.clone();},
    async open() {return {async put(req, res) {stored.set(req.url, res.clone());}};}
  },
  fetch: async () => ++attempts === 1
    ? new Response('temporary missing worker', {status: 404})
    : new Response('worker code'),
};
vm.createContext(context);
vm.runInContext(SOURCE, context);
(async () => {
  assert.equal((await context.cacheFirst(request)).status, 404);
  assert.equal(stored.size, 0, 'a failed worker response must not poison retries');
  assert.equal(await (await context.cacheFirst(request)).text(), 'worker code');
  assert.equal(await (await context.cacheFirst(request)).text(), 'worker code');
  assert.equal(attempts, 2, 'successful worker remains cached for offline use');
})().catch(error => {console.error(error); process.exitCode = 1;});
""".replace("BASE_PATH", json.dumps(base_path)).replace(
    "SOURCE", json.dumps(SW_JS.read_text()))
  result = subprocess.run(
    ["node", "-e", script], capture_output=True, text=True, timeout=10
  )
  assert result.returncode == 0, result.stderr
