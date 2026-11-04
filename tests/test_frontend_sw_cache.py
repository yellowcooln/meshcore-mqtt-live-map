"""Old PWA clients must not keep serving the pre-patch app after activation."""
import json
from pathlib import Path
import subprocess

import pytest


SW_JS = Path(__file__).resolve().parents[1] / "backend/static/sw.js"


@pytest.mark.parametrize("base_path", ["", "/socal"])
@pytest.mark.parametrize("late_old_write", [False, True])
def test_service_worker_activation_retires_legacy_frontend_cache(
  base_path, late_old_write
):
  # v1.9.8 and early v1.9.9 used this generation with cache-first static JS.
  script = r"""
const assert = require('node:assert/strict');
const vm = require('node:vm');
const legacy = 'meshmap-pwa-v7-maplibre6';
const url = 'https://example.test' + BASE_PATH + '/static/app.js?v=1.9.9';
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
  script = script.replace("BASE_PATH", json.dumps(base_path))
  script = script.replace("LATE_OLD_WRITE", json.dumps(late_old_write), 1)
  script = script.replace("SOURCE", json.dumps(SW_JS.read_text()), 1)
  result = subprocess.run(
    ["node", "-e", script], capture_output=True, text=True, timeout=10
  )
  assert result.returncode == 0, result.stderr
