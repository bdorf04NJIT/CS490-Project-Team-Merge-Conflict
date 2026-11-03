import { afterEach, expect, test, vi } from 'vitest'

afterEach(() => {
  vi.unstubAllEnvs()
  vi.resetModules()
})

test.each([['VITE_SUPABASE_URL'], ['VITE_SUPABASE_PUBLISHABLE_KEY']])(
  'fails with a clear message when %s is missing',
  async (name) => {
    vi.stubEnv('VITE_SUPABASE_URL', 'https://test.supabase.co')
    vi.stubEnv('VITE_SUPABASE_PUBLISHABLE_KEY', 'sb_publishable_test')
    vi.stubEnv(name, '')
    await expect(import('./supabase')).rejects.toThrow(
      'Set Supabase configuration in frontend/.env.local',
    )
  },
)

test('creates the client when both values are set', async () => {
  vi.stubEnv('VITE_SUPABASE_URL', 'https://test.supabase.co')
  vi.stubEnv('VITE_SUPABASE_PUBLISHABLE_KEY', 'sb_publishable_test')
  const { supabase } = await import('./supabase')
  expect(supabase).toBeDefined()
})
