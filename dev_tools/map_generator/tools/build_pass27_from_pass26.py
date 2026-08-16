from __future__ import annotations

"""Apply Pass 27 to an already-built and audited Pass 26 RC4 output."""

import sys
from pathlib import Path

HERE=Path(__file__).resolve().parent
if str(HERE) not in sys.path:sys.path.insert(0,str(HERE))

import build_pass27_intentional_open_blocks as pass27


def main():
    # The release-candidate workflow builds and audits RC4 first. Avoid rebuilding
    # it a second time; all remaining Pass-27 stages consume that protected output.
    pass27.rc4.main=lambda:None
    pass27.main()


if __name__=="__main__":main()
