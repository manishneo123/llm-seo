import { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Eye, ExternalLink } from 'lucide-react';
import { getPrompt, type PromptDetail, type MentionItem } from '../api/client';
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from '../components/Card';

function citationHref(domain: string, snippet: string | null | undefined): string {
  if (snippet) {
    const match = snippet.match(/https?:\/\/[^\s\]\)"']+/i);
    if (match) return match[0];
  }
  const d = (domain || '').trim();
  if (!d) return '#';
  return d.startsWith('http://') || d.startsWith('https://') ? d : `https://${d}`;
}

function formatRunDateTime(startedAt: string): { date: string; time: string } {
  try {
    const d = new Date(startedAt);
    const date = d.toLocaleDateString(undefined, { year: 'numeric', month: '2-digit', day: '2-digit' });
    const time = d.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit', hour12: false });
    return { date, time };
  } catch {
    return { date: startedAt, time: '' };
  }
}

function normalizeModelKey(model: string): string {
  return model.toLowerCase().replace(/[^a-z0-9]+/g, '-');
}

function ModelLabel({ model }: { model: string }) {
  const key = normalizeModelKey(model);
  return (
    <span className={`visibility-model-label visibility-model--${key}`}>
      <span className="visibility-model-label-dot" />
      {model}
    </span>
  );
}

function YesNoIcon({ value }: { value: boolean }) {
  return (
    <span className={`visibility-yn-icon visibility-yn-icon--${value ? 'yes' : 'no'}`} aria-label={value ? 'Yes' : 'No'} title={value ? 'Yes' : 'No'}>
      {value ? (
        <span className="visibility-yn-check" aria-hidden>✓</span>
      ) : (
        <span className="visibility-yn-cross" aria-hidden>✕</span>
      )}
    </span>
  );
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

  if (error) return <div className="page dashboard"><header className="page-header"><h1 className="page-title">Prompt</h1><p className="error">{error}</p><button type="button" className="link-btn" onClick={() => navigate('/prompts')}>← Back to prompts</button></header></div>;
  if (!prompt) return <div className="page dashboard"><p className="page-description">Loading…</p></div>;

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
    <div className="page dashboard">
      <header className="page-header">
        <button type="button" className="link-btn" onClick={() => navigate('/prompts')}>← Prompts</button>
        <h1 className="page-title">Prompt #{prompt.id}</h1>
        <p className="page-description">{prompt.niche ? `Niche: ${prompt.niche} · ` : ''}Created: {prompt.created_at}</p>
      </header>

      <section className="section detail-section">
        <h2 className="section-title">Text</h2>
        <p className="prompt-text">{prompt.text}</p>
      </section>

      <hr className="section-divider" />

      <Card className="visibility-across-runs-card">
        <CardHeader>
          <CardTitle className="visibility-across-runs-title">
            <Eye size={20} className="visibility-across-runs-icon" aria-hidden />
            Visibility across runs
          </CardTitle>
          <CardDescription>How this prompt performed across monitoring executions and models.</CardDescription>
        </CardHeader>
        <CardContent>
          {prompt.runs.length === 0 ? (
            <p className="visibility-across-runs-empty">No finished runs yet.</p>
          ) : (
            <div className="visibility-across-runs-table-wrap">
              <table className="prompts-table visibility-across-runs-table">
                <thead>
                  <tr>
                    <th>Execution</th>
                    <th>Model</th>
                    <th>Cited</th>
                    <th>Brand mentioned</th>
                    <th>Competitor only</th>
                    <th>Others cited</th>
                    <th>Response</th>
                  </tr>
                </thead>
                <tbody>
                  {(() => {
                    const runs = [...prompt.runs];
                    const byExec = new Map<number, typeof runs>();
                    for (const r of runs) {
                      const eid = r.execution_id ?? r.id;
                      if (!byExec.has(eid)) byExec.set(eid, []);
                      byExec.get(eid)!.push(r);
                    }
                    const groups = Array.from(byExec.entries()).sort((a, b) => b[0] - a[0]);
                    return groups.flatMap(([execId, execRuns]) =>
                      execRuns.map((r, i) => {
                        const { date, time } = formatRunDateTime(r.started_at);
                        const isFirstInGroup = i === 0;
                        const hasResponse = !!(prompt.response_by_run?.[r.id]?.response_text);
                        return (
                          <tr key={r.id} data-cited={r.cited} data-competitor-only={r.competitor_only === 1}>
                            <td className="visibility-across-runs-exec-cell">
                              {isFirstInGroup ? (
                                <>
                                  <span className="visibility-across-runs-exec-id">exec-{String(execId).padStart(3, '0')}</span>
                                  <span className="visibility-across-runs-exec-date">{date}</span>
                                  {time ? <span className="visibility-across-runs-exec-time">{time}</span> : null}
                                </>
                              ) : (
                                <>
                                  <span className="visibility-across-runs-exec-date">{date}</span>
                                  {time ? <span className="visibility-across-runs-exec-time">{time}</span> : null}
                                </>
                              )}
                            </td>
                            <td><ModelLabel model={r.model} /></td>
                            <td className="visibility-across-runs-yn-cell"><YesNoIcon value={r.cited} /></td>
                            <td className="visibility-across-runs-yn-cell"><YesNoIcon value={r.brand_mentioned === 1} /></td>
                            <td className="visibility-across-runs-yn-cell"><YesNoIcon value={r.competitor_only === 1} /></td>
                            <td className="visibility-across-runs-others-cell">
                              {(r.others_cited ?? []).length > 0 ? (
                                <span className="visibility-across-runs-tags">
                                  {(r.others_cited ?? []).map((domain) => (
                                    <span key={domain} className="visibility-across-runs-tag">{domain}</span>
                                  ))}
                                </span>
                              ) : (
                                '—'
                              )}
                            </td>
                            <td>
                              {hasResponse ? (
                                <button
                                  type="button"
                                  className="visibility-across-runs-view-btn"
                                  onClick={() => setResponseModalRunId(r.id)}
                                >
                                  <ExternalLink size={14} aria-hidden />
                                  View
                                </button>
                              ) : (
                                '—'
                              )}
                            </td>
                          </tr>
                        );
                      })
                    );
                  })()}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>

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
        <h2 className="section-title">Citation counts by model</h2>
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
        <h2 className="section-title">Brand mention counts by model</h2>
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
        <h2 className="section-title">Our domain mentioned (in text)</h2>
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
        <h2 className="section-title">Competition mentioned (in text)</h2>
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
          <h2 className="section-title">Stored LLM response (full content)</h2>
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
        <h2 className="section-title">Our domain cited</h2>
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
        <h2 className="section-title">Other websites cited</h2>
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
