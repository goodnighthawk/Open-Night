from __future__ import annotations

import ast
import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERVER = ROOT / "server.py"
ROADS = ROOT / "mapfiles/data/map_001_gwb_corridor/roads.csv"
SIDEWALKS = ROOT / "mapfiles/data/map_001_gwb_corridor/sidewalks.csv"


def function_source(path: Path, name: str) -> str:
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    lines = source.splitlines()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            end = getattr(node, "end_lineno", node.lineno)
            return "\n".join(lines[node.lineno - 1 : end])
    raise AssertionError(f"missing {name} in {path}")


def main() -> None:
    vehicle_block = function_source(SERVER, "_vehicle_map_blocked")

    # GTA-style player cars are allowed off the asphalt. The authoritative
    # collision rule may reject map edges, water and solid buildings. A road
    # proximity test is allowed only as the bridge-over-water exception; it
    # must not become a general requirement that the car stay on asphalt.
    compact = " ".join(vehicle_block.split())
    assert "if not point_near_road(" not in compact, "vehicle collision became road-only; sidewalks would be blocked"
    assert "and not point_near_road(" in compact, "bridge-over-water road exception unexpectedly disappeared"
    assert "collision_buildings_near" in vehicle_block, "solid building collision must remain authoritative"
    assert "point_in_water" in vehicle_block, "water must remain blocked for cars"

    with ROADS.open(encoding="utf-8-sig", newline="") as f:
        roads = list(csv.DictReader(f))
    assert roads, "runtime map has no roads"
    widths = [float(row["sidewalk_width"]) for row in roads if float(row.get("sidewalk_width") or 0) > 0]
    assert widths and min(widths) >= 30.0, "authored sidewalks are too narrow for the v0.9 driveability contract"

    with SIDEWALKS.open(encoding="utf-8-sig", newline="") as f:
        sidewalks = list(csv.DictReader(f))
    assert sidewalks, "runtime map has no sidewalk geometry"

    print(
        "V090_SIDEWALK_DRIVEABILITY_OK "
        f"roads={len(roads)} sidewalks={len(sidewalks)} min_sidewalk_width={min(widths):.1f}"
    )


if __name__ == "__main__":
    main()
