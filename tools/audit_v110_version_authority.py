#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from versioning import GAME_VERSION, version_label
from v110_server_launcher_patch import canonicalize_saved_config


EXPECTED = "1.1"


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8-sig")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def main() -> None:
    require(GAME_VERSION == EXPECTED, f"wire version is {GAME_VERSION!r}, expected {EXPECTED!r}")
    require(version_label() == "Open Night v1.1", version_label())
    require(read("VERSION.txt").startswith("Open Night v1.1"), "VERSION.txt is not v1.1")

    canonical_server = read("v100_server.py")
    require("server.SERVER_NAME = version_label()" in canonical_server,
            "canonical server does not own its discovery identity")
    require("v110_server_launcher_patch.install()" in canonical_server,
            "canonical no-argument server path does not patch the retained launcher")

    launcher_patch = read("v110_server_launcher_patch.py")
    require('"v100_server.py"' in launcher_patch,
            "server launcher patch does not route children through v100_server.py")
    for legacy in (
        "Open Night v0.8 / Pass 19",
        "Open Night v0.8.3",
        "Open Night v0.9.0 / consolidation",
    ):
        migrated = canonicalize_saved_config({"server_name": legacy})
        require(migrated["server_name"] == version_label(),
                f"legacy server name did not migrate: {legacy!r}")
    custom = canonicalize_saved_config({"server_name": "Adam's Test Server"})
    require(custom["server_name"] == "Adam's Test Server", "custom server name was overwritten")

    client_entry = read("v100_client.py")
    require("v110_version_client.install(game_client)" in client_entry,
            "canonical client did not install the v1.1 version gate")
    client_gate = read("v110_version_client.py")
    require("server_version != GAME_VERSION" in client_gate,
            "client version gate does not enforce exact parity")

    railway = read("railway.toml")
    require("PYMMO_PATCH_ID=open-night-v1.1" in railway,
            "Railway patch id is not v1.1")
    require("PYMMO_RESET_DB_ON_PATCH=false" in railway,
            "v1.1 Railway promotion would reset prototype persistence")
    railway_entry = read("railway_entry.py")
    require("from v100_server import main as run_v100_server" in railway_entry,
            "Railway bypasses the canonical GridWorld server")

    server_config = read("server_config.csv")
    require("server_name,Open Night v1.1" in server_config,
            "repo-local server default is not v1.1")
    require("OPEN NIGHT v1.1" in read("RUN_CLIENT.bat"),
            "desktop client launcher label is stale")
    require("GAME_VERSION" in read("tools/quick_local_test.py"),
            "quick local test does not derive its version from the wire authority")

    audit = {
        "wire_version": GAME_VERSION,
        "version_label": version_label(),
        "canonical_server_entry": "v100_server.py",
        "canonical_client_entry": "v100_client.py",
        "server_launcher_child_entry": "v100_server.py",
        "railway_entry": "railway_entry.py -> v100_server.py",
        "railway_patch_id": "open-night-v1.1",
        "railway_preserves_persistence": True,
        "discovered_server_exact_version_gate": True,
        "legacy_saved_server_name_migration": True,
        "custom_server_names_preserved": True,
    }
    print(json.dumps(audit, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
