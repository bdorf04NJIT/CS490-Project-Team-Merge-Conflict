import { useEffect, useState } from 'react'
import { getReviewSummary, STAR_VALUES, TargetError } from '../api/targets'
import type { ReviewSummary as Summary } from '../api/targets'

type Props = { accessToken: string; targetId: string; refreshKey: number }
type Result = { key: string; summary: Summary | null; error: string }

const averageFormat = new Intl.NumberFormat('en-US', {
  minimumFractionDigits: 1,
  maximumFractionDigits: 2,
})

function plural(count: number, word: string) {
  return `${count} ${word}${count === 1 ? '' : 's'}`
}

// Every value shown here comes from the backend summary, which is computed from the
// persisted reviews. Nothing is recalculated from the (possibly truncated) review list.
export default function ReviewSummary({ accessToken, targetId, refreshKey }: Props) {
  const [result, setResult] = useState<Result | null>(null)
  const [retry, setRetry] = useState(0)
  const requestKey = `${targetId}:${refreshKey}:${retry}`

  useEffect(() => {
    let cancelled = false
    getReviewSummary(accessToken, targetId)
      .then((summary) => {
        if (!cancelled) setResult({ key: requestKey, summary, error: '' })
      })
      .catch((e: unknown) => {
        if (cancelled) return
        const error =
          e instanceof TargetError ? e.message : 'Unable to load the review summary right now.'
        setResult({ key: requestKey, summary: null, error })
      })
    return () => {
      cancelled = true
    }
  }, [accessToken, targetId, requestKey])

  const heading = (
    <h4 id="summary-heading" className="font-semibold text-slate-900">
      Review summary
    </h4>
  )

  if (result === null || result.key !== requestKey) {
    return (
      <section aria-labelledby="summary-heading" className="mt-6">
        {heading}
        <p role="status" className="mt-1 text-sm text-slate-500">
          Loading review summary...
        </p>
      </section>
    )
  }

  if (!result.summary) {
    return (
      <section aria-labelledby="summary-heading" className="mt-6">
        {heading}
        <div
          role="alert"
          className="mt-2 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm leading-6 text-red-800"
        >
          <p>{result.error}</p>
          <button
            type="button"
            className="mt-2 font-medium text-indigo-600 hover:underline"
            onClick={() => setRetry((n) => n + 1)}
          >
            Try again
          </button>
        </div>
      </section>
    )
  }

  const { review_count: count, average_rating: average, rating_distribution } = result.summary

  if (count === 0) {
    return (
      <section aria-labelledby="summary-heading" className="mt-6">
        {heading}
        <p className="mt-1 text-sm text-slate-500">
          No reviews yet. Start ingestion or import a CSV.
        </p>
      </section>
    )
  }

  return (
    <section aria-labelledby="summary-heading" className="mt-6">
      {heading}
      <div className="mt-3 rounded-lg border border-slate-200 p-4 text-sm">
        <dl className="grid grid-cols-2 gap-4">
          <div>
            <dt className="font-medium text-slate-700">Reviews ingested</dt>
            <dd className="mt-0.5 text-2xl font-semibold text-slate-900">{count}</dd>
          </div>
          <div>
            <dt className="font-medium text-slate-700">Average rating</dt>
            <dd className="mt-0.5 text-slate-600">
              <span className="text-2xl font-semibold text-slate-900">
                {average === null ? '—' : averageFormat.format(average)}
              </span>{' '}
              out of 5
            </dd>
          </div>
        </dl>
        <h5 id="distribution-heading" className="mt-4 font-medium text-slate-700">
          Rating distribution
        </h5>
        <ul aria-labelledby="distribution-heading" className="mt-2 space-y-1.5">
          {STAR_VALUES.map((star) => {
            const starCount = rating_distribution[star]
            const percent = Math.round((starCount / count) * 100)
            return (
              <li
                key={star}
                aria-label={`${plural(Number(star), 'star')}: ${plural(starCount, 'review')}`}
                className="flex items-center gap-3"
              >
                <span className="w-12 shrink-0 text-slate-600">{star} ★</span>
                <span aria-hidden="true" className="h-2 flex-1 rounded-full bg-slate-100">
                  <span
                    className="block h-2 rounded-full bg-amber-400"
                    style={{ width: `${percent}%` }}
                  />
                </span>
                <span className="w-10 shrink-0 text-right text-slate-600">{starCount}</span>
              </li>
            )
          })}
        </ul>
      </div>
    </section>
  )
}
