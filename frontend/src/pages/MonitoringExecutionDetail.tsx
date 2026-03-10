import { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { getMonitoringExecution, type MonitoringExecutionDetail } from '../api/client';

export function MonitoringExecutionDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [execution, setExecution] = useState<MonitoringExecutionDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!id) return;
    getMonitoringExecution(Number(id))
      .then(setExecution)
      .catch((e) => setError(e instanceof Error ? e.message : 'Failed to load'));
  }, [id]);

  if (error) {
    return (
      <div className="dashboard">
        <h1>Execution</h1>
        <p className="error">{error}</p>
        <button type="button" onClick={() => navigate('/monitoring')}>← Back to Monitoring</button>
      </div>
    );
  }

  if (!execution) {
    return (
      <div className="dashboard">
        <p>Loading…</p>
      </div>
    );
  }

  return (
    <div className="dashboard">
      <header>
        <button type="button" className="link-btn" onClick={() => navigate('/monitoring')}>← Back to Monitoring</button>
        <h1>Execution #{execution.id}</h1>
        <p>Trigger: {execution.trigger_type} · Status: {execution.status}</p>
        <p className="section-desc">Started: {execution.started_at} · Finished: {execution.finished_at ?? '—'}</p>
      </header>

      <section className="section detail-section">
        <h2>Runs (by model)</h2>
        {execution.runs.length === 0 ? (
          <p className="table-placeholder">No runs for this execution (e.g. execution created before grouping).</p>
        ) : (
          <table className="prompts-table">
            <thead>
              <tr>
                <th>Run ID</th>
                <th>Model</th>
                <th>Started</th>
                <th>Finished</th>
                <th>Prompts</th>
                <th>Status</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {execution.runs.map((r) => (
                <tr key={r.id}>
                  <td>{r.id}</td>
                  <td>{r.model}</td>
                  <td>{r.started_at}</td>
                  <td>{r.finished_at ?? '—'}</td>
                  <td>{r.prompt_count}</td>
                  <td>{r.status}</td>
                  <td>
                    <button type="button" className="link-btn" onClick={() => navigate(`/prompts`)}>
                      View prompts
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      {execution.prompt_visibility && execution.prompt_visibility.length > 0 && (
        <section className="section detail-section">
          <h2>Prompt visibility for this execution</h2>
          <p className="section-desc">For each prompt, visibility (cited / brand mentioned / competitor-only) per model in this run.</p>
          <div className="prompts-table-wrap">
            <table className="prompts-table execution-visibility-table">
              <colgroup>
                <col className="col-prompt" style={{ width: '280px' }} />
                <col className="col-niche" style={{ width: '140px' }} />
              </colgroup>
              <thead>
                <tr>
                  <th className="col-prompt">Prompt</th>
                  <th className="col-niche">Niche</th>
                  {execution.runs.map((r) => (
                    <th key={r.id} colSpan={3} style={{ textAlign: 'center' }}>
                      {r.model}
                    </th>
                  ))}
                </tr>
                <tr>
                  <th className="col-prompt"></th>
                  <th className="col-niche"></th>
                  {execution.runs.flatMap((r) => [
                    <th key={`${r.id}-cite`} style={{ fontWeight: 500, fontSize: '0.8rem' }}>Cited</th>,
                    <th key={`${r.id}-brand`} style={{ fontWeight: 500, fontSize: '0.8rem' }}>Brand</th>,
                    <th key={`${r.id}-comp`} style={{ fontWeight: 500, fontSize: '0.8rem' }}>Comp-only</th>,
                  ])}
                </tr>
              </thead>
              <tbody>
                {execution.prompt_visibility.map((pv) => {
                  const byModel = Object.fromEntries(pv.visibility_by_run.map((v) => [v.model, v]));
                  return (
                    <tr key={pv.prompt_id}>
                      <td className="col-prompt execution-visibility-prompt-cell">
                        <button
                          type="button"
                          className="link-btn"
                          onClick={() => navigate(`/prompts/${pv.prompt_id}`)}
                          title={pv.text}
                        >
                          {pv.text.slice(0, 56)}{pv.text.length > 56 ? '…' : ''}
                        </button>
                      </td>
                      <td className="col-niche execution-visibility-niche-cell">{pv.niche ? pv.niche.slice(0, 24) + (pv.niche.length > 24 ? '…' : '') : '—'}</td>
                      {execution.runs.flatMap((r) => {
                        const v = byModel[r.model];
                        return [
                          <td key={`${r.id}-cite`} style={{ textAlign: 'center' }}>{v?.had_own_citation ? '✓' : '—'}</td>,
                          <td key={`${r.id}-brand`} style={{ textAlign: 'center' }}>{v?.brand_mentioned ? '✓' : '—'}</td>,
                          <td key={`${r.id}-comp`} style={{ textAlign: 'center' }}>{v?.competitor_only ? '✓' : '—'}</td>,
                        ];
                      })}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {execution.settings_snapshot && Object.keys(execution.settings_snapshot).length > 0 && (
        <section className="section detail-section">
          <h2>Settings used</h2>
          <pre className="response-text-pre" style={{ maxHeight: '12rem' }}>
            {JSON.stringify(execution.settings_snapshot, null, 2)}
          </pre>
        </section>
      )}
    </div>
  );
}
