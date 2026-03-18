# TRUSEO

Self-learning system for optimizing visibility in LLM-generated answers (ChatGPT, Perplexity, Claude). Four sprints: Monitor → Gap & Brief → Content → Distribution & Learning.

## How the platform learns (autolearning)

The system improves over time by closing the loop between **what you publish** and **how LLMs cite you**:

1. **Monitor** — We run your prompts against multiple LLMs and record whether your domain is cited, your brand is mentioned, or only competitors appear.
2. **Gap & brief** — Prompts where you’re not cited (or only competitors are) become briefs; the brief generator can use past learnings to focus on high-impact angles.
3. **Content & publish** — You create and publish content from those briefs.
4. **Uplift** — After publishing, we compare monitoring runs *before* and *after* to measure **citation uplift** (more citations to your domain) and **brand-mention uplift** (more explicit brand mentions in answers).
5. **Learning job** — A weekly job analyzes which content led to the biggest uplift, which prompts/niches get cited, and run rates. An LLM turns this into **learning hints** (e.g. prompt_gen_hints, brief_gen_system_extra) and writes `config/learning_hints.yaml`.
6. **Feedback** — The prompt generator, brief generator, and (optionally) distribution read these hints, so the next cycle of prompts and briefs is informed by what actually moved the needle.

So the platform is **autolearning**: it uses real citation and brand-mention outcomes to steer prompt design and brief generation toward strategies that get you cited more often in LLM answers.

## Features

- **Web dashboard** — Sign up, sign in, and manage API keys and model names (OpenAI, Anthropic, Perplexity, Gemini) in Settings. Add domains, run discovery, generate prompts, and trigger monitoring from the UI. View execution history, prompt visibility (cited / brand mentioned / competitor-only per model), and citation trends.
- **Try it free (trial)** — No sign-up required. At `/try`, enter a website URL; the system runs domain discovery (categories, niche, value proposition, competitors), generates prompts, and runs monitoring across all configured models. Results appear on a canonical page `/try/<slug>` (e.g. `/try/www-spydra-app`). Same-domain trials within 7 days reuse the last result. The trial results page shows domain discovery, visibility table, and per-prompt details: citations, mentions (own vs competitors), and full LLM responses.

## Setup

```bash
# Backend
python3 -m venv .venv
source .venv/bin/activate   # or .venv\Scripts\activate on Windows
pip install -r requirements.txt
cp .env.example .env
# Edit .env: set OPENAI_API_KEY, ANTHROPIC_API_KEY, PERPLEXITY_API_KEY (or others), TRACKED_DOMAINS, JWT_SECRET

# Frontend
cd frontend && npm install && cd ..
```

**Environment (`.env`):** See `.env.example`. Key variables: `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `PERPLEXITY_API_KEY`, `GOOGLE_API_KEY` (Gemini), `TRACKED_DOMAINS`, `JWT_SECRET` (required for auth). Optional: `TRIAL_PROMPTS_COUNT` (default 5), `TRIAL_DELAY_SECONDS` (default 5) for the trial flow.

## Run

**1. Domain discovery (recommended before prompts)**

Crawls each tracked domain, uses AI to extract category, up to 3 categories, niche, value proposition, key topics, target audience, and competitors, and stores profiles in the DB (and optionally `config/domain_profiles.yaml`). Prompt generation uses these profiles for **domain-specific** prompts.

```bash
cd /path/to/llm-seo
export PYTHONPATH=.
python3 -m src.domain_discovery.run_discovery
```

Requires at least one of `OPENAI_API_KEY` or `ANTHROPIC_API_KEY` in `.env`. Domains come from `TRACKED_DOMAINS` (`.env`) or `tracked_domains` in `config/domains.yaml`. When using the web app, domains are managed in the UI and discovery can be run from there.

**2. Generate prompts (once or when refreshing)**

If domain profiles exist (from discovery), prompts are generated **per domain** using each profile. Otherwise uses the single `niche` from config. Prompts are filtered so they do not mention the domain or brand name (discovery-style queries only).

```bash
export PYTHONPATH=.
python3 -m src.monitor.prompt_generator
```

**3. Run monitoring (daily or from UI)**

```bash
export PYTHONPATH=.
python3 -m src.monitor.run_monitor --limit 50
```

**Citations:** **Perplexity** (e.g. `sonar` / `sonar-pro`) returns source URLs in the API response. For **OpenAI**, set `OPENAI_USE_WEB_SEARCH=1` and optionally `OPENAI_SEARCH_MODEL` to use a web-search model; responses can include citation annotations we parse. For **Anthropic**, set `ANTHROPIC_USE_WEB_SEARCH=1` for cited answers. For **Gemini**, set `GOOGLE_API_KEY`; the monitor uses Google Search grounding for citation URLs. To inspect raw API responses and parser output: `python3 scripts/diagnose_citations.py` (optionally `--prompt-id 1`).

**4. Start API + frontend**

```bash
# Terminal 1: API
export PYTHONPATH=.
uvicorn api.main:app --reload --port 8000

