// User-facing wording for the reason categories the backend records when it skips
// a review record. Raw parser diagnostics are never shown, only these categories.
const LABELS: Record<string, string> = {
  missing_text: 'missing review text',
  text_too_long: 'review text too long',
  invalid_rating: 'missing or invalid rating',
  malformed_record: 'malformed source record',
}
const ORDER = Object.keys(LABELS)

export type SkipReasons = Record<string, number>

function validCount(value: unknown): value is number {
  return typeof value === 'number' && Number.isInteger(value) && value > 0
}

// "2 missing review text, 1 missing or invalid rating", or '' when nothing usable is given.
export function describeSkipReasons(reasons: unknown): string {
  if (!reasons || typeof reasons !== 'object' || Array.isArray(reasons)) return ''
  const entries = Object.entries(reasons as Record<string, unknown>).filter(
    (entry): entry is [string, number] => validCount(entry[1]),
  )
  const rank = (reason: string) => {
    const index = ORDER.indexOf(reason)
    return index === -1 ? ORDER.length : index
  }
  entries.sort(([a], [b]) => rank(a) - rank(b) || a.localeCompare(b))
  return entries
    .map(([reason, n]) => `${n} ${LABELS[reason] ?? 'could not be processed'}`)
    .join(', ')
}

// One sentence about skipped records for a run summary, or '' when none were skipped.
export function skippedSentence(skipped: unknown, reasons: unknown, total?: unknown): string {
  if (!validCount(skipped)) return ''
  // "1 record was", "2 records were", "1 of 5 records was".
  const subject = validCount(total)
    ? `${skipped} of ${total} records`
    : `${skipped} record${skipped === 1 ? '' : 's'}`
  const verb = skipped === 1 ? 'was' : 'were'
  const detail = describeSkipReasons(reasons)
  return (
    `${subject} ${verb} skipped${detail ? ` (${detail})` : ''} ` +
    'and not included in the review dataset.'
  )
}
