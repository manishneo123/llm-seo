import { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { marked } from 'marked';
import {
  getDraft,
  getCmsOptions,
  updateDraft,
  publishDraftToSource,
  submitPublishedUrl,
  generateBriefImages,
  type DraftDetail,
  type CmsOptions,
  type ContentSource,
} from '../api/client';
import { getSourceTypeLabel } from '../constants/cms';

/** Order for grouping: LinkedIn and Notion first, then others. */
const PUBLISH_TYPE_ORDER = ['linkedin', 'notion', 'devto', 'hashnode', 'ghost', 'wordpress', 'webflow'];
function groupContentSourcesByType(sources: ContentSource[]): { type: string; label: string; sources: ContentSource[] }[] {
  const byType = new Map<string, ContentSource[]>();
  for (const s of sources) {
    const t = (s.type || '').toLowerCase();
    if (!byType.has(t)) byType.set(t, []);
    byType.get(t)!.push(s);
  }
  const seen = new Set<string>();
  const result: { type: string; label: string; sources: ContentSource[] }[] = [];
  for (const type of PUBLISH_TYPE_ORDER) {
    const list = byType.get(type);
    if (list?.length && !seen.has(type)) {
      seen.add(type);
      result.push({ type, label: getSourceTypeLabel(type), sources: list });
    }
  }
  byType.forEach((list, type) => {
    if (!seen.has(type)) result.push({ type, label: getSourceTypeLabel(type), sources: list });
  });
  return result;
}

const API_BASE = import.meta.env.VITE_API_URL || '';

/** Rewrite relative image paths ](/file.png) or ](file.png) so preview can load images. Uses baseUrl when set, else /api/images/ (works with proxy or same-origin). */
function rewriteImageUrlsInMarkdown(md: string, baseUrl: string): string {
  const base = baseUrl ? baseUrl.replace(/\/$/, '') : '';
  const prefix = base ? `${base}/api/images/` : '/api/images/';
  return md.replace(
    /\]\((?!https?:\/\/)(\/?)([^)\s]+\.(png|jpg|jpeg|gif|webp))\)/gi,
    (_, _slash, path) => `](${prefix}${path.replace(/^\//, '')})`
  );
}

function parseJsonArray(s: string | string[] | null | undefined): string[] {
  if (!s) return [];
  if (Array.isArray(s)) return s.filter((x): x is string => typeof x === 'string');
  try {
    const a = JSON.parse(s);
    return Array.isArray(a) ? a.filter((x): x is string => typeof x === 'string') : [];
  } catch {
    return [];
  }
}

function getParagraphs(body: string): string[] {
  const trimmed = body.trim();
  if (!trimmed) return [];
  const byDouble = trimmed.split(/\n\n+/).filter((p) => p.trim());
  if (byDouble.length > 1) return byDouble;
  return trimmed.split(/\n/).filter((p) => p.trim()).map((p) => p.trim());
}

function insertImageAfterParagraph(body: string, paragraphIndex: number, imageMarkdown: string): string {
  const paragraphs = getParagraphs(body);
  if (paragraphIndex < 0 || paragraphIndex > paragraphs.length) return body;
  const insert = imageMarkdown.startsWith('!') ? imageMarkdown : `![image](${imageMarkdown})`;
  if (paragraphIndex >= paragraphs.length) return body + (body.trim() ? '\n\n' : '') + insert;
  const before = paragraphs.slice(0, paragraphIndex + 1).join('\n\n');
  const after = paragraphs.slice(paragraphIndex + 1).join('\n\n');
  return after ? `${before}\n\n${insert}\n\n${after}` : `${before}\n\n${insert}`;
}

function imageUrlForMarkdown(path: string): string {
  if (path.startsWith('http://') || path.startsWith('https://')) return path;
  return `/${path.replace(/^.*[/\\]/, '')}`;
}

