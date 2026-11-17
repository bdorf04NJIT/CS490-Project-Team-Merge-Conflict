import { useEffect, useState } from 'react'
import { getReviewSummary, TargetError } from '../api/targets'
import ReviewQa from './ReviewQa'

type Props = {
  accessToken: string
  targetId: string
  targetName: string
  refreshKey: number
  latestIngestionStatus?: string
}
type Result = { key: string; count: number | null; error: string }

/**
 * S2-020: a recorded ingestion run is not proof that usable reviews exist.
 * Only the owner-scoped, persisted review count enables the Q&A interaction.
 * The Flask Q&A endpoint independently refuses empty datasets before calling Gemini.
 */
export default function ReviewQaGate({
  accessToken,
  targetId,
  targetName,
  refreshKey,
  latestIngestionStatus,
}: Props) {
  const [result, setResult] = useState<Result | null>(null)
  const [retry, setRetry] = useState(0)
  const requestKey = JSON.stringify([accessToken, targetId, refreshKey, retry])

  useEffect(() => {
    let cancelled = false
    getReviewSummary(accessToken, targetId)
      .then((summary) => {
        if (!cancelled) setResult({ key: requestKey, count: summary.review_count, error: '' })
      })
      .catch((reason: unknown) => {
        if (cancelled) return
        setResult({
          key: requestKey,
          count: null,
          error:
            reason instanceof TargetError
              ? reason.message
              : 'Unable to verify saved review availability.',
        })
      })
    return () => {
      cancelled = true
    }
  }, [accessToken, targetId, requestKey])

  if (result === null || result.key !== requestKey) {
    return (
      <p role="status" className="text-sm text-slate-600">
        Checking saved reviews for {targetName}...
      </p>
    )
  }
  if (result.error) {
    return (
      <section aria-label="Review Q&A availability">
        <p role="alert" className="text-sm text-red-700">
          {result.error}
        </p>
        <button
          type="button"
          onClick={() => setRetry((value) => value + 1)}
          className="mt-2 text-sm font-medium text-indigo-600 hover:underline"
        >
          Retry review check
        </button>
      </section>
    )
  }
  if (result.count === 0) {
    return (
      <section aria-label="Review Q&A unavailable" role="status" className="text-sm text-slate-700">
        <h4 className="font-semibold text-slate-900">Ask about these reviews</h4>
        <p className="mt-2">
          {latestIngestionStatus === 'failed'
            ? 'The latest ingestion failed, and this target has no saved reviews.'
            : 'This target has no saved reviews yet.'}{' '}
          Complete ingestion before asking ReviewLens questions.
        </p>
      </section>
    )
  }
  return (
    <ReviewQa
      key={JSON.stringify([accessToken, targetId])}
      accessToken={accessToken}
      targetId={targetId}
      targetName={targetName}
    />
  )
}
