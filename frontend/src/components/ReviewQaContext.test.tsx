// @vitest-environment jsdom
import { afterEach, expect, test, vi } from 'vitest'
import { act, cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import ReviewQa from './ReviewQa'

function reply(answer: string) {
  return {
    ok: true,
    status: 200,
    json: async () => ({ status: 'answered', answer, review_ids: [], reviews_considered: 2 }),
  } as Response
}

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

async function ask(question: string) {
  await userEvent.type(screen.getByLabelText('Your question'), question)
  await userEvent.click(screen.getByRole('button', { name: 'Ask' }))
}

test('a late response from target A cannot replace target B answer', async () => {
  let finishA: (response: Response) => void = () => {}
  const pendingA = new Promise<Response>((resolve) => {
    finishA = resolve
  })
  const fetchMock = vi.fn((url: string) =>
    url === '/api/targets/a/questions'
      ? pendingA
      : Promise.resolve(reply('Service target answer from B')),
  )
  vi.stubGlobal('fetch', fetchMock)
  const view = render(<ReviewQa accessToken="tok" targetId="a" targetName="Battery Barn" />)

  await ask('What is battery life like?')
  expect(screen.getByText('ReviewLens is reading the reviews...')).toBeTruthy()

  view.rerender(<ReviewQa accessToken="tok" targetId="b" targetName="Service Shack" />)
  expect(screen.queryByText('ReviewLens is reading the reviews...')).toBeNull()
  expect((screen.getByLabelText('Your question') as HTMLTextAreaElement).value).toBe('')

  await ask('How is service?')
  expect(await screen.findByText('Service target answer from B')).toBeTruthy()
  await act(async () => finishA(reply('STALE BATTERY ANSWER FROM A')))

  expect(screen.queryByText('STALE BATTERY ANSWER FROM A')).toBeNull()
  expect(screen.getByText('Service target answer from B')).toBeTruthy()
  expect(fetchMock.mock.calls.map(([url]) => url)).toEqual([
    '/api/targets/a/questions',
    '/api/targets/b/questions',
  ])
})

test('changing authenticated identity also resets prior questions and answers', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(reply('Old account answer')))
  const view = render(<ReviewQa accessToken="tok-a" targetId="shared-id" />)
  await ask('Tell me about service')
  expect(await screen.findByText('Old account answer')).toBeTruthy()

  view.rerender(<ReviewQa accessToken="tok-b" targetId="shared-id" />)
  expect(screen.queryByText('Old account answer')).toBeNull()
  expect((screen.getByLabelText('Your question') as HTMLTextAreaElement).value).toBe('')
})
