from __future__ import annotations

"""Railway entry point for Open Night.

Installs optional production integrations, then executes server.py as __main__ so
its existing CLI and startup behavior stay unchanged.
"""

import runpy

from bug_github_mirror import install_database_bug_mirror


if __name__ == "__main__":
    install_database_bug_mirror()
    runpy.run_module("server", run_name="__main__")
