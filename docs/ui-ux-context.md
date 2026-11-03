# ReviewLens UI/UX Context

Team standard for new and changed frontend features. These conventions build on the existing indigo/slate UI; some require follow-up implementation. Use this as the shared reference when developing independently.

## 1. Application navigation

- Use **ReviewLens AI**, **target** (saved business/place), and **workspace** (target details) consistently. Labels use sentence case.
- `/` shows the signed-in target list and creation form; `/targets/:id` opens a workspace. Reuse `targetPath` and `usePath` from `frontend/src/hooks/usePath.ts`. Show authentication when signed out.
- Keep a shared header with the brand linking to `/`, signed-in identity, and **Log out**. Start workspaces with **Back to your targets**, then the target name and source.
- Use real links for navigation and buttons for operations. Preserve direct loads and browser Back/Forward. After an in-app page change, focus the page heading and update the title to `<page or target> | ReviewLens AI`.
- Unknown routes show a not-found message and a home link. Missing and inaccessible targets use the same unavailable message and reveal no target data.

## 2. Page layout

| Area | Default |
| --- | --- |
| Authentication | Centered white card, max width 420px; padding 28px, increasing to 40px at 640px |
| Signed-in pages | Centered container, max width 1120px; horizontal padding 16px, increasing to 32px at 640px; vertical padding 32px |
| Forms | One column, max width 640px |
| Cards | White, slate-200 border, 8px radius, 16px padding; 24px padding for major panels |
| Sections | 32px between major sections; 16px between related content blocks |

- Use one `main` and one page `h1`, then ordered `h2`/`h3` sections. Page order: navigation, back link, title/description, feedback, content.
- Show existing targets before the creation form. In workspaces, show target metadata and last ingestion state before ingestion controls and review content.
- Default to one column; complementary panels may use two columns at 768px with a 24px gap. Preserve reading/tab order. Wrap long names and URLs; avoid page-level horizontal scrolling at 320px and 200% zoom.

## 3. Form conventions

- Stack visible labels above controls: 8px label-to-control, 6px before help/error text, and 20px between fields. Associate each label with a unique input ID.
- Mark fields `(required)` or `(optional)` and set the appropriate required attribute. Placeholders provide examples rather than labels.
- Text controls use `w-full rounded-lg border border-slate-300 bg-white px-3.5 py-3 text-base text-slate-900 shadow-xs`. Focus uses an indigo-500 border and `ring-3 ring-indigo-500/15`.
- Use appropriate input types/autocomplete. Trim names and URLs, never passwords. Preserve values after failures; reset only after confirmed success or an explicit reset.
- Explain constraints before submission: full Google Maps place URL; CSV encoding, required columns, and limits from the [ingestion contract](review-ingestion-source.md).
- Use real forms with Enter-to-submit. Set button types explicitly so secondary actions do not submit.

## 4. Validation and errors

- Validate required values and obvious format/size limits on submit. After a failed submission, revalidate affected fields on correction or blur. Server validation remains authoritative.
- Map API `error.fields` to inputs. Put corrective text below each invalid control using `text-sm text-red-700` and a red-400 border; set `aria-invalid` and connect help/errors with `aria-describedby`. Focus the first invalid field.
- Put operation errors above the affected form/panel with `role="alert"`. Use an 8px radius, `px-4 py-3 text-sm leading-6`, red-200 border, red-50 background, and red-800 text.
- State what failed and the next step: "Unable to load your targets. Try again." Offer **Try again** for failed reads; writes require explicit resubmission. Check status before repeating an import with an uncertain result.
- Session expiry prompts sign-in. Missing/forbidden targets say "This target does not exist or you do not have access." Never expose raw exceptions, secrets, or provider/database details. Follow [security guardrails](data-and-security-guardrails.md).

## 5. Loading and processing states

