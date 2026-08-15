# Open Night Map Preview Channel

`OPEN_NIGHT_MAP_PREVIEW.bat` creates and launches an isolated work-in-progress
map installation. The normal `Open-Night` folder remains on stable `main`; the
sibling `Open-Night-Map-Preview` worktree follows GitHub's `map-preview` branch.

## Player workflow

1. Put `OPEN_NIGHT_MAP_PREVIEW.bat` in the stable GitHub-cloned `Open-Night`
   folder.
2. Run it once. It creates `map-preview` from `origin/main` if necessary and
   prepares the sibling preview installation.
3. Run the same BAT for every later test. It safely fast-forwards the preview
   worktree before launching.
4. Type `/mapfeedback description` in chat to capture the current frame and
   structured position/camera context.

Preview saves and feedback live under `%LOCALAPPDATA%\OpenNightMapPreview`, not
inside either Git worktree, so reports and screenshots cannot block updates.

## Map-generation workflow

- Publish incomplete but runnable map passes to `map-preview`.
- Keep stable `main` unchanged until a map pass is accepted and fully audited.
- Each pass should update its commit subject with the pass number and the main
  visual change.
- Run semantic validation and the fast map/art audits before pushing.
- Merge the accepted semantic CSVs, cosmetic bindings, generated assets, and
  generator changes to `main` together.
