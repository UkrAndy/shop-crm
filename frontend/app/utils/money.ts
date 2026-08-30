/**
 * Money arithmetic in whole kopiykas.
 *
 * JavaScript has no decimal type, and `0.1 + 0.2 !== 0.3`. The API therefore
 * sends money as strings and computes every total itself. The browser still has
 * to show a running total *while the user is typing*, before anything is saved,
 * and these helpers do that in integers so the number on screen is the one the
 * server will confirm rather than one that drifts by a kopiyka.
 *
 * `number` is safe as the carrier: kopiykas stay exact integers well past
 * 90 000 000 000 000 UAH, far beyond what `numeric(14, 2)` can hold anyway.
 */

const KOPIYKY_PATTERN = /^(\d+)(?:[.,](\d{1,2}))?$/

/** Parse "12.34" into 1234. Returns null for anything not a valid amount. */
export function parseKopiyky(value: string): number | null {
  const match = KOPIYKY_PATTERN.exec(value.trim())
  if (!match) return null

  const whole = Number(match[1])
  // "12.3" means 30 kopiykas, not 3 — pad before parsing.
  const fraction = Number((match[2] ?? '').padEnd(2, '0'))
  return whole * 100 + fraction
}

/** Format 1234 as "12.34". */
export function formatKopiyky(kopiyky: number): string {
  const sign = kopiyky < 0 ? '-' : ''
  const absolute = Math.abs(kopiyky)
  return `${sign}${Math.floor(absolute / 100)}.${String(absolute % 100).padStart(2, '0')}`
}

/**
 * `price × quantity` in kopiykas, or null if the price is unparseable.
 *
 * Multiplying by an integer quantity keeps the result exact, which is why the
 * quantity stays a whole number all the way down to the database.
 */
export function lineTotalKopiyky(price: string, quantity: number): number | null {
  const kopiyky = parseKopiyky(price)
  if (kopiyky === null || !Number.isInteger(quantity)) return null
  return kopiyky * quantity
}
