from __future__ import annotations

"""Build Pass 19 while freezing the approved Pass 18 world geometry.

This wrapper changes only the deterministic building-art assignment policy. Roads,
water/green masks, crossings, block footprints, bridge geometry and collision
footprints continue to come from build_unified_composition.py.
"""

import math
import sys
from collections import Counter, defaultdict, deque
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import build_unified_composition as base


PASS_ID = "art_convergence_pass_19"
usage: dict[str, Counter[tuple[str, int]]] = defaultdict(Counter)
recent: dict[str, deque[tuple[str, int]]] = defaultdict(lambda: deque(maxlen=5))


def _candidate_set(district: str, landmark: bool) -> list[tuple[str, int]]:
    fort = "fort_lee_blocks_v1.png"
    heights = "washington_heights_blocks_v1.png"
    compact = "compact_lot_blocks_v1.png"
    if district == "fort_lee":
        return [(fort, cell) for cell in range(16)] + [(compact, cell) for cell in range(8)]
    if landmark:
        return [(heights, cell) for cell in (7, 12, 14)] + [(compact, 15)]
    return ([(heights, cell) for cell in range(16) if cell not in {7, 12, 14}]
            + [(compact, cell) for cell in range(8, 15)])


def choose_building_sprite(district: str, width: float, height: float, sequence: int, landmark: bool = False) -> dict:
    """Choose a native-scale sprite, then prefer underused visually suitable peers.

    Geometry and accepted component scale remain dominant. Diversity is allowed to
    break close visual matches; it cannot rescue an undersized or badly stretched
    candidate merely to make the map look different.
    """
    candidates = _candidate_set(district, landmark)
    metrics = {
        atlas: base.building_atlas_metrics(atlas)
        for atlas in {atlas for atlas, _ in candidates}
    }
    evaluated = []
    preferred = sequence % max(1, len(candidates))
    for candidate_index, (atlas, cell) in enumerate(candidates):
        source_w, source_h = metrics[atlas][cell]
        fit = min(
            width / (source_w * base.ATLAS_WORLD_UNITS_PER_PIXEL),
            height / (source_h * base.ATLAS_WORLD_UNITS_PER_PIXEL),
        )
        render = min(base.MAX_BUILDING_SPRITE_SCALE, fit)
        bounded_error = abs(1.0 - min(base.MAX_BUILDING_SPRITE_SCALE,
                                      max(base.MIN_BUILDING_SPRITE_SCALE, fit)))
        outlier = max(0.0, base.MIN_BUILDING_SPRITE_SCALE - fit) * 8.0
        oversize = max(0.0, fit - base.MAX_BUILDING_SPRITE_SCALE) * 0.35
        aspect_error = abs(math.log(max(0.05, width / height) /
                                    max(0.05, source_w / source_h))) * 0.12
        deterministic = abs(candidate_index - preferred) * 0.0012
        native_score = bounded_error + outlier + oversize + aspect_error + deterministic
        evaluated.append((native_score, atlas, cell, source_w, source_h, fit, render))

    best_native = min(item[0] for item in evaluated)
    # Only close native-size alternatives may enter the diversity competition.
    # A 0.055 score window is intentionally narrow compared with the scale and
    # undersize penalties above.
    shortlist = [item for item in evaluated
                 if item[0] <= best_native + 0.055
                 and item[5] >= base.MIN_BUILDING_SPRITE_SCALE]
    if not shortlist:
        shortlist = [min(evaluated)]

    def convergence_score(item):
        native_score, atlas, cell, *_ = item
        key = (atlas, cell)
        used = usage[district][key]
        recent_rows = recent[district]
        # Frequency pressure grows gently. Immediate/nearby repetition is more
        # expensive because adjacent clones are the most obvious procedural tell.
        use_penalty = used * 0.010
        recency_penalty = 0.0
        if recent_rows:
            if key == recent_rows[-1]:
                recency_penalty += 0.090
            elif key in recent_rows:
                recency_penalty += 0.040
        return native_score + use_penalty + recency_penalty

    selected = min(shortlist, key=convergence_score)
    _, atlas, cell, source_w, source_h, fit, render = selected
    key = (atlas, cell)
    usage[district][key] += 1
    recent[district].append(key)
    return {
        "cosmetic_atlas": atlas,
        "cosmetic_cell": cell,
        "cosmetic_source_bbox_w": round(source_w, 2),
        "cosmetic_source_bbox_h": round(source_h, 2),
        "cosmetic_fit_scale_ratio": round(fit, 4),
        "cosmetic_render_scale_ratio": round(render, 4),
        "cosmetic_scale_status": "pass" if fit >= base.MIN_BUILDING_SPRITE_SCALE else "undersized_lot",
    }


def main() -> None:
    usage.clear()
    recent.clear()
    base.PASS_ID = PASS_ID
    base.choose_building_sprite = choose_building_sprite
    # The source generator already owns all accepted Pass 18 geometry. Calling
    # its main pipeline regenerates semantic CSVs, day/night masters and tiles
    # with only the art-assignment policy replaced above.
    base.main()
    total = sum(sum(counter.values()) for counter in usage.values())
    unique = len({key for counter in usage.values() for key in counter})
    max_use = max((count for counter in usage.values() for count in counter.values()), default=0)
    print(f"PASS19_ART_ASSIGNMENT buildings={total} unique_styles={unique} max_style_use={max_use}")
    print("Next: review unified_composition_day/night.png, then run promote_unified_composition.py only after visual approval.")


if __name__ == "__main__":
    main()
