# Scalability roadmap — whole NYC / ~1,000 players

## Present in v2.4.4

- Stable 1024px chunk contract.
- 192-chunk test world (2× the original map area).
- 6 logical regions, 8×4 chunks each.
- Chunk-bucket entity interest management with radius 2.
- Static map data remains local/chunked rather than scaling the login payload with world size.
- Deterministic traffic route/start architecture.

## Next major challenges

1. **Multi-process region ownership and handoff** — the single Python process still owns all six logical regions.
2. **Reference-map compiler → chunk contract** — compile traced roads/buildings/land use directly into 1024px chunks rather than temporary scaffold geometry.
3. **Delta/binary snapshots** — reduce JSON/network cost as entity and player counts rise.
4. **Simulation LOD** — fully simulate nearby traffic/NPCs while representing distant populations as inexpensive flow state.
5. **Client chunk streaming/culling** — whole NYC must load/unload art, collision and props by proximity.
6. **Persistence throughput** — pool/queue database work and separate high-frequency simulation state from durable account/world state.
7. **Failure isolation and observability** — region supervision, recovery, metrics, logs, and reconnect behavior.
8. **Browser asset streaming** — Pygbag cannot ship a whole-city art bundle as one monolithic download.
