# Open Night v4.0 — GWB playtest

The GWB corridor is the game's default map. This update adds the current generated
art, corrects the bridge approaches, enlarges its towers/trusses, and adds deck
barriers. Two overlapping avenues are removed; all perspective-bearing map art
faces south.

First- and second-floor shells share the exact rooftop footprints. Street/floor
and rooftop interactions connect the layers in both directions. Manholes connect
to a continuous underground pipe network with walkable junctions. Rooftops retain
a clear view of the surrounding city.

For the game, extract the source package and run `PLAYTEST_V4.bat`. It prepares
Python dependencies if needed and starts a local server and client. Both participants must use this v4.0 client/server build. The existing
production server has not been redeployed by this update.

For the standalone preview, extract the workbench package and double-click
`MAP_WORKBENCH.bat` (do not run a .bat file through Python).

- G: ground; R: roof; 1 / 2: first / second floor; U: underground pipes.
- Y: show population debug markers, then hover to inspect identity, kind, role, and level.
- F: fit the full map; mouse wheel: zoom; drag or WASD: pan.
- F5: reload map data; Ctrl+R: regenerate the GWB layout and all five layers.

Verified locally: catalog loading, exact floor/roof masks, all paired transition
endpoints through server interaction handlers, movement through every pipe junction,
bridge barriers, prediction, server housing/privacy contract, canonical population
startup, and two-client visibility/reconnect/messaging. The packaged workbench was
smoke-tested on floor and underground views.

The two new floors are unfurnished playtest shells. Production deployment,
latency-feel testing, and broader human gameplay regression remain separate gates.
