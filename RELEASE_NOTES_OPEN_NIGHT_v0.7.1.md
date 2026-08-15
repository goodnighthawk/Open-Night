# Open Night v0.7.1

This is a focused client update over v0.7.0.

## Player feedback

- `/bug description` captures the current game frame without sending the command to chat.
- A structured CSV row includes reporter, description, build, map/chunk/world position, camera, vehicle and nearest-AI context.
- GitHub-reviewable reports live under `feedback/next_version`; the existing persistent shared-data report remains available.
- Reports are local until the player deliberately commits and pushes them.

## Character facing

- Mouse-following head animation and its Settings toggle are removed.
- Head direction is always derived from the same body heading used for the character pose.
- Mouse camera look-ahead, middle-mouse camera rotation and camera-relative walking remain unchanged.

## Compatibility

- Server protocol and the v0.7.0 map are unchanged.
- Existing shared-data issue reports remain readable.
- GitHub clones on `main` can safely fast-forward from GitHub whenever `START_OPEN_NIGHT.bat` runs; local tracked edits are never overwritten.
- The web launcher pins Pygbag 0.9.2 and repairs existing 0.9.3 environments to avoid the upstream grey-screen browser-loader regression.
