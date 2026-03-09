import { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { getDraft, approveDraft, getCmsOptions, submitPublishedUrl, verifyDraftUrl, type DraftDetail, type CmsOptions } from '../api/client';

export function DraftDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [draft, setDraft] = useState<DraftDetail | null>(null);
  const [cmsOptions, setCmsOptions] = useState<CmsOptions | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [actioning, setActioning] = useState(false);
  const [manualUrl, setManualUrl] = useState('');
  const [urlActioning, setUrlActioning] = useState(false);

  useEffect(() => {
    if (!id) return;
    let cancelled = false;
    async function load() {
      try {
        const [d, c] = await Promise.all([getDraft(Number(id)), getCmsOptions()]);
        if (!cancelled) {
          setDraft(d);
          setCmsOptions(c);
          setError(null);
        }
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : 'Failed to load');
      }
    }
    load();
    return () => { cancelled = true; };
  }, [id]);

  const handleApprove = async (publish: boolean, destination?: string) => {
    if (!draft) return;
    setError(null);
    setActioning(true);
    try {
      const r = await approveDraft(draft.id, publish, destination);
      if (r.ok) {
        const d = await getDraft(draft.id);
        setDraft(d);
      } else {
        setError(r.error ?? 'Action failed');
      }
    } finally {
      setActioning(false);
    }
  };

  const handleSubmitUrl = async () => {
    if (!draft || !manualUrl.trim()) return;
    setError(null);
    setUrlActioning(true);
    try {
      await submitPublishedUrl(draft.id, manualUrl.trim());
      const d = await getDraft(draft.id);
      setDraft(d);
      setManualUrl('');
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to submit URL');
    } finally {
      setUrlActioning(false);
    }
  };

  const handleVerify = async () => {
    if (!draft) return;
    setError(null);
    setUrlActioning(true);
    try {
      await verifyDraftUrl(draft.id);
      const d = await getDraft(draft.id);
      setDraft(d);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to verify');
    } finally {
      setUrlActioning(false);
    }
  };

  if (error) return <div className="dashboard"><h1>Draft</h1><p className="error">{error}</p><button type="button" onClick={() => navigate('/drafts')}>← Back to drafts</button></div>;
  if (!draft) return <div className="dashboard"><h1>Draft</h1><p>Loading…</p></div>;

  const cmsDestinations: string[] = cmsOptions
    ? [
        cmsOptions.wordpress && 'wordpress',
        cmsOptions.webflow && 'webflow',
        cmsOptions.ghost && 'ghost',
        cmsOptions.hashnode && 'hashnode',
      ].filter((x): x is string => Boolean(x))
    : [];

  return (
    <div className="dashboard">
      <header>
        <button type="button" className="link-btn" onClick={() => navigate('/drafts')}>← Drafts</button>
        <h1>{draft.title}</h1>
        <p>Status: {draft.status} · Updated: {draft.updated_at} {draft.published_at ? `· Published: ${draft.published_at}` : ''}</p>
      </header>

      <section className="section detail-section">
        <h2>Content</h2>
        {draft.slug && <p><strong>Slug:</strong> {draft.slug}</p>}
        <pre className="draft-body">{draft.body_md}</pre>
      </section>

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
        <h2>Actions</h2>
        {draft.status === 'draft' && (
          <>
            <button type="button" disabled={actioning} onClick={() => handleApprove(false)}>Approve only</button>
            {' '}
            {cmsDestinations.length > 0 ? (
              cmsDestinations.map((dest) => (
                <button key={dest} type="button" disabled={actioning} onClick={() => handleApprove(true, dest)}>
                  Approve &amp; Publish to {dest}
                </button>
              ))
            ) : (
              <button type="button" disabled={actioning} onClick={() => handleApprove(true)}>Approve &amp; Publish (default CMS)</button>
            )}
          </>
        )}
        {draft.status !== 'draft' && <p>No actions available for status: {draft.status}</p>}
      </section>

      <section className="section detail-section">
        <h2>Manual publishing</h2>
        <p>If you published this draft elsewhere (e.g. Figma, another CMS), submit the live URL so we can verify and record it.</p>
        {draft.published_url && (
          <p>
            <strong>Submitted URL:</strong>{' '}
            <a href={draft.published_url} target="_blank" rel="noreferrer">{draft.published_url}</a>
            {' · '}
            <strong>Status:</strong> {draft.verification_status ?? '—'}
            {draft.verified_at && ` · Verified: ${draft.verified_at}`}
          </p>
        )}
        <div className="submit-url-row">
          <input
            type="url"
            className="submit-url-input"
            placeholder="https://..."
            value={manualUrl}
            onChange={(e) => setManualUrl(e.target.value)}
            disabled={urlActioning}
          />
          <button type="button" disabled={urlActioning || !manualUrl.trim()} onClick={handleSubmitUrl}>
            Submit URL
          </button>
          {draft.published_url && (
            <button type="button" disabled={urlActioning} onClick={handleVerify}>
              Re-verify
            </button>
          )}
        </div>
      </section>
    </div>
  );
}
