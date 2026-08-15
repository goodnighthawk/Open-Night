# Open Night screenshot-reference workflow

The screenshots supplied for Open Night are the intended model: simple map views that expose road layout, traffic, terrain, transit, and cycling information without requiring a live geographic-data API.

## Recommended use
Use the road-layout screenshot as the base alignment image. Import traffic, terrain, transit, and biking screenshots as optional overlays. They do not have to contain game art; they are tracing references.

Open **Reference Map Trace Studio** and select a layer. Left-click points along a road/route or around a terrain polygon. Enter saves the feature, Backspace/right-click removes the last point, and Escape cancels it. The tool writes only CSV traces.

Then choose **Compile traces to STAGING semantic map**. This maps screenshot pixels into the fixed Open Night world coordinate system and produces roads, traffic routes/starts, terrain polygons, transit overlays, and bicycle lanes/routes deterministically. No random route selection is introduced.

Only after reviewing the result use **Compile + INSTALL**. The old semantic map is backed up first. Cosmetics, street lamps, night previews, and portable `.map` export run afterward exactly as before.

## Why this is safer than automatic image recognition
The program does not try to guess arbitrary colored pixels as collision geometry. Screenshots vary by provider, zoom, labels and theme. Manual/vector-assisted tracing gives a stable authored result and makes traffic priority, road class, transit mode and bike facility explicit. Automated line assistance can be added later without changing the trace CSV contract.
