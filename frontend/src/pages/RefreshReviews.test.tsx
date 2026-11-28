// @vitest-environment jsdom
// S3-009: re-ingesting an analysis that already has reviews is presented as a refresh.
import { afterEach, expect, test, vi } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import TargetWorkspace from './TargetWorkspace'

const BASE = {
  id: 't1',
  name: 'Planet Fitness',
  platform: 'google_maps',
  source_url: 'https://www.google.com/maps/place/planet',
  created_at: '2026-11-01T00:00:00+00:00',
}
const WITH_DATA = { ...BASE, latest_ingestion: { status: 'succeeded' }, review_count: 50 }
const EMPTY = { ...BASE, latest_ingestion: null, review_count: 0 }

function reply(status: number, body: unknown = {}) {
  return { ok: status >= 200 && status < 300, status, json: async () => body } as Response
}

// A fake backend: the workspace GET returns `workspace` (then `after`, once a refresh has
// run), the refresh POST returns `post`, and summary/reviews are left unavailable.
function stubBackend(workspace: unknown, post: Response, after = workspace) {
  let refreshed = false
  const fetchMock = vi.fn((url: string, init?: RequestInit) => {
    if (init?.method === 'POST') {
      refreshed = true
      return Promise.resolve(post)
    }
    if (url.endsWith('/summary') || url.endsWith('/reviews') || url.includes('/reviews?')) {
      return Promise.resolve(reply(500))
    }
    return Promise.resolve(reply(200, refreshed ? after : workspace))
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

test('an analysis with reviews offers "Refresh reviews" and explains nothing is removed', async () => {
  stubBackend(WITH_DATA, reply(202, {}))
  render(<TargetWorkspace accessToken="tok" targetId="t1" onBack={() => {}} />)

  expect(await screen.findByRole('heading', { name: 'Refresh reviews' })).toBeTruthy()
  expect(screen.getByRole('button', { name: 'Refresh reviews' })).toBeTruthy()
  expect(screen.queryByRole('button', { name: 'Start ingestion' })).toBeNull()
  expect(
    screen.getByText(
      /New reviews are added to the 50 reviews you already have, and none are removed/,
    ),
  ).toBeTruthy()
})

test('an analysis without reviews still offers the first ingestion', async () => {
  stubBackend(EMPTY, reply(202, {}))
  render(<TargetWorkspace accessToken="tok" targetId="t1" onBack={() => {}} />)

  expect(await screen.findByRole('button', { name: 'Start ingestion' })).toBeTruthy()
  expect(screen.queryByRole('button', { name: 'Refresh reviews' })).toBeNull()
})

test('a refresh reports new, already saved, and the current dataset size', async () => {
  const fetchMock = stubBackend(
    WITH_DATA,
    reply(202, {
      target_id: 't1',
      status: 'accepted',
      run_status: 'succeeded',
      imported_count: 8,
      skipped_count: 0,
      skip_reasons: {},
      already_saved_count: 42,
      review_count: 58,
    }),
    { ...WITH_DATA, review_count: 58 },
  )
  render(<TargetWorkspace accessToken="tok" targetId="t1" onBack={() => {}} />)

  await userEvent.click(await screen.findByRole('button', { name: 'Refresh reviews' }))

  expect(
    await screen.findByText(
      'Refresh complete. Added 8 new reviews. 42 reviews were already saved. Current dataset: 58 reviews.',
    ),
  ).toBeTruthy()
  // The same analysis is refreshed: one POST to its own ingestion endpoint, no new target.
  const posts = fetchMock.mock.calls.filter(([, init]) => init?.method === 'POST')
  expect(posts.map(([url]) => url)).toEqual(['/api/targets/t1/ingestions'])
  // The workspace reloads and now describes the larger dataset.
  expect(await screen.findByText(/added to the 58 reviews you already have/)).toBeTruthy()
})

test('a refresh with nothing new says so instead of looking like a failure', async () => {
  stubBackend(
    WITH_DATA,
    reply(202, {
      target_id: 't1',
      status: 'accepted',
      run_status: 'succeeded',
      imported_count: 0,
      skipped_count: 0,
      skip_reasons: {},
      already_saved_count: 1,
      review_count: 50,
    }),
  )
  render(<TargetWorkspace accessToken="tok" targetId="t1" onBack={() => {}} />)

  await userEvent.click(await screen.findByRole('button', { name: 'Refresh reviews' }))

  const notice = await screen.findByText(
    'Refresh complete. No new reviews found. 1 review was already saved. Current dataset: 50 reviews.',
  )
  expect(notice.getAttribute('role')).toBe('status')
})

test('a failed refresh tells the user their current reviews are unchanged', async () => {
  stubBackend(WITH_DATA, reply(503, { error: {} }), {
    ...WITH_DATA,
    latest_ingestion: { status: 'failed' },
  })
  render(<TargetWorkspace accessToken="tok" targetId="t1" onBack={() => {}} />)

  await userEvent.click(await screen.findByRole('button', { name: 'Refresh reviews' }))

  // Find the refresh alert by its text: once the workspace reloads, other panels (for
  // example Q&A, whose data this fake backend leaves unavailable) may show alerts too.
  const alert = await screen.findByText(/Your current 50 reviews are unchanged\./)
  expect(alert.getAttribute('role')).toBe('alert')
  expect(alert.textContent).toContain("isn't available right now")
})
