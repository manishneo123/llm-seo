import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { getDrafts, type Draft } from '../api/client';

export function Drafts() {
  const navigate = useNavigate();
  const [drafts, setDrafts] = useState<Draft[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getDrafts()
      .then((r) => { setDrafts(r.drafts); setError(null); })
      .catch((e) => setError(e instanceof Error ? e.message : 'Failed to load'));
  }, []);

  if (error) return <div className="dashboard"><h1>Drafts</h1><p className="error">{error}</p></div>;

  return (
    <div className="dashboard">
      <header>
        <h1>Drafts</h1>
        <p>Review and approve content (Sprint 3). Open a draft to see full details and publish to Ghost, Hashnode, WordPress, or Webflow.</p>
      </header>
      <section className="section">
        {drafts.length === 0 ? (
          <p className="table-placeholder">No drafts. Run the Content agent from briefs.</p>
        ) : (
          <table className="prompts-table">
            <thead>
              <tr>
                <th>Title</th>
                <th>Status</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {drafts.map((d) => (
                <tr key={d.id}>
                  <td>
                    <button type="button" className="link-btn" onClick={() => navigate(`/drafts/${d.id}`)}>
                      {d.title?.slice(0, 50)}{d.title && d.title.length > 50 ? '…' : ''}
                    </button>
                  </td>
                  <td>{d.status}</td>
                  <td>
                    <button type="button" className="link-btn" onClick={() => navigate(`/drafts/${d.id}`)}>View</button>
                    {' '}
                    <button type="button" className="link-btn" onClick={() => navigate(`/drafts/${d.id}/publish`)}>Publish</button>
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
