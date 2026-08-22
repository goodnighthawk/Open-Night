# Windows packaged release

This branch packages the player-facing Open Night desktop client as a branded,
console-free Windows executable with Nuitka. The one-file bootstrap displays
`assets/branding/snakepit_splash.png` while it extracts and imports the client,
then the client removes the splash immediately before opening its own window.

## Build

Install Python 3.13 and Inno Setup 6, then run from the repository root:

```powershell
.\BUILD_WINDOWS_RELEASE.bat
```

The build script creates an ignored virtual environment beneath `build/`,
installs the pinned game and packaging dependencies, generates the Windows icon,
compiles the client, and produces:

- `dist/windows/OpenNight.exe` — portable one-file client
- `dist/windows/OpenNight-Setup-<version>.exe` — per-user installer
- `dist/windows/SHA256SUMS.txt` — hashes for verifying shared downloads

Use `packaging/windows/build_release.ps1 -Clean` to discard prior generated
packaging output before rebuilding. `-SkipInstaller` produces only the portable
client, `-SkipDependencyInstall` reuses the existing build environment, and
`-SkipSmokeTest` skips the packaged-runtime validation.

## Synchronizing with new game releases

The packaging branch must contain the exact `origin/main` commit being released.
After each main-game release, double-click:

```text
SYNC_AND_BUILD_WINDOWS_RELEASE.bat
```

The synchronization script refuses to touch a dirty worktree, fetches and merges
the latest `origin/main`, verifies that main is an ancestor of the packaging
branch, recompiles and smoke-tests the executable and installer using the updated
`VERSION.txt`, and pushes the packaging branch only after the build succeeds.
Use `-NoPush` when validating locally without updating GitHub.

Every push to `release/nuitka-windows-installer` also runs the Windows Packaged
Client workflow. The workflow independently rejects a branch that is behind
`origin/main`, rebuilds on a Windows runner, smoke-tests the embedded maps/art,
and uploads a versioned 30-day GitHub Actions artifact.

## Packaged-client smoke test

The Windows entry point includes a noninteractive package check used by release
automation. Set `OPEN_NIGHT_PACKAGE_SMOKE_TEST=1` and
`OPEN_NIGHT_SMOKE_REPORT=<path>` before launching `OpenNight.exe`. The process
checks the embedded maps, runtime artwork, public-server configuration, Pygame,
and the bundled FFmpeg radio decoder without opening the game window.

## Signing

The generated files are unsigned development artifacts. Before a public release,
sign both executables with the studio's Authenticode certificate and rebuild the
checksum file. Code signing is intentionally not automated because private keys
must not be stored in this repository.
