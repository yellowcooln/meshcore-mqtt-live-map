"""Execute production propagation startup/recovery and the real worker math."""
import json
from pathlib import Path
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "backend/static"


def run_node(script):
  result = subprocess.run(
    ["node", "-e", script], capture_output=True, text=True, timeout=15
  )
  assert result.returncode == 0, result.stderr


def worker_controller():
  source = (STATIC / "app.js").read_text()
  start = "function ensurePropagationWorker() {"
  end = "async function ensurePropagationGpu()"
  assert source.count(start) == source.count(end) == 1
  return start + source.split(start, 1)[1].split(end, 1)[0]


@pytest.mark.parametrize("base", ["", "/livemap"])
def test_worker_starts_with_restrictive_csp(base):
  assert "worker-src 'self';" in (STATIC / "index.html").read_text()
  run_node("""
const assert = require('node:assert/strict');
let propagationWorker = null;
const PROP_TERRARIUM_URL = 'https://example.test/{z}/{x}/{y}.png';
const apiPath = path => BASE + path;
class Worker {
  constructor(url) {
    assert.equal(url, BASE + '/static/propagation-worker.js');
  }
}
CONTROLLER
assert.ok(ensurePropagationWorker());
assert.equal(ensurePropagationWorker(), propagationWorker);
""".replace("BASE", json.dumps(base)).replace(
    "CONTROLLER", worker_controller()))


@pytest.mark.parametrize("failure", [
  "error", "messageerror", "render-error", "constructor", "postMessage"
])
def test_worker_failure_releases_render_and_allows_retry(failure):
  source = (STATIC / "app.js").read_text()
  render = "async function renderPropagationRaster() {" + source.split(
    "async function renderPropagationRaster() {", 1
  )[1].split("function setPropagationOrigin(", 1)[0]
  run_node(r"""
const assert = require('node:assert/strict');
let propagationWorker = null, propagationComputeToken = 0;
let propagationRenderInFlight = false, propagationNeedsRender = true;
let propagationBaseRange, propagationLastConfig, status;
const propagationActive = true, propagationOrigins = [{lat: 40, lon: -75}];
const PROP_TERRARIUM_URL = '', PROP_DEFAULTS = {freqMHz: 915};
const apiPath = path => path;
const getPropagationConfig = () => ({model: {n: 2}, txPower: 20, txAntennaGainDb: 0});
const resetPropagationRaster = () => {};
const calcReceiverSensitivityDbm = () => -130;
const calcMaxPathLossDb = () => 150;
const calcRangeMeters = () => 1000;
const derivePropagationResolution = () => ({gridStep: 500, sampleStep: 100});
const calcFsplAt1mDb = () => 30;
const upsertPropagationOriginMarker = () => {};
const updatePropagationSummary = () => {};
const setPropStatus = text => {status = text;};
let fail = FAILURE, instances = [];
class Worker {
  constructor() {
    if (fail === 'constructor') {fail = ''; throw Error('constructor failed');}
    instances.push(this);
  }
  postMessage(msg) {
    if (fail === 'postMessage') {fail = ''; throw Error('postMessage failed');}
    this.request = msg;
  }
  terminate() {this.terminated = true;}
}
CONTROLLER
RENDER
(async () => {
  await renderPropagationRaster();
  const old = propagationWorker;
  if (['error', 'messageerror', 'render-error'].includes(fail)) {
    if (fail === 'render-error') {
      old.onmessage({data: {type: 'error', token: propagationComputeToken,
        error: 'render failed'}});
    } else {
      assert.equal(typeof old['on' + fail], 'function', 'worker failure handler');
      old['on' + fail]({message: 'worker failed', preventDefault() {}});
    }
  }
  assert.equal(propagationRenderInFlight, false, 'failure must unlock Render prop');
  assert.equal(propagationNeedsRender, true);
  assert.match(status, /Render failed:.*[Rr]etry|Render failed:.*Render prop/);
  if (old) assert.equal(old.terminated, true);
  fail = '';
  await renderPropagationRaster();
  const fresh = propagationWorker;
  assert.ok(fresh && fresh !== old, 'retry creates a fresh worker');
  assert.equal(propagationRenderInFlight, true);
  assert.equal(fresh.request.token, propagationComputeToken);
  fresh.onmessage({data: {type: 'progress', token: propagationComputeToken,
    row: 1, rows: 2}});
  assert.equal(status, 'Rendering: 50%');
  const before = status;
  // Late events from a dead worker or a cancelled token cannot affect retry.
  if (old) {
    old.onmessage({data: {type: 'error', token: propagationComputeToken,
      error: 'late error'}});
    if (old.onerror) old.onerror({message: 'late failure'});
  }
  fresh.onmessage({data: {type: 'error', token: propagationComputeToken - 1}});
  assert.equal(propagationWorker, fresh);
  assert.equal(propagationRenderInFlight, true);
  assert.equal(status, before);
  propagationComputeToken++;
  propagationRenderInFlight = false;
  fresh.onerror({message: 'failure after cancellation'});
  assert.equal(status, before, 'cancelled work cannot overwrite UI');
})().catch(error => {console.error(error); process.exitCode = 1;});
""".replace("FAILURE", json.dumps(failure)).replace(
    "CONTROLLER", worker_controller()).replace("RENDER", render))


