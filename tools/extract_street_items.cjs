"use strict";

// Reproducibly repack selected authored groups from city_block/street_items.svg.
const fs = require("fs");
const path = require("path");
const crypto = require("crypto");
const sharp = require("sharp");

const root = path.resolve(__dirname, "..");
const source = path.join(root, "assets", "source_packs", "city_block", "street_items.svg");
const output = path.join(root, "assets", "source_packs", "city_block", "street_decorations");
const exportsByGroup = {
  g12580: "traffic_cone.png",
  g12894: "street_lamp.png",
  g41404: "telephone_box.png",
};

async function main() {
  fs.mkdirSync(output, { recursive: true });
  const original = fs.readFileSync(source, "utf8");
  const manifest = {
    source: "assets/source_packs/city_block/street_items.svg",
    source_sha256: crypto.createHash("sha256").update(Buffer.from(original)).digest("hex"),
    extraction: "top-level SVG group isolation, transparent trim, lossless PNG",
    assets: [],
  };
  for (const [groupId, filename] of Object.entries(exportsByGroup)) {
    const css = `<style>#layer1 &gt; *:not(#${groupId}){display:none!important}</style>`;
    const selected = original.replace("</defs>", `${css}</defs>`);
    const info = await sharp(Buffer.from(selected))
      .trim({ background: { r: 0, g: 0, b: 0, alpha: 0 } })
      .png({ compressionLevel: 9 })
      .toFile(path.join(output, filename));
    manifest.assets.push({ group_id: groupId, filename, width: info.width, height: info.height });
  }
  fs.writeFileSync(path.join(output, "manifest.json"), `${JSON.stringify(manifest, null, 2)}\n`);
  console.log(`Extracted ${Object.keys(exportsByGroup).length} city_block street items.`);
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
