from __future__ import annotations

import csv
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GAME_SETTINGS = ROOT / "config" / "game_settings.csv"
PREVIEW_SETTINGS = ROOT / "assets" / "characters" / "master_dual_camera" / "config" / "movement_settings.csv"
SERVER = ROOT / "server.py"
PREVIEW = ROOT / "dev_tools" / "character_preview" / "sprite_tester.py"


def _game_rows() -> dict[tuple[str, str], str]:
    with GAME_SETTINGS.open("r", encoding="utf-8-sig", newline="") as handle:
        return {
            (row["section"].strip(), row["key"].strip()): row["value"].strip()
            for row in csv.DictReader(handle)
        }


def _preview_rows() -> dict[str, str]:
    with PREVIEW_SETTINGS.open("r", encoding="utf-8-sig", newline="") as handle:
        return {row["setting"].strip(): row["value"].strip() for row in csv.DictReader(handle)}


def _number(raw: str) -> float:
    return float(raw)


def _close(a: float, b: float) -> bool:
    return math.isclose(a, b, rel_tol=1e-9, abs_tol=1e-9)


def main() -> int:
    game = _game_rows()
    preview = _preview_rows()
    failures: list[str] = []

    pairs = {
        ("movement", "walk_speed_px_per_second"): "walk_speed_px_per_second",
        ("movement", "sprint_multiplier"): "sprint_speed_multiplier",
        ("movement", "sprint_animation_rate_multiplier"): "sprint_animation_rate_multiplier",
        ("movement", "sprint_gait_width_multiplier"): "sprint_gait_width_multiplier",
        ("movement", "jump_forward_speed_px_per_second"): "jump_forward_speed_px_per_second",
        ("movement", "jump_duration_seconds"): "jump_duration_seconds",
        ("movement", "double_jump_window_seconds"): "double_jump_window_seconds",
        ("movement", "double_jump_forward_speed_px_per_second"): "double_jump_forward_speed_px_per_second",
        ("movement", "double_jump_duration_seconds"): "double_jump_duration_seconds",
        ("movement", "movement_stand_delay_seconds"): "movement_stand_delay_seconds",
        ("render", "jump_scale_multiplier"): "jump_scale_multiplier",
        ("render", "double_jump_scale_multiplier"): "double_jump_scale_multiplier",
        ("render", "jump_lift_px"): "jump_lift_px",
        ("render", "double_jump_lift_px"): "double_jump_lift_px",
    }
    for game_key, preview_key in pairs.items():
        if game_key not in game:
            failures.append(f"missing game setting {game_key[0]}.{game_key[1]}")
            continue
        if preview_key not in preview:
            failures.append(f"missing preview setting {preview_key}")
            continue
        gv = _number(game[game_key])
        pv = _number(preview[preview_key])
        if not _close(gv, pv):
            failures.append(f"{game_key[1]} differs: release={gv} preview={pv}")

    required_game = {
        ("movement", "walk_speed_px_per_second"): 92.5,
        ("movement", "sprint_multiplier"): 3.0,
        ("movement", "jump_forward_speed_px_per_second"): 570.0,
        ("movement", "double_jump_forward_speed_px_per_second"): 940.0 / 3.0,
        ("movement", "double_jump_window_seconds"): 0.55,
        ("movement", "double_jump_duration_seconds"): 0.95,
        ("movement", "movement_stand_delay_seconds"): 1.0,
    }
    for key, wanted in required_game.items():
        actual = _number(game.get(key, "nan"))
        if not _close(actual, wanted):
            failures.append(f"balance contract {key[0]}.{key[1]}={actual}, expected {wanted}")

    if game.get(("controls", "camera_relative_movement"), "").lower() != "true":
        failures.append("release camera_relative_movement must remain true")
    if preview.get("sprint_control") != "hold_shift":
        failures.append("preview sprint control must be hold_shift")
    if preview.get("crouch_control") != "c":
        failures.append("preview crouch control must be C")
    if preview.get("prone_control") != "x":
        failures.append("preview prone control must be X")
    if preview.get("stand_control") != "space_or_x":
        failures.append("preview stand control must be Space or X")
    if preview.get("double_jump_landing") != "prone":
        failures.append("preview double jump must land prone")
    if preview.get("movement_cancels_crouch", "").lower() != "true":
        failures.append("preview directional movement must cancel crouch through stand transition")
    if preview.get("movement_cancels_prone", "").lower() != "true":
        failures.append("preview directional movement must cancel prone through stand transition")

    server_source = SERVER.read_text(encoding="utf-8")
    preview_source = PREVIEW.read_text(encoding="utf-8")
    source_contracts = (
        ("server walk setting", 'MOVEMENT_SETTINGS.get("walk_speed_px_per_second"' in server_source),
        ("server sprint setting", 'MOVEMENT_SETTINGS.get("sprint_multiplier"' in server_source),
        ("server double-jump drag", 'drag = 0.85 if session.jump_kind == "double_jump" else 1.15' in server_source),
        ("preview walk setting", 'movement_settings.get("walk_speed_px_per_second"' in preview_source),
        ("preview sprint setting", 'movement_settings.get("sprint_speed_multiplier"' in preview_source),
        ("preview double-jump drag", '0.85 if self.one_shot == "double_jump" else 1.15' in preview_source),
    )
    for label, okay in source_contracts:
        if not okay:
            failures.append(f"source contract missing: {label}")

    profile = int(float(game.get(("engine", "client_profile_version"), "0")))
    if profile < 282:
        failures.append(f"client profile migration marker is {profile}, expected >=282")

    if failures:
        print("MOVEMENT_CONTRACT_GATE=FAIL")
        for failure in failures:
            print(f"FAIL: {failure}")
        return 1

    walk_speed = _number(game[("movement", "walk_speed_px_per_second")])
    sprint_multiplier = _number(game[("movement", "sprint_multiplier")])
    single_jump_speed = _number(game[("movement", "jump_forward_speed_px_per_second")])
    double_jump_speed = _number(game[("movement", "double_jump_forward_speed_px_per_second")])
    print("MOVEMENT_CONTRACT_GATE=PASS")
    print(f"walk_speed_px_s={walk_speed:.3f}")
    print(f"run_speed_px_s={walk_speed * sprint_multiplier:.3f}")
    print(f"single_jump_launch_px_s={single_jump_speed:.3f}")
    print(f"double_jump_launch_px_s={double_jump_speed:.3f}")
    print("preview_release_parity=confirmed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
