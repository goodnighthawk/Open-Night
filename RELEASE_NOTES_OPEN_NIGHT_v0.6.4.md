# Open Night v0.6.4

This is a multiplayer gameplay update over the complete Open Night v0.6.1 polished-map build and includes every v0.6.3.1 renderer/server-discovery fix.

## Multiplayer and social

- Global lightweight online-player markers make friends discoverable on the full world map without expanding detailed entity interest.
- Esc > Friends adds or removes online names from a local CSV-backed Friends list. Only friends appear on the compact minimap.
- Enter opens nearby local chat. Messages render in temporary speech bubbles above players and vehicle occupants.
- `/w FriendName message` sends a private, differently coloured whisper to an online friend.
- Player names use yellow for the local player and blue for remote players; the old yellow character ring is removed.
- Driver and passenger names remain visible and are stacked above the shared vehicle.

## Rooms, vehicles and movement

- Building interiors are server-authoritative. Players in the same room see one another, their tile movement, names, appearances and chat.
- Slow player-driven cars accept up to three passengers in addition to the driver. Boarding and exiting have speed safety gates.
- Authored layer transitions automatically trigger the jump pose. Manual and automatic jumps render at 1.35× scale with a visible upward lift.
- Vehicle collision uses full rotated rectangular bodies against buildings, shorelines and other vehicles instead of center-point separation.

## World interactions

- Moving vehicle bodies can run over NPC pedestrians. The NPC is removed, a temporary stylized red ground stain is synchronized to nearby clients, and a replacement returns to the route after a delay.
- The fixed customer sale point is removed. Packages sell directly to nearby pedestrian NPCs.
- Nearby player sales use a consent flow: the seller presses E to offer; the buyer presses E to accept and transfers $40.
- Esc Settings is a clipped, mouse-wheel/keyboard scroll menu with additional camera and movement toggles.

## Internet server

The Railway service must be redeployed for v0.6.4 because the authoritative server and multiplayer protocol changed. Run `DEPLOY_OPEN_NIGHT_SERVER.bat` and link the existing `open-night` service if prompted.
