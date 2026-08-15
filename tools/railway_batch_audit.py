from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BATCH = ROOT / "DEPLOY_OPEN_NIGHT_SERVER.bat"


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

    print("RAILWAY BATCH AUDIT: PASS")
    print("All npm railway.cmd commands use CALL; unified exit-code pause is present.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
