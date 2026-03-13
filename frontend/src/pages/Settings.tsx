import { useEffect, useState } from 'react';
import {
  getLlmProviderSettings,
  updateLlmProviderSettings,
  validateLlmProviderSettings,
  type LlmProviderSettings,
  type LlmProviderValidationResult,
} from '../api/client';

const PROVIDERS = [
  { key: 'openai' as const, label: 'OpenAI', placeholder: 'sk-...', modelPlaceholder: 'e.g. gpt-4o, gpt-4o-mini' },
  { key: 'perplexity' as const, label: 'Perplexity', placeholder: 'pplx-...', modelPlaceholder: 'e.g. sonar, sonar-pro' },
  { key: 'anthropic' as const, label: 'Anthropic', placeholder: 'sk-ant-...', modelPlaceholder: 'e.g. claude-sonnet-4-20250514' },
  { key: 'gemini' as const, label: 'Google Gemini', placeholder: 'AIza...', modelPlaceholder: 'e.g. gemini-2.0-flash' },
] as const;

export function Settings() {
  const [settings, setSettings] = useState<LlmProviderSettings | null>(null);
  const [form, setForm] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [validating, setValidating] = useState(false);
  const [validationResult, setValidationResult] = useState<LlmProviderValidationResult | null>(null);

  useEffect(() => {
    getLlmProviderSettings()
      .then((s) => {
        setSettings(s);
        setForm({
          openai: '',
          perplexity: '',
          anthropic: '',
          gemini: '',
          openai_model: s.openai_model ?? '',
          perplexity_model: s.perplexity_model ?? '',
          anthropic_model: s.anthropic_model ?? '',
          gemini_model: s.gemini_model ?? '',
        });
      })
      .catch((e) => setError(e instanceof Error ? e.message : 'Failed to load'));
  }, []);

  const handleSave = () => {
    setSaving(true);
    setError(null);
    setSaved(false);
    const payload: Record<string, string> = {};
    PROVIDERS.forEach(({ key }) => {
      const v = form[key];
      if (v === undefined) return;
      if (v !== '') payload[key] = v;
      else if (settings?.[key]) payload[key] = '';
    });
    ['openai_model', 'perplexity_model', 'anthropic_model', 'gemini_model'].forEach((k) => {
      const v = form[k];
      if (v !== undefined) payload[k] = v;
    });
    updateLlmProviderSettings(payload)
      .then((s) => {
        setSettings(s);
        setForm({
          openai: '', perplexity: '', anthropic: '', gemini: '',
          openai_model: s.openai_model ?? '', perplexity_model: s.perplexity_model ?? '',
          anthropic_model: s.anthropic_model ?? '', gemini_model: s.gemini_model ?? '',
        });
        setSaving(false);
        setSaved(true);
        setTimeout(() => setSaved(false), 3000);
      })
      .catch((e) => {
        setError(e instanceof Error ? e.message : 'Save failed');
        setSaving(false);
      });
  };

  const updateField = (key: string, value: string) => {
    setForm((prev) => ({ ...prev, [key]: value }));
    setValidationResult(null);
  };

  const handleValidate = () => {
    setValidating(true);
    setError(null);
    setValidationResult(null);
    validateLlmProviderSettings(form)
      .then((result) => {
        setValidationResult(result);
        setValidating(false);
      })
      .catch((e) => {
        setError(e instanceof Error ? e.message : 'Validation failed');
        setValidating(false);
      });
  };

  if (error) {
    return (
      <div className="page dashboard">
        <header className="page-header">
          <h1 className="page-title">Settings</h1>
          <p className="error">{error}</p>
          <button type="button" className="btn-secondary" onClick={() => { setError(null); getLlmProviderSettings().then(setSettings).catch(() => {}); }}>
            Retry
          </button>
        </header>
      </div>
    );
  }

  return (
    <div className="page dashboard">
      <header className="page-header">
        <h1 className="page-title">Settings</h1>
        <p className="page-description">Store API keys for OpenAI, Perplexity, Anthropic, and Google Gemini. These are used for monitoring, prompt generation, and content features. Keys are stored per account and shown masked.</p>
      </header>

      <section className="section detail-section">
        <h2 className="section-title">LLM provider API keys and models</h2>
        <div style={{ maxWidth: '560px' }}>
          {PROVIDERS.map(({ key, label, placeholder, modelPlaceholder }) => (
            <div key={key} className="form-group" style={{ marginBottom: '1.5rem' }}>
              <label className="form-label" style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                {label}
                {settings?.[key] && (
                  <button
                    type="button"
                    className="link-btn btn-ghost btn-sm"
                    onClick={() => updateField(key, '')}
                  >
                    Clear key
                  </button>
                )}
              </label>
              <input
                type="password"
                autoComplete="off"
                value={form[key] ?? ''}
                onChange={(e) => updateField(key, e.target.value)}
                placeholder={settings?.[key] ? 'Leave blank to keep current' : placeholder}
                className="form-input"
                style={{ maxWidth: '400px' }}
              />
              {settings?.[key] && (
                <p className="form-hint" style={{ marginTop: 0, marginBottom: '0.35rem' }}>
                  Current key: {settings[key]}
                </p>
              )}
              <label className="form-label" style={{ marginTop: '0.5rem' }}>{label} model</label>
              <input
                type="text"
                autoComplete="off"
                value={form[`${key}_model`] ?? ''}
                onChange={(e) => updateField(`${key}_model`, e.target.value)}
                placeholder={modelPlaceholder}
                className="form-input"
                style={{ maxWidth: '400px' }}
              />
              {settings?.[`${key}_model`] && (
                <p className="form-hint" style={{ marginTop: '0.25rem', marginBottom: 0 }}>
                  Current: {settings[`${key}_model`]}
                </p>
              )}
            </div>
          ))}
          <div className="form-actions">
            <button type="button" className="btn-primary" onClick={handleSave} disabled={saving}>
              {saving ? 'Saving…' : 'Save'}
            </button>
            <button type="button" className="btn-secondary" onClick={handleValidate} disabled={validating}>
              {validating ? 'Testing…' : 'Test connections'}
            </button>
            {saved && <span style={{ color: 'var(--color-success)', fontSize: 'var(--text-sm)' }}>Saved.</span>}
          </div>
          {validationResult && Object.keys(validationResult).length > 0 && (
            <div className="card-ui" style={{ marginTop: '1rem' }}>
              <div className="card-ui-content" style={{ padding: 'var(--space-md)' }}>
              <div className="subsection-title" style={{ marginBottom: 'var(--space-sm)' }}>Connection test results</div>
              <ul style={{ margin: 0, paddingLeft: '1.25rem' }}>
                {Object.entries(validationResult).map(([provider, r]) => (
                  <li key={provider} style={{ marginBottom: '0.25rem' }}>
                    <span style={{ textTransform: 'capitalize' }}>{provider}</span>:{' '}
                    {r.ok ? (
                      <span style={{ color: 'var(--color-success)' }}>OK</span>
                    ) : (
                      <span style={{ color: 'var(--color-error)' }}>{r.error ?? 'Failed'}</span>
                    )}
                  </li>
                ))}
              </ul>
              </div>
            </div>
          )}
        </div>
      </section>
    </div>
  );
}
