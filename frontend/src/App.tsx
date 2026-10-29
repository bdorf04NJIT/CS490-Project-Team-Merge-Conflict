import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import type { Session } from '@supabase/supabase-js'
import { supabase } from './lib/supabase'
import './App.css'

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
      if (!response.ok) throw new Error('Unable to verify your session with ReviewLens.')
      const body: { user_id: string } = await response.json()
      if (!controller.signal.aborted) setIdentity(body.user_id)
    }).catch(() => {
      if (!controller.signal.aborted) setError('Unable to verify your session with ReviewLens. Please try signing in again.')
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
    <main className="auth-panel">
      <h1>ReviewLens</h1>
      {error && <p role="alert">{error}</p>}
      {!session && message && <p role="status">{message}</p>}
      {loading ? <p role="status">Loading session…</p> : session ? (
        <section>
          <p>Signed in as {session.user.email}</p>
          <p>{identity ? `ReviewLens user ID: ${identity}` : 'Verifying ReviewLens session…'}</p>
          <button onClick={() => void logout()} disabled={busy}>Log out</button>
        </section>
      ) : (
        <form key={registering ? 'register' : 'login'} onSubmit={(event) => void authenticate(event)}>
          <h2>{registering ? 'Create account' : 'Sign in'}</h2>
          <label htmlFor="email">Email</label>
          <input id="email" name="email" type="email" autoComplete="username" required />
          <label htmlFor="password">Password</label>
          <input id="password" name="password" type="password" autoComplete={registering ? 'new-password' : 'current-password'} minLength={registering ? 6 : undefined} aria-describedby={registering ? 'password-requirements' : undefined} required />
          {registering && <p id="password-requirements">Password must be at least 6 characters long.</p>}
          <button type="submit" disabled={busy}>{busy ? 'Please wait...' : registering ? 'Create account' : 'Sign in'}</button>
          <button type="button" disabled={busy} onClick={() => {
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
