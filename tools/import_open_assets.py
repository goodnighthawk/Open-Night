from __future__ import annotations

import argparse
import csv
import math
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFilter


CAR_CLASSES = (
    ("pickup", 64, 30, 58, 24, 0.90, 1.0),
    ("sports", 52, 24, 46, 20, 1.08, 1.0),
    ("truck", 76, 32, 70, 26, 0.76, 0.65),
    ("emergency", 58, 27, 52, 22, 0.96, 0.70),
    ("van", 66, 32, 60, 26, 0.86, 0.85),
)


@dataclass
class Face:
    vertices: list[int]
    texcoords: list[int | None]
    material: str


def parse_mtl(path: Path) -> dict[str, tuple[int, int, int]]:
    colors: dict[str, tuple[int, int, int]] = {}
    current = "default"
    if not path.is_file():
        return colors
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        words = raw.strip().split()
        if not words:
            continue
        if words[0] == "newmtl":
            current = " ".join(words[1:]) or "default"
        elif words[0] == "Kd" and len(words) >= 4:
            try:
                colors[current] = tuple(max(0, min(255, round(float(value) * 255))) for value in words[1:4])
            except ValueError:
                pass
    return colors


def parse_obj(path: Path) -> tuple[list[tuple[float, float, float]], list[tuple[float, float]], list[Face], dict[str, tuple[int, int, int]]]:
    vertices: list[tuple[float, float, float]] = []
    texcoords: list[tuple[float, float]] = []
    faces: list[Face] = []
    material = "default"
    mtllib = ""
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        words = raw.strip().split()
        if not words:
            continue
        if words[0] == "v" and len(words) >= 4:
            vertices.append(tuple(map(float, words[1:4])))
        elif words[0] == "vt" and len(words) >= 3:
            texcoords.append((float(words[1]), float(words[2])))
        elif words[0] == "usemtl":
            material = " ".join(words[1:]) or "default"
        elif words[0] == "mtllib":
            mtllib = " ".join(words[1:])
        elif words[0] == "f" and len(words) >= 4:
            vi: list[int] = []
            ti: list[int | None] = []
            for token in words[1:]:
                fields = token.split("/")
                vertex_index = int(fields[0])
                vi.append(vertex_index - 1 if vertex_index > 0 else len(vertices) + vertex_index)
                texture_index = int(fields[1]) if len(fields) > 1 and fields[1] else 0
                ti.append(texture_index - 1 if texture_index > 0 else None)
            faces.append(Face(vi, ti, material))
    return vertices, texcoords, faces, parse_mtl(path.with_name(mtllib)) if mtllib else {}


def _shade(color: tuple[int, int, int], normal: tuple[float, float, float]) -> tuple[int, int, int, int]:
    nx, ny, nz = normal
    length = math.sqrt(nx * nx + ny * ny + nz * nz) or 1.0
    nx, ny, nz = nx / length, ny / length, nz / length
    light = (-0.35, 0.82, 0.45)
    intensity = max(0.38, min(1.08, 0.58 + 0.50 * (nx * light[0] + ny * light[1] + nz * light[2])))
    return tuple(max(0, min(255, round(component * intensity))) for component in color) + (255,)


