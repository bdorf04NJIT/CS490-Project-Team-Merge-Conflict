
> /clear

> Ticket S1-019
  Outcome:
  An authenticated user can initiate review ingestion for an AnalysisTarget
  they own using the source mechanism supported by the team.

  Technical Guidance:

  The team may implement either:

  Ingestion from a publicly accessible target URL, or
  A practical data-import mechanism appropriate to the supported review
  platform.
  The ingestion request must reference an existing AnalysisTarget.

  Before ingestion begins, the backend must verify:

  The request is authenticated.
  The AnalysisTarget exists.
  The authenticated user owns the AnalysisTarget.
  Required source information is present.
  A request against another user's target must fail before review processing
  occurs.

  Rules: S1-BR-018, S1-BR-019, S1-BR-025

● I'll start by looking at how the project is set up and how earlier tickets
  were built.

  Ran 3 shell commands (ctrl+o to expand)

● Opus 5.5's safeguards stopped the response above · continuing once
  with that noted

● That last response was stopped by a safety classifier, so I won't repeat it.
  Picking back up on S1-019: next I'll read the ticket context and the workspace
  page this ticket builds on.

  Ran 2 shell commands (ctrl+o to expand)

● Next I'll read S1-022 through S1-025 so this ticket doesn't spill into later
  work like ingestion runs and fetching reviews.

  Ran 2 shell commands (ctrl+o to expand)

● A local feature/S1-019-submit-ingestion branch already exists, so I'll check
  what's on it before doing anything.

  Ran 1 shell command (ctrl+o to expand)

● The existing S1-019 branch has no commits of its own; it sits one commit
  behind HEAD. I'll switch to it and fast-forward it, then look at the frontend
  tests.

  Ran 1 shell command (ctrl+o to expand)

● I'll build the submit endpoint and pre-ingestion checks using the saved Google
  Maps URL, plus a review-source adapter that S1-020 will later wire up to
  SerpApi—starting with the backend now.

