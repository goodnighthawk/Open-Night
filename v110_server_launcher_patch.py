from __future__ import annotations

"""v1.1 compatibility patch for the mature graphical server launcher.

The server-control UI is intentionally retained, but its saved configuration can
outlive a game build and its original process launcher pointed at ``server.py``.
For v1.1, migrate only recognized historical Open Night default names and route
the child process through the canonical GridWorld ``v100_server.py`` entrypoint.
User-authored custom server names remain untouched.
"""

from pathlib import Path
import re

from versioning import version_label


_LEGACY_OFFICIAL_NAME = re.compile(
    r"^Open Night v\d+(?:\.\d+){1,2}(?:\s*/\s*(?:Pass\s+\d+|consolidation))?$",
    re.IGNORECASE,
)


def is_legacy_official_server_name(value: object) -> bool:
    return bool(_LEGACY_OFFICIAL_NAME.fullmatch(str(value or "").strip()))


def canonicalize_saved_config(config: dict) -> dict:
    """Upgrade old official defaults without overwriting custom server names."""
    result = dict(config)
    if is_legacy_official_server_name(result.get("server_name")):
        result["server_name"] = version_label()
    return result


class _CanonicalSubprocessProxy:
    """Forward subprocess calls while rewriting only the game-server child."""

    def __init__(self, real_module, app_dir: Path):
        self._real = real_module
        self._app_dir = Path(app_dir)

    def __getattr__(self, name):
        return getattr(self._real, name)

    def Popen(self, args, *popen_args, **popen_kwargs):
        rewritten = args
        if isinstance(args, (list, tuple)) and len(args) >= 3:
            candidate = Path(str(args[2]))
            try:
                same_parent = candidate.parent.resolve() == self._app_dir.resolve()
            except OSError:
                same_parent = candidate.parent == self._app_dir
            if candidate.name.lower() == "server.py" and same_parent:
                rewritten = list(args)
                rewritten[2] = str(self._app_dir / "v100_server.py")
        return self._real.Popen(rewritten, *popen_args, **popen_kwargs)


def install() -> None:
    import server_launcher

    if bool(getattr(server_launcher, "_v110_launcher_patch_installed", False)):
        return

    original_load = server_launcher._load_config

    def load_config_v110() -> dict:
        return canonicalize_saved_config(original_load())

    server_launcher._load_config = load_config_v110
    server_launcher.subprocess = _CanonicalSubprocessProxy(
        server_launcher.subprocess, server_launcher.APP_DIR
    )
    server_launcher._v110_launcher_patch_installed = True
