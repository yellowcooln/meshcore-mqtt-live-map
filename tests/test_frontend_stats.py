import json
import subprocess
from pathlib import Path

import pytest


APP_JS = Path(__file__).resolve().parents[1] / "backend/static/app.js"


@pytest.mark.parametrize("history_enabled", [False, True])
@pytest.mark.parametrize("filtered", [False, True])
def test_stats_are_compact_and_respect_history_feature(history_enabled, filtered):
  source = APP_JS.read_text(encoding="utf-8")
  start = source.index("function setStats(")
  end = source.index("\nlet statsFramePending", start)
  function = source[start:end]
  script = f"""
const stats = {{textContent: ''}};
const document = {{getElementById: () => stats}};
const markers = {{size: 788}};
const deviceData = new Map();
const isMqttOnline = () => false;
const mqttPresenceKnown = true;
const mqttConnectedTotal = 40;
const routeLines = {{size: 60}};
const historyLines = {{size: 0}};
const routeByteFilter = new Set({json.dumps(['2b', '3b'] if filtered else ['all'])});
const routeNodeFilterText = '';
const routeHistoryEnabled = {json.dumps(history_enabled)};
const getVisibleRouteCount = () => {19 if filtered else 60};
{function}
setStats();
console.log(JSON.stringify(stats.textContent));
"""
  result = subprocess.run(
    ["node", "-e", script], check=True, capture_output=True, text=True
  )
  text = json.loads(result.stdout)
  routes = "19/60 routes" if filtered else "60 routes"
  expected = f"788 devices • 40 MQTT online • {routes}"
  if history_enabled:
    expected += " • 0 history"
  assert text == expected
