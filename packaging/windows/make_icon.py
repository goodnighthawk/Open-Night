from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image


def build_icon(source: Path, output: Path) -> None:
    logo = Image.open(source).convert("RGBA")
    alpha_box = logo.getchannel("A").getbbox()
    if alpha_box:
        logo = logo.crop(alpha_box)

    # The emblem occupies the upper part of the portrait lockup and remains
    # recognizable at taskbar sizes; the wordmark is intentionally omitted.
    emblem_height = max(1, int(logo.height * 0.72))
    emblem = logo.crop((0, 0, logo.width, emblem_height))
    emblem.thumbnail((448, 448), Image.Resampling.LANCZOS)

    canvas = Image.new("RGBA", (512, 512), (0, 0, 0, 0))
    x = (canvas.width - emblem.width) // 2
    y = (canvas.height - emblem.height) // 2
    canvas.alpha_composite(emblem, (x, y))

    output.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(
        output,
        format="ICO",
        sizes=((16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the Snakepit Windows application icon")
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    build_icon(args.source, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
