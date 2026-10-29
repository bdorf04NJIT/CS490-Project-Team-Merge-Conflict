// @vitest-environment jsdom
import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { act, cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import App from './App'

const auth = vi.hoisted(() => ({
  onAuthStateChange: vi.fn(), signInWithPassword: vi.fn(), signOut: vi.fn(), signUp: vi.fn(),
}))
vi.mock('./lib/supabase', () => ({ supabase: { auth } }))
const session = { access_token: 'provider-token', user: { email: 'user@example.com' } }
let notify: (event: string, value: typeof session | null) => void

beforeEach(() => {
  vi.resetAllMocks()
  auth.onAuthStateChange.mockImplementation((callback) => {
    notify = callback
    callback('INITIAL_SESSION', null)
    return { data: { subscription: { unsubscribe: vi.fn() } } }
  })
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
    ok: true, json: async () => ({ user_id: 'verified-user' }),
  }))
})
afterEach(() => { cleanup(); vi.unstubAllGlobals() })

test('signs in through the SDK and sends the provider token to Flask', async () => {
  auth.signInWithPassword.mockImplementation(async () => {
    notify('SIGNED_IN', session)
    return { error: null }
  })
  render(<App />)
  await userEvent.type(screen.getByLabelText('Email'), 'user@example.com')
  await userEvent.type(screen.getByLabelText('Password'), 'test-password')
  await userEvent.click(screen.getByRole('button', { name: 'Sign in' }))
  expect(auth.signInWithPassword).toHaveBeenCalledWith({ email: 'user@example.com', password: 'test-password' })
  expect(await screen.findByText('ReviewLens user ID: verified-user')).toBeTruthy()
  expect(fetch).toHaveBeenCalledWith('/api/me', expect.objectContaining({
    headers: { Authorization: 'Bearer provider-token' },
  }))
})

test('restores an existing session and logs out without retaining identity', async () => {
  auth.onAuthStateChange.mockImplementation((callback) => {
    callback('INITIAL_SESSION', session)
    return { data: { subscription: { unsubscribe: vi.fn() } } }
  })
  auth.signOut.mockResolvedValue({ error: null })
  render(<App />)
  await screen.findByText('ReviewLens user ID: verified-user')
  await userEvent.click(screen.getByRole('button', { name: 'Log out' }))
  expect(auth.signOut).toHaveBeenCalledWith({ scope: 'local' })
  expect(await screen.findByLabelText('Password')).toBeTruthy()
  expect(screen.queryByText(/verified-user/)).toBeNull()
})

test('failed login stays signed out and displays an error', async () => {
  auth.signInWithPassword.mockResolvedValue({ error: new Error('invalid') })
  render(<App />)
  await userEvent.type(screen.getByLabelText('Email'), 'user@example.com')
  await userEvent.type(screen.getByLabelText('Password'), 'wrong')
  await userEvent.click(screen.getByRole('button', { name: 'Sign in' }))
  expect((await screen.findByRole('alert')).textContent).toContain('Sign-in failed')
  expect(fetch).not.toHaveBeenCalled()
})

test('backend rejection does not display a verified identity', async () => {
  vi.mocked(fetch).mockResolvedValue({ ok: false } as Response)
  auth.onAuthStateChange.mockImplementation((callback) => {
    callback('INITIAL_SESSION', session)
    return { data: { subscription: { unsubscribe: vi.fn() } } }
  })
  render(<App />)
  await waitFor(() => expect(screen.getByRole('alert').textContent).toContain('Unable to verify'))
  expect(screen.queryByText(/ReviewLens user ID:/)).toBeNull()
})

