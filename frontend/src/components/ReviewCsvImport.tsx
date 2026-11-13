import { useState } from 'react'
import type { FormEvent } from 'react'
import { skippedSentence } from '../lib/skipReasons'

// onFinished runs after any attempt the server answered, so the workspace can reload the
// persisted ingestion status (failed imports are recorded as failed runs too).
type Props = { accessToken: string; targetId: string; onFinished: () => void }
type ImportRun = {
  status: string
  imported_count: number
  skipped_count: number
  skip_reasons?: Record<string, number>
}

export default function ReviewCsvImport({ accessToken, targetId, onFinished }: Props) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [summary, setSummary] = useState('')
  const [partial, setPartial] = useState(false)

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = event.currentTarget
    const input = form.elements.namedItem('file') as HTMLInputElement | null
    const file = input?.files?.[0]
    setError('')
    setSummary('')
    if (!file) {
      setError('Choose a genuine Google Maps review CSV file first.')
      return
    }
    if (file.size > 2 * 1024 * 1024) {
      setError('Choose a CSV file smaller than 2 MB.')
      return
    }
    const payload = new FormData()
    payload.append('file', file)
    setBusy(true)
    try {
      const response = await fetch(
        `/api/targets/${encodeURIComponent(targetId)}/ingestions/import`,
        {
          method: 'POST',
          headers: { Authorization: `Bearer ${accessToken}` },
          body: payload,
        },
      )
      if (!response.ok) {
        setError(
          response.status === 401
            ? 'Your session expired. Please sign in again.'
            : response.status === 404
              ? 'This target does not exist or you do not have access.'
              : response.status === 422
                ? 'The CSV did not contain usable reviews. Check its columns, review text, and ratings.'
                : 'Unable to import reviews right now. Please try again.',
        )
        if (response.status !== 401) onFinished()
        return
      }
      const data: { run: ImportRun } = await response.json()
      setPartial(data.run.status === 'partial')
      const skipped = skippedSentence(data.run.skipped_count, data.run.skip_reasons)
      setSummary(`Imported ${data.run.imported_count} reviews.${skipped ? ` ${skipped}` : ''}`)
      form.reset()
      onFinished()
    } catch {
      setError('Unable to connect to the review import service.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <section
      aria-label="Import supplied review data"
      className="mt-6 border-t border-slate-200 pt-5"
    >
      <h4 className="font-semibold text-slate-900">Or import supplied Google Maps reviews</h4>
      <p className="mt-1 text-sm text-slate-600">
        Upload a genuine UTF-8 CSV export with review_text and rating columns. Only data you provide
        will be imported.
      </p>
      <form className="mt-3" onSubmit={(event) => void submit(event)}>
        <label htmlFor="review-csv" className="block text-sm font-medium text-slate-700">
          Review CSV (max 2 MB)
        </label>
        <input
          id="review-csv"
          name="file"
          type="file"
          accept=".csv,text/csv"
          className="mt-2 block w-full text-sm text-slate-600"
          disabled={busy}
        />
        <button
          type="submit"
          disabled={busy}
          className="mt-3 w-full rounded-lg bg-indigo-600 px-4 py-3 text-sm font-semibold text-white disabled:opacity-60"
        >
          {busy ? 'Importing...' : 'Import CSV reviews'}
        </button>
      </form>
      {summary && (
        <p
          role="status"
          className={`mt-3 text-sm ${partial ? 'text-amber-900' : 'text-green-800'}`}
        >
          {summary}
        </p>
      )}
      {error && (
        <p role="alert" className="mt-3 text-sm text-red-800">
          {error}
        </p>
      )}
    </section>
  )
}
