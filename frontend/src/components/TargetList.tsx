import { useEffect, useState } from 'react'
import { listTargets, PLATFORM, TargetError } from '../api/targets'
import type { AnalysisTarget } from '../api/targets'
import { targetPath } from '../hooks/usePath'

type Props = { accessToken: string; refreshKey?: number; onOpen?: (id: string) => void }
type Result = { key: string; targets: AnalysisTarget[]; error: string }

export default function TargetList({ accessToken, refreshKey = 0, onOpen }: Props) {
  const [attempt, setAttempt] = useState(0)
  const [result, setResult] = useState<Result | null>(null)
  const requestKey = `${refreshKey}:${attempt}`

  useEffect(() => {
    let cancelled = false
    listTargets(accessToken)
      .then((targets) => {
        if (!cancelled) setResult({ key: requestKey, targets, error: '' })
      })
      .catch((e: unknown) => {
        if (cancelled) return
        const error =
          e instanceof TargetError
            ? e.message
            : 'Unable to load your targets right now. Please try again.'
        setResult({ key: requestKey, targets: [], error })
      })
    return () => {
      cancelled = true
    }
  }, [accessToken, requestKey])

  const loading = result === null || result.key !== requestKey

  return (
    <section aria-labelledby="targets-heading" className="mt-8">
      <h3 id="targets-heading" className="mb-4 text-lg font-semibold text-slate-900">
        Your analysis targets
      </h3>
      {loading ? (
        <p role="status" className="text-sm text-slate-500">
          Loading your targets...
        </p>
      ) : result.error ? (
        <div
          role="alert"
          className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm leading-6 text-red-800"
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
      ) : result.targets.length === 0 ? (
        <p className="text-sm text-slate-500">
          You don&apos;t have any analysis targets yet. Create one below.
        </p>
      ) : (
        <ul className="divide-y divide-slate-100 rounded-lg border border-slate-200">
          {result.targets.map((target) => (
            <li key={target.id}>
              <a
                href={targetPath(target.id)}
                className="block px-4 py-3 transition hover:bg-slate-50 focus:bg-slate-50 focus:outline-none"
                onClick={(event) => {
                  // Let modified clicks (new tab, etc.) use the real link.
                  if (!onOpen || event.button !== 0 || event.metaKey || event.ctrlKey) return
                  if (event.shiftKey || event.altKey) return
                  event.preventDefault()
                  onOpen(target.id)
                }}
              >
                <p className="font-medium text-indigo-700">{target.name}</p>
                <p className="mt-0.5 text-sm text-slate-600">
                  {target.platform === PLATFORM.id ? PLATFORM.label : target.platform}
                </p>
                <p className="mt-0.5 truncate text-sm text-slate-500" title={target.source_url}>
                  {target.source_url}
                </p>
              </a>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
