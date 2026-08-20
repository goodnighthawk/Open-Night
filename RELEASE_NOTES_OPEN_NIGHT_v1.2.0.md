# Open Night v1.2.0

Open Night v1.2 is the collision-recovery release based on player bug #30.

## Fixed

- AI cars no longer snap through large heading changes while separating after a collision.
- Recovery steering is capped at eight degrees per correction.
- Recovering cars inch at 12–24 pixels per second until clear, then resume their route.
- The sustained traffic gate now verifies the bounded recovery angle and recovery speed contract.

## Preserved

- The player-approved 22-car civilian fleet and unmatched special-vehicle fallbacks.
- Connected pedestrian routes, dense crossings, building setbacks, MySQL persistence, and durable bug delivery.
- `main` remains the only normal player update branch and the production Railway service remains `open-night`.

The multiplayer protocol/build version is `1.2`; v1.1 clients are intentionally blocked from joining until updated.
