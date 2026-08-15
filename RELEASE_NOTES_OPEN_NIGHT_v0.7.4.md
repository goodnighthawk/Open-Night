# Open Night v0.7.4

This is the multiplayer reliability build over v0.7.3.

- Friends remain marked on the world map and compact minimap independently of nearby avatar streaming.
- `/sms FriendName message` supports Tab autocomplete and Railway-backed online/offline delivery. Press F2 to open Messages.
- Client and server versions must match exactly before login, preventing incompatible builds from sharing a session.
- On-foot players can wade in water at reduced speed; cars and bicycles remain blocked from exposed water.
- Player cars now steer around a front-axle pivot.
- NPC run-over blood and respawn require an impact speed of at least 30 mph.
- `UPDATE_FRIEND_BUILD.bat` updates extracted copies from GitHub `main` or a supplied ZIP while preserving local friend/environment files.
- The moderated `/bug` queue and human-approval requirement from v0.7.3 remain unchanged.

Deploy `railway.toml` v0.7.4 before sharing the v0.7.4 friend client. The version gate will reject v0.7.3 clients after that deployment.
