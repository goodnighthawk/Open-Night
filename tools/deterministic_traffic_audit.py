from __future__ import annotations

import ast
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mapfiles.loader import load_all_maps, validate_map

MAP_ID = "map_001_gwb_corridor"
START_KEYS = (
    ("traffic_starts", "traffic_routes"),
    ("bicycle_starts", "bicycle_routes"),
    ("npc_starts", "npc_routes"),
)
RUNTIME_FUNCTIONS = {
    "_sample_route",
    "_fixed_start_plan",
    "initialize_traffic",
    "initialize_bicycles",
    "initialize_npcs",
    "_try_recycle_stuck_car",
}
RANDOM_NAMES = {"random", "randint", "randrange", "choice", "choices", "shuffle", "uniform"}


def fingerprint(rows: list[dict]) -> str:
    payload = [
        {
            "id": str(row.get("id", "")),
            "route_id": str(row.get("route_id", "")),
            "start_fraction": float(row.get("start_fraction", 0.0)),
            "asset_index": int(row.get("asset_index", 0)),
            "appearance_index": int(row.get("appearance_index", 0)),
            "speed_scale": float(row.get("speed_scale", 1.0)),
        }
        for row in rows
    ]
    blob = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def audit_start_table(cfg: dict, starts_key: str, routes_key: str) -> list[str]:
    errors: list[str] = []
    starts = cfg.get(starts_key, []) or []
    routes = cfg.get(routes_key, []) or []
    route_ids = {str(route.get("id", "")) for route in routes}
    ids: set[str] = set()
    for index, row in enumerate(starts):
        sid = str(row.get("id", ""))
        rid = str(row.get("route_id", ""))
        fraction = float(row.get("start_fraction", -1.0))
        if not sid:
            errors.append(f"{starts_key}[{index}] missing spawn id")
        elif sid in ids:
            errors.append(f"{starts_key} duplicate spawn id {sid}")
        ids.add(sid)
        if rid not in route_ids:
            errors.append(f"{starts_key}:{sid} unknown route {rid}")
        if not 0.0 <= fraction < 1.0:
            errors.append(f"{starts_key}:{sid} invalid start_fraction {fraction}")
    counts = Counter(str(row.get("route_id", "")) for row in starts)
    print(f"{starts_key}: {len(starts)} fixed slots | sha256={fingerprint(starts)}")
    print("  route slots: " + ", ".join(f"{route}={count}" for route, count in sorted(counts.items())))
    return errors


def audit_runtime_ast() -> list[str]:
    errors: list[str] = []
    source = (ROOT / "server.py").read_text(encoding="utf-8")
    tree = ast.parse(source, filename="server.py")
    functions = {node.name: node for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
    for name in sorted(RUNTIME_FUNCTIONS):
        node = functions.get(name)
        if node is None:
            errors.append(f"server.py missing required fixed-flow function {name}")
            continue
        for child in ast.walk(node):
            if isinstance(child, ast.Attribute) and isinstance(child.value, ast.Name):
                if child.value.id == "random":
                    errors.append(f"server.py:{name} uses random.{child.attr}")
            elif isinstance(child, ast.Call) and isinstance(child.func, ast.Name):
                if child.func.id in RANDOM_NAMES:
                    errors.append(f"server.py:{name} calls random-like function {child.func.id}")
    return errors


def main() -> int:
    maps = load_all_maps()
    cfg = maps.get(MAP_ID)
    if cfg is None:
        print(f"FAIL: {MAP_ID} not found under {ROOT / 'mapfiles' / 'data'}")
        return 2

    errors = validate_map(cfg)
    for starts_key, routes_key in START_KEYS:
        errors.extend(audit_start_table(cfg, starts_key, routes_key))
    errors.extend(audit_runtime_ast())

    if errors:
        print("\nDETERMINISM AUDIT FAILED")
        for error in errors:
            print(" -", error)
        return 1

    print("\nDETERMINISM AUDIT PASSED")
    print("Fixed AI route/start selection contains no runtime RNG in the audited path.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
