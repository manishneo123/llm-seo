import { useEffect, useState } from 'react';
import { getWeeklyReport } from '../api/client';

export function Reports() {
  const [summary, setSummary] = useState<string>('');
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getWeeklyReport()
      .then((r) => { setSummary(r.summary); setError(null); })
      .catch((e) => setError(e instanceof Error ? e.message : 'Failed to load'));
  }, []);

  if (error) return <div className="dashboard"><h1>Weekly report</h1><p className="error">{error}</p></div>;

  return (
    <div className="dashboard">
      <header>
        <h1>Weekly report</h1>
        <p>Citation trends and learning summary (Sprint 4)</p>
      </header>
      <section className="section">
        <pre className="draft-body report-summary">{summary || 'Loading…'}</pre>
      </section>
    </div>
  );
}
