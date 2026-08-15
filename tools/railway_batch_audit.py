from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BATCH = ROOT / "DEPLOY_OPEN_NIGHT_SERVER.bat"
RAILWAY = ROOT / "railway.toml"


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
    railway_required = ("pymmo_reset_db_on_patch=true", "pymmo_patch_id=", "--no-discovery")
    railway_missing = [token for token in railway_required if token not in railway]
    if "--memory-db" in railway:
        raise SystemExit("Railway still uses --memory-db; MySQL persistence would be disabled.")
    if railway_missing:
        raise SystemExit("Railway MySQL patch-reset config missing: " + ", ".join(railway_missing))

    print("RAILWAY BATCH AUDIT: PASS")
    print("All railway.cmd calls return safely; Railway MySQL patch-reset mode is enabled.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
