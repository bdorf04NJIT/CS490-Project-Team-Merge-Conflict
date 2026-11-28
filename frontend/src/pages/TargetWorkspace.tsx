import { useEffect, useRef, useState } from 'react'
import IngestionStatus from '../components/IngestionStatus'
import ReviewList from '../components/ReviewList'
import ReviewQaGate from '../components/ReviewQaGate'
import ReviewSummary from '../components/ReviewSummary'
import RenameAnalysis from '../components/RenameAnalysis'
import SaveAsAnalysis from '../components/SaveAsAnalysis'
import TargetSwitcher from '../components/TargetSwitcher'
import { getTarget, PLATFORM, startIngestion, TargetError } from '../api/targets'
import type { AnalysisTarget, IngestionRequest, TargetWorkspace as Workspace } from '../api/targets'
import { skippedSentence } from '../lib/skipReasons'

function plural(count: number, word: string) {
  return `${count} ${word}${count === 1 ? '' : 's'}`
}

// S3-009: a refresh merges into the existing dataset, so say what was new, what was
// already there, and how big the current dataset is now.
function refreshMessage(response: IngestionRequest) {
  const added = response.imported_count ?? 0
  const already = response.already_saved_count ?? 0
  return [
    added === 0
      ? 'Refresh complete. No new reviews found.'
      : `Refresh complete. Added ${plural(added, 'new review')}.`,
    already > 0
      ? `${plural(already, 'review')} ${already === 1 ? 'was' : 'were'} already saved.`
      : '',
    skippedSentence(response.skipped_count ?? 0, response.skip_reasons),
    response.review_count != null
      ? `Current dataset: ${plural(response.review_count, 'review')}.`
      : '',
  ]
    .filter(Boolean)
    .join(' ')
}

type Props = {
  accessToken: string
  targetId: string
  onBack: () => void
  // S2-017: when provided, the header offers a switcher between the user's own targets.
  onSwitch?: (id: string) => void
  // S3-002: called after a successful rename, so the parent can refresh its analysis list.
  onRenamed?: () => void
  // S3-003: called with the new analysis after Save As, so the parent can refresh the
  // list and open the copy.
  onSaveAs?: (id: string) => void
}
type Result = { key: string; targetId: string; target: Workspace | null; error: string }
type Ingest = {
  targetId: string
  state: 'submitting' | 'accepted' | 'partial' | 'error'
  message: string
}

