# User-created asset import

The v2.5 runtime imports selected geometry and effects from the supplied `Assets.zip` without bundling the original Unity project.

| Source family | Runtime result | Integration |
| --- | --- | --- |
| `Arcade_Car_Physics/Models/Car01.obj`–`Car05.obj` | Five 256×256 RGBA top-down vehicle masters | Vehicle manifest indices 81–85; class-sized at draw time; deterministic traffic coverage |
| `CityVoxelPack/.../building1.obj` | 256×256 top-down and isometric building sprites | Movement tester depth sort; game rooftop-module variation |
| `Arcade_Car_Physics/Textures/White puff` | 512×64 eight-frame dust atlas | Visible only during the on-foot run pose |
| `character/Player/Character@Running.fbx` | Motion timing reference | Existing artistically consistent `walk_8` character art played at the configured run cadence |

`tools/import_open_assets.py` is the reproducible converter. `assets/open_source_import/catalog.csv` records exact source paths, final game runtime files, camera modes, and activation status. The supplied assets are marked `user_created` as directed.

Only generated Pygame-compatible PNG/CSV assets are shipped. Unity metadata, editor files, duplicate source textures, and unused models are excluded.