function autoPlaceImages(body: string, imageUrls: string[]): string {
  if (imageUrls.length === 0) return body;
  const paragraphs = getParagraphs(body);
  if (paragraphs.length === 0) {
    const imageBlocks = imageUrls.map((path, i) => `![Image ${i + 1}](${imageUrlForMarkdown(path)})`);
    return body.trim() ? `${body.trim()}\n\n${imageBlocks.join('\n\n')}` : imageBlocks.join('\n\n');
  }
  const slots = paragraphs.length + 1;
  const positions: number[] = [];
  for (let i = 0; i < imageUrls.length; i++) {
    const slot = Math.floor(((i + 1) / (imageUrls.length + 1)) * slots);
    positions.push(Math.min(slot, paragraphs.length));
  }
  const parts: string[] = [];
  let paraIdx = 0;
  let imgIdx = 0;
  for (let slot = 0; slot <= paragraphs.length; slot++) {
    while (imgIdx < positions.length && positions[imgIdx] === slot) {
      const url = imageUrlForMarkdown(imageUrls[imgIdx]);
      parts.push(`![Image ${imgIdx + 1}](${url})`);
      imgIdx++;
    }
    if (paraIdx < paragraphs.length) {
      parts.push(paragraphs[paraIdx]);
      paraIdx++;
    }
  }
  return parts.join('\n\n');
}

