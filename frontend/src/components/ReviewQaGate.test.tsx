// @vitest-environment jsdom
import { afterEach, expect, test, vi } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import ReviewQaGate from './ReviewQaGate'

function reply(status: number, body: unknown = {}) {
  return { ok: status >= 200 && status < 300, status, json: async () => body } as Response
}

const distribution = { '1': 0, '2': 0, '3': 0, '4': 0, '5': 2 }
const zero = {
  review_count: 0,
  average_rating: null,
  rating_distribution: { '1': 0, '2': 0, '3': 0, '4': 0, '5': 0 },
}
const ready = { review_count: 2, average_rating: 5, rating_distribution: distribution }
const BASE = { accessToken: 'tok', targetId: 'a', targetName: 'Harbor Cafe', refreshKey: 0 }

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

test('failed ingestion with no reviews shows clear empty state and cannot ask Gemini', async () => {
  const fetchMock = vi.fn().mockResolvedValue(reply(200, zero))
  vi.stubGlobal('fetch', fetchMock)
  render(<ReviewQaGate {...BASE} latestIngestionStatus="failed" />)

  expect(await screen.findByText(/latest ingestion failed.*no saved reviews/i)).toBeTruthy()
  expect(screen.getByText(/Complete ingestion or import a CSV/)).toBeTruthy()
  expect(screen.queryByRole('button', { name: 'Ask' })).toBeNull()
  expect(fetchMock).toHaveBeenCalledWith('/api/targets/a/summary', {
    headers: { Authorization: 'Bearer tok' },
  })
  expect(fetchMock.mock.calls.every(([url]) => !String(url).endsWith('/questions'))).toBe(true)
})

test('a target with no reviews cannot present normal Q&A even after a successful run', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(reply(200, zero)))
  render(<ReviewQaGate {...BASE} latestIngestionStatus="succeeded" />)
  expect(await screen.findByText(/This target has no saved reviews yet/)).toBeTruthy()
  expect(screen.queryByLabelText('Your question')).toBeNull()
})

test('reviews from an earlier successful ingestion allow Q&A after a later failed run', async () => {
  const fetchMock = vi.fn((url: string) =>
    Promise.resolve(
      url.endsWith('/summary')
        ? reply(200, ready)
        : reply(200, {
            status: 'answered',
            answer: 'Coffee is popular.',
            review_ids: [],
            reviews_considered: 2,
          }),
    ),
  )
  vi.stubGlobal('fetch', fetchMock)
  render(<ReviewQaGate {...BASE} latestIngestionStatus="failed" />)
  await screen.findByRole('button', { name: 'Ask' })
  await userEvent.type(screen.getByLabelText('Your question'), 'How is the coffee?')
  await userEvent.click(screen.getByRole('button', { name: 'Ask' }))
  expect(await screen.findByText('Coffee is popular.')).toBeTruthy()
  expect(fetchMock.mock.calls.some(([url]) => url === '/api/targets/a/questions')).toBe(true)
})

test('a failed summary fetch must not silently enable Q&A', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(reply(503)))
  render(<ReviewQaGate {...BASE} />)
  expect(await screen.findByRole('alert')).toBeTruthy()
  expect(screen.queryByRole('button', { name: 'Ask' })).toBeNull()
  expect(screen.getByRole('button', { name: 'Retry review check' })).toBeTruthy()
})

test('review availability is rechecked after a new ingestion and never shows stale Q&A', async () => {
  const fetchMock = vi
    .fn()
    .mockResolvedValueOnce(reply(200, ready))
    .mockResolvedValueOnce(reply(200, zero))
  vi.stubGlobal('fetch', fetchMock)
  const view = render(<ReviewQaGate {...BASE} />)
  await screen.findByRole('button', { name: 'Ask' })
  view.rerender(<ReviewQaGate {...BASE} targetId="b" targetName="New Target" />)
  expect(screen.queryByRole('button', { name: 'Ask' })).toBeNull()
  expect(await screen.findByText(/This target has no saved reviews yet/)).toBeTruthy()
  expect(fetchMock.mock.calls.map(([url]) => url)).toEqual([
    '/api/targets/a/summary',
    '/api/targets/b/summary',
  ])
})
