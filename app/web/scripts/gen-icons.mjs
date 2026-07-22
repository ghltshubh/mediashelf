// One-off PWA icon generator. Rasterizes the brand logomark (kept in sync with
// src/components/Logo.tsx) into the PNG icons the manifest and index.html
// reference. Run manually after a logomark change:  node scripts/gen-icons.mjs
// `sharp` is a devDependency used only here — never imported at runtime.

import { mkdir, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import sharp from "sharp";

const OWNED = "#e3a84c"; // --owned (brass)
const BG = "#141210"; // --bg-0 (deep warm charcoal)
const outDir = resolve(dirname(fileURLToPath(import.meta.url)), "../public");

// The logomark from src/components/Logo.tsx, recolored to a concrete hex.
const MARK = `
  <rect x="3" y="20.2" width="22" height="2.6" rx="1.3" fill="${OWNED}"/>
  <rect x="5.2" y="9" width="3.3" height="11.2" rx="1.3" fill="${OWNED}"/>
  <rect x="9.9" y="5.8" width="3.3" height="14.4" rx="1.3" fill="${OWNED}" opacity="0.72"/>
  <rect x="14.6" y="10.6" width="3.3" height="9.6" rx="1.3" fill="${OWNED}" opacity="0.5"/>
  <rect x="19.3" y="8.4" width="3.3" height="11.8" rx="1.3" fill="${OWNED}" opacity="0.86" transform="rotate(11 20.95 14.3)"/>
`;

// Centered logomark (native viewBox 0..28) on an optional background, sized so
// the mark fills `inner` of the canvas — smaller inner = more padding.
function iconSvg(size, inner, { bg = BG, radius = 0 } = {}) {
  const box = size * inner;
  const offset = (size - box) / 2;
  const scale = box / 28;
  const bgRect = bg ? `<rect width="${size}" height="${size}" rx="${radius}" fill="${bg}"/>` : "";
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${size}" height="${size}" viewBox="0 0 ${size} ${size}">${bgRect}<g transform="translate(${offset} ${offset}) scale(${scale})">${MARK}</g></svg>`;
}

async function png(svg, size, file) {
  await sharp(Buffer.from(svg)).resize(size, size).png().toFile(resolve(outDir, file));
}

await mkdir(outDir, { recursive: true });
// Standard "any" icons + iOS home-screen icon: dark bg, ~70% content.
await png(iconSvg(512, 0.7), 512, "icon-512.png");
await png(iconSvg(192, 0.7), 192, "icon-192.png");
await png(iconSvg(180, 0.7), 180, "apple-touch-icon.png");
// Maskable: extra padding so the mark survives the platform's safe-zone crop.
await png(iconSvg(512, 0.56), 512, "icon-maskable-512.png");
// Browser-tab favicon: crisp vector, dark rounded square.
await writeFile(resolve(outDir, "favicon.svg"), iconSvg(32, 0.8, { radius: 6 }));

console.log("PWA icons written to", outDir);
