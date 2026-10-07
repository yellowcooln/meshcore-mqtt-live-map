window.__meshmapStarted = true;
const config = document.body ? document.body.dataset : {};
const queryParams = new URLSearchParams(window.location.search);
const cleanConfigValue = (value) => {
  const str = String(value || '').trim();
  return /^\{\{[^{}]+\}\}$/.test(str) ? '' : str;
};
const cartoBasemapKey = cleanConfigValue(config.cartoBasemapKey);
const newEnglandCoreScopeFallback = () => {
  const host = window.location.hostname.toLowerCase();
  return host === 'map.newenglandme.sh' ? 'https://analyzer.newenglandme.sh' : '';
};
const parseNumberParam = (value) => {
  if (value == null) return null;
  const str = String(value).trim();
  if (!str) return null;
  const num = Number(str);
  return Number.isFinite(num) ? num : null;
};
const clampNumber = (value, min, max) => Math.min(max, Math.max(min, value));
const parseBoolParam = (value) => {
  if (value == null) return null;
  const str = String(value).trim().toLowerCase();
  if (!str) return null;
  if (['1', 'true', 'yes', 'on'].includes(str)) return true;
  if (['0', 'false', 'no', 'off'].includes(str)) return false;
  if (!Number.isNaN(Number(str))) return Number(str) > 0;
  return null;
};
const escapeHtmlAttr = (value) => String(value ?? '')
  .replaceAll('&', '&amp;')
  .replaceAll('"', '&quot;')
  .replaceAll("'", '&#39;')
  .replaceAll('<', '&lt;')
  .replaceAll('>', '&gt;');
const escapeHtml = escapeHtmlAttr;
const parseHistoryFilterParam = (value) => {
  if (value == null) return null;
  const str = String(value).trim().toLowerCase();
  if (!str) return null;
  if (str === 'all' || str === '0') return 0;
  if (str === 'blue' || str === '1') return 1;
  if (str === 'yellow' || str === '2') return 2;
  if (str === 'yellowred' || str === 'yellow+red' || str === 'yellow-red' || str === '3') return 3;
  if (str === 'red' || str === '4') return 4;
  return null;
};
const parseRouteByteFilterParam = (value) => {
  if (value == null) return null;
  const str = String(value).trim().toLowerCase();
  if (!str) return null;
  if (str === 'all' || str === '0' || str === '*') return 'all';
  if (str === '1' || str === '1b' || str === '1-byte' || str === '1byte') return '1b';
  if (str === '2' || str === '2b' || str === '2-byte' || str === '2byte') return '2b';
  if (str === '3' || str === '3b' || str === '3-byte' || str === '3byte') return '3b';
  return null;
};
const parseByteFilterSet = (value) => {
  if (value == null) return null;
  const raw = String(value).trim();
  if (!raw) return null;
  const selected = new Set();
  raw.split(/[,+\s|]+/).forEach((part) => {
    const parsed = parseRouteByteFilterParam(part);
    if (parsed === 'all') {
      selected.clear();
      selected.add('all');
    } else if (parsed) {
      selected.add(parsed);
    }
  });
  if (!selected.size) return null;
  if (selected.has('all')) return new Set(['all']);
  return selected;
};
const serializeByteFilterSet = (selected) => {
  if (!selected || selected.has('all') || !selected.size) return 'all';
  return ['1b', '2b', '3b'].filter((value) => selected.has(value)).join(',') || 'all';
};
const queryLat = parseNumberParam(queryParams.get('lat') ?? queryParams.get('latitude'));
const queryLon = parseNumberParam(queryParams.get('lon') ?? queryParams.get('lng') ?? queryParams.get('long') ?? queryParams.get('longitude'));
const queryZoom = parseNumberParam(queryParams.get('zoom'));
const queryLayer = String(queryParams.get('layer') || queryParams.get('map') || '').toLowerCase();
const queryHistoryVisible = parseBoolParam(queryParams.get('history'));
const queryHeatVisible = parseBoolParam(queryParams.get('heat'));
const queryCoverageVisible = parseBoolParam(queryParams.get('coverage'));
const queryWeatherVisible = parseBoolParam(queryParams.get('weather'));
const queryWeatherRadarVisible = parseBoolParam(
  queryParams.get('weather_radar') || queryParams.get('radar')
);
const queryWeatherWindVisible = parseBoolParam(
  queryParams.get('weather_wind') || queryParams.get('wind')
);
const WEATHER_RADAR_LAYER_STORAGE_KEY = 'meshmapWeatherRadarLayerEnabled';
const WEATHER_WIND_LAYER_STORAGE_KEY = 'meshmapWeatherWindLayerEnabled';
const queryLabelsVisible = parseBoolParam(queryParams.get('labels'));
const queryNodesVisible = parseBoolParam(queryParams.get('nodes'));
const queryLegendVisible = parseBoolParam(queryParams.get('legend'));
const queryMenuVisible = parseBoolParam(
  queryParams.get('menu') || queryParams.get('hud') || queryParams.get('panel')
);
const queryUnits = String(queryParams.get('units') || queryParams.get('unit') || '').toLowerCase();
const queryLinkedDevice = String(
  queryParams.get('node') ||
  queryParams.get('repeater') ||
  queryParams.get('device') ||
  queryParams.get('device_id') ||
  queryParams.get('public_key') ||
  queryParams.get('pubkey') ||
  ''
).trim();
const linkedDeviceParamNames = ['node', 'repeater', 'device', 'device_id', 'public_key', 'pubkey'];
const queryHistoryFilter = parseHistoryFilterParam(
  queryParams.get('history_filter') || queryParams.get('historyFilter') || queryParams.get('historyfilter')
);
const queryRouteByteFilter = parseByteFilterSet(
  queryParams.get('route_bytes') ||
  queryParams.get('routeBytes') ||
  queryParams.get('routebytes')
);
const queryHistoryByteFilter = parseByteFilterSet(
  queryParams.get('history_bytes') ||
  queryParams.get('historyBytes') ||
  queryParams.get('historybytes')
);
const queryRouteNodeFilter = String(
  queryParams.get('route_nodes') || queryParams.get('routeNodes') || ''
).trim();
const queryVisibleRoles = String(queryParams.get('roles') || '').trim();
const queryPeersActive = parseBoolParam(
  queryParams.get('peers') ||
  queryParams.get('peer_tool') ||
  queryParams.get('peerTool')
);
const initialUpdateAvailable = parseBoolParam(config.updateAvailable);
const initialUpdateLocal = (config.updateLocal || '').trim();
const initialUpdateRemote = (config.updateRemote || '').trim();
const reportError = typeof window.__meshmapReportError === 'function'
  ? window.__meshmapReportError
  : (message) => console.warn(message);
const appVersion = (config.appVersion || 'dev').trim() || 'dev';
console.info(`[meshmap] version ${appVersion}`);
let serverTimeOffsetMs = 0;

function setServerTimeOffset(serverTimeSeconds) {
  const serverMs = Number(serverTimeSeconds) * 1000;
  if (!Number.isFinite(serverMs) || serverMs <= 0) return;
  serverTimeOffsetMs = serverMs - Date.now();
}

function getServerNowMs() {
  return Date.now() + serverTimeOffsetMs;
}

const envStartLat = parseFloat(config.mapStartLat);
const envStartLon = parseFloat(config.mapStartLon);
const envStartZoom = Number(config.mapStartZoom);
const defaultLat = Number.isFinite(envStartLat) ? envStartLat : 42.3601;
const defaultLon = Number.isFinite(envStartLon) ? envStartLon : -71.1500;
const defaultZoom = Number.isFinite(envStartZoom) && envStartZoom > 0 ? envStartZoom : 10;
const mapStartLat = Number.isFinite(queryLat) ? queryLat : defaultLat;
const mapStartLon = Number.isFinite(queryLon) ? queryLon : defaultLon;
const mapStartZoom = Number.isFinite(queryZoom) && queryZoom > 0 ? queryZoom : defaultZoom;
const mapRadiusKm = Number(config.mapRadiusKm) || 0;
const trailMaxSegmentKm = Math.max(0, Number(config.trailMaxSegmentKm) || 0);
const mapRadiusShow = String(config.mapRadiusShow).toLowerCase() === 'true';
const mapBoundaryMode = String(config.mapBoundaryMode || 'radius').toLowerCase();
const mapBoundaryShow = String(config.mapBoundaryShow).toLowerCase() === 'true';
const mapBoundaryName = String(config.mapBoundaryName || '').trim();
const mapBoundaryDataEl = document.getElementById('map-boundary-data');
let mapBoundaryPoints = [];
if (mapBoundaryDataEl) {
  try {
    const parsed = JSON.parse(mapBoundaryDataEl.textContent || '[]');
    if (Array.isArray(parsed)) {
      mapBoundaryPoints = parsed
        .map((pt) => Array.isArray(pt) && pt.length >= 2 ? [Number(pt[0]), Number(pt[1])] : null)
        .filter((pt) => Array.isArray(pt) && Number.isFinite(pt[0]) && Number.isFinite(pt[1]));
    }
  } catch (_err) {
    mapBoundaryPoints = [];
  }
}
let baseLayer = (config.mapDefaultLayer || 'light').toLowerCase();
const validLayers = new Set(['dark', 'topo', 'satellite', 'light']);
if (validLayers.has(queryLayer)) {
  baseLayer = queryLayer;
}
if (!validLayers.has(baseLayer)) {
  baseLayer = 'light';
}

const map = L.map('map', { zoomControl: false, preferCanvas: true }).setView([mapStartLat, mapStartLon], mapStartZoom);
const vectorRenderer = L.canvas({ padding: 0.3 });
const animatedLineRenderer = L.svg({ padding: 0.3 });
L.control.zoom({ position: 'bottomright' }).addTo(map);
if (!map.getPane('radarPane')) {
  map.createPane('radarPane');
}
const radarPane = map.getPane('radarPane');
if (radarPane) {
  radarPane.style.zIndex = '320';
  radarPane.style.pointerEvents = 'none';
}
if (!map.getPane('weatherWindPane')) {
  map.createPane('weatherWindPane');
}
const weatherWindPane = map.getPane('weatherWindPane');
if (weatherWindPane) {
  weatherWindPane.style.zIndex = '330';
  weatherWindPane.style.pointerEvents = 'none';
}
if (!map.getPane('peerPane')) {
  map.createPane('peerPane');
}
const peerPane = map.getPane('peerPane');
if (peerPane) {
  peerPane.style.zIndex = '340';
  peerPane.style.pointerEvents = 'none';
}
if (!map.getPane('arcadePane')) {
  map.createPane('arcadePane');
}
const arcadePane = map.getPane('arcadePane');
if (arcadePane) {
  arcadePane.style.zIndex = '345';
  arcadePane.style.pointerEvents = 'none';
}
const lightTiles = L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
  maxZoom: 19,
  attribution: '&copy; OpenStreetMap contributors'
}).addTo(map);
const cartoRasterTileUrl = (style) => (
  `https://{s}.basemaps.cartocdn.com/${style}/{z}/{x}/{y}{r}.png` +
  `?key=${encodeURIComponent(cartoBasemapKey)}`
);
const openFreeMapAttribution = (
  '<a href="https://openfreemap.org/" target="_blank" rel="noopener">OpenFreeMap</a> ' +
  '<a href="https://www.openmaptiles.org/" target="_blank" rel="noopener">&copy; OpenMapTiles</a> ' +
  'Data from <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap</a>'
);
const darkTiles = L.maplibreGL({
  style: 'https://tiles.openfreemap.org/styles/dark',
  attributionControl: { customAttribution: openFreeMapAttribution }
});
const topoTiles = L.tileLayer('https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png', {
  maxZoom: 17,
  attribution: '&copy; OpenStreetMap contributors &copy; OpenTopoMap'
});
const satelliteImageryTiles = L.tileLayer(
  'https://tiles.maps.eox.at/wmts/1.0.0/s2cloudless-2024_3857/default/g/{z}/{y}/{x}.jpg',
  {
    maxZoom: 19,
    attribution: 'Sentinel-2 cloudless &copy; EOX IT Services GmbH (contains modified Copernicus Sentinel data 2024)'
  }
);
const satelliteLabelTiles = cartoBasemapKey ? L.tileLayer(
  cartoRasterTileUrl('rastertiles/voyager_only_labels'),
  {
    maxZoom: 19,
    attribution: '&copy; OpenStreetMap contributors &copy; CARTO'
  }
) : null;
const satelliteTiles = L.layerGroup(
  satelliteLabelTiles ? [satelliteImageryTiles, satelliteLabelTiles] : [satelliteImageryTiles]
);
let mapRadiusCircle = null;
const activeBoundaryShow = mapBoundaryShow || mapRadiusShow;
if (mapBoundaryMode === 'radius' && activeBoundaryShow && mapRadiusKm > 0) {
  mapRadiusCircle = L.circle([mapStartLat, mapStartLon], {
    radius: mapRadiusKm * 1000.0,
    color: '#38bdf8',
    weight: 2,
    dashArray: '6 8',
    fillColor: '#38bdf8',
    fillOpacity: 0.05,
    interactive: false
  }).addTo(map);
}
let mapBoundaryPolygon = null;
if (mapBoundaryMode === 'polygon' && activeBoundaryShow && mapBoundaryPoints.length >= 3) {
  mapBoundaryPolygon = L.polygon(mapBoundaryPoints, {
    color: '#38bdf8',
    weight: 2,
    dashArray: '6 8',
    fillColor: '#38bdf8',
    fillOpacity: 0.04,
    interactive: false
  }).addTo(map);
  if (mapBoundaryName) {
    mapBoundaryPolygon.bindTooltip(escapeHtml(mapBoundaryName), {
      permanent: false,
      direction: 'center',
      sticky: false,
      opacity: 0.9
    });
  }
}
const storedLayer = localStorage.getItem('meshmapBaseLayer');
if (!validLayers.has(queryLayer) && validLayers.has(storedLayer)) {
  baseLayer = storedLayer;
}

const prodMode = String(config.prodMode).toLowerCase() === 'true';
const apiToken = config.prodToken || '';
const qrCodeButtonEnabled =
  String(config.qrCodeButtonEnabled).toLowerCase() === 'true';
const routeHistoryEnabled =
  String(config.routeHistoryEnabled).trim().toLowerCase() === 'true';
const publicPathPrefix = String(config.appBasePath || '').trim();
const apiPath = (path) => {
  const p = path.startsWith('/') ? path : `/${path}`;
  if (!publicPathPrefix) return p;
  return `${publicPathPrefix}${p}`;
};
if (map.attributionControl) {
  const privacyHref = escapeHtmlAttr(apiPath('/privacy'));
  map.attributionControl.addAttribution(
    `<a href="${privacyHref}" target="_blank" rel="noopener">Privacy</a>`
  );
}
const tokenHeaders = () => (prodMode && apiToken ? { 'x-access-token': apiToken } : {});
const withToken = (path) => {
  const resolved = apiPath(path);
  if (!prodMode || !apiToken) return resolved;
  const url = new URL(resolved, window.location.origin);
  url.searchParams.set('token', apiToken);
  return `${url.pathname}${url.search}`;
};

const markers = new Map();   // device_id -> Leaflet marker
const polylines = new Map(); // device_id -> Leaflet polyline
const markerLayer = L.layerGroup().addTo(map);
const trailLayer = L.layerGroup().addTo(map);
let nodesVisible = true;
let mqttOnlyVisible = false;
const routeLines = new Map(); // route_id -> { line, timeout }
const routeCache = new Map(); // route_id -> raw route payload
const deviceMeta = new Map(); // device_id -> { lat, lon, name }
const historyLines = new Map(); // edge_id -> { line, count }
const historyCache = new Map(); // edge_id -> raw edge data
let mqttPresenceKnown = false;
let mqttConnectedTotal = 0;
const historyLayer = L.layerGroup();
const peerLayer = L.layerGroup();
const peerLines = new Map(); // peer_id -> line
const routeLayer = L.layerGroup().addTo(map);
const arcadeLayer = L.layerGroup();
const hopLayer = L.layerGroup();
const hopMarkers = new Map(); // route_id -> [markers]
let hopsVisible = false;
let arcadeModeEnabled = false;
const FLOW_MIN_DURATION_MS = 2800;
const FLOW_MAX_DURATION_MS = 9000;
let arcadeAnimFrame = null;

function routeStyleForDisplay(payloadType, routeMode, arcadeMode = false) {
  const isFanout = routeMode === 'fanout';
  const payloadNum = Number(payloadType);
  const isAdvert = payloadNum === 4;
  const isTrace = payloadNum === 8 || payloadNum === 9;
  const isMessage = payloadNum === 2 || payloadNum === 5;
  const style = {
    color: isAdvert
      ? '#2ecc71'
      : (isTrace ? '#ff7a1a' : (isMessage ? '#2b8cff' : (isFanout ? '#2b8cff' : '#ff7a1a'))),
    weight: isFanout ? 4 : 5,
    opacity: isFanout ? 0.85 : 0.9,
    lineCap: 'butt',
    lineJoin: 'miter',
  };
  if (isAdvert) {
    style.dashArray = '2 10';
  } else if (isMessage) {
    style.dashArray = '6 12';
  } else if (isTrace) {
    style.dashArray = '8 14';
  } else if (!isFanout) {
    style.dashArray = '8 14';
  }
  if (arcadeMode) {
    style.weight = isFanout ? 3 : 2.5;
    style.opacity = 0.42;
    style.lineCap = 'round';
    style.lineJoin = 'round';
    if (isAdvert) {
      style.dashArray = '2 16';
    } else if (isMessage) {
      style.dashArray = '2 18';
    } else if (isTrace) {
      style.dashArray = '2 22';
    } else {
      style.dashArray = '2 20';
    }
  }
  return style;
}

function setArcadeModeEnabled(enabled, persist = true) {
  arcadeModeEnabled = Boolean(enabled);
  if (arcadeModeEnabled && nodesVisible) {
    if (!map.hasLayer(routeLayer)) {
      routeLayer.addTo(map);
    }
    if (!map.hasLayer(arcadeLayer)) {
      arcadeLayer.addTo(map);
    }
    routeLines.forEach((entry, routeId) => {
      if (entry && Array.isArray(entry.routePoints)) {
        syncArcadeForRoute(routeId, entry.routePoints);
      }
      if (entry && entry.line) {
        entry.line.setStyle(
          routeStyleForDisplay(entry.payloadType, entry.routeMode, true)
        );
        const lineEl = entry.line.getElement();
        if (lineEl) {
          lineEl.classList.remove('route-animated');
        }
      }
    });
    syncAllRouteDisplays();
    startArcadeLoop();
  } else {
    routeLines.forEach((_entry, routeId) => removeArcadeMarker(routeId));
    routeLines.forEach((entry) => {
      if (!entry || !entry.line) return;
      entry.line.setStyle(
        routeStyleForDisplay(entry.payloadType, entry.routeMode, false)
      );
      const lineEl = entry.line.getElement();
      if (lineEl) {
        lineEl.classList.add('route-animated');
      }
    });
    if (map.hasLayer(arcadeLayer)) {
      map.removeLayer(arcadeLayer);
    }
    stopArcadeLoop();
  }
}
const losElevationUrl = config.losElevationUrl || 'https://api.opentopodata.org/v1/srtm90m';
const losElevationProxyUrl = (config.losElevationProxyUrl || '/los/elevations').trim();
const losElevationFetchUrl = (() => {
  if (!losElevationUrl) return losElevationProxyUrl;
  try {
    const parsed = new URL(losElevationUrl, window.location.origin);
    if (parsed.origin === window.location.origin) {
      return parsed.toString();
    }
  } catch (err) {
    // ignore malformed URL and fall back to proxy
  }
  return losElevationProxyUrl || losElevationUrl;
})();
const losSampleMin = Number(config.losSampleMin) || 10;
const losSampleMax = Number(config.losSampleMax) || 80;
const losSampleStepMeters = Number(config.losSampleStepMeters) || 250;
const losCurvatureEnabled = parseBoolParam(config.losCurvatureEnabled) ?? true;
const losCurvatureFactor = (() => {
  const parsed = Number(config.losCurvatureFactor);
  if (Number.isFinite(parsed) && parsed > 0) return parsed;
  return 1.333333;
})();
const heatDefaultOn = parseBoolParam(config.heatDefaultOn) ?? true;
const losPeaksMax = Number(config.losPeaksMax) || 4;
const mqttOnlineSeconds = Number(config.mqttOnlineSeconds) || 300;
const mqttOnlineStatusTtlSeconds = Number(config.mqttOnlineStatusTtlSeconds) || mqttOnlineSeconds;
const mqttOnlineInternalTtlSeconds = Number(config.mqttOnlineInternalTtlSeconds) || mqttOnlineSeconds;
const defaultDistanceUnits = config.distanceUnits || 'km';
const heatAvailable = typeof L.heatLayer === 'function';
const heatLayer = heatAvailable ? L.heatLayer([], {
  radius: 28,
  blur: 22,
  minOpacity: 0.2,
  maxZoom: 16,
  gradient: { 0.2: '#fbbf24', 0.5: '#f97316', 0.8: '#ef4444', 1.0: '#b91c1c' }
}) : null;
const heatPoints = [];
const HEAT_TTL_MS = 10 * 60 * 1000;
const losLayer = L.layerGroup().addTo(map);
const losPointIcon = L.divIcon({
  className: 'los-point-icon',
  iconSize: [14, 14],
  iconAnchor: [7, 7]
});
const coverageApiUrl = cleanConfigValue(config.coverageApiUrl);
const customLinkUrl = cleanConfigValue(config.customLinkUrl);
const packetAnalyzerUrl = cleanConfigValue(config.packetAnalyzerUrl);
const coreScopeUrl = cleanConfigValue(config.corescopeUrl) ||
  newEnglandCoreScopeFallback();
const coverageEnabled = Boolean(coverageApiUrl);
const coverageLayer = L.layerGroup();
let coverageVisible = false;
let coverageData = null;
let meshMapperCoverageRects = [];
let meshMapperCoverageSource = null;
let meshMapperCoverageExpanded = [];
let coverageProvider = '';
let coverageRegion = '';
let coverageAttributionHtml = '';
const radarLayerGroup = L.layerGroup();
let radarLayer = null;
let radarVisible = false;
let radarLoading = false;
let radarPreloading = false;
let radarPreloadTimeout = null;
let radarFramePath = '';
let radarFrameHost = 'https://tilecache.rainviewer.com';
let radarRefreshTimer = null;
let radarRequestSeq = 0;
let radarLayerBoundsKey = '';
let radarCountryBounds = null;
let radarCountryBoundsKey = '';
let radarCountryBoundsPromise = null;
const RADAR_REFRESH_MS = 5 * 60 * 1000;
const RADAR_META_URLS = [
  'https://tilecache.rainviewer.com/api/weather-maps.json',
  'https://api.rainviewer.com/public/weather-maps.json'
];
const RADAR_MAX_NATIVE_ZOOM = 7;
const weatherRadarEnabled = String(config.weatherRadarEnabled).toLowerCase() !== 'false';
const weatherRadarCountryBoundsEnabled = String(config.weatherRadarCountryBoundsEnabled).toLowerCase() === 'true';
const weatherRadarCountryLookupUrl = (config.weatherRadarCountryLookupUrl || '/weather/radar/country-bounds').trim();
const WEATHER_RADAR_COUNTRY_CACHE_KEY = 'meshmapWeatherRadarCountryBounds';
const weatherWindLayer = L.layerGroup();
let weatherWindRequestSeq = 0;
let weatherWindRefreshTimer = null;
let weatherWindMoveTimer = null;
let weatherWindLoading = false;
const weatherWindEnabled = String(config.weatherWindEnabled).toLowerCase() !== 'false';
const weatherWindApiUrl = (config.weatherWindApiUrl || 'https://api.open-meteo.com/v1/forecast').trim();
const weatherWindGridSizeRaw = Number(config.weatherWindGridSize);
const weatherWindGridSize = Number.isFinite(weatherWindGridSizeRaw)
  ? clampNumber(Math.round(weatherWindGridSizeRaw), 1, 5)
  : 3;
const weatherWindRefreshSecondsRaw = Number(config.weatherWindRefreshSeconds);
const weatherWindRefreshMs = (Number.isFinite(weatherWindRefreshSecondsRaw)
  ? clampNumber(Math.round(weatherWindRefreshSecondsRaw), 30, 1800)
  : 180) * 1000;
const weatherAvailable = weatherRadarEnabled || weatherWindEnabled;
let weatherRadarLayerEnabled = weatherRadarEnabled;
let weatherWindLayerEnabled = weatherWindEnabled;
let losActive = false;
let losPoints = [];
let losLines = [];
let losSegmentMeta = [];
let losActiveSegmentIndex = null;
let losSuggestion = null;
let losPeakMarkers = [];
let losHoverMarker = null;
let losActivePeak = null;
let losLocked = false;
let losDragging = false;
let losComputeToken = 0;
let losComputeLast = 0;
let losComputeTimer = null;
const LOS_COMPUTE_THROTTLE_MS = 100;
const LOS_FINAL_DEBOUNCE_MS = 220;
const LOS_ELEVATION_CACHE_PRECISION = 4;
const LOS_ELEVATION_CACHE_STEP = 1 / Math.pow(10, LOS_ELEVATION_CACHE_PRECISION);
const LOS_ELEVATION_CACHE_TTL_MS = 6 * 60 * 60 * 1000;
const LOS_ELEVATION_CACHE_MAX = 4000;
const losElevationCache = new Map();
const LOS_ELEVATION_FETCH_MIN_MS = 500;
const LOS_ELEVATION_BACKOFF_MS = 2500;
let losElevationLastFetchMs = 0;
let losElevationBackoffUntil = 0;
let losLastElevations = null;
let losLastElevationCount = 0;
let lastLosDistance = null;
let lastLosStatusMeta = null;
const losProfile = document.getElementById('los-profile');
const losProfileSvg = document.getElementById('los-profile-svg');
const losProfileTooltip = document.getElementById('los-profile-tooltip');
const losLegendGroup = document.getElementById('legend-los-group');
const losClearButton = document.getElementById('los-clear');
const losRemoveLastButton = document.getElementById('los-remove-last');
const losPanel = document.getElementById('los-panel');
const losPanelCollapse = document.getElementById('los-panel-collapse');
const losHeightAInput = document.getElementById('los-height-a');
const losHeightBInput = document.getElementById('los-height-b');
const losPointLabel = document.getElementById('los-point-label');
const losPointLatInput = document.getElementById('los-point-lat');
const losPointLonInput = document.getElementById('los-point-lon');
const losPointHeightInput = document.getElementById('los-point-height');
const losAddCoordsButton = document.getElementById('los-add-coords');
const losUpdatePointButton = document.getElementById('los-update-point');
const propPanel = document.getElementById('prop-panel');
const propPanelCollapse = document.getElementById('prop-panel-collapse');
const historyPanel = document.getElementById('history-panel');
const historyLegendGroup = document.getElementById('legend-history-group');
const coverageLegendGroup = document.getElementById('legend-coverage-group');
const historyPanelLabel = document.getElementById('history-panel-label');
const historyPanelCollapse = document.getElementById('history-panel-collapse');
const weatherPanel = document.getElementById('weather-panel');
const weatherHideButton = document.getElementById('weather-hide');
const weatherRadarLayerToggle = document.getElementById('weather-radar-layer-toggle');
const weatherWindLayerToggle = document.getElementById('weather-wind-layer-toggle');
const peersPanel = document.getElementById('peers-panel');
const peersPanelCollapse = document.getElementById('peers-panel-collapse');
const peersTitle = document.getElementById('peers-title');
const peersWindow = document.getElementById('peers-window');
const peersStatus = document.getElementById('peers-status');
const peersMeta = document.getElementById('peers-meta');
const peersInHeading = document.getElementById('peers-in-heading');
const peersOutHeading = document.getElementById('peers-out-heading');
const peersIn = document.getElementById('peers-in');
const peersOut = document.getElementById('peers-out');
const peersToggle = document.getElementById('peers-toggle');
const peersClear = document.getElementById('peers-clear');
const peersFilter = document.getElementById('peers-filter');
const routeDetailsPanel = document.getElementById('route-details-panel');
const routeDetailsTitle = document.getElementById('route-details-title');
const routeDetailsContent = document.getElementById('route-details-content');
const routeDetailsTotal = document.getElementById('route-details-total');
const routeDetailsCollapse = document.getElementById('route-details-collapse');
const qrModal = document.getElementById('qr-modal');
const qrModalBackdrop = document.getElementById('qr-modal-backdrop');
const qrModalClose = document.getElementById('qr-modal-close');
const qrModalTitle = document.getElementById('qr-modal-title');
const qrModalLabel = document.getElementById('qr-modal-label');
const qrModalImage = document.getElementById('qr-modal-image');
let activeRouteDetailsMeta = null;
let activeRouteDetailsId = null;
let losProfileData = [];
let losProfileMeta = null;
let losPointMarkers = [];
let losSelectedPointIndex = null;
let losPointHeights = [];
const loadLosPointHeights = () => {
  try {
    const raw = localStorage.getItem('meshmapLosPointHeights');
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed.map((value) => {
      const n = Number(value);
      return Number.isFinite(n) ? n : 0;
    });
  } catch (_err) {
    return [];
  }
};
losPointHeights = loadLosPointHeights();
const persistLosPointHeights = () => {
  try {
    localStorage.setItem('meshmapLosPointHeights', JSON.stringify(losPointHeights));
  } catch (_err) {
    // ignore storage failures
  }
};
const getLosPointHeight = (index) => {
  if (!Number.isInteger(index) || index < 0) return 0;
  const value = Number(losPointHeights[index]);
  return Number.isFinite(value) ? value : 0;
};
const setLosPointHeight = (index, value) => {
  if (!Number.isInteger(index) || index < 0) return;
  const next = Number(value);
  losPointHeights[index] = Number.isFinite(next) ? next : 0;
  persistLosPointHeights();
};
const formatLosPointCoordinate = (value) => {
  const next = Number(value);
  return Number.isFinite(next) ? next.toFixed(6) : '';
};
const syncLosPointEditor = () => {
  const hasSelection = Number.isInteger(losSelectedPointIndex) &&
    losSelectedPointIndex >= 0 &&
    losSelectedPointIndex < losPoints.length;
  if (losPointLabel) {
    losPointLabel.textContent = hasSelection
      ? `Selected pin ${losSelectedPointIndex + 1}.`
      : 'No pin selected.';
  }
  if (losUpdatePointButton) {
    losUpdatePointButton.disabled = !hasSelection;
  }
  if (!hasSelection) return;
  const point = losPoints[losSelectedPointIndex];
  if (losPointLatInput) {
    losPointLatInput.value = formatLosPointCoordinate(point.lat);
  }
  if (losPointLonInput) {
    losPointLonInput.value = formatLosPointCoordinate(point.lng);
  }
  if (losPointHeightInput) {
    losPointHeightInput.value = String(getLosPointHeight(losSelectedPointIndex));
  }
};
const syncLosHeightInputs = () => {
  const startIdx = Number.isInteger(losActiveSegmentIndex) ? losActiveSegmentIndex : null;
  const endIdx = Number.isInteger(startIdx) ? startIdx + 1 : null;
  if (losHeightAInput) {
    losHeightAInput.value = String(startIdx != null ? getLosPointHeight(startIdx) : 0);
    losHeightAInput.disabled = startIdx == null;
  }
  if (losHeightBInput) {
    losHeightBInput.value = String(endIdx != null ? getLosPointHeight(endIdx) : 0);
    losHeightBInput.disabled = endIdx == null;
  }
  syncLosPointEditor();
};
syncLosHeightInputs();
const deviceData = new Map();
const linkedDeviceTarget = normalizeLinkedDeviceTarget(queryLinkedDevice);
let linkedDeviceFocusDone = !linkedDeviceTarget;
const searchInput = document.getElementById('node-search');
const searchResults = document.getElementById('node-search-results');
const nodeSizeInput = document.getElementById('node-size');
const nodeSizeValue = document.getElementById('node-size-value');
let searchMatches = [];
let focusDeviceToken = 0;
const storedLabels = localStorage.getItem('meshmapShowLabels');
let showLabels = storedLabels === 'true';
if (storedLabels === null) {
  localStorage.setItem('meshmapShowLabels', 'false');
}
const validUnits = new Set(['km', 'mi']);
let distanceUnits = (localStorage.getItem('meshmapDistanceUnits') || defaultDistanceUnits || 'km').toLowerCase();
if (!validUnits.has(distanceUnits)) {
  distanceUnits = 'km';
  localStorage.setItem('meshmapDistanceUnits', distanceUnits);
}
if (validUnits.has(queryUnits)) {
  distanceUnits = queryUnits;
  localStorage.setItem('meshmapDistanceUnits', distanceUnits);
}
const NODE_RADIUS_MIN = 4;
const NODE_RADIUS_MAX = 14;
const envNodeRadius = Number(config.nodeRadius);
const defaultNodeRadius = Number.isFinite(envNodeRadius) ? envNodeRadius : 8;
let nodeMarkerRadius = defaultNodeRadius;
const storedRadius = parseNumberParam(localStorage.getItem('meshmapNodeRadius'));
if (Number.isFinite(storedRadius)) {
  nodeMarkerRadius = storedRadius;
}
nodeMarkerRadius = clampNumber(nodeMarkerRadius, NODE_RADIUS_MIN, NODE_RADIUS_MAX);
if (!Number.isFinite(storedRadius)) {
  localStorage.setItem('meshmapNodeRadius', String(nodeMarkerRadius));
}
const historyLabel = document.getElementById('history-window-label');
const historyFilter = document.getElementById('history-filter');
const historyFilterLabel = document.getElementById('history-filter-label');
const historyByteFilterSelect = document.getElementById('history-byte-filter');
const historyLinkSizeInput = document.getElementById('history-link-size');
const historyLinkSizeValue = document.getElementById('history-link-size-value');
const routeByteFilterSelect = document.getElementById('route-byte-filter');
const routeNodeFilterInput = document.getElementById('route-node-filter');
const routeNodeFilterResults = document.getElementById('route-node-filter-results');
const roleFilterButtons = [...document.querySelectorAll('[data-role-filter]')];
let historyWindowSeconds = null;
if (!routeHistoryEnabled) {
  historyWindowSeconds = 0;
}
const historyToolVersion = '1';
localStorage.setItem('meshmapHistoryToolVersion', historyToolVersion);
let historyVisible = false;
let historyPanelHidden = false;
let weatherPanelHidden = false;
const peersDefaultOpen = parseBoolParam(config.peersDefaultOpen) === true;
let peersActive = false;
let peersSelectedId = null;
let peersData = null;
let peersRequestToken = 0;
let peersFilterText = '';
let historyFilterMode = Number(localStorage.getItem('meshmapHistoryFilter') || '0');
if (queryHistoryFilter != null) {
  historyFilterMode = queryHistoryFilter;
  localStorage.setItem('meshmapHistoryFilter', String(historyFilterMode));
}
if (![0, 1, 2, 3, 4].includes(historyFilterMode)) {
  historyFilterMode = 0;
  localStorage.setItem('meshmapHistoryFilter', '0');
}
if (historyFilter) {
  historyFilter.value = String(historyFilterMode);
}
const ROUTE_BYTE_FILTER_VALUES = new Set(['all', '1b', '2b', '3b']);
const normalizeByteFilterSet = (selected) => {
  const values = selected instanceof Set ? selected : parseByteFilterSet(selected);
  if (!values || !values.size || values.has('all')) return new Set(['all']);
  const filtered = new Set([...values].filter((value) => ROUTE_BYTE_FILTER_VALUES.has(value) && value !== 'all'));
  return filtered.size ? filtered : new Set(['all']);
};
const defaultRouteByteFilter = parseByteFilterSet(config.routeByteFilterDefault) || new Set(['all']);
const defaultHistoryByteFilter = parseByteFilterSet(config.historyByteFilterDefault) || new Set(['all']);
let routeByteFilter = normalizeByteFilterSet(
  queryRouteByteFilter ||
  parseByteFilterSet(localStorage.getItem('meshmapRouteByteFilter')) ||
  defaultRouteByteFilter
);
let historyByteFilter = normalizeByteFilterSet(
  queryHistoryByteFilter ||
  parseByteFilterSet(localStorage.getItem('meshmapHistoryByteFilter')) ||
  defaultHistoryByteFilter
);
let routeNodeFilterText = queryRouteNodeFilter ||
  localStorage.getItem('meshmapRouteNodeFilter') || '';
let routeNodeMatches = [];
const roleDefaultConfig = {
  repeater: parseBoolParam(config.showRepeatersDefault) !== false,
  companion: parseBoolParam(config.showCompanionsDefault) !== false,
  room: parseBoolParam(config.showRoomServersDefault) !== false,
  unknown: parseBoolParam(config.showUnknownDefault) !== false
};
const parseVisibleRoles = (raw) => {
  const values = new Set(
    String(raw || '').toLowerCase().split(',').map(value => value.trim()).filter(Boolean)
  );
  return new Set(
    ['repeater', 'companion', 'room', 'unknown'].filter(role => values.has(role))
  );
};
const storedVisibleRoles = localStorage.getItem('meshmapVisibleRoles');
let visibleRoles = storedVisibleRoles === null
  ? new Set(Object.keys(roleDefaultConfig).filter(role => roleDefaultConfig[role]))
  : parseVisibleRoles(storedVisibleRoles);
if (queryParams.has('roles')) {
  visibleRoles = parseVisibleRoles(queryVisibleRoles);
  localStorage.setItem('meshmapVisibleRoles', [...visibleRoles].join(','));
}
if (routeNodeFilterInput) routeNodeFilterInput.value = routeNodeFilterText;
const setByteFilterChecks = (root, selected) => {
  if (!root) return;
  const normalized = normalizeByteFilterSet(selected);
  root.querySelectorAll('input[type="checkbox"]').forEach((input) => {
    input.checked = normalized.has(input.value);
  });
  const label = root.querySelector('.byte-summary-label');
  if (label) {
    const text = serializeByteFilterSet(normalized)
      .split(',')
      .map((value) => ({ all: 'All', '1b': '1-byte', '2b': '2-byte', '3b': '3-byte' }[value] || value))
      .join(', ');
    label.textContent = text;
  }
};
const selectedByteFilterFromGroup = (root, changedInput = null) => {
  if (!root) return new Set(['all']);
  const allInput = root.querySelector('input[value="all"]');
  const specific = [...root.querySelectorAll('input[type="checkbox"]')]
    .filter((input) => input.value !== 'all');
  if (changedInput && changedInput.value === 'all' && changedInput.checked) {
    specific.forEach((input) => { input.checked = false; });
    return new Set(['all']);
  }
  if (changedInput && changedInput.value !== 'all' && changedInput.checked && allInput) {
    allInput.checked = false;
  }
  const selected = new Set(
    specific.filter((input) => input.checked).map((input) => input.value)
  );
  if (!selected.size || selected.size === specific.length) {
    if (allInput) allInput.checked = true;
    specific.forEach((input) => { input.checked = false; });
    return new Set(['all']);
  }
  return normalizeByteFilterSet(selected);
};
const positionByteDropdown = (root) => {
  if (!root || !root.open) return;
  const summary = root.querySelector('summary');
  const panel = root.querySelector('.byte-check-options');
  if (!summary || !panel) return;
  const rect = summary.getBoundingClientRect();
  const width = Math.max(rect.width, 128);
  const panelHeight = Math.max(panel.offsetHeight, 1);
  const viewportPad = 8;
  const left = Math.min(
    Math.max(viewportPad, rect.right - width),
    Math.max(viewportPad, window.innerWidth - width - viewportPad)
  );
  const belowTop = rect.bottom + 4;
  const aboveTop = rect.top - panelHeight - 4;
  const top = belowTop + panelHeight + viewportPad <= window.innerHeight
    ? belowTop
    : Math.max(viewportPad, aboveTop);
  panel.style.width = `${width}px`;
  panel.style.left = `${left}px`;
  panel.style.top = `${top}px`;
};
const setupByteDropdown = (root) => {
  if (!root) return;
  root.addEventListener('toggle', () => {
    if (root.open) {
      [routeByteFilterSelect, historyByteFilterSelect].forEach((other) => {
        if (other && other !== root) other.open = false;
      });
      requestAnimationFrame(() => positionByteDropdown(root));
    }
  });
};
setupByteDropdown(routeByteFilterSelect);
setupByteDropdown(historyByteFilterSelect);
document.addEventListener('click', (ev) => {
  const target = ev.target;
  [routeByteFilterSelect, historyByteFilterSelect].forEach((root) => {
    if (root && root.open && !root.contains(target)) {
      root.open = false;
    }
  });
});
document.addEventListener('keydown', (ev) => {
  if (ev.key !== 'Escape') return;
  [routeByteFilterSelect, historyByteFilterSelect].forEach((root) => {
    if (root) root.open = false;
  });
});
window.addEventListener('resize', () => {
  positionByteDropdown(routeByteFilterSelect);
  positionByteDropdown(historyByteFilterSelect);
});
setByteFilterChecks(routeByteFilterSelect, routeByteFilter);
setByteFilterChecks(historyByteFilterSelect, historyByteFilter);
const HISTORY_LINK_MIN = 0.1;
const HISTORY_LINK_MID = 1;
const HISTORY_LINK_MAX = 2;
const envHistoryLinkScale = Number(config.historyLinkScale);
let historyLinkScale = Number.isFinite(envHistoryLinkScale) ? envHistoryLinkScale : 1;
const storedHistoryLinkScale = parseNumberParam(localStorage.getItem('meshmapHistoryLinkScale'));
if (Number.isFinite(storedHistoryLinkScale)) {
  historyLinkScale = storedHistoryLinkScale;
}
historyLinkScale = clampNumber(historyLinkScale, HISTORY_LINK_MIN, HISTORY_LINK_MAX);
if (!Number.isFinite(storedHistoryLinkScale)) {
  localStorage.setItem('meshmapHistoryLinkScale', String(historyLinkScale));
}
const sliderToHistoryScale = (value) => {
  const t = clampNumber(Number(value), 0, 100);
  if (t <= 50) {
    return HISTORY_LINK_MIN + (t / 50) * (HISTORY_LINK_MID - HISTORY_LINK_MIN);
  }
  return HISTORY_LINK_MID + ((t - 50) / 50) * (HISTORY_LINK_MAX - HISTORY_LINK_MID);
};
const historyScaleToSlider = (scale) => {
  const v = clampNumber(scale, HISTORY_LINK_MIN, HISTORY_LINK_MAX);
  if (v <= HISTORY_LINK_MID) {
    return ((v - HISTORY_LINK_MIN) / (HISTORY_LINK_MID - HISTORY_LINK_MIN)) * 50;
  }
  return 50 + ((v - HISTORY_LINK_MID) / (HISTORY_LINK_MAX - HISTORY_LINK_MID)) * 50;
};
const updateHistoryLinkSizeUI = () => {
  if (historyLinkSizeInput) {
    historyLinkSizeInput.value = String(Math.round(historyScaleToSlider(historyLinkScale)));
  }
  if (historyLinkSizeValue) historyLinkSizeValue.textContent = `${historyLinkScale.toFixed(1)}x`;
};
updateHistoryLinkSizeUI();
const storedHeat = localStorage.getItem('meshmapShowHeat');
let heatVisible = storedHeat !== null ? storedHeat === 'true' : heatDefaultOn;
if (storedHeat === null) {
  localStorage.setItem('meshmapShowHeat', heatDefaultOn ? 'true' : 'false');
}
const mqttWindowLabel = document.getElementById('mqtt-online-label');
const mqttOnlyToggle = document.getElementById('mqtt-only-toggle');
if (mqttWindowLabel) {
  const mqttWindowSeconds = Math.max(
    mqttOnlineSeconds,
    mqttOnlineStatusTtlSeconds,
    mqttOnlineInternalTtlSeconds
  );
  mqttWindowLabel.textContent = `MQTT online (last ${formatOnlineWindow(mqttWindowSeconds)})`;
}
function updateMqttOnlyToggleUi() {
  if (!mqttOnlyToggle) return;
  mqttOnlyToggle.classList.toggle('active', mqttOnlyVisible);
  mqttOnlyToggle.setAttribute('aria-pressed', mqttOnlyVisible ? 'true' : 'false');
  mqttOnlyToggle.textContent = mqttOnlyVisible ? 'All' : 'Only';
  mqttOnlyToggle.title = mqttOnlyVisible
    ? 'Show all nodes'
    : 'Only show MQTT online nodes';
}
updateMqttOnlyToggleUi();

const propagationLayer = L.layerGroup().addTo(map);
let propagationActive = false;
let propagationOrigins = [];
let propagationOriginMarkers = new Map();
let propagationOriginSeq = 0;
let propagationRaster = null;
let propagationRasterCanvas = null;
let propagationRasterMeta = null;
let propagationBaseRange = null;
let propagationNeedsRender = false;
let propagationRenderInFlight = false;
let propagationComputeToken = 0;
let propagationWorker = null;
let propagationLastConfig = null;
let propagationGpu = null;
let propagationGpuInitPromise = null;
const LOS_PANEL_COLLAPSED_KEY = 'meshmapLosPanelCollapsed';
const PROP_PANEL_COLLAPSED_KEY = 'meshmapPropPanelCollapsed';
const HISTORY_PANEL_COLLAPSED_KEY = 'meshmapHistoryPanelCollapsed';
const PEERS_PANEL_COLLAPSED_KEY = 'meshmapPeersPanelCollapsed';
const ROUTE_DETAILS_PANEL_COLLAPSED_KEY = 'meshmapRouteDetailsPanelCollapsed';
let losPanelCollapsed = parseBoolParam(localStorage.getItem(LOS_PANEL_COLLAPSED_KEY)) === true;
let propPanelCollapsed = parseBoolParam(localStorage.getItem(PROP_PANEL_COLLAPSED_KEY)) === true;
let historyPanelCollapsed =
  parseBoolParam(localStorage.getItem(HISTORY_PANEL_COLLAPSED_KEY)) === true;
let peersPanelCollapsed =
  parseBoolParam(localStorage.getItem(PEERS_PANEL_COLLAPSED_KEY)) === true;
let routeDetailsPanelCollapsed =
  parseBoolParam(localStorage.getItem(ROUTE_DETAILS_PANEL_COLLAPSED_KEY)) === true;

const PROP_DEFAULTS = {
  freqMHz: 910.525,
  bwHz: 62500,
  sf: 7,
  cr: 8,
  snrMinDb: -7.5,
  noiseFigureDb: 6,
  fadeMarginDb: 10,
  fresnelFactor: 0.2,
  txAntennaGainDb: 3,
  clearanceRatio: 0.6,
  clearanceLossDb: 12,
  earthRadiusM: 6371000 * (4 / 3)
};

const PROP_TERRARIUM_URL = 'https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png';

const PROP_MODELS = {
  free: { label: 'Best-case (free-space)', n: 2.0, clutterLossDb: 0 },
  suburban: { label: 'Suburban', n: 2.2, clutterLossDb: 6 },
  urban: { label: 'Urban', n: 2.3, clutterLossDb: 10 },
  indoor: { label: 'Indoor/obstructed', n: 2.7, clutterLossDb: 18 }
};

function resolveRole(d) {
  const role = (d.role || '').toLowerCase();
  if (role.includes('repeater')) return 'repeater';
  if (role.includes('companion')) return 'companion';
  if (role.includes('room')) return 'room';
  return 'unknown';
}

function meshCoreContactTypeForDevice(d) {
  const role = String(d?.role || '').toLowerCase();
  if (role.includes('repeater')) return 2;
  if (role.includes('room')) return 3;
  if (role.includes('sensor')) return 4;
  return 1;
}

function markerStyleForRole(role) {
  if (role === 'repeater') {
    return { color: '#1d4ed8', fillColor: '#2b8cff', fillOpacity: 0.95, radius: nodeMarkerRadius, weight: 2 };
  }
  if (role === 'companion') {
    return { color: '#6b21a8', fillColor: '#a855f7', fillOpacity: 0.95, radius: nodeMarkerRadius, weight: 2 };
  }
  if (role === 'room') {
    return { color: '#b45309', fillColor: '#f59e0b', fillOpacity: 0.95, radius: nodeMarkerRadius, weight: 2 };
  }
  return { color: '#4b5563', fillColor: '#d1d5db', fillOpacity: 0.95, radius: nodeMarkerRadius, weight: 2 };
}

function markerStyleForDevice(d) {
  const role = resolveRole(d);
  const base = markerStyleForRole(role);
  if (isMqttOnline(d)) {
    return { ...base, color: '#22c55e', weight: 3 };
  }
  return base;
}

function applyMqttPresenceSummary(summary) {
  if (!summary || typeof summary !== 'object') return;
  if (summary.connected_total != null) {
    const n = Number(summary.connected_total);
    if (Number.isFinite(n) && n >= 0) {
      mqttConnectedTotal = Math.floor(n);
      mqttPresenceKnown = true;
    }
  }
}

function setStats() {
  const onlineOnMap = Array.from(deviceData.values()).filter(isMqttOnline).length;
  const onlineTotal = mqttPresenceKnown ? mqttConnectedTotal : onlineOnMap;
  const totalRoutes = routeLines.size;
  const visibleRoutes = getVisibleRouteCount();
  const routeFiltersInactive = routeByteFilter.has('all') &&
    !routeNodeFilterText.trim();
  const routeLabel = routeFiltersInactive || visibleRoutes === totalRoutes
    ? `${visibleRoutes} routes`
    : `${visibleRoutes}/${totalRoutes} routes`;
  document.getElementById('stats').textContent = `${markers.size} active devices • ${onlineTotal} MQTT online • ${routeLabel} • ${historyLines.size} history`;
}

let statsFramePending = false;
let deferStats = false;

function scheduleStatsUpdate() {
  if (statsFramePending) return;
  statsFramePending = true;
  window.requestAnimationFrame(() => {
    statsFramePending = false;
    setStats();
  });
}

function refreshStats() {
  if (deferStats) {
    scheduleStatsUpdate();
    return;
  }
  setStats();
}

function formatOnlineWindow(seconds) {
  if (!seconds || seconds <= 0) return '0 min';
  if (seconds >= 3600) {
    const hours = Math.round(seconds / 3600);
    return `${hours} hr`;
  }
  const minutes = Math.max(1, Math.round(seconds / 60));
  return `${minutes} min`;
}

// Geohash decoder (simple implementation)
function geohashDecode(geohash) {
  const BASE32 = '0123456789bcdefghjkmnpqrstuvwxyz';
  const BASE32_DICT = {};
  for (let i = 0; i < BASE32.length; i++) {
    BASE32_DICT[BASE32[i]] = i;
  }
  let even = true;
  let lat = [-90.0, 90.0];
  let lon = [-180.0, 180.0];
  let lat_err = 90.0;
  let lon_err = 180.0;
  for (let i = 0; i < geohash.length; i++) {
    const c = geohash[i];
    const cd = BASE32_DICT[c];
    for (let j = 0; j < 5; j++) {
      if (even) {
        lon_err /= 2;
        if ((cd & (16 >> j)) > 0) {
          lon[0] = (lon[0] + lon[1]) / 2;
        } else {
          lon[1] = (lon[0] + lon[1]) / 2;
        }
      } else {
        lat_err /= 2;
        if ((cd & (16 >> j)) > 0) {
          lat[0] = (lat[0] + lat[1]) / 2;
        } else {
          lat[1] = (lat[0] + lat[1]) / 2;
        }
      }
      even = !even;
    }
  }
  return {
    latitude: (lat[0] + lat[1]) / 2,
    longitude: (lon[0] + lon[1]) / 2,
    error: { latitude: lat_err, longitude: lon_err }
  };
}

function geohashDecodeBbox(geohash) {
  const decoded = geohashDecode(geohash);
  const latErr = decoded.error.latitude;
  const lonErr = decoded.error.longitude;
  return [
    decoded.latitude - latErr,
    decoded.longitude - lonErr,
    decoded.latitude + latErr,
    decoded.longitude + lonErr
  ];
}

function successRateToColor(rate) {
  const clampedRate = Math.max(0, Math.min(1, rate));
  let red, green, blue;
  if (clampedRate >= 0.8) {
    const t = (clampedRate - 0.8) / 0.2;
    red = Math.round(0 + (50 - 0) * t);
    green = Math.round(100 + (150 - 100) * t);
    blue = Math.round(0 + (50 - 0) * t);
  } else if (clampedRate >= 0.6) {
    const t = (clampedRate - 0.6) / 0.2;
    red = Math.round(50 + (255 - 50) * t);
    green = Math.round(150 + (165 - 150) * t);
    blue = Math.round(50 - 50 * t);
  } else if (clampedRate >= 0.4) {
    const t = (clampedRate - 0.4) / 0.2;
    red = 255;
    green = Math.round(165 + (100 - 165) * t);
    blue = 0;
  } else if (clampedRate >= 0.2) {
    const t = (clampedRate - 0.2) / 0.2;
    red = 255;
    green = Math.round(100 - 100 * t);
    blue = 0;
  } else {
    red = 255;
    green = 0;
    blue = 0;
  }
  const toHex = (n) => {
    const hex = n.toString(16);
    return hex.length === 1 ? '0' + hex : hex;
  };
  return `#${toHex(red)}${toHex(green)}${toHex(blue)}`;
}

async function fetchCoverageData() {
  try {
    const response = await fetch(withToken('/coverage'));
    if (!response.ok) {
      const errorText = await response.text().catch(() => 'Unknown error');
      throw new Error(`HTTP ${response.status}: ${errorText}`);
    }
    const data = await response.json();
    return {
      data,
      provider: String(response.headers.get('x-coverage-provider') || '').trim().toLowerCase(),
      region: String(response.headers.get('x-coverage-region') || '').trim().toUpperCase()
    };
  } catch (err) {
    const errorMsg = err && err.message ? err.message : String(err);
    reportError(`Failed to fetch coverage data: ${errorMsg}`);
    return null;
  }
}

function buildCoverageAttributionHtml() {
  if (coverageProvider !== 'meshmapper' || !coverageRegion) return '';
  if (!/^[A-Z0-9-]+$/.test(coverageRegion)) return '';
  const regionHost = coverageRegion.toLowerCase();
  return `<a href="https://${regionHost}.meshmapper.net" target="_blank" rel="noopener noreferrer">MeshMapper</a>`;
}

function updateCoverageAttribution() {
  const next = (coverageVisible && coverageData) ? buildCoverageAttributionHtml() : '';
  if (coverageAttributionHtml && map && map.attributionControl) {
    map.attributionControl.removeAttribution(coverageAttributionHtml);
    coverageAttributionHtml = '';
  }
  if (next && map && map.attributionControl) {
    map.attributionControl.addAttribution(next);
    coverageAttributionHtml = next;
  }
}

function updateCoverageLegend() {
  if (!coverageLegendGroup) return;
  const active = coverageVisible && coverageProvider === 'meshmapper' && Array.isArray(coverageData) && coverageData.length > 0;
  coverageLegendGroup.classList.toggle('active', active);
}

function getRenderBounds() {
  if (!map || !map.getBounds) return null;
  try {
    return map.getBounds().pad(0.2);
  } catch (_err) {
    return null;
  }
}

function boundsIntersectsViewport(south, west, north, east) {
  const viewport = getRenderBounds();
  if (!viewport) return true;
  const tileBounds = L.latLngBounds([[south, west], [north, east]]);
  return viewport.intersects(tileBounds);
}

function latLngInViewport(lat, lon) {
  const viewport = getRenderBounds();
  if (!viewport) return true;
  return viewport.contains([lat, lon]);
}

function syncLayerMembership(layer, item, shouldAttach) {
  if (!layer || !item) return;
  const attached = item.__attached === true;
  if (shouldAttach && !attached) {
    layer.addLayer(item);
    item.__attached = true;
    return;
  }
  if (!shouldAttach && attached) {
    layer.removeLayer(item);
    item.__attached = false;
  }
}

function coverageTimeLabel(ts) {
  const raw = typeof ts === 'string' ? Number.parseInt(ts, 10) : ts;
  if (!Number.isFinite(raw) || raw <= 0) return '';
  const ms = raw < 946684800000 ? raw * 1000 : raw;
  const date = new Date(ms);
  if (Number.isNaN(date.getTime())) return '';
  return date.toLocaleString();
}

function meshMapperCoveragePriority(type) {
  switch (String(type || '').trim().toUpperCase()) {
    case 'BIDIR':
      return 6;
    case 'DISC':
    case 'TRACE':
    case 'DISC/TRACE':
      return 5;
    case 'TX':
      return 4;
    case 'RX':
      return 3;
    case 'DEAD':
      return 2;
    case 'DROP':
      return 1;
    default:
      return 0;
  }
}

function expandMeshMapperCoverageSquares(data) {
  const merged = new Map();
  for (const square of data) {
    const bounds = square?.bounds;
    if (!bounds) continue;
    const south = Number(bounds.south);
    const west = Number(bounds.west);
    const north = Number(bounds.north);
    const east = Number(bounds.east);
    if (![south, west, north, east].every(Number.isFinite)) continue;
    const latStep = north - south;
    const lonStep = east - west;
    if (!(latStep > 0) || !(lonStep > 0)) continue;
    const priority = meshMapperCoveragePriority(square.coverage_type);
    const timestamp = Number(square.timestamp) || 0;
    for (let latOffset = -1; latOffset <= 1; latOffset += 1) {
      for (let lonOffset = -1; lonOffset <= 1; lonOffset += 1) {
        const nextSouth = south + (latStep * latOffset);
        const nextWest = west + (lonStep * lonOffset);
        const nextNorth = nextSouth + latStep;
        const nextEast = nextWest + lonStep;
        const key = `${nextSouth.toFixed(7)}:${nextWest.toFixed(7)}`;
        const current = merged.get(key);
        const shouldReplace = !current
          || priority > current.__priority
          || (priority === current.__priority && timestamp > current.__timestamp);
        if (!shouldReplace) continue;
        merged.set(key, {
          ...square,
          bounds: {
            south: nextSouth,
            west: nextWest,
            north: nextNorth,
            east: nextEast
          },
          __priority: priority,
          __timestamp: timestamp,
          __source_grid_id: square.grid_id || null
        });
      }
    }
  }
  return Array.from(merged.values());
}

function buildMeshMapperCoverageRect(square) {
  const bounds = square?.bounds;
  if (!bounds) return null;
  const south = Number(bounds.south);
  const west = Number(bounds.west);
  const north = Number(bounds.north);
  const east = Number(bounds.east);
  if (![south, west, north, east].every(Number.isFinite)) return null;
  const fillColor = square.fill_color || '#1e7e34';
  const rect = L.rectangle([[south, west], [north, east]], {
    renderer: vectorRenderer,
    stroke: true,
    color: square.border_color || fillColor,
    weight: 0.4,
    opacity: 0.22,
    fillOpacity: 0.5,
    fillColor
  });
  const details = [];
  if (square.coverage_type) {
    details.push(`Type: ${escapeHtml(square.coverage_type)}`);
  }
  if (square.snr !== null && square.snr !== undefined) {
    details.push(`SNR: ${escapeHtml(square.snr)} dB`);
  }
  const when = coverageTimeLabel(square.timestamp);
  if (when) details.push(`Updated: ${escapeHtml(when)}`);
  if (square.__source_grid_id) {
    details.push(`Source grid: ${escapeHtml(square.__source_grid_id)}`);
  }
  rect.bindPopup(details.join('<br/>'), { maxWidth: 320 });
  rect.__coverageBounds = { south, west, north, east };
  rect.__attached = false;
  return rect;
}

function renderMeshMapperCoverage(data) {
  coverageLayer.clearLayers();
  meshMapperCoverageSource = data;
  meshMapperCoverageExpanded = expandMeshMapperCoverageSquares(data);
  meshMapperCoverageRects = [];
  for (const square of meshMapperCoverageExpanded) {
    const rect = buildMeshMapperCoverageRect(square);
    if (rect) meshMapperCoverageRects.push(rect);
  }
  return syncMeshMapperCoverageViewport();
}

function syncMeshMapperCoverageViewport() {
  let rendered = 0;
  for (const rect of meshMapperCoverageRects) {
    const bounds = rect?.__coverageBounds;
    if (!bounds) continue;
    const visible = boundsIntersectsViewport(
      bounds.south,
      bounds.west,
      bounds.north,
      bounds.east
    );
    syncLayerMembership(coverageLayer, rect, visible);
    if (visible) rendered++;
  }
  return rendered;
}

function renderCoverage(data) {
  coverageLayer.clearLayers();
  meshMapperCoverageRects = [];
  meshMapperCoverageSource = null;
  meshMapperCoverageExpanded = [];
  if (!data || !Array.isArray(data)) {
    updateCoverageAttribution();
    updateCoverageLegend();
    return;
  }
  if (data.some(sample => sample && typeof sample === 'object' && sample.bounds)) {
    renderMeshMapperCoverage(data);
    updateCoverageAttribution();
    updateCoverageLegend();
    return;
  }
  // Aggregate samples by 6-char geohash prefix (coverage tile level)
  const tileMap = new Map(); // 6-char prefix -> { heard: count, lost: count, samples: [...] }
  for (const sample of data) {
    const hash = sample.hash || sample.name || sample.id;
    if (!hash) continue;
    const tileHash = hash.substring(0, 6); // Use 6-char prefix for coverage tiles
    if (!tileMap.has(tileHash)) {
      tileMap.set(tileHash, { heard: 0, lost: 0, samples: [], latestTime: 0, snr: null, rssi: null, paths: new Set() });
    }
    const tile = tileMap.get(tileHash);
    const observed = sample.observed !== undefined ? sample.observed : (sample.metadata?.observed !== undefined ? sample.metadata.observed : ((sample.path || sample.metadata?.path || []).length > 0));
    if (observed) {
      tile.heard++;
    } else {
      tile.lost++;
    }
    tile.samples.push(sample);
    const time = sample.time || sample.metadata?.time || 0;
    // Convert to number if it's a string, and handle milliseconds vs seconds
    let timeValue = typeof time === 'string' ? parseInt(time, 10) : (typeof time === 'number' ? time : 0);
    // If time looks like seconds (less than year 2000 in milliseconds), convert to milliseconds
    if (timeValue > 0 && timeValue < 946684800000) {
      timeValue = timeValue * 1000;
    }
    if (timeValue > tile.latestTime) {
      tile.latestTime = timeValue;
      tile.snr = sample.snr !== null && sample.snr !== undefined ? sample.snr : (sample.metadata?.snr !== null && sample.metadata?.snr !== undefined ? sample.metadata.snr : tile.snr);
      tile.rssi = sample.rssi !== null && sample.rssi !== undefined ? sample.rssi : (sample.metadata?.rssi !== null && sample.metadata?.rssi !== undefined ? sample.metadata.rssi : tile.rssi);
    }
    const path = sample.path || sample.metadata?.path || [];
    path.forEach(p => tile.paths.add(p));
  }
  let rendered = 0;
  for (const [tileHash, tile] of tileMap.entries()) {
    try {
      const [minLat, minLon, maxLat, maxLon] = geohashDecodeBbox(tileHash);
      if (!boundsIntersectsViewport(minLat, minLon, maxLat, maxLon)) continue;
      const totalSamples = tile.heard + tile.lost;
      if (totalSamples === 0) continue;
      const heardRatio = totalSamples > 0 ? tile.heard / totalSamples : 0;
      const color = successRateToColor(heardRatio);
      const baseOpacity = 0.75 * Math.min(1, totalSamples / 10);
      const opacity = heardRatio > 0 ? baseOpacity * heardRatio : Math.max(baseOpacity, 0.4);
      const rect = L.rectangle([[minLat, minLon], [maxLat, maxLon]], {
        renderer: vectorRenderer,
        color: color,
        weight: 1,
        fillOpacity: Math.max(opacity, 0.2),
        fillColor: color
      });
      let details = `Heard: ${tile.heard} Lost: ${tile.lost} (${(100 * heardRatio).toFixed(0)}%)`;
      if (tile.paths.size > 0) {
        const repeaters = Array.from(tile.paths)
          .slice(0, 5)
          .map(r => escapeHtml(String(r).toUpperCase()));
        details += `<br/>Repeaters: ${repeaters.join(', ')}${tile.paths.size > 5 ? '...' : ''}`;
      }
      if (tile.snr !== null && tile.snr !== undefined) {
        details += `<br/>SNR: ${escapeHtml(tile.snr)} dB`;
      }
      if (tile.rssi !== null && tile.rssi !== undefined) {
        details += `<br/>RSSI: ${escapeHtml(tile.rssi)} dBm`;
      }
      rect.bindPopup(details, { maxWidth: 320 });
      coverageLayer.addLayer(rect);
      rendered++;
    } catch (err) {
      // Silently skip invalid tiles
    }
  }
  updateCoverageAttribution();
  updateCoverageLegend();
}

function setCoverageVisible(visible) {
  coverageVisible = visible;
  const btn = document.getElementById('coverage-toggle');
  if (btn) {
    btn.classList.toggle('active', visible);
    btn.textContent = visible ? 'Hide coverage' : 'Coverage';
  }
  if (!nodesVisible) {
    if (coverageLayer && map.hasLayer(coverageLayer)) {
      map.removeLayer(coverageLayer);
    }
    updateCoverageAttribution();
    updateCoverageLegend();
    return;
  }
  if (visible) {
    if (!map.hasLayer(coverageLayer)) {
      coverageLayer.addTo(map);
    }
    if (!coverageData) {
      fetchCoverageData().then(result => {
        if (result && Array.isArray(result.data)) {
          coverageData = result.data;
          coverageProvider = result.provider || '';
          coverageRegion = result.region || '';
          if (result.data.length === 0) {
            reportError('Coverage database appears to be empty. Add coverage data to your coverage map server.');
          }
          renderCoverage(result.data);
        } else {
          updateCoverageLegend();
          reportError('Coverage API returned invalid data format');
        }
      });
    } else {
      renderCoverage(coverageData);
    }
  } else {
    if (map.hasLayer(coverageLayer)) {
      map.removeLayer(coverageLayer);
    }
    updateCoverageAttribution();
    updateCoverageLegend();
  }
}

function getRadarCountryRequestKey(lat, lon) {
  if (!Number.isFinite(lat) || !Number.isFinite(lon)) return '';
  return `${lat.toFixed(2)},${lon.toFixed(2)}`;
}

function getRadarCountryLookupCenter() {
  const center = typeof map.getCenter === 'function' ? map.getCenter() : null;
  const lat = center && Number.isFinite(center.lat) ? center.lat : mapStartLat;
  const lon = center && Number.isFinite(center.lng) ? center.lng : mapStartLon;
  return { lat, lon };
}

function getRadarBoundsKey(bounds) {
  if (!Array.isArray(bounds) || bounds.length !== 2) return '';
  const southWest = bounds[0];
  const northEast = bounds[1];
  if (!Array.isArray(southWest) || southWest.length !== 2) return '';
  if (!Array.isArray(northEast) || northEast.length !== 2) return '';
  const south = Number(southWest[0]);
  const west = Number(southWest[1]);
  const north = Number(northEast[0]);
  const east = Number(northEast[1]);
  if (!Number.isFinite(south) || !Number.isFinite(west)) return '';
  if (!Number.isFinite(north) || !Number.isFinite(east)) return '';
  if (south >= north || west >= east) return '';
  return `${south.toFixed(4)},${west.toFixed(4)},${north.toFixed(4)},${east.toFixed(4)}`;
}

function parseRadarCountryBounds(payload) {
  if (!payload || typeof payload !== 'object') return null;
  let south = NaN;
  let north = NaN;
  let west = NaN;
  let east = NaN;
  const rawBounds = payload.bounds && typeof payload.bounds === 'object' ? payload.bounds : null;
  if (rawBounds) {
    south = Number(rawBounds.south);
    north = Number(rawBounds.north);
    west = Number(rawBounds.west);
    east = Number(rawBounds.east);
  } else {
    const bbox = Array.isArray(payload.boundingbox) ? payload.boundingbox : [];
    if (bbox.length < 4) return null;
    south = Number(bbox[0]);
    north = Number(bbox[1]);
    west = Number(bbox[2]);
    east = Number(bbox[3]);
  }
  const bounds = [[south, west], [north, east]];
  const boundsKey = getRadarBoundsKey(bounds);
  if (!boundsKey) return null;
  const address = payload.address && typeof payload.address === 'object' ? payload.address : {};
  const countryCode = typeof address.country_code === 'string'
    ? address.country_code.trim().toLowerCase()
    : '';
  return { bounds, boundsKey, countryCode };
}

function loadStoredRadarCountryBounds() {
  if (!weatherRadarEnabled || !weatherRadarCountryBoundsEnabled) return;
  let raw = '';
  try {
    raw = localStorage.getItem(WEATHER_RADAR_COUNTRY_CACHE_KEY) || '';
  } catch (err) {
    return;
  }
  if (!raw) return;
  try {
    const parsed = JSON.parse(raw);
    if (!parsed || typeof parsed !== 'object') return;
    const center = getRadarCountryLookupCenter();
    const expectedKey = getRadarCountryRequestKey(center.lat, center.lon);
    const requestKey = typeof parsed.requestKey === 'string' ? parsed.requestKey : '';
    if (expectedKey && requestKey && expectedKey !== requestKey) return;
    const bounds = Array.isArray(parsed.bounds) ? parsed.bounds : null;
    const boundsKey = getRadarBoundsKey(bounds);
    if (!boundsKey) return;
    radarCountryBounds = bounds;
    radarCountryBoundsKey = boundsKey;
  } catch (err) {
    // Ignore invalid cache payloads
  }
}

function buildRadarCountryLookupUrl(lat, lon) {
  const baseUrl = weatherRadarCountryLookupUrl || '/weather/radar/country-bounds';
  let lookup;
  try {
    lookup = new URL(baseUrl, window.location.origin);
  } catch (err) {
    return '';
  }
  lookup.searchParams.set('format', 'jsonv2');
  lookup.searchParams.set('lat', String(lat));
  lookup.searchParams.set('lon', String(lon));
  lookup.searchParams.set('zoom', '3');
  lookup.searchParams.set('addressdetails', '1');
  if (lookup.origin === window.location.origin && prodMode && apiToken) {
    lookup.searchParams.set('token', apiToken);
  }
  return lookup.toString();
}

async function ensureRadarCountryBounds(options = {}) {
  const silent = options.silent === true;
  if (!weatherRadarEnabled || !weatherRadarCountryBoundsEnabled) return null;
  if (!weatherRadarCountryLookupUrl) return null;
  if (radarCountryBoundsKey && radarCountryBounds) return radarCountryBounds;
  if (radarCountryBoundsPromise) return radarCountryBoundsPromise;

  loadStoredRadarCountryBounds();
  if (radarCountryBoundsKey && radarCountryBounds) return radarCountryBounds;

  const center = getRadarCountryLookupCenter();
  const requestKey = getRadarCountryRequestKey(center.lat, center.lon);
  if (!requestKey) return null;
  const lookupUrl = buildRadarCountryLookupUrl(center.lat, center.lon);
  if (!lookupUrl) return null;

  radarCountryBoundsPromise = (async () => {
    try {
      const response = await fetch(lookupUrl, { cache: 'force-cache' });
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }
      const payload = await response.json();
      const parsed = parseRadarCountryBounds(payload);
      if (!parsed) {
        throw new Error('Country bounds missing in lookup response');
      }
      radarCountryBounds = parsed.bounds;
      radarCountryBoundsKey = parsed.boundsKey;
      try {
        localStorage.setItem(WEATHER_RADAR_COUNTRY_CACHE_KEY, JSON.stringify({
          requestKey,
          countryCode: parsed.countryCode,
          bounds: parsed.bounds
        }));
      } catch (err) {
        // Ignore cache write issues
      }
      return radarCountryBounds;
    } catch (err) {
      if (!silent) {
        const errorMsg = err && err.message ? err.message : String(err);
        reportError(`Radar country lookup failed: ${errorMsg}`);
      }
      return null;
    } finally {
      radarCountryBoundsPromise = null;
    }
  })();

  return radarCountryBoundsPromise;
}

async function fetchLatestRadarFrame() {
  let lastError = null;
  for (const metaUrl of RADAR_META_URLS) {
    try {
      const response = await fetch(metaUrl, { cache: 'no-store' });
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }
      const data = await response.json();
      const host = typeof data.host === 'string' && data.host.trim()
        ? data.host.replace(/\/+$/, '')
        : 'https://tilecache.rainviewer.com';
      const radar = data && typeof data === 'object' ? data.radar : null;
      const pastFrames = radar && Array.isArray(radar.past) ? radar.past : [];
      const nowcastFrames = radar && Array.isArray(radar.nowcast) ? radar.nowcast : [];
      const frames = nowcastFrames.length > 0 ? nowcastFrames : pastFrames;
      if (!frames.length) {
        throw new Error('No radar frames available');
      }
      const latest = frames[frames.length - 1] || {};
      const path = typeof latest.path === 'string' ? latest.path : '';
      if (!path) {
        throw new Error('Radar frame path missing');
      }
      return { host, path };
    } catch (err) {
      const message = err && err.message ? err.message : String(err);
      lastError = `${metaUrl}: ${message}`;
    }
  }
  throw new Error(lastError || 'Radar metadata unavailable');
}

function updateRadarLayer(host, path) {
  if (!path) return;
  const normalizedHost = host ? host.replace(/\/+$/, '') : 'https://tilecache.rainviewer.com';
  const normalizedPath = path.startsWith('/') ? path : `/${path}`;
  const activeBounds = weatherRadarCountryBoundsEnabled && radarCountryBoundsKey ? radarCountryBounds : null;
  const activeBoundsKey = weatherRadarCountryBoundsEnabled ? radarCountryBoundsKey : '';
  if (
    radarLayer &&
    radarFrameHost === normalizedHost &&
    radarFramePath === normalizedPath &&
    radarLayerBoundsKey === activeBoundsKey
  ) {
    return;
  }
  radarFrameHost = normalizedHost;
  radarFramePath = normalizedPath;
  if (radarLayer) {
    radarLayerGroup.removeLayer(radarLayer);
    radarLayer = null;
  }
  const tileUrl = `${normalizedHost}${normalizedPath}/256/{z}/{x}/{y}/4/1_1.png`;
  const layerOptions = {
    pane: 'radarPane',
    opacity: 0.58,
    maxNativeZoom: RADAR_MAX_NATIVE_ZOOM,
    maxZoom: 18,
    attribution: '&copy; RainViewer'
  };
  if (activeBounds) {
    layerOptions.bounds = L.latLngBounds(activeBounds);
  }
  radarLayer = L.tileLayer(tileUrl, layerOptions);
  radarLayerBoundsKey = activeBoundsKey;
  radarLayerGroup.addLayer(radarLayer);
  localStorage.setItem('meshmapRadarHost', radarFrameHost);
  localStorage.setItem('meshmapRadarPath', radarFramePath);
  if (!radarVisible) {
    startRadarPreload();
  }
}

function getWeatherWindSamplePoints() {
  const center = map.getCenter();
  const fallback = [{ lat: center.lat, lon: center.lng }];
  const bounds = map.getBounds();
  if (!bounds || !bounds.isValid() || weatherWindGridSize <= 1) return fallback;
  const south = bounds.getSouth();
  const north = bounds.getNorth();
  const west = bounds.getWest();
  const east = bounds.getEast();
  if (
    !Number.isFinite(south) || !Number.isFinite(north) ||
    !Number.isFinite(west) || !Number.isFinite(east) ||
    south >= north || west >= east
  ) {
    return fallback;
  }
  const points = [];
  for (let row = 0; row < weatherWindGridSize; row += 1) {
    const yRatio = weatherWindGridSize === 1 ? 0.5 : (row + 0.5) / weatherWindGridSize;
    const lat = south + (north - south) * yRatio;
    for (let col = 0; col < weatherWindGridSize; col += 1) {
      const xRatio = weatherWindGridSize === 1 ? 0.5 : (col + 0.5) / weatherWindGridSize;
      const lon = west + (east - west) * xRatio;
      points.push({ lat, lon });
    }
  }
  return points.length ? points : fallback;
}

function weatherWindUnitLabel() {
  return distanceUnits === 'mi' ? 'mph' : 'km/h';
}

function weatherWindIcon(speed, direction) {
  const speedLabel = Number.isFinite(speed) ? Math.max(0, Math.round(speed)) : 0;
  const safeDirection = Number.isFinite(direction)
    ? ((direction % 360) + 360) % 360
    : 0;
  return L.divIcon({
    className: 'weather-wind-icon',
    iconSize: [52, 24],
    iconAnchor: [26, 12],
    html:
      `<span class="weather-wind-arrow" style="transform: rotate(${safeDirection}deg)">➤</span>` +
      `<span class="weather-wind-speed">${speedLabel}${weatherWindUnitLabel()}</span>`
  });
}

async function fetchWeatherWindSamples(points) {
  if (!Array.isArray(points) || !points.length) return [];
  if (!weatherWindApiUrl) {
    throw new Error('Wind API URL not configured');
  }
  let url;
  try {
    url = new URL(weatherWindApiUrl, window.location.origin);
  } catch (err) {
    throw new Error('Wind API URL is invalid');
  }
  const latCsv = points.map((point) => point.lat.toFixed(5)).join(',');
  const lonCsv = points.map((point) => point.lon.toFixed(5)).join(',');
  url.searchParams.set('latitude', latCsv);
  url.searchParams.set('longitude', lonCsv);
  url.searchParams.set('current', 'wind_speed_10m,wind_direction_10m');
  url.searchParams.set('wind_speed_unit', distanceUnits === 'mi' ? 'mph' : 'kmh');
  if (url.origin === window.location.origin && prodMode && apiToken) {
    url.searchParams.set('token', apiToken);
  }
  const response = await fetch(url.toString(), { cache: 'no-store' });
  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`);
  }
  const payload = await response.json();
  const batch = Array.isArray(payload) ? payload : [payload];
  const samples = [];
  for (let i = 0; i < points.length; i += 1) {
    const source = batch[i] || batch[0] || {};
    const current = source && typeof source === 'object' ? source.current : null;
    const speed = Number(current && current.wind_speed_10m);
    const direction = Number(current && current.wind_direction_10m);
    if (!Number.isFinite(speed) || !Number.isFinite(direction)) {
      continue;
    }
    samples.push({
      lat: points[i].lat,
      lon: points[i].lon,
      speed,
      direction
    });
  }
  if (!samples.length) {
    throw new Error('Wind response missing fields');
  }
  return samples;
}

async function refreshWeatherWindLayer(options = {}) {
  const silent = options.silent === true;
  const background = options.background === true;
  if (!weatherWindEnabled || !weatherWindLayerEnabled || !weatherWindApiUrl) return;
  const manageUi = !(background && (!radarVisible || !weatherWindLayerEnabled));
  const seq = ++weatherWindRequestSeq;
  if (manageUi) {
    weatherWindLoading = true;
    updateRadarButtonState();
  }
  try {
    const points = getWeatherWindSamplePoints();
    const samples = await fetchWeatherWindSamples(points);
    if (seq !== weatherWindRequestSeq) return;
    weatherWindLayer.clearLayers();
    for (const sample of samples) {
      const marker = L.marker([sample.lat, sample.lon], {
        icon: weatherWindIcon(sample.speed, sample.direction),
        pane: 'weatherWindPane',
        interactive: false,
        keyboard: false
      });
      weatherWindLayer.addLayer(marker);
    }
    if (radarVisible && weatherWindLayerEnabled && nodesVisible && !map.hasLayer(weatherWindLayer)) {
      weatherWindLayer.addTo(map);
    }
  } catch (err) {
    if (!silent) {
      const errorMsg = err && err.message ? err.message : String(err);
      reportError(`Failed to fetch weather wind: ${errorMsg}`);
    }
  } finally {
    if (manageUi && seq === weatherWindRequestSeq) {
      weatherWindLoading = false;
      updateRadarButtonState();
    }
  }
}

function stopWeatherWindRefresh() {
  if (weatherWindRefreshTimer) {
    window.clearInterval(weatherWindRefreshTimer);
    weatherWindRefreshTimer = null;
  }
  if (weatherWindMoveTimer) {
    window.clearTimeout(weatherWindMoveTimer);
    weatherWindMoveTimer = null;
  }
}

function startWeatherWindRefresh() {
  if (!weatherWindEnabled || !weatherWindLayerEnabled) return;
  stopWeatherWindRefresh();
  weatherWindRefreshTimer = window.setInterval(() => {
    if (!radarVisible || !weatherWindLayerEnabled) return;
    refreshWeatherWindLayer({ silent: true, background: true });
  }, weatherWindRefreshMs);
}

function scheduleWeatherWindRefresh() {
  if (!weatherWindEnabled || !weatherWindLayerEnabled || !radarVisible) return;
  if (weatherWindMoveTimer) {
    window.clearTimeout(weatherWindMoveTimer);
  }
  weatherWindMoveTimer = window.setTimeout(() => {
    refreshWeatherWindLayer({ silent: true, background: true });
  }, 450);
}

function updateWeatherLayerButtons() {
  if (weatherRadarLayerToggle) {
    const available = weatherRadarEnabled;
    weatherRadarLayerToggle.disabled = !available;
    weatherRadarLayerToggle.classList.toggle('active', available && weatherRadarLayerEnabled);
    if (!available) {
      weatherRadarLayerToggle.textContent = 'Radar: unavailable';
    } else {
      weatherRadarLayerToggle.textContent = weatherRadarLayerEnabled ? 'Radar: on' : 'Radar: off';
    }
  }
  if (weatherWindLayerToggle) {
    const available = weatherWindEnabled;
    weatherWindLayerToggle.disabled = !available;
    weatherWindLayerToggle.classList.toggle('active', available && weatherWindLayerEnabled);
    if (!available) {
      weatherWindLayerToggle.textContent = 'Wind: unavailable';
    } else {
      weatherWindLayerToggle.textContent = weatherWindLayerEnabled ? 'Wind: on' : 'Wind: off';
    }
  }
}

function updateWeatherPanelVisibility() {
  if (!weatherPanel) return;
  const shouldShow = radarVisible && !weatherPanelHidden;
  weatherPanel.classList.toggle('active', shouldShow);
  if (shouldShow) {
    weatherPanel.removeAttribute('hidden');
    weatherPanel.style.display = 'block';
  } else {
    weatherPanel.setAttribute('hidden', 'hidden');
    weatherPanel.style.display = 'none';
  }
}

function setWeatherPanelHidden(hidden) {
  weatherPanelHidden = Boolean(hidden);
  updateWeatherPanelVisibility();
  layoutSidePanels();
}

function updateRadarButtonState() {
  const btn = document.getElementById('weather-toggle');
  if (!btn) return;
  if (!weatherAvailable) {
    btn.setAttribute('hidden', 'hidden');
    return;
  }
  btn.classList.toggle('active', radarVisible);
  if (radarVisible && (radarLoading || weatherWindLoading)) {
    btn.textContent = 'Weather: loading...';
  } else {
    btn.textContent = 'Weather';
  }
}

function stopRadarPreload(keepLayer = false) {
  radarPreloading = false;
  if (radarPreloadTimeout) {
    window.clearTimeout(radarPreloadTimeout);
    radarPreloadTimeout = null;
  }
  if (radarLayer) {
    radarLayer.setOpacity(0.58);
  }
  if (!keepLayer && (!radarVisible || !weatherRadarLayerEnabled) && map.hasLayer(radarLayerGroup)) {
    map.removeLayer(radarLayerGroup);
  }
}

function startRadarPreload() {
  if (!radarLayer || radarVisible || radarPreloading) return;
  radarPreloading = true;
  radarLayer.setOpacity(0.01);
  if (!map.hasLayer(radarLayerGroup)) {
    radarLayerGroup.addTo(map);
  }
  const finish = () => stopRadarPreload(false);
  radarLayer.once('load', finish);
  radarPreloadTimeout = window.setTimeout(finish, 3000);
}

async function refreshRadarLayer(options = {}) {
  const silent = options.silent === true;
  const background = options.background === true;
  const manageUi = !(background && (!radarVisible || !weatherRadarLayerEnabled));
  const seq = ++radarRequestSeq;
  if (manageUi) {
    radarLoading = true;
    updateRadarButtonState();
  }
  try {
    const boundsPromise = weatherRadarCountryBoundsEnabled
      ? ensureRadarCountryBounds({ silent: true })
      : null;
    const frame = await fetchLatestRadarFrame();
    if (boundsPromise) {
      await boundsPromise;
    }
    if (seq !== radarRequestSeq) return;
    updateRadarLayer(frame.host, frame.path);
    if (radarVisible && weatherRadarLayerEnabled && nodesVisible && !map.hasLayer(radarLayerGroup)) {
      radarLayerGroup.addTo(map);
    }
  } catch (err) {
    if (!silent) {
      const errorMsg = err && err.message ? err.message : String(err);
      reportError(`Failed to fetch weather radar: ${errorMsg}`);
    }
  } finally {
    if (manageUi && seq === radarRequestSeq) {
      radarLoading = false;
      updateRadarButtonState();
    }
  }
}

function stopRadarRefresh() {
  if (radarRefreshTimer) {
    window.clearInterval(radarRefreshTimer);
    radarRefreshTimer = null;
  }
}

function startRadarRefresh() {
  stopRadarRefresh();
  radarRefreshTimer = window.setInterval(() => {
    if (!radarVisible || !weatherRadarLayerEnabled) return;
    refreshRadarLayer();
  }, RADAR_REFRESH_MS);
}

function setWeatherRadarLayerEnabled(enabled) {
  if (!weatherRadarEnabled) {
    weatherRadarLayerEnabled = false;
    updateWeatherLayerButtons();
    return;
  }
  weatherRadarLayerEnabled = Boolean(enabled);
  try {
    localStorage.setItem(
      WEATHER_RADAR_LAYER_STORAGE_KEY,
      weatherRadarLayerEnabled ? 'true' : 'false'
    );
  } catch (_err) {}
  updateWeatherLayerButtons();
  if (!radarVisible || !nodesVisible || !weatherRadarLayerEnabled) {
    if (map.hasLayer(radarLayerGroup)) {
      map.removeLayer(radarLayerGroup);
    }
    stopRadarPreload(false);
    stopRadarRefresh();
    return;
  }
  stopRadarPreload(true);
  if (!map.hasLayer(radarLayerGroup)) {
    radarLayerGroup.addTo(map);
  }
  if (radarLayer) {
    radarLayer.setOpacity(0.58);
  }
  if (!radarLayer) {
    refreshRadarLayer({ silent: true });
  }
  startRadarRefresh();
}

function setWeatherWindLayerEnabled(enabled) {
  if (!weatherWindEnabled) {
    weatherWindLayerEnabled = false;
    updateWeatherLayerButtons();
    return;
  }
  weatherWindLayerEnabled = Boolean(enabled);
  try {
    localStorage.setItem(
      WEATHER_WIND_LAYER_STORAGE_KEY,
      weatherWindLayerEnabled ? 'true' : 'false'
    );
  } catch (_err) {}
  updateWeatherLayerButtons();
  if (!radarVisible || !nodesVisible || !weatherWindLayerEnabled) {
    if (map.hasLayer(weatherWindLayer)) {
      map.removeLayer(weatherWindLayer);
    }
    stopWeatherWindRefresh();
    return;
  }
  if (!map.hasLayer(weatherWindLayer)) {
    weatherWindLayer.addTo(map);
  }
  refreshWeatherWindLayer({ silent: true, background: true });
  startWeatherWindRefresh();
}

function setRadarVisible(visible) {
  radarVisible = visible;
  if (visible) {
    weatherPanelHidden = false;
  }
  updateWeatherPanelVisibility();
  updateRadarButtonState();
  updateWeatherLayerButtons();
  if (!nodesVisible) {
    if (map.hasLayer(radarLayerGroup)) {
      map.removeLayer(radarLayerGroup);
    }
    if (map.hasLayer(weatherWindLayer)) {
      map.removeLayer(weatherWindLayer);
    }
    stopRadarPreload(false);
    stopRadarRefresh();
    stopWeatherWindRefresh();
    layoutSidePanels();
    return;
  }
  if (visible) {
    if (weatherRadarLayerEnabled) {
      stopRadarPreload(true);
      if (!map.hasLayer(radarLayerGroup)) {
        radarLayerGroup.addTo(map);
      }
      if (radarLayer) {
        radarLayer.setOpacity(0.58);
      }
      if (!radarLayer) {
        refreshRadarLayer();
      }
      startRadarRefresh();
    } else {
      if (map.hasLayer(radarLayerGroup)) {
        map.removeLayer(radarLayerGroup);
      }
      stopRadarPreload(false);
      stopRadarRefresh();
    }
    if (weatherWindEnabled && weatherWindLayerEnabled) {
      if (!map.hasLayer(weatherWindLayer)) {
        weatherWindLayer.addTo(map);
      }
      refreshWeatherWindLayer({ silent: true, background: true });
      startWeatherWindRefresh();
    } else {
      if (map.hasLayer(weatherWindLayer)) {
        map.removeLayer(weatherWindLayer);
      }
      stopWeatherWindRefresh();
    }
  } else {
    if (map.hasLayer(radarLayerGroup)) {
      map.removeLayer(radarLayerGroup);
    }
    if (map.hasLayer(weatherWindLayer)) {
      map.removeLayer(weatherWindLayer);
    }
    stopRadarPreload(false);
    stopRadarRefresh();
    stopWeatherWindRefresh();
  }
  layoutSidePanels();
}

function updateNodeSizeUi() {
  if (nodeSizeInput) {
    nodeSizeInput.value = String(nodeMarkerRadius);
  }
  if (nodeSizeValue) {
    nodeSizeValue.textContent = `${nodeMarkerRadius}px`;
  }
}

function setNodeMarkerRadius(value, persist = true) {
  const next = clampNumber(Number(value), NODE_RADIUS_MIN, NODE_RADIUS_MAX);
  if (!Number.isFinite(next)) return;
  nodeMarkerRadius = next;
  if (persist) {
    localStorage.setItem('meshmapNodeRadius', String(nodeMarkerRadius));
  }
  updateNodeSizeUi();
  refreshOnlineMarkers();
}

function setNodesVisible(visible) {
  nodesVisible = visible;
  const btn = document.getElementById('nodes-toggle');
  if (btn) {
    btn.classList.toggle('active', !visible);
    btn.textContent = visible ? 'Hide nodes' : 'Show nodes';
  }
  if (visible) {
    if (!map.hasLayer(markerLayer)) {
      markerLayer.addTo(map);
    }
    if (!map.hasLayer(trailLayer)) {
      trailLayer.addTo(map);
    }
    if (!map.hasLayer(routeLayer)) {
      routeLayer.addTo(map);
    }
    if (arcadeModeEnabled && !map.hasLayer(arcadeLayer)) {
      arcadeLayer.addTo(map);
    }
    if (historyVisible && !map.hasLayer(historyLayer)) {
      historyLayer.addTo(map);
      renderHistoryFromCache();
    }
    if (heatVisible && heatLayer && !map.hasLayer(heatLayer)) {
      heatLayer.addTo(map);
    }
    if (coverageVisible && !map.hasLayer(coverageLayer)) {
      coverageLayer.addTo(map);
    }
    if (radarVisible && weatherRadarLayerEnabled && !map.hasLayer(radarLayerGroup)) {
      radarLayerGroup.addTo(map);
    }
    if (radarVisible && weatherWindEnabled && weatherWindLayerEnabled && !map.hasLayer(weatherWindLayer)) {
      weatherWindLayer.addTo(map);
    }
    if (radarVisible && weatherWindEnabled && weatherWindLayerEnabled) {
      startWeatherWindRefresh();
    }
    if (radarVisible && weatherRadarLayerEnabled) {
      startRadarRefresh();
    }
    if (peersActive && !map.hasLayer(peerLayer)) {
      peerLayer.addTo(map);
    }
    if (peersActive && peersData) {
      renderCurrentPeers();
    }
    refreshViewportLayers();
    if (arcadeModeEnabled) {
      routeLines.forEach((entry, routeId) => {
        if (entry && Array.isArray(entry.routePoints)) {
          syncArcadeForRoute(routeId, entry.routePoints);
        }
      });
      syncAllRouteDisplays();
      startArcadeLoop();
    }
  } else if (map.hasLayer(markerLayer)) {
    map.removeLayer(markerLayer);
    if (map.hasLayer(trailLayer)) {
      map.removeLayer(trailLayer);
    }
    if (map.hasLayer(routeLayer)) {
      map.removeLayer(routeLayer);
    }
    if (map.hasLayer(arcadeLayer)) {
      map.removeLayer(arcadeLayer);
    }
    if (map.hasLayer(historyLayer)) {
      map.removeLayer(historyLayer);
      clearHistoryLayer();
    }
    if (heatLayer && map.hasLayer(heatLayer)) {
      map.removeLayer(heatLayer);
    }
    if (coverageLayer && map.hasLayer(coverageLayer)) {
      map.removeLayer(coverageLayer);
    }
    if (map.hasLayer(radarLayerGroup)) {
      map.removeLayer(radarLayerGroup);
    }
    if (map.hasLayer(weatherWindLayer)) {
      map.removeLayer(weatherWindLayer);
    }
    stopRadarPreload(false);
    stopRadarRefresh();
    stopWeatherWindRefresh();
    if (map.hasLayer(peerLayer)) {
      map.removeLayer(peerLayer);
    }
    stopArcadeLoop();
  } else if (map.hasLayer(trailLayer)) {
    map.removeLayer(trailLayer);
  } else {
    if (map.hasLayer(routeLayer)) {
      map.removeLayer(routeLayer);
    }
    if (map.hasLayer(arcadeLayer)) {
      map.removeLayer(arcadeLayer);
    }
    if (map.hasLayer(historyLayer)) {
      map.removeLayer(historyLayer);
      clearHistoryLayer();
    }
    if (heatLayer && map.hasLayer(heatLayer)) {
      map.removeLayer(heatLayer);
    }
    if (map.hasLayer(radarLayerGroup)) {
      map.removeLayer(radarLayerGroup);
    }
    if (map.hasLayer(weatherWindLayer)) {
      map.removeLayer(weatherWindLayer);
    }
    stopWeatherWindRefresh();
    if (map.hasLayer(peerLayer)) {
      map.removeLayer(peerLayer);
    }
    stopArcadeLoop();
  }
}

function updateHistoryPanelVisibility() {
  if (!historyPanel) return;
  if (!routeHistoryEnabled) {
    historyPanel.classList.remove('active');
    historyPanel.setAttribute('hidden', 'hidden');
    historyPanel.style.display = 'none';
    return;
  }
  const shouldShow = historyVisible && !historyPanelHidden;
  historyPanel.classList.toggle('active', shouldShow);
  if (shouldShow) {
    historyPanel.removeAttribute('hidden');
    historyPanel.style.display = 'block';
  } else {
    historyPanel.setAttribute('hidden', 'hidden');
    historyPanel.style.display = 'none';
  }
}

function setHistoryPanelHidden(hidden) {
  historyPanelHidden = Boolean(hidden);
  if (historyPanelHidden) {
    setHistoryPanelCollapsed(true);
  }
  updateHistoryPanelVisibility();
  layoutSidePanels();
}

function setHistoryVisible(visible) {
  if (!routeHistoryEnabled) {
    historyVisible = false;
    historyPanelHidden = true;
    if (historyLegendGroup) {
      historyLegendGroup.classList.remove('active');
      historyLegendGroup.setAttribute('hidden', 'hidden');
      historyLegendGroup.style.display = 'none';
    }
    const btnDisabled = document.getElementById('history-toggle');
    if (btnDisabled) {
      btnDisabled.classList.remove('active');
    }
    if (map.hasLayer(historyLayer)) {
      map.removeLayer(historyLayer);
    }
    clearHistoryLayer();
    historyCache.clear();
    updateHistoryPanelVisibility();
    layoutSidePanels();
    return;
  }
  historyVisible = visible;
  if (visible) {
    historyPanelHidden = false;
    setHistoryPanelCollapsed(false);
  }
  const btn = document.getElementById('history-toggle');
  if (btn) {
    btn.classList.toggle('active', visible);
    btn.textContent = visible ? 'History: on' : 'History tool';
  }
  updateHistoryPanelVisibility();
  if (historyLegendGroup) {
    historyLegendGroup.classList.toggle('active', visible);
  }
  if (visible) {
    if (!map.hasLayer(historyLayer)) {
      historyLayer.addTo(map);
    }
    renderHistoryFromCache();
    updateHistoryRendering();
  } else if (map.hasLayer(historyLayer)) {
    map.removeLayer(historyLayer);
    clearHistoryLayer();
  }
  layoutSidePanels();
}

function setHopsVisible(visible) {
  hopsVisible = visible;
  const btn = document.getElementById('hops-toggle');
  if (btn) {
    btn.classList.toggle('active', visible);
    btn.textContent = visible ? 'Hide hops' : 'Show hops';
  }
  if (visible) {
    if (!map.hasLayer(hopLayer)) {
      hopLayer.addTo(map);
    }
    // Render for all existing routes
    for (const [id, entry] of routeLines.entries()) {
      renderHopMarkers(id, entry.meta);
    }
  } else {
    if (map.hasLayer(hopLayer)) {
      map.removeLayer(hopLayer);
    }
    clearAllHopMarkers();
    hideRouteDetailsPanel();
    layoutSidePanels();
  }
}

function makeArcadeIcon() {
  return L.divIcon({
    className: 'flow-marker',
    html: '<div class="flow-icon"></div>',
    iconSize: [22, 22],
    iconAnchor: [11, 11],
  });
}

function buildArcadePath(points) {
  if (!Array.isArray(points) || points.length < 2) return null;
  const latLngs = points.map((point) => L.latLng(point[0], point[1]));
  const segments = [];
  let total = 0;
  for (let idx = 0; idx < latLngs.length - 1; idx += 1) {
    const start = latLngs[idx];
    const end = latLngs[idx + 1];
    const length = start.distanceTo(end);
    if (!(length > 0)) continue;
    segments.push({
      start,
      end,
      startDistance: total,
      length,
    });
    total += length;
  }
  if (!(total > 0) || !segments.length) return null;
  return { latLngs, segments, total };
}

function interpolateArcadePosition(path, distance) {
  if (!path || !Array.isArray(path.segments) || !path.segments.length) return null;
  const clamped = Math.max(0, Math.min(distance, path.total));
  for (let idx = 0; idx < path.segments.length; idx += 1) {
    const segment = path.segments[idx];
    const segmentEnd = segment.startDistance + segment.length;
    if (clamped <= segmentEnd || idx === path.segments.length - 1) {
      const ratio = segment.length > 0
        ? (clamped - segment.startDistance) / segment.length
        : 0;
      const lat = segment.start.lat + ((segment.end.lat - segment.start.lat) * ratio);
      const lng = segment.start.lng + ((segment.end.lng - segment.start.lng) * ratio);
      const startPoint = map.latLngToLayerPoint(segment.start);
      const endPoint = map.latLngToLayerPoint(segment.end);
      const angle = Math.atan2(
        endPoint.y - startPoint.y,
        endPoint.x - startPoint.x
      ) * (180 / Math.PI);
      return { latlng: L.latLng(lat, lng), angle };
    }
  }
  return null;
}

function stopArcadeLoop() {
  if (arcadeAnimFrame != null) {
    window.cancelAnimationFrame(arcadeAnimFrame);
    arcadeAnimFrame = null;
  }
}

function updateArcadeMarker(entry, nowMs) {
  if (!entry || !entry.arcadeMarker || !entry.arcadeMarker.marker || !entry.arcadeMarker.path) return;
  const elapsed = Math.max(0, nowMs - entry.arcadeMarker.startedAt);
  const cycle = entry.arcadeMarker.durationMs > 0
    ? (elapsed % entry.arcadeMarker.durationMs)
    : 0;
  const distance = entry.arcadeMarker.path.total * (cycle / entry.arcadeMarker.durationMs);
  const resolved = interpolateArcadePosition(entry.arcadeMarker.path, distance);
  if (!resolved) return;
  entry.arcadeMarker.marker.setLatLng(resolved.latlng);
  const el = entry.arcadeMarker.marker.getElement();
  const icon = el ? el.querySelector('.flow-icon') : null;
  if (icon) {
    icon.style.transform = `rotate(${resolved.angle}deg)`;
  }
}

function animateArcadeMarkers(nowMs) {
  if (!arcadeModeEnabled || !nodesVisible || !map.hasLayer(arcadeLayer)) {
    stopArcadeLoop();
    return;
  }
  let activeCount = 0;
  routeLines.forEach((entry) => {
    if (!entry || !entry.arcadeMarker || !entry.arcadeMarker.marker || !entry.arcadeMarker.path) return;
    activeCount += 1;
    updateArcadeMarker(entry, nowMs);
  });
  if (!activeCount) {
    stopArcadeLoop();
    return;
  }
  arcadeAnimFrame = window.requestAnimationFrame(animateArcadeMarkers);
}

function startArcadeLoop() {
  if (arcadeAnimFrame != null || !arcadeModeEnabled || !nodesVisible || !map.hasLayer(arcadeLayer)) {
    return;
  }
  arcadeAnimFrame = window.requestAnimationFrame(animateArcadeMarkers);
}

function removeArcadeMarker(routeId) {
  const entry = routeLines.get(routeId);
  if (!entry || !entry.arcadeMarker || !entry.arcadeMarker.marker) return;
  arcadeLayer.removeLayer(entry.arcadeMarker.marker);
  entry.arcadeMarker = null;
}

function syncArcadeForRoute(id, points) {
  const entry = routeLines.get(id);
  if (!entry) return;
  if (!arcadeModeEnabled || !nodesVisible || !Array.isArray(points) || points.length < 2) {
    removeArcadeMarker(id);
    return;
  }
  const path = buildArcadePath(points);
  if (!path) {
    removeArcadeMarker(id);
    return;
  }
  if (!entry.arcadeMarker || !entry.arcadeMarker.marker) {
    entry.arcadeMarker = {
      marker: L.marker(path.latLngs[0], {
        icon: makeArcadeIcon(),
        pane: 'arcadePane',
        interactive: false,
        keyboard: false,
      }).addTo(arcadeLayer),
      startedAt: performance.now(),
      durationMs: FLOW_MIN_DURATION_MS,
      path,
    };
  }
  entry.arcadeMarker.path = path;
  entry.arcadeMarker.durationMs = clampNumber(path.total * 6, FLOW_MIN_DURATION_MS, FLOW_MAX_DURATION_MS);
  if (!Number.isFinite(entry.arcadeMarker.startedAt)) {
    entry.arcadeMarker.startedAt = performance.now();
  }
  updateArcadeMarker(entry, performance.now());
  startArcadeLoop();
}

function toggleArcadeMode() {
  setArcadeModeEnabled(!arcadeModeEnabled);
  console.info(`[meshmap] arcade mode ${arcadeModeEnabled ? 'on' : 'off'}`);
}

const ARCADE_SEQUENCE = [
  'ArrowUp', 'ArrowUp', 'ArrowDown', 'ArrowDown',
  'ArrowLeft', 'ArrowRight', 'ArrowLeft', 'ArrowRight',
  'b', 'a'
];
let arcadeSequenceIndex = 0;

function handleArcadeSequenceKey(ev) {
  const target = ev.target;
  if (
    target &&
    (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.isContentEditable)
  ) {
    return;
  }
  const key = String(ev.key || '');
  const expected = ARCADE_SEQUENCE[arcadeSequenceIndex];
  if (key === expected) {
    arcadeSequenceIndex += 1;
    if (arcadeSequenceIndex >= ARCADE_SEQUENCE.length) {
      arcadeSequenceIndex = 0;
      toggleArcadeMode();
    }
    return;
  }
  arcadeSequenceIndex = key === ARCADE_SEQUENCE[0] ? 1 : 0;
}

document.addEventListener('keydown', handleArcadeSequenceKey);

function stringHashColor(str) {
  let hash = 0;
  for (let i = 0; i < str.length; i++) {
    hash = str.charCodeAt(i) + ((hash << 5) - hash);
  }
  const c = (hash & 0x00FFFFFF).toString(16).toUpperCase();
  return '#' + '00000'.substring(0, 6 - c.length) + c;
}

function clearHopMarkersForRoute(routeId) {
  if (!hopMarkers.has(routeId)) return;
  hopMarkers.get(routeId).forEach(m => hopLayer.removeLayer(m));
  hopMarkers.delete(routeId);
}

function clearAllHopMarkers() {
  hopMarkers.forEach((_markers, routeId) => {
    clearHopMarkersForRoute(routeId);
  });
}

function hideRouteDetailsPanel() {
  if (routeDetailsPanel) {
    routeDetailsPanel.hidden = true;
    routeDetailsPanel.classList.remove('active');
    routeDetailsPanel.style.display = 'none';
  }
  activeRouteDetailsMeta = null;
  activeRouteDetailsId = null;
}

function routeHashByteWidth(hash) {
  const normalized = normalizeHopHashPrefix(hash);
  if (!normalized) return null;
  return normalized.length / 2;
}

function routeMatchesByteFilter(meta) {
  if (!meta || routeByteFilter.has('all')) return true;
  const hashes = Array.isArray(meta.hashes) ? meta.hashes : [];
  if (!hashes.length) return false;
  return hashes.some((hash) => routeByteFilter.has(`${routeHashByteWidth(hash)}b`));
}

function routeMatchesNodeFilter(meta) {
  const terms = routeNodeFilterText.toLowerCase().split(',')
    .map(term => term.trim()).filter(Boolean);
  if (!terms.length) return true;
  if (!meta) return false;
  const routeDeviceIds = new Set([
    meta.origin_id,
    meta.receiver_id,
    ...(Array.isArray(meta.points)
      ? meta.points.map(point => point && point.point_id)
      : [])
  ].filter(Boolean));
  const currentDeviceValues = [];
  routeDeviceIds.forEach((id) => {
    const device = deviceData.get(id);
    if (!device) return;
    currentDeviceValues.push(device.name, deviceDisplayName(device));
  });
  const pointValues = Array.isArray(meta.points)
    ? meta.points.flatMap(point => [
      point.point_id,
      point.point_label,
      point.node_prefix,
      point.hop_hash
    ])
    : [];
  const values = [
    meta.origin_id,
    meta.origin_label,
    meta.receiver_id,
    meta.receiver_label,
    meta.sender_name,
    ...currentDeviceValues,
    ...(Array.isArray(meta.hashes) ? meta.hashes : []),
    ...pointValues
  ].filter(Boolean).map(value => String(value).toLowerCase());
  return terms.some(term => values.some(value => value.includes(term)));
}

function routePointRole(point) {
  const device = point && point.point_id ? deviceData.get(point.point_id) : null;
  if (device) return resolveRole(device);
  const label = String(point && point.role_label || '').toLowerCase();
  if (label.includes('repeater')) return 'repeater';
  if (label.includes('companion')) return 'companion';
  if (label.includes('room')) return 'room';
  return 'unknown';
}

function visibleRouteSegments(meta) {
  if (!meta || !Array.isArray(meta.points)) return [];
  const segments = [];
  let current = [];
  const finishSegment = () => {
    if (current.length >= 2) segments.push(current);
    current = [];
  };
  meta.points.forEach((point) => {
    if (point && point.endpoint_only) return;
    if (!Number.isFinite(point && point.lat) || !Number.isFinite(point && point.lon)) {
      finishSegment();
      return;
    }
    if (visibleRoles.has(routePointRole(point))) {
      current.push(point);
    } else {
      finishSegment();
    }
  });
  finishSegment();
  return segments;
}

function routeMatchesRoleFilter(meta) {
  return visibleRouteSegments(meta).length > 0;
}

function routeVisibleForCurrentFilters(meta) {
  return nodesVisible && !mqttOnlyVisible &&
    routeMatchesByteFilter(meta) && routeMatchesNodeFilter(meta) &&
    routeMatchesRoleFilter(meta);
}

function getVisibleRouteCount() {
  let count = 0;
  routeLines.forEach((entry) => {
    if (routeVisibleForCurrentFilters(entry && entry.meta)) {
      count += 1;
    }
  });
  return count;
}

function syncRouteEntryDisplay(routeId, entry) {
  if (!entry || !entry.line) return;
  const roleSegments = visibleRouteSegments(entry.meta);
  const visible = routeVisibleForCurrentFilters(entry.meta);
  const style = routeStyleForDisplay(
    entry.payloadType,
    entry.routeMode,
    arcadeModeEnabled
  );
  if (visible) {
    const latLngSegments = roleSegments.map(segment =>
      segment.map(point => [point.lat, point.lon])
    );
    entry.line.setLatLngs(
      latLngSegments.length === 1 ? latLngSegments[0] : latLngSegments
    );
  }
  entry.line.setStyle({
    ...style,
    opacity: visible ? style.opacity : 0,
    fillOpacity: visible ? style.fillOpacity : 0
  });
  if (visible) {
    if (entry.line.bringToFront) {
      entry.line.bringToFront();
    }
    if (arcadeModeEnabled && roleSegments.length) {
      const arcadeSegment = roleSegments.reduce((longest, segment) =>
        segment.length > longest.length ? segment : longest
      );
      syncArcadeForRoute(
        routeId,
        arcadeSegment.map(point => [point.lat, point.lon])
      );
    }
  } else {
    removeArcadeMarker(routeId);
  }
  if (hopsVisible) {
    renderHopMarkers(routeId, entry.meta);
  } else {
    clearHopMarkersForRoute(routeId);
  }
  if (!visible && activeRouteDetailsId === routeId) {
    hideRouteDetailsPanel();
    layoutSidePanels();
  }
}

function syncAllRouteDisplays() {
  const cachedRoutes = Array.from(routeCache.values());
  clearRouteDisplay();
  cachedRoutes.forEach((route) => {
    upsertRoute(route, true);
  });
  refreshStats();
}

function syncRouteFilterDisplays() {
  routeLines.forEach((entry, routeId) => {
    syncRouteEntryDisplay(routeId, entry);
  });
  refreshStats();
}

function renderHopMarkers(routeId, meta) {
  clearHopMarkersForRoute(routeId);
  if (!hopsVisible || !meta || !meta.points || !routeVisibleForCurrentFilters(meta)) {
    return;
  }
  const visibleRoutePoints = new Set(visibleRouteSegments(meta).flat());

  // Generate color
  const color = stringHashColor(routeId);
  const markersList = [];

  meta.points.forEach((pt, index) => {
    if (!visibleRoutePoints.has(pt)) return;
    // Skip 0 (origin) and last (destination) if we only want hops?
    // "displays the hop number" - usually means 1, 2, 3...
    // The request says "route path on the map".
    // "User clicks on ... hop number ... displays hop number alongside repeater name"
    // Usually we want to see intermediate hops.
    // If points includes origin and dest, index 0 is origin (hop 0?), index N is dest.
    // Let's show all for completeness or just intermediates?
    // "Route Details" implies showing the whole path.
    // Let's show all points with their index.

    const lat = pt.lat;
    const lon = pt.lon;
    if (!Number.isFinite(lat) || !Number.isFinite(lon)) return;

    const icon = L.divIcon({
      className: 'hop-marker-container', // We'll use innerHTML for styling
      html: `<div class="hop-marker" style="background-color: ${color}; width: 16px; height: 16px;">${index}</div>`,
      iconSize: [16, 16],
      iconAnchor: [8, 8]
    });

    const marker = L.marker([lat, lon], { icon, interactive: true }).addTo(hopLayer);
    marker.on('click', (ev) => {
      L.DomEvent.stop(ev);
      showRouteDetails(meta);
    });
    markersList.push(marker);
  });

  hopMarkers.set(routeId, markersList);
}

function normalizeCoreScopeBaseUrl() {
  if (!coreScopeUrl) return '';
  const base = coreScopeUrl.replace(/#\/?$/, '').replace(/\/+$/, '');
  return /^https?:\/\//i.test(base) ? base : '';
}

function buildCoreScopeLink(kind, value) {
  const base = normalizeCoreScopeBaseUrl();
  const target = String(value || '').trim();
  if (!base || !target) return '';
  const normalizedTarget = /^[0-9a-f]+$/i.test(target) ? target.toLowerCase() : target;
  const encoded = encodeURIComponent(normalizedTarget);
  if (kind === 'node') return `${base}/#/nodes/${encoded}`;
  if (kind === 'trace') return `${base}/#/traces/${encoded}`;
  return `${base}/#/packets/${encoded}`;
}

function showRouteDetails(meta) {
  if (!meta || !routeMatchesByteFilter(meta) || !routeMatchesNodeFilter(meta)) {
    hideRouteDetailsPanel();
    return;
  }
  activeRouteDetailsMeta = meta;
  activeRouteDetailsId = meta.id || null;

  // Show panel
  if (routeDetailsPanel) {
    routeDetailsPanel.classList.add('active');
    routeDetailsPanel.hidden = false;
    routeDetailsPanel.style.display = 'block';
    setRouteDetailsPanelCollapsed(false);
  }

  if (routeDetailsTitle) {
    const routeHash = typeof meta.message_hash === 'string' && meta.message_hash.trim()
      ? meta.message_hash.trim()
      : (typeof meta.id === 'string' ? meta.id.trim() : '');
    const routeLabel = routeHash || 'unknown';
    routeDetailsTitle.innerHTML = '';
    routeDetailsTitle.append(document.createTextNode('Route: '));
    const coreScopePacketUrl = buildCoreScopeLink('packet', routeHash);
    if ((packetAnalyzerUrl || coreScopePacketUrl) && routeHash) {
      const link = document.createElement('a');
      link.href = packetAnalyzerUrl
        ? `${packetAnalyzerUrl}${encodeURIComponent(routeHash)}`
        : coreScopePacketUrl;
      link.target = '_blank';
      link.rel = 'noopener';
      link.className = 'route-hash-link';
      link.textContent = routeLabel;
      link.title = routeHash;
      routeDetailsTitle.append(link);
    } else {
      routeDetailsTitle.append(document.createTextNode(routeLabel));
    }
    routeDetailsTitle.append(document.createTextNode(` (${meta.hop_count} hops)`));
  }
  if (routeDetailsTotal) {
    const totalDistance = Number.isFinite(meta.distance_m)
      ? formatDistanceUnits(meta.distance_m)
      : null;
    routeDetailsTotal.textContent = totalDistance ? `Total distance: ${totalDistance}` : '';
  }

  if (routeDetailsContent) {
    routeDetailsContent.innerHTML = '';

    // Generate list
    const color = stringHashColor(meta.id);
    const displayPoints = meta.points.map((pt) => ({ ...pt }));
    const displayHashes = Array.isArray(meta.hashes) ? [...meta.hashes] : [];

    const resolvePointName = (pt, displayIdx) => {
      const isFirst = displayIdx === 0;
      const isLast = displayIdx === displayPoints.length - 1;
      let label = pt.point_label && pt.point_label !== 'Unknown' ? pt.point_label : null;

      if (!label && isFirst && meta.origin_label && !meta.origin_label.toLowerCase().includes('packet')) {
        label = meta.origin_label;
      }
      if (!label && isLast && meta.receiver_label && !meta.receiver_label.toLowerCase().includes('packet')) {
        label = meta.receiver_label;
      }
      if (!label && pt.point_id) {
        label = deviceLabelFromId(pt.point_id);
      }
      if (!label) {
        return isFirst ? 'Origin' : (isLast ? 'Receiver' : `Hop ${displayIdx}`);
      }
      return label;
    };

    displayPoints.forEach((pt, displayIdx) => {
      const row = document.createElement('div');
      row.className = 'hop-row';

      const paramName = resolvePointName(pt, displayIdx);

      const distInfo = Number.isFinite(pt.hop_distance_m)
        ? formatDistanceUnits(pt.hop_distance_m)
        : '';

      let idInfo = '';
      if (pt.node_prefix) {
        idInfo = `Prefix: ${pt.node_prefix}`;
      }

      let roleInfo = '';
      if (pt.role_label) {
        roleInfo = `Role: ${pt.role_label}`;
      }

      let endpointInfo = '';
      if (pt.endpoint_only && pt.endpoint_kind === 'sender_name') {
        endpointInfo = 'Sender name';
      } else if (pt.endpoint_only && pt.endpoint_kind === 'origin') {
        endpointInfo = 'Origin endpoint';
      } else if (pt.endpoint_only && pt.endpoint_kind === 'receiver') {
        endpointInfo = 'Receiver endpoint';
      }

      const metaInfo = [endpointInfo, roleInfo, distInfo, idInfo].filter(Boolean).join(' • ');

      let badgeContent = displayIdx;
      let badgeClass = 'hop-badge';
      let badgeStyle = `background-color: ${color}`;
      const safeBadgeClass = escapeHtmlAttr(badgeClass);
      const safeBadgeStyle = escapeHtmlAttr(badgeStyle);
      const safeBadgeContent = escapeHtml(badgeContent);
      const safeParamName = escapeHtml(paramName);
      const nodeLink = buildCoreScopeLink('node', pt.point_id);
      const nameHtml = nodeLink
        ? `<a class="hop-node-link" href="${escapeHtmlAttr(nodeLink)}" target="_blank" rel="noopener" title="Open ${escapeHtmlAttr(paramName)} in CoreScope">${safeParamName}</a>`
        : safeParamName;
      const safeMetaInfo = escapeHtml(metaInfo);

      row.innerHTML = `
                   <div class="${safeBadgeClass}" style="${safeBadgeStyle}">${safeBadgeContent}</div>
                   <div class="hop-info">
                      <div class="hop-name" title="${escapeHtmlAttr(paramName)}">${nameHtml}</div>
                      <div class="hop-meta">${safeMetaInfo}</div>
                   </div>
                `;
      routeDetailsContent.appendChild(row);
    });
  }
  layoutSidePanels();
}

function setPeersStatus(text) {
  if (peersStatus) {
    peersStatus.classList.remove('peers-status-action');
    peersStatus.removeAttribute('role');
    peersStatus.removeAttribute('tabindex');
    delete peersStatus.dataset.peerDeviceId;
    peersStatus.textContent = text || '';
    peersStatus.hidden = !text;
  }
}

function setPeersPanelTitle(name = 'Node peers', deviceId = '', windowHours = null) {
  if (peersTitle) {
    peersTitle.textContent = name || 'Node peers';
    if (deviceId) {
      peersTitle.classList.add('peers-title-action');
      peersTitle.setAttribute('role', 'button');
      peersTitle.setAttribute('tabindex', '0');
      peersTitle.dataset.peerDeviceId = deviceId;
      peersTitle.title = 'Focus selected node';
    } else {
      peersTitle.classList.remove('peers-title-action');
      peersTitle.removeAttribute('role');
      peersTitle.removeAttribute('tabindex');
      peersTitle.removeAttribute('title');
      delete peersTitle.dataset.peerDeviceId;
    }
  }
  if (peersWindow) {
    peersWindow.textContent = windowHours ? `${windowHours}h window` : '';
    peersWindow.hidden = !windowHours;
  }
}

function setPeersSelectedStatus(name, deviceId, windowHours = null) {
  setPeersPanelTitle(name, deviceId, windowHours);
  setPeersStatus('');
}

function packetLabel(count, direction) {
  const value = Math.max(0, Math.trunc(Number(count) || 0));
  const suffix = value === 1 ? 'pkt' : 'pkts';
  return `${value} ${direction} ${suffix}`;
}

function peerCountLabel(count) {
  const value = Math.max(0, Math.trunc(Number(count) || 0));
  return `${value} ${value === 1 ? 'peer' : 'peers'}`;
}

function renderPeerHeading(target, title, total, direction, unique, lineLabel) {
  if (!target) return;
  if (total == null || unique == null) {
    target.textContent = title;
    return;
  }
  target.innerHTML = `
    <span class="peer-heading-title">${title}</span>
    <span class="peer-heading-stats">
      <span>${packetLabel(total, direction)}</span>
      <span>${peerCountLabel(unique)}</span>
      <em>(${lineLabel})</em>
    </span>
  `;
}

function setPeerHeadings(
  incomingUnique = null,
  outgoingUnique = null,
  incomingTotal = null,
  outgoingTotal = null
) {
  const inCount = Number(incomingUnique);
  const outCount = Number(outgoingUnique);
  renderPeerHeading(
    peersInHeading,
    'Incoming (heard from)',
    incomingTotal,
    'Rx',
    Number.isFinite(inCount) ? inCount : null,
    'Blue lines'
  );
  renderPeerHeading(
    peersOutHeading,
    'Outgoing (heard by)',
    outgoingTotal,
    'Tx',
    Number.isFinite(outCount) ? outCount : null,
    'Purple lines'
  );
}

function clearPeerLines() {
  peerLines.forEach(line => {
    if (line && peerLayer.hasLayer(line)) {
      peerLayer.removeLayer(line);
    }
  });
  peerLines.clear();
  if (map.hasLayer(peerLayer)) {
    map.removeLayer(peerLayer);
  }
}

function renderPeerLines(origin, incoming, outgoing) {
  clearPeerLines();
  if (!peersActive || !nodesVisible) return;
  if (!origin || origin.lat == null || origin.lon == null) return;
  if (mqttOnlyVisible && peersSelectedId) {
    const selectedDevice = deviceData.get(peersSelectedId);
    if (selectedDevice && !devicePassesMqttOnlyFilter(selectedDevice)) return;
  }
  if (peersSelectedId) {
    const selectedDevice = deviceData.get(peersSelectedId);
    if (selectedDevice && !visibleRoles.has(resolveRole(selectedDevice))) return;
  }
  if (!map.hasLayer(peerLayer)) {
    peerLayer.addTo(map);
  }
  const originLatLng = [origin.lat, origin.lon];
  const drawLine = (peer, color, dash, direction) => {
    if (peer.lat == null || peer.lon == null) return;
    const peerDevice = peer.peer_id ? deviceData.get(peer.peer_id) : null;
    const peerRole = peerDevice
      ? resolveRole(peerDevice)
      : resolveRole({ role: peer.role });
    if (!visibleRoles.has(peerRole)) return;
    if (mqttOnlyVisible && peer.peer_id) {
      if (peerDevice && !devicePassesMqttOnlyFilter(peerDevice)) return;
    }
    const line = L.polyline([originLatLng, [peer.lat, peer.lon]], {
      pane: 'peerPane',
      color,
      weight: 3,
      opacity: 0.85,
      dashArray: dash,
      interactive: false
    }).addTo(peerLayer);
    const key = `${direction}:${peer.peer_id || `${peer.lat},${peer.lon}`}`;
    peerLines.set(key, line);
  };
  incoming.forEach(peer => drawLine(peer, '#38bdf8', '6 8', 'in'));
  outgoing.forEach(peer => drawLine(peer, '#a855f7', '2 6', 'out'));
  if (peerLayer.bringToFront) {
    peerLayer.bringToFront();
  }
}

function normalizedPeerFilter() {
  return String(peersFilterText || '').trim().toLowerCase();
}

function peerMatchesFilter(peer, query) {
  if (!query) return true;
  if (!peer) return false;
  const values = [
    peer.name,
    peer.peer_id,
    peer.role,
    peer.peer_id ? String(peer.peer_id).slice(0, 8) : '',
  ];
  return values.some(value => String(value || '').toLowerCase().includes(query));
}

function rankedPeers(peers) {
  const peerItems = Array.isArray(peers) ? peers : [];
  return peerItems.map((peer, index) => ({
    ...peer,
    rank: index + 1,
  }));
}

function filteredPeers(peers) {
  const peerItems = rankedPeers(peers);
  const query = normalizedPeerFilter();
  if (!query) return peerItems;
  return peerItems.filter(peer => peerMatchesFilter(peer, query));
}

function renderCurrentPeers() {
  if (!peersData) return;
  const origin = { lat: peersData.lat, lon: peersData.lon };
  const incoming = filteredPeers(peersData.incoming || []);
  const outgoing = filteredPeers(peersData.outgoing || []);
  renderPeerList(
    peersIn,
    incoming,
    peersData.incoming_total || 0,
    'incoming',
    origin,
    (peersData.incoming || []).length
  );
  renderPeerList(
    peersOut,
    outgoing,
    peersData.outgoing_total || 0,
    'outgoing',
    origin,
    (peersData.outgoing || []).length
  );
  renderPeerLines(origin, incoming, outgoing);
}

function getPeerDistanceMeters(origin, peer) {
  const apiDistance = Number(peer && peer.distance_m);
  if (Number.isFinite(apiDistance) && apiDistance >= 0) {
    return apiDistance;
  }
  if (!origin || !peer) return null;
  const originLat = Number(origin.lat);
  const originLon = Number(origin.lon);
  const peerLat = Number(peer.lat);
  const peerLon = Number(peer.lon);
  if (![originLat, originLon, peerLat, peerLon].every(Number.isFinite)) {
    return null;
  }
  return haversineMeters(originLat, originLon, peerLat, peerLon);
}

function renderPeerList(target, peers, total, label, origin = null, unfilteredCount = null) {
  if (!target) return;
  target.innerHTML = '';
  const peerItems = Array.isArray(peers) ? peers : [];
  if (peerItems.length === 0) {
    const empty = document.createElement('div');
    empty.className = 'small';
    const filtered = normalizedPeerFilter() && Number(unfilteredCount) > 0;
    empty.textContent = filtered
      ? `No ${label} peers match this filter.`
      : `No ${label} data yet.`;
    target.appendChild(empty);
    return;
  }
  peerItems.forEach((peer, index) => {
    const item = document.createElement('div');
    item.className = 'peer-item';
    const name = peer.name || (peer.peer_id ? `${peer.peer_id.slice(0, 8)}…` : 'Unknown');
    const parsedRank = Number(peer.rank);
    const rank = Number.isFinite(parsedRank) && parsedRank > 0
      ? Math.trunc(parsedRank)
      : index + 1;
    const rankDirection = label === 'incoming' ? 'Rx' : 'Tx';
    const percent = total > 0 ? `${peer.percent.toFixed(1)}%` : '0%';
    const distance = formatPeerDistanceUnits(getPeerDistanceMeters(origin, peer));
    const metaParts = [`${peer.count}`, `${percent}`].map(escapeHtml);
    if (distance) {
      metaParts.push(escapeHtml(distance));
    }
    const meta = metaParts.join('<span class="peer-stat-separator" aria-hidden="true">•</span>');
    item.innerHTML = `
      <span class="peer-identity">
        <span class="peer-rank" aria-label="${rankDirection} rank ${rank}">${rank}</span>
        <span class="peer-name">${escapeHtml(name)}</span>
      </span>
      <span class="peer-count">${meta}</span>
    `;
    const peerKey = peer.peer_id ? ` (${peer.peer_id.slice(0, 8)}…)` : '';
    item.title = `${rankDirection} rank ${rank} • ${name}${peerKey}`;
    item.addEventListener('click', () => {
      if (peer.peer_id) {
        focusDevice(peer.peer_id);
      }
    });
    target.appendChild(item);
  });
}

async function selectPeerNode(deviceId) {
  if (!deviceId) return;
  peersSelectedId = deviceId;
  if (!peersActive) return;
  const requestToken = ++peersRequestToken;
  setPeersPanelTitle();
  setPeersStatus('Loading peers…');
  if (peersMeta) {
    peersMeta.textContent = '';
    peersMeta.hidden = true;
  }
  try {
    const res = await fetch(withToken(`/peers/${encodeURIComponent(deviceId)}`), { headers: tokenHeaders() });
    if (!res.ok) {
      throw new Error(`peers ${res.status}`);
    }
    const data = await res.json();
    if (requestToken !== peersRequestToken || !peersActive || peersSelectedId !== deviceId) return;
    peersData = data;
    const name = data.name || (deviceId ? `${deviceId.slice(0, 8)}…` : 'Unknown');
    const inboundTotal = data.incoming_total || 0;
    const outboundTotal = data.outgoing_total || 0;
    const inboundUnique = data.incoming_unique ?? (data.incoming || []).length;
    const outboundUnique = data.outgoing_unique ?? (data.outgoing || []).length;
    setPeersSelectedStatus(name, deviceId, data.window_hours || 24);
    setPeerHeadings(inboundUnique, outboundUnique, inboundTotal, outboundTotal);
    if (peersMeta) {
      peersMeta.textContent = '';
      peersMeta.hidden = true;
    }
    renderCurrentPeers();
  } catch (err) {
    if (requestToken !== peersRequestToken) return;
    setPeersPanelTitle();
    setPeersStatus('Peer lookup failed.');
    if (peersMeta) {
      peersMeta.textContent = '';
      peersMeta.hidden = true;
    }
    setPeerHeadings();
    renderPeerList(peersIn, [], 0, 'incoming');
    renderPeerList(peersOut, [], 0, 'outgoing');
    peersData = null;
    clearPeerLines();
  }
}

function clearPeers() {
  peersRequestToken += 1;
  peersSelectedId = null;
  peersData = null;
  setPeersPanelTitle();
  setPeersStatus('Select a node to view peers.');
  if (peersMeta) {
    peersMeta.textContent = '';
    peersMeta.hidden = true;
  }
  setPeerHeadings();
  renderPeerList(peersIn, [], 0, 'incoming');
  renderPeerList(peersOut, [], 0, 'outgoing');
  if (peersFilter) peersFilter.value = '';
  peersFilterText = '';
  clearPeerLines();
}

function setPeersActive(active) {
  peersActive = active;
  if (peersToggle) {
    peersToggle.classList.toggle('active', active);
    peersToggle.textContent = active ? 'Peers: select node' : 'Peers tool';
  }
  if (peersPanel) {
    peersPanel.classList.toggle('active', active);
    if (active) {
      setPeersPanelCollapsed(false);
      peersPanel.removeAttribute('hidden');
      peersPanel.style.display = '';
    } else {
      peersPanel.setAttribute('hidden', 'hidden');
      peersPanel.style.display = '';
    }
  }
  if (active && peersData) {
    renderCurrentPeers();
  } else if (active) {
    setPeerHeadings(0, 0);
  }
  if (!active) {
    clearPeers();
  }
  layoutSidePanels();
}

function setHeatVisible(visible) {
  heatVisible = visible;
  const btn = document.getElementById('heat-toggle');
  if (!heatAvailable) {
    heatVisible = false;
    if (btn) {
      btn.disabled = true;
      btn.classList.add('disabled');
      btn.textContent = 'Heat unavailable';
    }
    return;
  }
  if (btn) {
    btn.classList.toggle('active', !visible);
    btn.textContent = visible ? 'Hide heat' : 'Show heat';
  }
  if (!nodesVisible) {
    if (heatLayer && map.hasLayer(heatLayer)) {
      map.removeLayer(heatLayer);
    }
    return;
  }
  if (visible) {
    if (heatLayer && !map.hasLayer(heatLayer)) {
      heatLayer.addTo(map);
    }
  } else if (heatLayer && map.hasLayer(heatLayer)) {
    map.removeLayer(heatLayer);
  }
}

function setLosStatus(text) {
  const el = document.getElementById('los-status');
  if (el) {
    el.textContent = text || '';
  }
}

function deviceShortId(d) {
  return d.device_id ? `${d.device_id.slice(0, 8)}…` : '';
}

function deviceDisplayName(d) {
  return d.name || deviceShortId(d) || 'Unknown';
}

function normalizeLinkedDeviceTarget(value) {
  return String(value ?? '').trim().toLowerCase();
}

function linkedDeviceSlug(value) {
  return normalizeLinkedDeviceTarget(value)
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '');
}

function deviceMatchesLinkedTarget(id, d, target) {
  if (!target) return false;
  const normalizedId = normalizeLinkedDeviceTarget(id);
  if (normalizedId === target) return true;
  if (target.length >= 6 && normalizedId.startsWith(target)) return true;

  const name = d && d.name ? d.name : '';
  const normalizedName = normalizeLinkedDeviceTarget(name);
  if (normalizedName && normalizedName === target) return true;
  const targetSlug = linkedDeviceSlug(target);
  return Boolean(targetSlug && linkedDeviceSlug(name) === targetSlug);
}

function findLinkedDeviceId(target) {
  if (!target) return null;
  for (const [id] of deviceData.entries()) {
    if (normalizeLinkedDeviceTarget(id) === target) return id;
  }
  const matches = [];
  for (const [id, d] of deviceData.entries()) {
    if (deviceMatchesLinkedTarget(id, d, target)) {
      matches.push({ id, d });
    }
  }
  const repeater = matches.find(({ d }) => resolveRole(d) === 'repeater');
  return repeater ? repeater.id : (matches[0] ? matches[0].id : null);
}

function tryFocusLinkedDevice() {
  if (linkedDeviceFocusDone || !linkedDeviceTarget) return false;
  const id = findLinkedDeviceId(linkedDeviceTarget);
  if (!id) return false;
  linkedDeviceFocusDone = true;
  if (!nodesVisible) {
    setNodesVisible(true);
  }
  focusDevice(id, { fromLink: true });
  return true;
}

function getLastSeenTs(d) {
  return d.last_seen_ts || d.ts;
}

function isMqttOnline(d) {
  if (d.mqtt_forced) return true;
  const now = getServerNowMs() / 1000;
  const statusValue = String(d.mqtt_status_value || '').trim().toLowerCase();
  const statusTs = Number(d.mqtt_status_ts) || 0;
  if (
    statusTs &&
    mqttOnlineStatusTtlSeconds > 0 &&
    (now - statusTs) <= mqttOnlineStatusTtlSeconds &&
    (statusValue === 'offline' || statusValue === 'disconnected')
  ) {
    return false;
  }

  const source = String(d.mqtt_online_source || '').trim().toLowerCase();
  if (source === 'internal') {
    const ts = Number(d.mqtt_internal_ts) || Number(d.mqtt_seen_ts) || 0;
    return ts > 0 && mqttOnlineInternalTtlSeconds > 0 && (now - ts) <= mqttOnlineInternalTtlSeconds;
  }
  if (source === 'status') {
    const ts = Number(d.mqtt_status_ts) || Number(d.mqtt_seen_ts) || 0;
    return ts > 0 && mqttOnlineStatusTtlSeconds > 0 && (now - ts) <= mqttOnlineStatusTtlSeconds;
  }

  const lastSeen = Number(d.mqtt_seen_ts) || 0;
  if (!lastSeen) return false;
  return mqttOnlineSeconds > 0 && (now - lastSeen) <= mqttOnlineSeconds;
}

function devicePassesMqttOnlyFilter(d) {
  return !mqttOnlyVisible || isMqttOnline(d);
}

function shouldShowDeviceOnMap(d) {
  return Boolean(d) &&
    nodesVisible &&
    visibleRoles.has(resolveRole(d)) &&
    devicePassesMqttOnlyFilter(d) &&
    latLngInViewport(d.lat, d.lon);
}

function updateRoleFilterUi() {
  roleFilterButtons.forEach((button) => {
    const shown = visibleRoles.has(button.dataset.roleFilter);
    button.textContent = shown ? 'Shown' : 'Hidden';
    button.classList.toggle('active', shown);
    button.setAttribute('aria-pressed', shown ? 'true' : 'false');
  });
}

function setRoleVisible(role, shown) {
  if (shown) visibleRoles.add(role);
  else visibleRoles.delete(role);
  localStorage.setItem('meshmapVisibleRoles', [...visibleRoles].join(','));
  updateRoleFilterUi();
  refreshViewportLayers();
  routeLines.forEach((entry, routeId) => {
    syncRouteEntryDisplay(routeId, entry);
  });
  if (peersActive && peersData) renderCurrentPeers();
  refreshStats();
}

function setMqttOnlyVisible(visible) {
  mqttOnlyVisible = Boolean(visible);
  updateMqttOnlyToggleUi();
  refreshViewportLayers();
  routeLines.forEach((entry, routeId) => {
    syncRouteEntryDisplay(routeId, entry);
  });
  if (peersActive && peersData) {
    const selectedDevice = peersSelectedId ? deviceData.get(peersSelectedId) : null;
    if (selectedDevice && !devicePassesMqttOnlyFilter(selectedDevice)) {
      clearPeerLines();
    } else {
      renderCurrentPeers();
    }
  }
  refreshStats();
}

function updateMarkerLabel(m, d) {
  if (!m || !d) return;
  if (!showLabels) {
    if (m.getTooltip()) m.unbindTooltip();
    return;
  }
  const label = deviceDisplayName(d);
  if (!label) return;
  if (m.getTooltip()) {
    m.setTooltipContent(escapeHtml(label));
  } else {
    m.bindTooltip(escapeHtml(label), {
      permanent: true,
      direction: 'top',
      className: 'node-label',
      offset: [0, -6]
    });
  }
}

function renderSearchResults(query) {
  if (!searchResults) return;
  const q = (query || '').trim().toLowerCase();
  searchMatches = [];
  if (!q) {
    searchResults.hidden = true;
    searchResults.innerHTML = '';
    return;
  }
  for (const [id, d] of deviceData.entries()) {
    const name = (d.name || '').toLowerCase();
    if (name.includes(q) || id.toLowerCase().includes(q)) {
      searchMatches.push({ id, d });
    }
  }
  searchMatches = searchMatches.slice(0, 8);
  if (searchMatches.length === 0) {
    searchResults.hidden = true;
    searchResults.innerHTML = '';
    return;
  }
  searchResults.innerHTML = '';
  searchMatches.forEach(({ id, d }) => {
    const item = document.createElement('div');
    item.className = 'node-search-item';
    const name = document.createElement('span');
    name.textContent = deviceDisplayName(d);
    const shortId = document.createElement('span');
    shortId.className = 'node-search-id';
    shortId.textContent = `${id.slice(0, 8)}…`;
    item.append(name, shortId);
    item.addEventListener('click', () => {
      if (peersActive) {
        selectPeerNode(id);
      }
      focusDevice(id);
    });
    searchResults.appendChild(item);
  });
  searchResults.hidden = false;
}

function routeNodeCurrentQuery() {
  const value = routeNodeFilterInput ? routeNodeFilterInput.value : '';
  const parts = String(value || '').split(',');
  return String(parts[parts.length - 1] || '').trim().toLowerCase();
}

function positionRouteNodeFilterResults() {
  if (!routeNodeFilterInput || !routeNodeFilterResults ||
      routeNodeFilterResults.hidden) return;
  const inputRect = routeNodeFilterInput.getBoundingClientRect();
  const viewportPad = 8;
  const gap = 4;
  const width = Math.min(
    inputRect.width,
    Math.max(1, window.innerWidth - viewportPad * 2)
  );
  const panelHeight = Math.max(routeNodeFilterResults.offsetHeight, 1);
  const left = Math.min(
    Math.max(viewportPad, inputRect.left),
    Math.max(viewportPad, window.innerWidth - width - viewportPad)
  );
  const belowTop = inputRect.bottom + gap;
  const aboveTop = inputRect.top - panelHeight - gap;
  const top = belowTop + panelHeight + viewportPad <= window.innerHeight
    ? belowTop
    : Math.max(viewportPad, aboveTop);
  routeNodeFilterResults.style.width = `${width}px`;
  routeNodeFilterResults.style.left = `${left}px`;
  routeNodeFilterResults.style.right = 'auto';
  routeNodeFilterResults.style.top = `${top}px`;
}

function hideRouteNodeFilterResults() {
  if (!routeNodeFilterResults) return;
  routeNodeFilterResults.hidden = true;
}

function selectRouteNodeFilterMatch(match) {
  if (!routeNodeFilterInput || !routeNodeFilterResults || !match) return;
  const parts = routeNodeFilterInput.value.split(',');
  parts.pop();
  const selected = String(match.d.name || match.id).trim();
  const existing = parts.map(value => value.trim()).filter(Boolean);
  if (!existing.some(value => value.toLowerCase() === selected.toLowerCase())) {
    existing.push(selected);
  }
  routeNodeFilterInput.value = `${existing.join(', ')}, `;
  routeNodeFilterText = routeNodeFilterInput.value;
  localStorage.setItem('meshmapRouteNodeFilter', routeNodeFilterText);
  routeNodeMatches = [];
  routeNodeFilterResults.hidden = true;
  routeNodeFilterResults.innerHTML = '';
  syncRouteFilterDisplays();
  routeNodeFilterInput.focus();
  renderRouteNodeFilterResults();
}

function currentRouteDeviceIds() {
  const ids = new Set();
  routeLines.forEach((entry) => {
    const meta = entry && entry.meta;
    if (!meta) return;
    [meta.origin_id, meta.receiver_id].filter(Boolean).forEach(id => ids.add(id));
    if (Array.isArray(meta.points)) {
      meta.points.forEach((point) => {
        if (point && point.point_id) ids.add(point.point_id);
      });
    }
  });
  return ids;
}

function renderRouteNodeFilterResults() {
  if (!routeNodeFilterResults) return;
  const query = routeNodeCurrentQuery();
  routeNodeMatches = [];
  routeNodeFilterResults.innerHTML = '';
  const parts = String(routeNodeFilterInput && routeNodeFilterInput.value || '').split(',');
  parts.pop();
  const selectedNames = new Set(
    parts.map(value => value.trim().toLowerCase()).filter(Boolean)
  );
  const routeDeviceIds = currentRouteDeviceIds();
  for (const id of routeDeviceIds) {
    const d = deviceData.get(id);
    if (!d) continue;
    const name = String(d.name || '').toLowerCase();
    const displayName = String(d.name || id).trim().toLowerCase();
    const matchesQuery = !query || name.includes(query) ||
      id.toLowerCase().includes(query);
    if (matchesQuery && !selectedNames.has(displayName)) {
      routeNodeMatches.push({ id, d });
    }
  }
  routeNodeMatches.sort((a, b) =>
    deviceDisplayName(a.d).localeCompare(deviceDisplayName(b.d))
  );
  routeNodeMatches = routeNodeMatches.slice(0, 8);
  routeNodeMatches.forEach((match) => {
    const item = document.createElement('div');
    item.className = 'node-search-item';
    const name = document.createElement('span');
    name.textContent = deviceDisplayName(match.d);
    const shortId = document.createElement('span');
    shortId.className = 'node-search-id';
    shortId.textContent = `${match.id.slice(0, 8)}…`;
    item.append(name, shortId);
    item.addEventListener('mousedown', (ev) => ev.preventDefault());
    item.addEventListener('click', () => selectRouteNodeFilterMatch(match));
    routeNodeFilterResults.appendChild(item);
  });
  routeNodeFilterResults.hidden = routeNodeMatches.length === 0;
  if (!routeNodeFilterResults.hidden) {
    window.requestAnimationFrame(positionRouteNodeFilterResults);
  }
}

function focusDevice(id, options = {}) {
  const marker = markers.get(id);
  const d = deviceData.get(id);
  if (!marker || !d) return;
  const targetZoom = Math.max(map.getZoom(), Number(options.minZoom) || 13);
  const openPopup = options.openPopup !== false;
  const latlng = marker.getLatLng();
  const token = ++focusDeviceToken;
  let popupOpened = false;
  const openAfterMove = () => {
    if (token !== focusDeviceToken) return;
    if (popupOpened || !openPopup) return;
    popupOpened = true;
    refreshViewportLayers();
    marker.openPopup();
  };
  map.once('moveend', openAfterMove);
  map.flyTo(latlng, targetZoom, { duration: options.fromLink ? 0.35 : 0.6 });
  window.setTimeout(openAfterMove, options.fromLink ? 450 : 700);
  if (searchInput) searchInput.value = '';
  if (searchResults) {
    searchResults.hidden = true;
    searchResults.innerHTML = '';
  }
}

function setLabelsActive(active) {
  showLabels = active;
  localStorage.setItem('meshmapShowLabels', showLabels ? 'true' : 'false');
  markers.forEach((m, id) => {
    const d = deviceData.get(id);
    if (d) updateMarkerLabel(m, d);
  });
  const labelsToggle = document.getElementById('labels-toggle');
  if (labelsToggle) {
    labelsToggle.textContent = showLabels ? 'Labels On' : 'Labels Off';
    labelsToggle.classList.toggle('active', showLabels);
  }
}

function clearLosProfile() {
  if (!losProfile || !losProfileSvg) return;
  losProfile.hidden = true;
  losProfileSvg.innerHTML = '';
  if (losProfileTooltip) {
    losProfileTooltip.hidden = true;
    losProfileTooltip.textContent = '';
  }
  losProfileData = [];
  losProfileMeta = null;
  layoutSidePanels();
}

function clearLosPeaks() {
  losPeakMarkers.forEach(item => {
    const marker = item && item.marker ? item.marker : item;
    if (marker) {
      losLayer.removeLayer(marker);
    }
  });
  losPeakMarkers = [];
  losActivePeak = null;
}

function clearLosHoverMarker() {
  if (losHoverMarker) {
    losLayer.removeLayer(losHoverMarker);
    losHoverMarker = null;
  }
  if (losActivePeak && losActivePeak.marker) {
    losActivePeak.marker.setStyle({
      radius: 4,
      color: '#f59e0b',
      fillColor: '#fbbf24',
      weight: 2,
      fillOpacity: 0.95
    });
    losActivePeak = null;
  }
}

function getLosSegmentLabel(index) {
  if (!Number.isInteger(index) || index < 0) return '';
  return `${index + 1}→${index + 2}`;
}

function buildCombinedLosProfile() {
  const combined = [];
  const segmentRanges = [];
  let offset = 0;
  let anyBlocked = false;
  losSegmentMeta.forEach((meta, index) => {
    const profile = Array.isArray(meta?.profile) ? meta.profile : null;
    if (!profile || profile.length < 2) return;
    const startDistance = offset;
    profile.forEach((point, pointIndex) => {
      const distance = Number(point[0]);
      const terrain = Number(point[1]);
      const losLineValue = Number(point[2]);
      if (![distance, terrain, losLineValue].every(Number.isFinite)) return;
      if (index > 0 && pointIndex === 0) return;
      combined.push([offset + distance, terrain, losLineValue]);
    });
    const segmentDistance = Number(profile[profile.length - 1][0]) || 0;
    const endDistance = offset + segmentDistance;
    segmentRanges[index] = { startDistance, endDistance };
    offset = endDistance;
    anyBlocked = anyBlocked || !!meta?.blocked;
  });
  return { profile: combined, blocked: anyBlocked, segmentRanges };
}

function resolveLosProfileDistance(distanceMeters) {
  const ranges = Array.isArray(losProfileMeta?.segmentRanges) ? losProfileMeta.segmentRanges : [];
  if (!ranges.length) {
    const endpoints = getActiveLosSegmentEndpoints();
    if (!endpoints) return null;
    return { segmentIndex: losActiveSegmentIndex, localDistance: distanceMeters, endpoints };
  }
  const clamped = Math.min(Math.max(distanceMeters, 0), losProfileMeta.totalDistance || 0);
  for (let index = 0; index < ranges.length; index++) {
    const range = ranges[index];
    if (!range) continue;
    const isLast = index === ranges.length - 1;
    if (clamped < range.endDistance || isLast) {
      const endpoints = getLosSegmentEndpoints(index);
      if (!endpoints) return null;
      return {
        segmentIndex: index,
        localDistance: Math.max(0, clamped - range.startDistance),
        endpoints
      };
    }
  }
  return null;
}

function getLosSegmentEndpoints(index) {
  if (!Number.isInteger(index) || index < 0 || (index + 1) >= losPoints.length) return null;
  return [losPoints[index], losPoints[index + 1]];
}

function getActiveLosSegmentEndpoints() {
  return getLosSegmentEndpoints(losActiveSegmentIndex);
}

function getActiveLosLine() {
  if (!Number.isInteger(losActiveSegmentIndex) || losActiveSegmentIndex < 0) return null;
  return losLines[losActiveSegmentIndex] || null;
}

function updateLosSegmentStyles() {
  losLines.forEach((line, index) => {
    if (!line) return;
    const meta = losSegmentMeta[index] || null;
    const active = index === losActiveSegmentIndex;
    const color = meta ? (meta.blocked ? '#ef4444' : '#22c55e') : '#9ca3af';
    line.setStyle({
      color,
      weight: active ? 5 : 4,
      opacity: active ? 0.9 : 0.75,
      dashArray: '6 10'
    });
  });
}

function selectLosSegment(index, options = {}) {
  if (!Number.isInteger(index) || index < 0 || index >= losLines.length) return;
  losActiveSegmentIndex = index;
  syncLosHeightInputs();
  updateLosSegmentStyles();
  const meta = losSegmentMeta[index] || null;
  const combined = buildCombinedLosProfile();
  if (combined.profile.length >= 2) {
    renderLosProfile(combined.profile, combined.blocked, combined);
  }
  if (meta) {
    lastLosStatusMeta = meta;
    setLosStatus(buildLosStatus(meta));
  } else if (options.silent !== true) {
    setLosStatus(`LOS: selected segment ${getLosSegmentLabel(index)}`);
  }
  if (options.recompute === true) {
    scheduleLosCheck(true, { allowNetwork: true, forceNetwork: true });
  }
}

function ensureLosSegments() {
  const needed = Math.max(0, losPoints.length - 1);
  while (losLines.length > needed) {
    const line = losLines.pop();
    if (line) {
      losLayer.removeLayer(line);
    }
  }
  while (losSegmentMeta.length > needed) {
    losSegmentMeta.pop();
  }
  for (let index = 0; index < needed; index++) {
    const endpoints = getLosSegmentEndpoints(index);
    if (!endpoints) continue;
    const latlngs = [endpoints[0], endpoints[1]];
    let line = losLines[index];
    if (!line) {
      line = L.polyline(latlngs, {
        color: '#9ca3af',
        weight: 4,
        opacity: 0.8,
        dashArray: '6 10'
      }).addTo(losLayer);
      line.__losSegmentIndex = index;
      line.on('mousemove', (ev) => {
        if (line.__losSegmentIndex !== losActiveSegmentIndex) return;
        if (ev && ev.latlng) {
          updateLosProfileFromMap(ev.latlng);
        }
      });
      line.on('mouseout', clearLosProfileHover);
      line.on('click', (ev) => {
        if (ev && ev.originalEvent) {
          ev.originalEvent.preventDefault();
          ev.originalEvent.stopPropagation();
        }
        if (typeof L !== 'undefined' && L.DomEvent) {
          L.DomEvent.stop(ev);
        }
        selectLosSegment(line.__losSegmentIndex, { recompute: true });
      });
      losLines[index] = line;
    } else {
      line.__losSegmentIndex = index;
      line.setLatLngs(latlngs);
    }
  }
  if (needed === 0) {
    losActiveSegmentIndex = null;
  } else if (losActiveSegmentIndex == null || losActiveSegmentIndex >= needed) {
    losActiveSegmentIndex = needed - 1;
  }
  updateLosSegmentStyles();
}
function setPropStatus(text) {
  const el = document.getElementById('prop-status');
  if (el) {
    el.textContent = text || '';
  }
}

function setPropRange(text) {
  const el = document.getElementById('prop-range');
  if (el) {
    el.textContent = text || '';
  }
}

function setPropCost(text) {
  const el = document.getElementById('prop-cost');
  if (el) {
    el.textContent = text || '';
  }
}
function layoutSidePanels() {
  if (!losPanel || !propPanel) return;
  const panels = [];
  if (losActive && losPanel.classList.contains('active')) panels.push(losPanel);
  if (radarVisible && weatherPanel && weatherPanel.classList.contains('active')) panels.push(weatherPanel);
  if (historyVisible && historyPanel && historyPanel.classList.contains('active')) panels.push(historyPanel);
  if (peersActive && peersPanel && peersPanel.classList.contains('active')) panels.push(peersPanel);
  if (routeDetailsPanel && routeDetailsPanel.classList.contains('active')) panels.push(routeDetailsPanel);
  if (propagationActive && propPanel.classList.contains('active')) panels.push(propPanel);
  const allPanels = [losPanel, weatherPanel, historyPanel, peersPanel, routeDetailsPanel, propPanel];
  allPanels.forEach(panel => {
    if (!panel) return;
    panel.style.top = '';
    panel.style.bottom = '';
    panel.style.maxHeight = '';
  });
  if (!panels.length) return;
  const gap = 12;
  const availableHeight = Math.max(200, window.innerHeight - 24);
  const totalHeight = panels.reduce((sum, panel) => sum + (panel.offsetHeight || 0), 0)
    + (panels.length - 1) * gap;
  if (totalHeight > availableHeight) {
    const maxPer = Math.max(
      140,
      Math.floor((availableHeight - (panels.length - 1) * gap) / panels.length)
    );
    panels.forEach(panel => {
      panel.style.maxHeight = `${maxPer}px`;
    });
  }
  const isMobile = window.matchMedia('(max-width: 900px)').matches;
  if (isMobile) {
    let bottom = 12;
    panels.slice().reverse().forEach(panel => {
      panel.style.bottom = `${bottom}px`;
      bottom += (panel.offsetHeight || 0) + gap;
    });
    return;
  }
  let top = 18;
  panels.forEach(panel => {
    panel.style.top = `${top}px`;
    top += (panel.offsetHeight || 0) + gap;
  });
}

function setToolPanelCollapsed(panel, button, collapsed, storageKey) {
  if (!panel || !button) return;
  panel.classList.toggle('panel-collapsed', collapsed);
  button.textContent = collapsed ? 'Expand' : 'Minimize';
  button.setAttribute('aria-expanded', collapsed ? 'false' : 'true');
  try {
    localStorage.setItem(storageKey, collapsed ? 'true' : 'false');
  } catch (_err) {
    // ignore storage failures
  }
  layoutSidePanels();
}

function setLosPanelCollapsed(collapsed) {
  losPanelCollapsed = Boolean(collapsed);
  setToolPanelCollapsed(
    losPanel,
    losPanelCollapse,
    losPanelCollapsed,
    LOS_PANEL_COLLAPSED_KEY
  );
}

function setPropPanelCollapsed(collapsed) {
  propPanelCollapsed = Boolean(collapsed);
  setToolPanelCollapsed(
    propPanel,
    propPanelCollapse,
    propPanelCollapsed,
    PROP_PANEL_COLLAPSED_KEY
  );
}

function setHistoryPanelCollapsed(collapsed) {
  historyPanelCollapsed = Boolean(collapsed);
  setToolPanelCollapsed(
    historyPanel,
    historyPanelCollapse,
    historyPanelCollapsed,
    HISTORY_PANEL_COLLAPSED_KEY
  );
}

function setPeersPanelCollapsed(collapsed) {
  peersPanelCollapsed = Boolean(collapsed);
  setToolPanelCollapsed(
    peersPanel,
    peersPanelCollapse,
    peersPanelCollapsed,
    PEERS_PANEL_COLLAPSED_KEY
  );
}

function setRouteDetailsPanelCollapsed(collapsed) {
  routeDetailsPanelCollapsed = Boolean(collapsed);
  setToolPanelCollapsed(
    routeDetailsPanel,
    routeDetailsCollapse,
    routeDetailsPanelCollapsed,
    ROUTE_DETAILS_PANEL_COLLAPSED_KEY
  );
}
function clearLos() {
  losPoints = [];
  losPointHeights = [];
  persistLosPointHeights();
  losLines = [];
  losSegmentMeta = [];
  losActiveSegmentIndex = null;
  losSuggestion = null;
  losLocked = false;
  lastLosStatusMeta = null;
  if (losComputeTimer) {
    clearTimeout(losComputeTimer);
    losComputeTimer = null;
  }
  losComputeToken += 1;
  losComputeLast = 0;
  losLayer.clearLayers();
  setLosStatus('');
  clearLosProfile();
  clearLosPeaks();
  clearLosHoverMarker();
  losSelectedPointIndex = null;
  losPointMarkers = [];
  syncLosHeightInputs();
}

function setLosActive(active) {
  losActive = active;
  const btn = document.getElementById('los-toggle');
  if (btn) {
    btn.classList.toggle('active', active);
    btn.textContent = active ? 'LOS: add pins' : 'LOS tool';
  }
  if (losLegendGroup) {
    losLegendGroup.classList.toggle('active', active);
  }
  if (losPanel) {
    losPanel.classList.toggle('active', active);
  }
  setLosPanelCollapsed(losPanelCollapsed);
  if (!active) {
    clearLos();
  } else {
    losLocked = false;
    setLosStatus('LOS: select first point (Shift+click or long-press nodes)');
  }
  layoutSidePanels();
}

function losFrequencyHz() {
  return PROP_DEFAULTS.freqMHz * 1e6;
}

function losFirstFresnelRadiusMeters(distanceMeters, sampleDistanceMeters) {
  if (!(distanceMeters > 0) || !(sampleDistanceMeters >= 0)) return 0;
  const d1 = sampleDistanceMeters;
  const d2 = distanceMeters - d1;
  if (!(d2 >= 0)) return 0;
  const frequencyHz = losFrequencyHz();
  if (!(frequencyHz > 0)) return 0;
  const wavelengthMeters = 299792458 / frequencyHz;
  return Math.sqrt((wavelengthMeters * d1 * d2) / distanceMeters);
}

function losFresnelRadiusAtProfileDistance(distanceMeters, segmentRanges) {
  const ranges = Array.isArray(segmentRanges) ? segmentRanges : [];
  if (ranges.length) {
    for (let index = 0; index < ranges.length; index += 1) {
      const range = ranges[index];
      if (!range) continue;
      const isLast = index === ranges.length - 1;
      if (distanceMeters < range.endDistance || isLast) {
        const segmentDistance = Math.max(
          0,
          Number(range.endDistance) - Number(range.startDistance)
        );
        const localDistance = Math.max(
          0,
          distanceMeters - Number(range.startDistance || 0)
        );
        return losFirstFresnelRadiusMeters(segmentDistance, localDistance);
      }
    }
  }
  const totalDistance = ranges.length
    ? Math.max(0, Number(ranges[ranges.length - 1]?.endDistance || 0))
    : Math.max(0, Number(distanceMeters));
  return losFirstFresnelRadiusMeters(totalDistance, distanceMeters);
}

function renderLosProfile(profile, blocked, options = {}) {
  if (!losProfile || !losProfileSvg) return;
  if (!Array.isArray(profile) || profile.length < 2) {
    clearLosProfile();
    return;
  }
  const width = 300;
  const height = 90;
  const pad = 6;
  const last = profile[profile.length - 1];
  const totalDistance = Math.max(1, Number(last[0]) || 1);
  const segmentRanges = Array.isArray(options.segmentRanges)
    ? options.segmentRanges
    : [];
  let minElev = Infinity;
  let maxElev = -Infinity;
  profile.forEach(item => {
    const terrain = Number(item[1]);
    const los = Number(item[2]);
    const distance = Number(item[0]);
    const fresnelRadius = losFresnelRadiusAtProfileDistance(
      distance,
      segmentRanges
    );
    const fresnelUpper = los + fresnelRadius;
    const fresnelLower = los - fresnelRadius;
    if (!Number.isNaN(terrain)) {
      minElev = Math.min(minElev, terrain);
      maxElev = Math.max(maxElev, terrain);
    }
    if (!Number.isNaN(los)) {
      minElev = Math.min(minElev, los);
      maxElev = Math.max(maxElev, los);
    }
    if (!Number.isNaN(fresnelUpper)) {
      minElev = Math.min(minElev, fresnelUpper);
      maxElev = Math.max(maxElev, fresnelUpper);
    }
    if (!Number.isNaN(fresnelLower)) {
      minElev = Math.min(minElev, fresnelLower);
      maxElev = Math.max(maxElev, fresnelLower);
    }
  });
  if (!Number.isFinite(minElev) || !Number.isFinite(maxElev) || minElev === maxElev) {
    clearLosProfile();
    return;
  }
  const span = maxElev - minElev;
  const innerWidth = width - pad * 2;
  const innerHeight = height - pad * 2;
  const toX = (d) => pad + (d / totalDistance) * innerWidth;
  const toY = (e) => height - pad - ((e - minElev) / span) * innerHeight;
  const terrainPath = profile.map((item, idx) => {
    const d = Number(item[0]);
    const elev = Number(item[1]);
    return `${idx === 0 ? 'M' : 'L'}${toX(d).toFixed(2)} ${toY(elev).toFixed(2)}`;
  }).join(' ');
  const losPath = profile.map((item, idx) => {
    const d = Number(item[0]);
    const elev = Number(item[2]);
    return `${idx === 0 ? 'M' : 'L'}${toX(d).toFixed(2)} ${toY(elev).toFixed(2)}`;
  }).join(' ');
  const fresnelUpperPath = profile.map((item, idx) => {
    const d = Number(item[0]);
    const los = Number(item[2]);
    const elev = los + losFresnelRadiusAtProfileDistance(d, segmentRanges);
    return `${idx === 0 ? 'M' : 'L'}${toX(d).toFixed(2)} ${toY(elev).toFixed(2)}`;
  }).join(' ');
  const fresnelLowerPath = profile.map((item, idx) => {
    const d = Number(item[0]);
    const los = Number(item[2]);
    const elev = los - losFresnelRadiusAtProfileDistance(d, segmentRanges);
    return `${idx === 0 ? 'M' : 'L'}${toX(d).toFixed(2)} ${toY(elev).toFixed(2)}`;
  }).join(' ');
  const losColor = blocked ? '#ef4444' : '#22c55e';
  losProfileSvg.setAttribute('viewBox', `0 0 ${width} ${height}`);
  losProfileSvg.innerHTML = `
        <path class="los-profile-terrain" d="${terrainPath}"></path>
        <path class="los-profile-fresnel" d="${fresnelUpperPath}"></path>
        <path class="los-profile-fresnel" d="${fresnelLowerPath}"></path>
        <path class="los-profile-los" d="${losPath}" stroke="${losColor}"></path>
        <line id="los-profile-cursor" x1="0" y1="0" x2="0" y2="${height}" stroke="rgba(255,255,255,.35)" stroke-width="1" opacity="0" />
        <circle id="los-profile-point" cx="0" cy="0" r="3" fill="${losColor}" opacity="0" />
      `;
  losProfileData = profile;
  losProfileMeta = {
    width,
    height,
    pad,
    minElev,
    maxElev,
    totalDistance,
    innerWidth,
    innerHeight,
    blocked,
    segmentRanges
  };
  losProfile.hidden = false;
  layoutSidePanels();
}

function formatDistanceUnits(meters) {
  if (meters == null) return '';
  const value = Number(meters);
  if (Number.isNaN(value)) return '';
  if (distanceUnits === 'mi') {
    const miles = value / 1609.344;
    if (miles < 0.5) {
      const feet = value * 3.28084;
      return `${Math.round(feet)} ft`;
    }
    return `${miles.toFixed(2)} mi`;
  }
  if (value >= 1000) return `${(value / 1000).toFixed(2)} km`;
  return `${Math.round(value)} m`;
}

function formatPeerDistanceUnits(meters) {
  if (meters == null) return '';
  const value = Number(meters);
  if (!Number.isFinite(value) || value < 0) return '';
  if (distanceUnits === 'mi') {
    const miles = value / 1609.344;
    const decimals = miles < 10 ? 1 : 0;
    return `${miles.toFixed(decimals)} mi`;
  }
  const km = value / 1000.0;
  const decimals = km < 10 ? 1 : 0;
  return `${km.toFixed(decimals)} km`;
}

function formatDistanceMeters(meters) {
  return formatDistanceUnits(meters);
}

function formatObstructionUnits(meters) {
  if (meters == null) return '';
  const value = Number(meters);
  if (Number.isNaN(value)) return '';
  if (distanceUnits === 'mi') {
    const feet = value * 3.28084;
    return `${feet.toFixed(1)} ft`;
  }
  return `${value.toFixed(1)} m`;
}

function buildLosStatus(meta) {
  if (!meta) return '';
  const distance = meta.distance_m != null ? formatDistanceUnits(meta.distance_m) : '';
  const obstruction = meta.blocked
    ? `Blocked (+${formatObstructionUnits(meta.obstruction_m)})`
    : 'Clear';
  const segmentLabel = meta.segment_label ? `${meta.segment_label} • ` : '';
  let status = `LOS: ${segmentLabel}${distance} • ${obstruction}`;
  if (meta.suggested) {
    status += meta.suggested_clear
      ? ' • Relay Suggested'
      : ' • Relay May Help (Still Blocked)';
  }
  return status;
}

function formatElevationMeters(meters) {
  if (meters == null) return '';
  const value = Number(meters);
  if (Number.isNaN(value)) return '';
  return `${value.toFixed(1)} m`;
}

function updateLosProfileCursor(distance, terrain, losLineValue) {
  if (!losProfileMeta || !losProfileSvg || !losProfileTooltip) return;
  if (!losProfileData || losProfileData.length < 2) return;
  const total = losProfileMeta.totalDistance;
  const clampedDistance = Math.min(Math.max(distance, 0), total);
  const xSvg = losProfileMeta.pad + (clampedDistance / total) * losProfileMeta.innerWidth;
  const ySvg = losProfileMeta.height - losProfileMeta.pad -
    ((terrain - losProfileMeta.minElev) / (losProfileMeta.maxElev - losProfileMeta.minElev)) * losProfileMeta.innerHeight;
  const cursor = document.getElementById('los-profile-cursor');
  const dot = document.getElementById('los-profile-point');
  if (cursor) {
    cursor.setAttribute('x1', xSvg.toFixed(2));
    cursor.setAttribute('x2', xSvg.toFixed(2));
    cursor.setAttribute('opacity', '1');
  }
  if (dot) {
    dot.setAttribute('cx', xSvg.toFixed(2));
    dot.setAttribute('cy', ySvg.toFixed(2));
    dot.setAttribute('opacity', '1');
  }
  const fresnelRadius = losFirstFresnelRadiusMeters(
    losProfileMeta.totalDistance,
    clampedDistance
  );
  const segmentFresnelRadius = losFresnelRadiusAtProfileDistance(
    clampedDistance,
    losProfileMeta.segmentRanges
  );
  losProfileTooltip.hidden = false;
  losProfileTooltip.textContent = `Distance ${formatDistanceMeters(clampedDistance)} • Terrain ${formatElevationMeters(terrain)} • LOS ${formatElevationMeters(losLineValue)} • Fresnel ${formatElevationMeters(segmentFresnelRadius || fresnelRadius)}`;
  losProfileTooltip.style.left = `${xSvg}px`;
  losProfileTooltip.style.top = `${ySvg}px`;
}

function updateLosPeakHighlight(distanceMeters) {
  if (!losPeakMarkers.length || distanceMeters == null) {
    if (losActivePeak) {
      losActivePeak.marker.setStyle({
        radius: 4,
        color: '#f59e0b',
        fillColor: '#fbbf24',
        weight: 2,
        fillOpacity: 0.95
      });
      if (losActivePeak.marker.closeTooltip) {
        losActivePeak.marker.closeTooltip();
      }
      losActivePeak = null;
    }
    return null;
  }
  const threshold = Math.max(150, losSampleStepMeters * 0.75);
  let best = null;
  losPeakMarkers.forEach(item => {
    if (!item || item.distance == null) return;
    const delta = Math.abs(item.distance - distanceMeters);
    if (delta <= threshold && (!best || delta < best.delta)) {
      best = { item, delta };
    }
  });
  if (!best) {
    if (losActivePeak) {
      losActivePeak.marker.setStyle({
        radius: 4,
        color: '#f59e0b',
        fillColor: '#fbbf24',
        weight: 2,
        fillOpacity: 0.95
      });
      if (losActivePeak.marker.closeTooltip) {
        losActivePeak.marker.closeTooltip();
      }
      losActivePeak = null;
    }
    return null;
  }
  if (losActivePeak && losActivePeak !== best.item) {
    losActivePeak.marker.setStyle({
      radius: 4,
      color: '#f59e0b',
      fillColor: '#fbbf24',
      weight: 2,
      fillOpacity: 0.95
    });
    if (losActivePeak.marker.closeTooltip) {
      losActivePeak.marker.closeTooltip();
    }
  }
  if (!losActivePeak || losActivePeak !== best.item) {
    best.item.marker.setStyle({
      radius: 6,
      color: '#f97316',
      fillColor: '#fbbf24',
      weight: 2,
      fillOpacity: 1
    });
    best.item.marker.openTooltip();
    losActivePeak = best.item;
  }
  return `Peak ${best.item.index}`;
}

function updateLosMapHover(distanceMeters) {
  const resolved = resolveLosProfileDistance(distanceMeters);
  if (!losProfileMeta || !resolved) return;
  const [start, end] = resolved.endpoints;
  const total = haversineMeters(start.lat, start.lng, end.lat, end.lng);
  const clamped = Math.min(Math.max(resolved.localDistance, 0), total);
  const t = total > 0 ? (clamped / total) : 0;
  const lat = start.lat + (end.lat - start.lat) * t;
  const lon = start.lng + (end.lng - start.lng) * t;
  const label = resolved.segmentIndex === losActiveSegmentIndex ? updateLosPeakHighlight(clamped) : null;
  const tooltip = label
    ? `${label} • ${formatDistanceMeters(clamped)}`
    : `LOS ${getLosSegmentLabel(resolved.segmentIndex)} • ${formatDistanceMeters(clamped)}`;
  if (!losHoverMarker) {
    losHoverMarker = L.circleMarker([lat, lon], {
      radius: 5,
      color: '#e2e8f0',
      fillColor: '#0f172a',
      fillOpacity: 0.9,
      weight: 2,
      bubblingMouseEvents: false
    }).addTo(losLayer);
  } else {
    losHoverMarker.setLatLng([lat, lon]);
  }
  losHoverMarker.bindTooltip(tooltip, { direction: 'top', opacity: 0.9, offset: [0, -8] });
  losHoverMarker.openTooltip();
}

function updateLosProfileHover(ev) {
  if (!losProfileMeta || !losProfileSvg || !losProfileTooltip) return;
  if (!losProfileData || losProfileData.length < 2) return;
  const rect = losProfileSvg.getBoundingClientRect();
  const x = Math.min(Math.max(ev.clientX - rect.left, losProfileMeta.pad), rect.width - losProfileMeta.pad);
  const ratio = (x - losProfileMeta.pad) / Math.max(1, rect.width - losProfileMeta.pad * 2);
  const idx = Math.min(losProfileData.length - 1, Math.max(0, Math.round(ratio * (losProfileData.length - 1))));
  const point = losProfileData[idx];
  if (!point) return;
  updateLosProfileCursor(point[0], point[1], point[2]);
  updateLosMapHover(point[0]);
}

function losProfileDistanceFromEvent(ev) {
  if (!losProfileMeta || !losProfileSvg) return null;
  const rect = losProfileSvg.getBoundingClientRect();
  const x = Math.min(Math.max(ev.clientX - rect.left, losProfileMeta.pad), rect.width - losProfileMeta.pad);
  const ratio = (x - losProfileMeta.pad) / Math.max(1, rect.width - losProfileMeta.pad * 2);
  const total = losProfileMeta.totalDistance;
  return Math.min(Math.max(ratio, 0), 1) * total;
}

function copyLosCoords(distanceMeters) {
  const resolved = resolveLosProfileDistance(distanceMeters);
  if (!resolved || distanceMeters == null || !losProfileMeta) return;
  const [start, end] = resolved.endpoints;
  const total = haversineMeters(start.lat, start.lng, end.lat, end.lng);
  const t = total > 0 ? Math.min(Math.max(resolved.localDistance / total, 0), 1) : 0;
  const lat = start.lat + (end.lat - start.lat) * t;
  const lon = start.lng + (end.lng - start.lng) * t;
  const coords = `${lat.toFixed(5)}, ${lon.toFixed(5)}`;
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(coords).then(() => {
      setLosStatus(`LOS: coords copied ${coords}`);
    }).catch(() => {
      setLosStatus(`LOS: ${coords}`);
    });
  } else {
    setLosStatus(`LOS: ${coords}`);
  }
  updateLosMapHover(distanceMeters);
}

function updateLosProfileAtDistance(distanceMeters) {
  if (!losProfileData || losProfileData.length < 2 || !losProfileMeta) return;
  const total = losProfileMeta.totalDistance;
  const clamped = Math.min(Math.max(distanceMeters, 0), total);
  lastLosDistance = clamped;
  const idx = Math.min(losProfileData.length - 1, Math.max(0, Math.round((clamped / total) * (losProfileData.length - 1))));
  const point = losProfileData[idx];
  if (!point) return;
  updateLosProfileCursor(point[0], point[1], point[2]);
  updateLosMapHover(point[0]);
}

function clearLosProfileHover() {
  const cursor = document.getElementById('los-profile-cursor');
  const dot = document.getElementById('los-profile-point');
  if (cursor) cursor.setAttribute('opacity', '0');
  if (dot) dot.setAttribute('opacity', '0');
  if (losProfileTooltip) losProfileTooltip.hidden = true;
  clearLosHoverMarker();
}

function updateLosProfileFromMap(latlng) {
  const endpoints = getActiveLosSegmentEndpoints();
  if (!latlng || !endpoints) return;
  if (!losProfileMeta || !losProfileData || losProfileData.length < 2) return;
  const [start, end] = endpoints;
  const dLat = end.lat - start.lat;
  const dLon = end.lng - start.lng;
  const denom = (dLat * dLat) + (dLon * dLon);
  if (denom === 0) return;
  let t = ((latlng.lat - start.lat) * dLat + (latlng.lng - start.lng) * dLon) / denom;
  t = Math.min(Math.max(t, 0), 1);
  const totalDistance = haversineMeters(start.lat, start.lng, end.lat, end.lng);
  const ranges = Array.isArray(losProfileMeta.segmentRanges) ? losProfileMeta.segmentRanges : [];
  const startOffset = ranges[losActiveSegmentIndex]?.startDistance || 0;
  updateLosProfileAtDistance(startOffset + (totalDistance * t));
}

function renderLosPeaks(peaks) {
  clearLosPeaks();
  if (!Array.isArray(peaks) || peaks.length === 0) return;
  peaks.forEach((peak, idx) => {
    const lat = Number(peak.lat);
    const lon = Number(peak.lon);
    if (Number.isNaN(lat) || Number.isNaN(lon)) return;
    const index = peak.index || (idx + 1);
    const distanceMeters = peak.distance_m != null ? Number(peak.distance_m) : null;
    const distance = formatDistanceMeters(distanceMeters);
    const elev = peak.elevation_m != null ? `${peak.elevation_m} m` : '';
    const coord = `${lat.toFixed(5)}, ${lon.toFixed(5)}`;
    const tooltip = `Peak ${index}${distance ? ` • ${distance}` : ''}<br/>${coord}${elev ? `<br/>${elev}` : ''}`;
    const marker = L.circleMarker([lat, lon], {
      radius: 4,
      color: '#f59e0b',
      fillColor: '#fbbf24',
      fillOpacity: 0.95,
      weight: 2,
      bubblingMouseEvents: false
    }).addTo(losLayer);
    marker.bindTooltip(tooltip, { direction: 'top', opacity: 0.9 });
    marker.on('click', (ev) => {
      if (ev && ev.originalEvent) {
        ev.originalEvent.preventDefault();
        ev.originalEvent.stopPropagation();
      }
      const coords = `${lat.toFixed(5)}, ${lon.toFixed(5)}`;
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(coords).then(() => {
          setLosStatus(`LOS: Peak ${index} coords copied`);
        }).catch(() => {
          setLosStatus(`LOS: Peak ${index} ${coords}`);
        });
      } else {
        setLosStatus(`LOS: Peak ${index} ${coords}`);
      }
    });
    losPeakMarkers.push({
      marker,
      index,
      distance: Number.isNaN(distanceMeters) ? null : distanceMeters,
      lat,
      lon
    });
  });
}

function applyLosResult(data) {
  if (!data || !data.ok) return false;
  const activeIndex = losActiveSegmentIndex;
  const activeLine = getActiveLosLine();
  if (Array.isArray(data.profile) && data.profile.length > 1) {
    const terrain = data.profile.map(item => Number(item[1]));
    if (terrain.every(val => Number.isFinite(val))) {
      losLastElevations = terrain;
      losLastElevationCount = terrain.length;
    }
  }
  const blocked = data.blocked;
  const meters = data.distance_m != null ? Number(data.distance_m) : null;
  const segmentMeta = {
    segment_index: activeIndex,
    segment_label: getLosSegmentLabel(activeIndex),
    distance_m: Number.isFinite(meters) ? meters : null,
    blocked,
    obstruction_m: data.max_obstruction_m,
    suggested: false,
    suggested_clear: false,
    profile: Array.isArray(data.profile) ? data.profile : []
  };
  if (losSuggestion) {
    losLayer.removeLayer(losSuggestion);
    losSuggestion = null;
  }
  if (blocked) {
    renderLosPeaks(data.peaks);
  } else {
    clearLosPeaks();
  }
  if (data.suggested) {
    const s = data.suggested;
    const label = s.clear ? 'Relay (Clear)' : 'Relay (Still Blocked)';
    const color = s.clear ? '#22c55e' : '#f59e0b';
    losSuggestion = L.circleMarker([s.lat, s.lon], {
      radius: 6,
      color,
      fillColor: color,
      fillOpacity: 0.9,
      weight: 2
    }).addTo(losLayer);
    losSuggestion.bindTooltip(`${label}<br/>${s.lat}, ${s.lon}`, { direction: 'top' });
    segmentMeta.suggested = true;
    segmentMeta.suggested_clear = !!s.clear;
  }
  if (Number.isInteger(activeIndex) && activeIndex >= 0) {
    losSegmentMeta[activeIndex] = { ...segmentMeta };
  }
  lastLosStatusMeta = segmentMeta;
  setLosStatus(buildLosStatus(segmentMeta));
  const combined = buildCombinedLosProfile();
  renderLosProfile(combined.profile, combined.blocked, combined);
  updateLosSegmentStyles();
  if (activeLine) {
    activeLine.bringToFront();
  }
  clearLosProfileHover();
  return true;
}

async function runLosCheckClient(a, b, options = {}) {
  const startIndex = Number.isInteger(losActiveSegmentIndex) ? losActiveSegmentIndex : 0;
  const endIndex = startIndex + 1;
  const heightA = getLosPointHeight(startIndex);
  const heightB = getLosPointHeight(endIndex);
  const distanceMeters = haversineMeters(a.lat, a.lng, b.lat, b.lng);
  if (distanceMeters <= 0) {
    return { ok: false, error: 'invalid_distance' };
  }
  const points = sampleLosPoints(a.lat, a.lng, b.lat, b.lng);
  const elevationResponse = await fetchElevations(points, options);
  if (!elevationResponse.ok) {
    return {
      ok: false,
      error: elevationResponse.error || 'elevation_failed',
      rateLimited: elevationResponse.rateLimited === true
    };
  }
  const elevations = elevationResponse.elevations || [];
  if (elevations.length !== points.length) {
    return { ok: false, error: 'elevation_failed:unexpected_length' };
  }
  if (!elevationResponse.approximate || !losLastElevations) {
    losLastElevations = elevations.slice();
    losLastElevationCount = elevations.length;
  }
  const adjusted = losEffectiveElevations(points, elevations, distanceMeters);
  const startElev = elevations[0] + heightA;
  const endElev = elevations[elevations.length - 1] + heightB;
  adjusted[0] = startElev;
  adjusted[adjusted.length - 1] = endElev;
  const maxObstruction = losMaxObstruction(points, adjusted, 0, points.length - 1);
  const blocked = maxObstruction > 0;
  const suggestion = blocked ? findLosSuggestion(points, adjusted) : null;
  const round2 = (value) => Number(value.toFixed(2));
  const profile = points.map((point, idx) => {
    const lineElev = startElev + (endElev - startElev) * point.t;
    return [
      round2(distanceMeters * point.t),
      round2(adjusted[idx]),
      round2(lineElev)
    ];
  });
  return {
    ok: true,
    blocked,
    max_obstruction_m: round2(maxObstruction),
    distance_m: round2(distanceMeters),
    profile,
    peaks: findLosPeaks(points, elevations, distanceMeters),
    suggested: suggestion,
    approximate: elevationResponse.approximate === true,
    rateLimited: elevationResponse.rateLimited === true
  };
}

async function fetchLosServerResult(a, b) {
  const startIndex = Number.isInteger(losActiveSegmentIndex) ? losActiveSegmentIndex : 0;
  const endIndex = startIndex + 1;
  const heightA = getLosPointHeight(startIndex);
  const heightB = getLosPointHeight(endIndex);
  const params = new URLSearchParams({
    lat1: a.lat.toFixed(6),
    lon1: a.lng.toFixed(6),
    lat2: b.lat.toFixed(6),
    lon2: b.lng.toFixed(6),
    h1: heightA.toFixed(2),
    h2: heightB.toFixed(2),
  });
  try {
    const res = await fetch(apiPath(`/los?${params.toString()}`));
    const data = await res.json();
    if (!data.ok) {
      return { ok: false, error: data.error || 'failed' };
    }
    return data;
  } catch (err) {
    return { ok: false, error: 'los_server_failed' };
  }
}

function resetPropagationRaster() {
  if (propagationRaster) {
    propagationLayer.removeLayer(propagationRaster);
    propagationRaster = null;
  }
  propagationRasterCanvas = null;
  propagationRasterMeta = null;
  if (propagationRenderInFlight) {
    propagationComputeToken += 1;
    propagationRenderInFlight = false;
  }
}

function clearPropagation() {
  clearPropagationOrigins();
  resetPropagationRaster();
  propagationBaseRange = null;
  propagationNeedsRender = false;
  propagationRenderInFlight = false;
  propagationComputeToken += 1;
  setPropRange('');
  setPropCost('');
  setPropStatus('');
}

function setPropActive(active) {
  propagationActive = active;
  const btn = document.getElementById('prop-toggle');
  if (btn) {
    btn.classList.toggle('active', active);
    btn.textContent = active ? 'Propagation: select node(s)' : 'Propagation';
  }
  if (propPanel) {
    propPanel.classList.toggle('active', active);
  }
  setPropPanelCollapsed(propPanelCollapsed);
  if (!active) {
    clearPropagation();
  } else {
    setPropStatus('Select a node or click the map to set a transmitter.');
  }
  layoutSidePanels();
}

function keepOverlaysAbovePropagation() {
  if (heatLayer && heatLayer.bringToFront) heatLayer.bringToFront();
  if (historyLayer && historyLayer.bringToFront) historyLayer.bringToFront();
  if (routeLayer && routeLayer.bringToFront) routeLayer.bringToFront();
  if (trailLayer && trailLayer.bringToFront) trailLayer.bringToFront();
  if (markerLayer && markerLayer.bringToFront) markerLayer.bringToFront();
  if (losLayer && losLayer.bringToFront) losLayer.bringToFront();
}

function calcReceiverSensitivityDbm(bwHz, noiseFigureDb, snrMinDb) {
  return -174 + (10 * Math.log10(bwHz)) + noiseFigureDb + snrMinDb;
}

function calcFsplAt1mDb(freqMHz) {
  return 32.44 + (20 * Math.log10(freqMHz)) - 60;
}

function calcMaxPathLossDb(txPowerDbm, sensitivityDbm, fadeMarginDb) {
  return txPowerDbm - sensitivityDbm - fadeMarginDb;
}

function calcRangeMeters(maxPathLossDb, freqMHz, pathLossExponent, clutterLossDb) {
  const n = Math.max(1.5, pathLossExponent);
  const fspl1m = calcFsplAt1mDb(freqMHz);
  const lossBudget = maxPathLossDb - fspl1m - (Number.isFinite(clutterLossDb) ? clutterLossDb : 0);
  const exponent = lossBudget / (10 * n);
  return Math.max(1, Math.pow(10, exponent));
}

function formatDistance(meters) {
  if (!Number.isFinite(meters)) return 'unknown';
  return formatDistanceUnits(meters);
}

function haversineMeters(lat1, lon1, lat2, lon2) {
  const toRad = (deg) => deg * (Math.PI / 180);
  const r = 6371000;
  const dLat = toRad(lat2 - lat1);
  const dLon = toRad(lon2 - lon1);
  const a = Math.sin(dLat / 2) ** 2
    + Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLon / 2) ** 2;
  const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
  return r * c;
}

function parseOptionalNumber(value) {
  if (value == null) return null;
  const trimmed = String(value).trim();
  if (trimmed === '') return null;
  const num = Number(trimmed);
  return Number.isFinite(num) ? num : null;
}

function formatNumber(value) {
  if (!Number.isFinite(value)) return '0';
  return value.toLocaleString(undefined, { maximumFractionDigits: 0 });
}

function isMultiOriginEnabled() {
  const input = document.getElementById('prop-multi-origin');
  return input ? input.checked : false;
}

function getPropagationConfig() {
  const txInput = document.getElementById('prop-txpower');
  const txGainInput = document.getElementById('prop-tx-gain');
  const opacityInput = document.getElementById('prop-opacity');
  const modelSelect = document.getElementById('prop-model');
  const terrainInput = document.getElementById('prop-terrain');
  const txAglInput = document.getElementById('prop-tx-agl');
  const rxAglInput = document.getElementById('prop-rx-agl');
  const txMslInput = document.getElementById('prop-tx-msl');
  const rxMslInput = document.getElementById('prop-rx-msl');
  const minRxInput = document.getElementById('prop-min-rx');
  const autoRangeInput = document.getElementById('prop-auto-range');
  const fadeMarginInput = document.getElementById('prop-fade-margin');
  const webGpuInput = document.getElementById('prop-webgpu');
  const autoResInput = document.getElementById('prop-auto-res');
  const maxCellsInput = document.getElementById('prop-max-cells');
  const gridInput = document.getElementById('prop-grid');
  const sampleInput = document.getElementById('prop-sample');
  const rangeFactorInput = document.getElementById('prop-range-factor');
  if (!txInput || !txGainInput || !opacityInput || !modelSelect || !terrainInput || !txAglInput || !rxAglInput || !txMslInput || !rxMslInput || !minRxInput || !autoRangeInput || !fadeMarginInput || !webGpuInput || !autoResInput || !maxCellsInput || !gridInput || !sampleInput || !rangeFactorInput) {
    return null;
  }
  const txPower = Number(txInput.value);
  const txAntennaGainDb = Number(txGainInput.value);
  const opacity = Number(opacityInput.value);
  const model = PROP_MODELS[modelSelect.value] || PROP_MODELS.suburban;
  const terrain = terrainInput.checked;
  const txAgl = Number(txAglInput.value);
  const rxAgl = Number(rxAglInput.value);
  const txMsl = parseOptionalNumber(txMslInput.value);
  const rxMsl = parseOptionalNumber(rxMslInput.value);
  const minRxDbm = Number(minRxInput.value);
  const autoRange = autoRangeInput.checked;
  const fadeMargin = fadeMarginInput.checked;
  const useWebGpu = webGpuInput.checked && !webGpuInput.disabled;
  const autoResolution = autoResInput.checked;
  const maxCells = Number(maxCellsInput.value);
  const gridStep = Number(gridInput.value);
  const sampleStep = Number(sampleInput.value);
  const rangeFactor = Number(rangeFactorInput.value);
  if (!Number.isFinite(txPower) || !Number.isFinite(opacity)) return null;
  return {
    txPower,
    txAntennaGainDb: Number.isFinite(txAntennaGainDb) ? Math.min(20, Math.max(-10, txAntennaGainDb)) : PROP_DEFAULTS.txAntennaGainDb,
    opacity: Math.min(0.9, Math.max(0.05, opacity)),
    model,
    terrain,
    gridStep: Number.isFinite(gridStep) ? Math.max(30, gridStep) : 90,
    sampleStep: Number.isFinite(sampleStep) ? Math.max(30, sampleStep) : 90,
    rangeFactor: Number.isFinite(rangeFactor) ? Math.min(1, Math.max(0.25, rangeFactor)) : 1,
    txAgl: Number.isFinite(txAgl) ? Math.max(0, txAgl) : 0,
    rxAgl: Number.isFinite(rxAgl) ? Math.max(0, rxAgl) : 0,
    minRxDbm: Number.isFinite(minRxDbm) ? Math.min(-60, Math.max(-150, minRxDbm)) : -97,
    autoRange,
    fadeMargin,
    useWebGpu,
    autoResolution,
    maxCells: Number.isFinite(maxCells) ? Math.min(500000, Math.max(20000, maxCells)) : 120000,
    txMsl,
    rxMsl
  };
}

function estimatePropagationCost(renderRange, gridStep, sampleStep, originCount) {
  const latScale = 111320;
  const refLat = propagationOrigins.length
    ? (propagationOrigins.reduce((sum, origin) => sum + origin.lat, 0) / propagationOrigins.length)
    : map.getCenter().lat;
  const lonScale = 111320 * Math.cos(refLat * (Math.PI / 180));
  const rows = Math.max(1, Math.ceil((renderRange * 2) / gridStep));
  const cols = Math.max(1, Math.ceil((renderRange * 2) / (gridStep * (lonScale / latScale))));
  const cells = rows * cols;
  const avgSamples = Math.max(2, Math.ceil(renderRange / sampleStep) + 1);
  const multiplier = Math.max(1, originCount || 1);
  return {
    cells,
    samples: Math.round(cells * avgSamples * multiplier)
  };
}

function derivePropagationResolution(config, renderRange, originCount) {
  const originFactor = Math.max(1, originCount || 1);
  let gridStep = config.gridStep;
  let sampleStep = config.sampleStep;
  let estimate = estimatePropagationCost(renderRange, gridStep, sampleStep, originFactor);
  if (config.autoResolution && estimate.cells > (config.maxCells / originFactor)) {
    const scale = Math.sqrt(estimate.cells / (config.maxCells / originFactor));
    gridStep = Math.min(600, Math.max(30, Math.round((gridStep * scale) / 5) * 5));
    sampleStep = Math.min(600, Math.max(30, Math.round((sampleStep * scale) / 5) * 5));
    estimate = estimatePropagationCost(renderRange, gridStep, sampleStep, originFactor);
  }
  return {
    gridStep,
    sampleStep,
    cells: estimate.cells,
    samples: estimate.samples
  };
}

function getPropagationOriginKey(origin) {
  return origin.id || origin.key;
}

function clearPropagationOrigins() {
  propagationOrigins = [];
  propagationOriginMarkers.forEach((marker) => {
    propagationLayer.removeLayer(marker);
  });
  propagationOriginMarkers.clear();
}

function removePropagationOrigin(origin) {
  if (!origin) return;
  const key = getPropagationOriginKey(origin);
  if (key && propagationOriginMarkers.has(key)) {
    propagationLayer.removeLayer(propagationOriginMarkers.get(key));
    propagationOriginMarkers.delete(key);
  }
  propagationOrigins = propagationOrigins.filter((item) => getPropagationOriginKey(item) !== key);
  updatePropagationSummary();
  if (!propagationOrigins.length) {
    setPropStatus('Select a node or click the map to set a transmitter.');
  } else {
    markPropagationDirty('Origin removed. Click "Render prop" to update.');
  }
  if (propagationRasterMeta && !propagationNeedsRender) {
    updatePropagationStatusFromRaster();
  }
}

function upsertPropagationOriginMarker(origin) {
  const key = getPropagationOriginKey(origin);
  if (!key) return;
  if (!propagationOriginMarkers.has(key)) {
    const marker = L.circleMarker([origin.lat, origin.lon], {
      radius: 5,
      color: '#22c55e',
      fillColor: '#22c55e',
      fillOpacity: 0.95,
      weight: 2
    }).addTo(propagationLayer);
    marker.on('click', (ev) => {
      if (ev && ev.originalEvent) {
        ev.originalEvent.preventDefault();
        ev.originalEvent.stopPropagation();
      }
      L.DomEvent.stop(ev);
      removePropagationOrigin(origin);
    });
    propagationOriginMarkers.set(key, marker);
  } else {
    const marker = propagationOriginMarkers.get(key);
    marker.setLatLng([origin.lat, origin.lon]);
  }
}

function isNodeCoveredByRaster(lat, lon, meta) {
  if (!meta) return false;
  if (!meta.coverage) return false;
  if (lat < meta.latMin || lat > meta.latMax || lon < meta.lonMin || lon > meta.lonMax) {
    return false;
  }
  const row = Math.floor((meta.latMax - lat) / meta.latStep);
  const col = Math.floor((lon - meta.lonMin) / meta.lonStep);
  if (row < 0 || col < 0 || row >= meta.rows || col >= meta.cols) return false;
  return meta.coverage[(row * meta.cols) + col] > 0;
}

function listLikelyNodesFromRaster() {
  const matches = [];
  if (!propagationOrigins.length) return matches;
  deviceMeta.forEach((meta, id) => {
    if (!meta || meta.lat == null || meta.lon == null) return;
    if (propagationOrigins.some((origin) => origin.id === id)) return;
    if (propagationRasterMeta && isNodeCoveredByRaster(meta.lat, meta.lon, propagationRasterMeta)) {
      let dist = Infinity;
      propagationOrigins.forEach((origin) => {
        const candidate = haversineMeters(origin.lat, origin.lon, meta.lat, meta.lon);
        if (candidate < dist) dist = candidate;
      });
      const label = meta.name ? meta.name : `${id.slice(0, 8)}...`;
      matches.push({ id, label, dist });
    }
  });
  matches.sort((a, b) => a.dist - b.dist);
  return matches;
}

function updatePropagationStatusFromRaster() {
  const likely = listLikelyNodesFromRaster();
  const count = likely.length;
  let status = `Likely to hit ${count} node${count === 1 ? '' : 's'}`;
  if (count > 0) {
    const names = likely.slice(0, 5).map(item => item.label).join(', ');
    status += `: ${names}`;
    if (count > 5) status += ` +${count - 5} more`;
  }
  setPropStatus(status);
}

function updatePropagationSummary() {
  const config = getPropagationConfig();
  if (!config) return;
  const sensitivity = calcReceiverSensitivityDbm(
    PROP_DEFAULTS.bwHz,
    PROP_DEFAULTS.noiseFigureDb,
    PROP_DEFAULTS.snrMinDb
  );
  const effectiveTxPower = config.txPower + config.txAntennaGainDb;
  const maxPathLoss = config.autoRange
    ? (effectiveTxPower - config.minRxDbm)
    : calcMaxPathLossDb(effectiveTxPower, sensitivity, PROP_DEFAULTS.fadeMarginDb);
  const baseRange = calcRangeMeters(maxPathLoss, PROP_DEFAULTS.freqMHz, config.model.n, config.model.clutterLossDb);
  propagationBaseRange = baseRange;
  const renderRange = config.autoRange ? baseRange : (baseRange * config.rangeFactor);
  const clutterNote = config.model.clutterLossDb ? ` +${config.model.clutterLossDb} dB clutter` : '';
  const cutoffNote = config.autoRange ? ` • cutoff ${config.minRxDbm} dBm` : '';
  setPropRange(`Range: ${formatDistance(renderRange)} (base ${formatDistance(baseRange)} • ${config.model.label}${clutterNote}${cutoffNote})`);
  const originCount = propagationOrigins.length;
  const resolution = derivePropagationResolution(config, renderRange, Math.max(1, originCount));
  const resLabel = config.autoResolution ? 'auto ' : '';
  const originLabel = originCount > 1 ? ` • ${originCount} origins` : (originCount === 1 ? ' • 1 origin' : '');
  setPropCost(`Estimate: ${formatNumber(resolution.cells)} cells • ${formatNumber(resolution.samples)} samples (${resLabel}grid ${formatNumber(resolution.gridStep)}m • sample ${formatNumber(resolution.sampleStep)}m${originLabel})`);
}

function markPropagationDirty(message) {
  propagationNeedsRender = true;
  if (message) {
    setPropStatus(message);
  } else if (propagationActive && propagationOrigins.length) {
    setPropStatus('Settings changed. Click "Render prop" to update.');
  }
}

function ensurePropagationWorker() {
  if (propagationWorker) return propagationWorker;
  const workerCode = [
    `const TILE_URL = ${JSON.stringify(PROP_TERRARIUM_URL)};`,
    'const TILE_SIZE = 256;',
    'const tileCache = new Map();',
    'function clamp(value, min, max) { return Math.min(max, Math.max(min, value)); }',
    'function lonLatToTile(lon, lat, zoom) {',
    '  const latRad = lat * Math.PI / 180;',
    '  const n = Math.pow(2, zoom);',
    '  const x = n * ((lon + 180) / 360);',
    '  const y = n * (1 - (Math.log(Math.tan(latRad) + 1 / Math.cos(latRad)) / Math.PI)) / 2;',
    '  const tileX = Math.floor(x);',
    '  const tileY = Math.floor(y);',
    '  const px = Math.floor((x - tileX) * TILE_SIZE);',
    '  const py = Math.floor((y - tileY) * TILE_SIZE);',
    '  return { tileX, tileY, px: clamp(px, 0, TILE_SIZE - 1), py: clamp(py, 0, TILE_SIZE - 1) };',
    '}',
    'async function fetchTile(z, x, y) {',
    '  const n = Math.pow(2, z);',
    '  if (x < 0 || y < 0 || x >= n || y >= n) return null;',
    '  const key = `${z}/${x}/${y}`;',
    '  if (tileCache.has(key)) return tileCache.get(key);',
    '  const url = TILE_URL.replace("{z}", z).replace("{x}", x).replace("{y}", y);',
    '  try {',
    '    const res = await fetch(url);',
    '    if (!res.ok) { tileCache.set(key, null); return null; }',
    '    const blob = await res.blob();',
    '    const bitmap = await createImageBitmap(blob);',
    '    const canvas = new OffscreenCanvas(TILE_SIZE, TILE_SIZE);',
    '    const ctx = canvas.getContext("2d");',
    '    ctx.drawImage(bitmap, 0, 0);',
    '    const data = ctx.getImageData(0, 0, TILE_SIZE, TILE_SIZE).data;',
    '    tileCache.set(key, data);',
    '    return data;',
    '  } catch (err) {',
    '    tileCache.set(key, null);',
    '    return null;',
    '  }',
    '}',
    'async function getElevation(lat, lon, zoom) {',
    '  const coords = lonLatToTile(lon, lat, zoom);',
    '  const tile = await fetchTile(zoom, coords.tileX, coords.tileY);',
    '  if (!tile) return null;',
    '  const idx = (coords.py * TILE_SIZE + coords.px) * 4;',
    '  const r = tile[idx];',
    '  const g = tile[idx + 1];',
    '  const b = tile[idx + 2];',
    '  return (r * 256 + g + b / 256) - 32768;',
    '}',
    'function knifeEdgeLossFromV(v) {',
    '  if (!Number.isFinite(v) || v <= 0) return 0;',
    '  const loss = 6.9 + 20 * Math.log10(Math.sqrt((v - 0.1) ** 2 + 1) + v - 0.1);',
    '  return Math.max(0, loss);',
    '}',
    'self.onmessage = async (event) => {',
    '  const data = event.data;',
    '  if (!data || data.type !== "render") return;',
    '  const { token, origins, config, renderRange, maxPathLossDb, fspl1mDb, freqMHz } = data;',
    '  try {',
    '    if (!Array.isArray(origins) || origins.length === 0) {',
    '      throw new Error("No origins provided");',
    '    }',
    '  const latScale = 111320;',
    '  const refLat = origins.reduce((sum, o) => sum + o.lat, 0) / origins.length;',
    '  const lonScale = 111320 * Math.cos(refLat * Math.PI / 180);',
    '  const latStep = config.gridStep / latScale;',
    '  const lonStep = config.gridStep / lonScale;',
    '  let latMin = Infinity;',
    '  let latMax = -Infinity;',
    '  let lonMin = Infinity;',
    '  let lonMax = -Infinity;',
    '  for (const origin of origins) {',
    '    const originLonScale = 111320 * Math.cos(origin.lat * Math.PI / 180);',
    '    const latRadius = renderRange / latScale;',
    '    const lonRadius = renderRange / originLonScale;',
    '    latMin = Math.min(latMin, origin.lat - latRadius);',
    '    latMax = Math.max(latMax, origin.lat + latRadius);',
    '    lonMin = Math.min(lonMin, origin.lon - lonRadius);',
    '    lonMax = Math.max(lonMax, origin.lon + lonRadius);',
    '  }',
    '  const rows = Math.max(1, Math.ceil((latMax - latMin) / latStep));',
    '  const cols = Math.max(1, Math.ceil((lonMax - lonMin) / lonStep));',
    '  const zoom = clamp(Math.round(Math.log2(156543.03392 * Math.cos(refLat * Math.PI / 180) / config.gridStep)), 8, 12);',
    '  const lambda = 299792458 / (freqMHz * 1e6);',
    '  const clutterLossDb = Number.isFinite(config.clutterLossDb) ? config.clutterLossDb : 0;',
    '  const originEntries = [];',
    '  for (const origin of origins) {',
    '    const originGround = config.useTerrain && config.txMsl == null ? await getElevation(origin.lat, origin.lon, zoom) : 0;',
    '    const txAbs = (config.txMsl != null) ? config.txMsl : (originGround ?? 0) + config.txAgl;',
    '    originEntries.push({',
    '      lat: origin.lat,',
    '      lon: origin.lon,',
    '      lonScale: 111320 * Math.cos(origin.lat * Math.PI / 180),',
    '      txAbs',
    '    });',
    '  }',
    '  const pixels = new Uint8ClampedArray(rows * cols * 4);',
    '  const coverage = new Uint8Array(rows * cols);',
    '  for (let row = 0; row < rows; row++) {',
    '    const lat = latMax - row * latStep;',
    '    for (let col = 0; col < cols; col++) {',
    '      const lon = lonMin + col * lonStep;',
    '      const idx = row * cols + col;',
    '      const offset = idx * 4;',
    '      let bestMargin = -Infinity;',
    '      let coverCount = 0;',
    '      let endGround = null;',
    '      if (config.useTerrain) {',
    '        endGround = await getElevation(lat, lon, zoom);',
    '        if (endGround == null) {',
    '          pixels[offset + 3] = 0;',
    '          continue;',
    '        }',
    '      }',
    '      for (const origin of originEntries) {',
    '        const dx = (lon - origin.lon) * origin.lonScale;',
    '        const dy = (lat - origin.lat) * latScale;',
    '        const distance = Math.sqrt(dx * dx + dy * dy);',
    '        if (distance <= 1 || distance > renderRange) {',
    '          continue;',
    '        }',
    '        let rxAbs = (config.rxMsl != null) ? config.rxMsl : (config.useTerrain ? endGround + config.rxAgl : origin.txAbs);',
    '        let maxV = 0;',
    '        let minClearanceRatio = Infinity;',
    '        if (config.useTerrain) {',
    '          const samples = Math.max(2, Math.ceil(distance / config.sampleStep) + 1);',
    '          for (let i = 1; i < samples - 1; i++) {',
    '            const t = i / (samples - 1);',
    '            const sLat = origin.lat + (lat - origin.lat) * t;',
    '            const sLon = origin.lon + (lon - origin.lon) * t;',
    '            const elev = await getElevation(sLat, sLon, zoom);',
    '            if (elev == null) continue;',
    '            const lineElev = origin.txAbs + (rxAbs - origin.txAbs) * t;',
    '            const d1 = distance * t;',
    '            const d2 = distance * (1 - t);',
    '            const f1 = Math.sqrt((lambda * d1 * d2) / (d1 + d2));',
    '            const bulge = (d1 * d2) / (2 * config.earthRadiusM);',
    '            const effectiveElev = elev + bulge;',
    '            let fresnel = 0;',
    '            if (config.fresnelFactor > 0) {',
    '              fresnel = config.fresnelFactor * f1;',
    '            }',
    '            const clearance = lineElev - effectiveElev;',
    '            if (f1 > 0) {',
    '              const ratio = clearance / f1;',
    '              if (ratio < minClearanceRatio) minClearanceRatio = ratio;',
    '            }',
    '            const obstruction = (effectiveElev - lineElev) - fresnel;',
    '            if (obstruction <= 0) continue;',
    '            const v = obstruction * Math.sqrt((2 * (d1 + d2)) / (lambda * d1 * d2));',
    '            if (v > maxV) maxV = v;',
    '          }',
    '        }',
    '        const extraLoss = maxV > 0 ? knifeEdgeLossFromV(maxV) : 0;',
    '        let clearanceLoss = 0;',
    '        if (config.useTerrain && Number.isFinite(minClearanceRatio) && minClearanceRatio < config.clearanceRatio) {',
    '          const ratio = Math.max(-1, minClearanceRatio);',
    '          const deficit = config.clearanceRatio - ratio;',
    '          clearanceLoss = Math.min(config.clearanceLossDb, (deficit / config.clearanceRatio) * config.clearanceLossDb);',
    '        }',
    '        const pathLoss = fspl1mDb + (10 * config.pathLossExp * Math.log10(distance)) + extraLoss + clearanceLoss + clutterLossDb;',
    '        const margin = maxPathLossDb - pathLoss;',
    '        if (margin > 0) {',
    '          coverCount += 1;',
    '          if (margin > bestMargin) bestMargin = margin;',
    '        }',
    '      }',
    '      if (coverCount > 0) {',
    '        const requiredOverlap = originEntries.length >= 3 ? originEntries.length : 2;',
    '        const strength = Math.min(1, bestMargin / 20);',
    '        if (coverCount >= requiredOverlap) {',
    '          pixels[offset] = 34;',
    '          pixels[offset + 1] = 197;',
    '          pixels[offset + 2] = 94;',
    '        } else {',
    '          pixels[offset] = 239;',
    '          pixels[offset + 1] = 68;',
    '          pixels[offset + 2] = 68;',
    '        }',
    '        pixels[offset + 3] = config.fadeByMargin ? Math.round(255 * strength) : 255;',
    '        coverage[idx] = Math.min(255, coverCount);',
    '      } else {',
    '        pixels[offset + 3] = 0;',
    '      }',
    '    }',
    '    if (row % 10 === 0) {',
    '      self.postMessage({ type: "progress", token, row, rows });',
    '      await new Promise((resolve) => setTimeout(resolve, 0));',
    '    }',
    '  }',
    '    self.postMessage({',
    '      type: "result",',
    '      token,',
    '      width: cols,',
    '      height: rows,',
    '      bounds: { latMin, latMax, lonMin, lonMax },',
    '      latStep,',
    '      lonStep,',
    '      pixels: pixels.buffer,',
    '      coverage: coverage.buffer',
    '    }, [pixels.buffer, coverage.buffer]);',
    '  } catch (err) {',
    '    const message = (err && err.message) ? err.message : String(err);',
    '    self.postMessage({ type: "error", token, error: message });',
    '  }',
    '};'
  ].join('\n');

  const blob = new Blob([workerCode], { type: 'text/javascript' });
  propagationWorker = new Worker(URL.createObjectURL(blob));
  propagationWorker.onmessage = (event) => {
    const msg = event.data;
    if (!msg || msg.token !== propagationComputeToken) return;
    if (msg.type === 'progress') {
      const pct = Math.round((msg.row / Math.max(1, msg.rows)) * 100);
      setPropStatus(`Rendering: ${pct}%`);
      return;
    }
    if (msg.type === 'result') {
      const pixels = new Uint8ClampedArray(msg.pixels);
      const coverage = new Uint8Array(msg.coverage);
      const canvas = document.createElement('canvas');
      canvas.width = msg.width;
      canvas.height = msg.height;
      const ctx = canvas.getContext('2d');
      const imageData = new ImageData(pixels, msg.width, msg.height);
      ctx.putImageData(imageData, 0, 0);
      propagationRasterCanvas = canvas;
      const dataUrl = canvas.toDataURL('image/png');
      const bounds = [
        [msg.bounds.latMin, msg.bounds.lonMin],
        [msg.bounds.latMax, msg.bounds.lonMax]
      ];
      if (!propagationRaster) {
        propagationRaster = L.imageOverlay(dataUrl, bounds, { opacity: propagationLastConfig?.opacity ?? 0.2 }).addTo(propagationLayer);
      } else {
        propagationRaster.setUrl(dataUrl);
        propagationRaster.setBounds(bounds);
      }
      if (propagationRaster && propagationLastConfig) {
        propagationRaster.setOpacity(propagationLastConfig.opacity);
      }
      keepOverlaysAbovePropagation();
      propagationRasterMeta = {
        latMin: msg.bounds.latMin,
        latMax: msg.bounds.latMax,
        lonMin: msg.bounds.lonMin,
        lonMax: msg.bounds.lonMax,
        latStep: msg.latStep,
        lonStep: msg.lonStep,
        rows: msg.height,
        cols: msg.width,
        coverage
      };
      propagationRenderInFlight = false;
      propagationNeedsRender = false;
      if (propagationOrigins.length) {
        updatePropagationStatusFromRaster();
      }
      return;
    }
    if (msg.type === 'error') {
      setPropStatus(`Render failed: ${msg.error || 'unknown error'}`);
      propagationRenderInFlight = false;
    }
  };
  return propagationWorker;
}

async function ensurePropagationGpu() {
  if (propagationGpu) return propagationGpu;
  if (!navigator.gpu) return null;
  if (propagationGpuInitPromise) return propagationGpuInitPromise;
  propagationGpuInitPromise = (async () => {
    try {
      const adapter = await navigator.gpu.requestAdapter();
      if (!adapter) return null;
      const device = await adapter.requestDevice();
      const module = device.createShaderModule({
        code: `
struct Params {
  latMin: f32,
  latMax: f32,
  lonMin: f32,
  lonMax: f32,
  latStep: f32,
  lonStep: f32,
  latScale: f32,
  renderRange: f32,
  fspl1mDb: f32,
  maxPathLossDb: f32,
  pathLossExp: f32,
  clutterLossDb: f32,
  fadeByMargin: f32,
  originCount: f32,
  rows: f32,
  cols: f32,
};

struct Origin {
  lat: f32,
  lon: f32,
  lonScale: f32,
  _pad: f32,
};

@group(0) @binding(0) var<uniform> params: Params;
@group(0) @binding(1) var<storage, read> origins: array<Origin>;
@group(0) @binding(2) var<storage, read_write> outPixels: array<u32>;
@group(0) @binding(3) var<storage, read_write> outCoverage: array<u32>;

fn log10(x: f32) -> f32 {
  return log2(x) / 3.321928;
}

@compute @workgroup_size(8, 8)
fn main(@builtin(global_invocation_id) gid: vec3<u32>) {
  let row = gid.y;
  let col = gid.x;
  let rows = u32(params.rows + 0.5);
  let cols = u32(params.cols + 0.5);
  if (row >= rows || col >= cols) {
    return;
  }
  let lat = params.latMax - f32(row) * params.latStep;
  let lon = params.lonMin + f32(col) * params.lonStep;
  var bestMargin = -1e9;
  var coverCount: u32 = 0u;
  let originCount = u32(params.originCount + 0.5);
  for (var i: u32 = 0u; i < originCount; i = i + 1u) {
    let origin = origins[i];
    let dx = (lon - origin.lon) * origin.lonScale;
    let dy = (lat - origin.lat) * params.latScale;
    let distance = sqrt(dx * dx + dy * dy);
    if (distance <= 1.0 || distance > params.renderRange) {
      continue;
    }
    let pathLoss = params.fspl1mDb + 10.0 * params.pathLossExp * log10(distance) + params.clutterLossDb;
    let margin = params.maxPathLossDb - pathLoss;
    if (margin > 0.0) {
      coverCount = coverCount + 1u;
      if (margin > bestMargin) {
        bestMargin = margin;
      }
    }
  }
  let idx = (row * cols + col) * 4u;
  if (coverCount > 0u) {
    let strength = clamp(bestMargin / 20.0, 0.0, 1.0);
    var required: u32 = 2u;
    if (originCount >= 3u) {
      required = originCount;
    }
    if (coverCount >= required) {
      outPixels[idx] = 34u;
      outPixels[idx + 1u] = 197u;
      outPixels[idx + 2u] = 94u;
    } else {
      outPixels[idx] = 239u;
      outPixels[idx + 1u] = 68u;
      outPixels[idx + 2u] = 68u;
    }
    var alpha = 255.0;
    if (params.fadeByMargin > 0.5) {
      alpha = 255.0 * strength;
    }
    outPixels[idx + 3u] = u32(alpha);
    outCoverage[row * cols + col] = coverCount;
  } else {
    outPixels[idx + 3u] = 0u;
    outCoverage[row * cols + col] = 0u;
  }
}
            `
      });
      const pipeline = device.createComputePipeline({
        layout: 'auto',
        compute: { module, entryPoint: 'main' }
      });
      propagationGpu = { device, pipeline };
      return propagationGpu;
    } catch (err) {
      propagationGpu = null;
      return null;
    } finally {
      propagationGpuInitPromise = null;
    }
  })();
  return propagationGpuInitPromise;
}

async function renderPropagationRasterWebGpu({
  token,
  origins,
  config,
  renderRange,
  maxPathLossDb,
  resolution
}) {
  try {
    const gpu = await ensurePropagationGpu();
    if (!gpu) return false;
    const { device, pipeline } = gpu;
    const latScale = 111320;
    const refLat = origins.reduce((sum, origin) => sum + origin.lat, 0) / origins.length;
    const lonScale = 111320 * Math.cos(refLat * (Math.PI / 180));
    const latStep = resolution.gridStep / latScale;
    const lonStep = resolution.gridStep / lonScale;
    let latMin = Infinity;
    let latMax = -Infinity;
    let lonMin = Infinity;
    let lonMax = -Infinity;
    origins.forEach((origin) => {
      const originLonScale = 111320 * Math.cos(origin.lat * (Math.PI / 180));
      const latRadius = renderRange / latScale;
      const lonRadius = renderRange / originLonScale;
      latMin = Math.min(latMin, origin.lat - latRadius);
      latMax = Math.max(latMax, origin.lat + latRadius);
      lonMin = Math.min(lonMin, origin.lon - lonRadius);
      lonMax = Math.max(lonMax, origin.lon + lonRadius);
    });
    const rows = Math.max(1, Math.ceil((latMax - latMin) / latStep));
    const cols = Math.max(1, Math.ceil((lonMax - lonMin) / lonStep));
    const cellCount = rows * cols;
    const params = new Float32Array([
      latMin,
      latMax,
      lonMin,
      lonMax,
      latStep,
      lonStep,
      latScale,
      renderRange,
      calcFsplAt1mDb(PROP_DEFAULTS.freqMHz),
      maxPathLossDb,
      config.model.n,
      config.model.clutterLossDb,
      config.fadeMargin ? 1 : 0,
      origins.length,
      rows,
      cols
    ]);
    const originData = new Float32Array(origins.length * 4);
    origins.forEach((origin, idx) => {
      const offset = idx * 4;
      originData[offset] = origin.lat;
      originData[offset + 1] = origin.lon;
      originData[offset + 2] = 111320 * Math.cos(origin.lat * (Math.PI / 180));
      originData[offset + 3] = 0;
    });
    const paramsBuffer = device.createBuffer({
      size: params.byteLength,
      usage: GPUBufferUsage.UNIFORM | GPUBufferUsage.COPY_DST
    });
    device.queue.writeBuffer(paramsBuffer, 0, params);
    const originsBuffer = device.createBuffer({
      size: originData.byteLength,
      usage: GPUBufferUsage.STORAGE | GPUBufferUsage.COPY_DST
    });
    device.queue.writeBuffer(originsBuffer, 0, originData);
    const pixelBufferSize = cellCount * 4 * 4;
    const coverageBufferSize = cellCount * 4;
    const pixelBuffer = device.createBuffer({
      size: pixelBufferSize,
      usage: GPUBufferUsage.STORAGE | GPUBufferUsage.COPY_SRC
    });
    const coverageBuffer = device.createBuffer({
      size: coverageBufferSize,
      usage: GPUBufferUsage.STORAGE | GPUBufferUsage.COPY_SRC
    });
    const pixelReadBuffer = device.createBuffer({
      size: pixelBufferSize,
      usage: GPUBufferUsage.MAP_READ | GPUBufferUsage.COPY_DST
    });
    const coverageReadBuffer = device.createBuffer({
      size: coverageBufferSize,
      usage: GPUBufferUsage.MAP_READ | GPUBufferUsage.COPY_DST
    });
    const bindGroup = device.createBindGroup({
      layout: pipeline.getBindGroupLayout(0),
      entries: [
        { binding: 0, resource: { buffer: paramsBuffer } },
        { binding: 1, resource: { buffer: originsBuffer } },
        { binding: 2, resource: { buffer: pixelBuffer } },
        { binding: 3, resource: { buffer: coverageBuffer } }
      ]
    });
    const encoder = device.createCommandEncoder();
    const pass = encoder.beginComputePass();
    pass.setPipeline(pipeline);
    pass.setBindGroup(0, bindGroup);
    pass.dispatchWorkgroups(Math.ceil(cols / 8), Math.ceil(rows / 8));
    pass.end();
    encoder.copyBufferToBuffer(pixelBuffer, 0, pixelReadBuffer, 0, pixelBufferSize);
    encoder.copyBufferToBuffer(coverageBuffer, 0, coverageReadBuffer, 0, coverageBufferSize);
    device.queue.submit([encoder.finish()]);
    await device.queue.onSubmittedWorkDone();
    if (token !== propagationComputeToken) return true;
    await pixelReadBuffer.mapAsync(GPUMapMode.READ);
    await coverageReadBuffer.mapAsync(GPUMapMode.READ);
    const pixelCopy = pixelReadBuffer.getMappedRange();
    const coverageCopy = coverageReadBuffer.getMappedRange();
    const pixelU32 = new Uint32Array(pixelCopy);
    const coverageU32 = new Uint32Array(coverageCopy);
    const pixels = new Uint8ClampedArray(pixelU32.length);
    for (let i = 0; i < pixelU32.length; i++) {
      pixels[i] = pixelU32[i];
    }
    const coverage = new Uint8Array(coverageU32.length);
    for (let i = 0; i < coverageU32.length; i++) {
      coverage[i] = Math.min(255, coverageU32[i]);
    }
    pixelReadBuffer.unmap();
    coverageReadBuffer.unmap();
    if (token !== propagationComputeToken) return true;
    const canvas = document.createElement('canvas');
    canvas.width = cols;
    canvas.height = rows;
    const ctx = canvas.getContext('2d');
    const imageData = new ImageData(pixels, cols, rows);
    ctx.putImageData(imageData, 0, 0);
    propagationRasterCanvas = canvas;
    const dataUrl = canvas.toDataURL('image/png');
    const bounds = [
      [latMin, lonMin],
      [latMax, lonMax]
    ];
    if (!propagationRaster) {
      propagationRaster = L.imageOverlay(dataUrl, bounds, { opacity: propagationLastConfig?.opacity ?? 0.2 }).addTo(propagationLayer);
    } else {
      propagationRaster.setUrl(dataUrl);
      propagationRaster.setBounds(bounds);
    }
    if (propagationRaster && propagationLastConfig) {
      propagationRaster.setOpacity(propagationLastConfig.opacity);
    }
    keepOverlaysAbovePropagation();
    propagationRasterMeta = {
      latMin,
      latMax,
      lonMin,
      lonMax,
      latStep,
      lonStep,
      rows,
      cols,
      coverage
    };
    propagationRenderInFlight = false;
    propagationNeedsRender = false;
    if (propagationOrigins.length) {
      updatePropagationStatusFromRaster();
    }
    return true;
  } catch (err) {
    return false;
  }
}

async function renderPropagationRaster() {
  if (!propagationActive) return;
  const config = getPropagationConfig();
  if (!config) return;
  if (!propagationOrigins.length) {
    setPropStatus('Select a node or click the map to set a transmitter.');
    return;
  }
  if (propagationRenderInFlight) {
    setPropStatus('Render already in progress.');
    return;
  }
  resetPropagationRaster();
  const sensitivity = calcReceiverSensitivityDbm(
    PROP_DEFAULTS.bwHz,
    PROP_DEFAULTS.noiseFigureDb,
    PROP_DEFAULTS.snrMinDb
  );
  const effectiveTxPower = config.txPower + config.txAntennaGainDb;
  const maxPathLoss = config.autoRange
    ? (effectiveTxPower - config.minRxDbm)
    : calcMaxPathLossDb(effectiveTxPower, sensitivity, PROP_DEFAULTS.fadeMarginDb);
  const baseRange = calcRangeMeters(maxPathLoss, PROP_DEFAULTS.freqMHz, config.model.n, config.model.clutterLossDb);
  propagationBaseRange = baseRange;
  const renderRange = config.autoRange ? baseRange : (baseRange * config.rangeFactor);
  const originCount = propagationOrigins.length;
  const resolution = derivePropagationResolution(config, renderRange, originCount);
  propagationLastConfig = config;
  propagationOrigins.forEach((origin) => upsertPropagationOriginMarker(origin));
  updatePropagationSummary();
  propagationComputeToken += 1;
  propagationRenderInFlight = true;
  const token = propagationComputeToken;
  const origins = propagationOrigins.map((origin) => ({ lat: origin.lat, lon: origin.lon }));
  if (config.useWebGpu && !config.terrain) {
    setPropStatus('Rendering (WebGPU): 0%');
    const ok = await renderPropagationRasterWebGpu({
      token,
      origins,
      config,
      renderRange,
      maxPathLossDb: maxPathLoss,
      resolution
    });
    if (ok) return;
    if (token === propagationComputeToken) {
      setPropStatus('WebGPU unavailable. Falling back to CPU...');
    }
  } else if (config.useWebGpu && config.terrain) {
    setPropStatus('WebGPU experimental only supports terrain off. Using CPU...');
  } else {
    setPropStatus('Rendering: 0%');
  }
  ensurePropagationWorker();
  propagationWorker.postMessage({
    type: 'render',
    token,
    origins,
    renderRange,
    maxPathLossDb: maxPathLoss,
    fspl1mDb: calcFsplAt1mDb(PROP_DEFAULTS.freqMHz),
    freqMHz: PROP_DEFAULTS.freqMHz,
    config: {
      gridStep: resolution.gridStep,
      sampleStep: resolution.sampleStep,
      pathLossExp: config.model.n,
      clutterLossDb: config.model.clutterLossDb,
      useTerrain: config.terrain,
      fresnelFactor: PROP_DEFAULTS.fresnelFactor,
      clearanceRatio: PROP_DEFAULTS.clearanceRatio,
      clearanceLossDb: PROP_DEFAULTS.clearanceLossDb,
      earthRadiusM: PROP_DEFAULTS.earthRadiusM,
      txAgl: config.txAgl,
      rxAgl: config.rxAgl,
      txMsl: config.txMsl,
      rxMsl: config.rxMsl,
      fadeByMargin: config.fadeMargin
    }
  });
}

function setPropagationOrigin(latlng, id = null) {
  if (!latlng) return;
  const meta = id ? deviceMeta.get(id) : null;
  const lat = latlng.lat;
  const lon = latlng.lng ?? latlng.lon;
  const multi = isMultiOriginEnabled();
  if (!multi) {
    clearPropagationOrigins();
  }
  let origin = null;
  if (id) {
    origin = propagationOrigins.find(item => item.id === id) || null;
  }
  if (!origin && multi && !id) {
    origin = propagationOrigins.find(item => item.lat === lat && item.lon === lon) || null;
  }
  if (!origin) {
    origin = {
      lat,
      lon,
      id,
      key: id ? null : `manual-${Date.now()}-${propagationOriginSeq += 1}`,
      name: meta ? meta.name : null
    };
    propagationOrigins.push(origin);
  } else {
    origin.lat = lat;
    origin.lon = lon;
    origin.name = meta ? meta.name : origin.name;
  }
  upsertPropagationOriginMarker(origin);
  updatePropagationSummary();
  const label = propagationOrigins.length === 1 ? 'Origin set.' : `${propagationOrigins.length} origins set.`;
  markPropagationDirty(`${label} Click "Render prop" to calculate coverage.`);
}

function formatLastContact(tsSeconds) {
  if (!tsSeconds) return 'unknown';
  const dt = new Date(tsSeconds * 1000);
  return dt.toLocaleString(undefined, {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: 'numeric',
    minute: '2-digit',
    second: '2-digit',
    hour12: true
  });
}

function payloadTypeLabel(pt) {
  const val = Number(pt);
  if (val === 4) return 'Advert';
  if (val === 8 || val === 9) return 'Trace';
  if (val === 2 || val === 5) return 'Message';
  return Number.isFinite(val) ? `Type ${val}` : 'Unknown';
}

function shortHash(hash) {
  if (!hash) return 'unknown';
  const text = String(hash);
  return text.length > 10 ? `${text.slice(0, 10)}…` : text;
}

function deviceLabelFromId(id) {
  if (!id) return 'Unknown';
  const d = deviceData.get(id);
  if (d) return deviceDisplayName(d);
  return `${String(id).slice(0, 8)}…`;
}

function makeHistoryPopup(entry) {
  const count = Number(entry && entry.count) || 1;
  const lastSeen = entry && entry.lastTs ? formatLastContact(entry.lastTs) : 'unknown';
  const rawSamples = entry && Array.isArray(entry.recent) ? entry.recent : [];
  const samples = rawSamples.filter((sample) => (
    sample && (
      sample.message_hash || sample.origin_id || sample.receiver_id || sample.payload_type || sample.topic
    )
  )).slice(0, 3);
  const sampleHtml = samples.length
    ? samples.map((sample) => {
      const when = sample.ts ? formatLastContact(sample.ts) : 'unknown';
      const label = payloadTypeLabel(sample.payload_type);
      const origin = deviceLabelFromId(sample.origin_id);
      const receiver = deviceLabelFromId(sample.receiver_id);
      const routeMode = sample.route_mode ? String(sample.route_mode) : 'path';
      const byteWidths = Array.isArray(sample.route_byte_widths) && sample.route_byte_widths.length
        ? sample.route_byte_widths.map(width => `${width}-byte`).join(', ')
        : 'unknown';
      return `
            <div class="popup-sample">
              <strong>${escapeHtml(label)}</strong> • ${escapeHtml(when)}<br/>
              Origin: ${escapeHtml(origin)}<br/>
              Receiver: ${escapeHtml(receiver)}<br/>
              Route: ${escapeHtml(routeMode)}<br/>
              Bytes: ${escapeHtml(byteWidths)}<br/>
              Hash: ${escapeHtml(shortHash(sample.message_hash))}
            </div>
          `;
    }).join('')
    : '<div class="popup-sample">No packet details yet.</div>';

  return `
        <span class="popup-title">History edge</span>
        <span class="small">
          Count: ${escapeHtml(count)}<br/>
          Last Seen: ${escapeHtml(lastSeen)}<br/>
          ${sampleHtml}
        </span>
      `;
}

function haversineMeters(lat1, lon1, lat2, lon2) {
  const R = 6371000;
  const toRad = (deg) => (deg * Math.PI) / 180;
  const dLat = toRad(lat2 - lat1);
  const dLon = toRad(lon2 - lon1);
  const a = Math.sin(dLat / 2) ** 2 +
    Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) *
    Math.sin(dLon / 2) ** 2;
  return 2 * R * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}

function trailDistanceKm(a, b) {
  if (!Array.isArray(a) || !Array.isArray(b) || a.length < 2 || b.length < 2) {
    return 0;
  }
  const lat1 = Number(a[0]);
  const lon1 = Number(a[1]);
  const lat2 = Number(b[0]);
  const lon2 = Number(b[1]);
  if (![lat1, lon1, lat2, lon2].every(Number.isFinite)) return 0;
  return haversineMeters(lat1, lon1, lat2, lon2) / 1000;
}

function splitTrailPoints(trail) {
  const points = Array.isArray(trail)
    ? trail
      .map(p => [Number(p[0]), Number(p[1])])
      .filter(p => Number.isFinite(p[0]) && Number.isFinite(p[1]))
    : [];
  if (points.length < 2 || trailMaxSegmentKm <= 0) return points;
  const segments = [];
  let segment = [points[0]];
  for (let idx = 1; idx < points.length; idx += 1) {
    const point = points[idx];
    const previous = points[idx - 1];
    if (trailDistanceKm(previous, point) > trailMaxSegmentKm) {
      if (segment.length >= 2) segments.push(segment);
      segment = [point];
    } else {
      segment.push(point);
    }
  }
  if (segment.length >= 2) segments.push(segment);
  return segments;
}

function sampleLosPoints(lat1, lon1, lat2, lon2) {
  const distance = haversineMeters(lat1, lon1, lat2, lon2);
  if (distance <= 0) {
    return [
      { lat: lat1, lon: lon1, t: 0 },
      { lat: lat2, lon: lon2, t: 1 }
    ];
  }
  let samples = Math.floor(distance / Math.max(1, losSampleStepMeters)) + 1;
  samples = Math.max(losSampleMin, Math.min(losSampleMax, samples));
  if (samples < 2) samples = 2;
  const points = [];
  for (let i = 0; i < samples; i += 1) {
    const t = i / (samples - 1);
    const lat = lat1 + (lat2 - lat1) * t;
    const lon = lon1 + (lon2 - lon1) * t;
    points.push({ lat, lon, t });
  }
  return points;
}

function losElevationCacheKey(lat, lon, precision = LOS_ELEVATION_CACHE_PRECISION) {
  const safeLat = Number(lat);
  const safeLon = Number(lon);
  if (!Number.isFinite(safeLat) || !Number.isFinite(safeLon)) return null;
  return `${safeLat.toFixed(precision)},${safeLon.toFixed(precision)}`;
}

function cacheLosElevation(key, value, now) {
  if (!key || !Number.isFinite(value)) return;
  losElevationCache.set(key, { value, ts: now });
  if (losElevationCache.size <= LOS_ELEVATION_CACHE_MAX) return;
  const excess = losElevationCache.size - LOS_ELEVATION_CACHE_MAX;
  const keys = losElevationCache.keys();
  for (let i = 0; i < excess; i += 1) {
    const next = keys.next();
    if (next.done) break;
    losElevationCache.delete(next.value);
  }
}

function approximateElevationsFromLast(count) {
  if (!losLastElevations || losLastElevations.length < 2) return null;
  const source = losLastElevations;
  const srcCount = source.length;
  const target = new Array(count);
  if (srcCount === count) {
    for (let i = 0; i < count; i += 1) {
      target[i] = source[i];
    }
    return target;
  }
  if (count === 1) {
    target[0] = source[0];
    return target;
  }
  for (let i = 0; i < count; i += 1) {
    const t = i / (count - 1);
    const pos = t * (srcCount - 1);
    const idx = Math.floor(pos);
    const frac = pos - idx;
    const a = source[idx];
    const b = source[Math.min(srcCount - 1, idx + 1)];
    target[i] = a + (b - a) * frac;
  }
  return target;
}

function flatElevations(count) {
  if (count <= 0) return [];
  const values = new Array(count);
  for (let i = 0; i < count; i += 1) {
    values[i] = 0;
  }
  return values;
}

function getCachedElevation(lat, lon, now, allowNeighbor = false) {
  const key = losElevationCacheKey(lat, lon);
  if (key) {
    const cached = losElevationCache.get(key);
    if (cached) {
      if (now - cached.ts <= LOS_ELEVATION_CACHE_TTL_MS) {
        return { value: cached.value, key };
      }
      losElevationCache.delete(key);
    }
  }
  if (!allowNeighbor) return null;
  let best = null;
  for (let dx = -1; dx <= 1; dx += 1) {
    for (let dy = -1; dy <= 1; dy += 1) {
      if (dx === 0 && dy === 0) continue;
      const nLat = Number(lat) + dx * LOS_ELEVATION_CACHE_STEP;
      const nLon = Number(lon) + dy * LOS_ELEVATION_CACHE_STEP;
      const nKey = losElevationCacheKey(nLat, nLon);
      if (!nKey) continue;
      const cached = losElevationCache.get(nKey);
      if (!cached) continue;
      if (now - cached.ts > LOS_ELEVATION_CACHE_TTL_MS) {
        losElevationCache.delete(nKey);
        continue;
      }
      const dist = Math.abs(dx) + Math.abs(dy);
      if (!best || dist < best.dist) {
        best = { value: cached.value, key: nKey, dist };
      }
    }
  }
  return best ? { value: best.value, key: best.key } : null;
}

function interpolateElevations(values) {
  const count = values.length;
  let lastKnown = null;
  for (let i = 0; i < count; i += 1) {
    if (!Number.isFinite(values[i])) continue;
    if (lastKnown != null && i - lastKnown > 1) {
      const startVal = values[lastKnown];
      const endVal = values[i];
      const span = i - lastKnown;
      for (let j = lastKnown + 1; j < i; j += 1) {
        const t = (j - lastKnown) / span;
        values[j] = startVal + (endVal - startVal) * t;
      }
    }
    lastKnown = i;
  }
  if (lastKnown == null) return false;
  // Fill leading/trailing gaps with nearest known value.
  let firstKnown = values.findIndex(val => Number.isFinite(val));
  if (firstKnown > 0) {
    for (let i = 0; i < firstKnown; i += 1) {
      values[i] = values[firstKnown];
    }
  }
  if (lastKnown < count - 1) {
    for (let i = lastKnown + 1; i < count; i += 1) {
      values[i] = values[lastKnown];
    }
  }
  return true;
}

async function fetchElevations(points, options = {}) {
  if (!losElevationFetchUrl) {
    return { ok: false, error: 'no_elevation_url' };
  }
  const allowNetwork = options.allowNetwork !== false;
  const allowApprox = options.allowApprox === true;
  const forceNetwork = options.forceNetwork === true;
  const now = Date.now();
  const results = new Array(points.length);
  const missing = [];
  points.forEach((point, idx) => {
    const cached = getCachedElevation(point.lat, point.lon, now, allowApprox);
    if (!cached) {
      missing.push({ idx, point, key: null });
      return;
    }
    results[idx] = cached.value;
    missing.push({ idx, point, key: cached.key, missing: false });
  });
  const unresolved = missing.filter(entry => entry.missing !== false && entry.key === null);
  if (!unresolved.length) {
    return { ok: true, elevations: results };
  }
  if (!allowNetwork) {
    const ok = interpolateElevations(results);
    if (!ok) {
      const fallback = allowApprox ? approximateElevationsFromLast(points.length) : null;
      if (fallback) {
        return { ok: true, elevations: fallback, approximate: true, fallback: true };
      }
      if (allowApprox) {
        return { ok: true, elevations: flatElevations(points.length), approximate: true, fallback: true };
      }
      return { ok: false, error: 'elevation_cache_miss' };
    }
    return { ok: true, elevations: results, approximate: true };
  }
  if (!forceNetwork) {
    if (now < losElevationBackoffUntil) {
      const ok = interpolateElevations(results);
      if (ok) {
        return { ok: true, elevations: results, approximate: true, rateLimited: true };
      }
      const fallback = allowApprox ? approximateElevationsFromLast(points.length) : null;
      if (fallback) {
        return { ok: true, elevations: fallback, approximate: true, rateLimited: true, fallback: true };
      }
      if (allowApprox) {
        return { ok: true, elevations: flatElevations(points.length), approximate: true, rateLimited: true, fallback: true };
      }
      return { ok: false, error: 'elevation_rate_limited', rateLimited: true };
    }
    if (now - losElevationLastFetchMs < LOS_ELEVATION_FETCH_MIN_MS) {
      const ok = interpolateElevations(results);
      if (ok) {
        return { ok: true, elevations: results, approximate: true, rateLimited: true };
      }
      const fallback = allowApprox ? approximateElevationsFromLast(points.length) : null;
      if (fallback) {
        return { ok: true, elevations: fallback, approximate: true, rateLimited: true, fallback: true };
      }
      if (allowApprox) {
        return { ok: true, elevations: flatElevations(points.length), approximate: true, rateLimited: true, fallback: true };
      }
      return { ok: false, error: 'elevation_rate_limited', rateLimited: true };
    }
  }
  losElevationLastFetchMs = now;
  const chunkSize = 100;
  const fetchTargets = unresolved;
  for (let start = 0; start < fetchTargets.length; start += chunkSize) {
    const chunk = fetchTargets.slice(start, start + chunkSize);
    const locations = chunk.map(entry => `${entry.point.lat},${entry.point.lon}`).join('|');
    const url = new URL(losElevationFetchUrl, window.location.origin);
    url.searchParams.set('locations', locations);
    let payload;
    try {
      const res = await fetch(url.toString());
      if (res.status === 429) {
        losElevationBackoffUntil = Date.now() + LOS_ELEVATION_BACKOFF_MS;
        const ok = interpolateElevations(results);
        if (ok) {
          return { ok: true, elevations: results, approximate: true, rateLimited: true };
        }
        const fallback = allowApprox ? approximateElevationsFromLast(points.length) : null;
        if (fallback) {
          return { ok: true, elevations: fallback, approximate: true, rateLimited: true, fallback: true };
        }
        if (allowApprox) {
          return { ok: true, elevations: flatElevations(points.length), approximate: true, rateLimited: true, fallback: true };
        }
        return { ok: false, error: 'elevation_rate_limited', rateLimited: true };
      }
      payload = await res.json();
    } catch (err) {
      return { ok: false, error: 'elevation_fetch_failed' };
    }
    if (payload.status && payload.status !== 'OK') {
      return { ok: false, error: `elevation_fetch_failed:${payload.status}` };
    }
    const elevs = payload.results || [];
    if (elevs.length !== chunk.length) {
      return { ok: false, error: 'elevation_fetch_failed:unexpected_length' };
    }
    elevs.forEach((entry, idx) => {
      const elev = Number(entry.elevation);
      const target = chunk[idx];
      results[target.idx] = elev;
      const key = target.key || losElevationCacheKey(target.point.lat, target.point.lon);
      cacheLosElevation(key, elev, now);
    });
  }
  if (results.some(val => val == null || Number.isNaN(val))) {
    return { ok: false, error: 'elevation_fetch_failed:missing' };
  }
  return { ok: true, elevations: results };
}

function losMaxObstruction(points, elevations, startIdx, endIdx) {
  if (endIdx <= startIdx + 1) return 0;
  const startT = points[startIdx].t;
  const endT = points[endIdx].t;
  if (endT <= startT) return 0;
  const startElev = elevations[startIdx];
  const endElev = elevations[endIdx];
  let maxObstruction = 0;
  for (let idx = startIdx + 1; idx < endIdx; idx += 1) {
    const frac = (points[idx].t - startT) / (endT - startT);
    const lineElev = startElev + (endElev - startElev) * frac;
    const clearance = elevations[idx] - lineElev;
    if (clearance > maxObstruction) maxObstruction = clearance;
  }
  return maxObstruction;
}

function losEarthRadiusMeters() {
  return 6371000 * losCurvatureFactor;
}

function losEarthBulgeMeters(distanceMeters, t) {
  if (!losCurvatureEnabled || !(distanceMeters > 0)) return 0;
  const d1 = distanceMeters * t;
  const d2 = distanceMeters - d1;
  const earthRadiusMeters = losEarthRadiusMeters();
  if (!(earthRadiusMeters > 0)) return 0;
  return (d1 * d2) / (2 * earthRadiusMeters);
}

function losEffectiveElevations(points, elevations, distanceMeters) {
  return elevations.map((elev, idx) =>
    elev + losEarthBulgeMeters(distanceMeters, points[idx]?.t || 0)
  );
}

function findLosSuggestion(points, elevations) {
  if (points.length < 3) return null;
  let bestIdx = null;
  let bestScore = null;
  let bestClear = false;
  for (let idx = 1; idx < points.length - 1; idx += 1) {
    const obstA = losMaxObstruction(points, elevations, 0, idx);
    const obstB = losMaxObstruction(points, elevations, idx, points.length - 1);
    const score = Math.max(obstA, obstB);
    const clear = score <= 0;
    if (clear && !bestClear) {
      bestIdx = idx;
      bestScore = score;
      bestClear = true;
    } else if (clear && bestClear) {
      if (elevations[idx] > elevations[bestIdx]) {
        bestIdx = idx;
        bestScore = score;
      }
    } else if (!bestClear) {
      if (bestScore == null || score < bestScore) {
        bestIdx = idx;
        bestScore = score;
      }
    }
  }
  if (bestIdx == null) return null;
  return {
    lat: Number(points[bestIdx].lat.toFixed(6)),
    lon: Number(points[bestIdx].lon.toFixed(6)),
    elevation_m: Number(elevations[bestIdx].toFixed(2)),
    clear: bestClear,
    max_obstruction_m: bestScore != null ? Number(bestScore.toFixed(2)) : null
  };
}

function findLosPeaks(points, elevations, distanceMeters) {
  if (points.length < 3) return [];
  const peakIndices = [];
  for (let i = 1; i < elevations.length - 1; i += 1) {
    const elev = elevations[i];
    if (elev >= elevations[i - 1] && elev >= elevations[i + 1]) {
      peakIndices.push(i);
    }
  }
  if (peakIndices.length === 0) {
    let maxIdx = 1;
    for (let i = 2; i < elevations.length - 1; i += 1) {
      if (elevations[i] > elevations[maxIdx]) maxIdx = i;
    }
    peakIndices.push(maxIdx);
  }
  const limited = peakIndices
    .sort((a, b) => elevations[b] - elevations[a])
    .slice(0, losPeaksMax)
    .sort((a, b) => points[a].t - points[b].t);
  return limited.map((idx, i) => ({
    index: i + 1,
    lat: Number(points[idx].lat.toFixed(6)),
    lon: Number(points[idx].lon.toFixed(6)),
    elevation_m: Number(elevations[idx].toFixed(2)),
    distance_m: Number((distanceMeters * points[idx].t).toFixed(2))
  }));
}

function makePopup(d) {
  const lastContact = formatLastContact(getLastSeenTs(d));
  const deviceLabel = deviceShortId(d);
  const qrTitle = (d.name || '').trim() || deviceLabel;
  const publicKey = typeof d.device_id === 'string' ? d.device_id : '';
  const latText = Number(d.lat).toFixed(6);
  const lonText = Number(d.lon).toFixed(6);
  const locationText = `Location: ${latText}, ${lonText}`;
  const publicKeyCopyTitle = 'Copy full public key';
  const qrParams = new URLSearchParams({
    name: qrTitle,
    public_key: publicKey,
    type: String(meshCoreContactTypeForDevice(d)),
    box_size: '14',
    border: '4'
  });
  const qrCodeUrl = publicKey ? withToken(`/qr?${qrParams.toString()}`) : '';
  const popupId = publicKey
    ? `<button
        type="button"
        class="popup-id popup-copy-id popup-copy-trigger"
        data-copy-text="${escapeHtmlAttr(publicKey)}"
        title="${escapeHtmlAttr(publicKeyCopyTitle)}"
      >${escapeHtml(deviceLabel)}</button>`
    : `<span class="popup-id">${escapeHtml(deviceLabel)}</span>`;
  const title = d.name
    ? `<span class="popup-title">${escapeHtml(d.name)}</span>${popupId}`
    : `<span class="popup-title">${popupId}</span>`;
  const role = resolveRole(d);
  const roleLabel = role === 'unknown' ? '' : role.charAt(0).toUpperCase() + role.slice(1);
  const mqttOnline = isMqttOnline(d);
  const popupActions = [];
  if (qrCodeButtonEnabled && qrCodeUrl) {
    popupActions.push(`
      <button
        type="button"
        class="popup-action-button"
        data-qr-url="${escapeHtmlAttr(qrCodeUrl)}"
        data-qr-title="${escapeHtmlAttr(qrTitle)}"
        data-qr-key="${escapeHtmlAttr(publicKey)}"
      >Generate QR Code</button>
    `);
  }
  if (publicKey) {
    const linkLabel = role === 'repeater' ? 'Copy repeater link' : 'Copy node link';
    popupActions.push(`
      <button
        type="button"
        class="popup-action-button"
        data-node-link-id="${escapeHtmlAttr(publicKey)}"
      >${escapeHtml(linkLabel)}</button>
    `);
  }
  return `
        ${title}
        <span class="small">
          ${roleLabel ? `Role: ${escapeHtml(roleLabel)}<br/>` : ``}
          <button
            type="button"
            class="popup-copy-location popup-copy-trigger"
            data-copy-text="${escapeHtmlAttr(locationText)}"
            title="Copy location"
          >${escapeHtml(locationText)}</button><br/>
          Last Contact: ${escapeHtml(lastContact)}<br/>
          ${mqttOnline ? `MQTT: Online<br/>` : ``}
          ${d.rssi != null ? `RSSI: ${escapeHtml(d.rssi)}<br/>` : ``}
          ${d.snr != null ? `SNR: ${escapeHtml(d.snr)}<br/>` : ``}
          ${popupActions.length ? `<div class="popup-actions">${popupActions.join('')}</div>` : ``}
        </span>
      `;
}

async function copyPopupText(ev) {
  const btn = ev?.currentTarget;
  if (!btn) return;
  const text = typeof btn.dataset.copyText === 'string' ? btn.dataset.copyText : '';
  if (!text) return;
  let copied = false;
  try {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      await navigator.clipboard.writeText(text);
      copied = true;
    }
  } catch (_err) {
    copied = false;
  }
  const original = btn.textContent || text;
  btn.textContent = copied ? 'Copied' : text;
  window.setTimeout(() => {
    btn.textContent = original;
  }, 1200);
}

function closeQrModal() {
  if (!qrModal) return;
  qrModal.hidden = true;
  if (qrModalImage) {
    qrModalImage.removeAttribute('src');
  }
  if (qrModalTitle) {
    qrModalTitle.textContent = 'Node';
  }
  if (qrModalLabel) {
    qrModalLabel.textContent = '';
    qrModalLabel.hidden = true;
    delete qrModalLabel.dataset.copyText;
    qrModalLabel.removeAttribute('title');
  }
}

function openQrModal(url, title, key) {
  if (!qrModal || !qrModalImage) return;
  qrModalImage.src = url;
  qrModalImage.alt = title ? `QR code for ${title}` : 'QR code';
  if (qrModalTitle) {
    qrModalTitle.textContent = title || 'Node';
  }
  if (qrModalLabel) {
    qrModalLabel.textContent = key ? `${key.slice(0, 8)}…` : '';
    qrModalLabel.hidden = !key;
    if (key) {
      qrModalLabel.dataset.copyText = key;
      qrModalLabel.title = 'Copy full public key';
    } else {
      delete qrModalLabel.dataset.copyText;
      qrModalLabel.removeAttribute('title');
    }
  }
  qrModal.hidden = false;
}

function handleQrPopupClick(ev) {
  const btn = ev?.currentTarget;
  const url = btn?.dataset?.qrUrl;
  if (!url) return;
  ev.preventDefault();
  ev.stopPropagation();
  openQrModal(
    url,
    btn.dataset.qrTitle || '',
    btn.dataset.qrKey || ''
  );
}

function upsertDevice(d, trail) {
  const id = d.device_id;
  const latlng = [d.lat, d.lon];
  const visibleOnMap = shouldShowDeviceOnMap(d);
  const role = resolveRole(d);
  const style = markerStyleForDevice(d);
  deviceData.set(id, d);
  deviceMeta.set(id, { lat: d.lat, lon: d.lon, name: d.name });

  // marker
  if (!markers.has(id)) {
    const m = L.circleMarker(latlng, { ...style, renderer: vectorRenderer });
    m.bindPopup(makePopup(d), {
      maxWidth: 260,
      maxHeight: 320,
      autoPan: false,
      keepInView: false
    });
    const bindPopupActions = () => {
      const root = m.getPopup()?.getElement?.();
      if (!root) return;
      root.querySelectorAll('.popup-copy-trigger').forEach((btn) => {
        if (btn.dataset.boundClick === 'true') return;
        btn.dataset.boundClick = 'true';
        btn.addEventListener('click', copyPopupText);
      });
      root.querySelectorAll('.popup-action-button[data-qr-url]').forEach((btn) => {
        if (btn.dataset.boundQr === 'true') return;
        btn.dataset.boundQr = 'true';
        btn.addEventListener('click', handleQrPopupClick);
      });
      root.querySelectorAll('.popup-action-button[data-node-link-id]').forEach((btn) => {
        if (btn.dataset.boundNodeLink === 'true') return;
        btn.dataset.boundNodeLink = 'true';
        btn.addEventListener('click', copyNodeLink);
      });
    };
    m.on('popupopen', bindPopupActions);
    // Live updates replace popup buttons without reopening the popup.
    m.getPopup().on('contentupdate', bindPopupActions);
    m.__suppressClick = false;
    m.__longPressTimer = null;
    m.__longPressFired = false;
    const triggerLosSelect = () => {
      if (!losActive) {
        return;
      }
      handleLosPoint(m.getLatLng());
      m.closePopup();
    };
    const cancelLongPress = () => {
      if (m.__longPressTimer) {
        clearTimeout(m.__longPressTimer);
        m.__longPressTimer = null;
      }
    };
    m.on('click', (ev) => {
      if (m.__suppressClick) {
        m.__suppressClick = false;
        return;
      }
      const original = ev.originalEvent;
      if (original && original.shiftKey) {
        triggerLosSelect();
        original.preventDefault();
        original.stopPropagation();
        L.DomEvent.stop(ev);
        return;
      }
      if (peersActive) {
        selectPeerNode(id);
        m.openPopup();
        if (original) {
          original.preventDefault();
          original.stopPropagation();
        }
        L.DomEvent.stop(ev);
        return;
      }
      if (propagationActive) {
        setPropagationOrigin(m.getLatLng(), id);
        m.openPopup();
        if (original) {
          original.preventDefault();
          original.stopPropagation();
        }
        L.DomEvent.stop(ev);
      }
    });
    m.on('contextmenu', (ev) => {
      m.__suppressClick = true;
      triggerLosSelect();
      if (ev && ev.originalEvent) {
        ev.originalEvent.preventDefault();
        ev.originalEvent.stopPropagation();
      }
      L.DomEvent.stop(ev);
    });
    m.on('touchstart', (ev) => {
      m.__longPressFired = false;
      cancelLongPress();
      m.__longPressTimer = setTimeout(() => {
        m.__longPressFired = true;
        m.__suppressClick = true;
        triggerLosSelect();
      }, 550);
      if (ev && ev.originalEvent) {
        ev.originalEvent.preventDefault();
        ev.originalEvent.stopPropagation();
      }
      L.DomEvent.stop(ev);
    });
    m.on('touchmove', () => {
      cancelLongPress();
    });
    m.on('touchend', (ev) => {
      cancelLongPress();
      if (m.__longPressFired) {
        if (ev && ev.originalEvent) {
          ev.originalEvent.preventDefault();
          ev.originalEvent.stopPropagation();
        }
        L.DomEvent.stop(ev);
      }
    });
    m.on('touchcancel', () => {
      cancelLongPress();
      m.__longPressFired = false;
    });
    markers.set(id, m);
    updateMarkerLabel(m, d);
    syncLayerMembership(markerLayer, m, visibleOnMap);
  } else {
    const m = markers.get(id);
    m.setLatLng(latlng);
    m.setPopupContent(makePopup(d));
    if (m.setStyle) m.setStyle(style);
    updateMarkerLabel(m, d);
    syncLayerMembership(markerLayer, m, visibleOnMap);
  }

  // trail polyline (skip companions)
  if (role !== 'companion' && Array.isArray(trail) && trail.length >= 2) {
    const points = splitTrailPoints(trail);
    if (!Array.isArray(points) || points.length < 1) {
      if (polylines.has(id)) {
        trailLayer.removeLayer(polylines.get(id));
        polylines.get(id).__attached = false;
        polylines.delete(id);
      }
    } else if (!polylines.has(id)) {
      const pl = L.polyline(points, {
        renderer: animatedLineRenderer,
        color: '#38bdf8',
        weight: 3,
        opacity: 0.85,
        className: 'trail-animated'
      });
      polylines.set(id, pl);
      syncLayerMembership(trailLayer, pl, visibleOnMap);
    } else {
      const pl = polylines.get(id);
      pl.setLatLngs(points);
      if (pl.setStyle) {
        pl.setStyle({ color: '#38bdf8', weight: 3, opacity: 0.85 });
      }
      syncLayerMembership(trailLayer, pl, visibleOnMap);
    }
  } else if (polylines.has(id)) {
    trailLayer.removeLayer(polylines.get(id));
    polylines.get(id).__attached = false;
    polylines.delete(id);
  }

  refreshStats();
  if (propagationActive && propagationOrigins.length) {
    const origin = propagationOrigins.find(item => item.id === id);
    if (origin) {
      origin.lat = d.lat;
      origin.lon = d.lon;
      origin.name = d.name || origin.name;
      upsertPropagationOriginMarker(origin);
      updatePropagationSummary();
      markPropagationDirty('Origin moved. Click "Render prop" to update.');
      return;
    }
    if (propagationRasterMeta && !propagationNeedsRender) {
      updatePropagationStatusFromRaster();
    }
  }
}

function removeDevices(ids) {
  ids.forEach(id => {
    if (markers.has(id)) {
      markerLayer.removeLayer(markers.get(id));
      markers.delete(id);
    }
    if (deviceData.has(id)) {
      deviceData.delete(id);
    }
    if (polylines.has(id)) {
      trailLayer.removeLayer(polylines.get(id));
      polylines.delete(id);
    }
    deviceMeta.delete(id);
  });
  refreshStats();
  refreshOnlineMarkers();
  if (propagationActive && propagationOrigins.length) {
    const removed = propagationOrigins.filter(origin => origin.id && ids.includes(origin.id));
    if (removed.length) {
      removed.forEach((origin) => {
        const key = getPropagationOriginKey(origin);
        if (key && propagationOriginMarkers.has(key)) {
          propagationLayer.removeLayer(propagationOriginMarkers.get(key));
          propagationOriginMarkers.delete(key);
        }
      });
      propagationOrigins = propagationOrigins.filter(origin => !(origin.id && ids.includes(origin.id)));
      updatePropagationSummary();
      if (!propagationOrigins.length) {
        setPropStatus('Select a node or click the map to set a transmitter.');
      } else {
        markPropagationDirty('Origin removed. Click "Render prop" to update.');
      }
    } else {
      if (propagationRasterMeta && !propagationNeedsRender) {
        updatePropagationStatusFromRaster();
      }
    }
  }
}

function refreshOnlineMarkers() {
  markers.forEach((m, id) => {
    const d = deviceData.get(id);
    if (!d) return;
    const style = markerStyleForDevice(d);
    if (m.setStyle) m.setStyle(style);
    if (m.getPopup()) m.setPopupContent(makePopup(d));
  });
  refreshViewportLayers();
  refreshStats();
}

function refreshViewportLayers() {
  for (const [id, marker] of markers.entries()) {
    const d = deviceData.get(id);
    syncLayerMembership(markerLayer, marker, shouldShowDeviceOnMap(d));
  }
  for (const [id, line] of polylines.entries()) {
    const d = deviceData.get(id);
    syncLayerMembership(trailLayer, line, shouldShowDeviceOnMap(d));
  }
  if (coverageVisible && coverageData) {
    if (coverageProvider === 'meshmapper' && meshMapperCoverageSource === coverageData && meshMapperCoverageRects.length) {
      syncMeshMapperCoverageViewport();
    } else {
      renderCoverage(coverageData);
    }
  }
}

function clearRouteDisplay() {
  routeLines.forEach((entry, routeId) => {
    if (entry.timeout) clearTimeout(entry.timeout);
    removeArcadeMarker(routeId);
    routeLayer.removeLayer(entry.line);
  });
  routeLines.clear();
  clearAllHopMarkers();
  hideRouteDetailsPanel();
  stopArcadeLoop();
}

function removeRoutes(ids) {
  ids.forEach(id => {
    const entry = routeLines.get(id);
    if (entry) {
      if (entry.timeout) clearTimeout(entry.timeout);
      removeArcadeMarker(id);
      routeLayer.removeLayer(entry.line);
      routeLines.delete(id);
    }
    routeCache.delete(id);
    clearHopMarkersForRoute(id);
    if (activeRouteDetailsId === id) {
      hideRouteDetailsPanel();
    }
  });
  refreshStats();
}

function clearRoutes() {
  clearRouteDisplay();
  routeCache.clear();
  refreshStats();
}

function clearHistoryLayer() {
  historyLines.forEach(entry => {
    if (!entry || !entry.line) return;
    historyLayer.removeLayer(entry.line);
  });
  historyLines.clear();
  refreshHistoryStyles();
  refreshStats();
}

function removeHistoryEdges(ids) {
  ids.forEach(id => {
    const entry = historyLines.get(id);
    if (!entry) return;
    historyLayer.removeLayer(entry.line);
    historyLines.delete(id);
    historyCache.delete(id);
  });
  refreshHistoryStyles();
  refreshStats();
}

function historyWeight(count) {
  const n = Math.max(1, Number(count) || 1);
  const base = Math.min(6, 0.9 + Math.log1p(n) * 1.1);
  return clampNumber(base * historyLinkScale, 0.4, 12);
}

function computeHistoryThresholds() {
  const counts = [];
  historyCache.forEach(edge => {
    const count = historyDisplayCount(edge);
    if (count > 0) {
      counts.push(count);
    }
  });
  if (!counts.length) {
    return { p70: null, p90: null };
  }
  counts.sort((a, b) => a - b);
  const pick = (pct) => {
    const idx = Math.max(0, Math.min(counts.length - 1, Math.floor(pct * (counts.length - 1))));
    return counts[idx];
  };
  const min = counts[0];
  const max = counts[counts.length - 1];
  let p70 = pick(0.7);
  let p90 = pick(0.9);
  if (p70 <= min) p70 = min + 1;
  if (p90 <= p70) p90 = p70 + 1;
  if (p70 > max) {
    p70 = max + 1;
    p90 = max + 2;
  } else if (p90 > max) {
    p90 = max + 1;
  }
  return { p70, p90 };
}

function historyColor(count, thresholds) {
  if (!thresholds || thresholds.p90 == null || thresholds.p70 == null) {
    return '#7dd3fc';
  }
  if (count >= thresholds.p90) return '#ef4444';
  if (count >= thresholds.p70) return '#f59e0b';
  return '#7dd3fc';
}

function historyBand(count, thresholds) {
  if (!thresholds || thresholds.p90 == null || thresholds.p70 == null) {
    return 'cool';
  }
  if (count >= thresholds.p90) return 'hot';
  if (count >= thresholds.p70) return 'warm';
  return 'cool';
}

function historyFilterAllows(count, thresholds) {
  if (historyFilterMode === 0) return true;
  const band = historyBand(count, thresholds);
  if (historyFilterMode === 1) return band === 'cool';
  if (historyFilterMode === 2) return band === 'warm';
  if (historyFilterMode === 3) return band === 'warm' || band === 'hot';
  if (historyFilterMode === 4) return band === 'hot';
  return true;
}

function historyByteFilterWidth() {
  if (historyByteFilter.has('all')) return null;
  return ['1b', '2b', '3b']
    .filter((value) => historyByteFilter.has(value))
    .map((value) => value.slice(0, 1));
}

function historyDisplayCount(edge) {
  if (!edge) return 0;
  const widths = historyByteFilterWidth();
  if (!widths) return Number(edge.count) || 0;
  const counts = edge.byte_counts;
  if (!counts || typeof counts !== 'object') return 0;
  return widths.reduce((total, width) => total + (Number(counts[width]) || 0), 0);
}

function updateHistoryFilterLabel() {
  if (!historyFilterLabel) return;
  let text = 'All links';
  if (historyFilterMode === 1) text = 'Blue links only';
  if (historyFilterMode === 2) text = 'Yellow links only';
  if (historyFilterMode === 3) text = 'Yellow + Red links';
  if (historyFilterMode === 4) text = 'Red links only';
  historyFilterLabel.textContent = text;
}

function updateHistoryRendering() {
  if (!historyVisible || !nodesVisible) return;
  const thresholds = computeHistoryThresholds();
  historyLines.forEach(entry => {
    if (!entry || !entry.line) return;
    const count = historyDisplayCount(entry);
    const shouldShow = count > 0 && historyFilterAllows(count, thresholds);
    entry.line.setStyle({
      color: historyColor(count, thresholds),
      weight: shouldShow ? historyWeight(count) : 0.1,
      opacity: shouldShow ? 0.6 : 0.0,
      lineCap: 'round',
      lineJoin: 'round'
    });
    entry.hidden = !shouldShow;
  });
}

function refreshHistoryStyles() {
  updateHistoryRendering();
}

function updateHistoryFilter(mode) {
  historyFilterMode = Number(mode);
  if (![0, 1, 2, 3, 4].includes(historyFilterMode)) {
    historyFilterMode = 0;
  }
  localStorage.setItem('meshmapHistoryFilter', String(historyFilterMode));
  updateHistoryFilterLabel();
  if (historyVisible && nodesVisible) {
    updateHistoryRendering();
  }
}

function updateHistoryByteFilter(value) {
  historyByteFilter = normalizeByteFilterSet(value);
  localStorage.setItem('meshmapHistoryByteFilter', serializeByteFilterSet(historyByteFilter));
  setByteFilterChecks(historyByteFilterSelect, historyByteFilter);
  if (historyVisible && nodesVisible) {
    updateHistoryRendering();
  }
  refreshStats();
}

function updateHistoryLinkScale(next) {
  const value = Number(next);
  if (!Number.isFinite(value)) return;
  historyLinkScale = clampNumber(sliderToHistoryScale(value), HISTORY_LINK_MIN, HISTORY_LINK_MAX);
  localStorage.setItem('meshmapHistoryLinkScale', String(historyLinkScale));
  updateHistoryLinkSizeUI();
  if (historyVisible && nodesVisible) {
    updateHistoryRendering();
  }
}

function historyEdgeId(edge) {
  if (!edge) return null;
  if (edge.id) return edge.id;
  if (Array.isArray(edge.a) && Array.isArray(edge.b)) {
    return `${edge.a.join(',')}-${edge.b.join(',')}`;
  }
  return null;
}

function renderHistoryEdge(edge) {
  if (!edge || !Array.isArray(edge.a) || !Array.isArray(edge.b)) return;
  const id = historyEdgeId(edge);
  if (!id) return;
  const points = [
    [edge.a[0], edge.a[1]],
    [edge.b[0], edge.b[1]]
  ];
  let entry = historyLines.get(id);
  if (!entry) {
    const line = L.polyline(points, { renderer: vectorRenderer, color: '#7dd3fc', weight: 2, opacity: 0.6 }).addTo(historyLayer);
    entry = { line, count: Number(edge.count) || 1, recent: [], lastTs: null, byte_counts: {} };
    historyLines.set(id, entry);
    line.on('click', (ev) => {
      const popup = makeHistoryPopup(entry);
      line.bindPopup(popup, {
        maxWidth: 300,
        autoPan: true,
        keepInView: true,
        autoPanPadding: [18, 18]
      }).openPopup(ev.latlng);
    });
  } else {
    entry.line.setLatLngs(points);
    entry.count = Number(edge.count) || entry.count || 1;
  }
  entry.recent = Array.isArray(edge.recent) ? edge.recent : [];
  entry.lastTs = edge.last_ts || entry.lastTs;
  entry.byte_counts = edge.byte_counts && typeof edge.byte_counts === 'object'
    ? edge.byte_counts
    : {};
  refreshHistoryStyles();
}

function renderHistoryFromCache() {
  if (!routeHistoryEnabled) return;
  historyCache.forEach(edge => renderHistoryEdge(edge));
  updateHistoryRendering();
  refreshStats();
}

function upsertHistoryEdge(edge) {
  if (!routeHistoryEnabled) return;
  const id = historyEdgeId(edge);
  if (!id) return;
  const edgeData = { ...edge, id };
  historyCache.set(id, edgeData);
  if (!historyVisible || !nodesVisible) {
    refreshStats();
    return;
  }
  renderHistoryEdge(edgeData);
}

function updateHistoryWindowLabel(seconds) {
  if (!routeHistoryEnabled) return;
  const targets = [historyLabel, historyPanelLabel].filter(Boolean);
  if (!targets.length) return;
  let text = 'History';
  if (seconds && seconds > 0) {
    const hours = seconds / 3600;
    if (hours >= 24) {
      text = `History (${Math.round(hours)}h)`;
    } else if (hours >= 1) {
      text = `History (${Math.round(hours * 10) / 10}h)`;
    } else {
      text = `History (${Math.max(1, Math.round(seconds / 60))}m)`;
    }
  }
  targets.forEach(el => {
    el.textContent = text;
  });
}

function refreshHeatLayer() {
  if (!heatLayer) return;
  const now = Date.now();
  const cutoff = now - HEAT_TTL_MS;
  const filtered = heatPoints.filter(p => p.ts >= cutoff);
  heatPoints.length = 0;
  heatPoints.push(...filtered);
  if (!heatVisible || !map.hasLayer(heatLayer)) {
    return;
  }
  heatLayer.setLatLngs(heatPoints.map(p => [p.lat, p.lon, p.weight]));
}

function addHeatPoints(points, tsSeconds, payloadType) {
  if (!heatLayer) return;
  if (!Array.isArray(points) || points.length < 1) return;
  const ts = (tsSeconds ? tsSeconds * 1000 : Date.now());
  points.forEach(p => {
    heatPoints.push({ lat: p[0], lon: p[1], ts, weight: 0.7 });
  });
  refreshHeatLayer();
}

function seedHeat(items) {
  if (!heatLayer) return;
  if (!Array.isArray(items)) return;
  heatPoints.length = 0;
  items.forEach(item => {
    if (!Array.isArray(item) || item.length < 3) return;
    heatPoints.push({
      lat: item[0],
      lon: item[1],
      ts: item[2] * 1000,
      weight: item[3] != null ? item[3] : 0.7
    });
  });
  refreshHeatLayer();
}

function computeRouteDistanceMeters(points) {
  if (!Array.isArray(points) || points.length < 2) return 0;
  let total = 0;
  for (let i = 1; i < points.length; i += 1) {
    const prev = points[i - 1];
    const next = points[i];
    if (!Array.isArray(prev) || !Array.isArray(next)) continue;
    const [plat, plon] = prev;
    const [nlat, nlon] = next;
    if (!Number.isFinite(plat) || !Number.isFinite(plon) || !Number.isFinite(nlat) || !Number.isFinite(nlon)) {
      continue;
    }
    total += haversineMeters(plat, plon, nlat, nlon);
  }
  return total;
}

function formatSecondsLabel(seconds) {
  if (!Number.isFinite(seconds)) return 'unknown';
  if (seconds <= 0) return 'expired';
  if (seconds < 60) return `${Math.round(seconds)}s`;
  const minutes = seconds / 60;
  if (minutes < 60) return `${Math.round(minutes)}m`;
  const hours = minutes / 60;
  if (hours < 24) return `${Math.round(hours)}h`;
  const days = hours / 24;
  return `${Math.round(days)}d`;
}

function formatTimestampLabel(tsSeconds) {
  if (!Number.isFinite(tsSeconds)) return 'unknown';
  try {
    return new Date(tsSeconds * 1000).toLocaleString();
  } catch (err) {
    return 'unknown';
  }
}

function normalizeHopHashPrefix(hash) {
  if (!hash) return null;
  const text = String(hash).trim();
  if (!text) return null;
  const raw = text.toLowerCase().startsWith('0x') ? text.slice(2) : text;
  if (!raw) return null;
  let normalized = raw.replace(/\s+/g, '');
  if (!normalized) return null;
  if (!/^[0-9a-fA-F]+$/.test(normalized)) return null;
  if (normalized.length % 2 === 1) {
    normalized = `0${normalized}`;
  }
  if (normalized.length !== 2 && normalized.length !== 4 && normalized.length !== 6) {
    return null;
  }
  return normalized.toUpperCase();
}

function hopPrefixIdLabel(hash) {
  const normalized = normalizeHopHashPrefix(hash);
  if (!normalized) return null;
  return normalized;
}

function hopPrefixDetailLabel(hash) {
  const normalized = normalizeHopHashPrefix(hash);
  if (!normalized) return null;
  const displayPrefix = hopPrefixIdLabel(normalized);
  const bits = displayPrefix.length * 4;
  const decVal = Number.parseInt(displayPrefix, 16);
  if (Number.isFinite(decVal)) {
    if (normalized.length === 2) {
      return `${displayPrefix} (${bits}-bit, ${decVal}, from legacy ${normalized})`;
    }
    return `${displayPrefix} (${bits}-bit, ${decVal})`;
  }
  return displayPrefix;
}


function pointIdNodePrefix(pointId, hopHash = null, fallbackByteWidth = null) {
  if (!pointId) return null;
  const rawPoint = String(pointId).trim();
  if (!/^[0-9a-fA-F]+$/.test(rawPoint)) return null;
  const normalizedPoint = rawPoint.toUpperCase();
  const normalizedHop = normalizeHopHashPrefix(hopHash);
  if (normalizedHop && normalizedPoint.startsWith(normalizedHop)) {
    return normalizedHop;
  }
  const fallbackChars = Number.isFinite(fallbackByteWidth) && fallbackByteWidth > 0
    ? Math.max(2, Math.min(6, Math.round(fallbackByteWidth) * 2))
    : 2;
  return normalizedPoint.slice(0, fallbackChars) || null;
}

function pointIdNodePrefixDetail(pointId, hopHash = null, fallbackByteWidth = null) {
  const prefix = pointIdNodePrefix(pointId, hopHash, fallbackByteWidth);
  if (!prefix) return null;
  const bits = prefix.length * 4;
  const decVal = Number.parseInt(prefix, 16);
  if (Number.isFinite(decVal)) {
    return `${prefix} (${bits}-bit, ${decVal})`;
  }
  return prefix;
}

function pointIdRoleLabel(pointId) {
  if (!pointId) return null;
  const device = deviceData.get(pointId);
  if (!device) return null;
  const role = resolveRole(device);
  if (!role || role === 'unknown') return null;
  return role.charAt(0).toUpperCase() + role.slice(1);
}

function buildRouteDetailsDisplayPoints(route, pointIds) {
  if (!route || !Array.isArray(route.points)) return [];
  const rows = route.points.map((pt, idx) => ({
    coords: pt,
    route_index: idx,
    point_id: pointIds ? pointIds[idx] || null : null,
    endpoint_only: false,
    endpoint_kind: null
  }));

  const senderName = typeof route.sender_name === 'string' ? route.sender_name.trim() : '';
  if (senderName) {
    rows.unshift({
      coords: null,
      route_index: null,
      point_id: null,
      point_label: senderName,
      role_label: 'Companion',
      endpoint_only: true,
      endpoint_kind: 'sender_name'
    });
  }

  const maybeAddCompanionEndpoint = (deviceId, kind) => {
    if (!deviceId) return;
    if (pointIds && pointIds.includes(deviceId)) return;
    const device = deviceData.get(deviceId);
    if (!device || resolveRole(device) !== 'companion') return;
    const lat = Number(device.lat);
    const lon = Number(device.lon);
    const coords = Number.isFinite(lat) && Number.isFinite(lon) ? [lat, lon] : null;
    const row = {
      coords,
      route_index: null,
      point_id: deviceId,
      endpoint_only: true,
      endpoint_kind: kind
    };
    if (kind === 'origin') {
      rows.unshift(row);
    } else {
      rows.push(row);
    }
  };

  maybeAddCompanionEndpoint(route.origin_id, 'origin');
  maybeAddCompanionEndpoint(route.receiver_id, 'receiver');
  return rows;
}

function buildRouteLogMeta(route) {
  if (!route || !Array.isArray(route.points)) return null;
  const pointIds = Array.isArray(route.point_ids) && route.point_ids.length === route.points.length
    ? route.point_ids
    : null;
  const displayPoints = buildRouteDetailsDisplayPoints(route, pointIds);
  const hopCount = Math.max(0, displayPoints.length - 1);
  const distanceMeters = computeRouteDistanceMeters(route.points);
  const expiresSeconds = Number(route.expires_at);
  const expiresInSeconds = Number.isFinite(expiresSeconds)
    ? (expiresSeconds - getServerNowMs() / 1000)
    : null;
  let cumulative = 0;
  const hashes = Array.isArray(route.hashes) ? route.hashes : null;
  const normalizedHashes = hashes
    ? hashes.map((hash) => normalizeHopHashPrefix(hash)).filter(Boolean)
    : [];
  const hashWidths = [
    ...new Set(normalizedHashes.map((hash) => routeHashByteWidth(hash)).filter(Number.isFinite))
  ];
  const fallbackByteWidth = hashWidths.length === 1 ? hashWidths[0] : null;
  const hashForPoint = (pointId, routeIndex) => {
    if (!pointId || !normalizedHashes.length || routeIndex == null) return null;
    const normalizedPoint = String(pointId).trim().toUpperCase();
    const candidateIndexes = [routeIndex, routeIndex - 1, routeIndex + 1]
      .filter((idx) => Number.isInteger(idx) && idx >= 0 && idx < normalizedHashes.length);
    for (const idx of candidateIndexes) {
      const hash = normalizedHashes[idx];
      if (hash && normalizedPoint.startsWith(hash)) return hash;
    }
    return normalizedHashes.find((hash) => normalizedPoint.startsWith(hash)) || null;
  };
  const pointRows = displayPoints.map((entry, idx) => {
    const coords = Array.isArray(entry.coords) ? entry.coords : [];
    const lat = Number(coords[0]);
    const lon = Number(coords[1]);
    let hopDistance = null;
    if (idx > 0 && Number.isFinite(lat) && Number.isFinite(lon)) {
      const prevEntry = displayPoints[idx - 1];
      const prevCoords = Array.isArray(prevEntry.coords) ? prevEntry.coords : [];
      const prevLat = Number(prevCoords[0]);
      const prevLon = Number(prevCoords[1]);
      if (Number.isFinite(prevLat) && Number.isFinite(prevLon)) {
        hopDistance = haversineMeters(prevLat, prevLon, lat, lon);
        if (Number.isFinite(hopDistance)) {
          cumulative += hopDistance;
        }
      }
    }
    const routeIndex = Number.isInteger(entry.route_index) ? entry.route_index : null;
    const pointId = entry.point_id || null;
    const hopHash = hashForPoint(pointId, routeIndex);
    return {
      index: idx,
      lat,
      lon,
      point_id: pointId || null,
      point_label: entry.point_label || (pointId ? deviceLabelFromId(pointId) : null),
      role_label: entry.role_label || pointIdRoleLabel(pointId),
      endpoint_only: !!entry.endpoint_only,
      endpoint_kind: entry.endpoint_kind || null,
      node_prefix: pointIdNodePrefix(pointId, hopHash, fallbackByteWidth),
      node_prefix_detail: pointIdNodePrefixDetail(pointId, hopHash, fallbackByteWidth),
      hop_distance_m: hopDistance,
      hop_distance_label: Number.isFinite(hopDistance) ? formatDistanceUnits(hopDistance) : null,
      cumulative_m: cumulative,
      cumulative_label: Number.isFinite(cumulative) ? formatDistanceUnits(cumulative) : null,
      hop_hash: hopHash || null,
      hop_prefix: hopHash ? hopPrefixIdLabel(hopHash) : null,
      hop_prefix_detail: hopHash ? hopPrefixDetailLabel(hopHash) : null
    };
  });
  return {
    id: route.id,
    route_mode: route.route_mode || 'path',
    payload_type: route.payload_type,
    payload_label: payloadTypeLabel(route.payload_type),
    hop_count: hopCount,
    point_count: route.points.length,
    distance_m: distanceMeters,
    distance_label: Number.isFinite(distanceMeters) && distanceMeters > 0 ? formatDistanceUnits(distanceMeters) : 'unknown',
    origin_id: route.origin_id,
    origin_label: deviceLabelFromId(route.origin_id),
    receiver_id: route.receiver_id,
    receiver_label: deviceLabelFromId(route.receiver_id),
    sender_name: route.sender_name || null,
    message_hash: route.message_hash,
    topic: route.topic,
    snr_values: route.snr_values,
    expires_at: expiresSeconds,
    expires_label: expiresInSeconds != null ? formatSecondsLabel(expiresInSeconds) : 'unknown',
    ts: route.ts,
    ts_label: formatTimestampLabel(route.ts),
    points: pointRows,
    hashes
  };
}

function logRouteDetails(meta, clickLatLng) {
  if (!meta) {
    console.warn('Route details unavailable');
    return;
  }
  const parts = [];
  if (meta.payload_label) parts.push(meta.payload_label);
  parts.push(meta.route_mode);
  parts.push(`${meta.hop_count} hop${meta.hop_count === 1 ? '' : 's'}`);
  if (meta.distance_label && meta.distance_label !== 'unknown') parts.push(meta.distance_label);
  const title = meta.id ? `Route ${meta.id}` : 'Route';
  if (console.groupCollapsed) {
    console.groupCollapsed(`${title}${parts.length ? ` (${parts.join(' • ')})` : ''}`);
  }
  const routeInfo = {
    mode: meta.route_mode,
    payload: meta.payload_label,
    hops: meta.hop_count,
    points: meta.point_count,
    distance: meta.distance_label,
    origin: meta.origin_label,
    receiver: meta.receiver_label,
    started: meta.ts_label,
    expires_in: meta.expires_label,
    message_hash: meta.message_hash,
    topic: meta.topic,
    snr_values: meta.snr_values,
    click: clickLatLng ? { lat: clickLatLng.lat, lon: clickLatLng.lng } : undefined
  };
  console.log('Route details:', routeInfo);
  if (Array.isArray(meta.points) && meta.points.length && console.table) {
    const rows = meta.points.map((pt) => ({
      index: pt.index,
      point_id: pt.point_id ? shortHash(pt.point_id) : null,
      point_label: pt.point_label || null,
      node_prefix: pt.node_prefix || null,
      node_prefix_detail: pt.node_prefix_detail || null,
      lat: Number.isFinite(pt.lat) ? pt.lat.toFixed(6) : pt.lat,
      lon: Number.isFinite(pt.lon) ? pt.lon.toFixed(6) : pt.lon,
      hop_distance: pt.hop_distance_label,
      cumulative: pt.cumulative_label,
      hop_hash: pt.hop_hash ? shortHash(pt.hop_hash) : null,
      hop_prefix: pt.hop_prefix || null,
      hop_prefix_detail: pt.hop_prefix_detail || null
    }));
    console.table(rows);
  }
  if (console.groupCollapsed) {
    console.groupEnd();
  }
}

function handleRouteClick(routeId, ev) {
  if (ev) {
    L.DomEvent.stop(ev);
  }
  const entry = routeLines.get(routeId);
  if (!entry) {
    console.warn('Route entry missing for click', routeId);
    return;
  }
  if (!entry.meta) {
    const latlngs = entry.line.getLatLngs ? entry.line.getLatLngs() : [];
    entry.meta = buildRouteLogMeta({ id: routeId, points: latlngs.map(pt => [pt.lat, pt.lng]) });
  }
  if (!routeMatchesByteFilter(entry.meta)) {
    return;
  }
  logRouteDetails(entry.meta, ev && ev.latlng);
  showRouteDetails(entry.meta);
}

function upsertRoute(r, skipHeat = false) {
  if (!r || !Array.isArray(r.points) || r.points.length < 2) return;
  const id = r.id || `route-${Date.now()}-${Math.random()}`;
  routeCache.set(id, {
    ...r,
    id,
    points: r.points.map((p) => [p[0], p[1]]),
    hashes: Array.isArray(r.hashes) ? [...r.hashes] : r.hashes,
    point_ids: Array.isArray(r.point_ids) ? [...r.point_ids] : r.point_ids,
    snr_values: Array.isArray(r.snr_values) ? [...r.snr_values] : r.snr_values
  });
  const points = r.points.map(p => [p[0], p[1]]);
  const routeMode = r.route_mode || 'path';
  const payloadType = Number(r.payload_type);
  const style = routeStyleForDisplay(payloadType, routeMode, arcadeModeEnabled);

  const routeMeta = buildRouteLogMeta({ ...r, id, points, hashes: r.hashes });
  let entry = routeLines.get(id);
  if (!entry) {
    const line = L.polyline(points, { ...style, renderer: animatedLineRenderer })
      .addTo(routeLayer);
    if (!prodMode) {
      line.on('click', (ev) => handleRouteClick(id, ev));
    }
    entry = { line, timeout: null };
    routeLines.set(id, entry);
  } else {
    entry.line.setLatLngs(points);
    entry.line.setStyle(style);
  }
  entry.meta = routeMeta;
  entry.routePoints = points;
  entry.payloadType = payloadType;
  entry.routeMode = routeMode;
  const lineEl = entry.line.getElement();
  if (lineEl) {
    if (arcadeModeEnabled) {
      lineEl.classList.remove('route-animated');
    } else {
      lineEl.classList.add('route-animated');
    }
  }
  syncRouteEntryDisplay(id, entry);
  if (routeDetailsPanel && !routeDetailsPanel.hidden && activeRouteDetailsId === id) {
    showRouteDetails(entry.meta);
  }

  if (entry.timeout) clearTimeout(entry.timeout);
  if (r.expires_at) {
    const ms = Math.max(1000, (r.expires_at * 1000) - getServerNowMs());
    entry.timeout = setTimeout(() => removeRoutes([id]), ms);
  }

  if (!skipHeat) {
    addHeatPoints(points, r.ts, r.payload_type);
  }
  refreshStats();
}

async function initialSnapshot() {
  try {
    const res = await fetch(withToken('/snapshot'), { headers: tokenHeaders() });
    const snap = await res.json();
    setServerTimeOffset(snap.server_time);
    if (snap.devices) {
      for (const [id, d] of Object.entries(snap.devices)) {
        const trail = snap.trails ? snap.trails[id] : null;
        upsertDevice(d, trail);
      }
      tryFocusLinkedDevice();
    }
    if (Array.isArray(snap.heat)) {
      seedHeat(snap.heat);
    }
    if (Array.isArray(snap.routes)) {
      clearRoutes();
      snap.routes.forEach(r => upsertRoute(r, true));
    }
    if (Array.isArray(snap.history_edges)) {
      if (routeHistoryEnabled) {
        snap.history_edges.forEach(edge => upsertHistoryEdge(edge));
      }
    }
    applyMqttPresenceSummary(snap.mqtt_presence);
    if (snap.history_window_seconds != null) {
      historyWindowSeconds = Number(snap.history_window_seconds);
      updateHistoryWindowLabel(historyWindowSeconds);
    }
    if (snap.update) {
      setUpdateBanner(snap.update);
    }
    refreshStats();
  } catch (e) {
    console.warn("snapshot failed", e);
  }
}

const pendingWsMessages = [];
let wsFlushScheduled = false;

function flushQueuedWsMessages() {
  wsFlushScheduled = false;
  if (!pendingWsMessages.length) return;
  const batch = pendingWsMessages.splice(0, pendingWsMessages.length);
  deferStats = true;
  try {
    for (const msg of batch) {
      handleRealtimeMessage(msg);
    }
  } finally {
    deferStats = false;
  }
  scheduleStatsUpdate();
}

function queueRealtimeMessage(msg) {
  pendingWsMessages.push(msg);
  if (wsFlushScheduled) return;
  wsFlushScheduled = true;
  window.requestAnimationFrame(flushQueuedWsMessages);
}

function handleRealtimeMessage(msg) {
  if (msg.type === "update") {
    upsertDevice(msg.device, msg.trail);
    tryFocusLinkedDevice();
    return;
  }

  if (msg.type === "device_seen") {
    const id = msg.device_id;
    applyMqttPresenceSummary(msg.mqtt_presence);
    const d = deviceData.get(id);
    if (d) {
      if (msg.last_seen_ts) d.last_seen_ts = msg.last_seen_ts;
      if (Object.prototype.hasOwnProperty.call(msg, 'mqtt_seen_ts')) d.mqtt_seen_ts = msg.mqtt_seen_ts;
      if (Object.prototype.hasOwnProperty.call(msg, 'mqtt_online_source')) d.mqtt_online_source = msg.mqtt_online_source;
      if (Object.prototype.hasOwnProperty.call(msg, 'mqtt_status_ts')) d.mqtt_status_ts = msg.mqtt_status_ts;
      if (Object.prototype.hasOwnProperty.call(msg, 'mqtt_status_value')) d.mqtt_status_value = msg.mqtt_status_value;
      if (Object.prototype.hasOwnProperty.call(msg, 'mqtt_internal_ts')) d.mqtt_internal_ts = msg.mqtt_internal_ts;
      if (Object.prototype.hasOwnProperty.call(msg, 'mqtt_packets_ts')) d.mqtt_packets_ts = msg.mqtt_packets_ts;
      deviceData.set(id, d);
      const m = markers.get(id);
      if (m) {
        if (m.setStyle) m.setStyle(markerStyleForDevice(d));
        m.setPopupContent(makePopup(d));
        updateMarkerLabel(m, d);
      }
      refreshStats();
    }
    if (!d) refreshStats();
    return;
  }

  if (msg.type === "mqtt_presence") {
    applyMqttPresenceSummary(msg.mqtt_presence);
    refreshStats();
    return;
  }

  if (msg.type === "route") {
    upsertRoute(msg.route);
    return;
  }

  if (msg.type === "route_remove") {
    removeRoutes(msg.route_ids || []);
    return;
  }

  if (msg.type === "history_edges") {
    if (!routeHistoryEnabled) return;
    const edges = Array.isArray(msg.edges) ? msg.edges : [];
    edges.forEach(edge => upsertHistoryEdge(edge));
    refreshStats();
    return;
  }

  if (msg.type === "history_edges_remove") {
    if (!routeHistoryEnabled) return;
    removeHistoryEdges(msg.edge_ids || []);
    return;
  }

  if (msg.type === "stale") {
    removeDevices(msg.device_ids || []);
  }
}

function connectWS() {
  const proto = location.protocol === 'https:' ? 'wss' : 'ws';
  const wsSuffix = (prodMode && apiToken) ? `?token=${encodeURIComponent(apiToken)}` : '';
  const ws = new WebSocket(`${proto}://${location.host}${apiPath('/ws')}${wsSuffix}`);

  ws.onopen = () => console.log("ws connected");
  ws.onclose = () => {
    console.log("ws disconnected, retrying...");
    setTimeout(connectWS, 1500);
  };

  ws.onmessage = (ev) => {
    const msg = JSON.parse(ev.data);

    if (msg.type === "snapshot") {
      // same shape as /snapshot
      setServerTimeOffset(msg.server_time);
      deferStats = true;
      try {
        for (const [id, d] of Object.entries(msg.devices || {})) {
          const trail = msg.trails ? msg.trails[id] : null;
          upsertDevice(d, trail);
        }
        tryFocusLinkedDevice();
        clearRoutes();
        if (Array.isArray(msg.heat)) {
          seedHeat(msg.heat);
        }
        if (Array.isArray(msg.routes)) {
          msg.routes.forEach(r => upsertRoute(r, true));
        }
        if (Array.isArray(msg.history_edges)) {
          if (routeHistoryEnabled) {
            msg.history_edges.forEach(edge => upsertHistoryEdge(edge));
          }
        }
        applyMqttPresenceSummary(msg.mqtt_presence);
        if (msg.history_window_seconds != null) {
          historyWindowSeconds = Number(msg.history_window_seconds);
          updateHistoryWindowLabel(historyWindowSeconds);
        }
        if (msg.update) {
          setUpdateBanner(msg.update);
        }
      } finally {
        deferStats = false;
      }
      setStats();
      return;
    }
    queueRealtimeMessage(msg);
  };
}

async function runLosCheck(options = {}) {
  const endpoints = getActiveLosSegmentEndpoints();
  if (!endpoints) return;
  const [a, b] = endpoints;
  losComputeLast = Date.now();
  const token = ++losComputeToken;
  const allowNetwork = options.allowNetwork !== false;
  const allowApprox = options.allowApprox === true;
  setLosStatus('LOS: calculating...');
  try {
    const activeLine = getActiveLosLine();
    if (activeLine) {
      activeLine.setStyle({ color: '#9ca3af', weight: 5, opacity: 0.9, dashArray: '6 10' });
    }
    const clientResult = await runLosCheckClient(a, b, {
      allowNetwork,
      allowApprox,
      forceNetwork: options.forceNetwork === true
    });
    if (token !== losComputeToken) return;
    if (clientResult.ok && applyLosResult(clientResult)) {
      return;
    }
    if (clientResult.error === 'invalid_distance') {
      lastLosStatusMeta = null;
      setLosStatus('LOS: invalid distance');
      return;
    }
    if (!allowNetwork || clientResult.rateLimited) {
      if (clientResult.error === 'elevation_cache_miss') {
        setLosStatus('LOS: waiting for elevation data');
      } else if (clientResult.rateLimited) {
        setLosStatus('LOS: rate limited, using cached terrain');
      } else {
        setLosStatus(`LOS: ${clientResult.error || 'error'}`);
      }
      return;
    }
    const serverResult = await fetchLosServerResult(a, b);
    if (token !== losComputeToken) return;
    if (serverResult.ok && applyLosResult(serverResult)) {
      return;
    }
    lastLosStatusMeta = null;
    setLosStatus(`LOS: ${serverResult.error || clientResult.error || 'error'}`);
    if (activeLine) {
      activeLine.setStyle({ color: '#9ca3af', weight: 5, opacity: 0.9, dashArray: '6 10' });
    }
    clearLosProfile();
    clearLosPeaks();
  } catch (err) {
    console.warn('los failed', err);
    lastLosStatusMeta = null;
    setLosStatus('LOS: error');
    clearLosProfile();
    clearLosPeaks();
  }
}

let losPendingOptions = null;
function scheduleLosCheck(force = false, options = {}) {
  if (!getActiveLosSegmentEndpoints()) return;
  losPendingOptions = options;
  if (force) {
    if (losComputeTimer) {
      clearTimeout(losComputeTimer);
      losComputeTimer = null;
    }
    runLosCheck(options);
    return;
  }
  const now = Date.now();
  const elapsed = now - losComputeLast;
  const delay = Math.max(0, LOS_COMPUTE_THROTTLE_MS - elapsed);
  if (delay === 0) {
    runLosCheck(options);
    return;
  }
  if (losComputeTimer) return;
  losComputeTimer = setTimeout(() => {
    losComputeTimer = null;
    runLosCheck(losPendingOptions || {});
  }, delay);
}

initialSnapshot();
connectWS();
setStats();
setInterval(refreshHeatLayer, 15000);
setInterval(refreshOnlineMarkers, 30000);
if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    const swPath = apiPath('/sw.js');
    const swScope = publicPathPrefix ? `${publicPathPrefix}/` : '/';
    navigator.serviceWorker.register(swPath, { scope: swScope }).catch(() => { });
  });
}

const hopsToggle = document.getElementById('hops-toggle');
if (hopsToggle) {
  hopsToggle.addEventListener('click', () => {
    setHopsVisible(!hopsVisible);
  });
}

setArcadeModeEnabled(arcadeModeEnabled, false);

const legendToggle = document.getElementById('legend-toggle');
const hud = document.querySelector('.hud');
const hudToggle = document.getElementById('hud-toggle');
if (hud && hudToggle) {
  hudToggle.addEventListener('click', (ev) => {
    ev.preventDefault();
    hud.classList.toggle('panel-hidden');
  });
}
if (hud && queryMenuVisible !== null) {
  hud.classList.toggle('panel-hidden', !queryMenuVisible);
}
if (legendToggle && hud) {
  const storedLegend = localStorage.getItem('meshmapLegendCollapsed');
  const overrideLegend = queryLegendVisible === null ? null : !queryLegendVisible;
  const initialLegendCollapsed = overrideLegend !== null ? overrideLegend : storedLegend === 'true';
  if (initialLegendCollapsed) {
    hud.classList.add('legend-collapsed');
    legendToggle.textContent = 'Show legend';
  }
  legendToggle.addEventListener('click', () => {
    const collapsed = hud.classList.toggle('legend-collapsed');
    legendToggle.textContent = collapsed ? 'Show legend' : 'Hide legend';
    localStorage.setItem('meshmapLegendCollapsed', collapsed ? 'true' : 'false');
  });
  if (overrideLegend !== null) {
    localStorage.setItem('meshmapLegendCollapsed', overrideLegend ? 'true' : 'false');
  }
}

if (losPanelCollapse) {
  losPanelCollapse.addEventListener('click', () => {
    setLosPanelCollapsed(!losPanelCollapsed);
  });
}
if (propPanelCollapse) {
  propPanelCollapse.addEventListener('click', () => {
    setPropPanelCollapsed(!propPanelCollapsed);
  });
}
if (historyPanelCollapse) {
  historyPanelCollapse.addEventListener('click', () => {
    setHistoryPanelCollapsed(!historyPanelCollapsed);
  });
}
if (peersPanelCollapse) {
  peersPanelCollapse.addEventListener('click', () => {
    setPeersPanelCollapsed(!peersPanelCollapsed);
  });
}
if (routeDetailsCollapse) {
  routeDetailsCollapse.addEventListener('click', () => {
    setRouteDetailsPanelCollapsed(!routeDetailsPanelCollapsed);
  });
}
setLosPanelCollapsed(losPanelCollapsed);
setPropPanelCollapsed(propPanelCollapsed);
setHistoryPanelCollapsed(historyPanelCollapsed);
setPeersPanelCollapsed(peersPanelCollapsed);
setRouteDetailsPanelCollapsed(routeDetailsPanelCollapsed);

const customLink = document.getElementById('custom-link');
const updateBanner = document.getElementById('update-banner');
const updateText = document.getElementById('update-text');
const updateDismiss = document.getElementById('update-dismiss');
let updateDismissKey = null;
const setUpdateBanner = (info) => {
  if (!updateBanner) return;
  if (!info || !info.available) {
    updateBanner.hidden = true;
    updateDismissKey = null;
    return;
  }
  const remoteKey = info.remote_short || info.remote || 'update';
  updateDismissKey = remoteKey;
  const dismissed = localStorage.getItem('meshmapUpdateDismissed');
  if (dismissed && dismissed === remoteKey) {
    updateBanner.hidden = true;
    return;
  }
  const localLabel = info.local_short || info.local || 'local';
  const remoteLabel = info.remote_short || info.remote || 'remote';
  if (updateText) {
    updateText.textContent = `Update available (${localLabel} \u2192 ${remoteLabel})`;
  }
  updateBanner.hidden = false;
};
if (customLink) {
  if (customLinkUrl) {
    customLink.setAttribute('href', customLinkUrl);
    customLink.setAttribute('title', customLinkUrl);
  } else {
    customLink.remove();
  }
}
const dismissUpdateBanner = (ev, source = 'click') => {
  if (!updateBanner || updateBanner.hidden) return;
  if (ev) {
    ev.preventDefault();
    ev.stopPropagation();
  }
  const key = updateDismissKey || initialUpdateRemote || 'update';
  try {
    localStorage.setItem('meshmapUpdateDismissed', key);
  } catch (err) {
    // ignore storage failures
  }
  updateBanner.hidden = true;
};

if (updateDismiss) {
  updateDismiss.addEventListener('click', (ev) => dismissUpdateBanner(ev, 'click'));
  updateDismiss.addEventListener('pointerdown', (ev) => dismissUpdateBanner(ev, 'pointerdown'));
  updateDismiss.addEventListener('touchend', (ev) => dismissUpdateBanner(ev, 'touchend'));
}
if (updateBanner) {
  updateBanner.addEventListener('click', (ev) => dismissUpdateBanner(ev, 'banner-click'));
  updateBanner.addEventListener('pointerdown', (ev) => dismissUpdateBanner(ev, 'banner-pointerdown'));
}
if (initialUpdateAvailable) {
  setUpdateBanner({
    available: true,
    local_short: initialUpdateLocal || null,
    remote_short: initialUpdateRemote || null,
    local: initialUpdateLocal || null,
    remote: initialUpdateRemote || null,
  });
}

function clearLinkedDeviceParams(url) {
  linkedDeviceParamNames.forEach((name) => url.searchParams.delete(name));
}

function buildMapShareUrl(options = {}) {
  const center = options.center || map.getCenter();
  const lat = Number(center.lat);
  const lon = Number(center.lng ?? center.lon);
  const zoom = options.zoom == null ? map.getZoom() : options.zoom;
  const url = new URL(window.location.href);
  clearLinkedDeviceParams(url);
  if (Number.isFinite(lat)) url.searchParams.set('lat', lat.toFixed(5));
  if (Number.isFinite(lon)) url.searchParams.set('lon', lon.toFixed(5));
  url.searchParams.set('zoom', String(zoom));
  url.searchParams.set('layer', baseLayer);
  url.searchParams.set('history', historyVisible ? 'on' : 'off');
  url.searchParams.set('heat', heatVisible ? 'on' : 'off');
  url.searchParams.set('coverage', coverageVisible ? 'on' : 'off');
  url.searchParams.set('weather', radarVisible ? 'on' : 'off');
  url.searchParams.set('weather_radar', weatherRadarLayerEnabled ? 'on' : 'off');
  url.searchParams.set('weather_wind', weatherWindLayerEnabled ? 'on' : 'off');
  url.searchParams.set('labels', showLabels ? 'on' : 'off');
  url.searchParams.set('nodes', nodesVisible ? 'on' : 'off');
  url.searchParams.set(
    'legend',
    hud && hud.classList.contains('legend-collapsed') ? 'off' : 'on'
  );
  url.searchParams.set(
    'menu',
    hud && hud.classList.contains('panel-hidden') ? 'off' : 'on'
  );
  url.searchParams.set('units', distanceUnits);
  url.searchParams.set('history_filter', String(historyFilterMode));
  url.searchParams.set('history_bytes', serializeByteFilterSet(historyByteFilter));
  url.searchParams.set('route_bytes', serializeByteFilterSet(routeByteFilter));
  if (routeNodeFilterText.trim()) {
    url.searchParams.set('route_nodes', routeNodeFilterText.trim());
  } else {
    url.searchParams.delete('route_nodes');
  }
  url.searchParams.set('roles', [...visibleRoles].join(','));
  if (options.deviceId) {
    url.searchParams.set('node', options.deviceId);
    url.searchParams.set('nodes', 'on');
  }
  return url.toString();
}

function buildDeviceLink(id, d) {
  const marker = markers.get(id);
  const markerLatLng = marker && marker.getLatLng ? marker.getLatLng() : null;
  const lat = markerLatLng ? markerLatLng.lat : Number(d && d.lat);
  const lon = markerLatLng ? markerLatLng.lng : Number(d && d.lon);
  return buildMapShareUrl({
    center: { lat, lon },
    zoom: Math.max(map.getZoom(), 13),
    deviceId: id
  });
}

async function copyTextWithFallback(text, promptLabel) {
  let copied = false;
  try {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      await navigator.clipboard.writeText(text);
      copied = true;
    }
  } catch (_err) {
    copied = false;
  }
  if (!copied) {
    window.prompt(promptLabel, text);
  }
  return copied;
}

async function copyNodeLink(ev) {
  const btn = ev?.currentTarget;
  const id = btn?.dataset?.nodeLinkId || '';
  if (!btn || !id) return;
  ev.preventDefault();
  ev.stopPropagation();
  const d = deviceData.get(id);
  const link = buildDeviceLink(id, d);
  const original = btn.textContent || 'Copy link';
  const copied = await copyTextWithFallback(link, 'Copy node link:');
  btn.textContent = copied ? 'Copied' : original;
  window.setTimeout(() => {
    btn.textContent = original;
  }, 1200);
}

const shareToggle = document.getElementById('share-toggle');
if (qrModalClose) {
  qrModalClose.addEventListener('click', closeQrModal);
}
if (qrModalBackdrop) {
  qrModalBackdrop.addEventListener('click', closeQrModal);
}
if (qrModalLabel) {
  qrModalLabel.addEventListener('click', copyPopupText);
}
document.addEventListener('keydown', (ev) => {
  if (ev.key === 'Escape' && qrModal && !qrModal.hidden) {
    closeQrModal();
  }
});
if (shareToggle) {
  const resetShareButton = () => {
    shareToggle.classList.remove('copied');
    shareToggle.setAttribute('aria-label', 'Copy share link');
    shareToggle.setAttribute('title', 'Copy share link');
  };
  shareToggle.addEventListener('click', async () => {
    await copyTextWithFallback(buildMapShareUrl(), 'Copy share link:');
    shareToggle.classList.add('copied');
    shareToggle.setAttribute('aria-label', 'Share link copied');
    shareToggle.setAttribute('title', 'Share link copied');
    window.setTimeout(resetShareButton, 1600);
  });
}

const mapToggle = document.getElementById('map-toggle');
const topoToggle = document.getElementById('topo-toggle');
function setBaseLayer(name) {
  if (map.hasLayer(lightTiles)) map.removeLayer(lightTiles);
  if (map.hasLayer(darkTiles)) map.removeLayer(darkTiles);
  if (map.hasLayer(topoTiles)) map.removeLayer(topoTiles);
  if (map.hasLayer(satelliteTiles)) map.removeLayer(satelliteTiles);
  if (name === 'dark') {
    map.addLayer(darkTiles);
  } else if (name === 'topo') {
    map.addLayer(topoTiles);
  } else if (name === 'satellite') {
    map.addLayer(satelliteTiles);
  } else {
    map.addLayer(lightTiles);
  }
  document.body.classList.toggle('dark-map', name === 'dark');
  baseLayer = name;
  localStorage.setItem('meshmapBaseLayer', baseLayer);
  if (mapToggle) {
    mapToggle.hidden = false;
    mapToggle.textContent = baseLayer === 'dark' ? 'Light map' : 'Dark map';
    mapToggle.title = '';
  }
  if (topoToggle) {
    if (baseLayer === 'topo') {
      topoToggle.textContent = 'Satellite map';
    } else if (baseLayer === 'satellite') {
      topoToggle.textContent = 'Standard map';
    } else {
      topoToggle.textContent = 'Topo map';
    }
  }
}

function nextStandardMapLayer() {
  if (baseLayer === 'topo') return 'satellite';
  if (baseLayer === 'satellite') return 'light';
  return 'topo';
}

if (mapToggle) {
  mapToggle.addEventListener('click', () => {
    setBaseLayer(baseLayer === 'dark' ? 'light' : 'dark');
  });
}
if (topoToggle) {
  topoToggle.addEventListener('click', () => {
    setBaseLayer(nextStandardMapLayer());
  });
}
setBaseLayer(baseLayer);

const unitsToggle = document.getElementById('units-toggle');
function setUnitsLabel() {
  if (!unitsToggle) return;
  unitsToggle.textContent = distanceUnits === 'mi' ? 'Units: mi' : 'Units: km';
}
function setDistanceUnits(units, persist = true) {
  if (!validUnits.has(units)) return;
  distanceUnits = units;
  if (persist) {
    localStorage.setItem('meshmapDistanceUnits', units);
  }
  setUnitsLabel();
  if (lastLosDistance != null && losProfileData.length) {
    updateLosProfileAtDistance(lastLosDistance);
  }
  if (lastLosStatusMeta) {
    setLosStatus(buildLosStatus(lastLosStatusMeta));
  }
  updatePropagationSummary();
  if (propagationRasterMeta && propagationOrigins.length) {
    updatePropagationStatusFromRaster();
  }
  if (activeRouteDetailsMeta && routeDetailsPanel && !routeDetailsPanel.hidden) {
    showRouteDetails(activeRouteDetailsMeta);
  }
  if (peersData) {
    renderCurrentPeers();
  }
  if (radarVisible && weatherWindEnabled && weatherWindLayerEnabled) {
    refreshWeatherWindLayer({ silent: true, background: true });
  }
}
setUnitsLabel();
if (unitsToggle) {
  unitsToggle.addEventListener('click', () => {
    const next = distanceUnits === 'mi' ? 'km' : 'mi';
    setDistanceUnits(next);
  });
}

if (routeByteFilterSelect) {
  routeByteFilterSelect.addEventListener('change', (ev) => {
    routeByteFilter = selectedByteFilterFromGroup(routeByteFilterSelect, ev.target);
    localStorage.setItem('meshmapRouteByteFilter', serializeByteFilterSet(routeByteFilter));
    setByteFilterChecks(routeByteFilterSelect, routeByteFilter);
    syncAllRouteDisplays();
  });
}

if (routeNodeFilterInput) {
  routeNodeFilterInput.addEventListener('input', (ev) => {
    routeNodeFilterText = String(ev.target.value || '');
    localStorage.setItem('meshmapRouteNodeFilter', routeNodeFilterText);
    syncRouteFilterDisplays();
    renderRouteNodeFilterResults();
  });
  routeNodeFilterInput.addEventListener('keydown', (ev) => {
    if (ev.key === 'Escape') {
      ev.preventDefault();
      hideRouteNodeFilterResults();
      return;
    }
    if (ev.key === 'Enter' && routeNodeMatches.length) {
      ev.preventDefault();
      selectRouteNodeFilterMatch(routeNodeMatches[0]);
    }
  });
  routeNodeFilterInput.addEventListener('focus', renderRouteNodeFilterResults);
  routeNodeFilterInput.addEventListener('blur', () => {
    window.setTimeout(() => {
      hideRouteNodeFilterResults();
    }, 100);
  });
  if (hud) {
    hud.addEventListener('scroll', positionRouteNodeFilterResults);
  }
}

document.addEventListener('click', (ev) => {
  if (!routeNodeFilterInput || !routeNodeFilterResults) return;
  if (routeNodeFilterInput.contains(ev.target) ||
      routeNodeFilterResults.contains(ev.target)) return;
  hideRouteNodeFilterResults();
});

roleFilterButtons.forEach((button) => {
  button.addEventListener('click', () => {
    const role = button.dataset.roleFilter;
    setRoleVisible(role, !visibleRoles.has(role));
  });
});
updateRoleFilterUi();

const labelsToggle = document.getElementById('labels-toggle');
if (labelsToggle) {
  labelsToggle.addEventListener('click', () => {
    setLabelsActive(!showLabels);
  });
}
if (queryLabelsVisible !== null) {
  showLabels = queryLabelsVisible;
  localStorage.setItem('meshmapShowLabels', showLabels ? 'true' : 'false');
}
setLabelsActive(showLabels);

if (searchInput) {
  searchInput.addEventListener('input', (ev) => {
    renderSearchResults(ev.target.value);
  });
  searchInput.addEventListener('keydown', (ev) => {
    const secret = String(searchInput.value || '').trim().toLowerCase();
    if (ev.key === 'Enter' && (secret === '/waka' || secret === '/arcade')) {
      ev.preventDefault();
      searchInput.value = '';
      renderSearchResults('');
      toggleArcadeMode();
      return;
    }
    if (ev.key === 'Enter' && searchMatches.length > 0) {
      ev.preventDefault();
      focusDevice(searchMatches[0].id);
    }
  });
}
document.addEventListener('click', (ev) => {
  if (!searchResults || !searchInput) return;
  if (searchResults.contains(ev.target) || searchInput.contains(ev.target)) return;
  searchResults.hidden = true;
  searchResults.innerHTML = '';
});
window.addEventListener('resize', () => {
  positionRouteNodeFilterResults();
  layoutSidePanels();
});

if (losProfileSvg) {
  losProfileSvg.addEventListener('mousemove', updateLosProfileHover);
  losProfileSvg.addEventListener('mouseleave', clearLosProfileHover);
  losProfileSvg.addEventListener('click', (ev) => {
    const distance = losProfileDistanceFromEvent(ev);
    if (distance == null) return;
    updateLosProfileAtDistance(distance);
    copyLosCoords(distance);
  });
}

const losToggle = document.getElementById('los-toggle');
if (losToggle) {
  losToggle.addEventListener('click', () => {
    setLosActive(!losActive);
  });
}
const parseLosHeightValue = (input) => {
  if (!input) return 0;
  const value = Number(input.value);
  return Number.isFinite(value) ? value : 0;
};
const parseLosPointEditorValues = () => {
  const rawLat = losPointLatInput ? String(losPointLatInput.value || '').trim() : '';
  const rawLon = losPointLonInput ? String(losPointLonInput.value || '').trim() : '';
  const rawHeight = losPointHeightInput
    ? String(losPointHeightInput.value || '').trim()
    : '';
  if (!rawLat || !rawLon) return null;
  const lat = Number(rawLat);
  const lon = Number(rawLon);
  const height = rawHeight ? Number(rawHeight) : 0;
  if (!Number.isFinite(lat) || lat < -90 || lat > 90) return null;
  if (!Number.isFinite(lon) || lon < -180 || lon > 180) return null;
  if (!Number.isFinite(height)) return null;
  return { lat, lon, height };
};
const handleLosHeightChange = () => {
  if (!Number.isInteger(losActiveSegmentIndex) || losActiveSegmentIndex < 0) return;
  setLosPointHeight(losActiveSegmentIndex, parseLosHeightValue(losHeightAInput));
  setLosPointHeight(losActiveSegmentIndex + 1, parseLosHeightValue(losHeightBInput));
  syncLosPointEditor();
  if (losPoints.length >= 2) {
    if (losActiveSegmentIndex >= 0 && losActiveSegmentIndex < losSegmentMeta.length) {
      losSegmentMeta[losActiveSegmentIndex] = null;
    }
    scheduleLosCheck(true, { allowNetwork: true, forceNetwork: true });
  }
};
if (losHeightAInput) {
  losHeightAInput.addEventListener('input', handleLosHeightChange);
  losHeightAInput.addEventListener('change', handleLosHeightChange);
}
if (losHeightBInput) {
  losHeightBInput.addEventListener('input', handleLosHeightChange);
  losHeightBInput.addEventListener('change', handleLosHeightChange);
}

function updateLosPointPosition(index, latlng) {
  if (index == null || !losPoints[index]) return;
  losPoints[index] = latlng;
  ensureLosSegments();
  const affected = [];
  if (index > 0) affected.push(index - 1);
  if (index < losLines.length) affected.push(index);
  affected.forEach((segIdx) => {
    if (segIdx >= 0 && segIdx < losSegmentMeta.length) {
      losSegmentMeta[segIdx] = null;
    }
  });
  if (affected.length) {
    losActiveSegmentIndex = affected[affected.length - 1];
  }
  lastLosStatusMeta = null;
  updateLosSegmentStyles();
  if (losPoints.length >= 2) {
    setLosStatus('LOS: calculating...');
  }
  return affected;
}

async function recomputeLosSegments(indices, options = {}) {
  const valid = Array.from(new Set((indices || []).filter((index) => (
    Number.isInteger(index) && index >= 0 && index < losLines.length
  ))));
  if (!valid.length) return;
  const finalIndex = Number.isInteger(options.finalIndex) && options.finalIndex >= 0 && options.finalIndex < losLines.length
    ? options.finalIndex
    : valid[valid.length - 1];
  for (const index of valid) {
    selectLosSegment(index, { silent: true });
    await runLosCheck({
      allowNetwork: options.allowNetwork !== false,
      allowApprox: options.allowApprox === true,
      forceNetwork: options.forceNetwork === true
    });
  }
  if (Number.isInteger(finalIndex) && finalIndex >= 0 && finalIndex < losLines.length) {
    selectLosSegment(finalIndex, { silent: true });
  }
}

function removeLastLosPoint() {
  if (!losPoints.length) return;
  const lastMarker = losPointMarkers.pop();
  if (lastMarker) {
    losLayer.removeLayer(lastMarker);
  }
  losPoints.pop();
  losPointHeights.pop();
  persistLosPointHeights();
  if (losSelectedPointIndex != null && losSelectedPointIndex >= losPoints.length) {
    setLosSelectedPoint(null);
  }
  ensureLosSegments();
  if (losPoints.length >= 2) {
    const nextIndex = Math.max(0, losPoints.length - 2);
    selectLosSegment(nextIndex, { silent: true });
    const combined = buildCombinedLosProfile();
    if (combined.profile.length >= 2) {
      renderLosProfile(combined.profile, combined.blocked, combined);
    } else {
      clearLosProfile();
    }
    setLosStatus(`LOS: removed pin ${losPoints.length + 1}`);
    return;
  }
  clearLosProfile();
  clearLosPeaks();
  lastLosStatusMeta = null;
  if (losPoints.length === 1) {
    setLosStatus('LOS: select next point');
  } else {
    setLosStatus('LOS: select first point (Shift+click or long-press nodes)');
  }
}

function setLosSelectedPoint(index) {
  if (!Number.isInteger(index) || index < 0 || index >= losPointMarkers.length) {
    losSelectedPointIndex = null;
  } else {
    losSelectedPointIndex = index;
  }
  losPointMarkers.forEach((pointMarker, idx) => {
    const el = pointMarker && pointMarker.getElement ? pointMarker.getElement() : null;
    if (!el) return;
    el.classList.toggle('selected', losSelectedPointIndex === idx);
  });
  syncLosPointEditor();
}

function createLosPointMarker(latlng, index) {
  const marker = L.marker(latlng, {
    icon: losPointIcon,
    draggable: true,
    autoPan: false,
    zIndexOffset: 450
  }).addTo(losLayer);
  marker.__losIndex = index;
  marker.on('click', (ev) => {
    if (ev && ev.originalEvent) {
      ev.originalEvent.preventDefault();
      ev.originalEvent.stopPropagation();
    }
    if (typeof L !== 'undefined' && L.DomEvent) {
      L.DomEvent.stop(ev);
    }
    setLosSelectedPoint(index);
    if (losLines.length > 0) {
      const nextSegment = index > 0 ? index - 1 : 0;
      selectLosSegment(nextSegment, { silent: true });
    }
    setLosStatus(`LOS: selected point ${index + 1} (click map to move or drag point)`);
  });
  marker.on('dragstart', () => {
    const el = marker.getElement();
    if (el) el.classList.add('dragging');
    setLosSelectedPoint(index);
    losDragging = true;
    clearLosProfileHover();
  });
  marker.on('drag', () => {
    const next = marker.getLatLng();
    updateLosPointPosition(index, next);
    scheduleLosCheck(false, { allowNetwork: false, allowApprox: true });
  });
  marker.on('dragend', async () => {
    const el = marker.getElement();
    if (el) el.classList.remove('dragging');
    const next = marker.getLatLng();
    const affected = updateLosPointPosition(index, next);
    losDragging = false;
    await recomputeLosSegments(affected, {
      allowNetwork: true,
      forceNetwork: true,
      finalIndex: affected && affected.length ? affected[affected.length - 1] : losActiveSegmentIndex
    });
  });
  marker.on('add', () => setLosSelectedPoint(losSelectedPointIndex));
  return marker;
}

function handleLosPoint(latlng, options = {}) {
  losPoints.push(latlng);
  if (losPointHeights.length < losPoints.length) {
    losPointHeights.push(0);
    persistLosPointHeights();
  }
  const pointIndex = losPoints.length - 1;
  if (options.height != null) {
    setLosPointHeight(pointIndex, options.height);
  }
  const marker = createLosPointMarker(latlng, losPoints.length - 1);
  losPointMarkers.push(marker);
  if (options.select === true) {
    setLosSelectedPoint(pointIndex);
  } else {
    setLosSelectedPoint(null);
  }

  if (losPoints.length === 1) {
    setLosStatus('LOS: select next point');
    return;
  }
  losLocked = true;
  ensureLosSegments();
  selectLosSegment(losPoints.length - 2, { silent: true });
  scheduleLosCheck(true, { allowNetwork: true, forceNetwork: true });
}

async function addLosPointFromInputs() {
  const parsed = parseLosPointEditorValues();
  if (!parsed) {
    setLosStatus('LOS: enter valid latitude and longitude');
    return;
  }
  handleLosPoint(L.latLng(parsed.lat, parsed.lon), { height: parsed.height });
}

async function moveSelectedLosPointFromInputs() {
  if (!Number.isInteger(losSelectedPointIndex) ||
      losSelectedPointIndex < 0 ||
      losSelectedPointIndex >= losPoints.length) {
    setLosStatus('LOS: select a pin first');
    return;
  }
  const parsed = parseLosPointEditorValues();
  if (!parsed) {
    setLosStatus('LOS: enter valid latitude and longitude');
    return;
  }
  const next = L.latLng(parsed.lat, parsed.lon);
  setLosPointHeight(losSelectedPointIndex, parsed.height);
  if (losPointMarkers[losSelectedPointIndex]) {
    losPointMarkers[losSelectedPointIndex].setLatLng(next);
  }
  const affected = updateLosPointPosition(losSelectedPointIndex, next) || [];
  syncLosHeightInputs();
  syncLosPointEditor();
  if (!affected.length) {
    setLosStatus(`LOS: moved pin ${losSelectedPointIndex + 1}`);
    return;
  }
  setLosStatus('LOS: calculating...');
  await recomputeLosSegments(affected, {
    allowNetwork: true,
    forceNetwork: true,
    finalIndex: affected[affected.length - 1]
  });
}

if (losClearButton) {
  losClearButton.addEventListener('click', () => {
    clearLos();
    if (losActive) {
      setLosStatus('LOS: select first point (Shift+click or long-press nodes)');
    }
  });
}
if (losRemoveLastButton) {
  losRemoveLastButton.addEventListener('click', () => {
    removeLastLosPoint();
  });
}
if (losAddCoordsButton) {
  losAddCoordsButton.addEventListener('click', () => {
    addLosPointFromInputs();
  });
}
if (losUpdatePointButton) {
  losUpdatePointButton.addEventListener('click', () => {
    moveSelectedLosPointFromInputs();
  });
}
const nodesToggle = document.getElementById('nodes-toggle');
if (nodesToggle) {
  const storedNodes = localStorage.getItem('meshmapNodesVisible');
  let initialNodes = storedNodes !== null ? storedNodes === 'true' : true;
  if (queryNodesVisible !== null) {
    initialNodes = queryNodesVisible;
    localStorage.setItem('meshmapNodesVisible', initialNodes ? 'true' : 'false');
  }
  setNodesVisible(initialNodes);
  nodesToggle.addEventListener('click', () => {
    setNodesVisible(!nodesVisible);
    localStorage.setItem('meshmapNodesVisible', nodesVisible ? 'true' : 'false');
  });
}
if (mqttOnlyToggle) {
  mqttOnlyToggle.addEventListener('click', () => {
    setMqttOnlyVisible(!mqttOnlyVisible);
  });
}
updateNodeSizeUi();
if (nodeSizeInput) {
  nodeSizeInput.addEventListener('input', (ev) => {
    setNodeMarkerRadius(ev.target.value);
  });
}

const historyToggle = document.getElementById('history-toggle');
if (historyToggle) {
  if (!routeHistoryEnabled) {
    historyToggle.setAttribute('hidden', 'hidden');
    historyToggle.style.display = 'none';
    setHistoryVisible(false);
  } else {
    let initialHistory = false;
    if (queryHistoryVisible !== null) {
      initialHistory = queryHistoryVisible;
    }
    setHistoryVisible(initialHistory);
    historyToggle.addEventListener('click', () => {
      if (historyVisible && historyPanelHidden) {
        setHistoryPanelHidden(false);
        return;
      }
      setHistoryVisible(!historyVisible);
    });
  }
}
updateHistoryFilterLabel();
if (historyFilter) {
  historyFilter.addEventListener('input', (ev) => {
    updateHistoryFilter(ev.target.value);
  });
}
if (historyByteFilterSelect) {
  historyByteFilterSelect.addEventListener('change', (ev) => {
    updateHistoryByteFilter(selectedByteFilterFromGroup(historyByteFilterSelect, ev.target));
  });
}
if (historyLinkSizeInput) {
  historyLinkSizeInput.addEventListener('input', (ev) => {
    updateHistoryLinkScale(ev.target.value);
  });
}

if (peersToggle) {
  const initialPeersActive =
    queryPeersActive !== null ? queryPeersActive : peersDefaultOpen;
  setPeersActive(initialPeersActive);
  peersToggle.addEventListener('click', () => {
    setPeersActive(!peersActive);
  });
}
if (peersStatus) {
  peersStatus.addEventListener('click', () => {
    if (peersStatus.dataset.peerDeviceId) {
      focusDevice(peersStatus.dataset.peerDeviceId);
    }
  });
  peersStatus.addEventListener('keydown', (ev) => {
    if (!peersStatus.dataset.peerDeviceId) return;
    if (ev.key === 'Enter' || ev.key === ' ') {
      ev.preventDefault();
      focusDevice(peersStatus.dataset.peerDeviceId);
    }
  });
}
if (peersTitle) {
  peersTitle.addEventListener('click', () => {
    if (peersTitle.dataset.peerDeviceId) {
      focusDevice(peersTitle.dataset.peerDeviceId);
    }
  });
  peersTitle.addEventListener('keydown', (ev) => {
    if (!peersTitle.dataset.peerDeviceId) return;
    if (ev.key === 'Enter' || ev.key === ' ') {
      ev.preventDefault();
      focusDevice(peersTitle.dataset.peerDeviceId);
    }
  });
}
if (peersClear) {
  peersClear.addEventListener('click', () => {
    clearPeers();
  });
}
if (peersFilter) {
  peersFilter.addEventListener('input', () => {
    peersFilterText = peersFilter.value || '';
    if (peersData) {
      renderCurrentPeers();
    }
  });
}

const heatToggle = document.getElementById('heat-toggle');
if (heatToggle) {
  const storedHeatVisible = localStorage.getItem('meshmapShowHeat');
  let initialHeat = storedHeatVisible !== null
    ? storedHeatVisible === 'true'
    : heatDefaultOn;
  if (queryHeatVisible !== null) {
    initialHeat = queryHeatVisible;
    localStorage.setItem('meshmapShowHeat', initialHeat ? 'true' : 'false');
  }
  setHeatVisible(initialHeat);
  heatToggle.addEventListener('click', () => {
    try {
      setHeatVisible(!heatVisible);
      localStorage.setItem('meshmapShowHeat', heatVisible ? 'true' : 'false');
    } catch (err) {
      reportError(`Heat toggle failed: ${err && err.message ? err.message : err}`);
      console.error(err);
    }
  });
}

const coverageToggle = document.getElementById('coverage-toggle');
if (coverageToggle && !coverageEnabled) {
  coverageToggle.setAttribute('hidden', 'hidden');
}
if (coverageToggle && coverageEnabled) {
  const storedCoverageVisible = localStorage.getItem('meshmapShowCoverage');
  let initialCoverage = storedCoverageVisible !== null ? storedCoverageVisible === 'true' : false;
  if (queryCoverageVisible !== null) {
    initialCoverage = queryCoverageVisible;
    localStorage.setItem('meshmapShowCoverage', initialCoverage ? 'true' : 'false');
  }
  setCoverageVisible(initialCoverage);
  coverageToggle.addEventListener('click', () => {
    try {
      setCoverageVisible(!coverageVisible);
      localStorage.setItem('meshmapShowCoverage', coverageVisible ? 'true' : 'false');
    } catch (err) {
      reportError(`Coverage toggle failed: ${err && err.message ? err.message : err}`);
    }
  });
}

const weatherToggle = document.getElementById('weather-toggle');
if (weatherToggle) {
  localStorage.removeItem('meshmapShowRadar');
  if (!weatherAvailable) {
    weatherToggle.setAttribute('hidden', 'hidden');
    if (weatherPanel) {
      weatherPanel.setAttribute('hidden', 'hidden');
      weatherPanel.classList.remove('active');
      weatherPanel.style.display = 'none';
    }
  }
  if (weatherRadarEnabled && weatherRadarCountryBoundsEnabled) {
    loadStoredRadarCountryBounds();
    ensureRadarCountryBounds({ silent: true });
  }
  const cachedRadarHost = (localStorage.getItem('meshmapRadarHost') || '').trim();
  const cachedRadarPath = (localStorage.getItem('meshmapRadarPath') || '').trim();
  if (weatherRadarEnabled && cachedRadarPath) {
    updateRadarLayer(cachedRadarHost || radarFrameHost, cachedRadarPath);
  }
  if (weatherRadarEnabled) {
    refreshRadarLayer({ silent: true, background: true });
  }
  const storedWeatherRadarLayer = parseBoolParam(
    localStorage.getItem(WEATHER_RADAR_LAYER_STORAGE_KEY)
  );
  const storedWeatherWindLayer = parseBoolParam(
    localStorage.getItem(WEATHER_WIND_LAYER_STORAGE_KEY)
  );
  weatherRadarLayerEnabled = weatherRadarEnabled && (
    queryWeatherRadarVisible !== null
      ? queryWeatherRadarVisible
      : (storedWeatherRadarLayer !== null ? storedWeatherRadarLayer : true)
  );
  if (weatherWindEnabled) {
    weatherWindLayerEnabled = queryWeatherWindVisible !== null
      ? queryWeatherWindVisible
      : (storedWeatherWindLayer !== null ? storedWeatherWindLayer : true);
  } else {
    weatherWindLayerEnabled = false;
  }
  try {
    localStorage.setItem(
      WEATHER_RADAR_LAYER_STORAGE_KEY,
      weatherRadarLayerEnabled ? 'true' : 'false'
    );
    localStorage.setItem(
      WEATHER_WIND_LAYER_STORAGE_KEY,
      weatherWindLayerEnabled ? 'true' : 'false'
    );
  } catch (_err) {}
  updateWeatherLayerButtons();
  let initialRadar = false;
  if (queryWeatherVisible !== null && weatherAvailable) {
    initialRadar = queryWeatherVisible;
  }
  setRadarVisible(initialRadar);
  weatherToggle.addEventListener('click', () => {
    if (!weatherAvailable) return;
    try {
      if (radarVisible && weatherPanelHidden) {
        setWeatherPanelHidden(false);
        return;
      }
      setRadarVisible(!radarVisible);
    } catch (err) {
      reportError(`Weather toggle failed: ${err && err.message ? err.message : err}`);
    }
  });
}
if (weatherRadarLayerToggle) {
  weatherRadarLayerToggle.addEventListener('click', () => {
    if (!weatherRadarEnabled) return;
    setWeatherRadarLayerEnabled(!weatherRadarLayerEnabled);
  });
}
if (weatherWindLayerToggle) {
  weatherWindLayerToggle.addEventListener('click', () => {
    if (!weatherWindEnabled) return;
    setWeatherWindLayerEnabled(!weatherWindLayerEnabled);
  });
}
if (weatherHideButton) {
  const hideWeatherPanel = (ev) => {
    if (ev) {
      if (ev.preventDefault) ev.preventDefault();
      if (ev.stopPropagation) ev.stopPropagation();
      if (typeof L !== 'undefined' && L.DomEvent) L.DomEvent.stop(ev);
    }
    setWeatherPanelHidden(true);
  };
  weatherHideButton.addEventListener('click', hideWeatherPanel);
  weatherHideButton.addEventListener('pointerdown', hideWeatherPanel);
}

const propToggle = document.getElementById('prop-toggle');
const propTxInput = document.getElementById('prop-txpower');
const propTxGainInput = document.getElementById('prop-tx-gain');
const propOpacityInput = document.getElementById('prop-opacity');
const propModelSelect = document.getElementById('prop-model');
const propTerrainInput = document.getElementById('prop-terrain');
const propTxAglInput = document.getElementById('prop-tx-agl');
const propRxAglInput = document.getElementById('prop-rx-agl');
const propTxMslInput = document.getElementById('prop-tx-msl');
const propRxMslInput = document.getElementById('prop-rx-msl');
const propMinRxInput = document.getElementById('prop-min-rx');
const propAutoRangeInput = document.getElementById('prop-auto-range');
const propMultiOriginInput = document.getElementById('prop-multi-origin');
const propFadeMarginInput = document.getElementById('prop-fade-margin');
const propWebGpuInput = document.getElementById('prop-webgpu');
const propClearOriginsButton = document.getElementById('prop-clear-origins');
const propAutoResInput = document.getElementById('prop-auto-res');
const propMaxCellsInput = document.getElementById('prop-max-cells');
const propGridInput = document.getElementById('prop-grid');
const propSampleInput = document.getElementById('prop-sample');
const propRangeFactorInput = document.getElementById('prop-range-factor');
const propRenderButton = document.getElementById('prop-render');

if (propTxInput) {
  const storedTx = localStorage.getItem('meshmapPropTxPower');
  if (storedTx !== null) propTxInput.value = storedTx;
  propTxInput.addEventListener('input', () => {
    localStorage.setItem('meshmapPropTxPower', propTxInput.value);
    updatePropagationSummary();
    markPropagationDirty();
  });
}

if (propTxGainInput) {
  const storedTxGain = localStorage.getItem('meshmapPropTxGain');
  if (storedTxGain !== null) propTxGainInput.value = storedTxGain;
  propTxGainInput.addEventListener('input', () => {
    localStorage.setItem('meshmapPropTxGain', propTxGainInput.value);
    updatePropagationSummary();
    markPropagationDirty();
  });
}

if (propOpacityInput) {
  const storedOpacity = localStorage.getItem('meshmapPropOpacity');
  if (storedOpacity !== null) propOpacityInput.value = storedOpacity;
  propOpacityInput.addEventListener('input', () => {
    localStorage.setItem('meshmapPropOpacity', propOpacityInput.value);
    if (propagationRaster) {
      propagationRaster.setOpacity(Number(propOpacityInput.value));
    }
    if (propagationLastConfig) {
      propagationLastConfig.opacity = Number(propOpacityInput.value);
    }
  });
}

if (propModelSelect) {
  const storedModel = localStorage.getItem('meshmapPropModel');
  if (storedModel && PROP_MODELS[storedModel]) {
    propModelSelect.value = storedModel;
  }
  propModelSelect.addEventListener('change', () => {
    localStorage.setItem('meshmapPropModel', propModelSelect.value);
    updatePropagationSummary();
    markPropagationDirty();
  });
}

if (propTerrainInput) {
  const storedTerrain = localStorage.getItem('meshmapPropTerrain');
  if (storedTerrain !== null) propTerrainInput.checked = storedTerrain === 'true';
  propTerrainInput.addEventListener('change', () => {
    localStorage.setItem('meshmapPropTerrain', propTerrainInput.checked ? 'true' : 'false');
    updatePropagationSummary();
    markPropagationDirty();
  });
}

if (propTxAglInput) {
  const storedTxAgl = localStorage.getItem('meshmapPropTxAgl');
  if (storedTxAgl !== null) propTxAglInput.value = storedTxAgl;
  propTxAglInput.addEventListener('input', () => {
    localStorage.setItem('meshmapPropTxAgl', propTxAglInput.value);
    updatePropagationSummary();
    markPropagationDirty();
  });
}

if (propRxAglInput) {
  const storedRxAgl = localStorage.getItem('meshmapPropRxAgl');
  if (storedRxAgl !== null) propRxAglInput.value = storedRxAgl;
  propRxAglInput.addEventListener('input', () => {
    localStorage.setItem('meshmapPropRxAgl', propRxAglInput.value);
    updatePropagationSummary();
    markPropagationDirty();
  });
}

if (propTxMslInput) {
  const storedTxMsl = localStorage.getItem('meshmapPropTxMsl');
  if (storedTxMsl !== null) propTxMslInput.value = storedTxMsl;
  propTxMslInput.addEventListener('input', () => {
    localStorage.setItem('meshmapPropTxMsl', propTxMslInput.value);
    updatePropagationSummary();
    markPropagationDirty();
  });
}

if (propRxMslInput) {
  const storedRxMsl = localStorage.getItem('meshmapPropRxMsl');
  if (storedRxMsl !== null) propRxMslInput.value = storedRxMsl;
  propRxMslInput.addEventListener('input', () => {
    localStorage.setItem('meshmapPropRxMsl', propRxMslInput.value);
    updatePropagationSummary();
    markPropagationDirty();
  });
}

if (propMinRxInput) {
  const storedMinRx = localStorage.getItem('meshmapPropMinRx');
  if (storedMinRx !== null) propMinRxInput.value = storedMinRx;
  propMinRxInput.addEventListener('input', () => {
    localStorage.setItem('meshmapPropMinRx', propMinRxInput.value);
    updatePropagationSummary();
    markPropagationDirty();
  });
}

if (propAutoRangeInput) {
  const storedAutoRange = localStorage.getItem('meshmapPropAutoRange');
  if (storedAutoRange !== null) propAutoRangeInput.checked = storedAutoRange === 'true';
  propAutoRangeInput.addEventListener('change', () => {
    localStorage.setItem('meshmapPropAutoRange', propAutoRangeInput.checked ? 'true' : 'false');
    if (propRangeFactorInput) {
      propRangeFactorInput.disabled = propAutoRangeInput.checked;
    }
    updatePropagationSummary();
    markPropagationDirty();
  });
  if (propRangeFactorInput) {
    propRangeFactorInput.disabled = propAutoRangeInput.checked;
  }
}

if (propMultiOriginInput) {
  const storedMulti = localStorage.getItem('meshmapPropMultiOrigin');
  if (storedMulti !== null) propMultiOriginInput.checked = storedMulti === 'true';
  propMultiOriginInput.addEventListener('change', () => {
    localStorage.setItem('meshmapPropMultiOrigin', propMultiOriginInput.checked ? 'true' : 'false');
    if (!propMultiOriginInput.checked && propagationOrigins.length > 1) {
      const first = propagationOrigins[0];
      clearPropagationOrigins();
      propagationOrigins = [first];
      upsertPropagationOriginMarker(first);
      updatePropagationSummary();
      markPropagationDirty('Multi-origin disabled. Keeping first origin only.');
    } else {
      markPropagationDirty();
      if (propagationActive && propMultiOriginInput.checked && !propagationOrigins.length) {
        setPropStatus('Multi-origin enabled. Click nodes or the map to add transmitters.');
      }
    }
  });
}

if (propFadeMarginInput) {
  const storedFade = localStorage.getItem('meshmapPropFadeMargin');
  if (storedFade !== null) propFadeMarginInput.checked = storedFade === 'true';
  propFadeMarginInput.addEventListener('change', () => {
    localStorage.setItem('meshmapPropFadeMargin', propFadeMarginInput.checked ? 'true' : 'false');
    markPropagationDirty();
  });
}

if (propWebGpuInput) {
  const supported = !!navigator.gpu;
  propWebGpuInput.disabled = !supported;
  const storedWebGpu = localStorage.getItem('meshmapPropWebGpu');
  if (storedWebGpu !== null) propWebGpuInput.checked = storedWebGpu === 'true';
  if (!supported) propWebGpuInput.checked = false;
  propWebGpuInput.addEventListener('change', () => {
    localStorage.setItem('meshmapPropWebGpu', propWebGpuInput.checked ? 'true' : 'false');
    markPropagationDirty();
    if (propagationActive && propWebGpuInput.checked && !supported) {
      setPropStatus('WebGPU not supported in this browser.');
    }
  });
}

if (propClearOriginsButton) {
  propClearOriginsButton.addEventListener('click', () => {
    clearPropagationOrigins();
    resetPropagationRaster();
    setPropStatus('Select a node or click the map to set a transmitter.');
    updatePropagationSummary();
  });
}

if (propAutoResInput) {
  const storedAutoRes = localStorage.getItem('meshmapPropAutoRes');
  if (storedAutoRes !== null) propAutoResInput.checked = storedAutoRes === 'true';
  propAutoResInput.addEventListener('change', () => {
    localStorage.setItem('meshmapPropAutoRes', propAutoResInput.checked ? 'true' : 'false');
    if (propMaxCellsInput) {
      propMaxCellsInput.disabled = !propAutoResInput.checked;
    }
    updatePropagationSummary();
    markPropagationDirty();
  });
  if (propMaxCellsInput) {
    propMaxCellsInput.disabled = !propAutoResInput.checked;
  }
}

if (propMaxCellsInput) {
  const storedMaxCells = localStorage.getItem('meshmapPropMaxCells');
  if (storedMaxCells !== null) propMaxCellsInput.value = storedMaxCells;
  propMaxCellsInput.addEventListener('input', () => {
    localStorage.setItem('meshmapPropMaxCells', propMaxCellsInput.value);
    updatePropagationSummary();
    markPropagationDirty();
  });
}

if (propGridInput) {
  const storedGrid = localStorage.getItem('meshmapPropGrid');
  if (storedGrid !== null) propGridInput.value = storedGrid;
  propGridInput.addEventListener('input', () => {
    localStorage.setItem('meshmapPropGrid', propGridInput.value);
    updatePropagationSummary();
    markPropagationDirty();
  });
}

if (propSampleInput) {
  const storedSample = localStorage.getItem('meshmapPropSample');
  if (storedSample !== null) propSampleInput.value = storedSample;
  propSampleInput.addEventListener('input', () => {
    localStorage.setItem('meshmapPropSample', propSampleInput.value);
    updatePropagationSummary();
    markPropagationDirty();
  });
}

if (propRangeFactorInput) {
  const storedRange = localStorage.getItem('meshmapPropRangeFactor');
  if (storedRange !== null) propRangeFactorInput.value = storedRange;
  propRangeFactorInput.addEventListener('input', () => {
    localStorage.setItem('meshmapPropRangeFactor', propRangeFactorInput.value);
    updatePropagationSummary();
    markPropagationDirty();
  });
}

if (propRenderButton) {
  propRenderButton.addEventListener('click', () => {
    renderPropagationRaster();
  });
}

if (propToggle) {
  propToggle.addEventListener('click', () => {
    setPropActive(!propagationActive);
    if (propagationActive) {
      updatePropagationSummary();
      if (propagationOrigins.length) {
        const label = propagationOrigins.length === 1 ? 'Origin set.' : `${propagationOrigins.length} origins set.`;
        setPropStatus(`${label} Click "Render prop" to calculate coverage.`);
      }
    }
  });
}

map.on('moveend', () => {
  refreshViewportLayers();
  scheduleWeatherWindRefresh();
});
map.on('zoomend', () => {
  refreshViewportLayers();
  scheduleWeatherWindRefresh();
});

map.on('click', (ev) => {
  const target = ev && ev.originalEvent ? ev.originalEvent.target : null;
  if (target && target.closest && target.closest('.leaflet-popup')) {
    return;
  }
  if (losActive) {
    if (losLocked && losSelectedPointIndex != null) {
      const idx = losSelectedPointIndex;
      if (losPointMarkers[idx]) {
        losPointMarkers[idx].setLatLng(ev.latlng);
      }
      const affected = updateLosPointPosition(idx, ev.latlng);
      setLosSelectedPoint(null);
      recomputeLosSegments(affected, {
        allowNetwork: true,
        forceNetwork: true,
        finalIndex: affected && affected.length ? affected[affected.length - 1] : losActiveSegmentIndex
      });
      return;
    }
    handleLosPoint(ev.latlng);
    return;
  }
  if (propagationActive) {
    setPropagationOrigin(ev.latlng);
  }
});
