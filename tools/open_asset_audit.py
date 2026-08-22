from __future__ import annotations

import ast
import csv
import struct
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def png_size(path: Path) -> tuple[int, int, int]:
    data = path.read_bytes()[:33]
    if data[:8] != b"\x89PNG\r\n\x1a\n" or data[12:16] != b"IHDR":
        raise AssertionError(f"not a PNG: {path.relative_to(ROOT)}")
    width, height, bit_depth, color_type = struct.unpack(">IIBB", data[16:26])
    assert bit_depth == 8, (path, bit_depth)
    return width, height, color_type


def rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def main() -> int:
    manifest = rows(ROOT / "assets/cars/player_vehicle_manifest.csv")
    generated = [row for row in manifest if row.get("art_set") == "generated_vehicle_fleet_2026_08_22"]
    assert len(generated) == 28, f"expected 28 generated vehicles, found {len(generated)}"
    for row in generated:
        assert row["file"].startswith("../source_packs/gen_vehicles/gen_vehicle_")
        assert row["traffic_eligible"].lower() == "true"
        width, height, color_type = png_size(ROOT / "assets/cars" / row["file"])
        assert width > 32 and height > 64 and color_type == 6

    catalog = rows(ROOT / "assets/open_source_import/catalog.csv")
    assert len(catalog) == 4, len(catalog)
    assert all(row["license"] == "user_created" for row in catalog)
    assert sum(row["asset_type"] == "vehicle_sprite" for row in catalog) == 0
    for row in catalog:
        runtime = row["runtime_file"].strip()
        if runtime:
            assert (ROOT / "assets/open_source_import" / runtime).is_file(), runtime

    assert png_size(ROOT / "assets/effects/sprint_dust_8.png") == (512, 64, 6)
    assert png_size(ROOT / "assets/open_source_import/city/city_building_01_topdown.png") == (256, 256, 6)
    assert png_size(ROOT / "assets/open_source_import/city/city_building_01_isometric.png") == (256, 256, 6)

    directions = rows(ROOT / "assets/characters/master_dual_camera/config/directions.csv")
    assert [row["direction"] for row in directions] == [
        "north", "northeast", "east", "southeast",
        "south", "southwest", "west", "northwest",
    ]
    fluid = rows(ROOT / "assets/characters/master_dual_camera/config/fluid_animations.csv")
    walk_rows = [row for row in fluid if row["animation"] == "walk_8"]
    run_rows = [row for row in fluid if row["animation"] == "run_wide_8"]
    assert len(walk_rows) == 10
    assert len(run_rows) == 10
    assert all(row["frame_count"] == "8" for row in walk_rows)
    assert all(row["frame_count"] == "8" for row in run_rows)
    assert all((ROOT / "assets/characters/master_dual_camera" / row["sheet"]).is_file() for row in walk_rows)
    assert all((ROOT / "assets/characters/master_dual_camera" / row["sheet"]).is_file() for row in run_rows)

    settings = {(row["section"], row["key"]): row["value"] for row in rows(ROOT / "config/game_settings.csv")}
    assert settings[("movement", "walk_speed_px_per_second")] == "185"
    assert settings[("movement", "sprint_multiplier")] == "3.0"
    assert settings[("movement", "sprint_animation_rate_multiplier")] == "1.85"
    assert settings[("movement", "sprint_gait_width_multiplier")] == "1.48"
    assert settings[("movement", "double_jump_forward_speed_px_per_second")] == "940"
    assert settings[("render", "double_jump_scale_multiplier")] == "1.50"

    client_source = (ROOT / "client.py").read_text(encoding="utf-8")
    client_tree = ast.parse(client_source, filename="client.py")
    server_tree = ast.parse((ROOT / "server.py").read_text(encoding="utf-8"), filename="server.py")
    assert "register_direction_tap" not in client_source
    assert "prone_toggle" in client_source
    assert "shift_boost" in client_source
    server_functions = {node.name for node in ast.walk(server_tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
    assert {"request_player_jump", "request_player_prone_toggle", "finish_expired_player_jump"} <= server_functions
    assert any(isinstance(node, ast.FunctionDef) and node.name == "_traffic_asset" for node in ast.walk(server_tree))

    print("OPEN ASSET AUDIT PASSED")
    print("  28 generated vehicles / 2 building views / 8-frame dust / 10 dedicated wide-gait run sheets")
    print("  user_created catalog / held-Shift run / server-authoritative double jump")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
