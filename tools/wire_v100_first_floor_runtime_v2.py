#!/usr/bin/env python3
"""Precision wrapper for the v1.0 First Floor runtime patch.

The loader currently stores interiors in a compact one-line list comprehension;
this wrapper patches that exact current form while preserving every other
exact-anchor safety check in ``wire_v100_first_floor_runtime.py``.
"""
from __future__ import annotations

import wire_v100_first_floor_runtime as wire


def patch_loader_precise() -> bool:
    text = wire.LOADER.read_text(encoding="utf-8")
    marker = '"building_id": str(r.get("building_id", ""))'
    if marker in text:
        return False
    old = '    cfg["interiors"] = [{"id": str(r.get("id", "")), "name": str(r.get("name", "")), "kind": str(r.get("kind", "interior")), "entry": [_float(r.get("entry_x")), _float(r.get("entry_y"))]} for r in _rows(folder / "interiors.csv")]\n'
    new = '    cfg["interiors"] = [{"id": str(r.get("id", "")), "name": str(r.get("name", "")), "kind": str(r.get("kind", "interior")), "entry": [_float(r.get("entry_x")), _float(r.get("entry_y"))], "building_id": str(r.get("building_id", "")), "door_hint": str(r.get("door_hint", ""))} for r in _rows(folder / "interiors.csv")]\n'
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"loader interior building binding: expected compact loader anchor once, found {count}")
    wire.LOADER.write_text(text.replace(old, new, 1), encoding="utf-8")
    return True


def main() -> None:
    wire.patch_loader = patch_loader_precise
    wire.main()


if __name__ == "__main__":
    main()
