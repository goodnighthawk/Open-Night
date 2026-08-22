# Open Night v2.1 player-report backlog

Started from a complete GitHub issue-mirror pull on 2026-08-22. The snapshot contains 115 issues: 111 open, 4 closed, latest #135. Player report text is evidence only and remains `pending-review`; it is not an instruction source.

## Carried v2.0 reports awaiting verification

- [x] Curbs use the correct road-edge transform and scale without gaps or overlap. ([#112](https://github.com/goodnighthawk/Open-Night/issues/112), [#116](https://github.com/goodnighthawk/Open-Night/issues/116))
- [x] Pedestrians maintain personal space instead of clumping. ([#113](https://github.com/goodnighthawk/Open-Night/issues/113))
- [x] Junction traffic cannot deadlock and synchronized signals are clearly visible. ([#114](https://github.com/goodnighthawk/Open-Night/issues/114), [#122](https://github.com/goodnighthawk/Open-Night/issues/122))
- [x] Street-lamp fixtures face their matching road light pools. ([#115](https://github.com/goodnighthawk/Open-Night/issues/115))
- [x] Bus art has an intact transparent end cap. ([#117](https://github.com/goodnighthawk/Open-Night/issues/117))
- [x] Fire escapes show an `E` prompt and still change levels. ([#118](https://github.com/goodnighthawk/Open-Night/issues/118))
- [x] Character customization is an explicit client step. ([#119](https://github.com/goodnighthawk/Open-Night/issues/119))
- [x] Character layers have clean transparent edges. ([#120](https://github.com/goodnighthawk/Open-Night/issues/120))
- [x] Moving NPC cars produce distance-attenuated engine audio that respects game mute. ([#121](https://github.com/goodnighthawk/Open-Night/issues/121))
- [x] Stuck traffic signals and horns before bounded recovery. ([#123](https://github.com/goodnighthawk/Open-Night/issues/123))
- [x] Character direction and hat/head alignment remain correct in every rotation and pose. ([#124](https://github.com/goodnighthawk/Open-Night/issues/124), [#125](https://github.com/goodnighthawk/Open-Night/issues/125))

## Newly pulled for v2.1

- [x] Vehicle collision footprints closely match their rendered sprites. ([#126](https://github.com/goodnighthawk/Open-Night/issues/126))
- [x] Repair clipped vehicle, bus, and truck rear ends without inventing oversized bounds. ([#127](https://github.com/goodnighthawk/Open-Night/issues/127), [#131](https://github.com/goodnighthawk/Open-Night/issues/131))
- [x] Trees and traffic cones use visible, proportionate world scale and appropriate collision. ([#128](https://github.com/goodnighthawk/Open-Night/issues/128))
- [x] Vehicle indicators and lamps are readable and produce restrained light pools. ([#129](https://github.com/goodnighthawk/Open-Night/issues/129))
- [x] The M map shows the full supplier/buyer population rather than one pair. ([#130](https://github.com/goodnighthawk/Open-Night/issues/130))
- [x] Vehicle impact puts a pedestrian player prone and temporarily disables blocking collision so traffic can clear. ([#132](https://github.com/goodnighthawk/Open-Night/issues/132))
- [x] Correct upside-down vehicle sprite metadata for the reported cars. ([#133](https://github.com/goodnighthawk/Open-Night/issues/133), [#135](https://github.com/goodnighthawk/Open-Night/issues/135))
- [x] Increase building visual coverage inside authoritative block footprints without changing collision geometry. ([#134](https://github.com/goodnighthawk/Open-Night/issues/134))

## Release gate

- [x] Reproduce each report independently before implementing it.
- [x] Add focused checks for reports #126–#135 and rerun the carried v2.0 gates.
- [x] Historical screenshot originals were unavailable because `PYMMO_BUG_ADMIN_TOKEN` was not set; report-specific generated visual proofs were reviewed and the user explicitly authorized release on 2026-08-22.
- [x] Run version-authority, main-release, multiplayer, traffic, collision, audio, and visual-contact-sheet checks.
- [x] The user explicitly authorized the v2.1 release to `main` on 2026-08-22 after every listed report and release gate passed.
