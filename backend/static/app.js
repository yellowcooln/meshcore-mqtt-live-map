    window.__meshmapStarted = true;
    const config = document.body ? document.body.dataset : {};
    const queryParams = new URLSearchParams(window.location.search);
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
    const queryLat = parseNumberParam(queryParams.get('lat') ?? queryParams.get('latitude'));
    const queryLon = parseNumberParam(queryParams.get('lon') ?? queryParams.get('lng') ?? queryParams.get('long') ?? queryParams.get('longitude'));
    const queryZoom = parseNumberParam(queryParams.get('zoom'));
    const queryLayer = String(queryParams.get('layer') || queryParams.get('map') || '').toLowerCase();
    const queryHistoryVisible = parseBoolParam(queryParams.get('history'));
    const queryHeatVisible = parseBoolParam(queryParams.get('heat'));
    const queryLabelsVisible = parseBoolParam(queryParams.get('labels'));
    const queryNodesVisible = parseBoolParam(queryParams.get('nodes'));
    const queryLegendVisible = parseBoolParam(queryParams.get('legend'));
    const queryMenuVisible = parseBoolParam(
      queryParams.get('menu') || queryParams.get('hud') || queryParams.get('panel')
    );
    const queryUnits = String(queryParams.get('units') || queryParams.get('unit') || '').toLowerCase();
    const queryHistoryFilter = parseHistoryFilterParam(
      queryParams.get('history_filter') || queryParams.get('historyFilter') || queryParams.get('historyfilter')
    );
    const reportError = typeof window.__meshmapReportError === 'function'
      ? window.__meshmapReportError
      : (message) => console.warn(message);

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
    const mapRadiusShow = String(config.mapRadiusShow).toLowerCase() === 'true';
    let baseLayer = (config.mapDefaultLayer || 'light').toLowerCase();
    const validLayers = new Set(['dark', 'topo', 'light']);
    if (validLayers.has(queryLayer)) {
      baseLayer = queryLayer;
    }
    if (!validLayers.has(baseLayer)) {
      baseLayer = 'light';
    }

    const map = L.map('map', { zoomControl: false }).setView([mapStartLat, mapStartLon], mapStartZoom);
    L.control.zoom({ position: 'bottomright' }).addTo(map);
    const lightTiles = L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 19,
      attribution: '&copy; OpenStreetMap contributors'
    }).addTo(map);
    const darkTiles = L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
      maxZoom: 19,
      attribution: '&copy; OpenStreetMap contributors &copy; CARTO'
    });
    const topoTiles = L.tileLayer('https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png', {
      maxZoom: 17,
      attribution: '&copy; OpenStreetMap contributors &copy; OpenTopoMap'
    });
    let mapRadiusCircle = null;
    if (mapRadiusShow && mapRadiusKm > 0) {
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
    const storedLayer = localStorage.getItem('meshmapBaseLayer');
    if (!validLayers.has(queryLayer) && (storedLayer === 'dark' || storedLayer === 'topo' || storedLayer === 'light')) {
      baseLayer = storedLayer;
    }

    const prodMode = String(config.prodMode).toLowerCase() === 'true';
    const apiToken = config.prodToken || '';
    const tokenHeaders = () => (prodMode && apiToken ? { 'x-access-token': apiToken } : {});
    const withToken = (path) => {
      if (!prodMode || !apiToken) return path;
      const url = new URL(path, window.location.origin);
      url.searchParams.set('token', apiToken);
      return `${url.pathname}${url.search}`;
    };

    const markers = new Map();   // device_id -> Leaflet marker
    const polylines = new Map(); // device_id -> Leaflet polyline
    const markerLayer = L.layerGroup().addTo(map);
    const trailLayer = L.layerGroup().addTo(map);
    let nodesVisible = true;
    const routeLines = new Map(); // route_id -> { line, timeout }
    const deviceMeta = new Map(); // device_id -> { lat, lon, name }
    const historyLines = new Map(); // edge_id -> { line, count }
    const historyCache = new Map(); // edge_id -> raw edge data
    const historyLayer = L.layerGroup();
    const routeLayer = L.layerGroup().addTo(map);
    const losElevationUrl = config.losElevationUrl || 'https://api.opentopodata.org/v1/srtm90m';
    const losSampleMin = Number(config.losSampleMin) || 10;
    const losSampleMax = Number(config.losSampleMax) || 80;
    const losSampleStepMeters = Number(config.losSampleStepMeters) || 250;
    const losPeaksMax = Number(config.losPeaksMax) || 4;
    const mqttOnlineSeconds = Number(config.mqttOnlineSeconds) || 300;
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
    const coverageLayer = L.layerGroup();
    let coverageVisible = false;
    let coverageData = null;
    let losActive = false;
    let losPoints = [];
    let losLine = null;
    let losSuggestion = null;
    let losPeakMarkers = [];
    let losHoverMarker = null;
    let losActivePeak = null;
    let losLocked = false;
    let lastLosDistance = null;
    let lastLosStatusMeta = null;
    const losProfile = document.getElementById('los-profile');
    const losProfileSvg = document.getElementById('los-profile-svg');
    const losProfileTooltip = document.getElementById('los-profile-tooltip');
    const losLegendGroup = document.getElementById('legend-los-group');
    const losClearButton = document.getElementById('los-clear');
    const losPanel = document.getElementById('los-panel');
    const propPanel = document.getElementById('prop-panel');
    const historyPanel = document.getElementById('history-panel');
    const historyLegendGroup = document.getElementById('legend-history-group');
    const historyPanelLabel = document.getElementById('history-panel-label');
    let losProfileData = [];
    let losProfileMeta = null;
    const deviceData = new Map();
    const searchInput = document.getElementById('node-search');
    const searchResults = document.getElementById('node-search-results');
    const nodeSizeInput = document.getElementById('node-size');
    const nodeSizeValue = document.getElementById('node-size-value');
    let searchMatches = [];
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
    const historyLinkSizeInput = document.getElementById('history-link-size');
    const historyLinkSizeValue = document.getElementById('history-link-size-value');
    let historyWindowSeconds = null;
    const historyToolVersion = '1';
    localStorage.setItem('meshmapHistoryToolVersion', historyToolVersion);
    let historyVisible = false;
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
    let heatVisible = storedHeat !== 'false';
    if (storedHeat === null) {
      localStorage.setItem('meshmapShowHeat', 'true');
    }
    const mqttWindowLabel = document.getElementById('mqtt-online-label');
    if (mqttWindowLabel) {
      mqttWindowLabel.textContent = `MQTT online (last ${formatOnlineWindow(mqttOnlineSeconds)})`;
    }

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

    function setStats() {
      const onlineCount = Array.from(deviceData.values()).filter(isMqttOnline).length;
      document.getElementById('stats').textContent = `${markers.size} active devices • ${onlineCount} MQTT online • ${routeLines.size} routes • ${historyLines.size} history`;
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
        return data;
      } catch (err) {
        const errorMsg = err && err.message ? err.message : String(err);
        reportError(`Failed to fetch coverage data: ${errorMsg}`);
        return null;
      }
    }

    function renderCoverage(data) {
      coverageLayer.clearLayers();
      if (!data || !Array.isArray(data)) {
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
          const totalSamples = tile.heard + tile.lost;
          if (totalSamples === 0) continue;
          const heardRatio = totalSamples > 0 ? tile.heard / totalSamples : 0;
          const color = successRateToColor(heardRatio);
          const baseOpacity = 0.75 * Math.min(1, totalSamples / 10);
          const opacity = heardRatio > 0 ? baseOpacity * heardRatio : Math.max(baseOpacity, 0.4);
          const rect = L.rectangle([[minLat, minLon], [maxLat, maxLon]], {
            color: color,
            weight: 1,
            fillOpacity: Math.max(opacity, 0.2),
            fillColor: color
          });
          let details = `Heard: ${tile.heard} Lost: ${tile.lost} (${(100 * heardRatio).toFixed(0)}%)`;
          if (tile.paths.size > 0) {
            const repeaters = Array.from(tile.paths).slice(0, 5).map(r => r.toUpperCase());
            details += `<br/>Repeaters: ${repeaters.join(', ')}${tile.paths.size > 5 ? '...' : ''}`;
          }
          if (tile.snr !== null && tile.snr !== undefined) {
            details += `<br/>SNR: ${tile.snr} dB`;
          }
          if (tile.rssi !== null && tile.rssi !== undefined) {
            details += `<br/>RSSI: ${tile.rssi} dBm`;
          }
          rect.bindPopup(details, { maxWidth: 320 });
          coverageLayer.addLayer(rect);
          rendered++;
        } catch (err) {
          // Silently skip invalid tiles
        }
      }
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
        return;
      }
      if (visible) {
        if (!map.hasLayer(coverageLayer)) {
          coverageLayer.addTo(map);
        }
        if (!coverageData) {
          fetchCoverageData().then(data => {
            if (data && Array.isArray(data)) {
              coverageData = data;
              if (data.length === 0) {
                reportError('Coverage database appears to be empty. Add coverage data to your coverage map server.');
              }
              renderCoverage(data);
            } else {
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
      }
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
      } else if (map.hasLayer(markerLayer)) {
        map.removeLayer(markerLayer);
        if (map.hasLayer(trailLayer)) {
          map.removeLayer(trailLayer);
        }
        if (map.hasLayer(routeLayer)) {
          map.removeLayer(routeLayer);
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
      } else if (map.hasLayer(trailLayer)) {
        map.removeLayer(trailLayer);
      } else {
        if (map.hasLayer(routeLayer)) {
          map.removeLayer(routeLayer);
        }
        if (map.hasLayer(historyLayer)) {
          map.removeLayer(historyLayer);
          clearHistoryLayer();
        }
        if (heatLayer && map.hasLayer(heatLayer)) {
          map.removeLayer(heatLayer);
        }
      }
    }

    function setHistoryVisible(visible) {
      historyVisible = visible;
      const btn = document.getElementById('history-toggle');
      if (btn) {
        btn.classList.toggle('active', visible);
        btn.textContent = visible ? 'History: on' : 'History tool';
      }
      if (historyPanel) {
        historyPanel.classList.toggle('active', visible);
        if (visible) {
          historyPanel.removeAttribute('hidden');
          historyPanel.style.display = 'block';
        } else {
          historyPanel.setAttribute('hidden', 'hidden');
          historyPanel.style.display = 'none';
        }
      }
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

    function getLastSeenTs(d) {
      return d.last_seen_ts || d.ts;
    }

    function isMqttOnline(d) {
      if (d.mqtt_forced) return true;
      const lastSeen = d.mqtt_seen_ts || null;
      if (!lastSeen) return false;
      return (Date.now() / 1000 - lastSeen) <= mqttOnlineSeconds;
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
        m.setTooltipContent(label);
      } else {
        m.bindTooltip(label, {
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
        item.innerHTML = `<span>${deviceDisplayName(d)}</span><span class="node-search-id">${id.slice(0, 8)}…</span>`;
        item.addEventListener('click', () => focusDevice(id));
        searchResults.appendChild(item);
      });
      searchResults.hidden = false;
    }

    function focusDevice(id) {
      const marker = markers.get(id);
      const d = deviceData.get(id);
      if (!marker || !d) return;
      const targetZoom = Math.max(map.getZoom(), 13);
      map.flyTo(marker.getLatLng(), targetZoom, { duration: 0.6 });
      marker.openPopup();
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
      if (historyVisible && historyPanel && historyPanel.classList.contains('active')) panels.push(historyPanel);
      if (propagationActive && propPanel.classList.contains('active')) panels.push(propPanel);
      [losPanel, historyPanel, propPanel].forEach(panel => {
        if (!panel) return;
        panel.style.top = '';
        panel.style.bottom = '';
      });
      if (!panels.length) return;
      const isMobile = window.matchMedia('(max-width: 900px)').matches;
      if (isMobile) {
        let bottom = 12;
        panels.slice().reverse().forEach(panel => {
          panel.style.bottom = `${bottom}px`;
          bottom += (panel.offsetHeight || 0) + 12;
        });
        return;
      }
      let top = 18;
      panels.forEach(panel => {
        panel.style.top = `${top}px`;
        top += (panel.offsetHeight || 0) + 12;
      });
    }
    function clearLos() {
      losPoints = [];
      losLine = null;
      losSuggestion = null;
      losLocked = false;
      lastLosStatusMeta = null;
      losLayer.clearLayers();
      setLosStatus('');
      clearLosProfile();
      clearLosPeaks();
      clearLosHoverMarker();
    }

    function setLosActive(active) {
      losActive = active;
      const btn = document.getElementById('los-toggle');
      if (btn) {
        btn.classList.toggle('active', active);
        btn.textContent = active ? 'LOS: click 2 points' : 'LOS tool';
      }
      if (losLegendGroup) {
        losLegendGroup.classList.toggle('active', active);
      }
      if (losPanel) {
        losPanel.classList.toggle('active', active);
      }
      if (!active) {
        clearLos();
      } else {
        losLocked = false;
        setLosStatus('LOS: select first point (Shift+click or long-press nodes)');
      }
      layoutSidePanels();
    }

    function renderLosProfile(profile, blocked) {
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
      let minElev = Infinity;
      let maxElev = -Infinity;
      profile.forEach(item => {
        const terrain = Number(item[1]);
        const los = Number(item[2]);
        if (!Number.isNaN(terrain)) {
          minElev = Math.min(minElev, terrain);
          maxElev = Math.max(maxElev, terrain);
        }
        if (!Number.isNaN(los)) {
          minElev = Math.min(minElev, los);
          maxElev = Math.max(maxElev, los);
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
      const losColor = blocked ? '#ef4444' : '#22c55e';
      losProfileSvg.setAttribute('viewBox', `0 0 ${width} ${height}`);
      losProfileSvg.innerHTML = `
        <path class="los-profile-terrain" d="${terrainPath}"></path>
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
        blocked
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
      let status = `LOS: ${distance} • ${obstruction}`;
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
      losProfileTooltip.hidden = false;
      losProfileTooltip.textContent = `Distance ${formatDistanceMeters(clampedDistance)} • Terrain ${formatElevationMeters(terrain)} • LOS ${formatElevationMeters(losLineValue)}`;
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
      if (!losProfileMeta || !losPoints || losPoints.length < 2) return;
      const total = losProfileMeta.totalDistance;
      const clamped = Math.min(Math.max(distanceMeters, 0), total);
      const t = total > 0 ? (clamped / total) : 0;
      const start = losPoints[0];
      const end = losPoints[1];
      const lat = start.lat + (end.lat - start.lat) * t;
      const lon = start.lng + (end.lng - start.lng) * t;
      const label = updateLosPeakHighlight(clamped);
      const tooltip = label
        ? `${label} • ${formatDistanceMeters(clamped)}`
        : `LOS point • ${formatDistanceMeters(clamped)}`;
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
      if (!losPoints || losPoints.length < 2 || distanceMeters == null || !losProfileMeta) return;
      const total = losProfileMeta.totalDistance || 0;
      const t = total > 0 ? Math.min(Math.max(distanceMeters / total, 0), 1) : 0;
      const start = losPoints[0];
      const end = losPoints[1];
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
      if (!latlng || losPoints.length < 2) return;
      if (!losProfileMeta || !losProfileData || losProfileData.length < 2) return;
      const start = losPoints[0];
      const end = losPoints[1];
      const dLat = end.lat - start.lat;
      const dLon = end.lng - start.lng;
      const denom = (dLat * dLat) + (dLon * dLon);
      if (denom === 0) return;
      let t = ((latlng.lat - start.lat) * dLat + (latlng.lng - start.lng) * dLon) / denom;
      t = Math.min(Math.max(t, 0), 1);
      const totalDistance = haversineMeters(start.lat, start.lng, end.lat, end.lng);
      updateLosProfileAtDistance(totalDistance * t);
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

    async function runLosCheckServer(a, b) {
      const params = new URLSearchParams({
        lat1: a.lat.toFixed(6),
        lon1: a.lng.toFixed(6),
        lat2: b.lat.toFixed(6),
        lon2: b.lng.toFixed(6)
      });
      const res = await fetch(`/los?${params.toString()}`);
      const data = await res.json();
      if (!data.ok) {
        lastLosStatusMeta = null;
        setLosStatus(`LOS: ${data.error || 'failed'}`);
        if (losLine) {
          losLine.setStyle({ color: '#9ca3af', weight: 4, opacity: 0.8, dashArray: '6 10' });
        }
        clearLosProfile();
        clearLosPeaks();
        return false;
      }
      const blocked = data.blocked;
      const meters = data.distance_m != null ? Number(data.distance_m) : null;
      lastLosStatusMeta = {
        distance_m: Number.isFinite(meters) ? meters : null,
        blocked,
        obstruction_m: data.max_obstruction_m,
        suggested: false,
        suggested_clear: false
      };
      if (losSuggestion) {
        losLayer.removeLayer(losSuggestion);
        losSuggestion = null;
      }
      renderLosPeaks(data.peaks);
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
        lastLosStatusMeta.suggested = true;
        lastLosStatusMeta.suggested_clear = !!s.clear;
      }
      setLosStatus(buildLosStatus(lastLosStatusMeta));
      renderLosProfile(data.profile, blocked);
      if (losLine) {
        losLine.setStyle({
          color: blocked ? '#ef4444' : '#22c55e',
          weight: 5,
          opacity: 0.9,
          dashArray: blocked ? '4 10' : null
        });
      }
      return true;
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
      if (!txInput || !opacityInput || !modelSelect || !terrainInput || !txAglInput || !rxAglInput || !txMslInput || !rxMslInput || !minRxInput || !autoRangeInput || !fadeMarginInput || !webGpuInput || !autoResInput || !maxCellsInput || !gridInput || !sampleInput || !rangeFactorInput) {
        return null;
      }
      const txPower = Number(txInput.value);
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
      const effectiveTxPower = config.txPower + PROP_DEFAULTS.txAntennaGainDb;
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
      const effectiveTxPower = config.txPower + PROP_DEFAULTS.txAntennaGainDb;
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
          return `
            <div class="popup-sample">
              <strong>${label}</strong> • ${when}<br/>
              Origin: ${origin}<br/>
              Receiver: ${receiver}<br/>
              Route: ${routeMode}<br/>
              Hash: ${shortHash(sample.message_hash)}
            </div>
          `;
        }).join('')
        : '<div class="popup-sample">No packet details yet.</div>';

      return `
        <span class="popup-title">History edge</span>
        <span class="small">
          Count: ${count}<br/>
          Last Seen: ${lastSeen}<br/>
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

    async function fetchElevations(points) {
      if (!losElevationUrl) {
        return { ok: false, error: 'no_elevation_url' };
      }
      const results = new Array(points.length);
      const chunkSize = 100;
      for (let start = 0; start < points.length; start += chunkSize) {
        const chunk = points.slice(start, start + chunkSize);
        const locations = chunk.map(p => `${p.lat},${p.lon}`).join('|');
        const url = `${losElevationUrl}?locations=${encodeURIComponent(locations)}`;
        let payload;
        try {
          const res = await fetch(url);
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
          results[start + idx] = Number(entry.elevation);
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
      const title = d.name
        ? `<span class="popup-title">${d.name}</span><span class="popup-id">${deviceLabel}</span>`
        : `<span class="popup-title popup-id">${deviceLabel}</span>`;
      const role = resolveRole(d);
      const roleLabel = role === 'unknown' ? '' : role.charAt(0).toUpperCase() + role.slice(1);
      const mqttLabel = isMqttOnline(d) ? 'Online' : 'Offline';
      return `
        ${title}
        <span class="small">
          ${roleLabel ? `Role: ${roleLabel}<br/>` : ``}
          Location: ${d.lat.toFixed(6)}, ${d.lon.toFixed(6)}<br/>
          Last Contact: ${lastContact}<br/>
          MQTT: ${mqttLabel}<br/>
          ${d.rssi != null ? `RSSI: ${d.rssi}<br/>` : ``}
          ${d.snr != null ? `SNR: ${d.snr}<br/>` : ``}
        </span>
      `;
    }

    function upsertDevice(d, trail) {
      const id = d.device_id;
      const latlng = [d.lat, d.lon];
      const role = resolveRole(d);
      const style = markerStyleForDevice(d);
      deviceData.set(id, d);
      deviceMeta.set(id, { lat: d.lat, lon: d.lon, name: d.name });

      // marker
      if (!markers.has(id)) {
        const m = L.circleMarker(latlng, style).addTo(markerLayer);
        m.bindPopup(makePopup(d), {
          maxWidth: 260,
          maxHeight: 320,
          autoPan: false,
          keepInView: false
        });
        m.__suppressClick = false;
        m.__longPressTimer = null;
        m.__longPressFired = false;
        const triggerLosSelect = () => {
          if (!losActive) {
            setLosActive(true);
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
      } else {
        const m = markers.get(id);
        m.setLatLng(latlng);
        m.setPopupContent(makePopup(d));
        if (m.setStyle) m.setStyle(style);
        updateMarkerLabel(m, d);
      }

      // trail polyline (skip companions)
      if (role !== 'companion' && Array.isArray(trail) && trail.length >= 2) {
        const points = trail.map(p => [p[0], p[1]]);
        if (!polylines.has(id)) {
          const pl = L.polyline(points, {
            color: '#38bdf8',
            weight: 3,
            opacity: 0.85,
            className: 'trail-animated'
          }).addTo(trailLayer);
          polylines.set(id, pl);
        } else {
          const pl = polylines.get(id);
          pl.setLatLngs(points);
          if (pl.setStyle) {
            pl.setStyle({ color: '#38bdf8', weight: 3, opacity: 0.85 });
          }
        }
      } else if (polylines.has(id)) {
        trailLayer.removeLayer(polylines.get(id));
        polylines.delete(id);
      }

      setStats();
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
      setStats();
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
      setStats();
    }

    function removeRoutes(ids) {
      ids.forEach(id => {
        const entry = routeLines.get(id);
        if (!entry) return;
        if (entry.timeout) clearTimeout(entry.timeout);
        routeLayer.removeLayer(entry.line);
        routeLines.delete(id);
      });
      setStats();
    }

    function clearRoutes() {
      routeLines.forEach(entry => {
        if (entry.timeout) clearTimeout(entry.timeout);
        routeLayer.removeLayer(entry.line);
      });
      routeLines.clear();
      setStats();
    }

    function clearHistoryLayer() {
      historyLines.forEach(entry => {
        if (!entry || !entry.line) return;
        historyLayer.removeLayer(entry.line);
      });
      historyLines.clear();
      refreshHistoryStyles();
      setStats();
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
      setStats();
    }

    function historyWeight(count) {
      const n = Math.max(1, Number(count) || 1);
      const base = Math.min(6, 0.9 + Math.log1p(n) * 1.1);
      return clampNumber(base * historyLinkScale, 0.4, 12);
    }

    function computeHistoryThresholds() {
      const counts = [];
      historyCache.forEach(edge => {
        if (edge && Number.isFinite(edge.count)) {
          counts.push(edge.count);
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
        const count = Number(entry.count) || 1;
        const shouldShow = historyFilterAllows(count, thresholds);
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
        const line = L.polyline(points, { color: '#7dd3fc', weight: 2, opacity: 0.6 }).addTo(historyLayer);
        entry = { line, count: Number(edge.count) || 1, recent: [], lastTs: null };
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
      refreshHistoryStyles();
    }

    function renderHistoryFromCache() {
      historyCache.forEach(edge => renderHistoryEdge(edge));
      updateHistoryRendering();
      setStats();
    }

    function upsertHistoryEdge(edge) {
      const id = historyEdgeId(edge);
      if (!id) return;
      const edgeData = { ...edge, id };
      historyCache.set(id, edgeData);
      if (!historyVisible || !nodesVisible) {
        setStats();
        return;
      }
      renderHistoryEdge(edgeData);
    }

    function updateHistoryWindowLabel(seconds) {
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

    function upsertRoute(r, skipHeat = false) {
      if (!r || !Array.isArray(r.points) || r.points.length < 2) return;
      const id = r.id || `route-${Date.now()}-${Math.random()}`;
      const points = r.points.map(p => [p[0], p[1]]);
      const routeMode = r.route_mode || 'path';
      const isFanout = routeMode === 'fanout';
      const payloadType = Number(r.payload_type);
      const isAdvert = payloadType === 4;
      const isTrace = payloadType === 8 || payloadType === 9;
      const isMessage = payloadType === 2 || payloadType === 5;
      const style = {
        color: isAdvert
          ? '#2ecc71'
          : (isTrace ? '#ff7a1a' : (isMessage ? '#2b8cff' : (isFanout ? '#2b8cff' : '#ff7a1a'))),
        weight: isFanout ? 4 : 5,
        opacity: isFanout ? 0.85 : 0.9,
        lineCap: 'butt',
        lineJoin: 'miter'
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

      let entry = routeLines.get(id);
      if (!entry) {
        const line = L.polyline(points, style).addTo(routeLayer);
        entry = { line, timeout: null };
        routeLines.set(id, entry);
      } else {
        entry.line.setLatLngs(points);
        entry.line.setStyle(style);
      }
      const lineEl = entry.line.getElement();
      if (lineEl) {
        lineEl.classList.add('route-animated');
      }

      if (entry.timeout) clearTimeout(entry.timeout);
      if (r.expires_at) {
        const ms = Math.max(1000, (r.expires_at * 1000) - Date.now());
        entry.timeout = setTimeout(() => removeRoutes([id]), ms);
      }

      if (!skipHeat) {
        addHeatPoints(points, r.ts, r.payload_type);
      }
      setStats();
    }

    async function initialSnapshot() {
      try {
        const res = await fetch(withToken('/snapshot'), { headers: tokenHeaders() });
        const snap = await res.json();
        if (snap.devices) {
          for (const [id, d] of Object.entries(snap.devices)) {
            const trail = snap.trails ? snap.trails[id] : null;
            upsertDevice(d, trail);
          }
        }
        if (Array.isArray(snap.heat)) {
          seedHeat(snap.heat);
        }
        if (Array.isArray(snap.routes)) {
          clearRoutes();
          snap.routes.forEach(r => upsertRoute(r, true));
        }
        if (Array.isArray(snap.history_edges)) {
          snap.history_edges.forEach(edge => upsertHistoryEdge(edge));
        }
        if (snap.history_window_seconds != null) {
          historyWindowSeconds = Number(snap.history_window_seconds);
          updateHistoryWindowLabel(historyWindowSeconds);
        }
        setStats();
      } catch (e) {
        console.warn("snapshot failed", e);
      }
    }

    function connectWS() {
      const proto = location.protocol === 'https:' ? 'wss' : 'ws';
      const wsSuffix = (prodMode && apiToken) ? `?token=${encodeURIComponent(apiToken)}` : '';
      const ws = new WebSocket(`${proto}://${location.host}/ws${wsSuffix}`);

      ws.onopen = () => console.log("ws connected");
      ws.onclose = () => {
        console.log("ws disconnected, retrying...");
        setTimeout(connectWS, 1500);
      };

      ws.onmessage = (ev) => {
        const msg = JSON.parse(ev.data);

        if (msg.type === "snapshot") {
          // same shape as /snapshot
          for (const [id, d] of Object.entries(msg.devices || {})) {
            const trail = msg.trails ? msg.trails[id] : null;
            upsertDevice(d, trail);
          }
          clearRoutes();
          if (Array.isArray(msg.heat)) {
            seedHeat(msg.heat);
          }
          if (Array.isArray(msg.routes)) {
            msg.routes.forEach(r => upsertRoute(r, true));
          }
          if (Array.isArray(msg.history_edges)) {
            msg.history_edges.forEach(edge => upsertHistoryEdge(edge));
          }
          if (msg.history_window_seconds != null) {
            historyWindowSeconds = Number(msg.history_window_seconds);
            updateHistoryWindowLabel(historyWindowSeconds);
          }
          setStats();
          return;
        }

        if (msg.type === "update") {
          upsertDevice(msg.device, msg.trail);
          return;
        }

        if (msg.type === "device_seen") {
          const id = msg.device_id;
          const d = deviceData.get(id);
          if (d) {
            if (msg.last_seen_ts) d.last_seen_ts = msg.last_seen_ts;
            if (msg.mqtt_seen_ts) d.mqtt_seen_ts = msg.mqtt_seen_ts;
            deviceData.set(id, d);
            const m = markers.get(id);
            if (m) {
              if (m.setStyle) m.setStyle(markerStyleForDevice(d));
              m.setPopupContent(makePopup(d));
              updateMarkerLabel(m, d);
            }
            setStats();
          }
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
          const edges = Array.isArray(msg.edges) ? msg.edges : [];
          edges.forEach(edge => upsertHistoryEdge(edge));
          setStats();
          return;
        }

        if (msg.type === "history_edges_remove") {
          removeHistoryEdges(msg.edge_ids || []);
          return;
        }

        if (msg.type === "stale") {
          removeDevices(msg.device_ids || []);
          return;
        }
      };
    }

    async function runLosCheck() {
      if (losPoints.length < 2) return;
      const [a, b] = losPoints;
      setLosStatus('LOS: calculating...');
      try {
        const distanceMeters = haversineMeters(a.lat, a.lng, b.lat, b.lng);
        if (distanceMeters <= 0) {
          setLosStatus('LOS: invalid distance');
          return;
        }
        const ok = await runLosCheckServer(a, b);
        if (ok) return;
        setLosStatus('LOS: error');
        if (losLine) {
          losLine.setStyle({ color: '#9ca3af', weight: 4, opacity: 0.8, dashArray: '6 10' });
        }
        clearLosProfile();
        clearLosPeaks();
      } catch (err) {
        console.warn('los failed', err);
        setLosStatus('LOS: error');
        clearLosProfile();
        clearLosPeaks();
      }
    }

    initialSnapshot();
    connectWS();
    setStats();
    setInterval(refreshHeatLayer, 15000);
    setInterval(refreshOnlineMarkers, 30000);
    if ('serviceWorker' in navigator) {
      window.addEventListener('load', () => {
        navigator.serviceWorker.register('/sw.js').catch(() => {});
      });
    }

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

    const shareToggle = document.getElementById('share-toggle');
    if (shareToggle) {
      const resetShareButton = () => {
        shareToggle.classList.remove('copied');
        shareToggle.setAttribute('aria-label', 'Copy share link');
        shareToggle.setAttribute('title', 'Copy share link');
      };
      shareToggle.addEventListener('click', async () => {
        const center = map.getCenter();
        const url = new URL(window.location.href);
        url.searchParams.set('lat', center.lat.toFixed(5));
        url.searchParams.set('lon', center.lng.toFixed(5));
        url.searchParams.set('zoom', String(map.getZoom()));
        url.searchParams.set('layer', baseLayer);
        url.searchParams.set('history', historyVisible ? 'on' : 'off');
        url.searchParams.set('heat', heatVisible ? 'on' : 'off');
        url.searchParams.set('labels', showLabels ? 'on' : 'off');
        url.searchParams.set('nodes', nodesVisible ? 'on' : 'off');
        url.searchParams.set('legend', hud && hud.classList.contains('legend-collapsed') ? 'off' : 'on');
        url.searchParams.set('menu', hud && hud.classList.contains('panel-hidden') ? 'off' : 'on');
        url.searchParams.set('units', distanceUnits);
        url.searchParams.set('history_filter', String(historyFilterMode));
        const shareUrl = url.toString();
        let copied = false;
        try {
          if (navigator.clipboard && navigator.clipboard.writeText) {
            await navigator.clipboard.writeText(shareUrl);
            copied = true;
          }
        } catch (err) {
          copied = false;
        }
        if (!copied) {
          window.prompt('Copy share link:', shareUrl);
        }
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
      if (name === 'dark') {
        map.addLayer(darkTiles);
      } else if (name === 'topo') {
        map.addLayer(topoTiles);
      } else {
        map.addLayer(lightTiles);
      }
      document.body.classList.toggle('dark-map', name === 'dark');
      baseLayer = name;
      localStorage.setItem('meshmapBaseLayer', baseLayer);
      if (mapToggle) {
        mapToggle.textContent = baseLayer === 'dark' ? 'Light map' : 'Dark map';
      }
      if (topoToggle) {
        topoToggle.textContent = baseLayer === 'topo' ? 'Standard map' : 'Topo map';
      }
    }

    if (mapToggle) {
      mapToggle.addEventListener('click', () => {
        setBaseLayer(baseLayer === 'dark' ? 'light' : 'dark');
      });
    }
    if (topoToggle) {
      topoToggle.addEventListener('click', () => {
        setBaseLayer(baseLayer === 'topo' ? 'light' : 'topo');
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
    }
    setUnitsLabel();
    if (unitsToggle) {
      unitsToggle.addEventListener('click', () => {
        const next = distanceUnits === 'mi' ? 'km' : 'mi';
        setDistanceUnits(next);
      });
    }

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

    function handleLosPoint(latlng) {
      if (losLocked || losPoints.length >= 2) {
        setLosStatus('LOS: Clear to start a new path');
        return;
      }
      losPoints.push(latlng);
      L.circleMarker(latlng, {
        radius: 5,
        color: '#fbbf24',
        fillColor: '#fbbf24',
        fillOpacity: 0.9,
        weight: 2
      }).addTo(losLayer);

      if (losPoints.length === 1) {
        setLosStatus('LOS: select second point');
        return;
      }
      if (losPoints.length === 2) {
        losLocked = true;
        losLine = L.polyline([losPoints[0], losPoints[1]], {
          color: '#9ca3af',
          weight: 4,
          opacity: 0.8,
          dashArray: '6 10'
        }).addTo(losLayer);
        losLine.on('mousemove', (ev) => {
          if (ev && ev.latlng) {
            updateLosProfileFromMap(ev.latlng);
          }
        });
        losLine.on('mouseout', clearLosProfileHover);
        runLosCheck();
      }
    }

    if (losClearButton) {
      losClearButton.addEventListener('click', () => {
        clearLos();
        if (losActive) {
          setLosStatus('LOS: select first point (Shift+click or long-press nodes)');
        }
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
    updateNodeSizeUi();
    if (nodeSizeInput) {
      nodeSizeInput.addEventListener('input', (ev) => {
        setNodeMarkerRadius(ev.target.value);
      });
    }

    const historyToggle = document.getElementById('history-toggle');
    if (historyToggle) {
      let initialHistory = false;
      if (queryHistoryVisible !== null) {
        initialHistory = queryHistoryVisible;
      }
      setHistoryVisible(initialHistory);
      historyToggle.addEventListener('click', () => {
        setHistoryVisible(!historyVisible);
      });
    }
    updateHistoryFilterLabel();
    if (historyFilter) {
      historyFilter.addEventListener('input', (ev) => {
        updateHistoryFilter(ev.target.value);
      });
    }
    if (historyLinkSizeInput) {
      historyLinkSizeInput.addEventListener('input', (ev) => {
        updateHistoryLinkScale(ev.target.value);
      });
    }

    const heatToggle = document.getElementById('heat-toggle');
    if (heatToggle) {
      const storedHeatVisible = localStorage.getItem('meshmapShowHeat');
      let initialHeat = storedHeatVisible !== null ? storedHeatVisible === 'true' : true;
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
    if (coverageToggle) {
      const storedCoverageVisible = localStorage.getItem('meshmapShowCoverage');
      let initialCoverage = storedCoverageVisible !== null ? storedCoverageVisible === 'true' : false;
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

    const propToggle = document.getElementById('prop-toggle');
    const propTxInput = document.getElementById('prop-txpower');
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

    map.on('click', (ev) => {
      const target = ev && ev.originalEvent ? ev.originalEvent.target : null;
      if (target && target.closest && target.closest('.leaflet-popup')) {
        return;
      }
      if (losActive) {
        handleLosPoint(ev.latlng);
        return;
      }
      if (propagationActive) {
        setPropagationOrigin(ev.latlng);
      }
    });
