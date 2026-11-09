// @vitest-environment jsdom
import { afterEach, expect, test, vi } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import ReviewQa from './ReviewQa'

function reply(status: number, body: unknown = {}) {
  return { ok: status >= 200 && status < 300, status, json: async () => body } as Response
}

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

async function ask(question: string) {
  const textarea = screen.getByLabelText('Your question')
  await userEvent.type(textarea, question)
  await userEvent.click(screen.getByRole('button', { name: 'Ask' }))
}

test('submits the question to the target and shows the answer with evidence count', async () => {
  const body = {
    status: 'answered',
    answer: 'Slow service is the top complaint.',
    review_ids: ['a', 'b'],
  }
  const fetchMock = vi.fn().mockResolvedValue(reply(200, body))
  vi.stubGlobal('fetch', fetchMock)
  render(<ReviewQa accessToken="tok" targetId="t1" />)

  await ask('What complaints appear most frequently?')

  expect(await screen.findByText('Slow service is the top complaint.')).toBeTruthy()
  expect(screen.getByText('Based on 2 reviews.')).toBeTruthy()
  expect(fetchMock).toHaveBeenCalledWith('/api/targets/t1/questions', {
    method: 'POST',
    headers: { Authorization: 'Bearer tok', 'Content-Type': 'application/json' },
    body: JSON.stringify({ question: 'What complaints appear most frequently?' }),
  })
})

test('does not submit a blank question', async () => {
  const fetchMock = vi.fn()
  vi.stubGlobal('fetch', fetchMock)
  render(<ReviewQa accessToken="tok" targetId="t1" />)

  expect(screen.getByRole('button', { name: 'Ask' })).toHaveProperty('disabled', true)
  await userEvent.type(screen.getByLabelText('Your question'), '   ')
  expect(screen.getByRole('button', { name: 'Ask' })).toHaveProperty('disabled', true)
  expect(fetchMock).not.toHaveBeenCalled()
})

test('shows an out-of-scope answer without an evidence count', async () => {
  const body = {
    status: 'out_of_scope',
    answer: 'I can only answer questions about these reviews.',
    review_ids: [],
  }
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(reply(200, body)))
  render(<ReviewQa accessToken="tok" targetId="t1" />)

  await ask("What's the weather today?")

  expect(await screen.findByText('I can only answer questions about these reviews.')).toBeTruthy()
  expect(screen.queryByText(/Based on/)).toBeNull()
})

test('shows a generic denial for another user or unknown target', async () => {
  const body = { error: { code: 'NOT_FOUND', message: 'internal detail' } }
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(reply(404, body)))
  render(<ReviewQa accessToken="tok" targetId="someone-elses" />)

  await ask('Anything?')

  const alert = await screen.findByRole('alert')
  expect(alert.textContent).toContain("don't have access")
  expect(alert.textContent).not.toContain('internal detail')
})

test('rejects a malformed answer body', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(reply(200, { answer: 42 })))
  render(<ReviewQa accessToken="tok" targetId="t1" />)

  await ask('Anything?')

  expect((await screen.findByRole('alert')).textContent).toContain('Unable to answer that')
})

test('reports a network failure', async () => {
  vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('offline')))
  render(<ReviewQa accessToken="tok" targetId="t1" />)

  await ask('Anything?')

  expect((await screen.findByRole('alert')).textContent).toContain('Unable to connect')
})
