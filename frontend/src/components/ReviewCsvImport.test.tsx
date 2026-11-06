// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import ReviewCsvImport from './ReviewCsvImport'

function reply(status: number, body: unknown = {}) {
  return { ok: status >= 200 && status < 300, status, json: async () => body } as Response
}

async function upload(status: number, body: unknown = {}) {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(reply(status, body)))
  const onFinished = vi.fn()
  render(<ReviewCsvImport accessToken="tok" targetId="t1" onFinished={onFinished} />)
  const file = new File(['review_text,rating\nGreat,5\n'], 'reviews.csv', { type: 'text/csv' })
  await userEvent.upload(screen.getByLabelText(/Review CSV/), file)
  await userEvent.click(screen.getByRole('button', { name: 'Import CSV reviews' }))
  return onFinished
}

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

describe('ReviewCsvImport', () => {
  it('confirms a successful import in green and refreshes the workspace', async () => {
    const run = { status: 'succeeded', imported_count: 2, skipped_count: 0 }
    const onFinished = await upload(201, { run })
    const notice = await screen.findByRole('status')
    expect(notice.textContent).toContain('Imported 2 reviews (0 skipped)')
    expect(notice.className).toContain('text-green-800')
    expect(onFinished).toHaveBeenCalledOnce()
  })

  it('shows a partial import in amber', async () => {
    const run = { status: 'partial', imported_count: 2, skipped_count: 1 }
    await upload(201, { run })
    const notice = await screen.findByRole('status')
    expect(notice.textContent).toContain('(1 skipped)')
    expect(notice.className).toContain('text-amber-900')
  })

  it('refreshes the workspace after a rejected import, which is recorded as a failed run', async () => {
    const onFinished = await upload(422)
    expect((await screen.findByRole('alert')).textContent).toContain('did not contain usable')
    expect(onFinished).toHaveBeenCalledOnce()
  })

  it('does not refresh when the session has expired', async () => {
    const onFinished = await upload(401)
    expect((await screen.findByRole('alert')).textContent).toContain('session expired')
    expect(onFinished).not.toHaveBeenCalled()
  })
})
