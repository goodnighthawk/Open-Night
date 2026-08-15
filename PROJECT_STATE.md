# Open Night — Working State

Read this file before starting a new development session. Update it whenever a
pass is checkpointed so GitHub, rather than chat history, remains the source of
truth.

## Current checkpoint

- Release under development: **Open Night v0.8.0**
- Working branch: `agent/v0.8.0-pass18-default`
- Integration base: latest accepted `main` map checkpoint
- Playable map: `map_001_gwb_corridor` only
- Map corridor: Fort Lee / GWB approaches / George Washington Bridge /
  Washington Heights
- Server: Railway WebSocket service, automatically selected by supported clients
- Persistence: Railway MySQL, reset once whenever `PYMMO_PATCH_ID` changes

## Approved direction

- Strictly top-down, readable GTA 2-like play space.
- Reference-driven Fort Lee/GWB/Washington Heights composition without literal
  street-level realism overwhelming gameplay.
- Roads, sidewalks, crossings, buildings, water, vegetation, props, and lighting
  must read as one composition.
- Roads remain clearly drivable; sidewalks must not be clipped by roads.
- Buildings use the approved top-down/2.5D facade and roof families.
- Streetlights belong on sidewalks; no decorative yellow road lines.
- Semantic gameplay geometry remains CSV-based and deterministic.

## Latest completed work (uncommitted at workflow creation)

- Revised latest map composition and installed semantic CSVs.
- Added sidewalk-only streetlamps and bridge lamps; art-rule audit reports zero
  errors.
- Added Railway MySQL environment-variable support.
- Added patch-ID persistence reset policy for v0.7.2.
- Railway deployment batch, database reset mock, and server CLI smoke checks pass.
- Made outdoor level connectors direction-aware: continuing forward or standing
  cannot bounce levels, while reversing direction can immediately traverse back
  toward the lower endpoint without a time-based lockout.
- Made Map Viewer open the authoritative default playable map unless `--choose`
  is explicitly requested.
- Changed Movement Preview running to hold Shift plus WASD; removed its
  double-tap run activation and Shift slow-walk behavior.
- Integrated that movement contract into multiplayer: the server now owns
  Shift-running, forward single/double jumps, double-jump prone landings,
  crouch/prone stand transitions, and broadcasts every pose to nearby players.
- Made double jump visibly larger than single jump in both the movement preview
  and multiplayer rendering.
- Added the v0.7.3 Railway-backed player-report queue. Reports remain pending
  until a token-authenticated human reviews the text/screenshot and explicitly
  approves or rejects the exact report ID.
- Limited screenshots, salted reporter identifiers, rate-limited submissions,
  and made `feedback/approved/` the only agent-actionable player-feedback path.

## Current next pass

1. Inspect the latest Fort Lee night preview against the approved art target.
2. Correct the largest remaining composition/style mismatch only.
3. Run `TEST_FAST.bat`.
4. Render the Fort Lee preview with `BUILD_PREVIEW.bat`.
5. Update this file and `feedback/next_version/tasks.csv`.
6. Run `CHECKPOINT_PROGRESS.bat` to commit and push the pass.

## Commands

- Play locally: `QUICK_LOCAL_TEST.bat`
- Small visual iteration: `BUILD_PREVIEW.bat`
- Fast noninteractive checks: `TEST_FAST.bat`
- Full verification and render: `BUILD_RELEASE.bat`
- Save a GitHub checkpoint: `CHECKPOINT_PROGRESS.bat`
- Launch/update the isolated WIP map channel: `OPEN_NIGHT_MAP_PREVIEW.bat`
- Open the authoritative default playable map: `RUN_MAP_VIEWER.bat` (pass
  `--choose` only when intentionally browsing another portable map)
- Deploy server: `DEPLOY_OPEN_NIGHT_SERVER.bat`
- Review pending bug reports: `REVIEW_BUG_REPORTS.bat`

## Session rules that reduce work usage

- One subsystem or one visual problem per pass.
- Use the Fort Lee crop until the pass is visually accepted.
- Do not run the full release build after every small edit.
- Do not duplicate extracted releases or generated backups in Git.
- End every successful pass with a pushed checkpoint.
- Start new chats by asking the agent to read this file and take the next queued
  task.
- Incomplete playable map passes go to `map-preview`; accepted releases go to
  `main`.
