# TRUSEO — Screens and UI Reference

This document describes every screen in the app: route, purpose, main components, and design patterns used.

---

## Global layout and design system

### Layout structure
- **App layout**: Centered column (`max-width: 1200px`), full viewport height. Header (sticky), main body (flex), footer.
- **App center**: Single column with `--bg-card` background and `--shadow-md`; content is visually “in the middle” of the page.
- **Header**: Brand link (TRUSEO + BarChart3 icon), nav links, and (when logged in) user dropdown on the right.
- **Footer**: Single line, copyright text, `--bg-footer` background.

### Design tokens (theme.css)
- **Colors**: Primary `#4f46e5`; surfaces (page `#f1f5f9`, card/header white); text `#0f172a`, muted `#64748b`; borders `#e2e8f0`; success/error/warning semantic colors.
- **Spacing**: `--space-xs` through `--space-2xl` (4px–32px).
- **Typography**: Inter (fallback system-ui); `--text-xs` to `--text-2xl`; `--font-medium`, `--font-semibold`, `--font-bold`.
- **Radii**: `--radius-sm` 4px, `--radius-md` 6px, `--radius-lg` 8px.
- **Shadows**: `--shadow-sm`, `--shadow-md`, `--shadow-lg`.

### Shared UI patterns
- **Dashboard container**: `.dashboard` — page title in `<header>`, then `.section` blocks.
- **Sections**: `.section`, `.detail-section` — margin, optional `h2` + `.section-desc`.
- **Forms**: `.form-group`, `.form-label`, `.form-input` / `.form-textarea` / `.form-select`, `.form-actions`; `.form-error` for validation.
- **Buttons**: `.btn-primary` (indigo), `.btn-secondary` (outline), `.btn-ghost`, `.btn-danger`, `.btn-sm` / `.btn-lg`; `.link-btn` for text-style links.
- **Tables**: `.prompts-table` (striped hover, th/td padding); `.table-placeholder` for empty state; `.prompts-table-wrap` for horizontal scroll.
- **Cards**: `.stat-card` (stat value + label + optional sub); `.card` for generic elevated blocks.

### Shared components (used across screens)
- **AppHeader**: NavLink brand, nav items, “More” dropdown (Content sources, Prompt generation, Monitoring, Reports), **UserDropdown** (name, email, Settings, Sign out). When not logged in: Try it free, Sign in, Sign up.
- **UserDropdown**: Button with user name + ChevronDown; dropdown with email, Settings link, Sign out; click-outside to close (lucide-react icons).
- **AppFooter**: Copyright line.
- **AppLayout**: Wraps children in app-center with header and footer.
- **ProtectedRoute**: Redirects to `/signin` if no auth token; shows “Loading…” while auth is resolving.
- **AuthProvider** (context): `user`, `token`, `loading`, `setUser`, `setToken`, `logout`; persists token, fetches `/api/me` on load.

### Reusable UI components (components/)
- **CitationTrendsChart**: Recharts line chart (LineChart, XAxis, YAxis, CartesianGrid, Tooltip, Legend). Props: `runs` (RunTrend[]). Shows citation rate % by date and model; model colors (openai, anthropic, perplexity, gemini). Placeholder when no data.
- **PromptsVisibilityTable**: TanStack Table with sort/filter. Columns: Cited, Brand mentioned, Competitor-only, Prompt. Props: `prompts` (PromptVisibility[]). Uses `.prompts-table`, `.table-filter` input.

---

## Public screens (no auth)

### 1. Sign in — `/signin`
- **Purpose**: Authenticate with email and password; redirect to `from` state or `/`.
- **Components**: Single page with `.auth-page`, `h1`, `.auth-form`, `.auth-footer` (link to Sign up).
- **Design**: Centered auth layout; form with Email and Password inputs, primary submit “Sign in”; `.form-error.auth-error` for API/validation errors; loading state “Signing in…” on button.
- **Behavior**: If already `token`, redirect to `from` or `/`. On success: `setToken`, `setUser`, `navigate(from)`.

