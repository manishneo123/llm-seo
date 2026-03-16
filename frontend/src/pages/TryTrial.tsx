import { useEffect, useState, useRef } from 'react';
import { Link, useParams, useNavigate } from 'react-router-dom';
import {
  runTrial,
  getTrialStatus,
  getTrialBySlug,
  getTrialDirectory,
  type MonitoringExecutionDetail,
  type TrialDirectoryItem,
  type TrialCitation,
  type TrialMention,
  type TrialPromptResponse,
} from '../api/client';
const API_BASE = import.meta.env.VITE_API_URL || '';
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from '../components/Card';
import { CheckCircle2, Sparkles, AlertTriangle, Circle } from 'lucide-react';

const TRIAL_TOKEN_KEY = 'llm_seo_trial_token';
const POLL_INTERVAL_MS = 2500;
const TURNSTILE_SITE_KEY = import.meta.env.VITE_TURNSTILE_SITE_KEY as string | undefined;

const MAX_RESPONSE_PREVIEW = 400;

function StatusBadge({ status }: { status: string }) {
  const variant = status === 'finished' ? 'success' : status === 'failed' ? 'error' : status === 'running' ? 'running' : 'default';
  return <span className={`monitoring-status-badge monitoring-status-badge--${variant}`}>{status}</span>;
}

type VisibilityValue = {
  had_own_citation: boolean;
  brand_mentioned: boolean;
  competitor_only: boolean;
};

function VisibilityDot({ value }: { value?: VisibilityValue }) {
  if (!value) {
    return (
      <Circle className="visibility-icon visibility-icon--none" aria-label="Not present" />
    );
  }
  const items: { key: string; label: string }[] = [];
  if (value.had_own_citation) {
    items.push({ key: 'cited', label: 'Cited' });
  }
  if (value.brand_mentioned) {
    items.push({ key: 'brand', label: 'Brand mentioned' });
  }
  if (value.competitor_only) {
    items.push({ key: 'competitor', label: 'Competitor only' });
  }
  if (items.length === 0) {
    items.push({ key: 'none', label: 'Not present' });
  }
  const combinedLabel = items.map((i) => i.label).join(', ');
  return (
    <span className="visibility-dot-multi" aria-label={combinedLabel} title={combinedLabel}>
      {items.map((it) => {
        if (it.key === 'cited') return <CheckCircle2 key={it.key} className="visibility-icon visibility-icon--cited" />;
        if (it.key === 'brand') return <Sparkles key={it.key} className="visibility-icon visibility-icon--brand" />;
        if (it.key === 'competitor') return <AlertTriangle key={it.key} className="visibility-icon visibility-icon--competitor" />;
        return <Circle key={it.key} className="visibility-icon visibility-icon--none" />;
      })}
    </span>
  );
}

function normalizeModelKey(model: string): string {
  return model.toLowerCase().replace(/[^a-z0-9]+/g, '-');
}

function ModelLabel({ model }: { model: string }) {
  const key = normalizeModelKey(model);
  return (
    <span className={`visibility-model-label visibility-model--${key}`}>
      <span className="visibility-model-label-dot" />
      {model}
    </span>
  );
}

