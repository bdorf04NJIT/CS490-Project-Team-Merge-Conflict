import { useEffect, useState } from 'react'
import { getTarget, PLATFORM, TargetError } from '../api/targets'
import type { TargetWorkspace as Workspace } from '../api/targets'

type Props = { accessToken: string; targetId: string; onBack: () => void }
type Result = { key: string; target: Workspace | null; error: string }

const STATUS_LABELS: Record<string, string> = {
  processing: 'Ingestion in progress',
  succeeded: 'Last ingestion succeeded',
  failed: 'Last ingestion failed',
}

export default function TargetWorkspace({ accessToken, targetId, onBack }: Props) {
  const [attempt, setAttempt] = useState(0)
  const [result, setResult] = useState<Result | null>(null)
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
      <dl className="mt-4 space-y-3 rounded-lg border border-slate-200 p-4 text-sm">
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
          Import reviews from this target&apos;s {PLATFORM.label} source. Starting ingestion is not
          available yet.
        </p>
        <button
          type="button"
          className="mt-3 w-full rounded-lg bg-indigo-600 px-4 py-3 text-sm font-semibold text-white shadow-xs transition hover:bg-indigo-700 disabled:opacity-60"
          aria-describedby="ingest-help"
          disabled
        >
          Start ingestion
        </button>
      </section>
    </section>
  )
}
