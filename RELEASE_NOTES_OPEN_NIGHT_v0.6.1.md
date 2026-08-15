# Open Night v0.6.1

- Polished screenshot-derived 16x12 map is the packaged default.
- Zebra crossing bars are guaranteed parallel to the nearest road/lane tangent.
- Compact zebra depths remain 22/26/28 px by residential/secondary/primary road class.
- Added hard art-rule gates for zebra orientation and maximum zebra depth.
- Removed legacy GIS/Overpass source trees, old map backups, and pre-pass rollback files from the release.
- Reference-image generator remains the only map-source workflow.

- Quick Local Test now keeps failed server/client consoles open, prints child exit codes, and pauses on launcher failure so Python tracebacks remain visible.