### 2. Sign up — `/signup`
- **Purpose**: Register with email, password (min 8 chars), optional name; redirect to `/` on success.
- **Components**: Same auth shell as Sign in — `.auth-page`, `.auth-form`, `.auth-footer` (link to Sign in).
- **Design**: Email, Password (min 8), Name (optional); primary “Sign up”; client-side validation for password length; `.form-error` for errors.
- **Behavior**: If already `token`, redirect to `/`. On success: `setToken`, `setUser`, `navigate('/')`.

### 3. Try it free (trial landing) — `/try`
- **Purpose**: Unauthenticated trial: enter website URL to run discovery + prompt generation + monitoring; also shows directory of recent trial results.
- **Components**: **TryTrial** page with conditional rendering: when no `slug` and no `token` — form (website input + “Run trial”); “Recent trial results” section with list of links to `/try/:slug`.
- **Design**: `.dashboard`; `h1` “Try it free”; short description; `.form-actions` with one text input and primary button (“Run trial” or “Discovering domain…”); list of links with `.section-desc` dates.
- **Behavior**: On submit → `runTrial(website)` → store token in sessionStorage, navigate to `/try/:slug`. Directory loaded via `getTrialDirectory()`.

### 4. Trial results (by slug) — `/try/:slug`
- **Purpose**: View trial execution: domain discovery, runs summary, prompt visibility, and “Results by prompt” (citations, mentions, LLM responses). Supports both “just finished” (token polling) and “shared link” (slug polling).
- **Components** (inside **TryTrial**):
  - **ResultsView** (when execution finished/failed): header with “← Start over”, “Trial results”, trigger/status/dates; **Domain discovery** block (`.discovery-grid`, `.discovery-item`, `.discovery-label`, `.discovery-value`) — Categories, Niche, Description, Target audience, Key topics, Competitors, Discovered at; **Runs table** (run id, model, started, finished, prompt count, status); **Prompt visibility** table (execution-visibility-table: Prompt, Niche, per-model Cited/Brand/Comp-only); **TrialResultsByPrompt** (see below); CTA “Sign up” link.
  - **TrialResultsByPrompt**: For each prompt in `prompt_visibility`: `.trial-prompt-card` with prompt text as title; per run: `.trial-model-block` with model name, Citations list (domain + “own” badge, optional `.trial-snippet`), Mentions list (text + “own”/“competitor” badge), **ResponsePreview** (expandable LLM response with “Show more”/“Show less”).
  - **ResponsePreview**: Pre block with truncated/expanded text; button to toggle (MAX_RESPONSE_PREVIEW = 400).
  - Progress view (execution not done): “Trial – Running monitoring”, same discovery summary grid, status text, runs table; slug-based polling when no token.
- **Design**: Cards with `.trial-prompt-card`, `.trial-model-block`; badges `.trial-own-badge` (green), `.trial-comp-badge` (amber); `.trial-snippet`, `.trial-response-pre`; `.execution-visibility-table` (fixed col widths for prompt/niche).
- **Behavior**: On mount with slug: `getTrialBySlug(slug)`; if 404 and token in sessionStorage, poll `getTrialStatus(token)`. When no token and execution not finished: poll `getTrialBySlug(slug)` on interval until status finished/failed. When done, full execution payload includes `discovery`, `citations`, `mentions`, `prompt_responses`.

---

## Protected screens (auth required)

### 5. Dashboard — `/`
- **Purpose**: High-level stats from latest monitoring runs.
- **Components**: **Dashboard** page; **StatCard** (value, label, optional sub); grid of stat cards.
- **Design**: `.dashboard`; header “TRUSEO Dashboard” + short description; `.dashboard-stats` with `.stat-grid` (grid, auto-fill min 160px); each **StatCard** uses `.stat-card`, `.stat-value`, `.stat-label`, `.stat-sub`.
- **Data**: Prompts tracked, Domains tracked, Prompts with own citation (+ citation rate %), Total own citations, Prompts with brand mentioned, Competitor-only answers, Last run. Links to Prompts and Monitoring.
- **Behavior**: `getDashboardStats()` on mount; error/loading states.

