# Map 001 chunk grid — v2.4.4

The world uses fixed **1024×1024 world-pixel chunks**.

- Map 001: **24 × 8 = 192 chunks**.
- Human chunk IDs run from **A1** at the northwest corner to **X8** at the southeast corner.
- The v2.3 authored map was 16 × 6 = 96 chunks; v2.4.4 therefore has exactly **2× the area**.
- The preserved authored core occupies **E2 through T7**.

## Logical server regions

Chunks are grouped into **8×4-chunk logical regions**:

- 3 regions east-west.
- 2 regions north-south.
- **6 logical regions total**.

The current Python server still owns all six regions in one process. The region IDs are preparation for later multi-process ownership and handoff.

## Interest window

The default network interest radius is 2 chunks around the player's current chunk. A player therefore reads at most **25 nearby chunk buckets**, independent of the total map size.
