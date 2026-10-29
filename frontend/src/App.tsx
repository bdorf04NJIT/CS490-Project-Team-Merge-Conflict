import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import type { Session } from '@supabase/supabase-js'
import { supabase } from './lib/supabase'
import Home from './pages/Home'

function App() {
  const [session, setSession] = useState<Session | null>(null)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [identity, setIdentity] = useState('')
  const [registering, setRegistering] = useState(false)
  const [message, setMessage] = useState('')

  useEffect(() => {
    const { data: { subscription } } = supabase.auth.onAuthStateChange((_event, next) => {
      setSession(next)
      setIdentity('')
      setError('')
      setLoading(false)
    })
    return () => subscription.unsubscribe()
  }, [])

  useEffect(() => {
    if (!session) return
    const controller = new AbortController()
    void fetch('/api/me', {
      headers: { Authorization: `Bearer ${session.access_token}` },
      signal: controller.signal,
    }).then(async (response) => {
      if (!response.ok) throw new Error('Unable to verify your session with ReviewLens AI.')
      const body: { user_id: string } = await response.json()
      if (!controller.signal.aborted) setIdentity(body.user_id)
    }).catch(() => {
      if (!controller.signal.aborted) setError('Unable to verify your session with ReviewLens AI. Please try signing in again.')
    })
    return () => controller.abort()
  }, [session])

  async function authenticate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = event.currentTarget
    const values = new FormData(form)
    setBusy(true)
    setError('')
    setMessage('')
    try {
      const credentials = {
        email: String(values.get('email')),
        password: String(values.get('password')),
      }
      if (registering) {
        const { data, error } = await supabase.auth.signUp({
          ...credentials,
          options: { emailRedirectTo: window.location.origin },
        })
        if (error) {
          setError('Unable to create an account. Check your details and the password requirements, or try signing in if you already have an account.')
        } else {
          form.reset()
          setRegistering(false)
          if (!data.session) {
            setMessage('Check your email for a confirmation link before signing in. If you already have an account, sign in instead.')
          }
        }
      } else {
        const { error } = await supabase.auth.signInWithPassword(credentials)
        if (error) setError('Sign-in failed. Check your email and password and try again.')
        else form.reset()
      }
    } catch {
      setError('Unable to connect. Check your connection and try again.')
    } finally {
      setBusy(false)
    }
  }

  async function logout() {
    setBusy(true)
    setError('')
    try {
      const { error } = await supabase.auth.signOut({ scope: 'local' })
      if (error) setError('Unable to sign out. Please try again.')
      else {
        setSession(null)
        setIdentity('')
        setMessage('')
      }
    } catch {
      setError('Unable to sign out. Check your connection and try again.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <main className="mx-4 my-10 max-w-[420px] rounded-2xl border border-slate-200/80 bg-white p-7 shadow-[0_12px_40px_-16px_rgba(15,23,42,0.18)] sm:mx-auto sm:my-24 sm:p-10">
      <h1 className="mb-8 flex items-center justify-center gap-2.5 text-xl font-semibold tracking-tight text-slate-900">
        <span aria-hidden="true" className="grid size-8 place-items-center rounded-lg bg-indigo-600 text-white">
          <svg className="size-6" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
            <path d="M12 17H7l-4 3V6a3 3 0 0 1 3-3h11a3 3 0 0 1 3 3v3M7 7h8M7 10h4" />
            <circle cx="16" cy="14" r="4" />
            <path d="m19 17 3 3" />
          </svg>
        </span>
        ReviewLens AI
      </h1>
      {error && <p role="alert" className="mb-5 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm leading-6 text-red-800">{error}</p>}
      {!session && message && <p role="status" className="mb-5 rounded-lg border border-indigo-100 bg-indigo-50 px-4 py-3 text-sm leading-6 text-indigo-900">{message}</p>}
      {loading ? <p role="status">Loading session...</p> : session ? (
        identity ? <Home email={session.user.email} busy={busy} onLogout={() => void logout()} /> : <section>
          {!error && <p role="status">Verifying your session...</p>}
          <button className="mt-4 rounded border border-slate-400 px-4 py-2 hover:bg-slate-100" onClick={() => void logout()} disabled={busy}>Log out</button>
        </section>
      ) : (
        <form className="flex flex-col" key={registering ? 'register' : 'login'} onSubmit={(event) => void authenticate(event)}>
          <h2 className="text-center text-2xl font-semibold tracking-tight text-slate-900">{registering ? 'Create account' : 'Sign in'}</h2>
          <p className="mt-2 mb-7 text-center text-sm leading-6 text-slate-500">{registering ? 'Get started with your ReviewLens AI account.' : 'Welcome back to ReviewLens AI.'}</p>
          <label className="mb-2 text-sm font-medium text-slate-700" htmlFor="email">Email</label>
          <input className="mb-5 w-full rounded-lg border border-slate-300 bg-white px-3.5 py-3 text-base text-slate-900 shadow-xs outline-none transition placeholder:text-slate-400 focus:border-indigo-500 focus:ring-3 focus:ring-indigo-500/15" id="email" name="email" type="email" placeholder="you@example.com" autoComplete="username" required />
          <label className="mb-2 text-sm font-medium text-slate-700" htmlFor="password">Password</label>
          <input className="w-full rounded-lg border border-slate-300 bg-white px-3.5 py-3 text-base text-slate-900 shadow-xs outline-none transition placeholder:text-slate-400 focus:border-indigo-500 focus:ring-3 focus:ring-indigo-500/15" id="password" name="password" type="password" placeholder={registering ? 'Create a password' : 'Enter your password'} autoComplete={registering ? 'new-password' : 'current-password'} required />
          <button className="mt-6 w-full rounded-lg bg-indigo-600 px-4 py-3 text-sm font-semibold text-white shadow-xs transition hover:bg-indigo-700 active:bg-indigo-800 disabled:opacity-60" type="submit" disabled={busy}>{busy ? 'Please wait...' : registering ? 'Create account' : 'Sign in'}</button>
          <button className="mt-6 border-t border-slate-100 pt-5 text-center text-sm font-medium text-indigo-600 transition hover:text-indigo-800 hover:underline" type="button" disabled={busy} onClick={() => {
            setRegistering(!registering)
            setError('')
            setMessage('')
          }}>{registering ? 'Already have an account? Sign in' : 'Create an account'}</button>
        </form>
      )}
    </main>
  )
}

export default App
