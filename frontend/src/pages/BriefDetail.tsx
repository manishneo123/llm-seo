import { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { getBrief, type BriefDetail } from '../api/client';

const API_BASE = import.meta.env.VITE_API_URL || '';

function parseJsonArray(s: string | null | undefined): string[] {
  if (!s) return [];
  try {
    const a = JSON.parse(s);
    return Array.isArray(a) ? a.filter((x): x is string => typeof x === 'string') : [];
  } catch {
    return [];
  }
}

export function BriefDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [brief, setBrief] = useState<BriefDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [copyFeedback, setCopyFeedback] = useState<string | null>(null);

  useEffect(() => {
    if (!id) return;
    let cancelled = false;
    getBrief(Number(id))
      .then((b) => { if (!cancelled) { setBrief(b); setError(null); } })
      .catch((e) => { if (!cancelled) setError(e instanceof Error ? e.message : 'Failed to load'); });
    return () => { cancelled = true; };
  }, [id]);

  const briefAsText = brief
    ? `# ${brief.topic}\n\n**Priority:** ${brief.priority_score} · **Status:** ${brief.status} · **Created:** ${brief.created_at}\n\n## Angle\n${brief.angle || '—'}\n\n## Suggested headings\n${brief.suggested_headings || '—'}\n\n## Entities to mention\n${brief.entities_to_mention || '—'}\n\n## Schema to add\n${brief.schema_to_add || '—'}\n\n${brief.prompt ? `## Source prompt\n${brief.prompt.text}\n\n**Niche:** ${brief.prompt.niche || '—'}` : ''}`
    : '';

  const handleCopyBrief = () => {
    if (!brief) return;
    navigator.clipboard.writeText(briefAsText).then(() => setCopyFeedback('Copied!')).catch(() => setCopyFeedback('Failed'));
    setTimeout(() => setCopyFeedback(null), 2000);
  };

  const handleDownloadBrief = () => {
    if (!brief) return;
    const blob = new Blob([briefAsText], { type: 'text/markdown' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `brief-${brief.id}-${(brief.topic || 'brief').replace(/[^a-z0-9]+/gi, '-').toLowerCase().slice(0, 40)}.md`;
    a.click();
    URL.revokeObjectURL(url);
  };

  if (error) return <div className="dashboard"><h1>Brief</h1><p className="error">{error}</p><button type="button" onClick={() => navigate('/briefs')}>← Back to briefs</button></div>;
  if (!brief) return <div className="dashboard"><h1>Brief</h1><p>Loading…</p></div>;

  return (
    <div className="dashboard">
      <header>
        <button type="button" className="link-btn" onClick={() => navigate('/briefs')}>← Briefs</button>
        <h1>{brief.topic}</h1>
        <p>Priority: {brief.priority_score} · Status: {brief.status} · Created: {brief.created_at}</p>
        <div className="brief-actions">
          <button type="button" onClick={handleCopyBrief}>
            {copyFeedback ?? 'Copy brief'}
          </button>
          <button type="button" onClick={handleDownloadBrief}>Download brief</button>
          {brief.draft && (
            <button type="button" className="link-btn" onClick={() => navigate(`/drafts/${brief.draft!.id}`)}>
              View draft →
            </button>
          )}
        </div>
      </header>

      <section className="section detail-section">
        <h2>Image prompts</h2>
        {(() => {
          const prompts = parseJsonArray(brief.image_prompts);
          return (
            <div className="brief-images-section">
              {prompts.length > 0 ? (
                <>
                  <p className="section-desc">Images are generated automatically when the draft is created. They are stored and shown on the draft page.</p>
                  <ul className="image-prompts-list">
                    {prompts.map((p, i) => (
                      <li key={i}>{p}</li>
                    ))}
                  </ul>
                </>
              ) : (
                <p className="section-desc">No image prompts. The brief generator can suggest prompts when creating the brief.</p>
              )}
            </div>
          );
        })()}
      </section>

      <section className="section detail-section">
        <h2>Details</h2>
        <dl className="detail-dl">
          <dt>Angle</dt><dd>{brief.angle || '—'}</dd>
          <dt>Suggested headings</dt><dd>{brief.suggested_headings || '—'}</dd>
          <dt>Entities to mention</dt><dd>{brief.entities_to_mention || '—'}</dd>
          <dt>Schema to add</dt><dd>{brief.schema_to_add || '—'}</dd>
        </dl>
      </section>

      {brief.prompt && (
        <section className="section detail-section">
          <h2>Source prompt</h2>
          <p className="prompt-text">{brief.prompt.text}</p>
          {brief.prompt.niche && <p><strong>Niche:</strong> {brief.prompt.niche}</p>}
          <button type="button" className="link-btn" onClick={() => navigate(`/prompts/${brief.prompt!.id}`)}>View prompt detail →</button>
        </section>
      )}

      {brief.draft && (
        <section className="section detail-section">
          <h2>Draft</h2>
          <p>{brief.draft.title} · Status: {brief.draft.status}</p>
          <button type="button" className="link-btn" onClick={() => navigate(`/drafts/${brief.draft!.id}`)}>View draft →</button>
        </section>
      )}
    </div>
  );
}
