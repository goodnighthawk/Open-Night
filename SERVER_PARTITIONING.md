# v2.4.4 server partitioning contract

Map 001 is 24×8 chunks, with each chunk fixed at 1024×1024 world pixels.

## Logical regions

The map is partitioned into **8×4 chunk regions**:

- Region grid: **3 columns × 2 rows**.
- Total logical regions: **6**.
- Region labels use `R<row>C<column>`.

These are logical ownership boundaries inside the current single Python process. They are intentionally compatible with a later region-worker architecture.

## Interest management

The server indexes dynamic entities by chunk. For a player in chunk `(cx, cy)`, snapshots query only chunks within `interest_radius_chunks=2`, giving at most 25 chunk buckets.

This means snapshot candidate work scales with nearby entity density rather than directly with the 192-chunk world size.

## Future handoff

A future multi-process server can assign one or more logical regions to workers and transfer authoritative player/entity ownership when crossing a region boundary. The chunk IDs and reference-map compiler output do not need to change for that step.
