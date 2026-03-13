import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  getPromptGenerationSettings,
  updatePromptGenerationSettings,
  runPromptGenerationNow,
  getPromptGenerationRuns,
  type PromptGenerationSettings,
  type PromptGenerationRun,
} from '../api/client';

const RUNS_PAGE_SIZE = 15;

export function PromptGeneration() {
  const navigate = useNavigate();
  const [settings, setSettings] = useState<PromptGenerationSettings | null>(null);
  const [runs, setRuns] = useState<PromptGenerationRun[]>([]);
  const [runsTotal, setRunsTotal] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [enabled, setEnabled] = useState(false);
  const [frequencyDays, setFrequencyDays] = useState<number | ''>(7);
  const [promptsPerDomain, setPromptsPerDomain] = useState<number | ''>('');
  const [saving, setSaving] = useState(false);
  const [running, setRunning] = useState(false);
  const [runsPage, setRunsPage] = useState(1);

  const loadSettings = () => {
    getPromptGenerationSettings()
      .then((s) => {
        setSettings(s);
        setEnabled(s.enabled);
        setFrequencyDays(s.frequency_days ?? 7);
        setPromptsPerDomain(s.prompts_per_domain ?? '');
      })
      .catch((e) => setError(e instanceof Error ? e.message : 'Failed to load'));
  };

  const loadRuns = () => {
    const offset = (runsPage - 1) * RUNS_PAGE_SIZE;
    getPromptGenerationRuns(RUNS_PAGE_SIZE, offset)
      .then((r) => {
        setRuns(r.runs);
        setRunsTotal(r.total);
      })
      .catch(() => setRuns([]));
  };

  useEffect(() => { loadSettings(); }, []);
  useEffect(() => { loadRuns(); }, [runsPage]);

  const handleSave = () => {
    setSaving(true);
    setError(null);
    updatePromptGenerationSettings({
      enabled,
      frequency_days: frequencyDays === '' ? 7 : Number(frequencyDays),
      prompts_per_domain: promptsPerDomain === '' ? null : Number(promptsPerDomain),
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
    runPromptGenerationNow()
      .then(() => {
        setRunning(false);
        loadSettings();
        setRunsPage(1);
        loadRuns();
      })
      .catch((e) => {
        setError(e instanceof Error ? e.message : 'Run failed');
        setRunning(false);
        loadRuns();
      });
  };

  if (error && !settings) {
    return (
      <div className="page dashboard">
        <header className="page-header">
          <h1 className="page-title">Prompt generation</h1>
          <p className="error">{error}</p>
          <button type="button" className="btn-secondary" onClick={() => { setError(null); loadSettings(); }}>Retry</button>
        </header>
      </div>
    );
  }

  return (
    <div className="page dashboard">
      <header className="page-header">
        <h1 className="page-title">Prompt generation</h1>
        <p className="page-description">Schedule automatic prompt generation from domain profiles and view run history.</p>
      </header>

      <section className="section detail-section">
        <h2 className="section-title">Schedule</h2>
        <p className="section-desc">Generate new prompts from domain profiles on a schedule. Runs only after domain discovery. Scheduler checks every minute.</p>
        <div className="profile-edit-form" style={{ maxWidth: '560px' }}>
          <label className="form-label" style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <input type="checkbox" checked={enabled} onChange={(e) => setEnabled(e.target.checked)} />
            Enable scheduled prompt generation
          </label>
          <label className="form-label">Frequency (days)</label>
          <input
            type="number"
            min={0.5}
            step={0.5}
            value={frequencyDays}
            onChange={(e) => setFrequencyDays(e.target.value === '' ? '' : parseFloat(e.target.value) || '')}
            placeholder="e.g. 7"
            className="form-input"
            style={{ width: '100px', marginBottom: '0.75rem' }}
          />
          <label className="form-label">Prompts per domain (empty = use config default)</label>
          <input
            type="number"
            min={1}
            value={promptsPerDomain}
            onChange={(e) => setPromptsPerDomain(e.target.value === '' ? '' : parseInt(e.target.value, 10) || '')}
            className="form-input"
            style={{ width: '100px', marginBottom: '0.75rem' }}
          />
          {settings?.last_run_at && (
            <p className="section-desc" style={{ marginBottom: '0.75rem' }}>
              Last run: {settings.last_run_at}
            </p>
          )}
          <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
            <button type="button" className="btn-primary" onClick={handleSave} disabled={saving}>
              {saving ? 'Saving…' : 'Save settings'}
            </button>
            <button type="button" className="btn-secondary" onClick={handleRunNow} disabled={running}>
              {running ? 'Running…' : 'Run prompt generation now'}
            </button>
          </div>
        </div>
      </section>

      <hr className="section-divider" />

      <section className="section">
        <h2 className="section-title">Prompt generation runs</h2>
        <p className="section-desc">History of scheduled and manual prompt generation runs.</p>
        {runsTotal > 0 && (
          <div className="pagination-bar">
            <button type="button" disabled={runsPage <= 1} onClick={() => setRunsPage((p) => Math.max(1, p - 1))}>
              ← Previous
            </button>
            <span className="pagination-info">
              Page {runsPage} of {Math.max(1, Math.ceil(runsTotal / RUNS_PAGE_SIZE))} ({runsTotal} total)
            </span>
            <button type="button" disabled={runsPage >= Math.ceil(runsTotal / RUNS_PAGE_SIZE)} onClick={() => setRunsPage((p) => p + 1)}>
              Next →
            </button>
          </div>
        )}
        {runs.length === 0 ? (
          <p className="table-placeholder">No runs yet. Save settings and click &quot;Run prompt generation now&quot;.</p>
        ) : (
          <table className="prompts-table">
            <thead>
              <tr>
                <th>ID</th>
                <th>Started</th>
                <th>Finished</th>
                <th>Trigger</th>
                <th>Status</th>
                <th>Inserted</th>
                <th>Details</th>
              </tr>
            </thead>
            <tbody>
              {runs.map((run) => (
                <tr key={run.id}>
                  <td>{run.id}</td>
                  <td>{run.started_at}</td>
                  <td>{run.finished_at ?? '—'}</td>
                  <td>{run.trigger_type}</td>
                  <td>{run.status}</td>
                  <td>{run.inserted_count ?? '—'}</td>
                  <td>
                    <button
                      type="button"
                      className="link-btn"
                      onClick={() => navigate(`/prompts?prompt_generation_run_id=${run.id}`)}
                    >
                      View prompts
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
