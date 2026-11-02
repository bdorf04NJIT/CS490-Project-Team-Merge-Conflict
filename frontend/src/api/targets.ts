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

export async function createTarget(
  accessToken: string,
  target: NewTarget,
): Promise<AnalysisTarget> {
  let response: Response
  try {
    response = await fetch('/api/targets', {
      method: 'POST',
      headers: { Authorization: `Bearer ${accessToken}`, 'Content-Type': 'application/json' },
      body: JSON.stringify({
        name: target.name,
        platform: PLATFORM.id,
        source_url: target.sourceUrl,
      }),
    })
  } catch {
    throw new TargetError(0, 'Unable to connect. Check your connection and try again.')
  }
  if (!response.ok) throw new TargetError(response.status, MESSAGES[response.status] ?? FALLBACK)
  return response.json()
}

const LIST_MESSAGES: Record<number, string> = {
  401: 'Your session has expired. Please sign in again.',
}
const LIST_FALLBACK = 'Unable to load your targets right now. Please try again.'

export async function listTargets(accessToken: string): Promise<AnalysisTarget[]> {
  let response: Response
  try {
    response = await fetch('/api/targets', {
      headers: { Authorization: `Bearer ${accessToken}` },
    })
  } catch {
    throw new TargetError(0, 'Unable to connect. Check your connection and try again.')
  }
  if (!response.ok) {
    throw new TargetError(response.status, LIST_MESSAGES[response.status] ?? LIST_FALLBACK)
  }

  const body: { targets?: AnalysisTarget[] } = await response.json()
  if (!Array.isArray(body.targets)) throw new TargetError(response.status, LIST_FALLBACK)
  return body.targets
}
