# Dual-Camera Character Sprite Tester

This is a separate Pygame sandbox for the authoritative `dual_camera_character_customization_set`. It loads the pack through `config/paired_parts.csv`, so it can test future compatible revisions without changing the tester.

## Run on Windows

1. Extract this ZIP.
2. Double-click `START_SPRITE_TESTER.bat`.
3. The first run creates a small `.venv` and installs Pygame.

The current sprite pack is bundled under `sprite_packs/`. Use **Open sprite ZIP** or **Open extracted folder** inside the program to test a newer pack.

## Controls

| Control | Result |
| --- | --- |
| WASD | Camera-relative eight-direction walking; combine keys for diagonals |
| Double-tap W, A, S or D | Run at 3.0× while the twice-tapped direction remains held; other held directions may form diagonals |
| Hold Shift + WASD | Slow walk |
| Space | Forward-propelled jump with twice the previous range; stands up if prone |
| Space twice | Double jump with twice the previous range; lands prone |
| Hold C | Crouch; movement input stands after a one-second delay |
| X | Toggle prone or stand; movement input stands after a one-second delay |
| T | Turn/pivot animation |
| F | Punch action-sheet test |
| G | Cycle gun-holding master poses |
| Tab | Switch top-down/isometric sprite mode |
| Hold middle mouse + drag | Continuous game-style camera rotation around the player |
| Q / E | Rotate the camera by 15° for keyboard accessibility |
| Mouse wheel | Zoom the complete world view from 0.55× to 2.0× |
| 1–0 | Load one of the ten tested presets |
| + / − | Keyboard camera zoom |
| Mouse | Local head-look indicator |
| F12 | Save a screenshot |
| Esc | Exit |

Use the arrow buttons beside each customization slot to cycle compatible body, hair/head, top, bottom, footwear and accessory choices. Invalid combinations are skipped automatically.

Complete tested presets use their fluid eight-frame walk sheets. The 3× state switches to separate eight-frame wide-gait run sheets, with substantially greater leg separation in the peak stride frames while the normal walk remains unchanged. New mixed outfits use the modular registered rows plus a lower-body wide-gait fallback, letting you test both production paths.

When the character is left standing, subtle breathing begins automatically after 0.35 seconds. After six seconds, a natural waiting gesture briefly shifts the upper-body weight before returning to breathing; it repeats at deterministic intervals. Any movement, action, crouch or prone input resets the idle timer. The five fluid profiles use authored six-frame breathing and twelve-frame waiting sheets in both camera modes, while every custom modular combination has a registered fallback.

Every movement and action path supports the clockwise eight-facing contract: north, northeast, east, southeast, south, southwest, west and northwest. Cardinal frames remain unchanged; diagonal frames occupy the intervening columns or rows.

The arena also demonstrates strict top-down occlusion: characters and scenery are sorted by their ground-contact Y position, so the character can walk behind foreground props rather than always drawing on top.

The movement arena now loads the converted user-created Unity assets under `assets/open_source_import/`: a five-vehicle top-down family, top-down/isometric voxel-building adaptations, and an eight-frame sprint-dust effect. The parked car and building participate in the same rotated depth sort as the character, and the dust atlas is shown only during the 3× running state. `catalog.csv` records each source-to-runtime mapping.

Camera behavior matches the game client: the local player stays exactly screen-centered, WASD remains screen-relative at every camera angle, mouse aim is independently transformed into world space, active camera dragging front-locks the player sprite, rotated screen depth controls occlusion, and the minimap remains north-up. Mouse-wheel zoom uses the game's 1.0× default, 0.55×–2.0× range and 0.10 step while keeping the customization panel unscaled.

After a double-jump landing, press either `Space` or `X` to stand immediately. Holding a movement direction while crouched or prone starts a one-second stand-up transition; movement resumes only after it completes. Hold Shift while moving for slow walk. Double-tap the same direction within 0.30 seconds and keep the second press held to run at 3.0× speed with the dedicated wider gait; releasing that direction, pressing Shift, crouching, going prone, jumping or starting an action cancels running.

Punching and gun holding currently display the pack's dedicated action masters; the panel clearly identifies those frames as action masters rather than pretending they are modular outfit combinations.

## Load a pack manually

```bat
.venv\Scripts\python.exe sprite_tester.py C:\path\to\dual_camera_character_customization_set.zip
```

An extracted directory containing `config\paired_parts.csv` also works.

## Lightweight validation

Double-click `LOCAL_QA.bat`. It checks the Python source, bundled ZIP, CSV references, paired 1024×2048 RGBA sheets, presets, actions and fluid-animation paths. If Pygame is already installed, it also renders a headless smoke-test screenshot.
