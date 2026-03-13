import { useEffect, useState } from 'react';
import { useNavigate, useLocation, useSearchParams } from 'react-router-dom';
import { getPrompts, type PromptListItem } from '../api/client';

const LIVE_LINKS = [
  { id: 'openai', label: 'ChatGPT', url: 'https://chat.openai.com/' },
  { id: 'perplexity', label: 'Perplexity', url: 'https://www.perplexity.ai/' },
  { id: 'anthropic', label: 'Claude', url: 'https://claude.ai/new' },
  { id: 'gemini', label: 'Gemini', url: 'https://www.google.com/search' },
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
  const [searchParams] = useSearchParams();
  const promptGenerationRunIdParam = searchParams.get('prompt_generation_run_id');
  const promptGenerationRunId = promptGenerationRunIdParam ? parseInt(promptGenerationRunIdParam, 10) : undefined;
  const isValidRunId = promptGenerationRunIdParam !== null && promptGenerationRunId != null && !Number.isNaN(promptGenerationRunId);

  const [prompts, setPrompts] = useState<PromptListItem[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [error, setError] = useState<string | null>(null);
  const [copiedId, setCopiedId] = useState<number | null>(null);

  const loadPrompts = (atPage?: number) => {
    const p = atPage ?? page;
    const offset = (p - 1) * PAGE_SIZE;
    getPrompts(PAGE_SIZE, offset, undefined, isValidRunId ? promptGenerationRunId : undefined)
      .then((r) => {
        setPrompts(r.prompts);
        setTotal(r.total);
        setError(null);
      })
      .catch((e) => setError(e instanceof Error ? e.message : 'Failed to load'));
  };

  useEffect(() => {
    loadPrompts();
  }, [page, promptGenerationRunId]);

  // When switching between "all prompts" and "prompts for a specific generation run",
  // always reset pagination to the first page.
  useEffect(() => {
    setPage(1);
  }, [promptGenerationRunIdParam]);

  // When returning from generate page, refresh list so new prompts appear
  useEffect(() => {
    const state = location.state as { generated?: boolean } | null;
    if (state?.generated) {
      setPage(1);
      loadPrompts(1);
      window.history.replaceState({}, document.title, location.pathname);
    }
  }, [location.state]);

  if (error) return <div className="page dashboard"><header className="page-header"><h1 className="page-title">Prompts</h1><p className="error">{error}</p></header></div>;

  return (
    <div className="page dashboard">
      <header className="page-header">
        <h1 className="page-title">Prompts</h1>
        <p className="page-description">All prompts used for monitoring.</p>
        {isValidRunId && (
          <p className="section-desc" style={{ marginTop: '0.25rem' }}>
            Showing prompts from generation run #{promptGenerationRunId}.{' '}
            <button type="button" className="link-btn" onClick={() => navigate('/prompts')}>
              Show all prompts
            </button>
          </p>
        )}
      </header>
      <section className="section">
        <h2 className="section-title">Prompt list</h2>
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
            {isValidRunId
              ? 'No prompts were created in this prompt generation run yet.'
              : 'No prompts yet. Use Prompt generation to create prompts from your domain profiles (run discovery on Domains first).'}
          </p>
        ) : (
          <div className="prompts-table-wrap">
          <table className="prompts-table prompts-list-table">
            <colgroup>
              <col className="col-id" style={{ width: '2.5rem' }} />
              <col className="col-text" style={{ width: '240px' }} />
              <col className="col-niche" style={{ width: '120px' }} />
              <col className="col-citations" style={{ width: '200px' }} />
              <col className="col-mentions" style={{ width: '200px' }} />
              <col className="col-competition" style={{ width: '140px' }} />
              <col className="col-try-live" style={{ width: '200px' }} />
              <col className="col-created" style={{ width: '10rem' }} />
            </colgroup>
            <thead>
              <tr>
                <th className="col-id">ID</th>
                <th className="col-text">Text</th>
                <th className="col-niche">Niche</th>
                <th className="col-citations">Citations (own / other)</th>
                <th className="col-mentions">Mentions (own / other)</th>
                <th className="col-competition">Competition mentioned</th>
                <th className="col-try-live">Try live</th>
                <th className="col-created">Created</th>
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
                    <td className="col-id">{p.id}</td>
                    <td className="col-text">
                      <button type="button" className="link-btn" onClick={() => navigate(`/prompts/${p.id}`)}>
                        {p.text?.slice(0, 60)}{p.text && p.text.length > 60 ? '…' : ''}
                      </button>
                    </td>
                    <td className="col-niche">{p.niche ?? '—'}</td>
                    <td className="col-citations citation-counts-cell">
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
                    <td className="col-mentions citation-counts-cell">
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
                    <td className="col-competition competition-mentioned-cell" title={(p.mentioned_competitors ?? []).join(', ') || undefined}>
                      {(p.mentioned_competitors ?? []).length > 0
                        ? (p.mentioned_competitors ?? []).join(', ')
                        : '—'}
                    </td>
                    <td className="col-try-live try-live-cell">
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
                    <td className="col-created">{p.created_at}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          </div>
        )}
      </section>
    </div>
  );
}
