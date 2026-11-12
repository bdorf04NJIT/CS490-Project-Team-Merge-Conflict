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

// The most recent persisted IngestionRun for a target, as returned by the backend.
// Only `status` is guaranteed; the other fields are shown when present.
export type IngestionState = {
  status: string
  total_count?: number
  imported_count?: number
  skipped_count?: number
  message?: string | null
  completed_at?: string
}

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

export type Review = {
  id: string
  text: string
  rating: number
  reviewer_name: string | null
  review_date: string | null
}

const REVIEWS_FALLBACK = 'Unable to load reviews right now. Please try again.'

export async function listReviews(accessToken: string, targetId: string): Promise<Review[]> {
  let response: Response
  try {
    response = await fetch(`/api/targets/${encodeURIComponent(targetId)}/reviews`, {
      headers: { Authorization: `Bearer ${accessToken}` },
    })
  } catch {
    throw new TargetError(0, 'Unable to connect. Check your connection and try again.')
  }
  if (!response.ok) {
    throw new TargetError(response.status, GET_MESSAGES[response.status] ?? REVIEWS_FALLBACK)
  }
  const body: { reviews?: Review[] } = await response.json()
  if (!Array.isArray(body?.reviews)) throw new TargetError(response.status, REVIEWS_FALLBACK)
  return body.reviews
}

export type IngestionRequest = {
  target_id: string
  status: string
  run_status?: 'succeeded' | 'partial' | 'failed'
  imported_count?: number
  skipped_count?: number
}

const INGEST_MESSAGES: Record<number, string> = {
  400: "This target's source can't be ingested. Check that it has a valid Google Maps URL.",
  401: 'Your session has expired. Please sign in again.',
  404: "This analysis target doesn't exist or you don't have access to it.",
  503: "Review ingestion isn't available right now. Please try again later.",
  422: 'The source did not return usable written reviews.',
}
const INGEST_FALLBACK = 'Unable to start ingestion right now. Please try again.'

export async function startIngestion(
  accessToken: string,
  targetId: string,
): Promise<IngestionRequest> {
  let response: Response
  try {
    // No body: the backend always ingests from the target's saved source URL.
    response = await fetch(`/api/targets/${encodeURIComponent(targetId)}/ingestions`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${accessToken}` },
    })
  } catch {
    throw new TargetError(0, 'Unable to connect. Check your connection and try again.')
  }
  if (!response.ok) {
    throw new TargetError(response.status, INGEST_MESSAGES[response.status] ?? INGEST_FALLBACK)
  }
  return response.json()
}

export const STAR_VALUES = ['5', '4', '3', '2', '1'] as const

export type ReviewSummary = {
  review_count: number
  average_rating: number | null
  rating_distribution: Record<(typeof STAR_VALUES)[number], number>
}

const SUMMARY_FALLBACK = 'Unable to load the review summary right now. Please try again.'

function isReviewSummary(body: unknown): body is ReviewSummary {
  const summary = body as Partial<ReviewSummary> | null
  return (
    typeof summary?.review_count === 'number' &&
    (summary.average_rating === null || typeof summary.average_rating === 'number') &&
    STAR_VALUES.every((star) => typeof summary.rating_distribution?.[star] === 'number')
  )
}

export async function getReviewSummary(
  accessToken: string,
  targetId: string,
): Promise<ReviewSummary> {
  let response: Response
  try {
    response = await fetch(`/api/targets/${encodeURIComponent(targetId)}/summary`, {
      headers: { Authorization: `Bearer ${accessToken}` },
    })
  } catch {
    throw new TargetError(0, 'Unable to connect. Check your connection and try again.')
  }
  if (!response.ok) {
    throw new TargetError(response.status, GET_MESSAGES[response.status] ?? SUMMARY_FALLBACK)
  }
  const body: unknown = await response.json()
  if (!isReviewSummary(body)) throw new TargetError(response.status, SUMMARY_FALLBACK)
  return body
}

// --- Review Q&A (S2-009) ---------------------------------------------------
// The user asks a natural-language question about the active target's reviews and
// ReviewLens (the LLM) answers from those reviews only. The answer contract mirrors
// the system prompt in backend/app/services/qa_prompt.py: the model replies with a
// status, an answer, and the ids of the reviews it used as evidence. The backend keeps
// only ids of reviews it actually supplied to the model (S2-011) and reports how many
// reviews the model was given in `reviews_considered`.

export const QA_STATUSES = ['answered', 'insufficient_evidence', 'out_of_scope'] as const
export type QaStatus = (typeof QA_STATUSES)[number]

export type QaAnswer = {
  status: QaStatus
  answer: string
  review_ids: string[]
  /** How many reviews were supplied to the model as evidence. */
  reviews_considered?: number
}

const QA_MESSAGES: Record<number, string> = {
  400: 'Enter a question, then ask again.',
  401: 'Your session has expired. Please sign in again.',
  404: "This analysis target doesn't exist or you don't have access to it.",
  422: 'There are no reviews to answer from yet. Ingest reviews first.',
  503: "The review assistant isn't available right now. Please try again later.",
}
const QA_FALLBACK = 'Unable to answer that right now. Please try again.'

function isQaAnswer(body: unknown): body is QaAnswer {
  const answer = body as Partial<QaAnswer> | null
  return (
    typeof answer?.answer === 'string' &&
    typeof answer.status === 'string' &&
    (QA_STATUSES as readonly string[]).includes(answer.status) &&
    Array.isArray(answer.review_ids) &&
    answer.review_ids.every((id) => typeof id === 'string') &&
    (answer.reviews_considered === undefined ||
      (Number.isInteger(answer.reviews_considered) && answer.reviews_considered >= 0))
  )
}

export async function askQuestion(
  accessToken: string,
  targetId: string,
  question: string,
): Promise<QaAnswer> {
  let response: Response
  try {
    response = await fetch(`/api/targets/${encodeURIComponent(targetId)}/questions`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${accessToken}`, 'Content-Type': 'application/json' },
      body: JSON.stringify({ question }),
    })
  } catch {
    throw new TargetError(0, 'Unable to connect. Check your connection and try again.')
  }
  if (!response.ok) {
    throw new TargetError(response.status, QA_MESSAGES[response.status] ?? QA_FALLBACK)
  }
  const body: unknown = await response.json()
  if (!isQaAnswer(body)) throw new TargetError(response.status, QA_FALLBACK)
  return body
}
