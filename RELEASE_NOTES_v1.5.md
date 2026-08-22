# Open Night v1.5

Vehicle-art and safe-spawn bug-fix release.

- Replacement traffic sprites now render at their authored world size instead of receiving an extra 1.65x client scale.
- Vehicle rendering remains centered on trimmed transparent sprite bounds, eliminating the reported oversized/clipped presentation.
- Login selection rejects road cells and chooses a valid sidewalk or pavement surface.
- The recently added player pixel-car sheets remain active alongside the 28-vehicle generated fleet.
- Existing synchronized traffic-signal state remains server authoritative at junctions.

Wire protocol and public release version: `1.5`.
