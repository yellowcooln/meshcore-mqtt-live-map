"""Execute the renderer boot module and real base-layer switching code."""
import json
import subprocess
from pathlib import Path

import pytest

STATIC = Path(__file__).resolve().parents[1] / "backend/static"


@pytest.mark.parametrize("failure", ["none", "renderer", "bridge"])
def test_esm_boot_orders_namespace_bridge_and_app(failure):
  script = r"""
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const events = [], scripts = [];
const context = vm.createContext({URL, console, window: {}, document: {
  createElement(tag) {
    if (tag === 'canvas') return {getContext: () => null};
    return {};
  },
  body: {appendChild(script) {events.push('app'); scripts.push(script);}}
}});
const failure = process.argv[1];
const module = new vm.SourceTextModule(fs.readFileSync(process.argv[2], 'utf8'), {
  context,
  initializeImportMeta(meta) {meta.url = 'https://example.test/sub/static/map-renderer.mjs?v=1.9.8';},
  async importModuleDynamically(specifier) {
    const bridge = specifier.includes('leaflet-maplibre');
    const name = bridge ? 'bridge' : 'renderer';
    events.push(name);
    if (failure === name) throw new Error('asset unavailable');
    if (bridge) assert.equal(typeof context.window.maplibregl.Map, 'function');
    const exports = bridge ? [] : ['Map'];
    const dep = new vm.SyntheticModule(exports, function() {
      if (!bridge) this.setExport('Map', function Map() {});
    }, {context});
    await dep.link(() => {}); await dep.evaluate(); return dep;
  }
});
(async () => {
  await module.link(() => {}); await module.evaluate();
  assert.deepEqual(events, failure === 'renderer' ? ['renderer', 'app'] : ['renderer', 'bridge', 'app']);
  assert.equal(scripts.length, 1);
  assert.equal(String(scripts[0].src), 'https://example.test/sub/static/app.js?v=1.9.8');
  if (failure === 'none') {
    assert.equal(typeof context.window.maplibregl.Map, 'function');
    assert.equal(context.window.maplibregl.supported(), false);
  } else assert.equal(context.window.maplibregl, null);
})().catch(error => {console.error(error); process.exitCode = 1;});
"""
  result = subprocess.run([
    "node", "--experimental-vm-modules", "-e", script, failure,
    str(STATIC / "map-renderer.mjs"),
  ], capture_output=True, text=True)
  assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("failure", ["unavailable", "add", "context"])
def test_dark_failure_keeps_raster_and_truthful_theme(failure):
  source = (STATIC / "app.js").read_text()
  start = source.index("function setBaseLayer(")
  end = source.index("function nextStandardMapLayer(", start)
  script = r"""
const assert = require('node:assert/strict');
const lightTiles = {name: 'light'}, topoTiles = {}, satelliteTiles = {};
const events = {};
const darkTiles = FAILURE === 'unavailable' ? null : {
  name: 'dark',
  getMaplibreMap: () => ({getCanvas: () => ({
    addEventListener(name, callback) {events[name] = callback;}
  })})
};
const layers = new Set([lightTiles]);
const map = {
  hasLayer(layer) {assert.ok(layer); return layers.has(layer);},
  removeLayer(layer) {layers.delete(layer);},
  addLayer(layer) {
    assert.ok(layer); layers.add(layer);
    if (FAILURE === 'add' && layer === darkTiles) throw new Error('WebGL unavailable');
  }
};
let baseLayer = 'dark', stored = '', isDark = false;
const document = {body: {classList: {toggle(name, value) {isDark = value;}}}};
const localStorage = {setItem(key, value) {stored = value;}};
const mapToggle = {}, topoToggle = {};
const reportError = () => {};
FUNCTION
setBaseLayer('dark');
if (FAILURE === 'context') {
  assert.equal(typeof events.webglcontextlost, 'function');
  events.webglcontextlost();
}
assert.equal(baseLayer, 'light');
assert.equal(stored, 'light');
assert.equal(isDark, false);
assert.equal(layers.size, 1);
assert.ok(layers.has(lightTiles));
assert.equal(mapToggle.textContent, 'Dark map');
""".replace("FAILURE", json.dumps(failure)).replace(
    "FUNCTION", source[start:end])
  result = subprocess.run(["node", "-e", script],
                          capture_output=True, text=True)
  assert result.returncode == 0, result.stdout + result.stderr
