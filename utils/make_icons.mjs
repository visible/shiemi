#!/usr/bin/env node
/**
 * Generate every icon surface from branding/mark.mjs.
 *
 *   bun utils/make_icons.mjs
 *
 * Writes the browser icon set to branding/icons/ and the site icons into
 * apps/web/app/. Both are committed, so neither a build nor a deploy needs an
 * image library: utils/build.py only copies files into the Chromium tree.
 * Re-run this when the mark changes.
 *
 * Each size is rendered from the mark at that size rather than downscaled from
 * one master, so the antialiasing is computed for the pixels it will occupy.
 */

import { Buffer } from 'node:buffer'
import { mkdir, writeFile } from 'node:fs/promises'
import path from 'node:path'
import sharp from 'sharp'
import { INK_LIGHT, PLATE, svg, themedSvg, vectorIcon } from '../branding/mark.mjs'

const ROOT = path.resolve(import.meta.dirname, '..')
const OUT = path.join(ROOT, 'branding', 'icons')
const VECTOR = path.join(ROOT, 'branding', 'vector')
const WEB = path.join(ROOT, 'apps', 'web', 'app')

// Sizes small enough that a BMP payload stays cheap. Windows has read PNG
// payloads since Vista, so the large ones go in as PNG to keep the file small.
const ICO_BMP = [16, 24, 32, 48, 64]
const ICO_PNG = [128, 256]

// Exactly the names Chromium already ships, so the overlay is like for like and
// no .grd reference is left dangling.
const LOGOS = [16, 24, 48, 64, 128, 256]

// Chromium draws the product logo from .icon files in four separate targets,
// each declaring its own canvas. Keys mirror the Chromium tree so the overlay in
// utils/build.py can copy by relative path with no lookup table of its own.
const VECTORS = {
  'chrome/app/vector_icons/browser_logo_old.icon': [16],
  'chrome/app/vector_icons/chrome_product.icon': [16],
  'components/omnibox/browser/vector_icons/chrome_product.icon': [24],
  'components/omnibox/browser/vector_icons/product_chrome_refresh_old.icon': [15],
  'components/omnibox/browser/vector_icons/product_old.icon': [32, 16],
  'components/vector_icons/chromium/product.icon': [24],
  'components/vector_icons/chromium/product_refresh.icon': [24],
  'ui/message_center/vector_icons/chrome_product.icon': [24],
  'ui/message_center/vector_icons/product_old.icon': [96],
}

/** Rasterise the mark at its final size. */
function draw(size, options = {}) {
  const markup = svg({ size, ...options })
  return sharp(Buffer.from(markup), { density: 2400 }).resize(size, size)
}

function icoDirEntry(size, bytes, offset) {
  const entry = Buffer.alloc(16)
  entry.writeUInt8(size >= 256 ? 0 : size, 0)
  entry.writeUInt8(size >= 256 ? 0 : size, 1)
  entry.writeUInt16LE(1, 4) // planes
  entry.writeUInt16LE(32, 6) // bpp
  entry.writeUInt32LE(bytes, 8)
  entry.writeUInt32LE(offset, 12)
  return entry
}

/** A 32bpp BI_RGB image plus the AND mask the format still demands. */
function bmpPayload(rgba, size) {
  const header = Buffer.alloc(40)
  header.writeUInt32LE(40, 0)
  header.writeInt32LE(size, 4)
  header.writeInt32LE(size * 2, 8) // colour data and mask stacked
  header.writeUInt16LE(1, 12)
  header.writeUInt16LE(32, 14)

  const maskStride = Math.ceil(size / 32) * 4
  const colour = Buffer.alloc(size * size * 4)
  header.writeUInt32LE(colour.length + maskStride * size, 20)

  for (let y = 0; y < size; y++) {
    const row = (size - 1 - y) * size * 4 // BMP rows run bottom up
    for (let x = 0; x < size; x++) {
      const s = row + x * 4
      const d = (y * size + x) * 4
      colour[d] = rgba[s + 2]
      colour[d + 1] = rgba[s + 1]
      colour[d + 2] = rgba[s]
      colour[d + 3] = rgba[s + 3]
    }
  }

  // Alpha in the colour data already describes the shape; the mask stays zero.
  return Buffer.concat([header, colour, Buffer.alloc(maskStride * size)])
}

async function buildIco() {
  const payloads = []

  for (const size of ICO_BMP) {
    const { data } = await draw(size, { plate: PLATE })
      .raw()
      .toBuffer({ resolveWithObject: true })
    payloads.push({ size, data: bmpPayload(data, size) })
  }

  for (const size of ICO_PNG) {
    const data = await draw(size, { plate: PLATE }).png({ compressionLevel: 9 }).toBuffer()
    payloads.push({ size, data })
  }

  const header = Buffer.alloc(6)
  header.writeUInt16LE(1, 2)
  header.writeUInt16LE(payloads.length, 4)

  let offset = 6 + payloads.length * 16
  const entries = payloads.map(({ size, data }) => {
    const entry = icoDirEntry(size, data.length, offset)
    offset += data.length
    return entry
  })

  return Buffer.concat([header, ...entries, ...payloads.map((p) => p.data)])
}

const report = (name, bytes) => console.log(`  ${name.padEnd(26)}${bytes} bytes`)

await mkdir(path.join(OUT, 'win'), { recursive: true })

const ico = await buildIco()
await writeFile(path.join(OUT, 'win', 'chromium.ico'), ico)
console.log(`  chromium.ico            ${ICO_BMP.length + ICO_PNG.length} images  ${ico.length} bytes`)

for (const size of LOGOS) {
  const data = await draw(size, { plate: PLATE }).png({ compressionLevel: 9 }).toBuffer()
  await writeFile(path.join(OUT, `product_logo_${size}.png`), data)
  report(`product_logo_${size}.png`, data.length)
}

// Tray and status surfaces expect a single-colour mark, so the accent drops out
// and the plate with it.
const mono = await draw(22, { ink: INK_LIGHT, accent: null })
  .png({ compressionLevel: 9 })
  .toBuffer()
await writeFile(path.join(OUT, 'product_logo_22_mono.png'), mono)
report('product_logo_22_mono.png', mono.length)

// The favicon ships as SVG so the ink can follow the tab strip's scheme. Apple
// touch icons cannot, and are composited on an unknown colour, so that one
// keeps its plate.
const favicon = themedSvg()
await writeFile(path.join(WEB, 'icon.svg'), `${favicon}\n`)
report('app/icon.svg', favicon.length + 1)

const apple = await draw(180, { plate: PLATE }).png({ compressionLevel: 9 }).toBuffer()
await writeFile(path.join(WEB, 'apple-icon.png'), apple)
report('app/apple-icon.png', apple.length)

for (const [relative, canvases] of Object.entries(VECTORS)) {
  const dest = path.join(VECTOR, relative)
  await mkdir(path.dirname(dest), { recursive: true })
  const body = `// Generated by utils/make_icons.mjs; edits here are lost.\n${vectorIcon(canvases)}`
  await writeFile(dest, body)
  report(relative, body.length)
}
