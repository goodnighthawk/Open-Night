# v2.2 deterministic fixed-flow traffic system

The v2.2 traffic architecture preserves the rule that forbids runtime random numbers for AI route and start selection.

## Source of truth

- `traffic_routes.csv` + `traffic_route_points.csv`: fixed moving-car loops.
- `traffic_starts.csv`: fixed car-to-route/start assignments. The first `--traffic N` rows are activated.
- `bicycle_routes.csv` + `bicycle_starts.csv`: fixed bicycle routes and starts.
- `npc_routes.csv` + `npc_starts.csv`: fixed pedestrian routes and starts.
- `parked_vehicles.csv`, `parked_bicycles.csv`, and bicycle-rack street props remain fixed map data.

There is no weighted random route chooser and no random start fraction at server startup. Cars remain on their assigned route. If an off-screen car is recycled after being stuck, it returns to its own fixed start slot.

## Traffic density

Historical traffic data should be compiled **offline** into the number and order of rows in `traffic_starts.csv`. A busy arterial therefore owns more fixed slots. The runtime server does not need a traffic-density probability model.

For Map 001 the fixed 120-slot table deliberately gives the largest share to GWB and major N/S + E/W arterial loops. Because the table is weighted-round-robin ordered, even a smaller request such as `--traffic 28` produces a representative mix of corridors.

## Runtime decisions retained

Runtime AI only handles local physical decisions: traffic lights, following distance, collision reservation, yielding to players, and deterministic stuck recovery. These are not route-selection systems.


## Enforcement

All moving AI start tables are resolved through one `_fixed_start_plan()` path. CSV row order, `route_id`, and `start_fraction` are authoritative. The runtime does not wrap, perturb, weight, or replace authored start fractions. `DETERMINISM_AUDIT.bat` checks the map tables and scans the fixed-start runtime functions for accidental random-number calls.