function TrialResultsByPrompt({ execution }: { execution: MonitoringExecutionDetail }) {
  const runs = execution.runs || [];
  const citations = execution.citations || [];
  const mentions = execution.mentions || [];
  const promptResponses = execution.prompt_responses || [];
  const visibility = execution.prompt_visibility || [];

  const citationsByPrompt = new Map<number, TrialCitation[]>();
  for (const c of citations) {
    const list = citationsByPrompt.get(c.prompt_id) ?? [];
    list.push(c);
    citationsByPrompt.set(c.prompt_id, list);
  }
  const mentionsByPrompt = new Map<number, TrialMention[]>();
  for (const m of mentions) {
    const list = mentionsByPrompt.get(m.prompt_id) ?? [];
    list.push(m);
    mentionsByPrompt.set(m.prompt_id, list);
  }
  const responsesByPrompt = new Map<number, TrialPromptResponse[]>();
  for (const r of promptResponses) {
    const list = responsesByPrompt.get(r.prompt_id) ?? [];
    list.push(r);
    responsesByPrompt.set(r.prompt_id, list);
  }

  return (
    <Card className="trial-results-by-prompt-card">
      <CardHeader>
        <CardTitle>Results by prompt</CardTitle>
        <CardDescription>Citations, mentions, and LLM responses per prompt and model.</CardDescription>
      </CardHeader>
      <CardContent>
        <div className="trial-prompt-list">
          {visibility.map((pv) => {
            const promptCitations = citationsByPrompt.get(pv.prompt_id) ?? [];
            const promptMentions = mentionsByPrompt.get(pv.prompt_id) ?? [];
            const promptResponsesList = responsesByPrompt.get(pv.prompt_id) ?? [];
            return (
              <div key={pv.prompt_id} className="trial-prompt-card">
                <h3 className="trial-prompt-card-title">{pv.text}</h3>
                {runs.map((run) => {
                  const model = run.model;
                  const runCitations = promptCitations.filter((c) => c.run_id === run.id);
                  const runMentions = promptMentions.filter((m) => m.run_id === run.id);
                  const resp = promptResponsesList.find((r) => r.run_id === run.id);
                  const hasContent = runCitations.length > 0 || runMentions.length > 0 || (resp?.response_text?.trim() ?? '');
                  if (!hasContent) return null;
                  return (
                    <div key={run.id} className="trial-model-block">
                      <h4 className="trial-model-name"><ModelLabel model={model} /></h4>
                      {runCitations.length > 0 && (
                        <div className="trial-detail-row">
                          <span className="trial-detail-label">Citations</span>
                          <ul className="trial-detail-list">
                            {runCitations.map((c, i) => (
                              <li key={i}>
                                <strong>{c.cited_domain || '—'}</strong>
                                {c.is_own_domain && <span className="trial-own-badge">own</span>}
                                {c.raw_snippet && (
                                  <blockquote className="trial-snippet">{c.raw_snippet}</blockquote>
                                )}
                              </li>
                            ))}
                          </ul>
                        </div>
                      )}
                      {runMentions.length > 0 && (
                        <div className="trial-detail-row">
                          <span className="trial-detail-label">Mentions</span>
                          <ul className="trial-detail-list">
                            {runMentions.map((m, i) => (
                              <li key={i}>
                                {m.mentioned || '—'}
                                {m.is_own_domain ? <span className="trial-own-badge">own</span> : <span className="trial-comp-badge">competitor</span>}
                              </li>
                            ))}
                          </ul>
                        </div>
                      )}
                      {resp?.response_text?.trim() && (
                        <div className="trial-detail-row">
                          <span className="trial-detail-label">LLM response</span>
                          <ResponsePreview text={resp.response_text} />
                        </div>
                      )}
                    </div>
                  );
                })}
                {promptCitations.length === 0 && promptMentions.length === 0 && promptResponsesList.length === 0 && (
                  <p className="trial-prompt-empty">No citations, mentions, or responses recorded for this prompt.</p>
                )}
              </div>
            );
          })}
        </div>
      </CardContent>
    </Card>
  );
}

function ResponsePreview({ text }: { text: string }) {
  const [expanded, setExpanded] = useState(false);
  const isLong = text.length > MAX_RESPONSE_PREVIEW;
  const display = expanded || !isLong ? text : text.slice(0, MAX_RESPONSE_PREVIEW) + '…';
  return (
    <div className="trial-response-wrap">
      <pre className="trial-response-pre">{display}</pre>
      {isLong && (
        <button type="button" className="link-btn btn-sm" onClick={() => setExpanded(!expanded)}>
          {expanded ? 'Show less' : 'Show more'}
        </button>
      )}
    </div>
  );
}

