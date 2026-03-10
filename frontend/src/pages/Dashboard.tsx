import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { getDashboardStats, type DashboardStats } from '../api/client';

function StatCard({ label, value, sub }: { label: string; value: number | string; sub?: string }) {
  return (
    <div className="stat-card">
      <div className="stat-value">{value}</div>
      <div className="stat-label">{label}</div>
      {sub != null && sub !== '' && <div className="stat-sub">{sub}</div>}
    </div>
  );
}

export function Dashboard() {
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    getDashboardStats()
      .then((s) => { if (!cancelled) { setStats(s); setError(null); } })
      .catch((e) => { if (!cancelled) setError(e instanceof Error ? e.message : 'Failed to load'); });
    return () => { cancelled = true; };
  }, []);

  if (error) {
    return (
      <div className="dashboard">
        <h1>LLM SEO Dashboard</h1>
        <p className="error">Error: {error}. Is the API running?</p>
      </div>
    );
  }

  if (!stats) {
    return (
      <div className="dashboard">
        <h1>LLM SEO Dashboard</h1>
        <p>Loading…</p>
      </div>
    );
  }

  const lastRun = stats.last_run_at
    ? new Date(stats.last_run_at).toLocaleString(undefined, { dateStyle: 'short', timeStyle: 'short' })
    : '—';

  return (
    <div className="dashboard">
      <header>
        <h1>LLM SEO Dashboard</h1>
        <p>Key numbers from your latest monitoring runs</p>
      </header>

      <section className="section dashboard-stats">
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
    </div>
  );
}