def test_static_worker_computes_progress_pixels_and_overlap():
  # Node's thread adapter supplies browser messaging only; all RF math and
  # transferable buffers execute in the actual shipped worker asset.
  run_node("""
const assert = require('node:assert/strict');
const {Worker} = require('node:worker_threads');
const fs = require('node:fs');
const source = fs.readFileSync(ASSET, 'utf8');
const adapter = `const {parentPort} = require('node:worker_threads');
 global.self = {postMessage: (msg, transfer) => parentPort.postMessage(msg, transfer)};
 ${source}
 parentPort.on('message', data => self.onmessage({data}));`;
const worker = new Worker(adapter, {eval: true});
const timer = setTimeout(() => {worker.terminate(); throw Error('worker timeout');}, 5000);
let progress = 0, sawError = false;
worker.on('error', error => {throw error;});
worker.on('message', msg => {
  if (msg.token === 6) {
    assert.equal(msg.type, 'error');
    assert.equal(msg.error, 'No origins provided');
    sawError = true;
    worker.postMessage(request);
    return;
  }
  assert.equal(msg.token, 7);
  if (msg.type === 'progress') {progress++; return;}
  try {
    assert.equal(msg.type, 'result');
    assert.ok(progress > 0);
    assert.equal(sawError, true, 'actual worker recovers after invalid input');
    assert.ok(msg.width >= 4 && msg.height >= 4);
    const coverage = new Uint8Array(msg.coverage);
    const pixels = new Uint8ClampedArray(msg.pixels);
    assert.equal(pixels.length, msg.width * msg.height * 4);
    assert.ok(coverage.some(count => count === 2));
    assert.ok(coverage.some(count => count === 0));
    const i = coverage.findIndex(count => count === 2) * 4;
    assert.deepEqual([...pixels.slice(i, i + 4)], [34, 197, 94, 255]);
  } finally {clearTimeout(timer); worker.terminate();}
});
const request = {type: 'render', token: 7,
 origins: [{lat: 40, lon: -75}, {lat: 40, lon: -75}],
 renderRange: 1000, maxPathLossDb: 160, fspl1mDb: 30, freqMHz: 915,
 config: {gridStep: 500, sampleStep: 100, useTerrain: false,
 txAgl: 10, pathLossExp: 2, fadeByMargin: false}};
worker.postMessage({...request, token: 6, origins: []});
""".replace("ASSET", json.dumps(str(STATIC / "propagation-worker.js"))))
