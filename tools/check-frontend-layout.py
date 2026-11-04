"""Browser regression for reported HUD/Peers layout issues.

Run with Playwright + Chromium installed:
  python tools/check-frontend-layout.py http://127.0.0.1:8080/map --output DIR
Use an isolated app with no production data. External map providers are mocked;
this tests actual app DOM/layout, not provider availability or physical Windows.
"""
import argparse
import base64
import json
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import urlopen

from playwright.sync_api import sync_playwright


parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("url")
parser.add_argument("--output", type=Path, required=True)
args = parser.parse_args()
args.output.mkdir(parents=True, exist_ok=True)
origin = urlsplit(args.url).netloc
cdn = {}
for name in ["leaflet@1.9.4/dist/leaflet.css", "leaflet@1.9.4/dist/leaflet.js",
             "leaflet.heat@0.2.0/dist/leaflet-heat.js"]:
  url = "https://unpkg.com/" + name
  with urlopen(url, timeout=30) as response:
    cdn[url] = response.read()
pixel = base64.b64decode(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII="
)
results = []
failures = []
with sync_playwright() as playwright:
  browser = playwright.chromium.launch(args=["--disable-features=OverlayScrollbar"])
  for width, height in [(1280, 900), (768, 1024), (390, 844), (320, 640)]:
    context = browser.new_context(viewport={"width": width, "height": height},
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
        return {clippedRows: clippedRows.length, overlaps,
          statsOverflow: stats.scrollWidth > stats.clientWidth + 1,
          documentOverflow: document.documentElement.scrollWidth > innerWidth,
          width: innerWidth, panelBottom: panel.bottom,
          attribution: attribution.map(a => ({top:a.top,height:a.height,width:a.width}))};
      }""")
      result = {"viewport": [width, height], "layer": layer, **metrics}
      results.append(result)
      if any([metrics["clippedRows"], metrics["overlaps"], metrics["statsOverflow"],
              metrics["documentOverflow"]]):
        failures.append(result)
      if width <= 900:
        # Inspect the tool without the separately toggleable HUD obscuring it.
        page.evaluate("document.querySelector('.hud').classList.add('panel-hidden')")
      page.screenshot(path=str(args.output / f"layout-{width}-{layer}.png"))
      if width <= 900:
        page.evaluate("document.querySelector('.hud').classList.remove('panel-hidden')")
    if errors:
      failures.append({"viewport": [width, height], "pageErrors": errors})
    context.close()
  browser.close()
(args.output / "results.json").write_text(json.dumps(results, indent=2))
print(json.dumps({"cases": len(results), "failures": failures}, indent=2))
if failures:
  raise SystemExit(1)
