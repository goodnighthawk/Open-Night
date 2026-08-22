# Open Night v2.0

Character-art replacement release built around the updated grungy 90-degree
top-down sprite sheet.

- Adds the cleaned 8x10 master sprite sheet and 80 transparent runtime layers:
  8 hats, 8 heads, and 8 body styles across 8 movement states.
- Replaces the live character renderer and catalog with a three-layer
  Hat + Head + Body system used consistently by players and human NPCs.
- Supports idle, left/right walk, left/right run, jump, crouch, and prone art,
  with runtime rotation matching the player's world-facing direction.
- Updates the character customization screen with the new presets and parts.
- Migrates existing saved appearances deterministically and persists new hats
  through the compatible account field without resetting player data.
- Removes the obsolete portrait-head overlay from the canonical game client so
  it cannot cover or conflict with the new top-down artwork.

The v2.0 gate verifies every asset's dimensions, renders all 64 body/state
combinations with their matching head and hat, checks account migration and
persistence compatibility, and reruns the main client/server release audits.
