import { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { getPrompt, type PromptDetail, type MentionItem } from '../api/client';

function citationHref(domain: string, snippet: string | null | undefined): string {
  if (snippet) {
    const match = snippet.match(/https?:\/\/[^\s\]\)"']+/i);
    if (match) return match[0];
  }
  const d = (domain || '').trim();
  if (!d) return '#';
  return d.startsWith('http://') || d.startsWith('https://') ? d : `https://${d}`;
}

export function PromptDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [prompt, setPrompt] = useState<PromptDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [responseModalRunId, setResponseModalRunId] = useState<number | null>(null);

  useEffect(() => {
    if (!id) return;
    let cancelled = false;
    getPrompt(Number(id))
      .then((p) => { if (!cancelled) { setPrompt(p); setError(null); } })
      .catch((e) => { if (!cancelled) setError(e instanceof Error ? e.message : 'Failed to load'); });
    return () => { cancelled = true; };
  }, [id]);

  if (error) return <div className="dashboard"><h1>Prompt</h1><p className="error">{error}</p><button type="button" onClick={() => navigate('/prompts')}>← Back to prompts</button></div>;
  if (!prompt) return <div className="dashboard"><h1>Prompt</h1><p>Loading…</p></div>;

  const models = ['openai', 'anthropic', 'perplexity', 'gemini'] as const;
  const countsByModel = models.map((model) => {
    const forModel = prompt.citations.filter((c) => c.model === model);
    const own = forModel.filter((c) => c.is_own_domain === 1).length;
    const other = forModel.filter((c) => c.is_own_domain !== 1).length;
    return { model, own, other, total: own + other };
  });
  const totalOwn = prompt.citations.filter((c) => c.is_own_domain === 1).length;
  const totalOther = prompt.citations.filter((c) => c.is_own_domain !== 1).length;

  const mentions = prompt.mentions ?? [];
  const mentionCountsByModel = models.map((model) => {
    const forModel = mentions.filter((m) => m.model === model);
    const own = forModel.filter((m) => m.is_own_domain === 1).length;
    const other = forModel.filter((m) => m.is_own_domain === 0).length;
    return { model, own, other, total: own + other };
  });
  const totalMentionOwn = mentions.filter((m) => m.is_own_domain === 1).length;
  const totalMentionOther = mentions.filter((m) => m.is_own_domain === 0).length;
  const anyBrandMentionedInRuns = prompt.runs?.some((r) => r.brand_mentioned === 1) ?? false;
  const groupByModel = (list: MentionItem[]) => {
    const g: Record<string, MentionItem[]> = {};
    for (const m of models) g[m] = [];
    g.other = [];
    for (const c of list) {
      if (models.includes(c.model as typeof models[number])) g[c.model].push(c);
      else g.other.push(c);
    }
    return g;
  };
  const mentionOwnByModel = groupByModel(mentions.filter((m) => m.is_own_domain === 1));
  const mentionOtherByModel = groupByModel(mentions.filter((m) => m.is_own_domain === 0));

  const groupByModelCitations = (list: typeof prompt.citations) => {
    const g: Record<string, typeof prompt.citations> = {};
    for (const m of models) g[m] = [];
    g.other = [];
    for (const c of list) {
      if (models.includes(c.model as typeof models[number])) g[c.model].push(c);
      else g.other.push(c);
    }
    return g;
  };
  const ownByModel = groupByModelCitations(prompt.citations.filter((c) => c.is_own_domain === 1));
  const otherByModel = groupByModelCitations(prompt.citations.filter((c) => c.is_own_domain !== 1));

  return (
    <div className="dashboard">
      <header>
        <button type="button" className="link-btn" onClick={() => navigate('/prompts')}>← Prompts</button>
        <h1>Prompt #{prompt.id}</h1>
        <p>{prompt.niche ? `Niche: ${prompt.niche} · ` : ''}Created: {prompt.created_at}</p>
      </header>

      <section className="section detail-section">
        <h2>Text</h2>
        <p className="prompt-text">{prompt.text}</p>
      </section>

      <section className="section detail-section">
        <h2>Visibility in runs</h2>
        {prompt.runs.length === 0 ? (
          <p>No finished runs yet.</p>
        ) : (
          <table className="prompts-table">
            <thead>
              <tr>
                <th>Run</th>
                <th>Model</th>
                <th>Date</th>
                <th>Cited</th>
                <th>Brand mentioned</th>
                <th>Competitor-only</th>
                <th>Others cited</th>
                <th>Response</th>
              </tr>
            </thead>
            <tbody>
              {prompt.runs.map((r) => {
                const hasResponse = !!(prompt.response_by_run?.[r.id]?.response_text);
                return (
                  <tr key={r.id} data-cited={r.cited} data-competitor-only={r.competitor_only === 1}>
                    <td>{r.id}</td>
                    <td>{r.model}</td>
                    <td>{r.started_at}</td>
                    <td>{r.cited ? 'Yes' : 'No'}</td>
                    <td>{r.brand_mentioned === 1 ? 'Yes' : 'No'}</td>
                    <td>{r.competitor_only === 1 ? 'Yes' : 'No'}</td>
                    <td className="others-cited-cell" title={(r.others_cited ?? []).join(', ') || undefined}>
                      {(r.others_cited ?? []).length > 0 ? (r.others_cited ?? []).join(', ') : '—'}
                    </td>
                    <td>
                      {hasResponse ? (
                        <button
                          type="button"
                          className="link-btn response-details-btn"
                          onClick={() => setResponseModalRunId(r.id)}
                        >
                          Details
                        </button>
                      ) : (
                        '—'
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
        {prompt.runs.some((r) => r.competitor_only === 1 && (r.others_cited ?? []).length > 0) ? (
          <div className="competitor-only-cited section-note">
            <h3>When competitor-only = Yes: others cited in that run</h3>
            <ul>
              {prompt.runs.filter((r) => r.competitor_only === 1 && (r.others_cited ?? []).length > 0).map((r) => (
                <li key={r.id}>
                  <strong>Run {r.id}</strong> ({r.model}): {(r.others_cited ?? []).join(', ')}
                </li>
              ))}
            </ul>
          </div>
        ) : null}
      </section>

      {responseModalRunId != null && prompt.response_by_run?.[responseModalRunId] && (
        <div
          className="response-modal-overlay"
          role="dialog"
          aria-modal="true"
          aria-labelledby="response-modal-title"
          onClick={() => setResponseModalRunId(null)}
        >
          <div className="response-modal" onClick={(e) => e.stopPropagation()}>
            <div className="response-modal-header">
              <h2 id="response-modal-title">
                Run {responseModalRunId} ({prompt.runs.find((r) => r.id === responseModalRunId)?.model ?? 'Unknown'}) — Response
              </h2>
              <button type="button" className="response-modal-close" onClick={() => setResponseModalRunId(null)}>
                Close
              </button>
            </div>
            <pre className="response-modal-content">
              {prompt.response_by_run[responseModalRunId].response_text}
            </pre>
          </div>
        </div>
      )}

      <section className="section detail-section">
        <h2>Citation counts by model</h2>
        <table className="prompts-table citation-counts-table">
          <thead>
            <tr>
              <th>Model</th>
              <th>Our domain</th>
              <th>Other websites</th>
              <th>Total</th>
            </tr>
          </thead>
          <tbody>
            {countsByModel.map(({ model, own, other, total }) => (
              <tr key={model}>
                <td className="model-name">{model}</td>
                <td>{own}</td>
                <td>{other}</td>
                <td>{total}</td>
              </tr>
            ))}
            <tr className="citation-counts-total">
              <td>Total</td>
              <td>{totalOwn}</td>
              <td>{totalOther}</td>
              <td>{totalOwn + totalOther}</td>
            </tr>
          </tbody>
        </table>
      </section>

      <section className="section detail-section">
        <h2>Brand mention counts by model</h2>
        <p className="section-desc">Brand/domain names found in the answer text (our domain vs others e.g. competitors).</p>
        <table className="prompts-table citation-counts-table">
          <thead>
            <tr>
              <th>Model</th>
              <th>Our domain</th>
              <th>Others</th>
              <th>Total</th>
            </tr>
          </thead>
          <tbody>
            {mentionCountsByModel.map(({ model, own, other, total }) => (
              <tr key={model}>
                <td className="model-name">{model}</td>
                <td>{own}</td>
                <td>{other}</td>
                <td>{total}</td>
              </tr>
            ))}
            <tr className="citation-counts-total">
              <td>Total</td>
              <td>{totalMentionOwn}</td>
              <td>{totalMentionOther}</td>
              <td>{totalMentionOwn + totalMentionOther}</td>
            </tr>
          </tbody>
        </table>
      </section>

      <section className="section detail-section">
        <h2>Our domain mentioned (in text)</h2>
        {totalMentionOwn === 0 ? (
          <p>No brand/domain mentions of your tracked domain in answer text yet.</p>
        ) : (
          [...models, 'other'].map((model) => {
            const list = mentionOwnByModel[model] || [];
            if (list.length === 0) return null;
            const distinct = Array.from(new Set(list.map((m) => m.mentioned)));
            return (
              <div key={model} className="citations-by-model">
                <h3 className="citations-model-heading">{model}</h3>
                <ul className="citations-list">
                  {distinct.map((brand) => (
                    <li key={`own-mention-${model}-${brand}`}>
                      <strong>{brand}</strong>
                      {' '}(run(s): {Array.from(new Set(list.filter((m) => m.mentioned === brand).map((m) => m.run_id))).join(', ')})
                    </li>
                  ))}
                </ul>
              </div>
            );
          })
        )}
      </section>

      <section className="section detail-section">
        <h2>Competition mentioned (in text)</h2>
        <p className="section-desc">Competitor brands/domains from discovery that appeared in the answer text.</p>
        {totalMentionOther === 0 ? (
          <>
            <p>No competition mentioned in answer text yet.</p>
            {anyBrandMentionedInRuns ? (
              <p className="section-note">
                Brand/competition was marked as mentioned for some runs but no competitor names from your discovery list were found. Ensure domain discovery has run so <code>config/domain_profiles.yaml</code> has a <code>competitors</code> list per domain, then re-run the monitor. Response text is now stored for all runs below.
              </p>
            ) : null}
          </>
        ) : (
          <>
            <p className="competition-summary">
              Competition mentioned: <strong>{((prompt.mentioned_competitors ?? []).length > 0 ? prompt.mentioned_competitors : Array.from(new Set(mentions.filter((m) => m.is_own_domain !== 1).map((m) => m.mentioned))))?.join(', ') ?? '—'}</strong>
            </p>
            {[...models, 'other'].map((model) => {
              const list = mentionOtherByModel[model] || [];
              if (list.length === 0) return null;
              const distinct = Array.from(new Set(list.map((m) => m.mentioned)));
              return (
                <div key={model} className="citations-by-model">
                  <h3 className="citations-model-heading">{model}</h3>
                  <ul className="citations-list">
                    {distinct.map((brand) => (
                      <li key={`other-mention-${model}-${brand}`}>
                        <strong>{brand}</strong>
                        {' '}(run(s): {Array.from(new Set(list.filter((m) => m.mentioned === brand).map((m) => m.run_id))).join(', ')})
                      </li>
                    ))}
                  </ul>
                </div>
              );
            })}
          </>
        )}
      </section>

      {prompt.response_by_run && Object.keys(prompt.response_by_run).length > 0 ? (
        <section className="section detail-section">
          <h2>Stored LLM response (full content)</h2>
          <p className="section-desc">Response text stored from each run for re-processing and debugging.</p>
          {prompt.runs.filter((r) => prompt.response_by_run?.[r.id]?.response_text).map((r) => {
            const data = prompt.response_by_run?.[r.id];
            if (!data?.response_text) return null;
            return (
              <details key={r.id} className="response-details">
                <summary>{r.model} (run {r.id}) — {data.response_text.length > 80 ? `${data.response_text.slice(0, 80)}…` : data.response_text}</summary>
                <pre className="response-text-pre">{data.response_text}</pre>
              </details>
            );
          })}
        </section>
      ) : null}

      <section className="section detail-section">
        <h2>Our domain cited</h2>
        {totalOwn === 0 ? (
          <p>No citations of your tracked domain yet for this prompt.</p>
        ) : (
          [...models, 'other'].map((model) => {
            const list = ownByModel[model] || [];
            if (list.length === 0) return null;
            return (
              <div key={model} className="citations-by-model">
                <h3 className="citations-model-heading">{model}</h3>
                <ul className="citations-list">
                  {list.map((c, i) => (
                    <li key={`own-${model}-${i}`}>
                      <a
                        href={citationHref(c.cited_domain, c.raw_snippet)}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="citation-link"
                      >
                        <strong>{c.cited_domain}</strong>
                      </a>{' '}
                      (run {c.run_id}) — {c.raw_snippet ? `${c.raw_snippet.slice(0, 120)}…` : '—'}
                    </li>
                  ))}
                </ul>
              </div>
            );
          })
        )}
      </section>

      <section className="section detail-section">
        <h2>Other websites cited</h2>
        {totalOther === 0 ? (
          <p>No other website citations recorded yet for this prompt.</p>
        ) : (
          [...models, 'other'].map((model) => {
            const list = otherByModel[model] || [];
            if (list.length === 0) return null;
            return (
              <div key={model} className="citations-by-model">
                <h3 className="citations-model-heading">{model}</h3>
                <ul className="citations-list">
                  {list.map((c, i) => (
                    <li key={`other-${model}-${i}`}>
                      <a
                        href={citationHref(c.cited_domain, c.raw_snippet)}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="citation-link"
                      >
                        <strong>{c.cited_domain}</strong>
                      </a>{' '}
                      (run {c.run_id}) — {c.raw_snippet ? `${c.raw_snippet.slice(0, 120)}…` : '—'}
                    </li>
                  ))}
                </ul>
              </div>
            );
          })
        )}
      </section>
    </div>
  );
}
