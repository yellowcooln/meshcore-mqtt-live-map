import json
import subprocess
from pathlib import Path

import pytest


APP_JS = Path(__file__).resolve().parents[1] / "backend/static/app.js"


@pytest.mark.parametrize("footer_height", [0, 17, 34, 51])
def test_mobile_panels_clear_map_attribution(footer_height):
  source = APP_JS.read_text(encoding="utf-8")
  start = source.index("function layoutSidePanels(")
  end = source.index("\nfunction setToolPanelCollapsed", start)
  script = f"""
const assert = require('node:assert/strict');
const makePanel = () => ({{
  style: {{}}, offsetHeight: 200,
  classList: {{contains: () => true}}
}});
const losPanel = makePanel(), propPanel = makePanel(), peersPanel = makePanel();
const weatherPanel = null, historyPanel = null, routeDetailsPanel = null;
const losActive = true, propagationActive = false, peersActive = true;
const radarVisible = false, historyVisible = false;
const window = {{innerHeight: 800, matchMedia: () => ({{matches: true}})}};
const document = {{querySelectorAll: () => [{{
  getBoundingClientRect: () => ({{top: 800 - {footer_height}, bottom: 800,
    width: 320, height: {footer_height}}})
}}]}};
{source[start:end]}
layoutSidePanels();
console.log(JSON.stringify([peersPanel.style.bottom, losPanel.style.bottom]));
"""
  result = subprocess.run(
    ["node", "-e", script], check=True, capture_output=True, text=True
  )
  positions = json.loads(result.stdout)
  inset = max(12, footer_height + 8) if footer_height else 12
  assert positions == [f"{inset}px", f"{inset + 212}px"]