| State | Required behavior |
| --- | --- |
| Loading | Keep the shell/navigation visible; show scoped text such as "Loading your targets..." with `role="status"`. Do not show an empty state yet. |
| Submitting/processing | Use "Creating...", "Importing...", or "Starting ingestion..."; prevent duplicate submissions, disable conflicting controls, and set `aria-busy` on the affected region. Keep unrelated navigation available. |
| Success | Announce confirmed results once with `role="status"`, refresh affected data, and offer the next action when useful. |
| Partial import | Show actual imported/skipped counts with an amber notice; distinguish partial success from total failure. |
| Empty | Explain the absence and next step: "No reviews yet. Start ingestion or import a CSV." |
| Failure | End the busy state, show recovery guidance, and retain valid existing reviews where access remains authorized. |

- Notices share the error panel's radius/padding: success uses green-50/green-800/green-200; information indigo-50/indigo-900/indigo-100; warning amber-50/amber-900/amber-200 (background/text/border).
- Keep feedback until another attempt or navigation. A spinner supplements text; never invent progress percentages, counts, or completion. Distinguish an accepted request from completed ingestion.
- Identify CSV imports as supplied data and live retrieval as fetched data. Explain near ingestion controls that repeated imports currently can duplicate reviews.

## 6. Buttons and actions

| Variant | Appearance | Use |
| --- | --- | --- |
| Primary | Indigo-600, white text; hover indigo-700, active indigo-800 | Main operation per task panel |
| Secondary | White, slate-300 border, slate-700 text; hover slate-50 | Cancel or alternative action |
| Text/link | Indigo-600; underline on hover/focus | Navigation or low-emphasis action |

- Use `rounded-lg px-4 py-3 text-sm font-semibold`, minimum 44px height/hit area, and verb/object labels: **Create target**, **Import CSV reviews**.
- Allow one primary action per task panel. Group actions with a 12px gap, secondary before primary. Stack full-width on small screens; use natural widths on larger screens. Authentication actions stay full-width.
- Buttons/links need a visible 2px indigo-600 focus outline with 4px offset. Disabled controls use 60% opacity; use a wait cursor only during processing and explain unmet prerequisites nearby.

## 7. Spacing and typography

Use Tailwind utilities and shared tokens in `frontend/src/index.css`.

| Token | Standard |
| --- | --- |
| Font | `'Segoe UI', Arial, sans-serif` |
| Background / surface | `#f4f6fa` / white |
| Main / supporting text | Slate-900 / slate-600; slate-500 for nonessential metadata |
| Page heading | 24px / 32px line height, semibold |
| Section heading | 18px / 28px, semibold |
| Body / inputs | 16px / 24px, normal |
| Labels / help / feedback | 14px / 20px; labels medium; alerts use 24px line height |
| Spacing | 4, 8, 12, 16, 20, 24, 32, 40px; 6px for field help |

Use left-aligned content and short, sentence-case instructions. Pair status colors with text. Maintain readable contrast (4.5:1 for normal text), visible keyboard focus, and reduced-motion support.

## 8. Reusable components

- Check `frontend/src/components` first. Reuse `CreateTargetForm`, `TargetList`, and `ReviewCsvImport` for their workflows. Keep pages in `pages`, requests in `api`, and reusable state behavior in `hooks`.
- When extracting shared UI, establish one `Button` (variant/busy/disabled), `FormField` (label/help/error), `Alert` (tone/announcement), and page shell. These are expected contracts, not existing exports.
- Shared controls own styling and accessibility wiring and forward native attributes/focus refs as needed. Feature components own requests, permissions, and messages.
- Extend shared components/tokens instead of duplicating styles. Update this reference in the same PR when adding a convention.

## Review checklist

- Routes, direct loads, Back/Forward, page titles, and heading focus work.
- Layout, tokens, labels, and actions match this reference; shared components are reused.
- Keyboard use, announcements, 320px/1280px layouts, and 200% zoom are usable.
- Loading, empty, success/partial, validation, and failure states are covered; duplicate submission is prevented.
- Follow [coding standards](coding-standards.md) for behavior tests and the root README for checks. Documentation-only changes need content/link review.
