// @vitest-environment jsdom
import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import Home from './Home'

// S2-018: one user, two distinctive review datasets. A -> B -> A must change
// the workspace, summary, saved reviews, question request URL, and visible answer.
const base = { platform: 'google_maps', created_at: '2026-11-01T00:00:00Z' }
const A = {
  ...base,
  id: 'a',
  name: 'Battery Barn',
  source_url: 'https://www.google.com/maps/place/a',
}
const B = {
  ...base,
  id: 'b',
  name: 'Service Shack',
  source_url: 'https://www.google.com/maps/place/b',
}
const datasets = {
  a: {
    review: {
      id: 'a-review',
      text: 'BATTERY_ONLY: charge lasts a week.',
      rating: 5,
      reviewer_name: 'A',
      review_date: null,
    },
    summary: {
      review_count: 1,
      average_rating: 5,
      rating_distribution: { '1': 0, '2': 0, '3': 0, '4': 0, '5': 1 },
    },
    answer: 'BATTERY_ANSWER: reviewers praise longevity.',
  },
  b: {
    review: {
      id: 'b-review',
      text: 'SERVICE_ONLY: helpful staff.',
      rating: 2,
      reviewer_name: 'B',
      review_date: null,
    },
    summary: {
      review_count: 1,
      average_rating: 2,
      rating_distribution: { '1': 0, '2': 1, '3': 0, '4': 0, '5': 0 },
    },
    answer: 'SERVICE_ANSWER: staff are helpful.',
  },
}
function reply(body: unknown): Response {
  return { ok: true, status: 200, json: async () => body } as Response
}
let fetchMock: ReturnType<typeof vi.fn>
beforeEach(() => {
  window.history.replaceState(null, '', '/targets/a')
  fetchMock = vi.fn((url: string, init?: RequestInit) => {
    if (url === '/api/targets') return Promise.resolve(reply({ targets: [A, B] }))
    const m = /^\/api\/targets\/(a|b)(?:\/(summary|reviews|questions))?$/.exec(url)
    if (!m) throw new Error(`Unexpected endpoint ${url}`)
    const id = m[1] as 'a' | 'b'
    const target = id === 'a' ? A : B
    if (!m[2])
      return Promise.resolve(reply({ ...target, latest_ingestion: { status: 'succeeded' } }))
    if (m[2] === 'summary') return Promise.resolve(reply(datasets[id].summary))
    if (m[2] === 'reviews') return Promise.resolve(reply({ reviews: [datasets[id].review] }))
    if (init?.method !== 'POST') throw new Error('Expected Q&A request')
    return Promise.resolve(
      reply({
        status: 'answered',
        answer: datasets[id].answer,
        review_ids: [datasets[id].review.id],
        reviews_considered: 1,
      }),
    )
  })
  vi.stubGlobal('fetch', fetchMock)
})
afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
  window.history.replaceState(null, '', '/')
})

async function ask() {
  await userEvent.type(await screen.findByLabelText('Your question'), 'What do reviewers say?')
  await userEvent.click(screen.getByRole('button', { name: 'Ask' }))
}

test('A -> B -> A changes summary, review evidence, and Q&A context without stale answers', async () => {
  render(<Home email="test@example.com" accessToken="tok" busy={false} onLogout={() => {}} />)
  await screen.findByRole('heading', { name: 'Battery Barn' })
  expect(await screen.findByText(datasets.a.review.text)).toBeTruthy()
  await ask()
  expect(await screen.findByText(datasets.a.answer)).toBeTruthy()
  await userEvent.selectOptions(await screen.findByLabelText('Switch target'), 'b')
  await screen.findByRole('heading', { name: 'Service Shack' })
  expect(await screen.findByText(datasets.b.review.text)).toBeTruthy()
  expect(screen.queryByText(datasets.a.review.text)).toBeNull()
  expect(screen.queryByText(datasets.a.answer)).toBeNull()
  expect((screen.getByLabelText('Your question') as HTMLTextAreaElement).value).toBe('')
  expect(await screen.findByText('For Service Shack')).toBeTruthy()
  expect(await screen.findByText('2.0')).toBeTruthy()
  await ask()
  expect(await screen.findByText(datasets.b.answer)).toBeTruthy()
  await userEvent.selectOptions(await screen.findByLabelText('Switch target'), 'a')
  await screen.findByRole('heading', { name: 'Battery Barn' })
  expect(await screen.findByText(datasets.a.review.text)).toBeTruthy()
  expect(screen.queryByText(datasets.b.review.text)).toBeNull()
  expect(screen.queryByText(datasets.b.answer)).toBeNull()
  expect(await screen.findByText('For Battery Barn')).toBeTruthy()
  expect(await screen.findByText('5.0')).toBeTruthy()
  await ask()
  expect(await screen.findByText(datasets.a.answer)).toBeTruthy()
  const questionUrls = fetchMock.mock.calls
    .filter(([, options]) => (options as RequestInit | undefined)?.method === 'POST')
    .map(([url]) => url)
  expect(questionUrls).toEqual([
    '/api/targets/a/questions',
    '/api/targets/b/questions',
    '/api/targets/a/questions',
  ])
})
