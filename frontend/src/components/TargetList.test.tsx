// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import TargetList from './TargetList'

const TARGETS = [
  {
    id: 't1',
    name: "Joe's Coffee",
    platform: 'google_maps',
    source_url: 'https://www.google.com/maps/place/joes',
    created_at: '2026-01-02T00:00:00+00:00',
  },
  {
    id: 't2',
    name: 'Corner Bakery',
    platform: 'google_maps',
    source_url: 'https://www.google.com/maps/place/bakery',
    created_at: '2026-01-01T00:00:00+00:00',
  },
]

function reply(status: number, body: unknown = {}) {
  return { ok: status >= 200 && status < 300, status, json: async () => body } as Response
}

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

describe('TargetList', () => {
  it('shows name, platform and source for each target and sends the token', async () => {
    const fetchMock = vi.fn().mockResolvedValue(reply(200, { targets: TARGETS }))
    vi.stubGlobal('fetch', fetchMock)
    render(<TargetList accessToken="tok-123" />)

    expect(await screen.findByText("Joe's Coffee")).toBeTruthy()
    expect(screen.getByText('Corner Bakery')).toBeTruthy()
    expect(screen.getAllByText('Google Maps')).toHaveLength(2)
    expect(screen.getByText('https://www.google.com/maps/place/joes')).toBeTruthy()
    expect(fetchMock).toHaveBeenCalledWith('/api/targets', {
      headers: { Authorization: 'Bearer tok-123' },
    })
  })

  it('shows an empty state when the user has no targets', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(reply(200, { targets: [] })))
    render(<TargetList accessToken="tok" />)
    expect(await screen.findByText(/don't have any analysis targets yet/i)).toBeTruthy()
  })

  it('shows a session message on 401 and no target data', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(reply(401, { error: {} })))
    render(<TargetList accessToken="tok" />)
    expect((await screen.findByRole('alert')).textContent).toContain('session has expired')
    expect(screen.queryByRole('list')).toBeNull()
  })

  it('shows a plain-language error on a server failure and can retry', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(reply(500))
      .mockResolvedValueOnce(reply(200, { targets: TARGETS }))
    vi.stubGlobal('fetch', fetchMock)
    render(<TargetList accessToken="tok" />)

    expect((await screen.findByRole('alert')).textContent).toContain('Unable to load your targets')
    await userEvent.click(screen.getByRole('button', { name: 'Try again' }))
    expect(await screen.findByText("Joe's Coffee")).toBeTruthy()
    expect(fetchMock).toHaveBeenCalledTimes(2)
  })

  it('shows a connection message when the network is down', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')))
    render(<TargetList accessToken="tok" />)
    expect((await screen.findByRole('alert')).textContent).toContain('Unable to connect')
  })

  it('shows a plain-language error when the response is malformed', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(reply(200, { unexpected: true })))
    render(<TargetList accessToken="tok" />)
    expect((await screen.findByRole('alert')).textContent).toContain('Unable to load your targets')
  })
})

describe('TargetList navigation', () => {
  it('links each target to its workspace and opens it on click', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(reply(200, { targets: TARGETS })))
    const onOpen = vi.fn()
    render(<TargetList accessToken="tok" onOpen={onOpen} />)

    const link = await screen.findByRole('link', { name: /Joe's Coffee/ })
    expect(link.getAttribute('href')).toBe('/targets/t1')
    await userEvent.click(link)
    expect(onOpen).toHaveBeenCalledWith('t1')
  })
})
