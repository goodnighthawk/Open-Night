# Open Night v2.1

Player-report reconciliation release covering the current GitHub backlog through
issue #135.

- Corrects curb corner registration, street-lamp direction, visible synchronized
  traffic signals, pedestrian spacing, and bounded junction recovery.
- Repairs clipped bus, truck, and vehicle end caps and corrects the two reported
  upside-down vehicle sprites.
- Brings vehicle collision bodies back to their rendered silhouettes while
  preserving sustained, overlap-free traffic flow.
- Enlarges vehicle lamps and indicators with restrained point glows and adds
  distance-attenuated NPC engine audio.
- Makes traffic cones and large shrubs visible collision objects for players and
  player-driven vehicles.
- Publishes all ten supplier and ten buyer destinations to both normal and
  portable M-map clients.
- Adds vehicle-impact prone recovery so struck pedestrians stop blocking traffic
  temporarily.
- Expands building visuals within their existing authoritative collision cells.
- Restores fire-escape interaction prompts, explicit character customization,
  clean character transparency, and aligned character layers in every pose.
- Repairs underground road validation and refreshes the portable map manifest.
- Keeps the launcher player-focused by removing the developer Map Generator entry.

Release verification includes focused #112–#135 checks, the recent-history gate,
the 75-second 28-car traffic simulation, deterministic map validation, character
contact sheets, audio and radio checks, and default plus portable multiplayer
server handshakes.
