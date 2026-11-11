// @vitest-environment jsdom
import { afterEach, expect, test, vi } from 'vitest'
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import TargetSwitcher from './TargetSwitcher'

const TARGETS = [
  { id: 'a', name: 'Battery Barn', platform: 'google_maps', source_url: 'x', created_at: 'x' },
  { id: 'b', name: 'Service Shack', platform: 'google_maps', source_url: 'y', created_at: 'y' },
]

function reply(status: number, body: unknown = {}) {
  return { ok: status >= 200 && status < 300, status, json: async () => body } as Response
}

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

test("lists the user's targets with the active one selected", async () => {
  const fetchMock = vi.fn().mockResolvedValue(reply(200, { targets: TARGETS }))
  vi.stubGlobal('fetch', fetchMock)
  render(<TargetSwitcher accessToken="tok" activeId="a" onSwitch={() => {}} />)

  const select = (await screen.findByLabelText('Switch target')) as HTMLSelectElement
  expect(select.value).toBe('a')
  expect(Array.from(select.options, (o) => o.textContent)).toEqual([
    'Battery Barn',
    'Service Shack',
  ])
  expect(fetchMock).toHaveBeenCalledWith('/api/targets', {
    headers: { Authorization: 'Bearer tok' },
  })
})

test('choosing another target asks to switch to it', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(reply(200, { targets: TARGETS })))
  const onSwitch = vi.fn()
  render(<TargetSwitcher accessToken="tok" activeId="a" onSwitch={onSwitch} />)

  await userEvent.selectOptions(await screen.findByLabelText('Switch target'), 'b')
  expect(onSwitch).toHaveBeenCalledWith('b')
})

test.each([
  ['only one target', reply(200, { targets: [TARGETS[0]] })],
  ['the list fails to load', reply(500)],
  ['the active target is not in the list', reply(200, { targets: [TARGETS[1], TARGETS[1]] })],
])('renders nothing when %s', async (_case, response) => {
  const fetchMock = vi.fn().mockResolvedValue(response)
  vi.stubGlobal('fetch', fetchMock)
  render(<TargetSwitcher accessToken="tok" activeId="a" onSwitch={() => {}} />)

  await waitFor(() => expect(fetchMock).toHaveBeenCalled())
  expect(screen.queryByLabelText('Switch target')).toBeNull()
})

test('renders nothing when the request never arrives', async () => {
  vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('offline')))
  render(<TargetSwitcher accessToken="tok" activeId="a" onSwitch={() => {}} />)
  await new Promise((r) => setTimeout(r, 0))
  expect(screen.queryByLabelText('Switch target')).toBeNull()
})
