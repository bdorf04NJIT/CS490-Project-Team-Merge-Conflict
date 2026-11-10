// @vitest-environment jsdom
import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { cleanup, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import Home from './Home'

const BASE = { platform: 'google_maps', created_at: '2026-11-01T00:00:00+00:00' }
const A = { ...BASE, id: 'a', name: 'Battery Barn', source_url: 'https://maps.app.goo.gl/a' }
const B = { ...BASE, id: 'b', name: 'Service Shack', source_url: 'https://maps.app.goo.gl/b' }
const SUMMARIES = {
  a: { review_count: 20, average_rating: 4.5, rating_distribution: dist(12, 6, 1, 1, 0) },
  b: { review_count: 8, average_rating: 2.25, rating_distribution: dist(1, 1, 1, 2, 3) },
}
const ANSWERS = {
  a: { status: 'answered', answer: 'Reviewers praise the battery life.', review_ids: ['ra'] },
  b: { status: 'answered', answer: 'Customer service is the top complaint.', review_ids: ['rb'] },
}

function dist(five: number, four: number, three: number, two: number, one: number) {
  return { '5': five, '4': four, '3': three, '2': two, '1': one }
}

function reply(status: number, body: unknown = {}) {
  return { ok: status >= 200 && status < 300, status, json: async () => body } as Response
}

function fakeBackend(fetchMock: ReturnType<typeof vi.fn>) {
  fetchMock.mockImplementation((url: string) => {
    if (url === '/api/targets') return Promise.resolve(reply(200, { targets: [A, B] }))
    const match = /^\/api\/targets\/([^/]+)(?:\/(\w+))?$/.exec(url)
    const id = match?.[1] as 'a' | 'b' | undefined
    const target = id === 'a' ? A : id === 'b' ? B : null
    if (!id || !target) return Promise.resolve(reply(404, { error: {} }))
    switch (match?.[2]) {
      case undefined:
        return Promise.resolve(reply(200, { ...target, latest_ingestion: { status: 'succeeded' } }))
      case 'summary':
        return Promise.resolve(reply(200, SUMMARIES[id]))
      case 'reviews':
        return Promise.resolve(reply(200, { reviews: [] }))
      case 'questions':
        return Promise.resolve(reply(200, ANSWERS[id]))
      default:
        return Promise.resolve(reply(404, { error: {} }))
    }
  })
}

let fetchMock: ReturnType<typeof vi.fn>

beforeEach(() => {
  fetchMock = vi.fn()
  fakeBackend(fetchMock)
  vi.stubGlobal('fetch', fetchMock)
  window.history.replaceState(null, '', '/targets/a')
})

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
  window.history.replaceState(null, '', '/')
})

function renderHome() {
  render(<Home email="a@example.com" accessToken="tok-a" busy={false} onLogout={() => {}} />)
}

async function ask(question: string) {
  await userEvent.type(screen.getByLabelText('Your question'), question)
  await userEvent.click(screen.getByRole('button', { name: 'Ask' }))
}

function questionCalls() {
  return fetchMock.mock.calls
    .filter(([, init]) => (init as RequestInit | undefined)?.method === 'POST')
    .map(([url]) => url)
}

test('the workspace identifies the active target in the heading, tab title, summary and Q&A', async () => {
  renderHome()
  const heading = await screen.findByRole('heading', { name: 'Battery Barn' })
  expect(document.title).toBe('Battery Barn | ReviewLens AI')
  expect(document.activeElement).toBe(heading)

  const summary = (await screen.findByText('Reviews ingested')).closest('section')!
  expect(within(summary).getByText('For Battery Barn')).toBeTruthy()
  expect(within(summary).getByText('20')).toBeTruthy()

  const qa = screen.getByRole('region', { name: 'Ask about these reviews' })
  expect(within(qa).getByText('Battery Barn')).toBeTruthy()
})

test('switching moves every panel, and the next question, to the new target', async () => {
  renderHome()
  await screen.findByRole('heading', { name: 'Battery Barn' })

  await ask('What do people like?')
  expect(await screen.findByText('Reviewers praise the battery life.')).toBeTruthy()

  await userEvent.selectOptions(screen.getByLabelText('Switch target'), 'b')

  const heading = await screen.findByRole('heading', { name: 'Service Shack' })
  expect(window.location.pathname).toBe('/targets/b')
  expect(document.title).toBe('Service Shack | ReviewLens AI')
  await waitFor(() => expect(document.activeElement).toBe(heading))
  expect((screen.getByLabelText('Switch target') as HTMLSelectElement).value).toBe('b')

  const summary = (await screen.findByText('For Service Shack')).closest('section')!
  expect(await within(summary).findByText('8')).toBeTruthy()
  expect(within(summary).queryByText('20')).toBeNull()

  expect(screen.queryByText('Reviewers praise the battery life.')).toBeNull()
  expect((screen.getByLabelText('Your question') as HTMLTextAreaElement).value).toBe('')
  const qa = screen.getByRole('region', { name: 'Ask about these reviews' })
  expect(within(qa).getByText('Service Shack')).toBeTruthy()

  await ask('What do people complain about?')
  expect(await screen.findByText('Customer service is the top complaint.')).toBeTruthy()
  expect(questionCalls()).toEqual(['/api/targets/a/questions', '/api/targets/b/questions'])
})

test('browser Back returns to the previous target', async () => {
  renderHome()
  await screen.findByRole('heading', { name: 'Battery Barn' })
  await userEvent.selectOptions(await screen.findByLabelText('Switch target'), 'b')
  await screen.findByRole('heading', { name: 'Service Shack' })

  window.history.back()
  expect(await screen.findByRole('heading', { name: 'Battery Barn' })).toBeTruthy()
  expect(document.title).toBe('Battery Barn | ReviewLens AI')
})

test("the switcher cannot open another user's target: a foreign id is still denied", async () => {
  window.history.replaceState(null, '', '/targets/someone-elses-target')
  renderHome()
  expect(await screen.findByRole('alert')).toBeTruthy()
  expect(screen.queryByLabelText('Switch target')).toBeNull()
  expect(screen.queryByLabelText('Your question')).toBeNull()
})

test('going back to the target list resets the tab title', async () => {
  renderHome()
  await screen.findByRole('heading', { name: 'Battery Barn' })
  await userEvent.click(screen.getByRole('button', { name: /Back to your targets/ }))
  await waitFor(() => expect(document.title).toBe('Your targets | ReviewLens AI'))
})
