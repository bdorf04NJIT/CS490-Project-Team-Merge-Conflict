import { useState } from 'react'
import type { FormEvent } from 'react'
import { askQuestion, TargetError } from '../api/targets'
import type { QaAnswer } from '../api/targets'

type Props = { accessToken: string; targetId: string; targetName?: string }

// S2-011: say how many reviews support the answer out of how many were read, so
// "2 reviews" isn't mistaken for "only 2 reviews were looked at".
function evidenceLine({ review_ids, reviews_considered }: QaAnswer): string {
  const cited = review_ids.length
  if (reviews_considered === undefined || reviews_considered < cited) {
    return `Based on ${cited} ${cited === 1 ? 'review' : 'reviews'}.`
  }
  return `${cited} of ${reviews_considered} ${reviews_considered === 1 ? 'review' : 'reviews'} ${cited === 1 ? 'mentions' : 'mention'} this.`
}

// S2-009: a minimal question-and-answer interaction for the active AnalysisTarget.
// No persistent chat history is required; we keep only the latest answer. The active
// target stays clear because this lives inside the target workspace, which already
// displays the target name and platform above it.
export default function ReviewQa({ accessToken, targetId, targetName }: Props) {
  const [question, setQuestion] = useState('')
  const [asking, setAsking] = useState(false)
  const [answer, setAnswer] = useState<QaAnswer | null>(null)
  const [error, setError] = useState('')

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const trimmed = question.trim()
    if (!trimmed || asking) return
    // Drop any prior answer or error so the processing state is unambiguous.
    setError('')
    setAnswer(null)
    setAsking(true)
    try {
      const result = await askQuestion(accessToken, targetId, trimmed)
      setAnswer(result)
    } catch (e: unknown) {
      setError(
        e instanceof TargetError ? e.message : 'Unable to answer that right now. Please try again.',
      )
    } finally {
      setAsking(false)
    }
  }

  return (
    <section aria-labelledby="qa-heading" className="mt-6 border-t border-slate-200 pt-5">
      <h4 id="qa-heading" className="font-semibold text-slate-900">
        Ask about these reviews
      </h4>
      <p id="qa-help" className="mt-1 text-sm text-slate-600">
        Ask a natural-language question. ReviewLens answers only from the reviews ingested for{' '}
        {targetName ? (
          <span className="font-medium text-slate-900">{targetName}</span>
        ) : (
          'this target'
        )}
        .
      </p>
      <form className="mt-3" onSubmit={(event) => void submit(event)}>
        <label htmlFor="qa-question" className="block text-sm font-medium text-slate-700">
          Your question
        </label>
        <textarea
          id="qa-question"
          name="question"
          rows={3}
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
          disabled={asking}
          aria-describedby="qa-help"
          placeholder="e.g. What complaints appear most frequently?"
          className="mt-2 block w-full resize-y rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-900 placeholder:text-slate-400 focus:border-indigo-500 focus:ring-2 focus:ring-indigo-200 focus:outline-none disabled:opacity-60"
        />
        <button
          type="submit"
          disabled={asking || question.trim() === ''}
          className="mt-3 w-full rounded-lg bg-indigo-600 px-4 py-3 text-sm font-semibold text-white shadow-xs transition hover:bg-indigo-700 disabled:opacity-60"
        >
          {asking ? 'Asking ReviewLens...' : 'Ask'}
        </button>
      </form>

      {asking && (
        <p role="status" className="mt-3 text-sm text-slate-500">
          ReviewLens is reading the reviews...
        </p>
      )}

      {!asking && answer && (
        <div
          aria-labelledby="qa-answer-heading"
          className="mt-4 rounded-lg border border-slate-200 p-4 text-sm"
        >
          <h5 id="qa-answer-heading" className="font-medium text-slate-700">
            ReviewLens answer
          </h5>
          <p role="status" className="mt-2 leading-6 whitespace-pre-wrap text-slate-900">
            {answer.answer}
          </p>
          {answer.status === 'answered' && answer.review_ids.length > 0 && (
            <p className="mt-3 text-xs text-slate-500">{evidenceLine(answer)}</p>
          )}
        </div>
      )}

      {!asking && error && (
        <p
          role="alert"
          className="mt-3 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm leading-6 text-red-800"
        >
          {error}
        </p>
      )}
    </section>
  )
}
