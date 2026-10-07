"""Execute the production popup/link JS with a Leaflet lifecycle fixture."""

import json
import subprocess
from pathlib import Path

import pytest


APP_JS = Path(__file__).resolve().parents[1] / "backend/static/app.js"


def _function(source, name, next_name):
  # Keep whole production functions, including default arguments/templates.
  start = source.index(f"function {name}(")
  end = source.index(f"function {next_name}(", start)
  return source[start:end].strip().removesuffix("async")


@pytest.mark.parametrize("refresh", ["upsert", "presence", "device_seen"])
def test_open_marker_popup_copies_its_node_after_content_refresh(refresh):
  source = APP_JS.read_text(encoding="utf-8")
  functions = "\n".join([
    _function(source, "upsertDevice", "removeDevices"),
    _function(source, "refreshOnlineMarkers", "refreshViewportLayers"),
    _function(source, "handleRealtimeMessage", "connectWS"),
    _function(source, "clearLinkedDeviceParams", "buildMapShareUrl"),
    _function(source, "buildMapShareUrl", "buildDeviceLink"),
    _function(source, "buildDeviceLink", "copyTextWithFallback"),
    "async " + _function(source, "copyNodeLink", "setBaseLayer").split(
      "const shareToggle =", 1)[0],
  ])
  script = r"""
const assert = require('node:assert/strict');
const markers = new Map(), deviceData = new Map(), deviceMeta = new Map();
const polylines = new Map(), copies = [];
const nodeA = {device_id: 'ab'.repeat(32), lat: 34.1, lon: -118.2};
const nodeB = {device_id: 'cd'.repeat(32), lat: 35.3, lon: -119.4};
const window = {
  location: {href: 'https://example.test/socal/map?repeater=old&auth=test'},
  setTimeout() {}
};
const map = {getZoom: () => 9, getCenter: () => ({lat: 0, lng: 0})};
const linkedDeviceParamNames = [
  'node', 'repeater', 'device', 'device_id', 'public_key', 'pubkey'
];
const baseLayer = 'dark', distanceUnits = 'mi', historyFilterMode = 0;
const historyVisible = false, heatVisible = false, coverageVisible = false;
const radarVisible = false, weatherRadarLayerEnabled = false;
const weatherWindLayerEnabled = false, showLabels = false, nodesVisible = true;
const hud = null, historyByteFilter = new Set(), routeByteFilter = new Set();
const routeNodeFilterText = '', visibleRoles = new Set(['repeater']);
const serializeByteFilterSet = () => 'all';
const vectorRenderer = {}, markerLayer = {}, trailLayer = {};
const propagationActive = false, peersActive = false, losActive = false;
const shouldShowDeviceOnMap = () => true;
const resolveRole = () => 'repeater', markerStyleForDevice = () => ({});
const updateMarkerLabel = () => {}, syncLayerMembership = () => {};
const refreshStats = () => {}, refreshViewportLayers = () => {};
const applyMqttPresenceSummary = () => {};
const copyPopupText = () => {}, handleQrPopupClick = () => {};
const makePopup = device => device.device_id;
const copyTextWithFallback = async text => {copies.push(text); return true;};

// Leaflet replaces popup innerHTML on setContent and emits contentupdate,
// but does not emit popupopen again. Model only that UI-library boundary.
class Button {
  constructor(id) {
    this.dataset = {nodeLinkId: id};
    this.textContent = 'Copy repeater link';
    this.listeners = [];
  }
  addEventListener(type, callback) {this.listeners.push(callback);}
  async click() {
    for (const callback of this.listeners) {
      await callback({currentTarget: this,
        preventDefault() {}, stopPropagation() {}});
    }
  }
}
class Popup {
  constructor(id) {this.id = id; this.events = {}; this.root = null;}
  on(type, callback) {
    (this.events[type] ||= []).push(callback); return this;
  }
  getElement() {return this.root;}
  update() {
    if (!this.root) return;
    const button = new Button(this.id);
    this.root = {button, querySelectorAll: selector =>
      selector.includes('data-node-link-id') ? [button] : []};
    for (const callback of this.events.contentupdate || []) callback({});
  }
}
class Marker {
  constructor(coords) {this.coords = coords; this.events = {};}
  on(type, callback) {
    (this.events[type] ||= []).push(callback); return this;
  }
  fire(type) {
    for (const callback of this.events[type] || []) {
      callback({popup: this.popup, originalEvent: {shiftKey: false}});
    }
  }
  bindPopup(id) {this.popup = new Popup(id); return this;}
  getPopup() {return this.popup;}
  setPopupContent(id) {this.popup.id = id; this.popup.update();}
  setLatLng(coords) {this.coords = coords;}
  getLatLng() {return {lat: this.coords[0], lng: this.coords[1]};}
  setStyle() {}
  openPopup() {
    this.popup.root = {};
    this.popup.update();
    this.fire('popupopen');
  }
}
const L = {circleMarker: coords => new Marker(coords)};
__FUNCTIONS__
(async () => {
  // No search/focusDevice call: directly click the node's marker.
  upsertDevice(nodeA);
  upsertDevice(nodeB);
  const marker = markers.get(nodeB.device_id);
  marker.fire('click');
  marker.openPopup();
  await marker.getPopup().getElement().button.click();
  assert.equal(copies.length, 1, 'initial marker copy works');
  if (__REFRESH__ === 'upsert') {
    upsertDevice({...nodeB, lat: 35.6, lon: -119.7});
  } else if (__REFRESH__ === 'device_seen') {
    handleRealtimeMessage({type: 'device_seen',
      device_id: nodeB.device_id, last_seen_ts: 1234567890});
  } else {
    refreshOnlineMarkers();
  }
  await marker.getPopup().getElement().button.click();
  assert.equal(copies.length, 2,
    'refreshed marker popup must still copy without search/reopening');
  // A second update must not duplicate handlers or use another node's ID.
  refreshOnlineMarkers();
  await marker.getPopup().getElement().button.click();
  assert.equal(copies.length, 3);
  const url = new URL(copies.at(-1));
  assert.equal(url.searchParams.get('node'), nodeB.device_id);
  assert.equal(url.searchParams.has('repeater'), false);
  assert.equal(url.pathname, '/socal/map');
  assert.equal(url.searchParams.get('zoom'), '13');
  assert.equal(url.searchParams.get('lat'),
    __REFRESH__ === 'upsert' ? '35.60000' : '35.30000');
  assert.equal(url.searchParams.get('lon'),
    __REFRESH__ === 'upsert' ? '-119.70000' : '-119.40000');
  console.log(JSON.stringify({copies: copies.length, node: url.searchParams.get('node')}));
})().catch(error => {console.error(error); process.exitCode = 1;});
"""
  script = script.replace("__FUNCTIONS__", functions)
  script = script.replace("__REFRESH__", json.dumps(refresh))
  result = subprocess.run(
    ["node", "-e", script], capture_output=True, text=True, timeout=15)
  assert result.returncode == 0, result.stderr
  assert json.loads(result.stdout)["copies"] == 3
