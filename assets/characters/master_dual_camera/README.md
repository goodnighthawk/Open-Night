# Dual-camera character customization sprite set

This pack provides one shared customization vocabulary for both camera modes:

- isometric three-quarter sprites;
- strict orthographic 90° top-down sprites.

Every selectable `part_id` has an isometric and top-down sheet with the same 256 × 256 cell contract, eight directions and eight animation rows. The clockwise direction order is north, northeast, east, southeast, south, southwest, west and northwest. The customizer can therefore change camera modes without changing the character's selected outfit.

Included: 39 paired selectable parts, 10 example presets, approximately 20,736 raw paired combinations before compatibility filters, CSV catalogs/rules, Pygame and browser runtime loaders, fluid animation sheets, automatic breathing/waiting sheets, action sheets, directional weapon overlays, and current preview sheets. The authoritative eight-facing artwork uses `_8dir.png` filenames; the four-facing source masters remain available only as migration inputs and are not referenced by runtime catalogs.

Use `config/paired_parts.csv` as the authoritative UI catalog. Use `config/compatibility_rules.csv` before accepting a combination. Draw order is body, top, bottom, footwear, head, accessory.

Top-down directions are fixed ground-plane rotations of strict overhead masters; do not substitute the isometric layers or rotate the camera projection.
Upright top-down poses follow the bundled reference-guy projection contract: top/back of head and shoulders dominate, idle legs are mostly occluded, and walking exposes one centered directional lead leg while the trailing leg remains beneath the torso. Prone is the intentional exception because the body lies in the ground plane.

Strict top-down scenes use painter-style occlusion. Sort actors, vehicles and props by their feet/ground-contact Y anchor; an item with larger ground Y draws later and can pass in front of an item above it. Do not force characters into a permanent foreground layer. See `config/depth_sorting.csv` and the runtime helpers.

Camera controls match the game client: hold middle mouse and drag for continuous rotation around the screen-centered local player, and use the mouse wheel for 0.55×–2.0× world zoom. WASD is transformed from screen space into world space, the character's head follows the body heading, the player is screen-forward-locked during an active drag, the fixed UI remains unscaled, and the minimap remains north-up. See `config/camera_rotation.csv`.

Movement settings use held Shift for 3.0× running in the preview and the server-authoritative multiplayer game. Running selects dedicated `run_wide_8` sheets: the contact frames stay compact while the two peak frames reach 1.48× leg separation, producing a visibly wider gait without changing the normal walk or moving the ground anchor. All five fluid profiles have eight-direction top-down and isometric run sheets; custom modular combinations use the registered lower-body widening fallback. Releasing Shift, stopping, crouching, going prone, jumping or another action stops running. Forward-propelled jumping and a second-Space double jump both use twice the previous range, and the second launch is drawn slightly larger before landing prone. `X` toggles prone and either `Space` or `X` stands immediately. Directional input cancels crouch or prone through a one-second stand-up delay before movement resumes. See `config/movement_settings.csv` and `previews/wide_gait_run_comparison.png`.

Standing characters automatically enter a six-frame breathing loop after 0.35 seconds, then perform a restrained twelve-frame upper-body weight shift after six seconds and at deterministic intervals. Movement, actions, crouch and prone reset the idle clock immediately. Both camera modes retain a locked ground-contact anchor; strict top-down frames preserve the approved 90° head-and-shoulder projection with legs barely visible. Authored sheets cover the five fluid profiles, while the tester/runtime contract provides a registered modular fallback for every valid outfit combination. See `config/idle_settings.csv`, the `breathing_6`/`waiting_12` rows in `config/fluid_animations.csv`, and `previews/idle_animation_preview.png`.

The separate tester can layer user-created converted Unity assets around this pack without changing the paper-doll contract. The imported running FBX timing is mapped to the dedicated `run_wide_8` artwork at the configured 1.85× cadence, while world speed remains the independent 3.0× setting.

To rebuild the idle sheets after changing source layers, run `tools/generate_idle_animations.py`. To rebuild the dedicated run sheets from the approved walk masters, run `tools/generate_wider_run_animations.py`. Both tools require Pillow; the idle tool also uses Pygame CE.

Legacy profile composites, duplicate helmet overlays, unpaired animation profiles, source weapon crops, and superseded loaders/catalogs are intentionally excluded. `config/paired_parts.csv` is the single source of truth.
