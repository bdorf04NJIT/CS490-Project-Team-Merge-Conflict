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
    expect(screen.getByText('No reviews have been ingested yet.')).toBeTruthy()
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
})
