from __future__ import annotations

import csv
import hashlib
import json
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Any

from mapfiles.loader import load_map_folder
from portable_paths import ensure_shared_layout

FORMAT = "PYMMO_PORTABLE_MAP"
FORMAT_VERSION = 1


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def read_document(map_path: Path) -> dict[str, Any]:
    path = Path(map_path).expanduser().resolve()
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("format") != FORMAT:
        raise ValueError(f"Unsupported .map format: {data.get('format')!r}")
    if int(data.get("format_version", 0)) != FORMAT_VERSION:
        raise ValueError(f"Unsupported .map version: {data.get('format_version')!r}")
    if not isinstance(data.get("tables"), dict):
        raise ValueError("Portable .map is missing tables")
    return data


def map_fingerprint(map_path: Path, data: dict | None = None) -> str:
    path = Path(map_path).expanduser().resolve()
    data = data or read_document(path)
    h = hashlib.sha256(path.read_bytes())
    asset_root = path.parent / str(data.get("asset_root", ""))
    if asset_root.is_dir():
        for file_path in sorted(p for p in asset_root.rglob("*") if p.is_file()):
            rel = file_path.relative_to(asset_root).as_posix().encode("utf-8")
            h.update(rel); h.update(b"\0"); h.update(bytes.fromhex(_sha256_file(file_path)))
    return h.hexdigest()


def validate_portable_map(map_path: Path, verify_hashes: bool = True) -> list[str]:
    path = Path(map_path).expanduser().resolve()
    errors: list[str] = []
    try:
        data = read_document(path)
    except Exception as exc:
        return [str(exc)]
    asset_root = path.parent / str(data.get("asset_root", ""))
    if not asset_root.is_dir():
        errors.append(f"Portable map asset folder missing: {asset_root}")
        return errors
    for row in data.get("asset_manifest", []) or []:
        rel = str(row.get("path", ""))
        p = asset_root / rel
        if not p.is_file():
            errors.append(f"Missing map asset: {rel}")
        elif verify_hashes and row.get("sha256") and _sha256_file(p) != str(row["sha256"]):
            errors.append(f"Map asset hash mismatch: {rel}")
    return errors


