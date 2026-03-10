import React, { useEffect, useState } from 'react';
import {
  listContentSources,
  getContentSourceDomains,
  getDomains,
  createContentSource,
  updateContentSource,
  deleteContentSource,
  addDomainContentSource,
  removeDomainContentSource,
  validateCmsCredentials,
  type ContentSource,
  type Domain,
} from '../api/client';
import { SOURCE_TYPE_LABELS } from '../constants/cms';

const SOURCE_TYPES = ['hashnode', 'ghost', 'wordpress', 'webflow', 'linkedin', 'devto', 'notion'] as const;

type ConfigField = { key: string; label: string; inputType: 'text' | 'password' | 'url'; required?: boolean };
const CONFIG_FIELDS: Record<string, ConfigField[]> = {
  hashnode: [
    { key: 'api_key', label: 'API key', inputType: 'password', required: true },
    { key: 'publication_id', label: 'Publication ID', inputType: 'text', required: true },
  ],
  ghost: [
    { key: 'url', label: 'Ghost URL', inputType: 'url', required: true },
    { key: 'admin_api_key', label: 'Admin API key', inputType: 'password', required: true },
  ],
  wordpress: [
    { key: 'url', label: 'WordPress URL', inputType: 'url', required: true },
    { key: 'app_password', label: 'Application password', inputType: 'password', required: true },
  ],
  webflow: [
    { key: 'api_token', label: 'API token', inputType: 'password', required: true },
    { key: 'collection_id', label: 'Collection ID', inputType: 'text', required: true },
  ],
  linkedin: [
    { key: 'access_token', label: 'Access token', inputType: 'password', required: true },
    { key: 'author_urn', label: 'Author URN (urn:li:person:ID or urn:li:organization:ID)', inputType: 'text', required: true },
  ],
  devto: [
    { key: 'api_key', label: 'API key', inputType: 'password', required: true },
  ],
  notion: [
    { key: 'integration_token', label: 'Integration token', inputType: 'password', required: true },
    { key: 'parent_id', label: 'Parent page or database ID', inputType: 'text', required: true },
    { key: 'parent_type', label: 'Parent type (page_id or database_id)', inputType: 'text', required: false },
  ],
};

function emptyConfigForType(type: string): Record<string, string> {
  const fields = CONFIG_FIELDS[type] || [];
  return Object.fromEntries(fields.map((f) => [f.key, '']));
}

function validateSourceForm(
  name: string,
  type: string,
  config: Record<string, string>,
  isEdit: boolean
): Record<string, string> {
  const err: Record<string, string> = {};
  if (!name.trim()) err.name = 'Name is required';
  const fields = CONFIG_FIELDS[type] || [];
  fields.forEach((f) => {
    if (!f.required) return;
    const v = (config[f.key] ?? '').trim();
    if (!v && !isEdit) err[f.key] = `${f.label} is required`;
    if (!v && isEdit && f.inputType !== 'password') err[f.key] = `${f.label} is required`;
  });
  return err;
}

