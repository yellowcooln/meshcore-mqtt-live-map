"""Browser regression for reported HUD/Peers layout issues.

Run with Playwright + Chromium installed:
  python tools/check-frontend-layout.py http://127.0.0.1:8080/map --output DIR
Use an isolated app with no production data. External map providers are mocked;
this tests actual app DOM/layout, not providers or physical desktop/mobile OSes.
Touch contexts emulate coarse pointers; narrow mouse contexts retain controls.
For offline fixtures, pass --vendor-dir with Leaflet CSS/JS and leaflet-heat.js.
"""
import argparse
import base64
import hashlib
import json
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import urlopen

from playwright.sync_api import sync_playwright


parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("url")
parser.add_argument("--output", type=Path, required=True)
parser.add_argument("--vendor-dir", type=Path,
                    help="Offline Leaflet CSS, JS and leaflet-heat.js directory")
parser.add_argument("--context", help="Run one named browser context")
args = parser.parse_args()
args.output.mkdir(parents=True, exist_ok=True)
origin = urlsplit(args.url).netloc
base = args.url.rsplit("/", 1)[0]
source_hashes = {}
for asset in ("app.js", "styles.css"):
  with urlopen(base + "/static/" + asset, timeout=30) as response:
    source_hashes[asset] = hashlib.sha256(response.read()).hexdigest()
(args.output / "served-source.json").write_text(
  json.dumps(source_hashes, indent=2)
)
cdn = {}
for name in ["leaflet@1.9.4/dist/leaflet.css", "leaflet@1.9.4/dist/leaflet.js",
             "leaflet.heat@0.2.0/dist/leaflet-heat.js"]:
  url = "https://unpkg.com/" + name
  if args.vendor_dir:
    cdn[url] = (args.vendor_dir / name.rsplit("/", 1)[-1]).read_bytes()
  else:
    with urlopen(url, timeout=30) as response:
      cdn[url] = response.read()
