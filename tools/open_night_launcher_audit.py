from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
checks = {
    "launcher": ROOT / "open_night_launcher.py",
    "player_launcher": ROOT / "open_night_player_launcher.py",
    "launcher_art": ROOT / "assets" / "launcher" / "open_night_gritty_neon.png",
    "start": ROOT / "START_OPEN_NIGHT.bat",
    "updater": ROOT / "UPDATE_OPEN_NIGHT.bat",
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
if (ROOT / "RUN_MAP_GENERATOR.bat").exists():
    raise SystemExit("Player-facing RUN_MAP_GENERATOR.bat shortcut still exists")
source = checks["launcher"].read_text(encoding="utf-8")
for token in ("open_night_gritty_neon.png", "NEON_PINK", "NEON_BLUE", "CITY ACCESS TERMINAL"):
    if token not in source:
        raise SystemExit(f"Neon launcher skin integration missing: {token}")
for token in ("QUICK TEST", "START SERVER", "DESKTOP CLIENT", "WEB CLIENT", "MOVEMENT PREVIEW", "MAP VIEWER"):
    if token not in source:
        raise SystemExit(f"Launcher action missing: {token}")
start_source = checks["start"].read_text(encoding="utf-8", errors="replace")
updater_source = checks["updater"].read_text(encoding="utf-8", errors="replace")
player_source = checks["player_launcher"].read_text(encoding="utf-8")
if "MAP GENERATOR" in source or "launch_map_generator" in source or "MAP GENERATOR" in player_source or "launch_map_generator" in player_source:
    raise SystemExit("Map Generator is still exposed through a launcher")
for token in ("self.update_process = self._new_console", "_restart_after_completed_update", "self._python_process(entry)"):
    if token not in source:
        raise SystemExit(f"Launcher does not refresh after an update: {token}")
if "UPDATE TO LATEST VERSION" not in player_source or "self.launch_update" not in player_source:
    raise SystemExit("Player launcher does not expose its prominent safe update control")
if "call UPDATE_OPEN_NIGHT.bat" in start_source:
    raise SystemExit("Player entry point still performs a hidden update before opening the launcher")
for token in ("git.exe", "GIT_TERMINAL_PROMPT=0", "UPDATE_TIMEOUT_SECONDS=30", "WaitForExit", "+main:refs/remotes/origin/main", "merge-base --is-ancestor", "merge --ff-only", "OPEN_NIGHT_SKIP_UPDATE"):
    if token not in updater_source:
        raise SystemExit(f"Safe GitHub updater contract missing: {token}")
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
for token in ("run_held = bool(", "self.sprint_active = run_held and moving", "Hold Shift + W/A/S/D = 3× run"):
    if token not in tester:
        raise SystemExit(f"Movement preview Shift-to-run integration missing: {token}")
for obsolete in ("register_direction_tap", "last_direction_tap", "Double-tap W/A/S/D"):
    if obsolete in tester:
        raise SystemExit(f"Movement preview still contains obsolete double-tap running: {obsolete}")
viewer = checks["map_viewer"].read_text(encoding="utf-8")
for token in ("DEFAULT_MAP_ID", "default_map_path", "Map_001_GWB.map", "--choose"):
    if token not in viewer:
        raise SystemExit(f"Map Viewer default-map integration missing: {token}")
print("OPEN NIGHT launcher audit: PASS")
print("6 developer actions + 3 player actions + 1 prominent update action; Map Generator has no public launcher entry point.")
