// @vitest-environment jsdom
import { afterEach, describe, expect, it } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
import IngestionStatus from './IngestionStatus'

const RUN = {
  total_count: 5,
  imported_count: 5,
  skipped_count: 0,
  message: 'Import succeeded.',
  completed_at: '2026-11-06T15:04:00+00:00',
}

function shown(container: HTMLElement) {
  const box = container.querySelector('[data-status]') as HTMLElement
  return { box, text: box.textContent ?? '' }
}

afterEach(cleanup)

describe('IngestionStatus', () => {
  it('explains that nothing has been ingested yet', () => {
    render(<IngestionStatus ingestion={null} />)
    expect(screen.getByText(/No reviews have been ingested yet/)).toBeTruthy()
  })

  it('shows a successful run in green with the number of reviews added', () => {
    const { container } = render(<IngestionStatus ingestion={{ ...RUN, status: 'succeeded' }} />)
    const { box, text } = shown(container)
    expect(text).toContain('Last ingestion succeeded')
    expect(text).toContain('Added 5 new reviews.')
    expect(text).not.toContain('skipped')
    expect(box.className).toContain('bg-green-50')
  })

  it('shows a partial run in amber, distinct from success and failure', () => {
    const run = { ...RUN, status: 'partial', imported_count: 3, skipped_count: 2 }
    const { container } = render(<IngestionStatus ingestion={run} />)
    const { box, text } = shown(container)
    expect(text).toContain('Last ingestion partially succeeded')
    expect(text).toContain("Added 3 new reviews. 2 of 5 records couldn't be used and were skipped.")
    expect(box.className).toContain('bg-amber-50')
  })

  it('shows a failed run in red with the stored reason', () => {
    const run = {
      ...RUN,
      status: 'failed',
      total_count: 0,
      imported_count: 0,
      message: 'No usable written reviews with ratings from 1 to 5 were found.',
    }
    const { container } = render(<IngestionStatus ingestion={run} />)
    const { box, text } = shown(container)
    expect(text).toContain('Last ingestion failed')
    expect(text).toContain('No usable written reviews with ratings from 1 to 5 were found.')
    expect(text).toContain('No reviews were added by this attempt.')
    expect(text).not.toContain('Added')
    expect(box.className).toContain('bg-red-50')
  })

  it('says when the run finished', () => {
    const { container } = render(<IngestionStatus ingestion={{ ...RUN, status: 'succeeded' }} />)
    const time = container.querySelector('time')
    expect(time?.getAttribute('dateTime')).toBe(RUN.completed_at)
    expect(time?.textContent).toMatch(/^Finished Nov \d, 2026/)
  })

  it('uses the singular for one review', () => {
    const run = { ...RUN, status: 'succeeded', total_count: 1, imported_count: 1 }
    const { container } = render(<IngestionStatus ingestion={run} />)
    expect(shown(container).text).toContain('Added 1 new review.')
  })

  it('reports zero new reviews when every review was already saved', () => {
    const run = { ...RUN, status: 'succeeded', imported_count: 0 }
    const { container } = render(<IngestionStatus ingestion={run} />)
    expect(shown(container).text).toContain('Added 0 new reviews.')
  })

  it('still shows the status when only the status is known', () => {
    const { container } = render(<IngestionStatus ingestion={{ status: 'failed' }} />)
    const { text } = shown(container)
    expect(text).toContain('Last ingestion failed')
    expect(text).toContain('No reviews were added by this attempt.')
    expect(container.querySelector('time')).toBeNull()
  })

  it('ignores malformed counts and dates instead of showing them', () => {
    const run = {
      status: 'partial',
      imported_count: -1,
      skipped_count: 2,
      completed_at: 'not a date',
    }
    const { container } = render(<IngestionStatus ingestion={run} />)
    const { text } = shown(container)
    expect(text).toBe('Last ingestion partially succeeded')
    expect(container.querySelector('time')).toBeNull()
  })

  it('shows an unrecognised status neutrally rather than hiding it', () => {
    const { container } = render(<IngestionStatus ingestion={{ status: 'queued' }} />)
    const { box, text } = shown(container)
    expect(text).toContain('Last ingestion: queued')
    expect(box.className).toContain('bg-slate-50')
  })
})