export function PublishDraft() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const draftId = id ? Number(id) : 0;
  const [draft, setDraft] = useState<DraftDetail | null>(null);
  const [cmsOptions, setCmsOptions] = useState<CmsOptions | null>(null);
  const [title, setTitle] = useState('');
  const [bodyMd, setBodyMd] = useState('');
  const [selectedSourceId, setSelectedSourceId] = useState<number | null>(null);
  const [manualUrl, setManualUrl] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [publishing, setPublishing] = useState(false);
  const [urlSubmitting, setUrlSubmitting] = useState(false);
  const [copyFeedback, setCopyFeedback] = useState<string | null>(null);
  const [autoPlaceFeedback, setAutoPlaceFeedback] = useState<string | null>(null);
  const [generatingImages, setGeneratingImages] = useState(false);

  useEffect(() => {
    if (!draftId) return;
    let cancelled = false;
    Promise.all([getDraft(draftId), getCmsOptions()])
      .then(([d, c]) => {
        if (!cancelled) {
          setDraft(d);
          setCmsOptions(c);
          setTitle(d.title ?? '');
          setBodyMd(d.body_md ?? '');
          setError(null);
        }
      })
      .catch((e) => {
        if (!cancelled) setError(e instanceof Error ? e.message : 'Failed to load');
      });
    return () => { cancelled = true; };
  }, [draftId]);

  const contentSources: ContentSource[] = cmsOptions?.content_sources ?? [];
  const imageUrls = draft ? parseJsonArray(draft.image_urls ?? draft.brief?.image_urls) : [];
  const paragraphs = getParagraphs(bodyMd);

  const handleSaveDraft = () => {
    if (!draft) return;
    setError(null);
    setSaving(true);
    updateDraft(draft.id, { title: title.trim(), body_md: bodyMd })
      .then(() => {
        setDraft((prev) => (prev ? { ...prev, title: title.trim(), body_md: bodyMd, updated_at: new Date().toISOString() } : null));
      })
      .catch((e) => setError(e instanceof Error ? e.message : 'Save failed'))
      .finally(() => setSaving(false));
  };

  const handleAutoPlaceImages = () => {
    if (imageUrls.length === 0) {
      setAutoPlaceFeedback('No images to place. Add images to the brief first.');
      setTimeout(() => setAutoPlaceFeedback(null), 3000);
      return;
    }
    setBodyMd((prev) => autoPlaceImages(prev, imageUrls));
    setAutoPlaceFeedback(`${imageUrls.length} image(s) placed in content.`);
    setTimeout(() => setAutoPlaceFeedback(null), 3000);
  };

  const handleInsertImageAfter = (paragraphIndex: number, imagePath: string) => {
    const url = imageUrlForMarkdown(imagePath);
    const imageMarkdown = `![Image](${url})`;
    setBodyMd((prev) => insertImageAfterParagraph(prev, paragraphIndex, imageMarkdown));
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

  const handlePublish = () => {
    if (!draft || selectedSourceId == null) return;
    setError(null);
    setPublishing(true);
    publishDraftToSource(draft.id, {
      content_source_id: selectedSourceId,
      title: title.trim(),
      body_md: bodyMd,
    })
      .then((r) => {
        if (r.published_url) window.open(r.published_url, '_blank');
        getDraft(draft.id).then(setDraft);
      })
      .catch((e) => setError(e instanceof Error ? e.message : 'Publish failed'))
      .finally(() => setPublishing(false));
  };

  const handleCopyContent = () => {
    const text = `# ${title}\n\n${bodyMd}`;
    navigator.clipboard.writeText(text).then(
      () => { setCopyFeedback('Copied!'); setTimeout(() => setCopyFeedback(null), 2500); },
      () => { setCopyFeedback('Failed'); setTimeout(() => setCopyFeedback(null), 2500); }
    );
  };

  const handleSubmitUrl = () => {
    if (!draft || !manualUrl.trim()) return;
    setError(null);
    setUrlSubmitting(true);
    submitPublishedUrl(draft.id, manualUrl.trim())
      .then(() => {
        getDraft(draft.id).then(setDraft);
        setManualUrl('');
      })
      .catch((e) => setError(e instanceof Error ? e.message : 'Submit failed'))
      .finally(() => setUrlSubmitting(false));
  };

  if (error && !draft) {
    return (
      <div className="page dashboard">
        <h1>Publish</h1>
        <p className="error">{error}</p>
        <button type="button" className="btn-secondary" onClick={() => navigate('/drafts')}>← Back to drafts</button>
      </div>
    );
  }
  if (!draft) return <div className="page dashboard"><p className="page-description">Loading…</p></div>;

  return (
    <div className="page dashboard">
      <header className="page-header">
        <button type="button" className="link-btn" onClick={() => navigate(`/drafts/${draft.id}`)}>← Draft</button>
        <h1 className="page-title">Prepare &amp; publish</h1>
        <p className="page-description">Edit content, place images, choose a destination, then publish or copy for manual upload.</p>
      </header>

      {error && <p className="error" style={{ marginBottom: '1rem' }}>{error}</p>}

      <section className="section detail-section">
        <h2 className="section-title">Content</h2>
        <p className="section-desc">Edit title and body below. Save draft to persist changes.</p>
        <label style={{ display: 'block', marginBottom: '0.5rem' }}>
          <strong>Title</strong>
          <input
            type="text"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            className="form-input"
            style={{ display: 'block', width: '100%', maxWidth: '560px', marginTop: '0.25rem' }}
          />
        </label>
        <label style={{ display: 'block', marginBottom: '0.5rem' }}>
          <strong>Body (Markdown)</strong>
          <textarea
            value={bodyMd}
            onChange={(e) => setBodyMd(e.target.value)}
            className="draft-body"
            rows={16}
            style={{ display: 'block', width: '100%', maxWidth: '720px', marginTop: '0.25rem', fontFamily: 'inherit', fontSize: '0.95em' }}
          />
        </label>
        <button type="button" className="btn-primary" onClick={handleSaveDraft} disabled={saving}>{saving ? 'Saving…' : 'Save draft'}</button>
      </section>

      <section className="section detail-section">
        <h2 className="section-title">Preview</h2>
        <p className="section-desc">How the post will look. Images use the same URLs as when published (set PUBLIC_URL in .env for production).</p>
        <div className="publish-preview" style={{ border: '1px solid #ddd', borderRadius: '6px', padding: '1rem 1.25rem', maxWidth: '720px', background: '#fff' }}>
          <h1 style={{ fontSize: '1.5rem', marginBottom: '0.75rem' }}>{title || 'Untitled'}</h1>
          <div
            className="publish-preview-body"
            dangerouslySetInnerHTML={{
              __html: marked(rewriteImageUrlsInMarkdown(bodyMd, API_BASE), { gfm: true }) as string,
            }}
            style={{ fontSize: '0.95rem', lineHeight: 1.6 }}
          />
        </div>
      </section>

      {(imageUrls.length > 0 || draft.brief) && (
        <section className="section detail-section">
          <h2 className="section-title">Images</h2>
          {imageUrls.length === 0 ? (
            <>
              <p className="section-desc">No images for this draft yet. Generate images from the brief’s image prompts (requires OPENAI_API_KEY).</p>
              <button type="button" disabled={generatingImages} onClick={handleGenerateImages} style={{ marginBottom: '0.75rem' }}>
                {generatingImages ? 'Generating…' : 'Generate images'}
              </button>
            </>
          ) : (
            <>
              <p className="section-desc">Place generated images in the content. Use auto-place to distribute them, or insert after a specific paragraph.</p>
              {autoPlaceFeedback && <p style={{ marginBottom: '0.5rem', color: 'var(--color-text-secondary, #555)' }}>{autoPlaceFeedback}</p>}
              <button type="button" onClick={handleAutoPlaceImages} style={{ marginBottom: '0.75rem' }}>Auto-place images in content</button>
              <div className="brief-images-grid" style={{ display: 'flex', flexWrap: 'wrap', gap: '1rem', marginBottom: '0.5rem' }}>
            {imageUrls.map((path, i) => {
              const imgSrc = path.startsWith('http://') || path.startsWith('https://')
                ? path
                : `${API_BASE}/api/images/${path.replace(/^.*[/\\]/, '')}`;
              return (
                <figure key={i} className="brief-image-fig" style={{ margin: 0 }}>
                  <img src={imgSrc} alt="" style={{ maxWidth: '160px', maxHeight: '120px', objectFit: 'contain' }} />
                  <figcaption style={{ fontSize: '0.9em' }}>
                    Image {i + 1}
                    <select
                      value=""
                      onChange={(e) => {
                        const idx = e.target.value ? Number(e.target.value) : -1;
                        if (idx >= 0) handleInsertImageAfter(idx, path);
                        e.target.value = '';
                      }}
                      style={{ marginLeft: '0.5rem' }}
                    >
                      <option value="">Insert after paragraph…</option>
                      {paragraphs.map((_, idx) => (
                        <option key={idx} value={idx}>{idx + 1}</option>
                      ))}
                      {paragraphs.length > 0 && <option value={paragraphs.length}>End</option>}
                    </select>
                  </figcaption>
                </figure>
              );
            })}
              </div>
            </>
          )}
        </section>
      )}

      <section className="section detail-section">
        <h2 className="section-title">Publish to content source</h2>
        <p className="section-desc">Select a destination and publish. Supported: LinkedIn, Notion, Dev.to, Hashnode, Ghost, WordPress, Webflow. Add sources in Content sources. The current title and body above will be used.</p>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', flexWrap: 'wrap', marginBottom: '0.5rem' }}>
          <select
            value={selectedSourceId ?? ''}
            onChange={(e) => setSelectedSourceId(e.target.value ? Number(e.target.value) : null)}
            className="form-input"
            style={{ minWidth: '220px' }}
          >
            <option value="">Select content source</option>
            {groupContentSourcesByType(contentSources).map(({ type, label, sources }) => (
              <optgroup key={type} label={label}>
                {sources.map((s) => (
                  <option key={s.id} value={s.id}>{s.name}</option>
                ))}
              </optgroup>
            ))}
          </select>
          <button
            type="button"
            className="btn-primary"
            onClick={handlePublish}
            disabled={publishing || selectedSourceId == null}
          >
            {publishing ? 'Publishing…' : 'Publish'}
          </button>
        </div>
        {contentSources.length === 0 && (
          <p className="section-desc">No content sources yet. Add a LinkedIn, Notion, or other source in Content sources to publish here.</p>
        )}
      </section>

      <section className="section detail-section">
        <h2 className="section-title">Manual upload</h2>
        <p className="section-desc">Copy the content and paste it into your blog or CMS. After you publish there, submit the URL below.</p>
        <button type="button" className="btn-secondary" onClick={handleCopyContent}>{copyFeedback ?? 'Copy content'}</button>
        <div style={{ marginTop: '0.75rem' }}>
          <label style={{ display: 'block', marginBottom: '0.25rem' }}>Published URL</label>
          <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', alignItems: 'center' }}>
            <input
              type="url"
              className="submit-url-input"
              placeholder="https://..."
              value={manualUrl}
              onChange={(e) => setManualUrl(e.target.value)}
              disabled={urlSubmitting}
              style={{ flex: 1, minWidth: '200px', maxWidth: '400px' }}
            />
            <button type="button" className="btn-primary" disabled={urlSubmitting || !manualUrl.trim()} onClick={handleSubmitUrl}>
              {urlSubmitting ? 'Submitting…' : 'Submit URL'}
            </button>
          </div>
        </div>
        {draft.published_url && (
          <p style={{ marginTop: '0.5rem' }}>
            Recorded: <a href={draft.published_url} target="_blank" rel="noreferrer">{draft.published_url}</a>
            {draft.verification_status && ` · ${draft.verification_status}`}
          </p>
        )}
      </section>
    </div>
  );
}
