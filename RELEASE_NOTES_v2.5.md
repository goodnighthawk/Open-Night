# Python MMO v2.5 release notes

- Integrated selected user-created Arcade Car Physics, CityVoxelPack, white-puff, and character-motion source assets into both game clients and the standalone movement tester.
- Added five new top-down vehicle sprites with class-consistent sizing and deterministic traffic coverage.
- Added camera-matched voxel-building art and eight-frame sprint dust.
- Upgraded the game to the current modular eight-direction dual-camera character pack.
- Fixed fluid character playback reading the wrong CSV frame-count field.
- Added double-tap directional running at server-authoritative 3× speed, a remote `run` pose, and faster run animation cadence.
- Added dedicated eight-direction `run_wide_8` sheets for both cameras. Peak run frames use a 1.48× wider gait, while custom modular outfits receive a compatible lower-body widening fallback.
- Preserved Shift sprint/vehicle boost for compatibility.
- Excluded original Unity/editor content and redundant legacy sprite sets from the release.
