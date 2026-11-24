// @vitest-environment jsdom
import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import SaveAsAnalysis from './SaveAsAnalysis'

const copy = {
  id: 'copy-1',
  name: 'Joe backup',
  platform: 'google_maps',
  source_url: 'https://www.google.com/maps/place/Joes+Coffee',
  created_at: '2026-11-01T12:00:00+00:00',
}

const onSaved = vi.fn()

beforeEach(() => {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue({ ok: true, status: 201, json: async () => copy }),
  )
})
afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
  onSaved.mockReset()
})

function open(sourceName = 'Joe Coffee') {
  render(
    <SaveAsAnalysis
      accessToken="user-token"
      targetId="target-1"
      sourceName={sourceName}
      onSaved={onSaved}
    />,
  )
}

test('creates a copy and reports the new analysis', async () => {
  open()
  await userEvent.click(screen.getByRole('button', { name: 'Save as' }))
  const input = screen.getByLabelText('New analysis name')
  await userEvent.clear(input)
  await userEvent.type(input, 'Joe backup')
  await userEvent.click(screen.getByRole('button', { name: 'Create copy' }))

  const [url, init] = vi.mocked(fetch).mock.calls[0]
  expect(url).toBe('/api/targets/target-1/copies')
  expect(init?.method).toBe('POST')
  expect(init?.headers).toMatchObject({ Authorization: 'Bearer user-token' })
  expect(JSON.parse(String(init?.body))).toEqual({ name: 'Joe backup' })
  expect(onSaved).toHaveBeenCalledWith(copy)
})

test('suggests a copy name based on the source', async () => {
  open('Blue Bottle')
  await userEvent.click(screen.getByRole('button', { name: 'Save as' }))
  expect((screen.getByLabelText('New analysis name') as HTMLInputElement).value).toBe(
    'Blue Bottle (copy)',
  )
})

test('rejects an empty name without calling the backend', async () => {
  open()
  await userEvent.click(screen.getByRole('button', { name: 'Save as' }))
  await userEvent.clear(screen.getByLabelText('New analysis name'))
  await userEvent.click(screen.getByRole('button', { name: 'Create copy' }))
  expect(fetch).not.toHaveBeenCalled()
  expect(screen.getByText('Enter a name for the new analysis.')).toBeTruthy()
  expect(onSaved).not.toHaveBeenCalled()
})

test('shows the backend validation message on a rejected name', async () => {
  const message = 'The name must be 255 characters or fewer.'
  vi.mocked(fetch).mockResolvedValue({
    ok: false,
    status: 400,
    json: async () => ({
      error: { code: 'VALIDATION_ERROR', message: 'x', fields: { name: message } },
    }),
  } as Response)
  open()
  await userEvent.click(screen.getByRole('button', { name: 'Save as' }))
  await userEvent.type(screen.getByLabelText('New analysis name'), ' more')
  await userEvent.click(screen.getByRole('button', { name: 'Create copy' }))
  expect(await screen.findByText(message)).toBeTruthy()
  expect(onSaved).not.toHaveBeenCalled()
})

test('cancel closes the editor without calling the backend', async () => {
  open()
  await userEvent.click(screen.getByRole('button', { name: 'Save as' }))
  await userEvent.click(screen.getByRole('button', { name: 'Cancel' }))
  expect(fetch).not.toHaveBeenCalled()
  expect(screen.queryByLabelText('New analysis name')).toBeNull()
})
