from __future__ import annotations

import shutil
from pathlib import Path
from portable_paths import APP_DIR, ensure_shared_layout, shared_root

def copy_missing_tree(src: Path, dst: Path) -> int:
    copied = 0
    if not src.exists(): return copied
    for path in src.rglob("*"):
        if not path.is_file(): continue
        rel = path.relative_to(src); target = dst / rel
        if target.exists(): continue
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target); copied += 1
    return copied

def copy_missing_configs(src: Path, dst: Path) -> int:
    copied=0
    for path in src.glob("*.csv"):
        target=dst/path.name
        if not target.exists(): shutil.copy2(path,target); copied+=1
    return copied

def main() -> int:
    paths=ensure_shared_layout()
    assets=copy_missing_tree(APP_DIR/"assets", paths["assets"])
    configs=copy_missing_configs(APP_DIR/"config", paths["config"])
    print("="*68)
    print("PYTHON MMO v2.5 — PORTABLE DATA READY")
    print("="*68)
    print(f"Code folder : {APP_DIR}")
    print(f"Shared data : {shared_root()}")
    print(f"New reusable assets copied : {assets}")
    print(f"New reusable configs copied: {configs}")
    print("Map 001 is the accepted screenshot-derived release-authoritative default map.")
    return 0

if __name__ == "__main__": raise SystemExit(main())
