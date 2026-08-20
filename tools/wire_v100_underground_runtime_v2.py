#!/usr/bin/env python3
"""Precision wrapper for the v1.0 Underground runtime wiring patch.

The original patch intentionally aborts when a source anchor is ambiguous. In
``environment_art.py`` the Ground composition scale/Y pair occurs in two
functions. This wrapper narrows that one replacement to
``_draw_baked_composition()`` while preserving every other exact-anchor safety
check and the original idempotent patch implementation.
"""
from __future__ import annotations

import wire_v100_underground_runtime as wire

_original_replace_once = wire.replace_once


def precise_replace_once(
    text: str,
    old: str,
    new: str,
    *,
    label: str,
    marker: str | None = None,
) -> tuple[str, bool]:
    if label != "composition scale selector":
        return _original_replace_once(text, old, new, label=label, marker=marker)
    if marker and marker in text:
        return text, False

    method_start = text.find("    def _draw_baked_composition(")
    if method_start < 0:
        raise RuntimeError("composition scale selector: _draw_baked_composition() missing")
    method_end = text.find("\n    def ", method_start + 8)
    if method_end < 0:
        method_end = len(text)
    block = text[method_start:method_end]
    count = block.count(old)
    if count != 1:
        raise RuntimeError(
            "composition scale selector: expected exactly one scale/Y pair "
            f"inside _draw_baked_composition(), found {count}"
        )
    patched = block.replace(old, new, 1)
    return text[:method_start] + patched + text[method_end:], True


def main() -> None:
    wire.replace_once = precise_replace_once
    wire.main()


if __name__ == "__main__":
    main()