### 6. Domains — `/domains`
- **Purpose**: Manage tracked domains; run discovery (all or per domain); view and edit domain profiles (category, niche, value proposition, target audience, key topics, competitors).
- **Components**: List of domains with add form (domain + brand names); per domain: actions (Run discovery, View profile), inline profile display or edit form; discovery status and “Run discovery (all)” button.
- **Design**: `.dashboard`; header; table or list of domains; `.form-group` for add/edit; checkboxes for “Run discovery for this domain”; profile shown in structured rows (category, niche, etc.); edit form with text inputs and list of competitors (add/remove).
- **Behavior**: `getDomains()`, `getDiscoveryStatus()`; `runDiscovery()`, `runDiscoveryForDomain(id)`; `getDomainProfile(id)`; `updateDomainProfile()`, `createDomain()`, `updateDomain()`, `deleteDomain()`.

### 7. Prompts — `/prompts`
- **Purpose**: List all prompts with optional filter by prompt_generation_run_id; pagination; open in LLM UIs (ChatGPT, Perplexity, Claude, Gemini) or go to detail.
- **Components**: Header with optional “Showing prompts from generation run #X” and “Show all prompts”; pagination bar (Previous/Next + “Page X of Y (total)”); table: Prompt text, Niche, “Try” links (open live URL + copy), “View” link to `/prompts/:id`.
- **Design**: `.dashboard`; `.pagination-bar`; `.prompts-table`; `.link-btn` for try/view.
- **Behavior**: `getPrompts(PAGE_SIZE, offset, undefined, promptGenerationRunId)`; optional `?prompt_generation_run_id=` from URL; state from Generate prompts can set `generated: true` and refresh list.

### 8. Prompt detail — `/prompts/:id`
- **Purpose**: Single prompt: text, niche, visibility in runs (table: run, cited, brand mentioned, competitor-only, others cited), citations by model (domain, snippet, is_own), mentions by model, “Competitor-only” block (others cited when competitor-only), full LLM response per run (modal).
- **Components**: Back link; sections: Text, Visibility in runs (table), Citations, Mentions; competitor-only cited list; buttons to open response modal per run.
- **Design**: `.dashboard`; `.detail-section`; `.prompt-text`; `.prompts-table`; citation/mention lists; `.response-modal-overlay`, `.response-modal`, `.response-modal-header`, `.response-text-pre` for modal body.
- **Behavior**: `getPrompt(id)`; modal state `responseModalRunId`; citation links use `citationHref(domain, snippet)`.

### 9. Generate prompts — `/prompts/generate`
- **Purpose**: One-off prompt generation: choose mode (per domain vs total), count, then run; redirect to Prompts with state to refresh.
- **Components**: Back link; conditional: if !discoveryDone, message + “Go to Domains”; else form: Mode (radio per_domain / total), Number of prompts (number input), “Generate” button.
- **Design**: `.dashboard`; `.form-group`, `.form-check` for radios; primary button; error message.
- **Behavior**: `getDiscoveryStatus()`; `generatePrompts(options)`; navigate to `/prompts` with `state: { generated: true, inserted }`.

### 10. Briefs — `/briefs`
- **Purpose**: List content briefs (Sprint 2); priority, topic, angle, status, draft link; open detail.
- **Components**: Header; table: Priority, Topic (link), Angle, Status, Draft (View draft → or —), “View details →”.
- **Design**: `.dashboard`; `.prompts-table`; `.table-placeholder` when no briefs.
- **Behavior**: `getBriefs()`.

### 11. Brief detail — `/briefs/:id`
- **Purpose**: Full brief: topic, priority, status, angle, suggested headings, entities to mention, schema, image prompts (and images if URLs), source prompt; Copy brief / Download brief / View draft.
- **Components**: Back link; header with actions (Copy, Download, View draft); sections for Image prompts (list + optional images), Angle, Suggested headings, Entities, Schema, Source prompt.
- **Design**: `.dashboard`; `.brief-actions`; `.brief-images-section`; pre or structured blocks for text fields.
- **Behavior**: `getBrief(id)`; copy/download build markdown from brief; link to `/drafts/:draftId` if draft exists.

