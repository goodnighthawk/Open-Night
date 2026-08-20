from __future__ import annotations

"""Client-side v1.1 compatibility gate for discovered multiplayer servers."""

from versioning import GAME_VERSION


def server_is_compatible(server: dict) -> bool:
    return str(server.get("version", "unknown")) == GAME_VERSION


def install(game_client) -> None:
    launcher = game_client.Launcher
    discovery = game_client.DiscoveryService
    if bool(getattr(launcher, "_v110_version_gate_installed", False)):
        return

    original_connect_selected = launcher._connect_selected
    original_snapshot = discovery.snapshot

    def snapshot_v110(self) -> list[dict]:
        servers = original_snapshot(self)
        annotated: list[dict] = []
        for source in servers:
            server = dict(source)
            compatible = server_is_compatible(server)
            server["compatible"] = compatible
            if not compatible:
                name = str(server.get("name", "Open Night Server"))
                if "[INCOMPATIBLE]" not in name:
                    server["name"] = f"{name}  [INCOMPATIBLE]"
            annotated.append(server)
        return annotated

    def connect_selected_v110(self, servers: list[dict]):
        selected = next((s for s in servers if s.get("uri") == self.selected_uri), None)
        if selected is not None and not server_is_compatible(selected):
            server_version = str(selected.get("version", "unknown"))
            self.message = (
                f"Version mismatch: client v{GAME_VERSION} cannot join server "
                f"v{server_version}. Update or redeploy that server."
            )
            return None
        return original_connect_selected(self, servers)

    discovery.snapshot = snapshot_v110
    launcher._connect_selected = connect_selected_v110
    launcher._v110_version_gate_installed = True