def _write_table(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields: list[str] = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        if not fields:
            f.write("")
            return
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader(); w.writerows(rows)


def _catalog(asset_root: Path) -> dict[str, dict[str, str]]:
    p = asset_root / "catalogs" / "object_catalog.csv"
    if not p.exists():
        return {}
    with p.open("r", encoding="utf-8-sig", newline="") as f:
        return {str(r.get("archetype_id", "")): dict(r) for r in csv.DictReader(f) if r.get("archetype_id")}


def _portable_visual_bindings(data: dict, asset_root: Path) -> dict[str, Any]:
    cosmetics = data.get("cosmetics", {}) or {}
    catalog = _catalog(asset_root)
    mode = str(data.get("default_render_mode", "night") or "night").lower()
    by_object = {str(r.get("object_id", "")): r for r in cosmetics.get("cosmetic_instances", []) if r.get("object_id")}
    prop_sprites: dict[str, str] = {}
    archetype_sprites: dict[str, str] = {}
    sprite_key = "night_sprite" if mode == "night" else "day_sprite"
    # Expose every portable archetype, not only semantic street props.  The
    # screenshot generator's zero-collision dressing layer uses these same
    # reusable assets and should therefore survive server/client distribution.
    for aid, cat in catalog.items():
        rel = str(cat.get(sprite_key, ""))
        if rel:
            ap = asset_root / rel
            if ap.is_file(): archetype_sprites[str(aid)] = str(ap)
    for object_id, row in by_object.items():
        if not object_id.startswith("prop:"):
            continue
        aid = str(row.get("archetype_id", ""))
        if aid in archetype_sprites:
            prop_sprites[object_id.split(":", 1)[1]] = archetype_sprites[aid]
    suffix = "night" if mode == "night" else "day"
    material_names = {
        "land": f"land_{suffix}.png", "road": f"asphalt_{suffix}.png",
        "sidewalk": f"sidewalk_{suffix}.png", "curb": f"curb_{suffix}.png",
        "water": f"water_{suffix}.png", "green": f"grass_{suffix}.png",
        "roof": f"roof_tar_{suffix}.png", "plaza": f"plaza_{suffix}.png",
    }
    materials = {}
    for key, name in material_names.items():
        p = asset_root / "textures" / "materials" / name
        if p.is_file(): materials[key] = str(p)
    return {
        "portable_prop_sprites": prop_sprites,
        "portable_archetype_sprites": archetype_sprites,
        "portable_materials": materials,
        "portable_light_emitters": cosmetics.get("light_emitters", []),
        "portable_cosmetics": cosmetics,
    }


def load_portable_map(map_path: Path, *, verify_hashes: bool = True) -> dict:
    path = Path(map_path).expanduser().resolve()
    errors = validate_portable_map(path, verify_hashes=verify_hashes)
    if errors:
        raise ValueError("; ".join(errors[:8]))
    data = read_document(path)
    digest = map_fingerprint(path, data)
    cache_root = ensure_shared_layout()["maps"] / "runtime_tables" / digest
    cache_root.mkdir(parents=True, exist_ok=True)
    for stem, rows in (data.get("tables", {}) or {}).items():
        _write_table(cache_root / f"{stem}.csv", list(rows or []))
    cfg = load_map_folder(cache_root, attach_grid=False)
    asset_root = path.parent / str(data.get("asset_root", ""))
    cfg.update(_portable_visual_bindings(data, asset_root))
    cfg["name"] = str(data.get("display_name") or cfg.get("name") or path.stem)
    cfg["description"] = f"Portable server map: {path.name}"
    cfg["map_build_id"] = digest[:20]
    cfg["default_render_mode"] = str(data.get("default_render_mode", "night"))
    cfg["default_lighting_profile"] = str(data.get("default_lighting_profile", "night_callback"))
    cfg["street_lamps_enabled"] = bool(data.get("street_lamps_enabled", True))
    cfg["_portable_map_hash"] = digest
    cfg["_portable_map_path"] = str(path)
    cfg["_portable_asset_root"] = str(asset_root)
    cfg["_portable_generator_version"] = str(data.get("generator_version", ""))
    return cfg


def build_transfer_bundle(map_path: Path) -> dict[str, Any]:
    path = Path(map_path).expanduser().resolve()
    data = read_document(path)
    errors = validate_portable_map(path, verify_hashes=True)
    if errors: raise ValueError("; ".join(errors[:8]))
    digest = map_fingerprint(path, data)
    out_dir = ensure_shared_layout()["maps"] / "server_transfer"
    out_dir.mkdir(parents=True, exist_ok=True)
    bundle = out_dir / f"{digest}.mapbundle"
    asset_root = path.parent / str(data.get("asset_root", ""))
    if not bundle.exists():
        with zipfile.ZipFile(bundle, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as z:
            z.write(path, path.name)
            for p in sorted(x for x in asset_root.rglob("*") if x.is_file()):
                z.write(p, f"{asset_root.name}/{p.relative_to(asset_root).as_posix()}")
    return {
        "hash": digest, "path": bundle, "size_bytes": bundle.stat().st_size,
        "map_filename": path.name, "map_id": str(data.get("map_id", "portable_map")),
        "display_name": str(data.get("display_name", path.stem)),
    }


def cached_map_hashes() -> list[str]:
    root = ensure_shared_layout()["maps"] / "client_cache"
    if not root.exists(): return []
    return sorted(p.name for p in root.iterdir() if p.is_dir() and (p / ".ready.json").is_file())[-16:]


def install_transfer_bundle(payload: bytes, expected_hash: str) -> Path:
    digest = str(expected_hash).strip().lower()
    if len(digest) < 32: raise ValueError("Invalid map hash")
    root = ensure_shared_layout()["maps"] / "client_cache" / digest
    if root.exists(): shutil.rmtree(root)
    root.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as f:
        f.write(payload); tmp = Path(f.name)
    try:
        with zipfile.ZipFile(tmp, "r") as z:
            for info in z.infolist():
                dest = (root / info.filename).resolve()
                if root.resolve() not in dest.parents and dest != root.resolve():
                    raise ValueError("Unsafe path in map transfer")
            z.extractall(root)
    finally:
        tmp.unlink(missing_ok=True)
    maps = list(root.glob("*.map"))
    if len(maps) != 1: raise ValueError("Transferred package must contain exactly one .map")
    actual = map_fingerprint(maps[0], read_document(maps[0]))
    if actual != digest:
        shutil.rmtree(root, ignore_errors=True)
        raise ValueError("Transferred map hash verification failed")
    (root / ".ready.json").write_text(json.dumps({"hash": digest, "map_filename": maps[0].name}), encoding="utf-8")
    return maps[0]


def load_cached_map(digest: str) -> dict:
    root = ensure_shared_layout()["maps"] / "client_cache" / str(digest)
    ready = json.loads((root / ".ready.json").read_text(encoding="utf-8"))
    return load_portable_map(root / str(ready["map_filename"]), verify_hashes=True)
