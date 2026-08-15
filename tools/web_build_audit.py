from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from prepare_web_stage import prepare

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = {
    "main.py", "client.py", "common.py", "server_directory.py", "assets", "config", "gameplay", "mapfiles", "VERSION.txt"
}
FORBIDDEN_AUDIO = {".wav", ".mp3", ".aiff", ".aif", ".au"}


def main() -> int:
    stage = Path(tempfile.mkdtemp(prefix="python_mmo_v25_web_audit_"))
    problems: list[str] = []
    try:
        prepare(stage)
        present = {p.name for p in stage.iterdir()}
        missing = sorted(REQUIRED - present)
        if missing:
            problems.append("missing required staged items: " + ", ".join(missing))
        for path in stage.rglob("*"):
            if path.is_dir() and path.name in {".venv", "__pycache__", "build"}:
                problems.append(f"forbidden directory staged: {path.relative_to(stage)}")
            if path.is_file():
                if path.suffix.lower() in FORBIDDEN_AUDIO:
                    problems.append(f"unsupported audio staged: {path.relative_to(stage)}")
                if path.suffix.lower() in {".pyc", ".pyo"}:
                    problems.append(f"bytecode cache staged: {path.relative_to(stage)}")
        run_web = (ROOT / "RUN_WEB_CLIENT.bat").read_text(encoding="utf-8", errors="replace")
        if "--disable-sound-format-error" not in run_web:
            problems.append("RUN_WEB_CLIENT.bat missing --disable-sound-format-error guard")
        if "prepare_web_stage.py" not in run_web:
            problems.append("RUN_WEB_CLIENT.bat does not use clean staging")
        requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8", errors="replace")
        if "pygbag==0.9.2" not in requirements:
            problems.append("Pygbag is not pinned to the known-working 0.9.2 browser runtime")
        for token in ('"pygbag==0.9.2"', "--version 0.9.2", "--package open-night-v0-7-2", '--title "Open Night v0.7.2"'):
            if token not in run_web:
                problems.append(f"RUN_WEB_CLIENT.bat missing grey-screen/cache guard: {token}")
        staged_client = (stage / "client.py").read_text(encoding="utf-8", errors="replace")
        staged_directory = (stage / "server_directory.py").read_text(encoding="utf-8", errors="replace")
        if "choose_browser_server_uri" not in staged_client:
            problems.append("staged web client does not use automatic public-server selection")
        if "from websockets.asyncio.client import connect" not in staged_directory:
            problems.append("server directory lost desktop protocol probing")
        if staged_directory.index("def probe_public_server") > staged_directory.index("from websockets.asyncio.client import connect"):
            problems.append("desktop websockets import is not lazy and would break Pygbag")
        public_config = stage / "config" / "public_servers.csv"
        if not public_config.is_file() or "wss://open-night-production.up.railway.app" not in public_config.read_text(encoding="utf-8-sig"):
            problems.append("staged web build is missing the configured Railway endpoint")
        if problems:
            print("WEB BUILD AUDIT FAILED")
            for item in problems:
                print(" -", item)
            return 1
        size = sum(p.stat().st_size for p in stage.rglob("*") if p.is_file())
        print("WEB BUILD AUDIT PASSED")
        print(f" staged files: {sum(1 for p in stage.rglob('*') if p.is_file())}")
        print(f" staged bytes: {size}")
        print(" .venv excluded; Pygbag 0.9.2 pinned; unsupported audio excluded; required web files present.")
        return 0
    finally:
        shutil.rmtree(stage, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
