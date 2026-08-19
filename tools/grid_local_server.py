from __future__ import annotations

"""Compatibility shim for older Quick Test commands.

The v1.0 authoritative server now lives at the repository root in v100_server.py.
Keep this wrapper so existing developer shortcuts continue to work without owning
an independent map/jump contract.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from v100_server import main


if __name__ == "__main__":
    main()
