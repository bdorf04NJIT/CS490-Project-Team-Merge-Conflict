// @vitest-environment jsdom
// S2-015: a scope refusal is shown distinctly from an answer about the reviews.
import { afterEach, expect, test, vi } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import ReviewQa from './ReviewQa'

const REFUSAL_LABEL = 'Outside the scope of these reviews'

function reply(status: number, body: unknown) {
  return { ok: status >= 200 && status < 300, status, json: async () => body } as Response
}

async function ask(question: string) {
  await userEvent.type(screen.getByLabelText('Your question'), question)
  await userEvent.click(screen.getByRole('button', { name: 'Ask' }))
}

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

test.each([
  "What are Joe's Coffee's Yelp reviews like?",
  'Is the bakery across the street any good?',
])('labels a refusal for %s and shows no evidence', async (question) => {
  const body = {
    status: 'out_of_scope',
    answer: "I can only answer questions about the Google Maps reviews of Joe's Coffee.",
    review_ids: [],
    reviews_considered: 5,
  }
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(reply(200, body)))
  render(<ReviewQa accessToken="tok" targetId="t1" targetName="Joe's Coffee" />)

  await ask(question)

  expect(await screen.findByText(body.answer)).toBeTruthy()
  expect(screen.getByText(REFUSAL_LABEL)).toBeTruthy()
  expect(screen.queryByText('Not covered by these reviews')).toBeNull()
  expect(screen.queryByText(/mention this|Based on/)).toBeNull()
})

test('a comparison the reviews support is answered, not labelled as a refusal', async () => {
  const body = {
    status: 'answered',
    answer: 'One reviewer says the latte is better than Bean Barn next door.',
    review_ids: ['r1'],
    reviews_considered: 5,
  }
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(reply(200, body)))
  render(<ReviewQa accessToken="tok" targetId="t1" targetName="Joe's Coffee" />)

  await ask('How do reviewers compare it to Bean Barn?')

  expect(await screen.findByText(body.answer)).toBeTruthy()
  expect(screen.queryByText(REFUSAL_LABEL)).toBeNull()
  expect(screen.getByText('1 of 5 reviews mentions this.')).toBeTruthy()
})

test('an insufficient-evidence reply keeps its own label, not the refusal label', async () => {
  const body = {
    status: 'insufficient_evidence',
    answer: 'The reviews do not mention parking.',
    review_ids: [],
    reviews_considered: 5,
  }
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(reply(200, body)))
  render(<ReviewQa accessToken="tok" targetId="t1" targetName="Joe's Coffee" />)

  await ask('Is parking easy?')

  expect(await screen.findByText('Not covered by these reviews')).toBeTruthy()
  expect(screen.queryByText(REFUSAL_LABEL)).toBeNull()
})
