# v0.3

- Rebuilt the 100-object environment sprite generator around the approved NYC/GWB palette and 2.5D detail language.
- Added richer building families, roof equipment, water towers, storefront strips, layered trees, road furniture, bridge/highway signage and waterfront objects.
- Added separate mod-friendly surface material tiles, sign textures and lighting-glow textures.
- Kept GTA2 influence in contrast, street readability, action-focused silhouettes and night lighting while returning the daytime palette/massing to the approved NYC target.
- Added portable `.map` export with a sibling editable `*_assets` folder.
- `.map` stores semantic map CSV tables and cosmetic/light/sign tables in a versioned JSON document and references assets only with relative paths.
- Added asset manifest with SHA-256 hashes and a portable-map validator.
- Added `EXPORT_PORTABLE_MAP.bat`.
- Geometry profile no longer uses literal 3x authored lanes; the v3 profile caps hierarchy at 6/4/3/2/1 lanes by road class.
