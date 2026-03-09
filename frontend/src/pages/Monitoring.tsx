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

const AVAILABLE_MODELS = ['openai', 'anthropic', 'perplexity', 'gemini'];
const PAGE_SIZE = 15;

export function Monitoring() {
  const navigate = useNavigate();
  const [settings, setSettings] = useState<SettingsType | null>(null);
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
      <div className="dashboard">
        <h1>Monitoring</h1>
        <p className="error">{error}</p>
        <button type="button" onClick={() => { setError(null); loadSettings(); loadExecutions(); }}>Retry</button>
      </div>
    );
  }

  return (
    <div className="dashboard">
      <header>
        <h1>Monitoring settings</h1>
        <p>Configure when and how monitoring runs. Saved settings are used by the scheduler and when you run manually.</p>
      </header>

      <section className="section detail-section">
        <h2>Schedule & filters</h2>
        <div className="profile-edit-form" style={{ maxWidth: '560px' }}>
          <label className="profile-edit-label" style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <input type="checkbox" checked={formEnabled} onChange={(e) => setFormEnabled(e.target.checked)} />
            Enable scheduled monitoring
          </label>
          <label className="profile-edit-label">Frequency (minutes)</label>
          <input
            type="number"
            min={1}
            max={10080}
            value={formFrequency}
            onChange={(e) => setFormFrequency(e.target.value === '' ? '' : parseInt(e.target.value, 10) || '')}
            placeholder="e.g. 360 for every 6 hours"
            className="table-filter"
            style={{ width: '140px', marginBottom: '0.75rem' }}
          />
          <p className="section-desc" style={{ marginTop: '-0.5rem', marginBottom: '0.75rem' }}>
            Leave empty to only run manually. Scheduler checks every minute.
          </p>

          <label className="profile-edit-label">LLMs to run (leave empty for all)</label>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.5rem', marginBottom: '0.75rem' }}>
            {AVAILABLE_MODELS.map((m) => (
              <label key={m} style={{ display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
                <input type="checkbox" checked={formModels.includes(m)} onChange={() => toggleModel(m)} />
                {m}
              </label>
            ))}
          </div>

          <label className="profile-edit-label">Filter by domains (leave empty for all prompts)</label>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.5rem', marginBottom: '0.75rem' }}>
            {domains.map((d) => (
              <label key={d.id} style={{ display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
                <input type="checkbox" checked={formDomainIds.includes(d.id)} onChange={() => toggleDomain(d.id)} />
                {d.domain}
              </label>
            ))}
            {domains.length === 0 && <span className="section-desc">No domains. Add domains first.</span>}
          </div>

          <label className="profile-edit-label">Prompt limit (max prompts per run, empty = use default)</label>
          <input
            type="number"
            min={1}
            value={formPromptLimit}
            onChange={(e) => setFormPromptLimit(e.target.value === '' ? '' : parseInt(e.target.value, 10) || '')}
            className="table-filter"
            style={{ width: '100px', marginBottom: '0.75rem' }}
          />

          <label className="profile-edit-label">Wait between prompt runs (seconds)</label>
          <input
            type="number"
            min={0}
            step={0.5}
            value={formDelaySeconds}
            onChange={(e) => setFormDelaySeconds(e.target.value === '' ? '' : parseFloat(e.target.value) ?? '')}
            className="table-filter"
            style={{ width: '100px', marginBottom: '1rem' }}
            placeholder="e.g. 1 or 1.5"
          />
          <p className="section-desc" style={{ marginTop: '-0.5rem', marginBottom: '1rem' }}>
            Pause between each prompt×model call to avoid throughput/rate limit errors. Empty = 0.5s default.
          </p>

          <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
            <button type="button" onClick={handleSave} disabled={saving}>
              {saving ? 'Saving…' : 'Save settings'}
            </button>
            <button type="button" onClick={handleRunNow} disabled={running}>
              {running ? 'Running…' : 'Run monitoring now'}
            </button>
          </div>
        </div>
      </section>

      <section className="section">
        <h2>Monitoring runs</h2>
        {total > 0 && (
          <div className="pagination-bar">
            <button type="button" disabled={page <= 1} onClick={() => setPage((p) => Math.max(1, p - 1))}>
              ← Previous
            </button>
            <span className="pagination-info">
              Page {page} of {Math.max(1, Math.ceil(total / PAGE_SIZE))} ({total} total)
            </span>
            <button type="button" disabled={page >= Math.ceil(total / PAGE_SIZE)} onClick={() => setPage((p) => p + 1)}>
              Next →
            </button>
          </div>
        )}
        {executions.length === 0 ? (
          <p className="table-placeholder">No monitoring runs yet. Save settings and click &quot;Run monitoring now&quot;.</p>
        ) : (
          <table className="prompts-table">
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
                  <td>{ex.id}</td>
                  <td>{ex.started_at}</td>
                  <td>{ex.finished_at ?? '—'}</td>
                  <td>{ex.trigger_type}</td>
                  <td>{ex.status}</td>
                  <td>
                    <button type="button" className="link-btn" onClick={() => navigate(`/monitoring/executions/${ex.id}`)}>
                      Details
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </div>
  );
}