function ResultsView({
  execution,
  slugDisplay,
  onStartOver,
  showStartOver = true,
}: {
  execution: MonitoringExecutionDetail;
  slugDisplay?: string;
  onStartOver: () => void;
  showStartOver?: boolean;
}) {
  const discovery = execution.discovery;
  return (
    <div className="page dashboard try-results-page">
      <header className="page-header">
        {showStartOver && (
          <button type="button" className="trial-results-back" onClick={onStartOver}>
            ← Start over
          </button>
        )}
        <h1 className="page-title">
          {slugDisplay ? `Results for ${slugDisplay}` : 'Trial results'}
        </h1>
        <p className="page-description">
          {execution.started_at}
          {execution.finished_at ? ` · Finished ${execution.finished_at}` : ''}
        </p>
        <div className="trial-results-meta">
          <StatusBadge status={execution.status} />
          {execution.status === 'finished' && slugDisplay && (
            <button
              type="button"
              className="btn-secondary btn-sm"
              onClick={() => window.open(`${API_BASE}/api/trial/report/${encodeURIComponent(slugDisplay)}.pdf`, '_blank')}
            >
              Download PDF report
            </button>
          )}
        </div>
      </header>

      {discovery && (
        <Card className="trial-results-card">
          <CardHeader>
            <CardTitle>Domain discovery</CardTitle>
            <CardDescription>Profile detected for this domain.</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="discovery-grid trial-discovery-grid">
              <div className="discovery-item">
                <span className="discovery-label">Categories</span>
                <span className="discovery-value">{discovery.categories?.length ? discovery.categories.join(' → ') : discovery.category || '—'}</span>
              </div>
              <div className="discovery-item">
                <span className="discovery-label">Niche</span>
                <span className="discovery-value">{discovery.niche || '—'}</span>
              </div>
              <div className="discovery-item">
                <span className="discovery-label">Description / Value proposition</span>
                <span className="discovery-value">{discovery.value_proposition || '—'}</span>
              </div>
              <div className="discovery-item">
                <span className="discovery-label">Target audience</span>
                <span className="discovery-value">{discovery.target_audience || '—'}</span>
              </div>
              <div className="discovery-item">
                <span className="discovery-label">Key topics</span>
                <span className="discovery-value">
                  {discovery.key_topics?.length ? discovery.key_topics.join(', ') : '—'}
                </span>
              </div>
              <div className="discovery-item">
                <span className="discovery-label">Competitors</span>
                <span className="discovery-value">
                  {discovery.competitors?.length ? discovery.competitors.join(', ') : '—'}
                </span>
              </div>
              {discovery.discovered_at && (
                <div className="discovery-item">
                  <span className="discovery-label">Discovered at</span>
                  <span className="discovery-value">{discovery.discovered_at}</span>
                </div>
              )}
            </div>
          </CardContent>
        </Card>
      )}

      <Card className="trial-results-card">
        <CardHeader>
          <CardTitle>Runs by model</CardTitle>
          <CardDescription>Each run corresponds to one model for this execution.</CardDescription>
        </CardHeader>
        <CardContent>
          {execution.runs.length === 0 ? (
            <div className="trial-results-empty">No runs for this execution.</div>
          ) : (
            <div className="monitoring-table-wrap">
              <table className="prompts-table monitoring-table">
                <thead>
                  <tr>
                    <th>Run</th>
                    <th>Model</th>
                    <th>Started</th>
                    <th>Finished</th>
                    <th>Prompts</th>
                    <th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {execution.runs.map((r) => (
                    <tr key={r.id}>
                      <td><span className="monitoring-id">#{r.id}</span></td>
                      <td><ModelLabel model={r.model} /></td>
                      <td>{r.started_at}</td>
                      <td>{r.finished_at ?? '—'}</td>
                      <td>{r.prompt_count}</td>
                      <td><StatusBadge status={r.status} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>

      {execution.prompt_visibility && execution.prompt_visibility.length > 0 && (
        <Card className="trial-results-card">
          <CardHeader>
            <CardTitle>Prompt visibility</CardTitle>
            <CardDescription>Per-prompt citation and brand mention status across all models.</CardDescription>
          </CardHeader>
          <CardContent className="execution-visibility-content">
            <div className="visibility-legend">
              <span className="visibility-legend-item">
                <CheckCircle2 className="visibility-icon visibility-icon--cited" />
                Cited
              </span>
              <span className="visibility-legend-item">
                <Sparkles className="visibility-icon visibility-icon--brand" />
                Brand mentioned
              </span>
              <span className="visibility-legend-item">
                <AlertTriangle className="visibility-icon visibility-icon--competitor" />
                Competitor only
              </span>
              <span className="visibility-legend-item">
                <Circle className="visibility-icon visibility-icon--none" />
                Not present
              </span>
            </div>
            <div className="prompts-table-wrap execution-visibility-wrap">
              <table className="prompts-table execution-visibility-table">
                <colgroup>
                  <col className="col-prompt" style={{ width: '280px' }} />
                  <col className="col-niche" style={{ width: '140px' }} />
                </colgroup>
                <thead>
                  <tr>
                    <th className="col-prompt">Prompt</th>
                    <th className="col-niche">Niche</th>
                    {execution.runs.map((r) => (
                      <th key={r.id} className="execution-visibility-model-header">
                        {r.model}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {execution.prompt_visibility.map((pv) => {
                    const byModel = Object.fromEntries(pv.visibility_by_run.map((v) => [v.model, v]));
                    return (
                      <tr key={pv.prompt_id}>
                        <td className="col-prompt execution-visibility-prompt-cell" title={pv.text}>
                          {pv.text.slice(0, 56)}{pv.text.length > 56 ? '…' : ''}
                        </td>
                        <td className="col-niche execution-visibility-niche-cell">{pv.niche ? pv.niche.slice(0, 24) + (pv.niche.length > 24 ? '…' : '') : '—'}</td>
                        {execution.runs.map((r) => {
                          const v = byModel[r.model] as VisibilityValue | undefined;
                          return (
                            <td key={r.id} className="execution-visibility-cell">
                              <VisibilityDot value={v} />
                            </td>
                          );
                        })}
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      )}

      {(execution.citations?.length || execution.mentions?.length || execution.prompt_responses?.length) ? (
        <TrialResultsByPrompt execution={execution} />
      ) : null}

      {/* Sign up CTA commented out for now
      <Card className="trial-results-card trial-results-cta">
        <CardContent>
          <p className="trial-results-cta-text">Sign up to save results, add more domains, and run monitoring on a schedule.</p>
          <Link to="/signup" className="btn-primary">Sign up</Link>
        </CardContent>
      </Card>
      */}
    </div>
  );
}

export function TryTrial() {
  const { slug: slugParam } = useParams<{ slug: string }>();
  const navigate = useNavigate();
  const [website, setWebsite] = useState('');
  const [token, setToken] = useState<string | null>(null);
  const [execution, setExecution] = useState<MonitoringExecutionDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [directory, setDirectory] = useState<TrialDirectoryItem[]>([]);
  const [slugLoaded, setSlugLoaded] = useState(false);
  const [turnstileReady, setTurnstileReady] = useState(false);
  const [turnstileToken, setTurnstileToken] = useState<string | null>(null);
  const [statusError, setStatusError] = useState<string | null>(null);
  const [retryCount, setRetryCount] = useState(0);
  const [lastTrialSlug, setLastTrialSlug] = useState<string | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const turnstileContainerRef = useRef<HTMLDivElement | null>(null);
  const pollFailuresRef = useRef(0);

  const isDone = execution && (execution.status === 'finished' || execution.status === 'failed');

  // On home page load/refresh: always show the analyse form (clear any previous trial state so multiple users see a fresh form)
  useEffect(() => {
    if (!slugParam) {
      sessionStorage.removeItem(TRIAL_TOKEN_KEY);
      setToken(null);
      setExecution(null);
      setLastTrialSlug(null);
      setStatusError(null);
    }
  }, []);

  // On slug page without token, restore from sessionStorage so polling can run (e.g. same user opened shared link)
  useEffect(() => {
    if (slugParam && !token) {
      const stored = sessionStorage.getItem(TRIAL_TOKEN_KEY);
      if (stored) setToken(stored);
    }
  }, [slugParam, token]);

  // Load by slug when on /try/:slug
  useEffect(() => {
    if (!slugParam) {
      setSlugLoaded(true);
      return;
    }
    setStatusError(null);
    getTrialBySlug(slugParam)
      .then((data) => {
        setExecution(data);
        setSlugLoaded(true);
        pollFailuresRef.current = 0;
      })
      .catch(() => {
        const stored = sessionStorage.getItem(TRIAL_TOKEN_KEY);
        if (stored) {
          setToken(stored);
        }
        setSlugLoaded(true);
      });
  }, [slugParam]);

  // Directory for /try (no slug)
  useEffect(() => {
    if (slugParam) return;
    getTrialDirectory({ limit: 20, offset: 0 })
      .then((res) => setDirectory(res.trials || []))
      .catch(() => setDirectory([]));
  }, [slugParam]);

  // Load Cloudflare Turnstile script when site key is configured
  useEffect(() => {
    if (!TURNSTILE_SITE_KEY) return;
    if (document.querySelector('script[src*="challenges.cloudflare.com/turnstile"]')) {
      setTurnstileReady(true);
      return;
    }
    const script = document.createElement('script');
    script.src = 'https://challenges.cloudflare.com/turnstile/v0/api.js';
    script.async = true;
    script.onload = () => setTurnstileReady(true);
    document.head.appendChild(script);
    return () => {};
  }, []);

  // Render Turnstile widget when script is ready and form is shown (no slug). Cloudflare may set window.turnstile shortly after script load.
  useEffect(() => {
    if (!TURNSTILE_SITE_KEY || !turnstileReady || slugParam) return;
    const el = turnstileContainerRef.current;
    if (!el) return;

    const win = window as unknown as { turnstile?: { render: (el: HTMLElement, opts: { sitekey: string; callback: (token: string) => void }) => string; reset?: (id: string) => void } };
    let widgetId: string | null = null;

    function doRender(): void {
      if (!win.turnstile || !el) return;
      const rawId = win.turnstile.render(el, {
        sitekey: TURNSTILE_SITE_KEY as string,
        callback: (token: string) => setTurnstileToken(token),
      });
      widgetId = rawId === undefined || rawId === null ? null : rawId;
    }

    doRender();
    if (widgetId === null) {
      const t = setTimeout(doRender, 200);
      return () => {
        clearTimeout(t);
        try {
          if (typeof widgetId === 'string') win.turnstile?.reset?.(widgetId);
        } catch {
          /* ignore */
        }
      };
    }

    return () => {
      try {
        if (typeof widgetId === 'string') win.turnstile?.reset?.(widgetId);
      } catch {
        /* ignore */
      }
    };
  }, [turnstileReady, slugParam]);

  // Poll by token (on home page after submit, or on /try/:slug) so progress/results show without redirect
  useEffect(() => {
    if (!token) return;
    pollFailuresRef.current = 0;
    setStatusError(null);
    function poll() {
      getTrialStatus(token!)
        .then((data) => {
          pollFailuresRef.current = 0;
          setExecution(data);
          setStatusError(null);
          if (data.status === 'finished' || data.status === 'failed') {
            if (pollRef.current) {
              clearInterval(pollRef.current);
              pollRef.current = null;
            }
          }
        })
        .catch(() => {
          pollFailuresRef.current += 1;
          if (pollFailuresRef.current >= 4) {
            setStatusError(
              'Unable to load status. The analysis may still be running—check back in a few minutes, or run a new trial below.'
            );
            if (pollRef.current) {
              clearInterval(pollRef.current);
              pollRef.current = null;
            }
          }
        });
    }
    poll();
    pollRef.current = setInterval(poll, POLL_INTERVAL_MS);
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [token, retryCount]);

  // Poll by slug when viewing /try/:slug without a token and execution is still running
  useEffect(() => {
    if (!slugParam) return;
    if (!execution) return;
    if (execution.status === 'finished' || execution.status === 'failed') return;
    const intervalId = setInterval(() => {
      getTrialBySlug(slugParam)
        .then((data) => {
          setExecution(data);
        })
        .catch(() => {});
    }, POLL_INTERVAL_MS);
    return () => clearInterval(intervalId);
  }, [slugParam, execution?.status]);

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const value = website.trim();
    if (!value) return;
    setError(null);
    setSubmitting(true);
    runTrial(value, turnstileToken ?? undefined, false)
      .then((res) => {
        if (!res || !res.token) {
          throw new Error('Trial did not return a session token. Please try again.');
        }
        sessionStorage.setItem(TRIAL_TOKEN_KEY, res.token);
        setToken(res.token);
        setLastTrialSlug(res.slug);
        setStatusError(null);
        pollFailuresRef.current = 0;
        if (res.execution) {
          setExecution(res.execution);
        } else {
          setExecution(null);
        }
      })
      .catch((err) => {
        setError(err instanceof Error ? err.message : 'Trial failed');
      })
      .finally(() => setSubmitting(false));
  }

  function handleStartOver() {
    sessionStorage.removeItem(TRIAL_TOKEN_KEY);
    setToken(null);
    setExecution(null);
    setLastTrialSlug(null);
    setStatusError(null);
    setError(null);
    setWebsite('');
    if (slugParam) navigate('/', { replace: true });
  }

  // Viewing by slug: show loading until slug load attempted
  if (slugParam && !slugLoaded) {
    return (
      <div className="page dashboard try-results-page">
        <header className="page-header">
          <p className="page-description">Loading…</p>
        </header>
      </div>
    );
  }

  // Viewing by slug: 404 and no token
  if (slugParam && slugLoaded && !execution && !token) {
    return (
      <div className="page dashboard try-results-page">
        <header className="page-header">
          <h1 className="page-title">Try it free</h1>
          <p className="page-description">No recent results for this domain (or results are older than 7 days). Run a new trial below.</p>
          <Link to="/" className="btn-primary">Run a trial</Link>
        </header>
      </div>
    );
  }

  // On home page (no slug) show form only when there is no active trial; otherwise show progress/results below
  if (!slugParam && !token) {
    return (
      <div className="page dashboard try-results-page">
        <header className="page-header">
          <h1 className="page-title">Try it free</h1>
          <p className="page-description">
            Enter your website and we&apos;ll generate prompts and run monitoring across models. No sign-up required.
          </p>
          <ul className="home-highlights" aria-label="Product highlights">
            <li><strong>Agentic pipeline</strong> — Discovers your domain, generates prompts, and monitors ChatGPT, Perplexity, Claude &amp; Gemini in one flow.</li>
            <li><strong>Self-learning</strong> — Learns which content drives more citations and brand mentions, then steers prompts and briefs toward what works.</li>
            <li><strong>Visibility that matters</strong> — See where you&apos;re cited, where competitors appear, and turn gaps into content briefs.</li>
            <li><strong>Built for LLM search</strong> — Optimize for how people find answers in AI assistants, not just traditional search.</li>
          </ul>
        </header>
        <Card className="trial-results-card trial-form-card">
          <CardHeader>
            <CardTitle>Run a trial</CardTitle>
            <CardDescription>We&apos;ll discover your domain, generate prompts, and run monitoring.</CardDescription>
          </CardHeader>
          <CardContent>
            <form
              className="trial-form"
              onSubmit={(e) => e.preventDefault()}
            >
              <div className="form-group">
                <label htmlFor="trial-website" className="form-label">Website</label>
                <input
                  id="trial-website"
                  type="text"
                  className="form-input"
                  placeholder="example.com"
                  value={website}
                  onChange={(e) => setWebsite(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') {
                      e.preventDefault();
                      handleSubmit(e as unknown as React.FormEvent);
                    }
                  }}
                  disabled={submitting}
                  autoFocus
                />
              </div>
              {TURNSTILE_SITE_KEY && (
                <div ref={turnstileContainerRef} className="trial-turnstile-wrap" aria-label="CAPTCHA" />
              )}
              {error && <p className="form-error">{error}</p>}
              <button
                type="button"
                className="btn-primary"
                disabled={submitting || (!!TURNSTILE_SITE_KEY && !turnstileToken)}
                onClick={() => handleSubmit({ preventDefault: () => {} } as React.FormEvent)}
              >
                {submitting ? 'Discovering domain…' : 'Analyse'}
              </button>
            </form>
          </CardContent>
        </Card>
        {directory.length > 0 && (
          <Card className="trial-results-card">
            <CardHeader>
              <CardTitle>Recent Analyses</CardTitle>
              <CardDescription>Click a domain to view results (last 7 days).</CardDescription>
            </CardHeader>
            <CardContent>
              <ul className="trial-directory-list">
                {directory.map((t) => (
                  <li key={t.slug}>
                    <Link to={`/try/${t.slug}`} className="trial-directory-link">
                      {t.website}
                    </Link>
                    <span className="trial-directory-date">
                      {t.finished_at ? new Date(t.finished_at).toLocaleDateString() : ''}
                    </span>
                  </li>
                ))}
              </ul>
            </CardContent>
          </Card>
        )}
      </div>
    );
  }

  // Below: only when we have a slug (viewing /try/:slug). Progress: have token but execution not done yet
  if (!execution) {
    return (
      <div className="page dashboard try-results-page">
        <header className="page-header">
          <h1 className="page-title">Trial</h1>
          <p className="page-description">
            {statusError || 'Generating prompts and starting monitoring…'}
          </p>
          {statusError && (
            <p className="page-description" style={{ marginTop: '1rem' }}>
              <button
                type="button"
                className="btn-secondary"
                style={{ marginRight: '0.5rem' }}
                onClick={() => { setStatusError(null); pollFailuresRef.current = 0; setRetryCount((c) => c + 1); }}
              >
                Retry
              </button>
              <Link to="/" className="btn-primary">Run a new trial</Link>
            </p>
          )}
        </header>
      </div>
    );
  }

  if (!isDone) {
    const discovery = execution.discovery;
    return (
      <div className="page dashboard try-results-page">
        <header className="page-header">
          <h1 className="page-title">Trial – Running monitoring</h1>
          <p className="page-description">We&apos;re querying each model with your prompts. This may take a few minutes.</p>
          <div className="trial-results-meta">
            <StatusBadge status={execution.status} />
          </div>
        </header>
        {discovery && (
          <Card className="trial-results-card">
            <CardHeader>
              <CardTitle>Domain discovery</CardTitle>
              <CardDescription>Profile detected for this domain.</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="discovery-grid trial-discovery-grid">
                <div className="discovery-item">
                  <span className="discovery-label">Categories</span>
                  <span className="discovery-value">{discovery.categories?.length ? discovery.categories.join(' → ') : discovery.category || '—'}</span>
                </div>
                <div className="discovery-item">
                  <span className="discovery-label">Niche</span>
                  <span className="discovery-value">{discovery.niche || '—'}</span>
                </div>
                <div className="discovery-item">
                  <span className="discovery-label">Description</span>
                  <span className="discovery-value">{discovery.value_proposition || '—'}</span>
                </div>
                <div className="discovery-item">
                  <span className="discovery-label">Target audience</span>
                  <span className="discovery-value">{discovery.target_audience || '—'}</span>
                </div>
                <div className="discovery-item">
                  <span className="discovery-label">Key topics</span>
                  <span className="discovery-value">{discovery.key_topics?.length ? discovery.key_topics.join(', ') : '—'}</span>
                </div>
                <div className="discovery-item">
                  <span className="discovery-label">Competitors</span>
                  <span className="discovery-value">{discovery.competitors?.length ? discovery.competitors.join(', ') : '—'}</span>
                </div>
              </div>
            </CardContent>
          </Card>
        )}
        {execution.runs && execution.runs.length > 0 && (
          <Card className="trial-results-card">
            <CardHeader>
              <CardTitle>Runs in progress</CardTitle>
              <CardDescription>Status per model.</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="monitoring-table-wrap">
                <table className="prompts-table monitoring-table">
                  <thead>
                    <tr>
                      <th>Model</th>
                      <th>Status</th>
                      <th>Prompts</th>
                    </tr>
                  </thead>
                  <tbody>
                    {execution.runs.map((r) => (
                      <tr key={r.id}>
                        <td><ModelLabel model={r.model} /></td>
                        <td><StatusBadge status={r.status} /></td>
                        <td>{r.prompt_count}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </CardContent>
          </Card>
        )}
      </div>
    );
  }

  return (
    <ResultsView
      execution={execution}
      slugDisplay={lastTrialSlug ?? slugParam ?? undefined}
      onStartOver={handleStartOver}
      showStartOver={!!slugParam || !!token}
    />
  );
}