pixel = base64.b64decode(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII="
)
results = []
failures = []
details = []
with sync_playwright() as playwright:
  browser = playwright.chromium.launch(args=["--disable-features=OverlayScrollbar"])
  contexts = [
    ("mouse-desktop", 1280, 900, False),
    ("mouse-narrow", 390, 844, False),
    ("mouse-412", 412, 810, False),
    ("touch-320", 320, 640, True),
    ("touch-390", 390, 844, True),
    ("touch-412", 412, 810, True),
    ("touch-tablet", 768, 1024, True),
    ("touch-landscape", 844, 390, True),
    ("touch-900", 900, 900, True),
    ("touch-901", 901, 900, True),
  ]
  for name, width, height, touch in contexts:
    if args.context and args.context != name:
      continue
    context = browser.new_context(viewport={"width": width, "height": height},
                                  has_touch=touch, is_mobile=touch,
                                  service_workers="block")
    page = context.new_page()
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))

    def route_request(route):
      url = route.request.url
      if urlsplit(url).netloc == origin:
        route.continue_()
      elif url in cdn:
        route.fulfill(body=cdn[url], content_type=(
          "text/css" if url.endswith(".css") else "application/javascript"))
      elif "tiles.openfreemap.org/styles/" in url:
        route.fulfill(json={"version": 8, "sources": {}, "layers": [
          {"id": "background", "type": "background",
           "paint": {"background-color": "#111827"}}
        ]})
      elif route.request.resource_type == "image":
        route.fulfill(body=pixel, content_type="image/png")
      else:
        route.abort()

    page.route("**/*", route_request)
    page.route_web_socket("**/ws*", lambda ws: None)
    page.goto(args.url, wait_until="networkidle")
    page.bring_to_front()
    context.new_cdp_session(page).send(
      "Emulation.setPageScaleFactor", {"pageScaleFactor": 1}
    )
    page.wait_for_function("typeof renderPeerList === 'function'")
    page.evaluate("""() => {
      const rows = Array.from({length: 49}, (_, i) => ({
        peer_id: String(i + 1).padStart(64, '0'),
        name: i ? 'Rainbow Ridge ⚡ WCMESH • a long repeater name' : 'Palmdale Repeater',
        count: 9999 - i, percent: 17.4, distance_m: 123456,
        rank: i + 1
      }));
      setPeersActive(true);
      setPeersPanelTitle('Winston1131', '', 24);
      renderPeerList(peersIn, rows, 50000, 'incoming');
      renderPeerList(peersOut, rows, 50000, 'outgoing');
      setPeerHeadings(49, 49, 50000, 50000);
      document.getElementById('stats').textContent =
        '788 devices • 40 MQTT online • 19/60 routes';
      layoutSidePanels();
    }""")
    for layer in ["light", "dark", "satellite"]:
      page.evaluate("layer => setBaseLayer(layer)", layer)
      page.wait_for_timeout(300)
      metrics = page.evaluate("""() => {
        const lists = [...document.querySelectorAll('.peer-list')];
        const clippedRows = lists.flatMap(list => [...list.children].filter(row => {
          const stat = row.querySelector('.peer-count');
          return stat && (stat.getBoundingClientRect().right >
            list.getBoundingClientRect().left + list.clientWidth + 1 ||
            row.scrollWidth > row.clientWidth + 1);
        }));
        const attribution = [...document.querySelectorAll(
          '.leaflet-bottom .leaflet-control, .maplibregl-ctrl-attrib')]
          .filter(el => el.getBoundingClientRect().height > 0)
          .map(el => el.getBoundingClientRect());
        const panel = document.getElementById('peers-panel').getBoundingClientRect();
        const overlaps = attribution.some(a => a.left < panel.right &&
          a.right > panel.left && a.top < panel.bottom && a.bottom > panel.top);
        const stats = document.getElementById('stats');
        const zoom = document.querySelector('.leaflet-control-zoom');
        const zoomRect = zoom.getBoundingClientRect();
        const credit = map.attributionControl.getContainer();
        const expectedInset = Math.max(12, ...attribution.map(a =>
          innerHeight - a.top + 8));
        return {clippedRows: clippedRows.length, overlaps,
          statsOverflow: stats.scrollWidth > stats.clientWidth + 1,
          documentOverflow: document.documentElement.scrollWidth > innerWidth,
          width: innerWidth, panelBottom: panel.bottom,
          coarse: matchMedia('(pointer: coarse)').matches,
          zoomHidden: getComputedStyle(zoom).display === 'none',
          zoomHeight: zoomRect.height, touchZoom: map.touchZoom.enabled(),
          attributionVisible: credit.getBoundingClientRect().height > 0,
          privacyVisible: !!credit.querySelector('a[href$="/privacy"]'),
          insetMatchesControls: innerWidth > 900 || Math.abs(
            parseFloat(peersPanel.style.bottom) - expectedInset) < 1,
          bottomInset: parseFloat(peersPanel.style.bottom), expectedInset,
          clientWidth: document.documentElement.clientWidth,
          scrollWidth: document.documentElement.scrollWidth,
          visualViewport: {width: visualViewport.width,
            height: visualViewport.height, scale: visualViewport.scale},
          attribution: attribution.map(a => ({top:a.top,height:a.height,width:a.width}))};
      }""")
      result = {"context": name, "touch": touch,
                "viewport": [width, height], "layer": layer, **metrics}
      results.append(result)
      if any([metrics["clippedRows"], metrics["overlaps"], metrics["statsOverflow"],
              metrics["documentOverflow"], metrics["coarse"] != touch,
              metrics["zoomHidden"] != (touch and width <= 900),
              not metrics["attributionVisible"], not metrics["privacyVisible"],
              not metrics["insetMatchesControls"],
              touch and not metrics["touchZoom"]]):
        failures.append(result)
      if width <= 900:
        # Inspect the tool without the separately toggleable HUD obscuring it.
        page.evaluate("document.querySelector('.hud').classList.add('panel-hidden')")
      page.screenshot(path=str(args.output / f"layout-{name}-{layer}.png"))
      if width <= 900:
        page.evaluate("document.querySelector('.hud').classList.remove('panel-hidden')")
    if name == "touch-412":
      def panel_metrics(stage):
        metric = page.evaluate("""() => {
          const rect = el => {
            const r = el.getBoundingClientRect();
            return {left:r.left, right:r.right, top:r.top, bottom:r.bottom,
              width:r.width, height:r.height};
          };
          const panel = rect(peersPanel), los = rect(losPanel);
          const controls = [...document.querySelectorAll(
            '.leaflet-bottom .leaflet-control, .maplibregl-ctrl-attrib')]
            .map(rect).filter(r => r.width > 0 && r.height > 0);
          const intersects = (a, b) => a.left < b.right && a.right > b.left &&
            a.top < b.bottom && a.bottom > b.top;
          return {panel, los, controls,
            collapsed: peersPanel.classList.contains('panel-collapsed'),
            overlap: controls.some(c => intersects(panel, c) ||
              (losActive && intersects(los, c))),
            stackedGap: losActive ? panel.top - los.bottom : null,
            bottomInset: parseFloat(peersPanel.style.bottom),
            expectedInset: Math.max(12, ...controls.map(c =>
              innerHeight - c.top + 8))};
        }""")
        result = {"context": name, "stage": stage, **metric}
        details.append(result)
        if (metric["overlap"] or
            abs(metric["bottomInset"] - metric["expectedInset"]) > 1 or
            (metric["stackedGap"] is not None and
             metric["stackedGap"] < 11)):
          failures.append(result)
        return metric

      page.evaluate("setPeersPanelCollapsed(true)")
      minimized = panel_metrics("minimized-populated")
      if not minimized["collapsed"]:
        failures.append({"context": name, "minimizeFailed": True})
      page.evaluate("""() => {
        setPeersPanelCollapsed(false);
        renderPeerList(peersIn, [], 0, 'incoming');
        renderPeerList(peersOut, [], 0, 'outgoing');
      }""")
      panel_metrics("empty")
      page.evaluate("setLosActive(true)")
      panel_metrics("stacked")
      before = page.evaluate("parseFloat(peersPanel.style.bottom)")
      credit = "Synthetic coverage credits " * 20
      page.evaluate("credit => setTimeout(() => "
                    "map.attributionControl.addAttribution(credit), 10)", credit)
      page.wait_for_timeout(300)
      wrapped = panel_metrics("asynchronous-wrapped-attribution")
      if wrapped["bottomInset"] <= before:
        failures.append({"context": name, "attributionDidNotRelayout": True})
      page.evaluate("credit => { "
                    "map.attributionControl.removeAttribution(credit); }", credit)
      page.wait_for_timeout(300)
      panel_metrics("attribution-restored")
      page.evaluate("""() => {
        setLosActive(false); setPeersPanelCollapsed(true);
        document.querySelector('.hud').classList.add('panel-hidden');
      }""")
      page.bring_to_front()
      before_zoom = page.evaluate("map.getZoom()")
      session = context.new_cdp_session(page)
      for step in range(6):
        offset = 20 + step * 15
        session.send("Input.dispatchTouchEvent", {
          "type": "touchStart" if step == 0 else "touchMove",
          "touchPoints": [{"x": 200 - offset, "y": 150, "id": 1},
                          {"x": 200 + offset, "y": 150, "id": 2}],
        })
        page.wait_for_timeout(40)
      session.send("Input.dispatchTouchEvent", {
        "type": "touchEnd", "touchPoints": []
      })
      page.wait_for_timeout(400)
      after_zoom = page.evaluate("map.getZoom()")
      details.append({"context": name, "stage": "real-pinch",
                      "beforeZoom": before_zoom, "afterZoom": after_zoom})
      if after_zoom <= before_zoom:
        failures.append({"context": name, "pinchZoomFailed": True})
      page.screenshot(path=str(args.output / "touch-412-pinch.png"))
    elif not (touch and width <= 900):
      before_zoom = page.evaluate("map.getZoom()")
      page.locator('.leaflet-control-zoom-in').click()
      page.wait_for_timeout(400)
      after_zoom = page.evaluate("map.getZoom()")
      details.append({"context": name, "stage": "zoom-button",
                      "beforeZoom": before_zoom, "afterZoom": after_zoom})
      if after_zoom <= before_zoom:
        failures.append({"context": name, "zoomButtonFailed": True})
    if errors:
      failures.append({"context": name, "pageErrors": errors})
    context.close()
  browser.close()
(args.output / "results.json").write_text(json.dumps(results, indent=2))
(args.output / "interaction-results.json").write_text(
  json.dumps(details, indent=2)
)
print(json.dumps({"cases": len(results), "interactionCases": len(details),
                  "failures": failures}, indent=2))
if not results:
  raise SystemExit("No browser contexts selected")
if failures:
  raise SystemExit(1)
