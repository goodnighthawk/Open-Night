# Reference Images -> Playable Approved-Art Map Rules (v1.5)

Map 001 treats aligned street-map screenshots as the geographic scaffold. The shipped map is authored for gameplay scale and the approved top-down / 2.5D art target.

## Hard geometry rules

1. Roads union with roads; sidewalks union with sidewalks; curbs and furnishing strips are derived once from the final road graph.
2. A normal street cross-section is building -> setback/frontage -> sidewalk -> furnishing strip -> curb -> asphalt.
3. Sidewalk and asphalt geometry must never overlap in the final rendered masks.
4. Ordinary streets require readable sidewalks; motorways/bridge-only transport links may explicitly omit them.
5. Buildings must yield to the complete road + curb + furnishing + sidewalk + frontage + setback envelope.
6. Buildings may be simplified, moved, resized, merged, or deleted when the reference footprint harms readability or gameplay.
7. Gameplay/collision footprints stay simple. Visual 2.5D walls, roof setbacks, penthouses, parapets and roof furniture are client-side art profiles.
8. Intersections are authored as one feature: asphalt, curb corners, curb cuts, zebra crossings, stop bars and signals must agree spatially.
9. Crosswalks connect pedestrian edges and span the final carriageway; they are not generated from traffic lights.
10. Traffic routes must stay on final drivable geometry; pedestrian routes should remain on sidewalk/crosswalk geometry; bike routes remain on bike/eligible-road geometry.

## Placement rules

11. Trees belong in sidewalk furnishing/tree-pit zones, plazas, parks or setbacks. Never place tree trunks in asphalt, crosswalks, buildings or bridge traffic lanes.
12. Lamps, hydrants, bins, signs and similar props belong on the curb-side furnishing zone and must leave the pedestrian through-zone clear.
13. Traffic signals belong at intersection corners/curb edges and near the crossing they control, not in the center of a traffic lane.
14. No prop may block a zebra, curb cut, doorway, spawn, traffic lane or critical pedestrian route.
15. Parked vehicles align with the final curb/road direction and remain clear of crosswalks, intersections and driveways.
16. Important props are deterministic authored data. Do not randomize their runtime placement.
17. Vegetation density is district-sensitive: dense along parks/residential/waterfront edges, lighter where it hides important roadway/landmark composition.

## Scale and visual hierarchy

18. Cars determine lane scale and players determine sidewalk scale. Do not shrink streets to preserve reference geometry.
19. Road, sidewalk, building, water, green space and bridge deck must remain immediately distinguishable at gameplay zoom.
20. Use one world-scale contract for players, vehicles, bicycles, doors, sidewalks, road lanes and props.
21. Empty space must be intentional: park, plaza, parking, waterfront or setback—not simply missing reference-map content.
22. Buildings should form coherent urban street walls rather than repeated floating rectangles.
23. Assign buildings to reusable art families (brick mid-rise, concrete mid-rise, commercial low-rise, industrial, tower, landmark) rather than rendering every footprint identically.
24. 2.5D wall extrusion and shadows share one direction across buildings, trees, bridge structures and vehicles.
25. Landmarks override generic generation. The GWB receives bespoke bridge deck, towers, edge steel, cable cues, gantries and shadows.

## Validation / art-review rules

26. Fail: building intersects protected street corridor.
27. Fail: tree/hydrant/lamp is on drivable asphalt or inside a building.
28. Fail: tree/hydrant/lamp has no valid sidewalk/furnishing zone on its nearest ordinary street.
29. Fail: non-signal prop blocks the protected crosswalk/curb-cut clear zone.
30. Fail: crosswalk is not on a drivable road or is too short for curb-to-curb geometry.
31. Warn/fail: traffic signal is not near any authored crosswalk or is deep in asphalt.
32. Fail: spawn is inside a building or water polygon.
33. Art-review screenshots use fixed camera positions so every visual edit is compared like-for-like.
34. The acceptance question is: **Does the playable map still represent the real place while looking like the approved game artwork?** Literal screenshot tracing fidelity is not the acceptance criterion.
