import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { getTrialDirectory, type TrialDirectoryItem } from '../api/client';
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from '../components/Card';

const PAGE_SIZE = 20;

export function TrialDirectory() {
  const [items, setItems] = useState<TrialDirectoryItem[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [q, setQ] = useState('');
  const [category, setCategory] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const offset = (page - 1) * PAGE_SIZE;

  useEffect(() => {
    setLoading(true);
    setError(null);
    getTrialDirectory({
      q: q.trim() || undefined,
      category: category.trim() || undefined,
      limit: PAGE_SIZE,
      offset,
    })
      .then((res) => {
        setItems(res.trials || []);
        setTotal(res.total || 0);
      })
      .catch((e) => {
        setError(e instanceof Error ? e.message : 'Failed to load directory');
        setItems([]);
        setTotal(0);
      })
      .finally(() => setLoading(false));
  }, [q, category, offset]);

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <div className="page dashboard">
      <header className="page-header">
        <h1 className="page-title">Trial directory</h1>
        <p className="page-description">
          Browse domains that have been analyzed via the public trial. Click a row to open the full trial results.
        </p>
      </header>

      <Card className="trial-results-card">
        <CardHeader>
          <CardTitle>Domains</CardTitle>
          <CardDescription>Search by domain or category. Results are limited to recent trials.</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="trial-directory-filters">
            <div className="form-group">
              <label className="form-label" htmlFor="trial-dir-q">Domain</label>
              <input
                id="trial-dir-q"
                type="text"
                className="form-input"
                placeholder="example.com"
                value={q}
                onChange={(e) => { setPage(1); setQ(e.target.value); }}
              />
            </div>
            <div className="form-group">
              <label className="form-label" htmlFor="trial-dir-category">Category</label>
              <input
                id="trial-dir-category"
                type="text"
                className="form-input"
                placeholder="e.g. SaaS, Voice AI"
                value={category}
                onChange={(e) => { setPage(1); setCategory(e.target.value); }}
              />
            </div>
          </div>

          {error && <p className="form-error">{error}</p>}

          {loading ? (
            <p className="section-desc">Loading…</p>
          ) : items.length === 0 ? (
            <p className="section-desc">No trial results found for this filter.</p>
          ) : (
            <>
              <div className="monitoring-table-wrap">
                <table className="prompts-table monitoring-table">
                  <thead>
                    <tr>
                      <th>Domain</th>
                      <th>Categories</th>
                      <th>Last run</th>
                      <th></th>
                    </tr>
                  </thead>
                  <tbody>
                    {items.map((t) => (
                      <tr key={t.slug}>
                        <td>{t.website}</td>
                        <td>
                          {(t.categories && t.categories.length > 0) || t.category ? (
                            <span className="trial-directory-tags">
                              {(t.categories && t.categories.length > 0 ? t.categories : t.category ? [t.category] : []).map((c) => (
                                <span key={c} className="trial-directory-tag">{c}</span>
                              ))}
                            </span>
                          ) : (
                            '—'
                          )}
                        </td>
                        <td>{t.finished_at ? new Date(t.finished_at).toLocaleString() : '—'}</td>
                        <td>
                          <Link to={`/try/${t.slug}`} className="link-btn">
                            View results →
                          </Link>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div className="pagination-bar">
                <button
                  type="button"
                  disabled={page <= 1}
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                >
                  ← Previous
                </button>
                <span className="pagination-info">
                  Page {page} of {totalPages} · {total} domains
                </span>
                <button
                  type="button"
                  disabled={page >= totalPages}
                  onClick={() => setPage((p) => p + 1)}
                >
                  Next →
                </button>
              </div>
            </>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

