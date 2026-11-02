import { useState } from 'react'
import type { FormEvent } from 'react'
import { createTarget, PLATFORM, TargetError } from '../api/targets'
import type { AnalysisTarget } from '../api/targets'

type Props = { accessToken: string; onCreated?: () => void }

const inputClass =
  'mb-5 w-full rounded-lg border border-slate-300 bg-white px-3.5 py-3 text-base text-slate-900 shadow-xs outline-none transition placeholder:text-slate-400 focus:border-indigo-500 focus:ring-3 focus:ring-indigo-500/15'

export default function CreateTargetForm({ accessToken, onCreated }: Props) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [created, setCreated] = useState<AnalysisTarget | null>(null)

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const values = new FormData(event.currentTarget)
    setBusy(true)
    setError('')
    try {
      const target = await createTarget(accessToken, {
        name: String(values.get('name')).trim(),
        sourceUrl: String(values.get('source_url')).trim(),
      })
      setCreated(target)
      onCreated?.()
    } catch (e) {
      setError(
        e instanceof TargetError
          ? e.message
          : 'Unable to create the target right now. Please try again.',
      )
    } finally {
      setBusy(false)
    }
  }

  if (created) {
    return (
      <section
        aria-labelledby="created-heading"
        className="mt-8 rounded-lg border border-emerald-200 bg-emerald-50 p-4"
      >
        <h3 id="created-heading" role="status" className="font-semibold text-emerald-900">
          Analysis target created
        </h3>
        <dl className="mt-3 space-y-1 text-sm text-emerald-950">
          <div>
            <dt className="inline font-medium">Name: </dt>
            <dd className="inline">{created.name}</dd>
          </div>
          <div>
            <dt className="inline font-medium">Platform: </dt>
            <dd className="inline">{PLATFORM.label}</dd>
          </div>
          <div>
            <dt className="inline font-medium">Source: </dt>
            <dd className="inline break-all">{created.source_url}</dd>
          </div>
        </dl>
        <button
          className="mt-4 text-sm font-medium text-indigo-600 hover:underline"
          type="button"
          onClick={() => setCreated(null)}
        >
          Create another target
        </button>
      </section>
    )
  }

  return (
    <form
      aria-labelledby="create-heading"
      className="mt-8 flex flex-col"
      onSubmit={(event) => void submit(event)}
    >
      <h3 id="create-heading" className="mb-4 text-lg font-semibold text-slate-900">
        New analysis target
      </h3>
      {error && (
        <p
          role="alert"
          className="mb-5 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm leading-6 text-red-800"
        >
          {error}
        </p>
      )}
      <label className="mb-2 text-sm font-medium text-slate-700" htmlFor="target-name">
        Business or place name
      </label>
      <input
        className={inputClass}
        id="target-name"
        name="name"
        maxLength={255}
        placeholder="Joe's Coffee"
        required
      />
      <label className="mb-2 text-sm font-medium text-slate-700" htmlFor="target-url">
        Google Maps URL
      </label>
      <input
        className={inputClass}
        id="target-url"
        name="source_url"
        type="url"
        maxLength={2048}
        placeholder="https://www.google.com/maps/place/..."
        required
      />
      <p className="mb-5 text-sm text-slate-500">
        Review platform: <span className="font-medium text-slate-700">{PLATFORM.label}</span>
      </p>
      <button
        className="w-full rounded-lg bg-indigo-600 px-4 py-3 text-sm font-semibold text-white shadow-xs transition hover:bg-indigo-700 disabled:opacity-60"
        type="submit"
        disabled={busy}
      >
        {busy ? 'Creating...' : 'Create target'}
      </button>
    </form>
  )
}
