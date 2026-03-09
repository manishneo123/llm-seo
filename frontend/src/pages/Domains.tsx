import { useEffect, useState } from 'react';
import {
  getDomains,
  getDiscoveryStatus,
  runDiscovery,
  runDiscoveryForDomain,
  getDomainProfile,
  updateDomainProfile,
  createDomain,
  updateDomain,
  deleteDomain,
  type Domain,
  type DiscoveryStatus,
  type DomainProfile,
} from '../api/client';

export function Domains() {
  const [domains, setDomains] = useState<Domain[]>([]);
  const [status, setStatus] = useState<DiscoveryStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [discoveryRunning, setDiscoveryRunning] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [addForm, setAddForm] = useState(false);
  const [formDomain, setFormDomain] = useState('');
  const [formBrandNames, setFormBrandNames] = useState('');
  const [profileByDomainId, setProfileByDomainId] = useState<Record<number, DomainProfile | null>>({});
  const [loadingProfileId, setLoadingProfileId] = useState<number | null>(null);
  const [discoveryRunningDomainId, setDiscoveryRunningDomainId] = useState<number | null>(null);
  const [editingProfileId, setEditingProfileId] = useState<number | null>(null);
  const [profileForm, setProfileForm] = useState<{
    category: string;
    niche: string;
    value_proposition: string;
    target_audience: string;
    key_topics: string[];
    competitors: string[];
  }>({ category: '', niche: '', value_proposition: '', target_audience: '', key_topics: [], competitors: [] });
  const [newCompetitor, setNewCompetitor] = useState('');
  const [profileSaveError, setProfileSaveError] = useState<string | null>(null);

  const load = () => {
    getDomains()
      .then((r) => { setDomains(r.domains); setError(null); })
      .catch((e) => setError(e instanceof Error ? e.message : 'Failed to load'));
    getDiscoveryStatus()
      .then((s) => setStatus(s))
      .catch(() => setStatus(null));
  };

  useEffect(() => { load(); }, []);

  const loadProfile = (domainId: number) => {
    setLoadingProfileId(domainId);
    getDomainProfile(domainId)
      .then((p) => setProfileByDomainId((prev) => ({ ...prev, [domainId]: p })))
      .catch(() => setProfileByDomainId((prev) => ({ ...prev, [domainId]: null })))
      .finally(() => setLoadingProfileId(null));
  };

  const handleRunDiscovery = () => {
    setDiscoveryRunning(true);
    setError(null);
    runDiscovery()
      .then((r) => {
        setDiscoveryRunning(false);
        load();
      })
      .catch((e) => {
        setDiscoveryRunning(false);
        setError(e instanceof Error ? e.message : 'Discovery failed');
      });
  };

  const handleRunDiscoveryForDomain = (domainId: number) => {
    setDiscoveryRunningDomainId(domainId);
    setError(null);
    runDiscoveryForDomain(domainId)
      .then(() => {
        setDiscoveryRunningDomainId(null);
        loadProfile(domainId);
        load();
      })
      .catch((e) => {
        setDiscoveryRunningDomainId(null);
        setError(e instanceof Error ? e.message : 'Discovery failed');
      });
  };

  const startEditProfile = (p: DomainProfile) => {
    const domainId = p.domain_id;
    setEditingProfileId(domainId);
    setProfileForm({
      category: p.category ?? '',
      niche: p.niche ?? '',
      value_proposition: p.value_proposition ?? '',
      target_audience: p.target_audience ?? '',
      key_topics: p.key_topics ?? [],
      competitors: p.competitors ?? [],
    });
    setNewCompetitor('');
    setProfileSaveError(null);
  };

  const cancelEditProfile = () => {
    setEditingProfileId(null);
    setProfileSaveError(null);
  };

  const addCompetitor = () => {
    const s = newCompetitor.trim();
    if (!s) return;
    setProfileForm((prev) => ({ ...prev, competitors: [...prev.competitors, s] }));
    setNewCompetitor('');
  };

  const removeCompetitor = (index: number) => {
    setProfileForm((prev) => ({
      ...prev,
      competitors: prev.competitors.filter((_, i) => i !== index),
    }));
  };

  const handleSaveProfile = (domainId: number) => {
    setProfileSaveError(null);
    updateDomainProfile(domainId, {
      category: profileForm.category,
      niche: profileForm.niche,
      value_proposition: profileForm.value_proposition,
      target_audience: profileForm.target_audience,
      key_topics: profileForm.key_topics,
      competitors: profileForm.competitors,
    })
      .then((updated) => {
        setProfileByDomainId((prev) => ({ ...prev, [domainId]: updated }));
        setEditingProfileId(null);
      })
      .catch((e) => setProfileSaveError(e instanceof Error ? e.message : 'Save failed'));
  };

  const handleSaveEdit = (id: number) => {
    const domain = domains.find((d) => d.id === id);
    if (!domain) return;
    const brandNames = formBrandNames.split(',').map((s) => s.trim()).filter(Boolean);
    updateDomain(id, formDomain, brandNames)
      .then((updated) => {
        setDomains((prev) => prev.map((d) => (d.id === id ? updated : d)));
        setEditingId(null);
        setFormDomain('');
        setFormBrandNames('');
      })
      .catch((e) => setError(e instanceof Error ? e.message : 'Update failed'));
  };

  const handleAdd = () => {
    const brandNames = formBrandNames.split(',').map((s) => s.trim()).filter(Boolean);
    createDomain(formDomain.trim(), brandNames)
      .then((created) => {
        setDomains((prev) => [...prev, created]);
        setAddForm(false);
        setFormDomain('');
        setFormBrandNames('');
        load();
      })
      .catch((e) => setError(e instanceof Error ? e.message : 'Create failed'));
  };

  const handleDelete = (id: number) => {
    if (!window.confirm('Delete this domain? Its discovery profile will also be removed.')) return;
    deleteDomain(id)
      .then(() => {
        setDomains((prev) => prev.filter((d) => d.id !== id));
        setProfileByDomainId((prev) => {
          const next = { ...prev };
          delete next[id];
          return next;
        });
        load();
      })
      .catch((e) => setError(e instanceof Error ? e.message : 'Delete failed'));
  };

  if (error) {
    return (
      <div className="dashboard">
        <h1>Domains</h1>
        <p className="error">{error}</p>
        <button type="button" onClick={() => { setError(null); load(); }}>Retry</button>
      </div>
    );
  }

  return (
    <div className="dashboard">
      <header>
        <h1>Domains</h1>
        <p>Add domains to track (your brand/sites). Run discovery to extract profiles and competitors; then you can generate prompts.</p>
      </header>

      <section className="section">
        <h2>Discovery</h2>
        {status && (
          <p className="section-desc">
            Domains: {status.domains_count} · Profiles: {status.profiles_count}
            {status.discovery_done ? ' · Discovery done — you can generate prompts.' : ' · Run discovery to enable prompt generation.'}
          </p>
        )}
        <div className="section-actions">
          <button
            type="button"
            onClick={handleRunDiscovery}
            disabled={discoveryRunning || (status?.domains_count ?? 0) === 0}
          >
            {discoveryRunning ? 'Running discovery…' : 'Run discovery'}
          </button>
        </div>
      </section>

      <section className="section">
        <h2>Tracked domains</h2>
        {addForm ? (
          <div className="detail-section">
            <input
              type="text"
              placeholder="Domain (e.g. www.example.com)"
              value={formDomain}
              onChange={(e) => setFormDomain(e.target.value)}
              className="table-filter"
              style={{ maxWidth: '320px', marginRight: '0.5rem' }}
            />
            <input
              type="text"
              placeholder="Brand names (comma-separated)"
              value={formBrandNames}
              onChange={(e) => setFormBrandNames(e.target.value)}
              className="table-filter"
              style={{ maxWidth: '280px', marginRight: '0.5rem' }}
            />
            <button type="button" onClick={handleAdd} disabled={!formDomain.trim()}>Add</button>
            <button type="button" onClick={() => { setAddForm(false); setFormDomain(''); setFormBrandNames(''); }}>Cancel</button>
          </div>
        ) : (
          <button type="button" onClick={() => setAddForm(true)}>Add domain</button>
        )}
        {domains.length === 0 ? (
          <p className="table-placeholder">No domains. Add one or more domains to run discovery.</p>
        ) : (
          <table className="prompts-table">
            <thead>
              <tr>
                <th>Domain</th>
                <th>Brand names</th>
                <th>Profile</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {domains.map((d) => (
                <tr key={d.id}>
                  {editingId === d.id ? (
                    <>
                      <td>
                        <input
                          type="text"
                          value={formDomain}
                          onChange={(e) => setFormDomain(e.target.value)}
                          className="table-filter"
                          style={{ width: '100%', maxWidth: '200px' }}
                        />
                      </td>
                      <td>
                        <input
                          type="text"
                          value={formBrandNames}
                          onChange={(e) => setFormBrandNames(e.target.value)}
                          className="table-filter"
                          style={{ width: '100%', maxWidth: '220px' }}
                          placeholder="Comma-separated"
                        />
                      </td>
                      <td>—</td>
                      <td>
                        <button type="button" onClick={() => handleSaveEdit(d.id)}>Save</button>
                        <button type="button" onClick={() => { setEditingId(null); setFormDomain(''); setFormBrandNames(''); }}>Cancel</button>
                      </td>
                    </>
                  ) : (
                    <>
                      <td>{d.domain}</td>
                      <td>{(d.brand_names ?? []).length ? (d.brand_names ?? []).join(', ') : '—'}</td>
                      <td>
                        <button
                          type="button"
                          className="link-btn"
                          onClick={() => loadProfile(d.id)}
                          disabled={loadingProfileId === d.id}
                        >
                          {loadingProfileId === d.id
                            ? 'Loading…'
                            : profileByDomainId[d.id]?.discovered_at
                              ? 'View profile'
                              : 'Load profile'}
                        </button>
                        {' '}
                        <button
                          type="button"
                          className="link-btn"
                          onClick={() => handleRunDiscoveryForDomain(d.id)}
                          disabled={discoveryRunningDomainId === d.id}
                          title="Run discovery for this domain only"
                        >
                          {discoveryRunningDomainId === d.id ? 'Discovering…' : 'Discover'}
                        </button>
                        {loadingProfileId !== d.id && profileByDomainId[d.id] !== undefined && (
                          <span className="section-desc" style={{ marginLeft: '0.5rem', display: 'inline-block' }}>
                            {profileByDomainId[d.id]?.discovered_at
                              ? `${profileByDomainId[d.id]?.niche || '—'} · ${profileByDomainId[d.id]?.competitors?.length ?? 0} competitors`
                              : 'No profile yet. Run Discover.'}
                          </span>
                        )}
                      </td>
                      <td>
                        <button type="button" className="link-btn" onClick={() => { setEditingId(d.id); setFormDomain(d.domain); setFormBrandNames((d.brand_names ?? []).join(', ')); }}>Edit</button>
                        {' '}
                        <button type="button" className="link-btn" onClick={() => handleDelete(d.id)}>Delete</button>
                      </td>
                    </>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      {Object.entries(profileByDomainId).map(([id, p]) => {
        if (!p || !p.discovered_at) return null;
        const pid = Number(id);
        const domainId = p.domain_id ?? pid;
        const isEditing = editingProfileId === domainId;
        return (
          <section key={pid} className="section detail-section">
            <h2>
              Profile: {p.domain}
              {!isEditing && (
                <button
                  type="button"
                  className="link-btn"
                  style={{ marginLeft: '0.75rem', fontSize: '0.9rem' }}
                  onClick={() => startEditProfile(p)}
                >
                  Edit profile
                </button>
              )}
            </h2>
            {profileSaveError && isEditing && <p className="error">{profileSaveError}</p>}
            {isEditing ? (
              <div className="profile-edit-form">
                <label className="profile-edit-label">Category</label>
                <input
                  type="text"
                  value={profileForm.category}
                  onChange={(e) => setProfileForm((f) => ({ ...f, category: e.target.value }))}
                  className="table-filter"
                  style={{ marginBottom: '0.75rem', maxWidth: '100%' }}
                />
                <label className="profile-edit-label">Niche</label>
                <input
                  type="text"
                  value={profileForm.niche}
                  onChange={(e) => setProfileForm((f) => ({ ...f, niche: e.target.value }))}
                  className="table-filter"
                  style={{ marginBottom: '0.75rem', maxWidth: '100%' }}
                />
                <label className="profile-edit-label">Value proposition</label>
                <textarea
                  value={profileForm.value_proposition}
                  onChange={(e) => setProfileForm((f) => ({ ...f, value_proposition: e.target.value }))}
                  className="table-filter"
                  rows={3}
                  style={{ marginBottom: '0.75rem', width: '100%', resize: 'vertical' }}
                />
                <label className="profile-edit-label">Target audience</label>
                <textarea
                  value={profileForm.target_audience}
                  onChange={(e) => setProfileForm((f) => ({ ...f, target_audience: e.target.value }))}
                  className="table-filter"
                  rows={2}
                  style={{ marginBottom: '0.75rem', width: '100%', resize: 'vertical' }}
                />
                <label className="profile-edit-label">Key topics (one per line)</label>
                <textarea
                  value={profileForm.key_topics.join('\n')}
                  onChange={(e) => setProfileForm((f) => ({ ...f, key_topics: e.target.value.split('\n').map((s) => s.trim()).filter(Boolean) }))}
                  className="table-filter"
                  rows={4}
                  placeholder="One topic per line"
                  style={{ marginBottom: '0.75rem', width: '100%', resize: 'vertical' }}
                />
                <label className="profile-edit-label">Competitors (add or remove)</label>
                <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '0.5rem', flexWrap: 'wrap' }}>
                  <input
                    type="text"
                    value={newCompetitor}
                    onChange={(e) => setNewCompetitor(e.target.value)}
                    onKeyDown={(e) => e.key === 'Enter' && (e.preventDefault(), addCompetitor())}
                    className="table-filter"
                    placeholder="Add competitor name"
                    style={{ flex: '1', minWidth: '140px' }}
                  />
                  <button type="button" onClick={addCompetitor}>Add</button>
                </div>
                <ul className="profile-competitors-list">
                  {profileForm.competitors.map((c, i) => (
                    <li key={`${c}-${i}`}>
                      <span>{c}</span>
                      <button type="button" className="link-btn" onClick={() => removeCompetitor(i)} title="Remove">×</button>
                    </li>
                  ))}
                </ul>
                {profileForm.competitors.length === 0 && <p className="section-desc">No competitors. Add some above.</p>}
                <div style={{ marginTop: '1rem', display: 'flex', gap: '0.5rem' }}>
                  <button type="button" onClick={() => handleSaveProfile(domainId)}>Save profile</button>
                  <button type="button" onClick={cancelEditProfile}>Cancel</button>
                </div>
              </div>
            ) : (
              <dl className="detail-dl">
                <dt>Category</dt><dd>{p.category || '—'}</dd>
                <dt>Niche</dt><dd>{p.niche || '—'}</dd>
                <dt>Value proposition</dt><dd>{p.value_proposition || '—'}</dd>
                <dt>Target audience</dt><dd>{p.target_audience || '—'}</dd>
                <dt>Key topics</dt><dd>{(p.key_topics ?? []).join(', ') || '—'}</dd>
                <dt>Competitors</dt><dd>{(p.competitors ?? []).join(', ') || '—'}</dd>
                <dt>Discovered at</dt><dd>{p.discovered_at || '—'}</dd>
              </dl>
            )}
          </section>
        );
      })}
    </div>
  );
}
