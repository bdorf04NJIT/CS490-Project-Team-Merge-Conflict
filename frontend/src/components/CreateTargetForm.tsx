import { useState } from 'react'
import type { FormEvent } from 'react'
import { createTarget, PLATFORM, TargetError } from '../api/targets'
import type { AnalysisTarget, FieldErrors } from '../api/targets'

type Props = { accessToken: string; onCreated?: () => void; onOpen?: (id: string) => void }

const inputBase =
  'w-full rounded-lg border bg-white px-3.5 py-3 text-base text-slate-900 shadow-xs outline-none transition placeholder:text-slate-400 focus:ring-3'
const inputOk = 'border-slate-300 focus:border-indigo-500 focus:ring-indigo-500/15'
const inputBad = 'border-red-400 focus:border-red-500 focus:ring-red-500/15'

const REQUIRED: FieldErrors = {
  name: 'Enter the business or place name.',
  source_url: 'Enter the Google Maps URL for this place.',
}

function FieldMessage({ id, message }: { id: string; message?: string }) {
  return message ? (
    <p id={id} className="mt-1.5 text-sm text-red-700">
      {message}
    </p>
  ) : null
}

export default function CreateTargetForm({ accessToken, onCreated, onOpen }: Props) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({})
  const [created, setCreated] = useState<AnalysisTarget | null>(null)

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const values = new FormData(event.currentTarget)
    const name = String(values.get('name') ?? '').trim()
    const sourceUrl = String(values.get('source_url') ?? '').trim()
    setError('')

    const missing: FieldErrors = {}
    if (!name) missing.name = REQUIRED.name
    if (!sourceUrl) missing.source_url = REQUIRED.source_url
    setFieldErrors(missing)
    if (Object.keys(missing).length) return

    setBusy(true)
    try {
      const target = await createTarget(accessToken, { name, sourceUrl })
      setCreated(target)
      onCreated?.()
    } catch (e) {
      if (e instanceof TargetError) {
        setFieldErrors(e.fields)
        const onlyFieldProblems =
          e.status === 400 && (e.fields.name || e.fields.source_url) && !e.fields.platform
        if (!onlyFieldProblems) setError(e.fields.platform ?? e.message)
      } else {
        setError('Unable to create the target right now. Please try again.')
      }
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
        <div className="mt-4 flex flex-wrap gap-x-5 gap-y-2">
          {onOpen && (
            <button
              className="text-sm font-medium text-indigo-600 hover:underline"
              type="button"
              onClick={() => onOpen(created.id)}
            >
              Open workspace
            </button>
          )}
          <button
            className="text-sm font-medium text-indigo-600 hover:underline"
            type="button"
            onClick={() => setCreated(null)}
          >
            Create another target
          </button>
        </div>
      </section>
    )
  }

  return (
    <form
      aria-labelledby="create-heading"
      className="mt-8 flex flex-col"
      noValidate
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
        className={`${inputBase} ${fieldErrors.name ? inputBad : inputOk}`}
        id="target-name"
        name="name"
        maxLength={255}
        placeholder="Joe's Coffee"
        aria-invalid={Boolean(fieldErrors.name)}
        aria-describedby={fieldErrors.name ? 'target-name-error' : undefined}
      />
      <FieldMessage id="target-name-error" message={fieldErrors.name} />

      <label className="mt-5 mb-2 text-sm font-medium text-slate-700" htmlFor="target-url">
        Google Maps URL
      </label>
      <input
        className={`${inputBase} ${fieldErrors.source_url ? inputBad : inputOk}`}
        id="target-url"
        name="source_url"
        type="url"
        maxLength={2048}
        placeholder="https://www.google.com/maps/place/..."
        aria-invalid={Boolean(fieldErrors.source_url)}
        aria-describedby={fieldErrors.source_url ? 'target-url-error' : undefined}
      />
      <FieldMessage id="target-url-error" message={fieldErrors.source_url} />

      <p className="mt-5 mb-5 text-sm text-slate-500">
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