### 12. Drafts — `/drafts`
- **Purpose**: List drafts (Sprint 3); title, status; View / Publish.
- **Components**: Header; table: Title (link), Status, View + Publish buttons.
- **Design**: Same list pattern as Briefs; `.prompts-table`, `.link-btn`.
- **Behavior**: `getDrafts()`.

### 13. Draft detail — `/drafts/:id`
- **Purpose**: View draft title, status, dates; body (markdown rendered or raw); “Prepare & publish”; Copy draft; “Generate images” if brief exists.
- **Components**: Back link; header with actions; body in `.draft-body` (markdown); optional image generation button.
- **Design**: `.dashboard`; `.brief-actions`; styled pre/markdown area.
- **Behavior**: `getDraft(id)`; `generateBriefImages(briefId)`; link to PublishDraft.

### 14. Publish draft — `/drafts/:id/publish`
- **Purpose**: Choose CMS/source (Hashnode, Ghost, WordPress, Webflow, LinkedIn, DevTo, Notion); configure destination; preview body with image URL rewriting; publish and optionally submit published URL.
- **Components**: Draft title; grouped content sources by type; per source: name, config fields, “Publish” button; preview of body (marked + image rewrite); success/error feedback.
- **Design**: `.dashboard`; `.content-source-edit-form`, `.edit-form-row`; preview in styled block; primary/secondary buttons.
- **Behavior**: `getDraft(id)`, `getCmsOptions()`; `publishDraftToSource(draftId, sourceId, …)`, `submitPublishedUrl()`; image URL rewrite for preview; `getSourceTypeLabel()` from constants/cms.

### 15. Content sources — `/content-sources`
- **Purpose**: Manage CMS/configs for publishing: list sources; add (name, type, config); edit/delete; link domains to sources.
- **Components**: List of sources (type, name, linked domains); Add form (name, type dropdown, dynamic config fields by type); edit form; domain multi-select for “link domains”; validate credentials button.
- **Design**: `.dashboard`; table or cards; `.content-source-edit-form`; type-specific config (hashnode, ghost, wordpress, webflow, linkedin, devto, notion) with labels and input types (text/password/url).
- **Behavior**: `listContentSources()`, `getContentSourceDomains()`, `getDomains()`; create/update/delete source; add/remove domain–source links; `validateCmsCredentials()`.

### 16. Prompt generation (scheduled) — `/prompt-generation`
- **Purpose**: Settings for scheduled prompt generation (enabled, frequency_days, prompts_per_domain); “Run now”; list of runs (id, started, status, prompts inserted) with pagination; link to prompts filtered by run.
- **Components**: Header; form: Enabled checkbox, Frequency (days), Prompts per domain; Save; “Run now”; table of runs with “View prompts” link (to `/prompts?prompt_generation_run_id=`).
- **Design**: `.dashboard`; form layout; `.prompts-table`; pagination.
- **Behavior**: `getPromptGenerationSettings()`, `updatePromptGenerationSettings()`; `runPromptGenerationNow()`; `getPromptGenerationRuns()`.

### 17. Monitoring — `/monitoring`
- **Purpose**: Monitoring settings (enabled, frequency, models, domain_ids, prompt_limit, delay_seconds); “Save”; “Run now”; list of executions with pagination and link to execution detail.
- **Components**: Form: Enabled, Frequency (minutes), Models (checkboxes: openai, anthropic, perplexity, gemini), Domains (multi-select), Prompt limit, Delay (seconds); Save / Run now; table: Execution id (link), Started, Finished, Trigger, Status, “View” → execution detail.
- **Design**: `.dashboard`; checkboxes and number/select inputs; `.prompts-table`; primary/secondary buttons; loading states “Saving…” / “Running…”.
- **Behavior**: `getMonitoringSettings()`, `updateMonitoringSettings()`; `getDomains()`; `runMonitoringNow(options)`; `getMonitoringExecutions(PAGE_SIZE, offset)`; navigate to `/monitoring/executions/:id`.

