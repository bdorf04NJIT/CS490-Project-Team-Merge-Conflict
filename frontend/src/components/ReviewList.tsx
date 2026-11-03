import { useEffect, useState } from 'react'
import { listReviews, TargetError } from '../api/targets'
import type { Review } from '../api/targets'

type Props = { accessToken: string; targetId: string; refreshKey: number }
type Result = { key: string; reviews: Review[]; error: string }

const PREVIEW = 5
// The backend returns at most 100 reviews per request.
const PAGE_LIMIT = 100

function Stars({ rating }: { rating: number }) {
  const filled = Math.max(0, Math.min(5, Math.round(rating)))
  return (
    <span role="img" aria-label={`${rating} out of 5 stars`} className="text-amber-500">
      {'★'.repeat(filled)}
      <span className="text-slate-300">{'★'.repeat(5 - filled)}</span>
    </span>
  )
}

export default function ReviewList({ accessToken, targetId, refreshKey }: Props) {
  const [result, setResult] = useState<Result | null>(null)
  const [showAll, setShowAll] = useState(false)
  const requestKey = `${targetId}:${refreshKey}`

  useEffect(() => {
    let cancelled = false
    listReviews(accessToken, targetId)
      .then((reviews) => {
        if (!cancelled) setResult({ key: requestKey, reviews, error: '' })
      })
      .catch((e: unknown) => {
        if (cancelled) return
        const error = e instanceof TargetError ? e.message : 'Unable to load reviews right now.'
        setResult({ key: requestKey, reviews: [], error })
      })
    return () => {
      cancelled = true
    }
  }, [accessToken, targetId, requestKey])

  if (result === null || result.key !== requestKey) {
    return (
      <p role="status" className="mt-6 text-sm text-slate-500">
        Loading reviews...
      </p>
    )
  }
  if (result.error) {
    return (
      <p role="alert" className="mt-6 text-sm text-red-700">
        {result.error}
      </p>
    )
  }

  const { reviews } = result
  const count = reviews.length >= PAGE_LIMIT ? `${PAGE_LIMIT}+` : String(reviews.length)
  const shown = showAll ? reviews : reviews.slice(0, PREVIEW)

  return (
    <section aria-labelledby="reviews-heading" className="mt-6">
      <h4 id="reviews-heading" className="font-semibold text-slate-900">
        Saved reviews ({count})
      </h4>
      {reviews.length === 0 ? (
        <p className="mt-1 text-sm text-slate-500">No reviews have been saved yet.</p>
      ) : (
        <>
          <ul className="mt-3 space-y-3">
            {shown.map((review) => (
              <li key={review.id} className="rounded-lg border border-slate-200 p-3 text-sm">
                <div className="flex flex-wrap items-center gap-x-2 text-xs text-slate-500">
                  <Stars rating={review.rating} />
                  {review.reviewer_name && <span>{review.reviewer_name}</span>}
                  {review.review_date && <span>{review.review_date.slice(0, 10)}</span>}
                </div>
                <p className="mt-1 break-words text-slate-700">{review.text}</p>
              </li>
            ))}
          </ul>
          {reviews.length > PREVIEW && (
            <button
              type="button"
              className="mt-2 text-sm font-medium text-indigo-600 hover:underline"
              onClick={() => setShowAll((value) => !value)}
            >
              {showAll ? 'Show fewer' : `Show all ${count}`}
            </button>
          )}
        </>
      )}
    </section>
  )
}