def render_obj(
    obj_path: Path,
    output: Path,
    *,
    yaw_degrees: float = 0.0,
    tilt_from_overhead_degrees: float = 10.0,
    palette_path: Path | None = None,
    canvas: int = 256,
) -> None:
    vertices, texcoords, faces, materials = parse_obj(obj_path)
    if not vertices or not faces:
        raise ValueError(f"No renderable geometry in {obj_path}")
    yaw = math.radians(yaw_degrees)
    cy, sy = math.cos(yaw), math.sin(yaw)
    tilt = math.radians(tilt_from_overhead_degrees)
    ct, st = math.cos(tilt), math.sin(tilt)
    transformed: list[tuple[float, float, float]] = []
    projected: list[tuple[float, float, float]] = []
    for x, y, z in vertices:
        rx, rz = cy * x - sy * z, sy * x + cy * z
        transformed.append((rx, y, rz))
        projected.append((rx, -rz * ct - y * st, y * ct - rz * st))
    min_x = min(p[0] for p in projected)
    max_x = max(p[0] for p in projected)
    min_y = min(p[1] for p in projected)
    max_y = max(p[1] for p in projected)
    span = max(max_x - min_x, max_y - min_y, 1e-6)
    margin = canvas * 0.07
    scale = (canvas - margin * 2) / span
    offset_x = (canvas - (min_x + max_x) * scale) * 0.5
    offset_y = (canvas - (min_y + max_y) * scale) * 0.5
    palette = Image.open(palette_path).convert("RGBA") if palette_path and palette_path.is_file() else None

    def face_color(face: Face) -> tuple[int, int, int]:
        if palette is not None:
            uv = [texcoords[i] for i in face.texcoords if i is not None and 0 <= i < len(texcoords)]
            if uv:
                u = sum(item[0] for item in uv) / len(uv)
                v = sum(item[1] for item in uv) / len(uv)
                px = max(0, min(palette.width - 1, round(u * (palette.width - 1))))
                py = max(0, min(palette.height - 1, round((1.0 - v) * (palette.height - 1))))
                return palette.getpixel((px, py))[:3]
        return materials.get(face.material, (134, 142, 143))

    draw_rows = []
    for face in faces:
        if len(face.vertices) < 3:
            continue
        points3 = [transformed[i] for i in face.vertices]
        a, b, c = points3[0], points3[1], points3[2]
        ab = (b[0] - a[0], b[1] - a[1], b[2] - a[2])
        ac = (c[0] - a[0], c[1] - a[1], c[2] - a[2])
        normal = (
            ab[1] * ac[2] - ab[2] * ac[1],
            ab[2] * ac[0] - ab[0] * ac[2],
            ab[0] * ac[1] - ab[1] * ac[0],
        )
        points2 = [(projected[i][0] * scale + offset_x, projected[i][1] * scale + offset_y) for i in face.vertices]
        depth = sum(projected[i][2] for i in face.vertices) / len(face.vertices)
        draw_rows.append((depth, points2, _shade(face_color(face), normal)))
    fills = Image.new("RGBA", (canvas, canvas), (0, 0, 0, 0))
    draw = ImageDraw.Draw(fills)
    for _depth, points, color in sorted(draw_rows, key=lambda item: item[0]):
        draw.polygon(points, fill=color)
    alpha = fills.getchannel("A")
    expanded = alpha.filter(ImageFilter.MaxFilter(5))
    outline_alpha = ImageChops.subtract(expanded, alpha)
    image = Image.new("RGBA", (canvas, canvas), (24, 24, 23, 0))
    image.putalpha(outline_alpha)
    image.alpha_composite(fills)
    output.parent.mkdir(parents=True, exist_ok=True)
    image.save(output, optimize=True)