● Write(backend\app\adapters\review_source.py)
  ⎿  Wrote 14 lines to backend\app\adapters\review_source.py
      1 """Boundary to the external review source (Google Maps reviews).
      2
      3 The ingestion service hands a verified target to this adapter onl
        y after the
      4 authentication, ownership, and source checks pass. Fetching revie
        ws from the
      5 source is implemented in S1-020; until then the adapter reports t
        hat ingestion
      6 is unavailable instead of pretending to succeed or substituting s
        ample data.
     … +8 lines (ctrl+o to expand)

● Update(backend\app\errors.py)
  ⎿  Added 6 lines
      32      message = "Provide only name, platform, and a valid HTTP(S)
           source_url. Ownership is assigned automatically."
      33  
      34  
      35 +class IngestionUnavailable(AppError):                          
      36 +    status = 503                                               
      37 +    code = "INGESTION_UNAVAILABLE"                             
      38 +    message = "Review ingestion isn't available right now. Plea
         +se try again later."                                           
      39 +                                                               
      40 +                                                               
      41  def _body(code, message, fields=None):
      42      error = {"code": code, "message": message}
      43      if fields:

● Next, in the targets service I'll move the URL check and the owner-scoped
  lookup into shared helpers so ingestion can reuse them.

● Bash(cd "c:/Users/bdorf/VsCode/NJITSenSem1/CS490/CS490-Project-Team-Merge-Conf
      lict/backend"; python - <<'EOF'
      from pathlib import Path…)
  ⎿  Updated backend\app\services\targets.py (+45 -28)
      44      return False
      45  
      46  
      47 +def source_url_error(source_url):                              
      48 +    """Return a user-facing message if source_url is not a usab
         +le Google Maps URL."""                                         
      49 +    if not source_url:                                         
      50 +        return MESSAGES["url_missing"]                         
      51 +    if len(source_url) > MAX_URL:                              
      52 +        return MESSAGES["url_long"]                            
      53 +    try:                                                       
      54 +        url = urlsplit(source_url)                             
      55 +        usable = (                                             
      56 +            url.scheme in {"http", "https"}                    
      57 +            and bool(url.hostname)                             
      58 +            and not url.username                               
      59 +            and not url.password                               
      60 +            and " " not in source_url                          
      61 +        )                                                      
      62 +        _ = url.port  # invalid port numbers raise ValueError  
      63 +    except ValueError:                                         
      64 +        usable = False                                         
      65 +    if not usable:                                             
      66 +        return MESSAGES["url_invalid"]                         
      67 +    if not is_google_maps_url(url):                            
      68 +        return MESSAGES["url_not_maps"]                        
      69 +    return None                                                
      70 +                                                               
      71 +                                                               
      72  def _text(payload, field):
      73      value = payload.get(field)
      74      return value.strip() if isinstance(value, str) else ""
     ...
      87          errors["name"] = MESSAGES["name_long"]
      88  
      89      source_url = _text(payload, "source_url")
      65 -    if not source_url:                                         
      66 -        errors["source_url"] = MESSAGES["url_missing"]         
      67 -    elif len(source_url) > MAX_URL:                            
      68 -        errors["source_url"] = MESSAGES["url_long"]            
      69 -    else:                                                      
      70 -        try:                                                   
     … 57 more lines (ctrl+o to expand)
  ⎿  (files that changed while this command ran, by the command or by
     another process; a convenience view, not a review or audit of the
     command)

● Bash(cd "c:/Users/bdorf/VsCode/NJITSenSem1/CS490/CS490-Project-Team-Merge-Conf
      lict/backend"; python - <<'EOF'
      from pathlib import Path…)
  ⎿  Updated backend\app\services\targets.py (+1 -6)
      141  
      142  
      143  def get_target(engine, *, owner_id, target_id):
      144 -    """Return one target only if owner_id owns it.            
      145 -                                                              
      146 -    The id and the owner are matched in the same query, so ano
          -ther user's target                                            
      147 -    and a target that does not exist both raise the same NotFo
          -und. A caller can                                             
      148 -    therefore not learn whether someone else's id exists.     
      149 -    """                                                       
      144 +    """Return one target only if owner_id owns it (see find_ow
          +ned_target)."""                                               
      145      with Session(engine) as session:
      146          row = find_owned_target(session, owner_id=owner_id, ta
           rget_id=target_id)
      147          # Ingestion runs are recorded starting in S1-023; unti
           l then there is none to report.

● Now the ingestion service and the route:

● Write(backend\app\services\ingestion.py)
  ⎿  Wrote 40 lines to backend\app\services\ingestion.py
       1 import logging
       2
       3 from sqlalchemy.orm import Session
       4
       5 from ..errors import ValidationError
       6 from .targets import find_owned_target, source_url_error
       7
       8 logger = logging.getLogger(__name__)
       9
      10 SOURCE_MESSAGE = (
     … +30 lines (ctrl+o to expand)

● Bash(cd "c:/Users/bdorf/VsCode/NJITSenSem1/CS490/CS490-Project-Team-Merge-Conf
      lict/backend"; python - <<'EOF'
      from pathlib import Path…)
  ⎿  Updated backend\app\__init__.py (+2 -0)
       5  from dotenv import load_dotenv
       6  from flask import Flask
       7  
       8 +from .adapters.review_source import UnconfiguredReviewSource   
       9  from .database import init_database
      10  from .errors import register_error_handlers
      11  from .routes import bp
     ...
      28      )
      29      register_error_handlers(app)
      30      init_database(app)
      31 +    app.extensions.setdefault("review_source", UnconfiguredRevi
         +ewSource())                                                    
      32      app.register_blueprint(bp)
      33      return app
  ⎿  Updated backend\app\routes.py (+15 -0)
      1  from flask import Blueprint, current_app, g, jsonify, request
      2  
      3  from .auth import require_auth
      4 +from .services.ingestion import start_ingestion                 
      5  from .services.targets import create_target, get_target, list_ta
         rgets
      6  
      7  bp = Blueprint("api", __name__, url_prefix="/api")
     ...
      43      # The URL id only says which target is requested; ownership
           is checked in the query.
      44      target = get_target(current_app.extensions["database"], own
          er_id=g.user_id, target_id=target_id)
      45      return jsonify(target)
      46 +                                                               
      47 +                                                               
      48 +@bp.post("/targets/<target_id>/ingestions")                    
      49 +@require_auth                                                  
      50 +def post_ingestion(target_id):                                 
      51 +    # Ownership, body, and source checks all run before the rev
         +iew source is called.                                          
      52 +    result = start_ingestion(                                  
      53 +        current_app.extensions["database"],                    
      54 +        current_app.extensions["review_source"],               
      55 +        owner_id=g.user_id,                                    
      56 +        target_id=target_id,                                   
      57 +        payload=request.get_json(silent=True),                 
      58 +    )                                                          
      59 +    return jsonify(result), 202                                

● Now the backend tests. A fake review source records every call, so each denial
  test can confirm that review processing never started.

● Write(backend\tests\test_ingestion_submit.py)
  ⎿  Wrote 164 lines to backend\tests\test_ingestion_submit.py
      1 import pytest
      2 from sqlalchemy import select, update
      3 from sqlalchemy.orm import Session
      4
      5 from app.adapters.review_source import UnconfiguredReviewSource
      6 from app.models import AnalysisTarget
      7
      8 SOURCE_URL = "https://www.google.com/maps/place/Coffee+Shop"
      9
     … +155 lines (ctrl+o to expand)

  Ran 1 shell command (ctrl+o to expand)

● All 128 tests pass. Ruff wants one formatting fix. After that, I'll
  temporarily remove the ownership filter to confirm the denial tests actually
  catch it, as the AI-development doc requires.

● Bash(cd "c:/Users/bdorf/VsCode/NJITSenSem1/CS490/CS490-Project-Team-Merge-Conf
      lict/backend"; PY=.venv/Scripts/python; $PY -m ruff format -q
      app/services/ingestion.py…)
  ⎿  Updated backend\app\services\ingestion.py (+1 -3)
       7  
       8  logger = logging.getLogger(__name__)
       9  
      10 -SOURCE_MESSAGE = (                                             
      11 -    "This target needs a valid Google Maps URL before reviews c
         -an be ingested."                                               
      12 -)                                                              
      10 +SOURCE_MESSAGE = "This target needs a valid Google Maps URL bef
         +ore reviews can be ingested."                                  
      11  
      12  
      13  def start_ingestion(engine, review_source, *, owner_id, target_
          id, payload):

● Tests fail correctly when either check is removed, confirming both are
  needed—I've restored them. Now I'll move on to the frontend, wiring up the API
  call and the Start ingestion button.

● Bash(cd "c:/Users/bdorf/VsCode/NJITSenSem1/CS490/CS490-Project-Team-Merge-Conf
      lict/frontend"; cat >> src/api/targets.ts <<'EOF'…)  ⎿  Updated frontend\src\api\targets.ts (+30 -0)
      119      throw new TargetError(response.status, GET_FALLBACK)
      120    return { ...body, latest_ingestion: body.latest_ingestion ??
            null } as TargetWorkspace
      121  }
      122 +                                                              
      123 +export type IngestionRequest = { target_id: string; status: st
          +ring }                                                        
      124 +                                                              
      125 +const INGEST_MESSAGES: Record<number, string> = {             
      126 +  400: "This target's source can't be ingested. Check that it 
          +has a valid Google Maps URL.",                                
      127 +  401: 'Your session has expired. Please sign in again.',     
      128 +  404: "This analysis target doesn't exist or you don't have a
          +ccess to it.",                                                
      129 +  503: "Review ingestion isn't available right now. Please try
          + again later.",                                               
      130 +}                                                             
      131 +const INGEST_FALLBACK = 'Unable to start ingestion right now. 
          +Please try again.'                                            
      132 +                                                              
      133 +export async function startIngestion(                         
      134 +  accessToken: string,                                        
      135 +  targetId: string,                                           
      136 +): Promise<IngestionRequest> {                                
      137 +  let response: Response                                      
      138 +  try {                                                       
      139 +    // No body: the backend always ingests from the target's s
          +aved source URL.                                              
      140 +    response = await fetch(`/api/targets/${encodeURIComponent(
          +targetId)}/ingestions`, {                                     
      141 +      method: 'POST',                                         
      142 +      headers: { Authorization: `Bearer ${accessToken}` },    
      143 +    })                                                        
      144 +  } catch {                                                   
      145 +    throw new TargetError(0, 'Unable to connect. Check your co
          +nnection and try again.')                                     
      146 +  }                                                           
      147 +  if (!response.ok) {                                         
      148 +    throw new TargetError(response.status, INGEST_MESSAGES[res
          +ponse.status] ?? INGEST_FALLBACK)                             
      149 +  }                                                           
      150 +  return response.json()                                      
      151 +}                                                             

● Bash(cd "c:/Users/bdorf/VsCode/NJITSenSem1/CS490/CS490-Project-Team-Merge-Conf
      lict/frontend"; python - <<'EOF'
      from pathlib import Path…)
  ⎿  Updated frontend\src\pages\TargetWorkspace.tsx (+39 -5)
       1  import { useEffect, useState } from 'react'
       2 -import { getTarget, PLATFORM, TargetError } from '../api/target
         -s'                                                             
       2 +import { getTarget, PLATFORM, startIngestion, TargetError } fro
         +m '../api/targets'                                             
       3  import type { TargetWorkspace as Workspace } from '../api/targe
          ts'
       4  
       5  type Props = { accessToken: string; targetId: string; onBack: (
          ) => void }
       6  type Result = { key: string; target: Workspace | null; error: s
          tring }
       7 +type Ingest = { targetId: string; state: 'submitting' | 'accept
         +ed' | 'error'; message: string }                               
       8  
       9  const STATUS_LABELS: Record<string, string> = {
      10    processing: 'Ingestion in progress',
     ...
      15  export default function TargetWorkspace({ accessToken, targetId
          , onBack }: Props) {
      16    const [attempt, setAttempt] = useState(0)
      17    const [result, setResult] = useState<Result | null>(null)
      18 +  const [ingest, setIngest] = useState<Ingest | null>(null)    
      19    const requestKey = `${targetId}:${attempt}`
      20  
      21    useEffect(() => {
     ...
      36    }, [accessToken, targetId, requestKey])
      37  
      38    const loading = result === null || result.key !== requestKey
      39 +  // Ignore ingestion feedback left over from a different targe
         +t.                                                             
      40 +  const ingestRequest = ingest?.targetId === targetId ? ingest 
         +: null                                                         
      41 +  const submitting = ingestRequest?.state === 'submitting'     
      42 +                                                               
      43 +  async function handleStartIngestion() {                      
      44 +    if (submitting) return                                     
      45 +    setIngest({ targetId, state: 'submitting', message: '' })  
      46 +    try {                                                      
      47 +      await startIngestion(accessToken, targetId)              
      48 +      setIngest({ targetId, state: 'accepted', message: 'Ingest
         +ion started for this target.' })                               
      49 +    } catch (e: unknown) {                                     
      50 +      const message =                                          
      51 +        e instanceof TargetError ? e.message : 'Unable to start
         + ingestion right now. Please try again.'                       
      52 +      setIngest({ targetId, state: 'error', message })         
      53 +    }                                                          
      54 +  }                                                            
      55    const backLink = (
      56      <button
      57        type="button"
     … 37 more lines (ctrl+o to expand)

● Now the frontend tests:

● Bash(cd "c:/Users/bdorf/VsCode/NJITSenSem1/CS490/CS490-Project-Team-Merge-Conf
      lict/frontend"; python - <<'EOF'
      from pathlib import Path…)
  ⎿  Updated frontend\src\api\targets.ts (+30 -30)
      119      throw new TargetError(response.status, GET_FALLBACK)
      120    return { ...body, latest_ingestion: body.latest_ingestion ??
            null } as TargetWorkspace
      121  }
      122 -                                                              
      123 -export type IngestionRequest = { target_id: string; status: st
          -ring }                                                        
      124 -                                                              
      125 -const INGEST_MESSAGES: Record<number, string> = {             
      126 -  400: "This target's source can't be ingested. Check that it 
          -has a valid Google Maps URL.",                                
      127 -  401: 'Your session has expired. Please sign in again.',     
      128 -  404: "This analysis target doesn't exist or you don't have a
          -ccess to it.",                                                
      129 -  503: "Review ingestion isn't available right now. Please try
          - again later.",                                               
      130 -}                                                             
      131 -const INGEST_FALLBACK = 'Unable to start ingestion right now. 
          -Please try again.'                                            
      132 -                                                              
      133 -export async function startIngestion(                         
      134 -  accessToken: string,                                        
      135 -  targetId: string,                                           
      136 -): Promise<IngestionRequest> {                                
      137 -  let response: Response                                      
      138 -  try {                                                       
      139 -    // No body: the backend always ingests from the target's s
          -aved source URL.                                              
      140 -    response = await fetch(`/api/targets/${encodeURIComponent(
          -targetId)}/ingestions`, {                                     
      141 -      method: 'POST',                                         
      142 -      headers: { Authorization: `Bearer ${accessToken}` },    
      143 -    })                                                        
      144 -  } catch {                                                   
      145 -    throw new TargetError(0, 'Unable to connect. Check your co
          -nnection and try again.')                                     
      146 -  }                                                           
      147 -  if (!response.ok) {                                         
      148 -    throw new TargetError(response.status, INGEST_MESSAGES[res
          -ponse.status] ?? INGEST_FALLBACK)                             
      149 -  }                                                           
      150 -  return response.json()                                      
      151 -}                                                             
      122 +                                                              
      123 +export type IngestionRequest = { target_id: string; status: st
          +ring }                                                        
      124 +                                                              
      125 +const INGEST_MESSAGES: Record<number, string> = {             
      126 +  400: "This target's source can't be ingested. Check that it 
          +has a valid Google Maps URL.",                                
      127 +  401: 'Your session has expired. Please sign in again.',     
      128 +  404: "This analysis target doesn't exist or you don't have a
          +ccess to it.",                                                
     … 23 more lines (ctrl+o to expand)
  ⎿  Updated frontend\src\pages\TargetWorkspace.test.tsx (+171 -101)
        1 -// @vitest-environment jsdom                                  
        2 -import { afterEach, describe, expect, it, vi } from 'vitest'  
        3 -import { cleanup, render, screen } from '@testing-library/reac
          -t'                                                            
        4 -import userEvent from '@testing-library/user-event'           
        5 -import TargetWorkspace from './TargetWorkspace'               
        6 -                                                              
        7 -const TARGET = {                                              
        8 -  id: 't1',                                                   
        9 -  name: "Joe's Coffee",                                       
       10 -  platform: 'google_maps',                                    
       11 -  source_url: 'https://www.google.com/maps/place/joes',       
       12 -  created_at: '2026-01-02T00:00:00+00:00',                    
       13 -  latest_ingestion: null,                                     
       14 -}                                                             
       15 -                                                              
       16 -function reply(status: number, body: unknown = {}) {          
       17 -  return { ok: status >= 200 && status < 300, status, json: as
          -ync () => body } as Response                                  
       18 -}                                                             
       19 -                                                              
       20 -afterEach(() => {                                             
       21 -  cleanup()                                                   
       22 -  vi.unstubAllGlobals()                                       
       23 -})                                                            
       24 -                                                              
       25 -describe('TargetWorkspace', () => {                           
       26 -  it('identifies the target and shows its platform, source, st
          -ate and ingestion path', async () => {                        
       27 -    const fetchMock = vi.fn().mockResolvedValue(reply(200, TAR
          -GET))                                                         
       28 -    vi.stubGlobal('fetch', fetchMock)                         
       29 -    render(<TargetWorkspace accessToken="tok-123" targetId="t1
          -" onBack={() => {}} />)                                       
       30 -                                                              
       31 -    expect(await screen.findByRole('heading', { name: "Joe's C
          -offee" })).toBeTruthy()                                       
       32 -    expect(screen.getByText('Google Maps')).toBeTruthy()      
       33 -    const source = screen.getByRole('link', { name: TARGET.sou
          -rce_url })                                                    
       34 -    expect(source.getAttribute('href')).toBe(TARGET.source_url
          -)                                                             
       35 -    expect(source.getAttribute('rel')).toContain('noopener')  
       36 -    expect(screen.getByText('No reviews have been ingested yet
          -.')).toBeTruthy()                                             
       37 -    expect(screen.getByRole('button', { name: 'Start ingestion
          -' })).toBeTruthy()                                            
       38 -    expect(fetchMock).toHaveBeenCalledWith('/api/targets/t1', 
          -{                                                             
       39 -      headers: { Authorization: 'Bearer tok-123' },           
       40 -    })                                                        
     … 232 more lines (ctrl+o to expand)
  ⎿  Updated frontend\src\pages\TargetWorkspace.tsx (+3 -1)
      48        setIngest({ targetId, state: 'accepted', message: 'Ingest
          ion started for this target.' })
      49      } catch (e: unknown) {
      50        const message =
      51 -        e instanceof TargetError ? e.message : 'Unable to start
         - ingestion right now. Please try again.'                       
      51 +        e instanceof TargetError                               
      52 +          ? e.message                                          
      53 +          : 'Unable to start ingestion right now. Please try ag
         +ain.'                                                          
      54        setIngest({ targetId, state: 'error', message })
      55      }
      56    }
  ⎿  (timeout 5m)

● Frontend tests (45), lint, type check and Prettier all pass. One last check
  for leftover "not available yet" text, then the full diff:

  Ran 1 shell command (ctrl+o to expand)

● S1-019 is built on feature/S1-019-submit-ingestion and nothing is committed.
  All 128 backend tests pass, and the 45 frontend tests, lint, type check and
  formatting all pass too. In the real app, though, clicking Start ingestion
  shows "Review ingestion isn't available right now." Pulling reviews from
  Google Maps is S1-020, so until then the backend reports unavailable instead
  of faking a success.

  How I read the ticket: the ticket lets the team choose between URL ingestion
  and an import. I went with URL ingestion because the README and docs already
  describe ingesting from a URL through SerpApi. The request sends no URL. The
  backend always uses the Google Maps URL saved on the target, so a client can't
  point ingestion at a different address.

  Backend
  - New endpoint: POST /api/targets/<id>/ingestions is in routes.py
    (backend/app/routes.py) and calls ingestion.py
    (backend/app/services/ingestion.py). Checks run in the ticket's order:
    a. Signed in: otherwise 401.
    b. Target exists and you own it: both are checked in one database query, so
       another user's target and a missing one get the same 404.
    c. Empty request body: any field, such as owner_id or source_url, is
       rejected with 400.
    d. Saved URL is a usable Google Maps link: otherwise 400.
  - Success: returns 202 with {"target_id", "status": "accepted"}.
  - Placeholder review source: a new adapter, review_source.py
    (backend/app/adapters/review_source.py), is only called after every check
    passes. For now it always answers with a new 503 error,
    INGESTION_UNAVAILABLE. S1-020 replaces it with the real SerpApi source.
  - Refactor: I moved the URL check and the owner-scoped lookup in targets.py
    (backend/app/services/targets.py) into shared helpers, so the workspace page
    and ingestion use the same checks.

  Frontend
  - The Start ingestion button in TargetWorkspace.tsx
    (frontend/src/pages/TargetWorkspace.tsx) now works. It shows a busy state
    while the request is running, a confirmation on success, and a
    plain-language message for 400, 401, 404, 503 and network failures.

  Tests
  - test_ingestion_submit.py (backend/tests/test_ingestion_submit.py) uses a
    fake review source that records each call. Every denial test confirms the
    source was never called and nothing in the database changed. The owner can
    still start ingestion afterwards.
  - I temporarily removed the ownership check, and separately the URL check; the
    tests failed both times, so they catch regressions. Both checks are back in
    place.
  - Frontend tests cover the request, the busy state, and each error message.

  Before opening the PR:
  - AI transcript: save this session to ai-transcripts/S1-019/.
  - Extra security review: this change touches ownership and ingestion, so the
    team rules require a second reviewer.

  Let me know if you want me to commit and open the PR.