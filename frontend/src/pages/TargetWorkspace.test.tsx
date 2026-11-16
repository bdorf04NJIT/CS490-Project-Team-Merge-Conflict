// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import TargetWorkspace from './TargetWorkspace'

const TARGET = {
  id: 't1',
  name: "Joe's Coffee",
  platform: 'google_maps',
  source_url: 'https://www.google.com/maps/place/joes',
  created_at: '2026-01-02T00:00:00+00:00',
  latest_ingestion: null,
}

function reply(status: number, body: unknown = {}) {
  return { ok: status >= 200 && status < 300, status, json: async () => body } as Response
}

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

describe('TargetWorkspace', () => {
  it('identifies the target and shows its platform, source, state and ingestion path', async () => {
    const fetchMock = vi.fn().mockResolvedValue(reply(200, TARGET))
    vi.stubGlobal('fetch', fetchMock)
    render(<TargetWorkspace accessToken="tok-123" targetId="t1" onBack={() => {}} />)

    expect(await screen.findByRole('heading', { name: "Joe's Coffee" })).toBeTruthy()
    expect(screen.getByText('Google Maps')).toBeTruthy()
    const source = screen.getByRole('link', { name: TARGET.source_url })
    expect(source.getAttribute('href')).toBe(TARGET.source_url)
    expect(source.getAttribute('rel')).toContain('noopener')
    expect(screen.getByText(/No reviews have been ingested yet/)).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Start ingestion' })).toBeTruthy()
    expect(fetchMock).toHaveBeenCalledWith('/api/targets/t1', {
      headers: { Authorization: 'Bearer tok-123' },
    })
  })

  it('shows the current ingestion state when one exists', async () => {
    const body = { ...TARGET, latest_ingestion: { status: 'failed' } }
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(reply(200, body)))
    render(<TargetWorkspace accessToken="tok" targetId="t1" onBack={() => {}} />)
    expect(await screen.findByText('Last ingestion failed')).toBeTruthy()
  })

  it.each([
    ['succeeded', 'Last ingestion succeeded', 'Added 4 new reviews.'],
    ['partial', 'Last ingestion partially succeeded', '4 of 5 records were skipped'],
    ['failed', 'Last ingestion failed', 'The source did not respond.'],
  ])('shows a persisted %s run from the workspace response', async (status, label, detail) => {
    const run = {
      status,
      total_count: status === 'failed' ? 0 : 5,
      imported_count: status === 'failed' ? 0 : 4,
      skipped_count: status === 'partial' ? 4 : 0,
      message: status === 'failed' ? 'The source did not respond.' : 'Import succeeded.',
      completed_at: '2026-11-06T15:04:00+00:00',
    }
    const fetchMock = vi.fn((url: string) =>
      Promise.resolve(
        url.endsWith('/summary')
          ? reply(500)
          : url.endsWith('/reviews')
            ? reply(200, { reviews: [] })
            : reply(200, { ...TARGET, latest_ingestion: run }),
      ),
    )
    vi.stubGlobal('fetch', fetchMock)
    render(<TargetWorkspace accessToken="tok" targetId="t1" onBack={() => {}} />)
    expect(await screen.findByText(label)).toBeTruthy()
    expect(document.body.textContent).toContain(detail)
  })

  it('reloads the persisted status after a refused ingestion and keeps the error visible', async () => {
    const succeeded = { ...TARGET, latest_ingestion: { status: 'succeeded' } }
    const failed = { ...TARGET, latest_ingestion: { status: 'failed', message: 'Try later.' } }
    let workspace = succeeded
    const fetchMock = vi.fn((url: string, init?: RequestInit) => {
      if (init?.method === 'POST') {
        workspace = failed
        return Promise.resolve(reply(503, { error: {} }))
      }
      if (url.endsWith('/summary') || url.endsWith('/reviews')) return Promise.resolve(reply(500))
      return Promise.resolve(reply(200, workspace))
    })
    vi.stubGlobal('fetch', fetchMock)
    render(<TargetWorkspace accessToken="tok" targetId="t1" onBack={() => {}} />)

    expect(await screen.findByText('Last ingestion succeeded')).toBeTruthy()
    await userEvent.click(screen.getByRole('button', { name: 'Start ingestion' }))

    expect(await screen.findByText('Last ingestion failed')).toBeTruthy()
    expect(screen.queryByText('Last ingestion succeeded')).toBeNull()
    expect(screen.getByText(/isn't available right now/)).toBeTruthy()
    const workspaceLoads = fetchMock.mock.calls.filter(([url]) => url === '/api/targets/t1')
    expect(workspaceLoads).toHaveLength(2)
  })

  it('does not reload the workspace when the session has expired', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(reply(200, TARGET))
      .mockResolvedValueOnce(reply(401, { error: {} }))
    vi.stubGlobal('fetch', fetchMock)
    render(<TargetWorkspace accessToken="tok" targetId="t1" onBack={() => {}} />)
    await userEvent.click(await screen.findByRole('button', { name: 'Start ingestion' }))
    expect((await screen.findByRole('alert')).textContent).toContain('session has expired')
    expect(fetchMock).toHaveBeenCalledTimes(2)
  })

  it('reports a partially successful ingestion with an amber notice', async () => {
    const partial = {
      target_id: 't1',
      status: 'accepted',
      run_status: 'partial',
      imported_count: 3,
      skipped_count: 2,
      skip_reasons: { missing_text: 2 },
    }
    const fetchMock = vi.fn((url: string, init?: RequestInit) =>
      Promise.resolve(
        init?.method === 'POST'
          ? reply(200, partial)
          : url.endsWith('/summary') || url.endsWith('/reviews')
            ? reply(500)
            : reply(200, TARGET),
      ),
    )
    vi.stubGlobal('fetch', fetchMock)
    render(<TargetWorkspace accessToken="tok" targetId="t1" onBack={() => {}} />)
    await userEvent.click(await screen.findByRole('button', { name: 'Start ingestion' }))
    const notice = await screen.findByText(
      'Imported 3 reviews. 2 records were skipped (2 missing review text) and not included in the review dataset.',
    )
    expect(notice.className).toContain('bg-amber-50')
  })

  it('shows the review summary and reviews once an ingestion has run', async () => {
    const body = { ...TARGET, latest_ingestion: { status: 'succeeded' } }
    const summary = {
      target_id: 't1',
      review_count: 5,
      average_rating: 3.4,
      rating_distribution: { '1': 1, '2': 1, '3': 0, '4': 1, '5': 2 },
      latest_ingestion: { status: 'succeeded' },
    }
    const fetchMock = vi.fn((url: string) =>
      Promise.resolve(
        url.endsWith('/summary')
          ? reply(200, summary)
          : url.endsWith('/reviews')
            ? reply(200, { reviews: [] })
            : reply(200, body),
      ),
    )
    vi.stubGlobal('fetch', fetchMock)
    render(<TargetWorkspace accessToken="tok" targetId="t1" onBack={() => {}} />)

    expect(await screen.findByRole('heading', { name: 'Review summary' })).toBeTruthy()
    expect(await screen.findByText('3.4')).toBeTruthy()
    expect(fetchMock).toHaveBeenCalledWith('/api/targets/t1/summary', {
      headers: { Authorization: 'Bearer tok' },
    })
  })

  it('does not request a summary before any ingestion', async () => {
    const fetchMock = vi.fn().mockResolvedValue(reply(200, TARGET))
    vi.stubGlobal('fetch', fetchMock)
    render(<TargetWorkspace accessToken="tok" targetId="t1" onBack={() => {}} />)
    await screen.findByRole('heading', { name: "Joe's Coffee" })
    expect(screen.queryByRole('heading', { name: 'Review summary' })).toBeNull()
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it('shows a generic denial and no target data for another user or unknown id', async () => {
    const body = { error: { code: 'NOT_FOUND', message: "We couldn't find that analysis target." } }
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(reply(404, body)))
    render(<TargetWorkspace accessToken="tok" targetId="someone-elses" onBack={() => {}} />)

    expect((await screen.findByRole('alert')).textContent).toContain("don't have access")
    expect(screen.queryByRole('heading', { name: /Joe/ })).toBeNull()
    expect(screen.queryByRole('button', { name: 'Start ingestion' })).toBeNull()
  })

  it('encodes the id in the request URL', async () => {
    const fetchMock = vi.fn().mockResolvedValue(reply(404))
    vi.stubGlobal('fetch', fetchMock)
    render(<TargetWorkspace accessToken="tok" targetId="a/../b?x=1" onBack={() => {}} />)
    await screen.findByRole('alert')
    expect(fetchMock.mock.calls[0][0]).toBe('/api/targets/a%2F..%2Fb%3Fx%3D1')
  })

  it('shows a session message on 401', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(reply(401, { error: {} })))
    render(<TargetWorkspace accessToken="tok" targetId="t1" onBack={() => {}} />)
    expect((await screen.findByRole('alert')).textContent).toContain('session has expired')
  })

  it('recovers from a server failure with retry', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(reply(500))
      .mockResolvedValueOnce(reply(200, TARGET))
    vi.stubGlobal('fetch', fetchMock)
    render(<TargetWorkspace accessToken="tok" targetId="t1" onBack={() => {}} />)

    expect((await screen.findByRole('alert')).textContent).toContain('Unable to open this target')
    await userEvent.click(screen.getByRole('button', { name: 'Try again' }))
    expect(await screen.findByRole('heading', { name: "Joe's Coffee" })).toBeTruthy()
  })

  it('rejects a malformed response', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(reply(200, { unexpected: true })))
    render(<TargetWorkspace accessToken="tok" targetId="t1" onBack={() => {}} />)
    expect((await screen.findByRole('alert')).textContent).toContain('Unable to open this target')
  })

  it('goes back to the target list', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(reply(200, TARGET)))
    const onBack = vi.fn()
    render(<TargetWorkspace accessToken="tok" targetId="t1" onBack={onBack} />)
    await screen.findByRole('heading', { name: "Joe's Coffee" })
    await userEvent.click(screen.getByRole('button', { name: /Back to your targets/ }))
    expect(onBack).toHaveBeenCalledOnce()
  })

  it('starts ingestion for the open target and confirms it', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(reply(200, TARGET))
      .mockResolvedValueOnce(reply(202, { target_id: 't1', status: 'accepted' }))
    vi.stubGlobal('fetch', fetchMock)
    render(<TargetWorkspace accessToken="tok-123" targetId="t1" onBack={() => {}} />)

    await userEvent.click(await screen.findByRole('button', { name: 'Start ingestion' }))

    expect((await screen.findByText('Ingestion started for this target.')).textContent).toBeTruthy()
    expect(fetchMock).toHaveBeenLastCalledWith('/api/targets/t1/ingestions', {
      method: 'POST',
      headers: { Authorization: 'Bearer tok-123' },
    })
  })

  it('disables the button while the request is in flight', async () => {
    let finish: (r: Response) => void = () => {}
    const pending = new Promise<Response>((resolve) => (finish = resolve))
    const fetchMock = vi.fn().mockResolvedValueOnce(reply(200, TARGET)).mockReturnValueOnce(pending)
    vi.stubGlobal('fetch', fetchMock)
    render(<TargetWorkspace accessToken="tok" targetId="t1" onBack={() => {}} />)

    await userEvent.click(await screen.findByRole('button', { name: 'Start ingestion' }))
    const busy = screen.getByRole('button', { name: 'Starting ingestion...' }) as HTMLButtonElement
    expect(busy.disabled).toBe(true)
    await userEvent.click(busy)
    expect(fetchMock).toHaveBeenCalledTimes(2)

    finish(reply(202, { target_id: 't1', status: 'accepted' }))
    expect(await screen.findByText('Ingestion started for this target.')).toBeTruthy()
  })

  it.each([
    [404, "don't have access"],
    [400, 'valid Google Maps URL'],
    [401, 'session has expired'],
    [503, "isn't available right now"],
    [500, 'Unable to start ingestion'],
  ])('shows a clear error when ingestion is refused with %i', async (status, text) => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(reply(200, TARGET))
      .mockResolvedValueOnce(reply(200, TARGET))
      .mockResolvedValueOnce(reply(status, { error: { message: 'internal detail' } }))
    vi.stubGlobal('fetch', fetchMock)
    render(<TargetWorkspace accessToken="tok" targetId="t1" onBack={() => {}} />)

    await userEvent.click(await screen.findByRole('button', { name: 'Start ingestion' }))

    const alert = await screen.findByRole('alert')
    expect(alert.textContent).toContain(text)
    expect(alert.textContent).not.toContain('internal detail')
    expect(screen.queryByText('Ingestion started for this target.')).toBeNull()
    expect(
      (screen.getByRole('button', { name: 'Start ingestion' }) as HTMLButtonElement).disabled,
    ).toBe(false)
  })

  it('reports a network failure when starting ingestion', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(reply(200, TARGET))
      .mockRejectedValueOnce(new TypeError('offline'))
    vi.stubGlobal('fetch', fetchMock)
    render(<TargetWorkspace accessToken="tok" targetId="t1" onBack={() => {}} />)
    await userEvent.click(await screen.findByRole('button', { name: 'Start ingestion' }))
    expect((await screen.findByRole('alert')).textContent).toContain('Unable to connect')
  })
})
