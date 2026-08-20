from __future__ import annotations

"""Client-side v1.1 version gate for discovered multiplayer servers."""

from versioning import GAME_VERSION


def install(game_client) -> None:
    launcher = game_client.Launcher
    if bool(getattr(launcher, "_v110_version_gate_installed", False)):
        return

    original_connect_selected = launcher._connect_selected

    def connect_selected_v110(self, servers: list[dict]):
        selected = next((s for s in servers if s.get("uri") == self.selected_uri), None)
        if selected is not None:
            server_version = str(selected.get("version", "unknown"))
            if server_version != GAME_VERSION:
                self.message = (
                    f"Version mismatch: client v{GAME_VERSION} cannot join server "
                    f"v{server_version}. Update or redeploy that server."
                )
                return None
        return original_connect_selected(self, servers)

    launcher._connect_selected = connect_selected_v110
    launcher._v110_version_gate_installed = True