export default function TargetWorkspace({
  accessToken,
  targetId,
  onBack,
  onSwitch,
  onRenamed,
  onSaveAs,
}: Props) {
  const [attempt, setAttempt] = useState(0)
  const [result, setResult] = useState<Result | null>(null)
  const [ingest, setIngest] = useState<Ingest | null>(null)
  const headingRef = useRef<HTMLHeadingElement>(null)
  const requestKey = `${targetId}:${attempt}`

  // When a target finishes loading (on open or after a switch), name it in the browser
  // tab and move focus to its heading, per docs/ui-ux-context.md. Keyed on the loaded
  // target id, so refreshing the same target (e.g. after ingestion) doesn't steal focus.
  const loadedId = result?.target?.id ?? null
  const loadedName = result?.target?.name ?? null
  useEffect(() => {
    if (!loadedId || !loadedName) return
    document.title = `${loadedName} | ReviewLens AI`
    headingRef.current?.focus()
  }, [loadedId, loadedName])

  useEffect(() => {
    let cancelled = false
    getTarget(accessToken, targetId)
      .then((target) => {
        if (!cancelled) setResult({ key: requestKey, targetId, target, error: '' })
      })
      .catch((e: unknown) => {
        if (cancelled) return
        const error = e instanceof TargetError ? e.message : 'Unable to open this target right now.'
        // Keep no target data around after a failure, so a denied id shows nothing.
        setResult({ key: requestKey, targetId, target: null, error })
      })
    return () => {
      cancelled = true
    }
  }, [accessToken, targetId, requestKey])

  // While refreshing an already-open workspace (for example after an ingestion
  // attempt), keep showing it so panel feedback isn't wiped by a loading screen.
  const stale = result !== null && result.key !== requestKey
  const loading =
    result === null || result.targetId !== targetId || (stale && result.target === null)
  // Ignore ingestion feedback left over from a different target.
  const ingestRequest = ingest?.targetId === targetId ? ingest : null
  const submitting = ingestRequest?.state === 'submitting'

  // `existingReviews` is the current dataset size when the user clicked; above 0 this is
  // a refresh (S3-009) of an analysis that already has reviews.
  async function handleStartIngestion(existingReviews: number) {
    if (submitting) return
    const isRefresh = existingReviews > 0
    setIngest({ targetId, state: 'submitting', message: '' })
    try {
      const response = await startIngestion(accessToken, targetId)
      setIngest({
        targetId,
        state: response.run_status === 'partial' ? 'partial' : 'accepted',
        message: !response.run_status
          ? 'Ingestion started for this target.'
          : isRefresh
            ? refreshMessage(response)
            : [
                `Imported ${response.imported_count} reviews.`,
                skippedSentence(response.skipped_count, response.skip_reasons),
              ]
                .filter(Boolean)
                .join(' '),
      })
      if (response.run_status) setAttempt((n) => n + 1)
    } catch (e: unknown) {
      const base =
        e instanceof TargetError
          ? e.message
          : 'Unable to start ingestion right now. Please try again.'
      // A failed refresh saves nothing, so the existing dataset is still the current one.
      const message = isRefresh
        ? `${base} Your current ${plural(existingReviews, 'review')} are unchanged.`
        : base
      setIngest({ targetId, state: 'error', message })
      // The server records a failed run for refused attempts, so reload the persisted
      // status. Skip it when the request never arrived or the session has expired.
      if (e instanceof TargetError && e.status !== 0 && e.status !== 401) {
        setAttempt((n) => n + 1)
      }
    }
  }
  function handleRenamed(updated: AnalysisTarget) {
    // Update only the visible name in place; the source, review dataset, and Q&A
    // are unchanged by a rename (S3-002), so there is no need to reload them.
    setResult((prev) =>
      prev && prev.target && prev.target.id === updated.id
        ? { ...prev, target: { ...prev.target, name: updated.name } }
        : prev,
    )
    onRenamed?.()
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
  const reviewCount = target.review_count ?? 0
  const isRefresh = reviewCount > 0

  return (
    <section aria-labelledby="workspace-heading" className="mt-8">
      <div className="flex flex-wrap items-center justify-between gap-3">
        {backLink}
        {onSwitch && (
          <TargetSwitcher accessToken={accessToken} activeId={targetId} onSwitch={onSwitch} />
        )}
      </div>
      <p className="mt-4 text-xs font-semibold tracking-wide text-indigo-600 uppercase">
        Analysis target workspace
      </p>
      <div className="mt-1 flex flex-wrap items-start justify-between gap-3">
        <h3
          id="workspace-heading"
          ref={headingRef}
          tabIndex={-1}
          className="text-lg font-semibold break-words text-slate-900 focus:outline-none"
        >
          {target.name}
        </h3>
        {/* Analysis actions. More actions (Save As, Delete, Export) can be added here. */}
        <div className="flex flex-wrap items-center gap-2" aria-label="Analysis actions">
          <RenameAnalysis
            accessToken={accessToken}
            targetId={targetId}
            currentName={target.name}
            onRenamed={handleRenamed}
          />
          <SaveAsAnalysis
            accessToken={accessToken}
            targetId={targetId}
            sourceName={target.name}
            onSaved={(copy) => onSaveAs?.(copy.id)}
          />
        </div>
      </div>
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
              <dd>
                <IngestionStatus ingestion={ingestion} />
              </dd>
            </div>
          </dl>

          <section aria-labelledby="ingest-heading" className="mt-6">
            <h4 id="ingest-heading" className="font-semibold text-slate-900">
              {isRefresh ? 'Refresh reviews' : 'Ingest reviews'}
            </h4>
            <p id="ingest-help" className="mt-1 text-sm text-slate-500">
              {isRefresh
                ? `Fetch the latest reviews from this target's saved ${PLATFORM.label} source. New reviews are added to the ${plural(reviewCount, 'review')} you already have, and none are removed.`
                : `Import reviews from this target's saved ${PLATFORM.label} source.`}
            </p>
            <button
              type="button"
              className="mt-3 w-full rounded-lg bg-indigo-600 px-4 py-3 text-sm font-semibold text-white shadow-xs transition hover:bg-indigo-700 disabled:opacity-60"
              aria-describedby="ingest-help"
              disabled={submitting}
              onClick={() => void handleStartIngestion(reviewCount)}
            >
              {isRefresh
                ? submitting
                  ? 'Refreshing reviews...'
                  : 'Refresh reviews'
                : submitting
                  ? 'Starting ingestion...'
                  : 'Start ingestion'}
            </button>
            {(ingestRequest?.state === 'accepted' || ingestRequest?.state === 'partial') && (
              <p
                role="status"
                className={`mt-3 rounded-lg border px-4 py-3 text-sm ${
                  ingestRequest.state === 'partial'
                    ? 'border-amber-200 bg-amber-50 text-amber-900'
                    : 'border-green-200 bg-green-50 text-green-800'
                }`}
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
          {/* The review summary belongs with the data, so it sits under ingestion. */}
          {ingestion && (
            <ReviewSummary
              accessToken={accessToken}
              targetId={targetId}
              targetName={target.name}
              refreshKey={attempt}
            />
          )}
        </div>

        {/* Right column: asking questions and browsing the review evidence. */}
        <div>
          {ingestion ? (
            <>
              <div className="rounded-xl border border-indigo-100 bg-indigo-50/40 p-5 shadow-xs">
                {/* Keyed by target so a switch always starts with an empty question and answer. */}
                <ReviewQaGate
                  key={targetId}
                  accessToken={accessToken}
                  targetId={targetId}
                  targetName={target.name}
                  refreshKey={attempt}
                  latestIngestionStatus={ingestion.status}
                />
              </div>
              <ReviewList accessToken={accessToken} targetId={targetId} refreshKey={attempt} />
            </>
          ) : (
            <div className="rounded-xl border border-dashed border-slate-300 bg-slate-50 p-6 text-sm text-slate-500">
              <h4 className="font-semibold text-slate-700">Ask about these reviews</h4>
              <p className="mt-1">
                Ingest reviews to start asking ReviewLens questions about this target.
              </p>
            </div>
          )}
        </div>
      </div>
    </section>
  )
}