export function ContentSources() {
  const [sources, setSources] = useState<ContentSource[]>([]);
  const [domains, setDomains] = useState<Domain[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [addForm, setAddForm] = useState(false);
  const [formName, setFormName] = useState('');
  const [formType, setFormType] = useState<string>('hashnode');
  const [formConfig, setFormConfig] = useState<Record<string, string>>(emptyConfigForType('hashnode'));
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editForm, setEditForm] = useState<{ name: string; type: string; config: Record<string, string> }>({ name: '', type: 'hashnode', config: {} });
  const [editErrors, setEditErrors] = useState<Record<string, string>>({});
  const [addErrors, setAddErrors] = useState<Record<string, string>>({});
  const [validateStatus, setValidateStatus] = useState<null | 'testing' | { ok: boolean; message: string }>(null);
  const [domainsBySourceId, setDomainsBySourceId] = useState<Record<number, { id: number; domain: string }[]>>({});
  const [selectedDomainId, setSelectedDomainId] = useState<number | null>(null);

  const load = () => {
    listContentSources()
      .then((r) => { setSources(r.content_sources); setError(null); })
      .catch((e) => setError(e instanceof Error ? e.message : 'Failed to load'));
    getDomains()
      .then((r) => setDomains(r.domains))
      .catch(() => setDomains([]));
  };

  const loadDomainsForSource = (sourceId: number) => {
    getContentSourceDomains(sourceId)
      .then((r) => setDomainsBySourceId((prev) => ({ ...prev, [sourceId]: r.domains })))
      .catch(() => setDomainsBySourceId((prev) => ({ ...prev, [sourceId]: [] })));
  };

  useEffect(() => { load(); }, []);

  useEffect(() => {
    sources.forEach((s) => loadDomainsForSource(s.id));
  }, [sources.length]);

  const handleAdd = () => {
    setAddErrors({});
    const errs = validateSourceForm(formName, formType, formConfig, false);
    if (Object.keys(errs).length > 0) {
      setAddErrors(errs);
      return;
    }
    setError(null);
    const config: Record<string, string> = {};
    (CONFIG_FIELDS[formType] || []).forEach((f) => {
      const v = (formConfig[f.key] || '').trim();
      if (v) config[f.key] = v;
    });
    createContentSource({ name: formName.trim(), type: formType, config })
      .then((created) => {
        setSources((prev) => [...prev, created]);
        setAddForm(false);
        setFormName('');
        setFormType('hashnode');
        setFormConfig(emptyConfigForType('hashnode'));
        setAddErrors({});
      })
      .catch((e) => setError(e instanceof Error ? e.message : 'Create failed'));
  };

  const startEdit = (s: ContentSource) => {
    const fields = CONFIG_FIELDS[s.type] || [];
    const currentConfig = (s.config as Record<string, string> | null) || {};
    setEditForm({
      name: s.name,
      type: s.type,
      config: Object.fromEntries(fields.map((f) => [f.key, currentConfig[f.key] || ''])),
    });
    setEditingId(s.id);
    setEditErrors({});
    setValidateStatus(null);
  };

  const cancelEdit = () => {
    setEditingId(null);
    setEditForm({ name: '', type: 'hashnode', config: {} });
    setEditErrors({});
    setValidateStatus(null);
  };

  const handleTestConnection = () => {
    setValidateStatus('testing');
    const config: Record<string, string> = {};
    (CONFIG_FIELDS[editForm.type] || []).forEach((f) => {
      const v = (editForm.config[f.key] ?? '').trim();
      if (v) config[f.key] = v;
    });
    validateCmsCredentials({ destination: editForm.type, config: Object.keys(config).length ? config : undefined })
      .then((r) => setValidateStatus({ ok: r.ok, message: r.message }))
      .catch((e) => setValidateStatus({ ok: false, message: e instanceof Error ? e.message : 'Validation failed' }));
  };

  const handleSaveEdit = (id: number) => {
    setEditErrors({});
    const errs = validateSourceForm(editForm.name, editForm.type, editForm.config, true);
    if (Object.keys(errs).length > 0) {
      setEditErrors(errs);
      return;
    }
    setError(null);
    const config: Record<string, string> = {};
    (CONFIG_FIELDS[editForm.type] || []).forEach((f) => {
      const v = (editForm.config[f.key] || '').trim();
      if (v) config[f.key] = v;
    });
    updateContentSource(id, { name: editForm.name.trim(), config })
      .then((updated) => {
        setSources((prev) => prev.map((x) => (x.id === id ? updated : x)));
        cancelEdit();
      })
      .catch((e) => setError(e instanceof Error ? e.message : 'Update failed'));
  };

  const handleDelete = (id: number) => {
    if (!window.confirm('Delete this content source? Domain mappings will be removed.')) return;
    setError(null);
    deleteContentSource(id)
      .then(() => {
        setSources((prev) => prev.filter((x) => x.id !== id));
        setDomainsBySourceId((prev) => { const next = { ...prev }; delete next[id]; return next; });
      })
      .catch((e) => setError(e instanceof Error ? e.message : 'Delete failed'));
  };

  const handleAddDomainToSource = (sourceId: number) => {
    const domainId = selectedDomainId ?? domains[0]?.id;
    if (domainId == null) return;
    const linked = domainsBySourceId[sourceId] ?? [];
    if (linked.some((d) => d.id === domainId)) return;
    setError(null);
    addDomainContentSource(domainId, sourceId)
      .then(() => {
        loadDomainsForSource(sourceId);
        setSelectedDomainId(null);
      })
      .catch((e) => setError(e instanceof Error ? e.message : 'Add failed'));
  };

  const handleRemoveDomainFromSource = (sourceId: number, domainId: number) => {
    setError(null);
    removeDomainContentSource(domainId, sourceId)
      .then(() => loadDomainsForSource(sourceId))
      .catch((e) => setError(e instanceof Error ? e.message : 'Remove failed'));
  };

  if (error) {
    return (
      <div className="dashboard">
        <h1>Content sources</h1>
        <p className="error">{error}</p>
        <button type="button" onClick={() => { setError(null); load(); }}>Retry</button>
      </div>
    );
  }

  return (
    <div className="dashboard">
      <header>
        <h1>Content sources</h1>
        <p className="section-desc">
          Create CMS sources (e.g. Hashnode, Ghost) and map them to domains. When publishing a draft you can choose a source; the mapping is stored for each publication.
        </p>
      </header>

      <section className="section">
        <h2>Sources</h2>
        {addForm ? (
          <div className="detail-section" style={{ marginBottom: '1rem' }}>
            <div style={{ marginBottom: '0.75rem' }}>
              <label style={{ marginRight: '0.5rem' }}>
                Name *
                <input
                  type="text"
                  placeholder="e.g. My Hashnode blog"
                  value={formName}
                  onChange={(e) => setFormName(e.target.value)}
                  className="table-filter"
                  style={{ maxWidth: '240px', marginLeft: '0.5rem' }}
                />
              </label>
              {addErrors.name && <span className="error" style={{ marginLeft: '0.5rem', fontSize: '0.85em' }}>{addErrors.name}</span>}
              <select
                value={formType}
                onChange={(e) => {
                  const t = e.target.value;
                  setFormType(t);
                  setFormConfig(emptyConfigForType(t));
                }}
                className="table-filter"
                style={{ marginRight: '0.5rem' }}
              >
                {SOURCE_TYPES.map((t) => (
                  <option key={t} value={t}>{SOURCE_TYPE_LABELS[t] ?? t}</option>
                ))}
              </select>
              <button type="button" onClick={handleAdd}>Add</button>
              <button type="button" onClick={() => { setAddForm(false); setFormName(''); setFormType('hashnode'); setFormConfig(emptyConfigForType('hashnode')); }}>Cancel</button>
            </div>
            {(CONFIG_FIELDS[formType] || []).length > 0 && (
              <>
                <div className="subsection-heading" style={{ marginBottom: '0.5rem', fontWeight: 600 }}>Credentials (required)</div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem', maxWidth: '420px' }}>
                  {(CONFIG_FIELDS[formType] || []).map((f) => (
                    <label key={f.key} style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                      <span style={{ minWidth: '140px' }}>{f.label}{f.required ? ' *' : ''}</span>
                      <input
                        type={f.inputType}
                        value={formConfig[f.key] ?? ''}
                        onChange={(e) => setFormConfig((prev) => ({ ...prev, [f.key]: e.target.value }))}
                        className="table-filter"
                        placeholder={f.inputType === 'password' ? '••••••••' : ''}
                        style={{ flex: 1 }}
                        autoComplete="off"
                      />
                      {addErrors[f.key] && <span className="error" style={{ fontSize: '0.85em' }}>{addErrors[f.key]}</span>}
                    </label>
                  ))}
                </div>
              </>
            )}
          </div>
        ) : (
          <button type="button" onClick={() => setAddForm(true)}>Add content source</button>
        )}
        {sources.length === 0 ? (
          <p className="table-placeholder">No content sources. Add one to map to domains and use when publishing drafts.</p>
        ) : (
          <table className="prompts-table">
            <thead>
              <tr>
                <th>Name</th>
                <th>Type</th>
                <th>Mapped domains</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {sources.map((s) => (
                <React.Fragment key={s.id}>
                <tr>
                  <td>{s.name}</td>
                  <td>{SOURCE_TYPE_LABELS[s.type] ?? s.type}</td>
                  <td>
                    {(domainsBySourceId[s.id] ?? []).length > 0
                      ? (domainsBySourceId[s.id] ?? []).map((d) => d.domain).join(', ')
                      : '—'}
                  </td>
                  <td>
                    <button type="button" className="link-btn" onClick={() => startEdit(s)} disabled={editingId !== null && editingId !== s.id}>Edit</button>
                    {' '}
                    <button type="button" className="link-btn" onClick={() => handleDelete(s.id)} disabled={editingId !== null}>Delete</button>
                  </td>
                </tr>
                {editingId === s.id && (
                  <tr>
                    <td colSpan={4} style={{ padding: '0.75rem', background: 'var(--bg-subtle, #f8f9fa)', verticalAlign: 'top' }}>
                      <div className="subsection-heading" style={{ marginBottom: '0.5rem', fontWeight: 600 }}>Edit content source</div>
                      <div className="content-source-edit-form">
                        <div className="edit-form-row">
                          <span className="edit-form-label">Name *</span>
                          <div className="edit-form-field">
                            <input
                              type="text"
                              value={editForm.name}
                              onChange={(e) => setEditForm((prev) => ({ ...prev, name: e.target.value }))}
                              className="table-filter"
                            />
                            {editErrors.name && <span className="field-error">{editErrors.name}</span>}
                          </div>
                        </div>
                        <div className="edit-form-row">
                          <span className="edit-form-label">Type</span>
                          <div className="edit-form-field">
                            <span>{SOURCE_TYPE_LABELS[editForm.type] ?? editForm.type}</span>
                          </div>
                        </div>
                        {(CONFIG_FIELDS[editForm.type] || []).map((f) => (
                          <div key={f.key} className="edit-form-row">
                            <span className="edit-form-label">{f.label}{f.required ? ' *' : ''}</span>
                            <div className="edit-form-field">
                              <input
                                type={f.inputType}
                                value={editForm.config[f.key] ?? ''}
                                onChange={(e) => setEditForm((prev) => ({
                                  ...prev,
                                  config: { ...prev.config, [f.key]: e.target.value },
                                }))}
                                className="table-filter"
                                placeholder={f.inputType === 'password' ? 'Leave blank to keep current' : ''}
                                autoComplete="off"
                              />
                              {editErrors[f.key] && <span className="field-error">{editErrors[f.key]}</span>}
                            </div>
                          </div>
                        ))}
                        <div className="edit-form-row" style={{ marginTop: '0.25rem' }}>
                          <span className="edit-form-label">Mapped domains</span>
                          <div className="edit-form-field" style={{ maxWidth: 'none' }}>
                          <ul className="list-inline" style={{ marginBottom: '0.35rem' }}>
                            {(domainsBySourceId[s.id] ?? []).map((d) => (
                              <li key={d.id} style={{ display: 'inline-flex', alignItems: 'center', marginRight: '0.5rem', marginBottom: '0.25rem' }}>
                                <span>{d.domain}</span>
                                <button
                                  type="button"
                                  className="link-btn"
                                  style={{ marginLeft: '0.25rem', fontSize: '0.85em' }}
                                  onClick={() => handleRemoveDomainFromSource(s.id, d.id)}
                                  title="Remove mapping"
                                >
                                  ×
                                </button>
                              </li>
                            ))}
                          </ul>
                          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', flexWrap: 'wrap' }}>
                            <select
                              value={selectedDomainId ?? ''}
                              onChange={(e) => setSelectedDomainId(e.target.value ? Number(e.target.value) : null)}
                              className="table-filter"
                              style={{ maxWidth: '220px' }}
                            >
                              <option value="">Select domain to add</option>
                              {domains
                                .filter((d) => !(domainsBySourceId[s.id] ?? []).some((x) => x.id === d.id))
                                .map((d) => (
                                  <option key={d.id} value={d.id}>{d.domain}</option>
                                ))}
                            </select>
                            <button type="button" onClick={() => handleAddDomainToSource(s.id)} disabled={!selectedDomainId && domains.length > 0}>Add domain</button>
                          </div>
                          </div>
                        </div>
                      </div>
                      <div style={{ marginTop: '0.75rem', display: 'flex', alignItems: 'center', gap: '0.5rem', flexWrap: 'wrap' }}>
                        <button type="button" onClick={() => handleSaveEdit(s.id)}>Save</button>
                        <button type="button" onClick={handleTestConnection} disabled={validateStatus === 'testing'}>
                          {validateStatus === 'testing' ? 'Testing…' : 'Test connection'}
                        </button>
                        <button type="button" className="link-btn" onClick={cancelEdit}>Cancel</button>
                        {validateStatus && validateStatus !== 'testing' && (
                          <span style={{ color: validateStatus.ok ? 'var(--color-success, #0a0)' : 'var(--color-error, #c00)', fontSize: '0.9em' }}>
                            {validateStatus.message}
                          </span>
                        )}
                      </div>
                    </td>
                  </tr>
                )}
                </React.Fragment>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </div>
  );
}
