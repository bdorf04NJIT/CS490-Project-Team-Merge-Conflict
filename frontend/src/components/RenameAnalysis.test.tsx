// @vitest-environment jsdom
import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import RenameAnalysis from './RenameAnalysis'

const renamed = {
  id: 'target-1',
  name: 'New name',
  platform: 'google_maps',
  source_url: 'https://www.google.com/maps/place/Joes+Coffee',
  created_at: '2026-11-01T12:00:00+00:00',
}

beforeEach(() => {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => renamed }),
  )
})
afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

function openEditor(currentName = 'Old name') {
  render(
    <RenameAnalysis
      accessToken="user-token"
      targetId="target-1"
      currentName={currentName}
      onRenamed={onRenamed}
    />,
  )
}

const onRenamed = vi.fn()
afterEach(() => onRenamed.mockReset())

test('closes when clicking outside the open editor', async () => {
  render(
    <div>
      <button type="button">outside</button>
      <RenameAnalysis
        accessToken="user-token"
        targetId="target-1"
        currentName="Old name"
        onRenamed={onRenamed}
      />
    </div>,
  )
  await userEvent.click(screen.getByRole('button', { name: 'Rename' }))
  expect(screen.getByLabelText('Analysis name')).toBeTruthy()
  await userEvent.click(screen.getByRole('button', { name: 'outside' }))
  expect(screen.queryByLabelText('Analysis name')).toBeNull()
  expect(fetch).not.toHaveBeenCalled()
})

test('keeps the Rename trigger visible while the editor is open below it', async () => {
  openEditor()
  await userEvent.click(screen.getByRole('button', { name: 'Rename' }))
  // The trigger stays in place; the editor appears below it rather than replacing it.
  expect(screen.getByRole('button', { name: 'Rename' })).toBeTruthy()
  expect(screen.getByLabelText('Analysis name')).toBeTruthy()
})

test('renames the analysis and reports the updated target', async () => {
  openEditor()
  await userEvent.click(screen.getByRole('button', { name: 'Rename' }))
  const input = screen.getByLabelText('Analysis name')
  await userEvent.clear(input)
  await userEvent.type(input, 'New name')
  await userEvent.click(screen.getByRole('button', { name: 'Save' }))

  const [url, init] = vi.mocked(fetch).mock.calls[0]
  expect(url).toBe('/api/targets/target-1')
  expect(init?.method).toBe('PATCH')
  expect(init?.headers).toMatchObject({ Authorization: 'Bearer user-token' })
  expect(JSON.parse(String(init?.body))).toEqual({ name: 'New name' })
  expect(onRenamed).toHaveBeenCalledWith(renamed)
})

test('pre-fills the editor with the current name', async () => {
  openEditor('Joe Coffee')
  await userEvent.click(screen.getByRole('button', { name: 'Rename' }))
  expect((screen.getByLabelText('Analysis name') as HTMLInputElement).value).toBe('Joe Coffee')
})

test('rejects an empty name without calling the backend', async () => {
  openEditor()
  await userEvent.click(screen.getByRole('button', { name: 'Rename' }))
  await userEvent.clear(screen.getByLabelText('Analysis name'))
  await userEvent.click(screen.getByRole('button', { name: 'Save' }))
  expect(fetch).not.toHaveBeenCalled()
  expect(screen.getByText('Enter a name for this analysis.')).toBeTruthy()
  expect(onRenamed).not.toHaveBeenCalled()
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
  openEditor()
  await userEvent.click(screen.getByRole('button', { name: 'Rename' }))
  await userEvent.type(screen.getByLabelText('Analysis name'), ' more')
  await userEvent.click(screen.getByRole('button', { name: 'Save' }))
  expect(await screen.findByText(message)).toBeTruthy()
  expect(onRenamed).not.toHaveBeenCalled()
})

test('shows a not-found message when the analysis is not the user to rename', async () => {
  vi.mocked(fetch).mockResolvedValue({
    ok: false,
    status: 404,
    json: async () => ({ error: { code: 'NOT_FOUND', message: 'x' } }),
  } as Response)
  openEditor()
  await userEvent.click(screen.getByRole('button', { name: 'Rename' }))
  await userEvent.type(screen.getByLabelText('Analysis name'), ' x')
  await userEvent.click(screen.getByRole('button', { name: 'Save' }))
  expect((await screen.findByRole('alert')).textContent).toContain(
    "doesn't exist or you don't have access",
  )
  expect(onRenamed).not.toHaveBeenCalled()
})

test('cancel closes the editor without calling the backend', async () => {
  openEditor('Keep me')
  await userEvent.click(screen.getByRole('button', { name: 'Rename' }))
  await userEvent.type(screen.getByLabelText('Analysis name'), ' edited')
  await userEvent.click(screen.getByRole('button', { name: 'Cancel' }))
  expect(fetch).not.toHaveBeenCalled()
  expect(screen.queryByLabelText('Analysis name')).toBeNull()
  // Reopening shows the original name again, not the abandoned edit.
  await userEvent.click(screen.getByRole('button', { name: 'Rename' }))
  expect((screen.getByLabelText('Analysis name') as HTMLInputElement).value).toBe('Keep me')
})
