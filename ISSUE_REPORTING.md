# In-game issue reporting

## Chat `/bug` workflow

1. Press **Enter** while playing.
2. Type `/bug` followed by a useful description, for example `/bug bicycle spawned in the river beside the west bridge`.
3. Press **Enter** again. The command is not sent to other players.

The desktop game captures the current frame and appends a structured row to:

`feedback\next_version\next_version_feedback.csv`

Screenshots are stored in `feedback\next_version\screenshots\`. When playing from the cloned GitHub folder these appear as ordinary GitHub Desktop changes. Review them, then commit and push only the reports you want shared for the next version. Reports are never uploaded automatically.

## F10 report workflow
1. Stand at or look at the buggy area.
2. Press **F10**. The current gameplay frame is captured immediately before the report overlay appears.
3. Choose a category: `1 Art`, `2 AI`, `3 Collision/Nav`, `4 Other`.
4. Optionally type a short note.
5. Press **Enter** to save, or `F10`/`Esc` to cancel.

## What is saved
Reports persist under `Documents\PythonMMO_SharedData\issue_reports` (or `PYMMO_SHARED_DATA`). A reviewable mirror is also written to `feedback\next_version` for GitHub-based iteration. Each row records source, reporter, description, build version, map, A1 chunk label, numeric chunk coordinate, exact world coordinate, local 0–1023 chunk coordinate, camera rotation/zoom, vehicle state, nearest NPC/traffic/bicycle context, status, target version, duplicate linkage, and screenshot path.

The F10 screenshot is the unobstructed gameplay frame from the instant F10 was pressed. `/bug` captures the frame present when the chat command is submitted.

## Next-version triage
Run `BUILD_ISSUE_FIXLIST.bat`. It groups all open reports by chunk/category and writes `next_version_fixlist.csv`, ordered by report count. Reports are intentionally stored outside the version folder so replacing the current game folder with later builds does not lose them.
