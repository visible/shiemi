/**
 * The Shiemi mark: six petals radiating from an open centre.
 *
 * Geometry lives here rather than in an exported asset so every surface draws
 * the same shape from the same numbers, and so the icon is reproducible from
 * source like the rest of the build.
 */

export const PLATE = '#d2703f'
export const MARK = '#ffffff'
export const INK_DARK = '#121211'
export const INK_LIGHT = '#ecebe8'

const BOX = 32
const MID = BOX / 2
const COUNT = 6

/**
 * Petal proportions per rendered size rather than one set scaled down.
 *
 * The large numbers are the drawn shape. Below 32 a petal is under two device
 * pixels across at its widest, which antialiases into a grey smear and closes
 * the gaps between petals, so small sizes are drawn shorter and fatter to hold
 * six distinct shapes.
 */
function geometry(size) {
  if (size <= 20) return { tip: 11.8, width: 29, base: 2.9 }
  if (size <= 32) return { tip: 12.2, width: 25, base: 2.4 }
  return { tip: 12.4, width: 21, base: 2.0 }
}

const rad = (deg) => (deg * Math.PI) / 180
const fixed = (n) => Number(n.toFixed(2))

const angles = () =>
  Array.from({ length: COUNT }, (_, i) => -90 + i * (360 / COUNT))

/**
 * One petal as polar anchor and control points: narrow at the centre, swelling
 * out to a rounded tip and back. Two cubics, so it serialises to both SVG and
 * Chromium's vector icon format without either one reparsing the other.
 *
 * `width` is the angular spread of the control points rather than of the curve,
 * so a petal reads a little narrower than the number suggests.
 */
function petal(deg, { tip, width, base }) {
  return [
    [base, deg],
    [tip * 0.55, deg - width],
    [tip * 0.97, deg - width * 0.5],
    [tip, deg],
    [tip * 0.97, deg + width * 0.5],
    [tip * 0.55, deg + width],
    [base, deg],
  ]
}

/** Project polar points onto a square canvas of the given side. */
const projector = (side) => (r, deg) => {
  const scale = side / BOX
  return [
    fixed(side / 2 + r * scale * Math.cos(rad(deg))),
    fixed(side / 2 + r * scale * Math.sin(rad(deg))),
  ]
}

export const VIEWBOX = `0 0 ${BOX} ${BOX}`

/** One SVG path string per petal, for callers that draw their own elements. */
export function paths({ size = 256 } = {}) {
  const geo = geometry(size)
  const at = projector(BOX)
  return angles().map((deg) => {
    const [start, ...rest] = petal(deg, geo).map(([r, d]) => at(r, d).join(' '))
    return `M ${start} C ${rest.slice(0, 3).join(' ')} C ${rest.slice(3).join(' ')} Z`
  })
}

/** The petals alone, no plate and no wrapper. */
export function petals({ size = 256, colour = MARK } = {}) {
  return paths({ size })
    .map((d) => `<path d="${d}" fill="${colour}"/>`)
    .join('')
}

/**
 * A complete SVG document.
 *
 * `plate` carries the brand colour and keeps the mark legible on a surface we
 * do not control, which is every surface an icon lands on: a taskbar, a tab
 * strip, a home screen. White petals on their own would vanish on light.
 */
export function svg({ size = 256, colour = MARK, plate = PLATE } = {}) {
  const radius = fixed(BOX * 0.234)
  return (
    `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${BOX} ${BOX}">` +
    (plate ? `<rect width="${BOX}" height="${BOX}" rx="${radius}" fill="${plate}"/>` : '') +
    petals({ size, colour }) +
    '</svg>'
  )
}

/**
 * The mark in Chromium's vector icon format, for the product logo drawn in
 * infobars, dialogs and the omnibox.
 *
 * No colour and no plate are emitted: every surface that draws this tints it to
 * suit the theme, so anything fixed here would fight one theme or the other.
 * CUBIC_TO takes absolute control points, in the SVG argument order.
 */
export function vectorIcon(canvases = [24]) {
  return (
    [...canvases]
      // The aggregator rejects representations that are not largest first.
      .sort((a, b) => b - a)
      .map(representation)
      .join('\n') + '\n'
  )
}

function representation(canvas) {
  const geo = geometry(canvas)
  const at = projector(canvas)

  const lines = [`CANVAS_DIMENSIONS, ${canvas},`]
  for (const deg of angles()) {
    const [start, ...rest] = petal(deg, geo).map(([r, d]) => at(r, d).join(', '))
    lines.push(
      `MOVE_TO, ${start},`,
      `CUBIC_TO, ${rest.slice(0, 3).join(', ')},`,
      `CUBIC_TO, ${rest.slice(3).join(', ')},`,
      'CLOSE,',
    )
  }
  lines[lines.length - 1] = 'CLOSE'
  return lines.join('\n')
}
