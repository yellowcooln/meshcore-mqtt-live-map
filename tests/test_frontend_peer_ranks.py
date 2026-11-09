import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_JS = ROOT / "backend" / "static" / "app.js"
STYLES_CSS = ROOT / "backend" / "static" / "styles.css"


def _extract_function(source, name):
  marker = f"function {name}("
  start = source.index(marker)
  brace = source.index("{", start)
  depth = 0
  for index in range(brace, len(source)):
    if source[index] == "{":
      depth += 1
    elif source[index] == "}":
      depth -= 1
      if depth == 0:
        return source[start:index + 1]
  raise AssertionError(f"unterminated function: {name}")


def test_peer_filter_preserves_full_list_rank():
  source = APP_JS.read_text(encoding="utf-8")
  ranked_peers = _extract_function(source, "rankedPeers")
  normalized_filter = _extract_function(source, "normalizedPeerFilter")
  matches_filter = _extract_function(source, "peerMatchesFilter")
  filtered_peers = _extract_function(source, "filteredPeers")
  script = f"""
let peersFilterText = 'charlie';
{ranked_peers}
{normalized_filter}
{matches_filter}
{filtered_peers}
const incoming = [
  {{ name: 'Alpha', peer_id: 'AA', count: 30 }},
  {{ name: 'Bravo', peer_id: 'BB', count: 20 }},
  {{ name: 'Charlie', peer_id: 'CC', count: 10 }}
];
const outgoing = [
  {{ name: 'Delta', peer_id: 'DD', count: 40 }},
  {{ name: 'Charlie', peer_id: 'CC', count: 15 }}
];
console.log(JSON.stringify({{
  incoming: filteredPeers(incoming),
  outgoing: filteredPeers(outgoing)
}}));
"""

  result = subprocess.run(
    ["node", "-e", script],
    check=True,
    capture_output=True,
    text=True,
  )
  payload = json.loads(result.stdout)

  assert payload["incoming"][0]["rank"] == 3
  assert payload["outgoing"][0]["rank"] == 2


def test_peer_rows_render_a_fixed_rank_column():
  source = APP_JS.read_text(encoding="utf-8")
  render_peer_list = _extract_function(source, "renderPeerList")
  css = STYLES_CSS.read_text(encoding="utf-8")

  assert 'class="peer-rank"' in render_peer_list
  assert ".peer-rank {" in css
  assert "font-variant-numeric: tabular-nums;" in css


def test_peer_grid_can_shrink_without_clipping_distances():
  css = STYLES_CSS.read_text(encoding="utf-8")
  list_rules = css.split(".peer-list {", 1)[1].split("}", 1)[0]
  row_rules = css.split(".peer-item {", 1)[1].split("}", 1)[0]
  assert "grid-template-columns: minmax(0, 1fr);" in list_rules
  assert "min-width: 0;" in row_rules


def test_unit_change_keeps_active_peer_filter_and_ranks():
  source = APP_JS.read_text(encoding="utf-8")
  set_distance_units = _extract_function(source, "setDistanceUnits")

  assert "renderCurrentPeers();" in set_distance_units
  assert "renderPeerList(peersIn, peersData.incoming" not in set_distance_units
