// @vitest-environment jsdom
import { afterEach, expect, test, vi } from 'vitest'
import { cleanup, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import ReviewSummary from './ReviewSummary'

// Known fixture: the backend summary for persisted ratings [5, 5, 4, 2, 1]
// (the same fixture asserted in backend/tests/test_review_summary.py).
const FIXTURE = {
  target_id: 't1',
  review_count: 5,
  average_rating: 3.4,
  rating_distribution: { '1': 1, '2': 1, '3': 0, '4': 1, '5': 2 },
  latest_ingestion: { status: 'succeeded' },
}

function reply(status: number, body: unknown = {}) {
  return { ok: status >= 200 && status < 300, status, json: async () => body } as Response
}

function term(name: string) {
  return screen.getByText(name, { selector: 'dt' }).nextElementSibling?.textContent
}

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

test('shows the exact count, average and distribution from the persisted summary', async () => {
  const fetchMock = vi.fn().mockResolvedValue(reply(200, FIXTURE))
  vi.stubGlobal('fetch', fetchMock)
  render(<ReviewSummary accessToken="tok" targetId="t1" refreshKey={0} />)

  await screen.findByText('Reviews ingested')
  expect(term('Reviews ingested')).toBe('5')
  expect(term('Average rating')).toBe('3.4 out of 5')

  const distribution = screen.getByRole('list', { name: 'Rating distribution' })
  const rows = within(distribution).getAllByRole('listitem')
  expect(rows.map((row) => row.getAttribute('aria-label'))).toEqual([
    '5 stars: 2 reviews',
    '4 stars: 1 review',
    '3 stars: 0 reviews',
    '2 stars: 1 review',
    '1 star: 1 review',
  ])
  expect(fetchMock).toHaveBeenCalledWith('/api/targets/t1/summary', {
    headers: { Authorization: 'Bearer tok' },
  })
})

test('shows a two-decimal average as returned by the backend', async () => {
  const body = {
    ...FIXTURE,
    review_count: 2,
    average_rating: 3.75,
    rating_distribution: { '1': 0, '2': 0, '3': 1, '4': 1, '5': 0 },
  }
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(reply(200, body)))
  render(<ReviewSummary accessToken="tok" targetId="t1" refreshKey={0} />)
  await screen.findByText('Reviews ingested')
  expect(term('Average rating')).toBe('3.75 out of 5')
})

test('shows an empty state when no reviews are persisted', async () => {
  const body = {
    ...FIXTURE,
    review_count: 0,
    average_rating: null,
    rating_distribution: { '1': 0, '2': 0, '3': 0, '4': 0, '5': 0 },
  }
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(reply(200, body)))
  render(<ReviewSummary accessToken="tok" targetId="t1" refreshKey={0} />)
  expect(await screen.findByText('No reviews yet. Start ingestion or import a CSV.')).toBeTruthy()
  expect(screen.queryByText('Average rating')).toBeNull()
})

test('reloads the summary when the refresh key changes', async () => {
  const updated = {
    ...FIXTURE,
    review_count: 6,
    average_rating: 3.67,
    rating_distribution: { ...FIXTURE.rating_distribution, '5': 3 },
  }
  const fetchMock = vi
    .fn()
    .mockResolvedValueOnce(reply(200, FIXTURE))
    .mockResolvedValueOnce(reply(200, updated))
  vi.stubGlobal('fetch', fetchMock)
  const { rerender } = render(<ReviewSummary accessToken="tok" targetId="t1" refreshKey={0} />)
  await screen.findByText('Reviews ingested')
  expect(term('Reviews ingested')).toBe('5')

  rerender(<ReviewSummary accessToken="tok" targetId="t1" refreshKey={1} />)
  await screen.findByText('Reviews ingested')
  expect(term('Reviews ingested')).toBe('6')
  expect(fetchMock).toHaveBeenCalledTimes(2)
})

test('shows a generic denial for another user or unknown target', async () => {
  const body = { error: { code: 'NOT_FOUND', message: 'internal detail' } }
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(reply(404, body)))
  render(<ReviewSummary accessToken="tok" targetId="someone-elses" refreshKey={0} />)
  const alert = await screen.findByRole('alert')
  expect(alert.textContent).toContain("don't have access")
  expect(alert.textContent).not.toContain('internal detail')
  expect(screen.queryByText('Reviews ingested')).toBeNull()
})

test('rejects a malformed summary and recovers with retry', async () => {
  const fetchMock = vi
    .fn()
    .mockResolvedValueOnce(reply(200, { review_count: '5' }))
    .mockResolvedValueOnce(reply(200, FIXTURE))
  vi.stubGlobal('fetch', fetchMock)
  render(<ReviewSummary accessToken="tok" targetId="t1" refreshKey={0} />)

  expect((await screen.findByRole('alert')).textContent).toContain(
    'Unable to load the review summary',
  )
  await userEvent.click(screen.getByRole('button', { name: 'Try again' }))
  await screen.findByText('Reviews ingested')
  expect(term('Reviews ingested')).toBe('5')
})

test('reports a network failure', async () => {
  vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('offline')))
  render(<ReviewSummary accessToken="tok" targetId="t1" refreshKey={0} />)
  expect((await screen.findByRole('alert')).textContent).toContain('Unable to connect')
})
