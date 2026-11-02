// @vitest-environment jsdom
import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import CreateTargetForm from './CreateTargetForm'

const created = {
  id: 'target-1',
  name: "Joe's Coffee",
  platform: 'google_maps',
  source_url: 'https://www.google.com/maps/place/Joes+Coffee',
  created_at: '2026-11-01T12:00:00+00:00',
}

beforeEach(() => {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue({ ok: true, status: 201, json: async () => created }),
  )
})
afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

async function fillAndSubmit() {
  render(<CreateTargetForm accessToken="user-token" />)
  await userEvent.type(screen.getByLabelText('Business or place name'), "  Joe's Coffee  ")
  await userEvent.type(screen.getByLabelText('Google Maps URL'), created.source_url)
  await userEvent.click(screen.getByRole('button', { name: 'Create target' }))
}

test('shows the fixed platform before submission', () => {
  render(<CreateTargetForm accessToken="user-token" />)
  expect(screen.getByText('Google Maps', { selector: 'span' })).toBeTruthy()
})

test('creates a target with the user token and confirms it', async () => {
  await fillAndSubmit()
  expect(await screen.findByRole('status')).toHaveProperty('textContent', 'Analysis target created')
  expect(screen.getByText("Joe's Coffee")).toBeTruthy()
  expect(screen.getByText(created.source_url)).toBeTruthy()

  const [url, init] = vi.mocked(fetch).mock.calls[0]
  expect(url).toBe('/api/targets')
  expect(init?.method).toBe('POST')
  expect(init?.headers).toMatchObject({ Authorization: 'Bearer user-token' })
  expect(JSON.parse(String(init?.body))).toEqual({
    name: "Joe's Coffee",
    platform: 'google_maps',
    source_url: created.source_url,
  })
})

test('lets the user start another target after confirmation', async () => {
  await fillAndSubmit()
  await userEvent.click(await screen.findByRole('button', { name: 'Create another target' }))
  expect((screen.getByLabelText('Business or place name') as HTMLInputElement).value).toBe('')
})

test('does not submit when required fields are empty and says which are missing', async () => {
  render(<CreateTargetForm accessToken="user-token" />)
  await userEvent.type(screen.getByLabelText('Business or place name'), '   ')
  await userEvent.click(screen.getByRole('button', { name: 'Create target' }))
  expect(fetch).not.toHaveBeenCalled()
  expect(screen.getByText('Enter the business or place name.')).toBeTruthy()
  expect(screen.getByText('Enter the Google Maps URL for this place.')).toBeTruthy()
  expect(screen.getByLabelText('Business or place name').getAttribute('aria-invalid')).toBe('true')
})

test('shows the backend field message under the URL input', async () => {
  const message = 'Enter a Google Maps link, such as https://www.google.com/maps/place/...'
  vi.mocked(fetch).mockResolvedValue({
    ok: false,
    status: 400,
    json: async () => ({
      error: { code: 'VALIDATION_ERROR', message: 'x', fields: { source_url: message } },
    }),
  } as Response)
  render(<CreateTargetForm accessToken="user-token" />)
  await userEvent.type(screen.getByLabelText('Business or place name'), "Joe's Coffee")
  await userEvent.type(screen.getByLabelText('Google Maps URL'), 'https://www.yelp.com/biz/joes')
  await userEvent.click(screen.getByRole('button', { name: 'Create target' }))

  const url = screen.getByLabelText('Google Maps URL')
  expect((await screen.findByText(message)).id).toBe('target-url-error')
  expect(url.getAttribute('aria-invalid')).toBe('true')
  expect(url.getAttribute('aria-describedby')).toBe('target-url-error')
  expect(screen.getByLabelText('Business or place name').getAttribute('aria-invalid')).toBe('false')
  expect(screen.queryByRole('status')).toBeNull()
})

test('a malformed URL is sent to the backend instead of being blocked by the browser', async () => {
  render(<CreateTargetForm accessToken="user-token" />)
  await userEvent.type(screen.getByLabelText('Business or place name'), "Joe's Coffee")
  await userEvent.type(screen.getByLabelText('Google Maps URL'), 'not a url')
  await userEvent.click(screen.getByRole('button', { name: 'Create target' }))
  expect(fetch).toHaveBeenCalledTimes(1)
})

test('field errors clear after a successful retry', async () => {
  vi.mocked(fetch).mockResolvedValueOnce({
    ok: false,
    status: 400,
    json: async () => ({
      error: { code: 'VALIDATION_ERROR', message: 'x', fields: { name: 'Bad name.' } },
    }),
  } as Response)
  await fillAndSubmit()
  expect(await screen.findByText('Bad name.')).toBeTruthy()
  await userEvent.click(screen.getByRole('button', { name: 'Create target' }))
  expect(await screen.findByRole('status')).toBeTruthy()
  expect(screen.queryByText('Bad name.')).toBeNull()
})

test.each([
  [400, 'Check the target name and Google Maps URL'],
  [401, 'Your session has expired'],
  [500, 'Unable to create the target right now'],
])('backend %i shows a readable error and no confirmation', async (status, message) => {
  vi.mocked(fetch).mockResolvedValue({
    ok: false,
    status,
    json: async () => ({ error: { code: 'X', message: 'internal detail' } }),
  } as Response)
  await fillAndSubmit()
  expect((await screen.findByRole('alert')).textContent).toContain(message)
  expect(screen.queryByText('internal detail')).toBeNull()
  expect(screen.queryByRole('status')).toBeNull()
  expect((screen.getByLabelText('Google Maps URL') as HTMLInputElement).value).toBe(
    created.source_url,
  )
})

test('network failure shows a connection error', async () => {
  vi.mocked(fetch).mockRejectedValue(new TypeError('Failed to fetch'))
  await fillAndSubmit()
  expect((await screen.findByRole('alert')).textContent).toContain('Unable to connect')
  expect(screen.queryByRole('status')).toBeNull()
})