### 18. Monitoring execution detail — `/monitoring/executions/:id`
- **Purpose**: Single execution: runs table (id, model, started, finished, prompts, status, “View prompts”); prompt visibility table (prompt, niche, per-model Cited/Brand/Comp-only); optional settings snapshot (JSON).
- **Components**: Back link to Monitoring; runs table; prompt visibility table (same structure as trial: `.execution-visibility-table`, col-prompt, col-niche); optional pre for settings_snapshot.
- **Design**: `.dashboard`; `.detail-section`; `.execution-visibility-table`; prompt cell has link to `/prompts/:id`.
- **Behavior**: `getMonitoringExecution(id)`.

### 19. Reports — `/reports`
- **Purpose**: Date-filtered reports: Weekly summary (text), Monitoring runs, Citations, Drafts; Apply loads data; Download as CSV (or TXT for weekly).
- **Components**: Filters: Report type (select), From date, To date; Apply and Download buttons; report content: weekly = pre block; monitoring-runs = table (id, started, finished, status, trigger); citations = table (columns from API); drafts = table.
- **Design**: `.dashboard`; `.edit-form-row`, `.edit-form-label`, `.edit-form-field`; `.prompts-table`; `.report-summary`; `.table-placeholder` when no data.
- **Behavior**: `getWeeklyReport()`, `getMonitoringRunsReport()`, `getCitationsReport()`, `getDraftsReport()` with date params; client-side CSV/TXT download.

### 20. Settings — `/settings`
- **Purpose**: Per-user API keys and model names for OpenAI, Perplexity, Anthropic, Gemini; masked display; save; validate (connection check per provider).
- **Components**: One section “TRUSEO provider API keys and models”; per provider: API key input (placeholder), Model name input; Save button; “Validate” button; validation result (per-provider success/failure message).
- **Design**: `.dashboard`; `.form-group` with max-width 560px; primary Save, secondary Validate; validation messages in block.
- **Behavior**: `getLlmProviderSettings()`, `updateLlmProviderSettings()`, `validateLlmProviderSettings(form)`; form state for key/model fields; keys cleared after save (masked from UI).

---

## Route summary

| Route | Auth | Screen |
|-------|------|--------|
| `/signin` | No | Sign in |
| `/signup` | No | Sign up |
| `/try` | No | Try it free (form + directory) |
| `/try/:slug` | No | Trial results (by slug) |
| `/` | Yes | Dashboard |
| `/domains` | Yes | Domains |
| `/prompts` | Yes | Prompts |
| `/prompts/generate` | Yes | Generate prompts |
| `/prompts/:id` | Yes | Prompt detail |
| `/briefs` | Yes | Briefs |
| `/briefs/:id` | Yes | Brief detail |
| `/drafts` | Yes | Drafts |
| `/drafts/:id` | Yes | Draft detail |
| `/drafts/:id/publish` | Yes | Publish draft |
| `/content-sources` | Yes | Content sources |
| `/prompt-generation` | Yes | Prompt generation (scheduled) |
| `/monitoring` | Yes | Monitoring |
| `/monitoring/executions/:id` | Yes | Monitoring execution detail |
| `/reports` | Yes | Reports |
| `/settings` | Yes | Settings |

---

## Icons and assets

- **lucide-react**: BarChart3 (brand), ChevronDown (user menu), Settings, LogOut used in header/user dropdown.
- No other icon library; tables and forms use text/buttons only except where noted.

---

## CSS files

- **index.css**: Root typography, links, headings, button base.
- **theme.css**: Design tokens (colors, spacing, typography, radii, shadows).
- **App.css**: Layout (app-layout, app-center, header, footer, body); header nav and dropdowns; buttons; forms; dashboard; stat cards; tables; modals; trial-specific (discovery grid, trial-prompt-card, trial-model-block, badges, snippet, response pre); execution visibility table; auth page; pagination; brief/draft actions; etc.
