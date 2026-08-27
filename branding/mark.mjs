/**
 * The Shiemi mark: one arc rotated four times around an empty centre, with the
 * top arc carrying the accent.
 *
 * Geometry lives here rather than in an exported asset so every surface draws
 * the same shape from the same numbers, and so the icon is reproducible from
 * source like the rest of the build.
 */

export const INK_DARK = '#121211'
export const INK_LIGHT = '#ecebe8'
export const PLATE = '#0d0d0c'
export const ACCENT = '#d2703f'

const BOX = 32
const MID = BOX / 2

/**
 * Stroke, radius and span per rendered size rather than one set scaled down.
 *
 * Two things fail if the large-size numbers are simply shrunk. A 16px icon gets
 * 1.5 device pixels of stroke, which antialiases into a grey smudge, so small
 * sizes are drawn heavier. And the round caps overhang each arc end by half the
 * stroke, which leaves a gap of about a third of the stroke width: fine at 8
 * device pixels, gone below one, at which point the four arcs fuse into a plain
 * ring and the mark loses its shape. So the span shortens as the size drops,
 * holding the gap above 1.4 device pixels everywhere.
 */
function geometry(size) {
  if (size <= 20) return { radius: 10.4, stroke: 4, span: 52 }
  if (size <= 32) return { radius: 10.6, stroke: 3.4, span: 61 }
  return { radius: 10.7, stroke: 3.1, span: 68 }
}

const rad = (deg) => (deg * Math.PI) / 180
const fixed = (n) => Number(n.toFixed(2))

function arc(mid, { radius, span, stroke }, colour, className) {
  const at = (deg) =>
    `${fixed(MID + radius * Math.cos(rad(deg)))} ${fixed(MID + radius * Math.sin(rad(deg)))}`
  return (
    `<path d="M ${at(mid - span / 2)} A ${radius} ${radius} 0 0 1 ${at(mid + span / 2)}" ` +
    (className ? `class="${className}" ` : '') +
    `fill="none" stroke="${colour}" stroke-width="${stroke}" stroke-linecap="round"/>`
  )
}

/** The four arcs alone, no plate and no wrapper. */
export function arcs({ size = 256, ink = INK_LIGHT, accent = ACCENT } = {}) {
  const geo = geometry(size)
  // Top arc first, so the accent always lands in the same place.
  return [0, 1, 2, 3]
    .map((i) => arc(-90 + i * 90, geo, i === 0 && accent ? accent : ink))
    .join('')
}

/**
 * A complete SVG document.
 *
 * `plate` is for anywhere the mark cannot ask what is behind it: a Windows icon
 * has no way to read the taskbar colour, and ink on its own would disappear.
 * Browser tabs can be asked, so the favicon leaves it off.
 */
export function svg({ size = 256, ink = INK_LIGHT, accent = ACCENT, plate = null } = {}) {
  const radius = fixed(BOX * 0.23)
  return (
    `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${BOX} ${BOX}">` +
    (plate ? `<rect width="${BOX}" height="${BOX}" rx="${radius}" fill="${plate}"/>` : '') +
    arcs({ size, ink, accent }) +
    '</svg>'
  )
}

/**
 * The mark in Chromium's vector icon format, for the product logo drawn in
 * infobars, dialogs and the omnibox.
 *
 * That format fills paths and has no stroke command, so each arc is emitted as
 * an annular sector closed by a semicircular cap at each end. ARC_TO takes the
 * SVG argument order: rx, ry, rotation, large-arc, sweep, x, y.
 *
 * No colour is emitted. Every surface that draws this tints it to suit the
 * theme, so a fixed colour would be wrong against one background or the other,
 * and the accent belongs on the app icon where the backdrop is ours.
 */
export function vectorIcon(canvases = [24]) {
  const sizes = [...canvases].sort((a, b) => b - a)
  return sizes.map(sector).join('\n') + '\n'
}

function sector(canvas) {
  const scale = canvas / BOX
  const { radius, span, stroke } = geometry(canvas)
  const cap = (stroke * scale) / 2
  const outer = radius * scale + cap
  const inner = radius * scale - cap
  const centre = canvas / 2
  const at = (r, deg) =>
    `${fixed(centre + r * Math.cos(rad(deg)))}, ${fixed(centre + r * Math.sin(rad(deg)))}`

  const lines = [`CANVAS_DIMENSIONS, ${canvas},`]
  for (const i of [0, 1, 2, 3]) {
    const from = -90 + i * 90 - span / 2
    const to = -90 + i * 90 + span / 2
    lines.push(
      `MOVE_TO, ${at(outer, from)},`,
      `ARC_TO, ${fixed(outer)}, ${fixed(outer)}, 0, 0, 1, ${at(outer, to)},`,
      `ARC_TO, ${fixed(cap)}, ${fixed(cap)}, 0, 0, 1, ${at(inner, to)},`,
      `ARC_TO, ${fixed(inner)}, ${fixed(inner)}, 0, 0, 0, ${at(inner, from)},`,
      `ARC_TO, ${fixed(cap)}, ${fixed(cap)}, 0, 0, 1, ${at(outer, from)},`,
      'CLOSE,',
    )
  }
  lines[lines.length - 1] = 'CLOSE'
  return lines.join('\n')
}

/**
 * Favicon variant: no plate, and the ink follows the browser's scheme.
 *
 * The stroke is set twice on purpose. The attribute is what renderers that
 * ignore stylesheets will use, and custom properties are worse still: librsvg
 * drops a var() stroke entirely and the mark loses three of its four arcs.
 */
export function themedSvg() {
  const geo = geometry(32)
  const body = [0, 1, 2, 3]
    .map((i) =>
      i === 0
        ? arc(-90, geo, ACCENT)
        : arc(-90 + i * 90, geo, INK_DARK, 'ink'),
    )
    .join('')
  return (
    `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${BOX} ${BOX}">` +
    '<style>' +
    `.ink{stroke:${INK_DARK}}` +
    `@media(prefers-color-scheme:dark){.ink{stroke:${INK_LIGHT}}}` +
    '</style>' +
    body +
    '</svg>'
  )
}
