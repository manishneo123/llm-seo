import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { getBriefs, type Brief } from '../api/client';

export function Briefs() {
  const navigate = useNavigate();
  const [briefs, setBriefs] = useState<Brief[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getBriefs()
      .then((r) => { setBriefs(r.briefs); setError(null); })
      .catch((e) => setError(e instanceof Error ? e.message : 'Failed to load'));
  }, []);

  if (error) return <div className="page dashboard"><header className="page-header"><h1 className="page-title">Content briefs</h1><p className="error">{error}</p></header></div>;

  return (
    <div className="page dashboard">
      <header className="page-header">
        <h1 className="page-title">Content briefs</h1>
        <p className="page-description">Prioritized briefs from uncited prompts (Sprint 2). Open a brief to see full details.</p>
      </header>
      <section className="section">
        <h2 className="section-title">All briefs</h2>
        {briefs.length === 0 ? (
          <p className="table-placeholder">No briefs yet. Run the Gap & Brief agent.</p>
        ) : (
          <table className="prompts-table">
            <thead>
              <tr>
                <th>Priority</th>
                <th>Topic</th>
                <th>Angle</th>
                <th>Status</th>
                <th>Draft</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {briefs.map((b) => (
                <tr key={b.id}>
                  <td>{b.priority_score}</td>
                  <td>
                    <button type="button" className="link-btn" onClick={() => navigate(`/briefs/${b.id}`)}>
                      {b.topic?.slice(0, 50)}{b.topic && b.topic.length > 50 ? '…' : ''}
                    </button>
                  </td>
                  <td>{b.angle?.slice(0, 60)}{b.angle && b.angle.length > 60 ? '…' : ''}</td>
                  <td>{b.status}</td>
                  <td>
                    {b.draft?.id ? (
                      <button type="button" className="link-btn" onClick={() => navigate(`/drafts/${b.draft!.id}`)}>
                        View draft →
                      </button>
                    ) : (
                      '—'
                    )}
                  </td>
                  <td>
                    <button type="button" className="link-btn" onClick={() => navigate(`/briefs/${b.id}`)}>View details →</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </div>
  );
}
