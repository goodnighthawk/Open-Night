from __future__ import annotations

"""Railway entry point for the Open Night v1.1 GridWorld-authoritative server."""

from bug_github_mirror import install_database_bug_mirror
from v100_server import main as run_v100_server


if __name__ == "__main__":
    install_database_bug_mirror()
    run_v100_server()
