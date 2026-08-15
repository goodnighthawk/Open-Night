# Vehicle asset integration — v2.5

`assets/cars/vehicle_manifest.csv` is the authoritative art catalog used by both server metadata and client rendering.

Normal road traffic uses 81 remade high-resolution sprites derived from the legacy vehicle identities and the approved car art style, plus five Pygame-ready top-down conversions from the supplied user-created Arcade Car Physics geometry. The obsolete originals, Unity project metadata, generation atlases, and superseded staging packs are not shipped.

Every PNG is tightly alpha-cropped. Physical gameplay length is class-controlled rather than inferred from source-canvas padding: compacts 44 px, sedans 48 px, taxi 50 px, vans/pickups 56 px, normal trucks and limo 72 px, fire truck 86 px, bus 98 px, and large cargo truck 104 px. Loaded and unloaded trucks use the same 72 px footprint.

The server transmits only a compact sprite index plus class/footprint metadata. Clients load the matching local PNG and rotate it from its native north/up orientation into the server heading.

The new cars occupy manifest indices 81–85. The deterministic traffic selector deliberately injects one imported car every seven fixed traffic slots, so they remain visible even when a server uses a low traffic count. This design keeps desktop and web clients visually consistent without changing the traffic protocol or road AI.
