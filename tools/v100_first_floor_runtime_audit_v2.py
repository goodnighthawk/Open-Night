#!/usr/bin/env python3
"""Formatting-tolerant source-contract wrapper for the First Floor audit.

All semantic/collision/render checks remain in ``v100_first_floor_runtime_audit``.
Only the client input source check is made structural rather than dependent on a
single-line formatting choice.
"""
from __future__ import annotations

from pathlib import Path

import v100_first_floor_runtime_audit as audit

ROOT = Path(__file__).resolve().parents[1]


def _function_block(text: str, name: str) -> str:
    anchor = f"    def {name}("
    start = text.find(anchor)
    if start < 0:
        audit.fail(f"Function missing: {name}")
    end = text.find("\n    def ", start + len(anchor))
    return text[start:end if end >= 0 else None]


def precise_source_contract_checks() -> None:
    interior_art = (ROOT / "interior_art.py").read_text(encoding="utf-8")
    client = (ROOT / "client.py").read_text(encoding="utf-8")
    server = (ROOT / "server.py").read_text(encoding="utf-8")
    common = (ROOT / "common.py").read_text(encoding="utf-8")
    loader = (ROOT / "mapfiles/loader.py").read_text(encoding="utf-8")

    for marker in ("def iso(", "TILE_W = 64", "TILE_H = 32", "self.iso(", "iso_x =", "iso_y ="):
        if marker in interior_art:
            audit.fail(f"Legacy isometric runtime marker present: {marker}")
    for marker in (
        "world-registered First Floor renderer",
        "interior_floor_rect(self.map_config",
        'mode="topdown"',
        "FIRST FLOOR · WORLD REGISTERED",
    ):
        if marker not in interior_art:
            audit.fail(f"First Floor renderer marker missing: {marker}")

    for marker in (
        "IsometricInterior(self.map_config)",
        "self.interior.set_map(self.map_config)",
        "Movement is sampled continuously in send_input()",
        'float(message.get("x", 0.0) or 0.0)',
    ):
        if marker not in client:
            audit.fail(f"First Floor client marker missing: {marker}")

    send_input = _function_block(client, "send_input")
    for marker in (
        "if self.interior.active:",
        "movement_vector(blocked=interior_blocked)",
        '"type": "interior_move"',
        '"dx": ix',
        '"dy": iy',
        "return",
    ):
        if marker not in send_input:
            audit.fail(f"First Floor send_input contract missing: {marker}")

    for marker in (
        "interior_start_world(ACTIVE_MAP, player.interior_id)",
        "nx, ny, aim = interior_move_world(",
        'dx, dy = float(message.get("dx", 0.0)), float(message.get("dy", 0.0))',
        '"x": round(float(player.interior_x), 2)',
    ):
        if marker not in server:
            audit.fail(f"First Floor server marker missing: {marker}")
    if "interior_step(" in server or "INTERIOR_START_TILE" in server:
        audit.fail("Server still uses detached grid interior movement")
    if "interior_x: float = 0.0" not in common or '"interior_x": round(float(self.interior_x), 2)' not in common:
        audit.fail("PlayerState does not serialize world-space First Floor coordinates")
    if '"building_id": str(r.get("building_id", ""))' not in loader:
        audit.fail("Map loader does not preserve explicit interior building binding")


def main() -> None:
    audit.source_contract_checks = precise_source_contract_checks
    audit.main()


if __name__ == "__main__":
    main()
