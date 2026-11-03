// @vitest-environment jsdom
import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { act, cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import App from './App'

const auth = vi.hoisted(() => ({
  onAuthStateChange: vi.fn(),
  signInWithPassword: vi.fn(),
  signOut: vi.fn(),
  signUp: vi.fn(),
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
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string) => ({
      ok: true,
      json: async () => (url === '/api/targets' ? { targets: [] } : { user_id: 'verified-user' }),
    })),
  )
})
afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
  window.history.replaceState(null, '', '/')
})

test('signs in through the SDK and sends the provider token to Flask', async () => {
  auth.signInWithPassword.mockImplementation(async () => {
    notify('SIGNED_IN', session)
    return { error: null }
  })
  render(<App />)
  await userEvent.type(screen.getByLabelText('Email'), 'user@example.com')
  await userEvent.type(screen.getByLabelText('Password'), 'test-password')
  await userEvent.click(screen.getByRole('button', { name: 'Sign in' }))
  expect(auth.signInWithPassword).toHaveBeenCalledWith({
    email: 'user@example.com',
    password: 'test-password',
  })
  expect(await screen.findByRole('heading', { name: 'Welcome to ReviewLens AI' })).toBeTruthy()
  expect(fetch).toHaveBeenCalledWith(
    '/api/me',
    expect.objectContaining({
      headers: { Authorization: 'Bearer provider-token' },
    }),
  )
})

test('restores an existing session and logs out without retaining identity', async () => {
  auth.onAuthStateChange.mockImplementation((callback) => {
    callback('INITIAL_SESSION', session)
    return { data: { subscription: { unsubscribe: vi.fn() } } }
  })
  auth.signOut.mockResolvedValue({ error: null })
  render(<App />)
  await screen.findByRole('heading', { name: 'Welcome to ReviewLens AI' })
  await userEvent.click(screen.getByRole('button', { name: 'Log out' }))
  expect(auth.signOut).toHaveBeenCalledWith({ scope: 'local' })
  expect(await screen.findByLabelText('Password')).toBeTruthy()
  expect(screen.queryByRole('heading', { name: 'Welcome to ReviewLens AI' })).toBeNull()
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
  expect(screen.queryByRole('heading', { name: 'Welcome to ReviewLens AI' })).toBeNull()
})

test('uses refreshed tokens and clears identity after an external sign-out', async () => {
  render(<App />)
  act(() => notify('SIGNED_IN', session))
  await screen.findByRole('heading', { name: 'Welcome to ReviewLens AI' })
  act(() => notify('TOKEN_REFRESHED', { ...session, access_token: 'refreshed-token' }))
  await waitFor(() =>
    expect(fetch).toHaveBeenCalledWith(
      '/api/me',
      expect.objectContaining({
        headers: { Authorization: 'Bearer refreshed-token' },
      }),
    ),
  )
  await waitFor(() =>
    expect(fetch).toHaveBeenCalledWith(
      '/api/targets',
      expect.objectContaining({
        headers: { Authorization: 'Bearer refreshed-token' },
      }),
    ),
  )
  act(() => notify('SIGNED_OUT', null))
  expect(screen.getByLabelText('Password')).toBeTruthy()
  expect(screen.queryByRole('heading', { name: 'Welcome to ReviewLens AI' })).toBeNull()
})

test('failed logout reports an error and keeps the session available', async () => {
  auth.signOut.mockResolvedValue({ error: new Error('offline') })
  render(<App />)
  act(() => notify('SIGNED_IN', session))
  await screen.findByRole('heading', { name: 'Welcome to ReviewLens AI' })
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
    email: 'new@example.com',
    password: 'new-password',
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
  expect(await screen.findByRole('heading', { name: 'Welcome to ReviewLens AI' })).toBeTruthy()
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
  expect(await screen.findByRole('heading', { name: 'Welcome to ReviewLens AI' })).toBeTruthy()
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

const WORKSPACE_TARGET = {
  id: 't1',
  name: "Joe's Coffee",
  platform: 'google_maps',
  source_url: 'https://www.google.com/maps/place/joes',
  created_at: '2026-01-02T00:00:00+00:00',
}

function signedIn(routes: Record<string, { status: number; body: unknown }>) {
  auth.onAuthStateChange.mockImplementation((callback) => {
    callback('INITIAL_SESSION', session)
    return { data: { subscription: { unsubscribe: vi.fn() } } }
  })
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string) => {
      const route = routes[url] ?? { status: 200, body: { user_id: 'verified-user' } }
      return {
        ok: route.status < 300,
        status: route.status,
        json: async () => route.body,
      } as Response
    }),
  )
}

test('opens a target workspace from the list and returns to the list', async () => {
  signedIn({
    '/api/targets': { status: 200, body: { targets: [WORKSPACE_TARGET] } },
    '/api/targets/t1': { status: 200, body: { ...WORKSPACE_TARGET, latest_ingestion: null } },
  })
  render(<App />)
  await userEvent.click(await screen.findByRole('link', { name: /Joe's Coffee/ }))

  expect(await screen.findByRole('heading', { name: "Joe's Coffee" })).toBeTruthy()
  expect(window.location.pathname).toBe('/targets/t1')
  expect(screen.getByRole('button', { name: 'Start ingestion' })).toBeTruthy()

  await userEvent.click(screen.getByRole('button', { name: /Back to your targets/ }))
  expect(await screen.findByRole('heading', { name: 'Your analysis targets' })).toBeTruthy()
  expect(window.location.pathname).toBe('/')
})

test('direct navigation to another user target id is denied without data', async () => {
  window.history.replaceState(null, '', '/targets/user-a-target')
  signedIn({
    '/api/targets/user-a-target': {
      status: 404,
      body: { error: { code: 'NOT_FOUND', message: "We couldn't find that analysis target." } },
    },
  })
  render(<App />)

  expect((await screen.findByRole('alert')).textContent).toContain("don't have access")
  expect(fetch).toHaveBeenCalledWith('/api/targets/user-a-target', {
    headers: { Authorization: 'Bearer provider-token' },
  })
  expect(screen.queryByRole('button', { name: 'Start ingestion' })).toBeNull()
})
