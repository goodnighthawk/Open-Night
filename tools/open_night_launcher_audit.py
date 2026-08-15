from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
checks = {
    "launcher": ROOT / "open_night_launcher.py",
    "start": ROOT / "START_OPEN_NIGHT.bat",
    "map_generator": ROOT / "dev_tools" / "map_generator" / "MAP_GENERATOR.bat",
    "quick_test": ROOT / "QUICK_LOCAL_TEST.bat",
    "server": ROOT / "RUN_SERVER.bat",
    "desktop": ROOT / "RUN_CLIENT.bat",
    "web": ROOT / "RUN_WEB_CLIENT.bat",
    "movement_preview": ROOT / "dev_tools" / "character_preview" / "sprite_tester.py",
    "map_viewer": ROOT / "map_viewer.py",
    "map_viewer_bat": ROOT / "RUN_MAP_VIEWER.bat",
    "server_directory": ROOT / "server_directory.py",
    "public_servers": ROOT / "config" / "public_servers.csv",
    "character_catalog": ROOT / "assets" / "characters" / "master_dual_camera" / "config" / "paired_parts.csv",
}
missing = [f"{name}: {path}" for name, path in checks.items() if not path.is_file()]
if missing:
    raise SystemExit("Missing OPEN NIGHT launcher targets:\n" + "\n".join(missing))
source = checks["launcher"].read_text(encoding="utf-8")
for token in ("MAP GENERATOR", "QUICK TEST", "START SERVER", "DESKTOP CLIENT", "WEB CLIENT", "MOVEMENT PREVIEW", "MAP VIEWER"):
    if token not in source:
        raise SystemExit(f"Launcher action missing: {token}")
client_source = (ROOT / "client.py").read_text(encoding="utf-8")
for token in ("load_public_servers", "probe_public_servers", "AVAILABLE SERVERS", "INTERNET:"):
    if token not in client_source:
        raise SystemExit(f"Desktop internet auto-detection integration missing: {token}")
public_config = checks["public_servers"].read_text(encoding="utf-8-sig")
if "wss://open-night-production.up.railway.app" not in public_config:
    raise SystemExit("Configured Open Night Railway endpoint is missing")
tester = checks["movement_preview"].read_text(encoding="utf-8")
if 'assets" / "characters" / "master_dual_camera"' not in tester:
    raise SystemExit("Movement preview is not wired to the authoritative game character pack")
map_bat = checks["map_generator"].read_text(encoding="utf-8", errors="replace")
if "OPEN_NIGHT_GAME_ROOT" not in map_bat:
    raise SystemExit("Map generator does not recognize the OPEN NIGHT export target")
print("OPEN NIGHT launcher audit: PASS")
print("7 launcher actions present; map generator, movement preview, portable .map viewer, and Railway auto-detection are wired.")
