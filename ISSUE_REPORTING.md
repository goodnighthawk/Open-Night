# In-game issue reporting

## F10 report workflow
1. Stand at or look at the buggy area.
2. Press **F10**. The current gameplay frame is captured immediately before the report overlay appears.
3. Choose a category: `1 Art`, `2 AI`, `3 Collision/Nav`, `4 Other`.
4. Optionally type a short note.
5. Press **Enter** to save, or `F10`/`Esc` to cancel.

## What is saved
Reports persist under `Documents\PythonMMO_SharedData\issue_reports` (or `PYMMO_SHARED_DATA`). Each row records build version, map, A1 chunk label, numeric chunk coordinate, exact world coordinate, local 0–1023 chunk coordinate, camera rotation/zoom, vehicle state, nearest NPC/traffic/bicycle context, note, and screenshot path.

The screenshot is the unobstructed gameplay frame from the instant F10 was pressed.

## Next-version triage
Run `BUILD_ISSUE_FIXLIST.bat`. It groups all open reports by chunk/category and writes `next_version_fixlist.csv`, ordered by report count. Reports are intentionally stored outside the version folder so replacing the current game folder with later builds does not lose them.