# Terminal 2: Frontend
cd frontend && npm run dev
```

Open http://localhost:5173 for the dashboard (proxy forwards `/api` to port 8000). Use **Try it free** (or `/try`) to run a trial without signing in.

**5. LLM task queue worker (required for monitoring and trial)**

When you trigger monitoring from the UI or run a trial, LLM calls are enqueued and processed by a **separate worker** so that throughput stays within provider limits. Run the worker in its own process:

```bash
export PYTHONPATH=.
python3 -m src.monitor.llm_task_queue
```

Optional: `--once` to process a single task and exit; `--delay 5` to set the delay between tasks (default: `QUEUE_DELAY_SECONDS` or `TRIAL_DELAY_SECONDS` from `.env`, or 5). Keep this process running (e.g. in a separate terminal or as a systemd service) whenever the API is used for monitoring or trials.

**Runs stuck ("Runs in progress" never finishes)?** Monitoring and trial runs enqueue LLM tasks; a **worker must be running** to process them. Check the queue:

```bash
# Queue status (all executions)
python3 -m src.monitor.llm_task_queue --status

# Queue status for one execution (e.g. from trial token)
python3 -m src.monitor.llm_task_queue --status --execution-id 123
```

Or call `GET /api/queue/status?token=YOUR_TRIAL_TOKEN` (or `?execution_id=123`). If `pending` > 0 and nothing is being processed, start the worker (see above). If there are `recent_errors`, inspect the messages for API key or rate-limit issues.

**Production:** The app is hosted at **https://truseo.io**. For production builds, set `VITE_API_URL` (or proxy `/api` to your API) and configure `API_BASE_URL` / `PUBLIC_URL` in `.env` accordingly.

**Trial / domain analysis not working?**

1. **API URL** — The frontend must call the same API that serves the app. Build with `VITE_API_URL=` (empty) if the API is on the same origin (e.g. reverse proxy); otherwise set `VITE_API_URL=https://your-api-host` so `POST /api/trial/run` and `GET /api/trial/status` hit the correct server.
2. **Queue worker** — Trial runs enqueue LLM tasks; the worker must be running (`python3 -m src.monitor.llm_task_queue`) or runs stay "in progress" and never finish.
3. **Rate limit / CAPTCHA** — If you hit rate limit (429) or CAPTCHA (400), the form shows the error. Adjust `TRIAL_RATE_LIMIT_*` or configure Turnstile; leave `TURNSTILE_SECRET_KEY` unset to disable CAPTCHA.
4. **Domain reachability** — The server checks that the domain responds to HTTP(S). Invalid or unreachable domains return a clear error.
5. **Logs** — Server logs include `trial_run_start`, `trial_run_domain_ok`, `trial_status_ok` / `trial_status_token_not_found`. Use them to see where the flow stops.

**6. Gap & Brief agent (weekly)**

```bash
PYTHONPATH=. python3 -m src.gap_brief.run_brief_agent --days 7 --limit 10
```

**7. Content agent (from briefs)**

```bash
PYTHONPATH=. python3 -m src.content.run_content_agent --limit 5
```

**7. Distribution and weekly report**

```bash
PYTHONPATH=. python3 -m src.distribution.run_distribution --report
PYTHONPATH=. python3 -m src.distribution.run_distribution --distribute --limit 5
```

**8. Learning job (Phase B)**

Analyzes citation uplift, cited prompts/niches, and run rates; calls an LLM to produce **learning hints** (prompt_gen_hints, brief_gen_system_extra, channel_weights) and writes `config/learning_hints.yaml`. The prompt generator, brief generator, and distribution steps read these hints so the pipeline improves over time.

```bash
PYTHONPATH=. python3 -m src.learning.run_learning
```

**9. Autonomous orchestrator (Phase A + Phase B)**

Runs the pipeline automatically based on rules: discovery (if profiles missing or >7 days), prompt gen (if no prompts or >7 days), monitor (every 24h), brief (if uncited prompts and few pending briefs), content (if pending briefs), distribution (every 7 days if approved drafts), weekly report (every 7 days), **learning** (every 7 days). State is stored in `data/orchestrator_state.json`.

```bash
# Single run (executes whichever steps are due)
PYTHONPATH=. python3 -m src.orchestrator.run

# See what would run without executing
PYTHONPATH=. python3 -m src.orchestrator.run --dry-run
```

**Cron (e.g. every 6 hours):** `0 */6 * * * cd /path/to/llm-seo && PYTHONPATH=. .venv/bin/python -m src.orchestrator.run`

## Project layout

- `api/` — FastAPI app: citation trends, prompts visibility, runs, trial (run/status/by-slug/directory), auth (signup/signin)
- `api/auth.py` — JWT auth and user/settings
- `src/db/` — SQLite schema, migrations (trial_sessions, categories, domain_profiles.categories, etc.)
- `src/monitor/` — Sprint 1: prompt generation, query runner, citation parser
- `src/gap_brief/` — Sprint 2: gap analysis and content briefs
- `src/content/` — Sprint 3: content generation and CMS
- `src/distribution/` — Sprint 4: distribution and learning loop
- `src/domain_discovery/` — Crawl domains, AI profile extraction (category, categories, niche, value proposition, competitors)
- `src/learning/` — Phase B: learning hints → `config/learning_hints.yaml`
- `src/orchestrator/` — Autonomous loop: discovery, monitor, brief, content, distribution, report, learning
- `frontend/` — React + TypeScript: dashboard, monitoring, prompts, settings, signin/signup, trial (`/try`, `/try/:slug`)
- `config/` — domains, niche; `domain_profiles.yaml` (optional); `learning_hints.yaml` (from learning job)
- `data/` — SQLite DB (created on first run); briefs, drafts, trial_sessions; `orchestrator_state.json`
