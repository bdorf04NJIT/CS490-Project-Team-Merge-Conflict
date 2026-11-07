import { useEffect, useState } from 'react'
import ReviewCsvImport from '../components/ReviewCsvImport'
import ReviewList from '../components/ReviewList'
import ReviewQa from '../components/ReviewQa'
import ReviewSummary from '../components/ReviewSummary'
import { getTarget, PLATFORM, startIngestion, TargetError } from '../api/targets'
import type { TargetWorkspace as Workspace } from '../api/targets'

type Props = { accessToken: string; targetId: string; onBack: () => void }
type Result = { key: string; target: Workspace | null; error: string }
type Ingest = { targetId: string; state: 'submitting' | 'accepted' | 'error'; message: string }

const STATUS_LABELS: Record<string, string> = {
  processing: 'Ingestion in progress',
  succeeded: 'Last ingestion succeeded',
  failed: 'Last ingestion failed',
}

export default function TargetWorkspace({ accessToken, targetId, onBack }: Props) {
  const [attempt, setAttempt] = useState(0)
  const [result, setResult] = useState<Result | null>(null)
  const [ingest, setIngest] = useState<Ingest | null>(null)
  const requestKey = `${targetId}:${attempt}`

  useEffect(() => {
    let cancelled = false
    getTarget(accessToken, targetId)
      .then((target) => {
        if (!cancelled) setResult({ key: requestKey, target, error: '' })
      })
      .catch((e: unknown) => {
        if (cancelled) return
        const error = e instanceof TargetError ? e.message : 'Unable to open this target right now.'
        // Keep no target data around after a failure, so a denied id shows nothing.
        setResult({ key: requestKey, target: null, error })
      })
    return () => {
      cancelled = true
    }
  }, [accessToken, targetId, requestKey])

  const loading = result === null || result.key !== requestKey
  // Ignore ingestion feedback left over from a different target.
  const ingestRequest = ingest?.targetId === targetId ? ingest : null
  const submitting = ingestRequest?.state === 'submitting'

  async function handleStartIngestion() {
    if (submitting) return
    setIngest({ targetId, state: 'submitting', message: '' })
    try {
      const response = await startIngestion(accessToken, targetId)
      setIngest({
        targetId,
        state: 'accepted',
        message: response.run_status
          ? `Imported ${response.imported_count} reviews (${response.skipped_count} skipped).`
          : 'Ingestion started for this target.',
      })
      if (response.run_status) setAttempt((n) => n + 1)
    } catch (e: unknown) {
      const message =
        e instanceof TargetError
          ? e.message
          : 'Unable to start ingestion right now. Please try again.'
      setIngest({ targetId, state: 'error', message })
    }
  }
  const backLink = (
    <button
      type="button"
      className="text-sm font-medium text-indigo-600 hover:underline"
      onClick={onBack}
    >
      &larr; Back to your targets
    </button>
  )

  if (loading) {
    return (
      <section className="mt-8">
        {backLink}
        <p role="status" className="mt-4 text-sm text-slate-500">
          Opening workspace...
        </p>
      </section>
    )
  }

  if (!result.target) {
    return (
      <section className="mt-8">
        {backLink}
        <div
          role="alert"
          className="mt-4 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm leading-6 text-red-800"
        >
          <p>{result.error}</p>
          <button
            type="button"
            className="mt-2 font-medium text-indigo-600 hover:underline"
            onClick={() => setAttempt((n) => n + 1)}
          >
            Try again
          </button>
        </div>
      </section>
    )
  }

  const target = result.target
  const ingestion = target.latest_ingestion

  return (
    <section aria-labelledby="workspace-heading" className="mt-8">
      {backLink}
      <p className="mt-4 text-xs font-semibold tracking-wide text-indigo-600 uppercase">
        Analysis target workspace
      </p>
      <h3 id="workspace-heading" className="mt-1 text-lg font-semibold break-words text-slate-900">
        {target.name}
      </h3>

      <div className="mt-6 grid gap-8 lg:grid-cols-2 lg:gap-10">
        {/* Left column: target details and getting reviews into the workspace. */}
        <div>
          <dl className="space-y-3 rounded-lg border border-slate-200 p-4 text-sm">
            <div>
              <dt className="font-medium text-slate-700">Review platform</dt>
              <dd className="mt-0.5 text-slate-600">
                {target.platform === PLATFORM.id ? PLATFORM.label : target.platform}
              </dd>
            </div>
            <div>
              <dt className="font-medium text-slate-700">Source</dt>
              <dd className="mt-0.5 break-all text-slate-600">
                {/^https?:\/\//i.test(target.source_url) ? (
                  <a
                    className="text-indigo-600 hover:underline"
                    href={target.source_url}
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    {target.source_url}
                  </a>
                ) : (
                  target.source_url
                )}
              </dd>
            </div>
            <div>
              <dt className="font-medium text-slate-700">Ingestion status</dt>
              <dd className="mt-0.5 text-slate-600">
                {ingestion
                  ? (STATUS_LABELS[ingestion.status] ?? ingestion.status)
                  : 'No reviews have been ingested yet.'}
              </dd>
            </div>
          </dl>

          <section aria-labelledby="ingest-heading" className="mt-6">
            <h4 id="ingest-heading" className="font-semibold text-slate-900">
              Ingest reviews
            </h4>
            <p id="ingest-help" className="mt-1 text-sm text-slate-500">
              Import reviews from this target&apos;s saved {PLATFORM.label} source.
            </p>
            <button
              type="button"
              className="mt-3 w-full rounded-lg bg-indigo-600 px-4 py-3 text-sm font-semibold text-white shadow-xs transition hover:bg-indigo-700 disabled:opacity-60"
              aria-describedby="ingest-help"
              disabled={submitting}
              onClick={handleStartIngestion}
            >
              {submitting ? 'Starting ingestion...' : 'Start ingestion'}
            </button>
            {ingestRequest?.state === 'accepted' && (
              <p
                role="status"
                className="mt-3 rounded-lg border border-green-200 bg-green-50 px-4 py-3 text-sm text-green-800"
              >
                {ingestRequest.message}
              </p>
            )}
            {ingestRequest?.state === 'error' && (
              <p
                role="alert"
                className="mt-3 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm leading-6 text-red-800"
              >
                {ingestRequest.message}
              </p>
            )}
          </section>
          <ReviewCsvImport
            accessToken={accessToken}
            targetId={targetId}
            onImported={() => setAttempt((n) => n + 1)}
          />
          {/* The review summary belongs with the data, so it sits under ingestion. */}
          {ingestion && (
            <ReviewSummary accessToken={accessToken} targetId={targetId} refreshKey={attempt} />
          )}
        </div>

        {/* Right column: asking questions and browsing the review evidence. */}
        <div>
          {ingestion ? (
            <>
              <div className="rounded-xl border border-indigo-100 bg-indigo-50/40 p-5 shadow-xs">
                <ReviewQa accessToken={accessToken} targetId={targetId} />
              </div>
              <ReviewList accessToken={accessToken} targetId={targetId} refreshKey={attempt} />
            </>
          ) : (
            <div className="rounded-xl border border-dashed border-slate-300 bg-slate-50 p-6 text-sm text-slate-500">
              <h4 className="font-semibold text-slate-700">Ask about these reviews</h4>
              <p className="mt-1">
                Ingest reviews or import a CSV to start asking ReviewLens questions about this
                target.
              </p>
            </div>
          )}
        </div>
      </div>
    </section>
  )
}
