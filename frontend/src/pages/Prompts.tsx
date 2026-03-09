import { useEffect, useState } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { getPrompts, getDiscoveryStatus, type PromptListItem } from '../api/client';

const LIVE_LINKS = [
  { id: 'openai', label: 'ChatGPT', url: 'https://chat.openai.com/' },
  { id: 'perplexity', label: 'Perplexity', url: 'https://www.perplexity.ai/' },
  { id: 'anthropic', label: 'Claude', url: 'https://claude.ai/new' },
  { id: 'gemini', label: 'Gemini', url: 'https://gemini.google.com/app' },
] as const;

function openLiveWithPrompt(promptText: string, link: (typeof LIVE_LINKS)[number]) {
  const url = `${link.url}?q=${encodeURIComponent(promptText)}`;
  window.open(url, '_blank', 'noopener,noreferrer');
  navigator.clipboard.writeText(promptText).catch(() => {});
}

const PAGE_SIZE = 20;

export function Prompts() {
  const navigate = useNavigate();
  const location = useLocation();
  const [prompts, setPrompts] = useState<PromptListItem[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [error, setError] = useState<string | null>(null);
  const [copiedId, setCopiedId] = useState<number | null>(null);
  const [discoveryDone, setDiscoveryDone] = useState(false);

  const loadPrompts = (atPage?: number) => {
    const p = atPage ?? page;
    const offset = (p - 1) * PAGE_SIZE;
    getPrompts(PAGE_SIZE, offset)
      .then((r) => {
        setPrompts(r.prompts);
        setTotal(r.total);
        setError(null);
      })
      .catch((e) => setError(e instanceof Error ? e.message : 'Failed to load'));
  };

  useEffect(() => {
    loadPrompts();
  }, [page]);

  useEffect(() => {
    getDiscoveryStatus()
      .then((s) => setDiscoveryDone(s.discovery_done))
      .catch(() => setDiscoveryDone(false));
  }, []);

  // When returning from generate page, refresh list so new prompts appear
  useEffect(() => {
    const state = location.state as { generated?: boolean } | null;
    if (state?.generated) {
      setPage(1);
      loadPrompts(1);
      window.history.replaceState({}, document.title, location.pathname);
    }
  }, [location.state]);

  if (error) return <div className="dashboard"><h1>Prompts</h1><p className="error">{error}</p></div>;

  return (
    <div className="dashboard">
      <header>
        <h1>Prompts</h1>
        <p>All prompts used for monitoring.</p>
        <div className="section-actions" style={{ marginTop: '0.5rem' }}>
          <button type="button" onClick={() => navigate('/prompts/generate')}>
            Generate prompts
          </button>
          {!discoveryDone && (
            <span className="section-desc" style={{ marginLeft: '0.5rem' }}>
              (Add domains and run discovery first)
            </span>
          )}
        </div>
      </header>
      <section className="section">
        {total > 0 && (
          <div className="pagination-bar">
            <button
              type="button"
              disabled={page <= 1}
              onClick={() => setPage((p) => Math.max(1, p - 1))}
            >
              ← Previous
            </button>
            <span className="pagination-info">
              Page {page} of {Math.max(1, Math.ceil(total / PAGE_SIZE))} ({total} total)
            </span>
            <button
              type="button"
              disabled={page >= Math.ceil(total / PAGE_SIZE)}
              onClick={() => setPage((p) => p + 1)}
            >
              Next →
            </button>
          </div>
        )}
        {prompts.length === 0 ? (
          <p className="table-placeholder">
            No prompts yet. Click &quot;Generate prompts&quot; to create prompts from your domain profiles (run discovery on Domains first).
          </p>
        ) : (
          <table className="prompts-table prompts-list-table">
            <thead>
              <tr>
                <th>ID</th>
                <th>Text</th>
                <th>Niche</th>
                <th>Citations (own / other)</th>
                <th>Mentions (own / other)</th>
                <th>Competition mentioned</th>
                <th>Try live</th>
                <th>Created</th>
              </tr>
            </thead>
            <tbody>
              {prompts.map((p) => {
                const counts = p.citation_counts ?? {};
                const mentionCounts = p.mention_counts ?? {};
                const models = ['openai', 'anthropic', 'perplexity', 'gemini'] as const;
                const promptText = p.text ?? '';
                return (
                  <tr key={p.id}>
                    <td>{p.id}</td>
                    <td>
                      <button type="button" className="link-btn" onClick={() => navigate(`/prompts/${p.id}`)}>
                        {p.text?.slice(0, 60)}{p.text && p.text.length > 60 ? '…' : ''}
                      </button>
                    </td>
                    <td>{p.niche ?? '—'}</td>
                    <td className="citation-counts-cell">
                      {models.map((model) => {
                        const c = counts[model] ?? { own: 0, other: 0 };
                        const hasAny = c.own > 0 || c.other > 0;
                        if (!hasAny) return null;
                        return (
                          <span key={model} className="citation-count-badge" title={`${model}: our domain ${c.own}, other sites ${c.other}`}>
                            {model}: {c.own}/{c.other}
                          </span>
                        );
                      })}
                      {models.every((m) => ((counts[m] ?? {}).own + (counts[m] ?? {}).other) === 0) && (
                        <span className="citation-count-empty">—</span>
                      )}
                    </td>
                    <td className="citation-counts-cell">
                      {models.map((model) => {
                        const c = mentionCounts[model] ?? { own: 0, other: 0 };
                        const hasAny = c.own > 0 || c.other > 0;
                        if (!hasAny) return null;
                        return (
                          <span key={model} className="citation-count-badge mention-badge" title={`${model}: our domain ${c.own}, others ${c.other}`}>
                            {model}: {c.own}/{c.other}
                          </span>
                        );
                      })}
                      {models.every((m) => ((mentionCounts[m] ?? {}).own + (mentionCounts[m] ?? {}).other) === 0) && (
                        <span className="citation-count-empty">—</span>
                      )}
                    </td>
                    <td className="competition-mentioned-cell" title={(p.mentioned_competitors ?? []).join(', ') || undefined}>
                      {(p.mentioned_competitors ?? []).length > 0
                        ? (p.mentioned_competitors ?? []).join(', ')
                        : '—'}
                    </td>
                    <td className="try-live-cell">
                      {copiedId === p.id && <span className="try-live-copied">Copied!</span>}
                      {LIVE_LINKS.map((link) => (
                        <a
                          key={link.id}
                          href="#"
                          className="try-live-link"
                          title={`Open in ${link.label} with this prompt`}
                          onClick={(e) => {
                            e.preventDefault();
                            openLiveWithPrompt(promptText, link);
                            setCopiedId(p.id);
                            setTimeout(() => setCopiedId(null), 2000);
                          }}
                        >
                          {link.label}
                        </a>
                      ))}
                    </td>
                    <td>{p.created_at}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </section>
    </div>
  );
}
