import { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { getMonitoringExecution, type MonitoringExecutionDetail } from '../api/client';
const API_BASE = import.meta.env.VITE_API_URL || '';
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from '../components/Card';
import { CheckCircle2, Sparkles, AlertTriangle, Circle } from 'lucide-react';

function StatusBadge({ status }: { status: string }) {
  const variant = status === 'finished' ? 'success' : status === 'failed' ? 'error' : status === 'running' ? 'running' : 'default';
  return <span className={`monitoring-status-badge monitoring-status-badge--${variant}`}>{status}</span>;
}

type VisibilityValue = {
  had_own_citation: boolean;
  brand_mentioned: boolean;
  competitor_only: boolean;
};

function VisibilityDot({ value }: { value?: VisibilityValue }) {
  if (!value) {
    return (
      <Circle className="visibility-icon visibility-icon--none" aria-label="Not present" />
    );
  }
  const items: { key: string; label: string }[] = [];
  if (value.had_own_citation) {
    items.push({ key: 'cited', label: 'Cited' });
  }
  if (value.brand_mentioned) {
    items.push({ key: 'brand', label: 'Brand mentioned' });
  }
  if (value.competitor_only) {
    items.push({ key: 'competitor', label: 'Competitor only' });
  }
  if (items.length === 0) {
    items.push({ key: 'none', label: 'Not present' });
  }
  const combinedLabel = items.map((i) => i.label).join(', ');
  return (
    <span className="visibility-dot-multi" aria-label={combinedLabel} title={combinedLabel}>
      {items.map((it) => {
        if (it.key === 'cited') return <CheckCircle2 key={it.key} className="visibility-icon visibility-icon--cited" />;
        if (it.key === 'brand') return <Sparkles key={it.key} className="visibility-icon visibility-icon--brand" />;
        if (it.key === 'competitor') return <AlertTriangle key={it.key} className="visibility-icon visibility-icon--competitor" />;
        return <Circle key={it.key} className="visibility-icon visibility-icon--none" />;
      })}
    </span>
  );
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
      <div className="page dashboard execution-detail-page">
        <header className="page-header">
          <button type="button" className="execution-detail-back" onClick={() => navigate('/monitoring')}>← Monitoring</button>
          <h1 className="page-title">Execution</h1>
          <p className="error">{error}</p>
          <button type="button" className="btn-secondary" onClick={() => { setError(null); if (id) getMonitoringExecution(Number(id)).then(setExecution).catch((e) => setError(e instanceof Error ? e.message : 'Failed to load')); }}>Retry</button>
        </header>
      </div>
    );
  }

  if (!execution) {
    return (
      <div className="page dashboard execution-detail-page">
        <header className="page-header">
          <button type="button" className="execution-detail-back" onClick={() => navigate('/monitoring')}>← Monitoring</button>
          <p className="page-description">Loading execution…</p>
        </header>
      </div>
    );
  }

  return (
    <div className="page dashboard execution-detail-page">
      <header className="page-header">
        <button type="button" className="execution-detail-back" onClick={() => navigate('/monitoring')}>← Monitoring</button>
        <h1 className="page-title">Execution #{execution.id}</h1>
        <p className="page-description">Trigger: {execution.trigger_type} · Started {execution.started_at}{execution.finished_at ? ` · Finished ${execution.finished_at}` : ''}</p>
        <div className="execution-detail-meta">
          <StatusBadge status={execution.status} />
          {execution.status === 'finished' && (
            <button
              type="button"
              className="btn-secondary btn-sm"
              onClick={() => window.open(`${API_BASE}/api/reports/executions/${execution.id}.pdf`, '_blank')}
            >
              Download PDF report
            </button>
          )}
        </div>
      </header>

      <Card className="execution-detail-card">
        <CardHeader>
          <CardTitle>Runs by model</CardTitle>
          <CardDescription>Each run corresponds to one model. Prompts and visibility are listed below.</CardDescription>
        </CardHeader>
        <CardContent>
          {execution.runs.length === 0 ? (
            <div className="execution-detail-empty">No runs for this execution (e.g. created before grouping).</div>
          ) : (
            <div className="monitoring-table-wrap">
              <table className="prompts-table monitoring-table">
                <thead>
                  <tr>
                    <th>Run</th>
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
                      <td><span className="monitoring-id">#{r.id}</span></td>
                      <td><ModelLabel model={r.model} /></td>
                      <td>{r.started_at}</td>
                      <td>{r.finished_at ?? '—'}</td>
                      <td>{r.prompt_count}</td>
                      <td><StatusBadge status={r.status} /></td>
                      <td>
                        <button type="button" className="link-btn" onClick={() => navigate('/prompts')}>View prompts →</button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>

      {execution.prompt_visibility && execution.prompt_visibility.length > 0 && (
        <Card className="execution-detail-card">
          <CardHeader>
            <CardTitle>Prompt visibility</CardTitle>
            <CardDescription>Per-prompt citation and brand mention status across all models for this execution.</CardDescription>
          </CardHeader>
          <CardContent className="execution-visibility-content">
            <div className="visibility-legend">
              <span className="visibility-legend-item">
                <CheckCircle2 className="visibility-icon visibility-icon--cited" />
                Cited
              </span>
              <span className="visibility-legend-item">
                <Sparkles className="visibility-icon visibility-icon--brand" />
                Brand mentioned
              </span>
              <span className="visibility-legend-item">
                <AlertTriangle className="visibility-icon visibility-icon--competitor" />
                Competitor only
              </span>
              <span className="visibility-legend-item">
                <Circle className="visibility-icon visibility-icon--none" />
                Not present
              </span>
            </div>
            <div className="prompts-table-wrap execution-visibility-wrap">
              <table className="prompts-table execution-visibility-table">
                <thead>
                  <tr>
                    <th className="col-prompt">Prompt</th>
                    <th className="col-niche">Niche</th>
                    {execution.runs.map((r) => (
                      <th key={r.id} className="execution-visibility-model-header">
                        <ModelLabel model={r.model} />
                      </th>
                    ))}
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
                        {execution.runs.map((r) => {
                          const v = byModel[r.model] as VisibilityValue | undefined;
                          return (
                            <td key={r.id} className="execution-visibility-cell">
                              <VisibilityDot value={v} />
                            </td>
                          );
                        })}
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      )}

      {execution.settings_snapshot && Object.keys(execution.settings_snapshot).length > 0 && (
        <Card className="execution-detail-card">
          <CardHeader>
            <CardTitle>Settings used</CardTitle>
            <CardDescription>Configuration snapshot for this run.</CardDescription>
          </CardHeader>
          <CardContent>
            <pre className="execution-settings-pre">
              {JSON.stringify(execution.settings_snapshot, null, 2)}
            </pre>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