def build_dust_atlas(source: Path, output: Path) -> None:
    picks = (0, 3, 6, 9, 12, 15, 19, 24)
    atlas = Image.new("RGBA", (64 * len(picks), 64), (0, 0, 0, 0))
    for index, source_index in enumerate(picks):
        image = Image.open(source / f"whitePuff{source_index:02d}.png").convert("RGBA")
        alpha = image.getchannel("A")
        bbox = alpha.getbbox()
        if bbox:
            image = image.crop(bbox)
        image.thumbnail((60, 48), Image.Resampling.LANCZOS)
        gray = ImageEnhance.Contrast(image.convert("L")).enhance(1.25)
        tint = Image.new("RGBA", image.size, (172, 158, 133, 0))
        tint.putalpha(Image.eval(gray, lambda value: max(0, min(190, int(value * 0.72)))))
        atlas.alpha_composite(tint, (index * 64 + (64 - tint.width) // 2, 64 - tint.height - 4))
    output.parent.mkdir(parents=True, exist_ok=True)
    atlas.save(output, optimize=True)


def write_catalog(output_root: Path) -> None:
    rows = []
    for offset, (category, render_length, render_width, collision_length, collision_width, speed_factor, weight) in enumerate(CAR_CLASSES, 1):
        rows.append({
            "asset_id": f"arcade_car_{offset:02d}",
            "runtime_file": f"vehicles/arcade_car_{offset:02d}_topdown.png",
            "source_path": f"Assets/Arcade_Car_Physics/Models/Car{offset:02d}.obj",
            "asset_type": "vehicle_sprite",
            "camera_mode": "topdown",
            "license": "user_created",
            "runtime_status": "active",
            "notes": f"{category}; render {render_length}x{render_width}; collision {collision_length}x{collision_width}; speed {speed_factor}; weight {weight}",
        })
    rows.extend((
        {"asset_id": "sprint_dust_8", "runtime_file": "effects/sprint_dust_8.png", "source_path": "Assets/Arcade_Car_Physics/Textures/White puff", "asset_type": "effect_atlas", "camera_mode": "both", "license": "user_created", "runtime_status": "active", "notes": "Eight-frame approved-palette sprint dust"},
        {"asset_id": "city_building_01_topdown", "runtime_file": "city/city_building_01_topdown.png", "source_path": "Assets/CityVoxelPack/Assets/buildings/medium/Meshes/building1.obj", "asset_type": "building_sprite", "camera_mode": "topdown", "license": "user_created", "runtime_status": "active", "notes": "Top-down adaptation for the movement tester"},
        {"asset_id": "city_building_01_isometric", "runtime_file": "city/city_building_01_isometric.png", "source_path": "Assets/CityVoxelPack/Assets/buildings/medium/Meshes/building1.obj", "asset_type": "building_sprite", "camera_mode": "isometric", "license": "user_created", "runtime_status": "active", "notes": "2.5D rooftop-module adaptation for game and tester"},
        {"asset_id": "character_running_fbx", "runtime_file": "", "source_path": "Assets/character/Player/Character@Running.fbx", "asset_type": "motion_source", "camera_mode": "3d_source", "license": "user_created", "runtime_status": "active_timing_reference", "notes": "Mapped to the dual-camera walk_8 art at run cadence"},
    ))
    path = output_root / "catalog.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=tuple(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def make_preview(output_root: Path) -> None:
    preview = Image.new("RGBA", (920, 500), (27, 31, 31, 255))
    draw = ImageDraw.Draw(preview)
    draw.text((24, 16), "OPEN-ASSET PYGAME ADAPTATION — 5 VEHICLES + RUN EFFECT", fill=(238, 232, 208, 255))
    for index in range(1, 6):
        image = Image.open(output_root / "vehicles" / f"arcade_car_{index:02d}_topdown.png").convert("RGBA")
        image.thumbnail((150, 150), Image.Resampling.NEAREST)
        x = 22 + (index - 1) * 175
        preview.alpha_composite(image, (x + (150 - image.width) // 2, 58))
        draw.text((x + 34, 216), f"ARCADE CAR {index:02d}", fill=(173, 199, 197, 255))
    for index, name in enumerate(("city_building_01_topdown.png", "city_building_01_isometric.png")):
        image = Image.open(output_root / "city" / name).convert("RGBA")
        image.thumbnail((180, 180), Image.Resampling.NEAREST)
        x = 42 + index * 240
        preview.alpha_composite(image, (x, 272))
    dust = Image.open(output_root / "effects" / "sprint_dust_8.png").convert("RGBA")
    dust = dust.resize((384, 48), Image.Resampling.NEAREST)
    preview.alpha_composite(dust, (510, 338))
    draw.text((552, 402), "8-FRAME SPRINT DUST", fill=(214, 190, 135, 255))
    preview.save(output_root / "preview.png", optimize=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Convert compatible Unity open assets into Pygame-ready 2D sprites")
    parser.add_argument("source_assets", type=Path, help="Extracted Unity Assets directory")
    parser.add_argument("output", type=Path, help="Output directory")
    args = parser.parse_args()
    source = args.source_assets.resolve()
    output = args.output.resolve()
    car_models = source / "Arcade_Car_Physics" / "Models"
    for index in range(1, 6):
        render_obj(car_models / f"Car{index:02d}.obj", output / "vehicles" / f"arcade_car_{index:02d}_topdown.png")
    build_dust_atlas(source / "Arcade_Car_Physics" / "Textures" / "White puff", output / "effects" / "sprint_dust_8.png")
    city = source / "CityVoxelPack" / "Assets" / "buildings" / "medium"
    render_obj(city / "Meshes" / "building1.obj", output / "city" / "city_building_01_topdown.png", palette_path=city / "Textures" / "building1.png", tilt_from_overhead_degrees=4.0)
    render_obj(city / "Meshes" / "building1.obj", output / "city" / "city_building_01_isometric.png", palette_path=city / "Textures" / "building1.png", yaw_degrees=45.0, tilt_from_overhead_degrees=35.0)
    write_catalog(output)
    make_preview(output)
    print(f"Imported runtime-ready assets to {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
