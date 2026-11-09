const TILE_URL = "https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png";
const TILE_SIZE = 256;
const tileCache = new Map();
function clamp(value, min, max) { return Math.min(max, Math.max(min, value)); }
function lonLatToTile(lon, lat, zoom) {
  const latRad = lat * Math.PI / 180;
  const n = Math.pow(2, zoom);
  const x = n * ((lon + 180) / 360);
  const y = n * (1 - (Math.log(Math.tan(latRad) + 1 / Math.cos(latRad)) / Math.PI)) / 2;
  const tileX = Math.floor(x);
  const tileY = Math.floor(y);
  const px = Math.floor((x - tileX) * TILE_SIZE);
  const py = Math.floor((y - tileY) * TILE_SIZE);
  return { tileX, tileY, px: clamp(px, 0, TILE_SIZE - 1), py: clamp(py, 0, TILE_SIZE - 1) };
}
async function fetchTile(z, x, y) {
  const n = Math.pow(2, z);
  if (x < 0 || y < 0 || x >= n || y >= n) return null;
  const key = `${z}/${x}/${y}`;
  if (tileCache.has(key)) return tileCache.get(key);
  const url = TILE_URL.replace("{z}", z).replace("{x}", x).replace("{y}", y);
  try {
    const res = await fetch(url);
    if (!res.ok) { tileCache.set(key, null); return null; }
    const blob = await res.blob();
    const bitmap = await createImageBitmap(blob);
    const canvas = new OffscreenCanvas(TILE_SIZE, TILE_SIZE);
    const ctx = canvas.getContext("2d");
    ctx.drawImage(bitmap, 0, 0);
    const data = ctx.getImageData(0, 0, TILE_SIZE, TILE_SIZE).data;
    tileCache.set(key, data);
    return data;
  } catch (err) {
    tileCache.set(key, null);
    return null;
  }
}
async function getElevation(lat, lon, zoom) {
  const coords = lonLatToTile(lon, lat, zoom);
  const tile = await fetchTile(zoom, coords.tileX, coords.tileY);
  if (!tile) return null;
  const idx = (coords.py * TILE_SIZE + coords.px) * 4;
  const r = tile[idx];
  const g = tile[idx + 1];
  const b = tile[idx + 2];
  return (r * 256 + g + b / 256) - 32768;
}
function knifeEdgeLossFromV(v) {
  if (!Number.isFinite(v) || v <= 0) return 0;
  const loss = 6.9 + 20 * Math.log10(Math.sqrt((v - 0.1) ** 2 + 1) + v - 0.1);
  return Math.max(0, loss);
}
self.onmessage = async (event) => {
  const data = event.data;
  if (!data || data.type !== "render") return;
  const { token, origins, config, renderRange, maxPathLossDb, fspl1mDb, freqMHz } = data;
  try {
    if (!Array.isArray(origins) || origins.length === 0) {
      throw new Error("No origins provided");
    }
    const latScale = 111320;
    const refLat = origins.reduce((sum, o) => sum + o.lat, 0) / origins.length;
    const lonScale = 111320 * Math.cos(refLat * Math.PI / 180);
    const latStep = config.gridStep / latScale;
    const lonStep = config.gridStep / lonScale;
    let latMin = Infinity;
    let latMax = -Infinity;
    let lonMin = Infinity;
    let lonMax = -Infinity;
    for (const origin of origins) {
      const originLonScale = 111320 * Math.cos(origin.lat * Math.PI / 180);
      const latRadius = renderRange / latScale;
      const lonRadius = renderRange / originLonScale;
      latMin = Math.min(latMin, origin.lat - latRadius);
      latMax = Math.max(latMax, origin.lat + latRadius);
      lonMin = Math.min(lonMin, origin.lon - lonRadius);
      lonMax = Math.max(lonMax, origin.lon + lonRadius);
    }
    const rows = Math.max(1, Math.ceil((latMax - latMin) / latStep));
    const cols = Math.max(1, Math.ceil((lonMax - lonMin) / lonStep));
    const zoom = clamp(Math.round(Math.log2(156543.03392 * Math.cos(refLat * Math.PI / 180) / config.gridStep)), 8, 12);
    const lambda = 299792458 / (freqMHz * 1e6);
    const clutterLossDb = Number.isFinite(config.clutterLossDb) ? config.clutterLossDb : 0;
    const originEntries = [];
    for (const origin of origins) {
      const originGround = config.useTerrain && config.txMsl == null ? await getElevation(origin.lat, origin.lon, zoom) : 0;
      const txAbs = (config.txMsl != null) ? config.txMsl : (originGround ?? 0) + config.txAgl;
      originEntries.push({
        lat: origin.lat,
        lon: origin.lon,
        lonScale: 111320 * Math.cos(origin.lat * Math.PI / 180),
        txAbs
      });
    }
    const pixels = new Uint8ClampedArray(rows * cols * 4);
    const coverage = new Uint8Array(rows * cols);
    for (let row = 0; row < rows; row++) {
      const lat = latMax - row * latStep;
      for (let col = 0; col < cols; col++) {
        const lon = lonMin + col * lonStep;
        const idx = row * cols + col;
        const offset = idx * 4;
        let bestMargin = -Infinity;
        let coverCount = 0;
        let endGround = null;
        if (config.useTerrain) {
          endGround = await getElevation(lat, lon, zoom);
          if (endGround == null) {
            pixels[offset + 3] = 0;
            continue;
          }
        }
        for (const origin of originEntries) {
          const dx = (lon - origin.lon) * origin.lonScale;
          const dy = (lat - origin.lat) * latScale;
          const distance = Math.sqrt(dx * dx + dy * dy);
          if (distance <= 1 || distance > renderRange) {
            continue;
          }
          let rxAbs = (config.rxMsl != null) ? config.rxMsl : (config.useTerrain ? endGround + config.rxAgl : origin.txAbs);
          let maxV = 0;
          let minClearanceRatio = Infinity;
          if (config.useTerrain) {
            const samples = Math.max(2, Math.ceil(distance / config.sampleStep) + 1);
            for (let i = 1; i < samples - 1; i++) {
              const t = i / (samples - 1);
              const sLat = origin.lat + (lat - origin.lat) * t;
              const sLon = origin.lon + (lon - origin.lon) * t;
              const elev = await getElevation(sLat, sLon, zoom);
              if (elev == null) continue;
              const lineElev = origin.txAbs + (rxAbs - origin.txAbs) * t;
              const d1 = distance * t;
              const d2 = distance * (1 - t);
              const f1 = Math.sqrt((lambda * d1 * d2) / (d1 + d2));
              const bulge = (d1 * d2) / (2 * config.earthRadiusM);
              const effectiveElev = elev + bulge;
              let fresnel = 0;
              if (config.fresnelFactor > 0) {
                fresnel = config.fresnelFactor * f1;
              }
              const clearance = lineElev - effectiveElev;
              if (f1 > 0) {
                const ratio = clearance / f1;
                if (ratio < minClearanceRatio) minClearanceRatio = ratio;
              }
              const obstruction = (effectiveElev - lineElev) - fresnel;
              if (obstruction <= 0) continue;
              const v = obstruction * Math.sqrt((2 * (d1 + d2)) / (lambda * d1 * d2));
              if (v > maxV) maxV = v;
            }
          }
          const extraLoss = maxV > 0 ? knifeEdgeLossFromV(maxV) : 0;
          let clearanceLoss = 0;
          if (config.useTerrain && Number.isFinite(minClearanceRatio) && minClearanceRatio < config.clearanceRatio) {
            const ratio = Math.max(-1, minClearanceRatio);
            const deficit = config.clearanceRatio - ratio;
            clearanceLoss = Math.min(config.clearanceLossDb, (deficit / config.clearanceRatio) * config.clearanceLossDb);
          }
          const pathLoss = fspl1mDb + (10 * config.pathLossExp * Math.log10(distance)) + extraLoss + clearanceLoss + clutterLossDb;
          const margin = maxPathLossDb - pathLoss;
          if (margin > 0) {
            coverCount += 1;
            if (margin > bestMargin) bestMargin = margin;
          }
        }
        if (coverCount > 0) {
          const requiredOverlap = originEntries.length >= 3 ? originEntries.length : 2;
          const strength = Math.min(1, bestMargin / 20);
          if (coverCount >= requiredOverlap) {
            pixels[offset] = 34;
            pixels[offset + 1] = 197;
            pixels[offset + 2] = 94;
          } else {
            pixels[offset] = 239;
            pixels[offset + 1] = 68;
            pixels[offset + 2] = 68;
          }
          pixels[offset + 3] = config.fadeByMargin ? Math.round(255 * strength) : 255;
          coverage[idx] = Math.min(255, coverCount);
        } else {
          pixels[offset + 3] = 0;
        }
      }
      if (row % 10 === 0) {
        self.postMessage({ type: "progress", token, row, rows });
        await new Promise((resolve) => setTimeout(resolve, 0));
      }
    }
    self.postMessage({
      type: "result",
      token,
      width: cols,
      height: rows,
      bounds: { latMin, latMax, lonMin, lonMax },
      latStep,
      lonStep,
      pixels: pixels.buffer,
      coverage: coverage.buffer
    }, [pixels.buffer, coverage.buffer]);
  } catch (err) {
    const message = (err && err.message) ? err.message : String(err);
    self.postMessage({ type: "error", token, error: message });
  }
};
