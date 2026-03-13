import { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { getDraft, generateBriefImages, type DraftDetail } from '../api/client';
import { getSourceTypeLabel } from '../constants/cms';

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

export function DraftDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [draft, setDraft] = useState<DraftDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [copyFeedback, setCopyFeedback] = useState<string | null>(null);
  const [generatingImages, setGeneratingImages] = useState(false);

  useEffect(() => {
    if (!id) return;
    let cancelled = false;
    async function load() {
      try {
        const d = await getDraft(Number(id));
        if (!cancelled) {
          setDraft(d);
          setError(null);
        }
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : 'Failed to load');
      }
    }
    load();
    return () => { cancelled = true; };
  }, [id]);

  const handleCopyDraft = () => {
    if (!draft) return;
    const text = `# ${draft.title}\n\n${draft.body_md ?? ''}`;
    navigator.clipboard.writeText(text).then(() => setCopyFeedback('Copied!')).catch(() => setCopyFeedback('Failed'));
    setTimeout(() => setCopyFeedback(null), 2000);
  };

  const handleGenerateImages = async () => {
    if (!draft?.brief) return;
    setError(null);
    setGeneratingImages(true);
    try {
      await generateBriefImages(draft.brief.id);
      const d = await getDraft(draft.id);
      setDraft(d);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to generate images');
    } finally {
      setGeneratingImages(false);
    }
  };

  if (error) return <div className="page dashboard"><header className="page-header"><h1 className="page-title">Draft</h1><p className="error">{error}</p><button type="button" className="link-btn" onClick={() => navigate('/drafts')}>← Back to drafts</button></header></div>;
  if (!draft) return <div className="page dashboard"><p className="page-description">Loading…</p></div>;

  return (
    <div className="page dashboard">
      <header className="page-header">
        <button type="button" className="link-btn" onClick={() => navigate('/drafts')}>← Drafts</button>
        <h1 className="page-title">{draft.title}</h1>
        <p className="page-description">Status: {draft.status} · Updated: {draft.updated_at} {draft.published_at ? `· Published: ${draft.published_at}` : ''}</p>
        <div className="brief-actions" style={{ marginTop: '0.5rem' }}>
          <button type="button" className="link-btn" onClick={() => navigate(`/drafts/${draft.id}/publish`)}>
            Prepare &amp; publish →
          </button>
          <button type="button" onClick={handleCopyDraft}>
            {copyFeedback ?? 'Copy draft'}
          </button>
        </div>
      </header>

      <section className="section detail-section">
        <h2 className="section-title">Content</h2>
        {draft.slug && <p><strong>Slug:</strong> {draft.slug}</p>}
        <pre className="draft-body">{draft.body_md}</pre>
      </section>

      {draft.brief && (
        <section className="section detail-section">
          <h2 className="section-title">Generated images</h2>
          {(() => {
            const urls = parseJsonArray(draft.image_urls ?? draft.brief?.image_urls);
            if (urls.length === 0) {
              return (
                <>
                  <p className="section-desc">No images for this draft yet. Generate images from the brief’s image prompts (requires OPENAI_API_KEY).</p>
                  <button type="button" disabled={generatingImages} onClick={handleGenerateImages}>
                    {generatingImages ? 'Generating…' : 'Generate images'}
                  </button>
                </>
              );
            }
            return (
              <>
                <p className="section-desc">Images created for this draft; stored in the project or S3.</p>
                <div className="brief-images-grid">
                  {urls.map((path, i) => {
                    const imgSrc = path.startsWith('http://') || path.startsWith('https://')
                      ? path
                      : `${API_BASE}/api/images/${path.replace(/^.*[/\\]/, '')}`;
                    return (
                      <figure key={i} className="brief-image-fig">
                        <img src={imgSrc} alt={draft.brief?.topic ?? 'Draft image'} />
                        <figcaption>Image {i + 1}</figcaption>
                      </figure>
                    );
                  })}
                </div>
              </>
            );
          })()}
        </section>
      )}

      {draft.brief && (
        <section className="section detail-section">
          <h2>Brief</h2>
          <dl className="detail-dl">
            <dt>Topic</dt><dd>{draft.brief.topic}</dd>
            <dt>Angle</dt><dd>{draft.brief.angle || '—'}</dd>
            <dt>Priority</dt><dd>{draft.brief.priority_score}</dd>
            <dt>Suggested headings</dt><dd>{draft.brief.suggested_headings || '—'}</dd>
            <dt>Entities to mention</dt><dd>{draft.brief.entities_to_mention || '—'}</dd>
            <dt>Schema</dt><dd>{draft.brief.schema_to_add || '—'}</dd>
            <dt>Status</dt><dd>{draft.brief.status}</dd>
          </dl>
          <button type="button" className="link-btn" onClick={() => navigate(`/briefs/${draft.brief!.id}`)}>View full brief →</button>
        </section>
      )}

      {draft.prompt && (
        <section className="section detail-section">
          <h2>Source prompt</h2>
          <p className="prompt-text">{draft.prompt.text}</p>
          {draft.prompt.niche && <p><strong>Niche:</strong> {draft.prompt.niche}</p>}
          <button type="button" className="link-btn" onClick={() => navigate(`/prompts/${draft.prompt!.id}`)}>View prompt detail →</button>
        </section>
      )}

      <section className="section detail-section">
        <h2>Publishing</h2>
        <p className="section-desc">Use &quot;Prepare &amp; publish&quot; above to publish. Publication history below.</p>
        {(draft.publications?.length ?? 0) > 0 && (
          <>
            <h3 className="subsection-heading">Publication history</h3>
            <table className="prompts-table">
              <thead>
                <tr>
                  <th>Source</th>
                  <th>Type</th>
                  <th>Status</th>
                  <th>URL</th>
                  <th>Date</th>
                </tr>
              </thead>
              <tbody>
                {draft.publications!.map((pub) => (
                  <tr key={pub.id}>
                    <td>{pub.content_source_name ?? 'Manual'}</td>
                    <td>{getSourceTypeLabel(pub.content_source_type)}</td>
                    <td>{pub.status}</td>
                    <td>{pub.published_url ? <a href={pub.published_url} target="_blank" rel="noreferrer">{pub.published_url}</a> : pub.error_message ?? '—'}</td>
                    <td>{pub.published_at ?? pub.created_at}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </>
        )}
      </section>
    </div>
  );
}
