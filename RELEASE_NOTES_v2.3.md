# Open Night v2.3

Player-report reconciliation release covering the GitHub backlog through issue #160.

- Adds E passenger boarding for nearby player-driven cars and a Space handbrake for drivers.
- Adds deterministic curbside parking bays, with both parked cars and open spaces for players.
- Prevents collision pileups by displacing overlapped players, low-speed pedestrians, and non-player cars to legal clear poses.
- Keeps pedestrians on connected crossing routes while checking for close and approaching cars, and adds soft crowd separation.
- Restores all dynamic GridWorld traffic-light fixtures and all 20 supplier/buyer markers on the M map and minimap.
- Moves public phones inward onto pavement and gives each one a compact cyan light pool.
- Enlarges the reported wooden shrub planter fourfold with matching collision.
- Removes gridcar010's synthetic rear-strip artifact and corrects the red/white cap with a north-facing peak.

Release verification covers reports #150–#160, all carried report suites, deterministic parking/signal/job population, multiplayer handshakes, sustained traffic recovery, world collision, launcher/version authority, and runtime visual review.
