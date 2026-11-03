// @vitest-environment jsdom
import { afterEach, expect, test, vi } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import ReviewList from './ReviewList'

function reply(status: number, body: unknown = {}) {
  return { ok: status >= 200 && status < 300, status, json: async () => body } as Response
}

function reviews(count: number) {
  return Array.from({ length: count }, (_, i) => ({
    id: `r${i}`,
    text: `Review number ${i}`,
    rating: (i % 5) + 1,
    reviewer_name: i === 0 ? 'Alex' : null,
    review_date: i === 0 ? '2026-10-12T00:00:00Z' : null,
  }))
}

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

test('shows the saved review count and a preview of real reviews', async () => {
  const fetchMock = vi.fn().mockResolvedValue(reply(200, { reviews: reviews(14) }))
  vi.stubGlobal('fetch', fetchMock)
  render(<ReviewList accessToken="tok" targetId="t1" refreshKey={0} />)

  expect(await screen.findByRole('heading', { name: 'Saved reviews (14)' })).toBeTruthy()
  expect(screen.getAllByRole('listitem')).toHaveLength(5)
  expect(screen.getByText('Alex')).toBeTruthy()
  expect(screen.getByText('2026-10-12')).toBeTruthy()
  expect(screen.getByRole('img', { name: '1 out of 5 stars' })).toBeTruthy()
  expect(fetchMock).toHaveBeenCalledWith('/api/targets/t1/reviews', {
    headers: { Authorization: 'Bearer tok' },
  })

  await userEvent.click(screen.getByRole('button', { name: 'Show all 14' }))
  expect(screen.getAllByRole('listitem')).toHaveLength(14)
})

test('says when nothing has been saved', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(reply(200, { reviews: [] })))
  render(<ReviewList accessToken="tok" targetId="t1" refreshKey={0} />)
  expect(await screen.findByText('No reviews have been saved yet.')).toBeTruthy()
})

test('shows a generic message and no reviews when access is denied', async () => {
  const body = { error: { message: 'internal detail' } }
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(reply(404, body)))
  render(<ReviewList accessToken="tok" targetId="someone-elses" refreshKey={0} />)

  const alert = await screen.findByRole('alert')
  expect(alert.textContent).toContain("don't have access")
  expect(alert.textContent).not.toContain('internal detail')
  expect(screen.queryByRole('listitem')).toBeNull()
})
