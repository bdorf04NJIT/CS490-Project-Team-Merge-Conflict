import { useState } from 'react'
import type { FormEvent } from 'react'
import { renameTarget, TargetError } from '../api/targets'
import type { AnalysisTarget } from '../api/targets'

type Props = {
  accessToken: string
  targetId: string
  currentName: string
  // Called with the updated analysis after a successful rename, so the caller can
  // refresh the heading and the analysis list.
  onRenamed: (target: AnalysisTarget) => void
}

const inputBase =
  'w-full rounded-lg border bg-white px-3 py-2 text-sm text-slate-900 shadow-xs outline-none transition placeholder:text-slate-400 focus:ring-3'
const inputOk = 'border-slate-300 focus:border-indigo-500 focus:ring-indigo-500/15'
const inputBad = 'border-red-400 focus:border-red-500 focus:ring-red-500/15'

export default function RenameAnalysis({ accessToken, targetId, currentName, onRenamed }: Props) {
  const [editing, setEditing] = useState(false)
  const [name, setName] = useState(currentName)
  const [busy, setBusy] = useState(false)
  const [fieldError, setFieldError] = useState('')
  const [error, setError] = useState('')

  function open() {
    // Always start from the current name, discarding any abandoned edit.
    setName(currentName)
    setFieldError('')
    setError('')
    setEditing(true)
  }

  function close() {
    setEditing(false)
    setFieldError('')
    setError('')
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const trimmed = name.trim()
    setError('')
    if (!trimmed) {
      setFieldError('Enter a name for this analysis.')
      return
    }
    setFieldError('')
    setBusy(true)
    try {
      const updated = await renameTarget(accessToken, targetId, trimmed)
      onRenamed(updated)
      setEditing(false)
    } catch (e) {
      if (e instanceof TargetError) {
        if (e.status === 400 && e.fields.name) setFieldError(e.fields.name)
        else setError(e.message)
      } else {
        setError('Unable to rename this analysis right now. Please try again.')
      }
    } finally {
      setBusy(false)
    }
  }

  if (!editing) {
    return (
      <button
        type="button"
        className="inline-flex items-center rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-sm font-medium text-slate-700 shadow-xs transition hover:bg-slate-50 focus-visible:ring-3 focus-visible:ring-indigo-500/15"
        onClick={open}
      >
        Rename
      </button>
    )
  }

  const describedBy =
    [fieldError ? 'rename-name-error' : null, 'rename-name-help'].filter(Boolean).join(' ') ||
    undefined

  return (
    <form
      className="max-w-sm rounded-lg border border-slate-200 bg-white p-3 shadow-xs"
      onSubmit={(event) => void submit(event)}
      aria-busy={busy}
      noValidate
    >
      {error && (
        <p
          role="alert"
          className="mb-3 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm leading-6 text-red-800"
        >
          {error}
        </p>
      )}

      <label htmlFor="rename-name" className="mb-1.5 block text-sm font-medium text-slate-700">
        Analysis name
      </label>
      <input
        id="rename-name"
        className={`${inputBase} ${fieldError ? inputBad : inputOk}`}
        value={name}
        maxLength={255}
        required
        autoFocus
        placeholder="Joe's Coffee downtown"
        onChange={(event) => setName(event.target.value)}
        aria-invalid={Boolean(fieldError)}
        aria-describedby={describedBy}
      />
      {fieldError ? (
        <p id="rename-name-error" className="mt-1.5 text-sm text-red-700">
          {fieldError}
        </p>
      ) : null}
      <p id="rename-name-help" className="mt-1.5 text-xs text-slate-500">
        Changing the name does not affect the review source, reviews, or Q&amp;A.
      </p>

      <div className="mt-3 flex gap-2">
        <button
          type="button"
          onClick={close}
          disabled={busy}
          className="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-sm font-semibold text-slate-700 transition hover:bg-slate-50 disabled:opacity-60"
        >
          Cancel
        </button>
        <button
          type="submit"
          disabled={busy}
          className="rounded-lg bg-indigo-600 px-3 py-1.5 text-sm font-semibold text-white shadow-xs transition hover:bg-indigo-700 active:bg-indigo-800 disabled:opacity-60"
        >
          {busy ? 'Saving...' : 'Save'}
        </button>
      </div>
    </form>
  )
}
