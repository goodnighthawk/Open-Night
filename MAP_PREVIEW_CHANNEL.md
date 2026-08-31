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

## Standalone GWB workbench release

Each push to GitHub's `map-preview` branch runs the **GWB Map Workbench Preview**
workflow. Its `open-night-gwb-map-previewer` artifact is a portable review
bundle: download and extract it, then double-click `MAP_WORKBENCH.bat`. Use `G`
for Ground, `R` for Roof, and `F` to fit the complete map. The artifact also
contains the full Ground/Roof PNGs and does not change the stable game version.

## Map-generation workflow

- Publish incomplete but runnable map passes to `map-preview`.
- Keep stable `main` unchanged until a map pass is accepted and fully audited.
- Each pass should update its commit subject with the pass number and the main
  visual change.
- Run semantic validation and the fast map/art audits before pushing.
- Merge the accepted semantic CSVs, cosmetic bindings, generated assets, and
  generator changes to `main` together.
