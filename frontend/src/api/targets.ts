export const PLATFORM = { id: 'google_maps', label: 'Google Maps' } as const

export type AnalysisTarget = {
  id: string
  name: string
  platform: string
  source_url: string
  created_at: string
}

export type NewTarget = { name: string; sourceUrl: string }

export class TargetError extends Error {
  readonly status: number

  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

const MESSAGES: Record<number, string> = {
  400: 'Check the target name and Google Maps URL, then try again.',
  401: 'Your session has expired. Please sign in again.',
}
const FALLBACK = 'Unable to create the target right now. Please try again.'

export async function createTarget(accessToken: string, target: NewTarget): Promise<AnalysisTarget> {
  let response: Response
  try {
    response = await fetch('/api/targets', {
      method: 'POST',
      headers: { Authorization: `Bearer ${accessToken}`, 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: target.name, platform: PLATFORM.id, source_url: target.sourceUrl }),
    })
  } catch {
    throw new TargetError(0, 'Unable to connect. Check your connection and try again.')
  }
  if (!response.ok) throw new TargetError(response.status, MESSAGES[response.status] ?? FALLBACK)
  return response.json()
}
