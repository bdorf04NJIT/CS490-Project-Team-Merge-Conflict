export const PLATFORM = { id: 'google_maps', label: 'Google Maps' } as const

export type AnalysisTarget = {
  id: string
  name: string
  platform: string
  source_url: string
  created_at: string
}

export type NewTarget = { name: string; sourceUrl: string }

export type FieldErrors = Partial<Record<'name' | 'source_url' | 'platform', string>>

export class TargetError extends Error {
  readonly status: number
  readonly fields: FieldErrors

  constructor(status: number, message: string, fields: FieldErrors = {}) {
    super(message)
    this.status = status
    this.fields = fields
  }
}

const MESSAGES: Record<number, string> = {
  400: 'Check the target name and Google Maps URL, then try again.',
  401: 'Your session has expired. Please sign in again.',
}
const FALLBACK = 'Unable to create the target right now. Please try again.'

async function readFieldErrors(response: Response): Promise<FieldErrors> {
  try {
    const body = await response.json()
    const fields = body?.error?.fields ?? {}
    const result: FieldErrors = {}
    for (const key of ['name', 'source_url', 'platform'] as const) {
      if (typeof fields[key] === 'string') result[key] = fields[key]
    }
    return result
  } catch {
    return {}
  }
}

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
  if (!response.ok) {
    const fields = response.status === 400 ? await readFieldErrors(response) : {}
    throw new TargetError(response.status, MESSAGES[response.status] ?? FALLBACK, fields)
  }
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

export type IngestionState = { status: string }

export type TargetWorkspace = AnalysisTarget & { latest_ingestion: IngestionState | null }

const GET_MESSAGES: Record<number, string> = {
  401: 'Your session has expired. Please sign in again.',
  404: "This analysis target doesn't exist or you don't have access to it.",
}
const GET_FALLBACK = 'Unable to open this target right now. Please try again.'

export async function getTarget(accessToken: string, id: string): Promise<TargetWorkspace> {
  let response: Response
  try {
    response = await fetch(`/api/targets/${encodeURIComponent(id)}`, {
      headers: { Authorization: `Bearer ${accessToken}` },
    })
  } catch {
    throw new TargetError(0, 'Unable to connect. Check your connection and try again.')
  }
  if (!response.ok) {
    throw new TargetError(response.status, GET_MESSAGES[response.status] ?? GET_FALLBACK)
  }

  const body: Partial<TargetWorkspace> = await response.json()
  if (typeof body?.id !== 'string' || typeof body.name !== 'string')
    throw new TargetError(response.status, GET_FALLBACK)
  return { ...body, latest_ingestion: body.latest_ingestion ?? null } as TargetWorkspace
}
