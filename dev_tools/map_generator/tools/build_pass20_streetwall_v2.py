from __future__ import annotations

"""Pass 20 RC2.

The first exact-clearance candidate showed that three otherwise road-safe buildings
could not back out of the sidewalk envelope because the generic six-unit
building-to-building buffer blocked the move. Urban street walls are allowed to
abut, so this wrapper removes only that artificial inter-building buffer. It does
not weaken the road or sidewalk acceptance thresholds.
"""

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import build_pass20_streetwall as pass20


def streetwall_overlap(a, b, clearance=0.0) -> bool:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    return not (
        ax + aw + clearance <= bx or bx + bw + clearance <= ax or
        ay + ah + clearance <= by or by + bh + clearance <= ay
    )


def main() -> None:
    pass20.PASS_ID = "pass_20_streetwall_frontage_rc2"
    pass20.overlaps = streetwall_overlap
    pass20.main()


if __name__ == "__main__":
    main()
