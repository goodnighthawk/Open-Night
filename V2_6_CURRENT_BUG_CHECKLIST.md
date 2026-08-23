# Open Night v2.6 release checklist

v2.6 carries the complete verified v2.5 player-report backlog through GitHub issue #184 and packages the remaining legitimate character-art source assets. Source images are evidence and provenance assets; the cleaned transparent sheet remains the runtime authority.

## Character-art archive

- [x] Archive the original `master_8x10.png` source sheet.
- [x] Archive the revised `master_8x10_v2.png` source sheet.
- [x] Keep `master_8x10_v2_clean.png` as the only runtime-loaded master sheet.
- [x] Verify both source sheets retain their 1254×1254 source dimensions and the cleaned runtime master remains a transparent 1280×1280 sheet.
- [x] Verify source and runtime files have distinct content hashes.

## Carried gameplay and map authority

- [x] Carry every implemented and verified player report through issue #184.
- [x] Preserve the George Washington Bridge, 30 enterable buildings, and matching 30-player public capacity.
- [x] Keep ambient pedestrians and dogs off rooftops; permit only buyer and supplier job NPC roles there.
- [x] Reject malformed generated map drift that substitutes zebra-crossing art for lane-divider art.

## Release gate

- [x] Advance launcher, client, server, public-discovery, and Railway patch authority to version 2.6.
- [x] Pass the focused v2.6 asset/map release audit and every carried release suite locally.
- [ ] Commit directly to `main`, push without merging or force-pushing, and verify GitHub Actions plus Railway production.
