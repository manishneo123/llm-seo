import { useEffect, useState } from 'react';
import { getCitationTrends, getPromptsVisibility } from '../api/client';
import { CitationTrendsChart } from '../components/CitationTrendsChart';
import { PromptsVisibilityTable } from '../components/PromptsVisibilityTable';

export function Dashboard() {
  const [trends, setTrends] = useState<{ runs: import('../api/client').RunTrend[] } | null>(null);
  const [visibility, setVisibility] = useState<import('../api/client').PromptsVisibilityResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [competitorOnlyFilter, setCompetitorOnlyFilter] = useState(false);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const [t, v] = await Promise.all([
          getCitationTrends(),
          getPromptsVisibility(undefined, 200, competitorOnlyFilter),
        ]);
        if (!cancelled) {
          setTrends(t);
          setVisibility(v);
          setError(null);
        }
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : 'Failed to load');
      }
    }
    load();
    return () => { cancelled = true; };
  }, [competitorOnlyFilter]);

  if (error) {
    return (
      <div className="dashboard">
        <h1>LLM SEO Dashboard</h1>
        <p className="error">Error: {error}. Is the API running on port 8000?</p>
      </div>
    );
  }

  return (
    <div className="dashboard">
      <header>
        <h1>LLM SEO Dashboard</h1>
        <p>Citation visibility across ChatGPT, Claude, and Perplexity</p>
      </header>

      <section className="section">
        <h2>Citation rate over time</h2>
        {trends ? <CitationTrendsChart runs={trends.runs} /> : <p>Loading…</p>}
      </section>

      <section className="section">
        <h2>Prompts: visible vs invisible</h2>
        <p className="section-actions">
          <label>
            <input
              type="checkbox"
              checked={competitorOnlyFilter}
              onChange={(e) => setCompetitorOnlyFilter(e.target.checked)}
            />
            {' '}Show only competitor-only (answer cited others, not us)
          </label>
        </p>
        {visibility ? (
          <PromptsVisibilityTable prompts={visibility.prompts} />
        ) : (
          <p>Loading…</p>
        )}
      </section>
    </div>
  );
}
