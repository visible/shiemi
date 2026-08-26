#!/usr/bin/env node
/**
 * Generate the branding icon set from branding/mark.png.
 *
 *   bun utils/make_icons.mjs
 *
 * Output goes to branding/icons/ and is committed, so a build never needs an
 * image library: utils/build.py only copies the files into the Chromium tree.
 * Re-run this only when the master art changes.
 */

import { Buffer } from 'node:buffer'
import { mkdir, writeFile } from 'node:fs/promises'
import path from 'node:path'
import sharp from 'sharp'

const ROOT = path.resolve(import.meta.dirname, '..')
const MASTER = path.join(ROOT, 'branding', 'mark.png')
const OUT = path.join(ROOT, 'branding', 'icons')

// Windows draws app icons edge to edge, but the mark is a figure rather than a
// glyph and reads as cramped without a little room. At or below 24px every pixel
// counts more than the breathing room does, so those go full bleed.
const MARGIN = 0.06
const TIGHT_AT_OR_BELOW = 24

// Sizes small enough that a BMP payload stays cheap. Windows has read PNG
// payloads since Vista, so the large ones go in as PNG to keep the file small.
const ICO_BMP = [16, 24, 32, 48, 64]
const ICO_PNG = [128, 256]

// Exactly the names Chromium already ships, so the overlay is like for like and
// no .grd reference is left dangling.
const LOGOS = [16, 24, 48, 64, 128, 256]

async function squared(margin) {
  const trimmed = await sharp(MASTER).trim().toBuffer({ resolveWithObject: true })
  const { width, height } = trimmed.info
  const side = Math.round(Math.max(width, height) * (1 + margin * 2))
  const pad = (n) => Math.floor((side - n) / 2)

  return sharp({
    create: {
      width: side,
      height: side,
      channels: 4,
      background: { r: 0, g: 0, b: 0, alpha: 0 },
    },
  })
    .composite([{ input: trimmed.data, top: pad(height), left: pad(width) }])
    .png()
    .toBuffer()
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
    const { data } = await scaled(size).raw().toBuffer({ resolveWithObject: true })
    payloads.push({ size, data: bmpPayload(data, size) })
  }

  for (const size of ICO_PNG) {
    const data = await scaled(size).png({ compressionLevel: 9 }).toBuffer()
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

const padded = await squared(MARGIN)
const tight = await squared(0)

/** Downscale from whichever framing suits the size, sharpening the tiny ones. */
function scaled(size) {
  const small = size <= TIGHT_AT_OR_BELOW
  const pipe = sharp(small ? tight : padded).resize(size, size, {
    kernel: 'lanczos3',
  })
  return small ? pipe.sharpen({ sigma: 0.6 }) : pipe
}

await mkdir(path.join(OUT, 'win'), { recursive: true })

const ico = await buildIco()
await writeFile(path.join(OUT, 'win', 'chromium.ico'), ico)
console.log(`  chromium.ico          ${ICO_BMP.length + ICO_PNG.length} images  ${ico.length} bytes`)

for (const size of LOGOS) {
  const data = await scaled(size).png({ compressionLevel: 9 }).toBuffer()
  await writeFile(path.join(OUT, `product_logo_${size}.png`), data)
  console.log(`  product_logo_${size}.png`.padEnd(26) + `${data.length} bytes`)
}

// Tray and status surfaces expect a single-colour mark.
const mono = await scaled(22).greyscale().png({ compressionLevel: 9 }).toBuffer()
await writeFile(path.join(OUT, 'product_logo_22_mono.png'), mono)
console.log(`  product_logo_22_mono.png`.padEnd(26) + `${mono.length} bytes`)