test('uses refreshed tokens and clears identity after an external sign-out', async () => {
  render(<App />)
  act(() => notify('SIGNED_IN', session))
  await screen.findByText('ReviewLens user ID: verified-user')
  act(() => notify('TOKEN_REFRESHED', { ...session, access_token: 'refreshed-token' }))
  await waitFor(() => expect(fetch).toHaveBeenLastCalledWith('/api/me', expect.objectContaining({
    headers: { Authorization: 'Bearer refreshed-token' },
  })))
  act(() => notify('SIGNED_OUT', null))
  expect(screen.getByLabelText('Password')).toBeTruthy()
  expect(screen.queryByText(/ReviewLens user ID:/)).toBeNull()
})

test('failed logout reports an error and keeps the session available', async () => {
  auth.signOut.mockResolvedValue({ error: new Error('offline') })
  render(<App />)
  act(() => notify('SIGNED_IN', session))
  await screen.findByText('ReviewLens user ID: verified-user')
  await userEvent.click(screen.getByRole('button', { name: 'Log out' }))
  expect((await screen.findByRole('alert')).textContent).toContain('Unable to sign out')
  expect(screen.getByRole('button', { name: 'Log out' })).toBeTruthy()
})

test('registration requiring confirmation returns to login without backend access', async () => {
  auth.signUp.mockResolvedValue({ data: { session: null }, error: null })
  render(<App />)
  await userEvent.click(screen.getByRole('button', { name: 'Create an account' }))
  await userEvent.type(screen.getByLabelText('Email'), 'new@example.com')
  await userEvent.type(screen.getByLabelText('Password'), 'new-password')
  await userEvent.click(screen.getByRole('button', { name: 'Create account' }))
  expect(auth.signUp).toHaveBeenCalledWith({
    email: 'new@example.com', password: 'new-password',
    options: { emailRedirectTo: window.location.origin },
  })
  expect((await screen.findByRole('status')).textContent).toContain('Check your email')
  expect(screen.getByRole('button', { name: 'Sign in' })).toBeTruthy()
  expect((screen.getByLabelText('Password') as HTMLInputElement).value).toBe('')
  expect(fetch).not.toHaveBeenCalled()
  auth.signInWithPassword.mockImplementation(async () => {
    notify('SIGNED_IN', session)
    return { error: null }
  })
  await userEvent.type(screen.getByLabelText('Email'), 'new@example.com')
  await userEvent.type(screen.getByLabelText('Password'), 'new-password')
  await userEvent.click(screen.getByRole('button', { name: 'Sign in' }))
  expect(await screen.findByText('ReviewLens user ID: verified-user')).toBeTruthy()
})

test('registration signs in immediately when Supabase returns a session', async () => {
  auth.signUp.mockImplementation(async () => {
    notify('SIGNED_IN', session)
    return { data: { session }, error: null }
  })
  render(<App />)
  await userEvent.click(screen.getByRole('button', { name: 'Create an account' }))
  await userEvent.type(screen.getByLabelText('Email'), 'user@example.com')
  await userEvent.type(screen.getByLabelText('Password'), 'new-password')
  await userEvent.click(screen.getByRole('button', { name: 'Create account' }))
  expect(await screen.findByText('ReviewLens user ID: verified-user')).toBeTruthy()
  expect(screen.queryByText(/Check your email/)).toBeNull()
})

test('rejected registration stays on the form without claiming success', async () => {
  auth.signUp.mockResolvedValue({ data: { session: null }, error: new Error('rejected') })
  render(<App />)
  await userEvent.click(screen.getByRole('button', { name: 'Create an account' }))
  await userEvent.type(screen.getByLabelText('Email'), 'new@example.com')
  await userEvent.type(screen.getByLabelText('Password'), 'rejected-password')
  await userEvent.click(screen.getByRole('button', { name: 'Create account' }))
  expect((await screen.findByRole('alert')).textContent).toContain('Unable to create an account')
  expect(screen.getByRole('button', { name: 'Create account' })).toBeTruthy()
  expect(screen.queryByText(/Check your email/)).toBeNull()
  expect(fetch).not.toHaveBeenCalled()
})
