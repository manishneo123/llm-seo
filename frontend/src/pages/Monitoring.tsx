import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  getMonitoringSettings,
  updateMonitoringSettings,
  runMonitoringNow,
  getMonitoringExecutions,
  getDomains,
  type MonitoringSettings as SettingsType,
  type MonitoringExecution,
} from '../api/client';
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from '../components/Card';

const AVAILABLE_MODELS = ['openai', 'anthropic', 'perplexity', 'gemini'];
const PAGE_SIZE = 15;

function StatusBadge({ status }: { status: string }) {
  const variant = status === 'finished' ? 'success' : status === 'failed' ? 'error' : status === 'running' ? 'running' : 'default';
  return <span className={`monitoring-status-badge monitoring-status-badge--${variant}`}>{status}</span>;
}

export function Monitoring() {
  const navigate = useNavigate();
  const [, setSettings] = useState<SettingsType | null>(null);
  const [domains, setDomains] = useState<{ id: number; domain: string }[]>([]);
  const [executions, setExecutions] = useState<MonitoringExecution[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [running, setRunning] = useState(false);

  const [formEnabled, setFormEnabled] = useState(true);
  const [formFrequency, setFormFrequency] = useState<number | ''>('');
  const [formModels, setFormModels] = useState<string[]>([]);
  const [formDomainIds, setFormDomainIds] = useState<number[]>([]);
  const [formPromptLimit, setFormPromptLimit] = useState<number | ''>('');
  const [formDelaySeconds, setFormDelaySeconds] = useState<number | ''>('');

  const loadSettings = () => {
    getMonitoringSettings()
      .then((s) => {
        setSettings(s);
        setFormEnabled(s.enabled);
        setFormFrequency(s.frequency_minutes ?? '');
        setFormModels(s.models ?? []);
        setFormDomainIds(s.domain_ids ?? []);
        setFormPromptLimit(s.prompt_limit ?? '');
        setFormDelaySeconds(s.delay_seconds ?? '');
      })
      .catch((e) => setError(e instanceof Error ? e.message : 'Failed to load'));
  };

  const loadExecutions = () => {
    const offset = (page - 1) * PAGE_SIZE;
    getMonitoringExecutions(PAGE_SIZE, offset)
      .then((r) => {
        setExecutions(r.executions);
        setTotal(r.total);
      })
      .catch((e) => setError(e instanceof Error ? e.message : 'Failed to load'));
  };

  const loadDomains = () => {
    getDomains()
      .then((r) => setDomains(r.domains.map((d) => ({ id: d.id, domain: d.domain }))))
      .catch(() => setDomains([]));
  };

  useEffect(() => { loadSettings(); loadDomains(); }, []);
  useEffect(() => { loadExecutions(); }, [page]);

  const handleSave = () => {
    setSaving(true);
    setError(null);
    updateMonitoringSettings({
      enabled: formEnabled,
      frequency_minutes: formFrequency === '' ? null : Number(formFrequency),
      models: formModels.length ? formModels : null,
      domain_ids: formDomainIds.length ? formDomainIds : null,
      prompt_limit: formPromptLimit === '' ? null : Number(formPromptLimit),
      delay_seconds: formDelaySeconds === '' ? null : Number(formDelaySeconds),
    })
      .then((s) => {
        setSettings(s);
        setSaving(false);
      })
      .catch((e) => {
        setError(e instanceof Error ? e.message : 'Save failed');
        setSaving(false);
      });
  };

  const handleRunNow = () => {
    setRunning(true);
    setError(null);
    runMonitoringNow({
      models: formModels.length ? formModels : undefined,
      domain_ids: formDomainIds.length ? formDomainIds : undefined,
      prompt_limit: formPromptLimit === '' ? undefined : Number(formPromptLimit),
      delay_seconds: formDelaySeconds === '' ? undefined : Number(formDelaySeconds),
    })
      .then(() => {
        setRunning(false);
        setPage(1);
        loadExecutions();
      })
      .catch((e) => {
        setError(e instanceof Error ? e.message : 'Run failed');
        setRunning(false);
      });
  };

  const toggleModel = (m: string) => {
    setFormModels((prev) => (prev.includes(m) ? prev.filter((x) => x !== m) : [...prev, m]));
  };

  const toggleDomain = (id: number) => {
    setFormDomainIds((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));
  };

  if (error) {
    return (
      <div className="page dashboard">
        <header className="page-header">
          <h1 className="page-title">Monitoring</h1>
          <p className="error">{error}</p>
          <button type="button" className="btn-secondary" onClick={() => { setError(null); loadSettings(); loadExecutions(); }}>Retry</button>
        </header>
      </div>
    );
  }

  return (
    <div className="page dashboard monitoring-page">
      <header className="page-header">
        <h1 className="page-title">Monitoring</h1>
        <p className="page-description">Configure scheduled runs and trigger monitoring. View run history below.</p>
      </header>

      <Card className="monitoring-settings-card">
        <CardHeader>
          <CardTitle>Schedule & configuration</CardTitle>
          <CardDescription>Settings are used by the scheduler and when you run manually. Scheduler checks every minute.</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="monitoring-form-grid">
            <div className="monitoring-form-row monitoring-form-row--toggle">
              <label className="form-label">Scheduled monitoring</label>
              <label className="toggle-wrap">
                <input type="checkbox" checked={formEnabled} onChange={(e) => setFormEnabled(e.target.checked)} className="toggle-input" />
                <span className="toggle-slider" />
              </label>
            </div>
            <div className="monitoring-form-row">
              <label className="form-label">Frequency (minutes)</label>
              <input
                type="number"
                min={1}
                max={10080}
                value={formFrequency}
                onChange={(e) => setFormFrequency(e.target.value === '' ? '' : parseInt(e.target.value, 10) || '')}
                placeholder="e.g. 360"
                className="form-input monitoring-input-narrow"
              />
              <p className="form-hint">Leave empty to run only manually.</p>
            </div>
            <div className="monitoring-form-row">
              <label className="form-label">Models</label>
              <div className="monitoring-model-chips">
                {AVAILABLE_MODELS.map((m) => (
                  <button
                    key={m}
                    type="button"
                    className={`monitoring-chip ${formModels.includes(m) ? 'monitoring-chip--active' : ''}`}
                    onClick={() => toggleModel(m)}
                  >
                    {m}
                  </button>
                ))}
              </div>
              <p className="form-hint">Leave all unselected to use all models.</p>
            </div>
            <div className="monitoring-form-row">
              <label className="form-label">Domains</label>
              <div className="monitoring-domain-chips">
                {domains.length === 0 ? (
                  <span className="form-hint">No domains. Add domains first.</span>
                ) : (
                  domains.map((d) => (
                    <button
                      key={d.id}
                      type="button"
                      className={`monitoring-chip monitoring-chip--domain ${formDomainIds.includes(d.id) ? 'monitoring-chip--active' : ''}`}
                      onClick={() => toggleDomain(d.id)}
                    >
                      {d.domain}
                    </button>
                  ))
                )}
              </div>
            </div>
            <div className="monitoring-form-row monitoring-form-row--inline">
              <div>
                <label className="form-label">Prompt limit</label>
                <input
                  type="number"
                  min={1}
                  value={formPromptLimit}
                  onChange={(e) => setFormPromptLimit(e.target.value === '' ? '' : parseInt(e.target.value, 10) || '')}
                  placeholder="All"
                  className="form-input monitoring-input-narrow"
                />
              </div>
              <div>
                <label className="form-label">Delay between calls (sec)</label>
                <input
                  type="number"
                  min={0}
                  step={0.5}
                  value={formDelaySeconds}
                  onChange={(e) => setFormDelaySeconds(e.target.value === '' ? '' : parseFloat(e.target.value) ?? '')}
                  placeholder="0.5"
                  className="form-input monitoring-input-narrow"
                />
              </div>
            </div>
          </div>
          <div className="monitoring-actions">
            <button type="button" className="btn-primary" onClick={handleRunNow} disabled={running}>
              {running ? 'Running…' : 'Run monitoring now'}
            </button>
            <button type="button" className="btn-secondary" onClick={handleSave} disabled={saving}>
              {saving ? 'Saving…' : 'Save settings'}
            </button>
          </div>
        </CardContent>
      </Card>

      <Card className="monitoring-runs-card">
        <CardHeader>
          <CardTitle>Recent runs</CardTitle>
          <CardDescription>Execution history. Open a run to see prompt visibility and details.</CardDescription>
        </CardHeader>
        <CardContent className="monitoring-runs-content">
          {total > 0 && (
            <div className="monitoring-pagination">
              <button type="button" className="btn-secondary btn-sm" disabled={page <= 1} onClick={() => setPage((p) => Math.max(1, p - 1))}>
                Previous
              </button>
              <span className="monitoring-pagination-info">
                Page {page} of {Math.max(1, Math.ceil(total / PAGE_SIZE))} · {total} total
              </span>
              <button type="button" className="btn-secondary btn-sm" disabled={page >= Math.ceil(total / PAGE_SIZE)} onClick={() => setPage((p) => p + 1)}>
                Next
              </button>
            </div>
          )}
          {executions.length === 0 ? (
            <div className="monitoring-empty">
              <p>No monitoring runs yet.</p>
              <p className="form-hint">Save settings above and click &quot;Run monitoring now&quot;.</p>
            </div>
          ) : (
            <div className="monitoring-table-wrap">
              <table className="prompts-table monitoring-table">
                <thead>
                  <tr>
                    <th>ID</th>
                    <th>Started</th>
                    <th>Finished</th>
                    <th>Trigger</th>
                    <th>Status</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  {executions.map((ex) => (
                    <tr key={ex.id}>
                      <td><span className="monitoring-id">#{ex.id}</span></td>
                      <td>{ex.started_at}</td>
                      <td>{ex.finished_at ?? '—'}</td>
                      <td>{ex.trigger_type}</td>
                      <td><StatusBadge status={ex.status} /></td>
                      <td>
                        <button type="button" className="link-btn" onClick={() => navigate(`/monitoring/executions/${ex.id}`)}>
                          View →
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
