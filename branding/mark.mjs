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
 * Stroke and radius per rendered size rather than one set scaled down. A 16px
 * tray icon gets 1.5 device pixels of stroke from the large-size numbers, which
 * antialiases into a grey smudge; below 20 the ring is drawn heavier so it
 * lands on close to whole pixels.
 */
function geometry(size) {
  if (size <= 20) return { radius: 10.4, stroke: 4, span: 64 }
  if (size <= 32) return { radius: 10.6, stroke: 3.4, span: 66 }
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
