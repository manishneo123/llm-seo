import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { getDiscoveryStatus, generatePrompts } from '../api/client';

const PAGE_SIZE = 20;

export function GeneratePrompts() {
  const navigate = useNavigate();
  const [discoveryDone, setDiscoveryDone] = useState(false);
  const [generateCount, setGenerateCount] = useState(10);
  const [generateMode, setGenerateMode] = useState<'total' | 'per_domain'>('per_domain');
  const [generateRunning, setGenerateRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getDiscoveryStatus()
      .then((s) => setDiscoveryDone(s.discovery_done))
      .catch(() => setDiscoveryDone(false));
  }, []);

  const handleGenerate = () => {
    setGenerateRunning(true);
    setError(null);
    const options = generateMode === 'per_domain'
      ? { prompts_per_domain: Math.max(1, generateCount) }
      : { count: Math.max(1, generateCount) };
    generatePrompts(options)
      .then((r) => {
        setGenerateRunning(false);
        navigate('/prompts', { state: { generated: true, inserted: r.inserted } });
      })
      .catch((e) => {
        setGenerateRunning(false);
        setError(e instanceof Error ? e.message : 'Generate failed');
      });
  };

  return (
    <div className="dashboard">
      <header>
        <button type="button" className="link-btn" onClick={() => navigate('/prompts')}>← Back to prompts</button>
        <h1>Generate prompts</h1>
        <p>Create new prompts from your domain profiles. Run discovery on the Domains page first.</p>
      </header>

      {!discoveryDone ? (
        <section className="section detail-section">
          <p className="section-desc">Add domains and run discovery on the Domains page to enable prompt generation.</p>
          <button type="button" onClick={() => navigate('/domains')}>Go to Domains</button>
        </section>
      ) : (
        <section className="section detail-section">
          <h2>Settings</h2>
          <p className="section-desc">Choose how many prompts to generate per domain or in total. New prompts will appear in the prompts list.</p>
          <div className="profile-edit-form" style={{ maxWidth: '480px' }}>
            <label className="profile-edit-label">Mode</label>
            <div style={{ marginBottom: '1rem' }}>
              <label style={{ display: 'block', marginBottom: '0.5rem' }}>
                <input
                  type="radio"
                  checked={generateMode === 'per_domain'}
                  onChange={() => setGenerateMode('per_domain')}
                />
                {' '}Per domain — generate N prompts for each domain (N × number of domains)
              </label>
              <label style={{ display: 'block' }}>
                <input
                  type="radio"
                  checked={generateMode === 'total'}
                  onChange={() => setGenerateMode('total')}
                />
                {' '}Total — generate N prompts in total (using first domain profile)
              </label>
            </div>
            <label className="profile-edit-label">Number of prompts</label>
            <input
              type="number"
              min={1}
              max={500}
              value={generateCount}
              onChange={(e) => setGenerateCount(parseInt(e.target.value, 10) || 10)}
              className="table-filter"
              style={{ width: '100px', marginBottom: '1rem' }}
            />
            <span className="section-desc" style={{ marginLeft: '0.5rem' }}>
              {generateMode === 'per_domain' ? 'prompts per domain' : 'prompts total'}
            </span>
            {error && <p className="error" style={{ marginTop: '0.75rem' }}>{error}</p>}
            <div style={{ marginTop: '1.25rem', display: 'flex', gap: '0.5rem' }}>
              <button type="button" onClick={handleGenerate} disabled={generateRunning}>
                {generateRunning ? 'Generating…' : 'Generate prompts'}
              </button>
              <button type="button" onClick={() => navigate('/prompts')}>Cancel</button>
            </div>
          </div>
        </section>
      )}
    </div>
  );
}
