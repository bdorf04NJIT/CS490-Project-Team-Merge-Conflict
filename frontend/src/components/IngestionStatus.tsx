import type { IngestionState } from '../api/targets'

type Props = { ingestion: IngestionState | null }

// Ingestion runs synchronously, so a persisted run is always finished: it either
// succeeded, partially succeeded (some records skipped) or failed.
const STATES: Record<string, { label: string; tone: string }> = {
  succeeded: {
    label: 'Last ingestion succeeded',
    tone: 'border-green-200 bg-green-50 text-green-800',
  },
  partial: {
    label: 'Last ingestion partially succeeded',
    tone: 'border-amber-200 bg-amber-50 text-amber-900',
  },
  failed: {
    label: 'Last ingestion failed',
    tone: 'border-red-200 bg-red-50 text-red-800',
  },
}
const UNKNOWN_TONE = 'border-slate-200 bg-slate-50 text-slate-700'

const timeFormat = new Intl.DateTimeFormat('en-US', { dateStyle: 'medium', timeStyle: 'short' })

function count(value: unknown): number | null {
  return typeof value === 'number' && Number.isInteger(value) && value >= 0 ? value : null
}

function plural(n: number, word: string) {
  return `${n} ${word}${n === 1 ? '' : 's'}`
}

function details(ingestion: IngestionState): string | null {
  const imported = count(ingestion.imported_count)
  const skipped = count(ingestion.skipped_count)
  const total = count(ingestion.total_count)
  if (ingestion.status === 'failed') {
    // The backend only stores safe, user-facing failure messages.
    const reason = ingestion.message?.trim()
    return `${reason ? `${reason} ` : ''}No reviews were added by this attempt.`
  }
  if (imported === null) return null
  // imported_count excludes reviews that were already saved by an earlier run.
  const added = `Added ${plural(imported, 'new review')}.`
  if (ingestion.status === 'partial' && skipped !== null) {
    const of = total !== null ? ` of ${total}` : ''
    return `${added} ${skipped}${of} records couldn't be used and were skipped.`
  }
  return added
}

function completedAt(value: unknown) {
  if (typeof value !== 'string') return null
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return null
  return (
    <time dateTime={value} className="block text-xs opacity-80">
      Finished {timeFormat.format(date)}
    </time>
  )
}

// Shows the result of the target's most recent persisted ingestion run. It reflects
// stored run state rather than guessing from whether any reviews exist.
export default function IngestionStatus({ ingestion }: Props) {
  if (!ingestion) {
    return (
      <p className="mt-0.5 text-slate-600">
        No reviews have been ingested yet. Start ingestion or import a CSV.
      </p>
    )
  }
  const known = STATES[ingestion.status]
  const text = details(ingestion)
  return (
    <div
      data-status={ingestion.status}
      className={`mt-1 rounded-lg border px-4 py-3 leading-6 ${known?.tone ?? UNKNOWN_TONE}`}
    >
      <p className="font-semibold">{known?.label ?? `Last ingestion: ${ingestion.status}`}</p>
      {text && <p>{text}</p>}
      {completedAt(ingestion.completed_at)}
    </div>
  )
}
