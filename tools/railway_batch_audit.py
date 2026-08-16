from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BATCH = ROOT / "DEPLOY_OPEN_NIGHT_SERVER.bat"
RAILWAY = ROOT / "railway.toml"
RAILWAY_IGNORE = ROOT / ".railwayignore"

# Cloud upload proxies reject an archive near 200 MiB.  Keep a safety margin so
# a small source update cannot unexpectedly make the next deployment fail.
MAX_ESTIMATED_UPLOAD_BYTES = 180 * 1024 * 1024


def _estimated_upload_bytes() -> int:
    """Conservative size estimate for the Railway source archive.

    Railway also applies .gitignore and compresses the upload, so this scan is
    intentionally an upper bound.  It only models the directory exclusions we
    require below plus Railway's built-in .git/node_modules exclusions.
    """
    ignored_prefixes = (
        ".git/",
        ".venv/",
        "node_modules/",
        "stress_results/",
        "build_previews/",
        "art_review/",
        "dev_tools/",
        "assets/art_review_targets/",
    )
    total = 0
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(ROOT).as_posix()
        if rel.startswith(ignored_prefixes):
            continue
        if "/__pycache__/" in f"/{rel}" or rel.endswith((".pyc", ".pyo", ".log")):
            continue
        total += path.stat().st_size
    return total


def main() -> int:
    source = BATCH.read_text(encoding="utf-8", errors="strict")
    lowered = source.lower()
    required = (
        "call :main",
        "call railway.cmd status",
        "call railway.cmd link",
        "call railway.cmd up",
        "set \"deploy_rc=%errorlevel%\"",
        "pause >nul",
        ":missing_railway",
        ":link_failed",
        ":deploy_failed",
    )
    missing = [token for token in required if token not in lowered]
    if missing:
        raise SystemExit("Railway deployment batch missing: " + ", ".join(missing))

    bare_calls = []
    for number, line in enumerate(source.splitlines(), start=1):
        command = line.strip().lower()
        if command.startswith("railway ") or command.startswith("railway.cmd "):
            bare_calls.append(f"line {number}: {line.strip()}")
    if bare_calls:
        raise SystemExit("Railway command would terminate parent batch:\n" + "\n".join(bare_calls))

    railway = RAILWAY.read_text(encoding="utf-8", errors="strict").lower()
    railway_required = (
        "pymmo_reset_db_on_patch=true",
        "pymmo_patch_id=open-night-v0.8.1",
        "--no-discovery",
    )
    railway_missing = [token for token in railway_required if token not in railway]
    if "--memory-db" in railway:
        raise SystemExit("Railway still uses --memory-db; MySQL persistence would be disabled.")
    if railway_missing:
        raise SystemExit("Railway MySQL patch-reset config missing: " + ", ".join(railway_missing))

    railway_ignore = RAILWAY_IGNORE.read_text(encoding="utf-8", errors="strict").lower()
    ignore_required = (
        "build_previews/",
        "art_review/",
        "dev_tools/",
        "assets/art_review_targets/",
    )
    ignore_missing = [token for token in ignore_required if token not in railway_ignore]
    if ignore_missing:
        raise SystemExit("Railway upload-size exclusions missing: " + ", ".join(ignore_missing))

    runtime_required = (
        ROOT / "server.py",
        ROOT / "database.py",
        ROOT / "common.py",
        ROOT / "mapfiles" / "data" / "map_001_gwb_corridor" / "map.csv",
        ROOT / "assets" / "cars" / "vehicle_manifest.csv",
        ROOT / "assets" / "characters" / "master_dual_camera" / "config" / "paired_parts.csv",
    )
    runtime_missing = [str(path.relative_to(ROOT)) for path in runtime_required if not path.is_file()]
    if runtime_missing:
        raise SystemExit("Railway runtime files missing: " + ", ".join(runtime_missing))

    estimated_bytes = _estimated_upload_bytes()
    if estimated_bytes > MAX_ESTIMATED_UPLOAD_BYTES:
        raise SystemExit(
            "Estimated Railway upload is too large: "
            f"{estimated_bytes / (1024 * 1024):.1f} MiB "
            f"(limit for this audit: {MAX_ESTIMATED_UPLOAD_BYTES / (1024 * 1024):.0f} MiB)."
        )

    server = (ROOT / "server.py").read_text(encoding="utf-8", errors="strict").lower()
    database = (ROOT / "database.py").read_text(encoding="utf-8", errors="strict").lower()
    setup = (ROOT / "RAILWAY_SETUP.md").read_text(encoding="utf-8", errors="strict").lower()
    if "create table if not exists bug_reports" not in database:
        raise SystemExit("Railway MySQL schema is missing the moderated bug-report queue.")
    for token in ("pymmo_bug_admin_token", "bug_admin_hello", "bug_report_submit"):
        if token not in server and token not in setup:
            raise SystemExit(f"Railway bug moderation setup missing: {token}")

    print("RAILWAY BATCH AUDIT: PASS")
    print(
        "All railway.cmd calls return safely; MySQL patch reset and moderated reports are enabled."
    )
    print(f"Conservative upload estimate: {estimated_bytes / (1024 * 1024):.1f} MiB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
