import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Zap, Lightbulb } from 'lucide-react';
import { getDashboardStats, getLearningSummary, type DashboardStats, type LearningSummary } from '../api/client';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '../components/Card';

function StatCard({ label, value, sub }: { label: string; value: number | string; sub?: string }) {
  return (
    <Card className="card-stat">
      <CardContent>
        <div className="card-stat-value">{value}</div>
        <div className="card-stat-label">{label}</div>
        {sub != null && sub !== '' && <div className="card-stat-sub">{sub}</div>}
      </CardContent>
    </Card>
  );
}

export function Dashboard() {
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [learning, setLearning] = useState<LearningSummary | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    getDashboardStats()
      .then((s) => { if (!cancelled) { setStats(s); setError(null); } })
      .catch((e) => { if (!cancelled) setError(e instanceof Error ? e.message : 'Failed to load'); });
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    let cancelled = false;
    getLearningSummary()
      .then((s) => { if (!cancelled) setLearning(s); })
      .catch(() => { if (!cancelled) setLearning(null); });
    return () => { cancelled = true; };
  }, []);

  if (error) {
    return (
      <div className="page dashboard">
        <header className="page-header">
          <h1 className="page-title">TRUSEO Dashboard</h1>
          <p className="error">Error: {error}. Is the API running?</p>
        </header>
      </div>
    );
  }

  if (!stats) {
    return (
      <div className="page dashboard">
        <header className="page-header">
          <h1 className="page-title">TRUSEO Dashboard</h1>
          <p className="page-description">Loading…</p>
        </header>
      </div>
    );
  }

  const lastRun = stats.last_run_at
    ? new Date(stats.last_run_at).toLocaleString(undefined, { dateStyle: 'short', timeStyle: 'short' })
    : '—';

  return (
    <div className="page dashboard">
      <header className="page-header">
        <h1 className="page-title">TRUSEO Dashboard</h1>
        <p className="page-description">Key numbers from your latest monitoring runs</p>
      </header>

      <section className="section">
        <h2 className="section-title">Overview</h2>
        <div className="stat-grid">
          <StatCard label="Prompts tracked" value={stats.total_prompts} />
          <StatCard label="Domains tracked" value={stats.domains_tracked} />
          <StatCard
            label="Prompts with own citation"
            value={stats.prompts_with_own_citation}
            sub={stats.total_prompts ? `${stats.citation_rate_pct}% citation rate` : undefined}
          />
          <StatCard label="Total own citations" value={stats.total_own_citations} sub="Links to your site in answers" />
          <StatCard label="Prompts with brand mentioned" value={stats.prompts_with_brand_mentioned} sub="Brand name in answer text" />
          <StatCard label="Competitor-only answers" value={stats.prompts_competitor_only} sub="Cited others, not you" />
          <StatCard label="Last run" value={lastRun} />
        </div>
        <p className="section-desc" style={{ marginTop: '1rem' }}>
          Based on the latest finished runs. <Link to="/prompts">View prompts</Link> · <Link to="/monitoring">Monitoring</Link>
        </p>
      </section>

      <section className="section dashboard-learning-section">
        <Card className="card-ui dashboard-learning-card">
          <CardHeader>
            <CardTitle className="dashboard-learning-title">
              <Lightbulb size={20} aria-hidden /> What we&apos;ve learned
            </CardTitle>
            <CardDescription>
              Hints from citation and brand uplift, and top drafts that improved visibility.
            </CardDescription>
          </CardHeader>
          <CardContent>
            {learning?.hints?.prompt_gen_hints && (
              <div className="dashboard-learning-block">
                <strong>Prompt generation:</strong>
                <p className="dashboard-learning-text">{learning.hints.prompt_gen_hints}</p>
              </div>
            )}
            {learning?.hints?.brief_gen_system_extra && (
              <div className="dashboard-learning-block">
                <strong>Brief generation:</strong>
                <p className="dashboard-learning-text">{learning.hints.brief_gen_system_extra}</p>
              </div>
            )}
            {learning?.top_uplift && learning.top_uplift.length > 0 && (
              <div className="dashboard-learning-block">
                <strong>Top uplifted drafts:</strong>
                <ul className="dashboard-learning-uplift-list">
                  {learning.top_uplift.map((u) => (
                    <li key={u.draft_id}>
                      <Link to={`/drafts/${u.draft_id}`} className="dashboard-learning-uplift-link">
                        {u.draft_title}
                      </Link>
                      {' '}
                      <span className="dashboard-learning-delta">
                        (citation {u.citation_delta >= 0 ? '+' : ''}{u.citation_delta}%
                        {u.brand_delta != null ? `, brand ${u.brand_delta >= 0 ? '+' : ''}${u.brand_delta}%` : ''})
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
            {learning && !learning?.hints?.prompt_gen_hints && !learning?.hints?.brief_gen_system_extra && (!learning?.top_uplift || learning.top_uplift.length === 0) && (
              <p className="section-desc">Run the learning job and publish drafts to see hints and uplift here.</p>
            )}
          </CardContent>
        </Card>
      </section>

      <section className="section dashboard-try-section">
        <Card className="card-ui dashboard-try-card">
          <CardHeader>
            <CardTitle className="dashboard-try-title">
              <Zap size={20} aria-hidden /> Try it free
            </CardTitle>
            <CardDescription>
              Enter any website URL to run a one-off analysis: domain discovery, prompt generation, and visibility across LLMs—no sign-up required.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <Link to="/try" className="btn-primary">Open Try it free</Link>
          </CardContent>
        </Card>
      </section>
    </div>
  );
}
