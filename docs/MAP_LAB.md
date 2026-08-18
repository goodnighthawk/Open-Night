# Open Night Map Lab

Map Lab is the fast local visual-iteration loop for the v1.0 Ground + Roof map. It uses the same generator, `GridWorld`, `GridRenderer`, and repo-resident `city_block` assets as the game, but it does **not** wait for GitHub Actions.

## Start it

1. In GitHub Desktop, switch to `v1.0-art-overlay` and **Fetch origin / Pull origin**.
2. Open the local `Open-Night` folder.
3. Double-click `MAP_LAB.bat`.
4. A browser gallery opens automatically. Leave the Map Lab command window open.

The first launch installs `pygame-ce` automatically if it is missing.

## Iterate

Edit and save any of these as usual:

- `grid_world.py`
- `grid_renderer.py`
- `grid_runtime.py`
- `tools/generate_v100_ground_roof_layers.py`
- the Ground grid JSON/catalog files
- files inside `assets/source_packs/city_block/`

Map Lab detects the save, regenerates Ground + Roof locally, rerenders the gallery, and the browser refreshes automatically.

The gallery always shows the same proof views:

- full Ground/exterior map
- fixed intersection crop
- largest-building Ground crop
- full Roof map
- the **same largest building** on Roof
- curb + building orientation test sheet, including `example_small.png`
- previous/current Ground difference image

If fewer than 0.5% of sampled Ground pixels changed, the gallery displays a warning. This catches iterations that technically ran but did not visibly change the map.

## Stop it

Click the Map Lab command window and press `Ctrl+C`.

## Output

Local outputs are written to:

`artifacts/map_lab/current/`

The immediately previous successful render is kept in:

`artifacts/map_lab/previous/`

These folders are local working output and should not be committed.

## When to use GitHub Actions

Use Map Lab for repeated art/layout changes. Only push once the local gallery is visibly better. GitHub Actions remains the final regression check for compilation, collision, deterministic generation, asset existence, and exact Ground↔Roof registration.
