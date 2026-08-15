# Open Night v0.6.3.1

This client hotfix updates v0.6.3 and remains an update over the complete v0.6.1 polished-map game.

## Fixed

- Fixed the desktop-client crash after joining when a moving cyclist selected a fluid rider frame outside the loaded sprite surface.
- Normal releases now use the character pack bundled in their own extracted folder. An older pack under `Documents\PythonMMO_SharedData` can no longer override the release silently.
- Every final fluid-animation cell crop now derives the available rows and columns from the loaded surface, wraps unexpected indices safely, and falls back to a transparent cell if no complete cell exists.
- Fluid reference-height sampling and action-sheet cell access use the same bounds-safe path.
- `RUN_CLIENT.bat` preserves the full traceback in `client_crash.log`, prints it after a failure, and keeps the window open.

## Preserved

- Desktop and web clients still auto-detect `wss://open-night-production.up.railway.app`.
- The Railway deployment helper still returns correctly from every `railway.cmd` call and remains open on failure.
- All v0.6.1 map, art, traversal, traffic, Map Viewer, portable-map, and launcher behavior is retained.

## Server update

This is a client renderer fix. The already-running Railway v0.6.3 server is protocol-compatible and does not need to be redeployed for this hotfix.
