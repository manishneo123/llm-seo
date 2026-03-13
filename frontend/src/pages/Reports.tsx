import { useState, useCallback } from 'react';
import {
  getWeeklyReport,
  getMonitoringRunsReport,
  getCitationsReport,
  getDraftsReport,
  type ReportDateParams,
  type MonitoringRunReportRow,
  type CitationReportRow,
  type DraftReportRow,
} from '../api/client';

type ReportType = 'weekly' | 'monitoring-runs' | 'citations' | 'drafts';

const REPORT_TYPES: { value: ReportType; label: string }[] = [
  { value: 'weekly', label: 'Weekly summary' },
  { value: 'monitoring-runs', label: 'Monitoring runs' },
  { value: 'citations', label: 'Citations' },
  { value: 'drafts', label: 'Drafts' },
];

function downloadCsv(filename: string, rows: Record<string, unknown>[]): void {
  if (rows.length === 0) {
    const header = '';
    const blob = new Blob([header], { type: 'text/csv;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
    return;
  }
  const keys = Object.keys(rows[0]);
  const escape = (v: unknown): string => {
    const s = String(v ?? '');
    if (s.includes('"') || s.includes(',') || s.includes('\n') || s.includes('\r')) {
      return `"${s.replace(/"/g, '""')}"`;
    }
    return s;
  };
  const header = keys.map(escape).join(',');
  const lines = [header, ...rows.map((r) => keys.map((k) => escape(r[k])).join(','))];
  const csv = lines.join('\r\n');
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

function downloadTxt(filename: string, text: string): void {
  const blob = new Blob([text], { type: 'text/plain;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

export function Reports() {
  const [reportType, setReportType] = useState<ReportType>('weekly');
  const [fromDate, setFromDate] = useState<string>('');
  const [toDate, setToDate] = useState<string>('');
  const [summary, setSummary] = useState<string>('');
  const [monitoringRows, setMonitoringRows] = useState<MonitoringRunReportRow[]>([]);
  const [citationRows, setCitationRows] = useState<CitationReportRow[]>([]);
  const [draftRows, setDraftRows] = useState<DraftReportRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);

  const params: ReportDateParams = {};
  if (fromDate) params.from_date = fromDate;
  if (toDate) params.to_date = toDate;

  const loadReport = useCallback(() => {
    setError(null);
    setLoading(true);
    setLoaded(false);
    const doLoad = () => {
      if (reportType === 'weekly') {
        getWeeklyReport(Object.keys(params).length ? params : undefined)
          .then((r) => {
            setSummary(r.summary);
            setMonitoringRows([]);
            setCitationRows([]);
            setDraftRows([]);
            setLoaded(true);
          })
          .catch((e) => setError(e instanceof Error ? e.message : 'Failed to load'))
          .finally(() => setLoading(false));
      } else if (reportType === 'monitoring-runs') {
        getMonitoringRunsReport(Object.keys(params).length ? params : undefined)
          .then((r) => {
            setSummary('');
            setMonitoringRows(r.rows);
            setCitationRows([]);
            setDraftRows([]);
            setLoaded(true);
          })
          .catch((e) => setError(e instanceof Error ? e.message : 'Failed to load'))
          .finally(() => setLoading(false));
      } else if (reportType === 'citations') {
        getCitationsReport(Object.keys(params).length ? params : undefined)
          .then((r) => {
            setSummary('');
            setMonitoringRows([]);
            setCitationRows(r.rows);
            setDraftRows([]);
            setLoaded(true);
          })
          .catch((e) => setError(e instanceof Error ? e.message : 'Failed to load'))
          .finally(() => setLoading(false));
      } else {
        getDraftsReport(Object.keys(params).length ? params : undefined)
          .then((r) => {
            setSummary('');
            setMonitoringRows([]);
            setCitationRows([]);
            setDraftRows(r.rows);
            setLoaded(true);
          })
          .catch((e) => setError(e instanceof Error ? e.message : 'Failed to load'))
          .finally(() => setLoading(false));
      }
    };
    doLoad();
  }, [reportType, fromDate, toDate]);

  const handleDownload = () => {
    const from = fromDate || 'start';
    const to = toDate || 'end';
    if (reportType === 'weekly') {
      downloadTxt(`report-weekly-${from}-${to}.txt`, summary || '');
      return;
    }
    if (reportType === 'monitoring-runs') {
      downloadCsv(
        `report-monitoring-runs-${from}-${to}.csv`,
        monitoringRows.map((r) => ({
          id: r.id,
          started_at: r.started_at,
          finished_at: r.finished_at,
          status: r.status,
          trigger_type: r.trigger_type,
        }))
      );
      return;
    }
    if (reportType === 'citations') {
      downloadCsv(`report-citations-${from}-${to}.csv`, citationRows as unknown as Record<string, unknown>[]);
      return;
    }
    if (reportType === 'drafts') {
      downloadCsv(`report-drafts-${from}-${to}.csv`, draftRows as unknown as Record<string, unknown>[]);
    }
  };

  return (
    <div className="page dashboard">
      <header className="page-header">
        <h1 className="page-title">Reports</h1>
        <p className="page-description">View and download reports by type and date range. Leave dates empty for all time.</p>
      </header>

      <section className="section">
        <h2 className="section-title">Filters</h2>
        <div className="content-source-edit-form" style={{ maxWidth: '520px', marginBottom: '1rem' }}>
          <div className="edit-form-row">
            <span className="edit-form-label">Report type</span>
            <div className="edit-form-field">
              <select
                value={reportType}
                onChange={(e) => setReportType(e.target.value as ReportType)}
                className="form-input"
                style={{ maxWidth: '220px' }}
              >
                {REPORT_TYPES.map((t) => (
                  <option key={t.value} value={t.value}>{t.label}</option>
                ))}
              </select>
            </div>
          </div>
          <div className="edit-form-row">
            <span className="edit-form-label">From date</span>
            <div className="edit-form-field">
              <input
                type="date"
                value={fromDate}
                onChange={(e) => setFromDate(e.target.value)}
                className="form-input"
                style={{ maxWidth: '160px' }}
              />
            </div>
          </div>
          <div className="edit-form-row">
            <span className="edit-form-label">To date</span>
            <div className="edit-form-field">
              <input
                type="date"
                value={toDate}
                onChange={(e) => setToDate(e.target.value)}
                className="form-input"
                style={{ maxWidth: '160px' }}
              />
            </div>
          </div>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', flexWrap: 'wrap', marginBottom: '1rem' }}>
          <button type="button" className="btn-primary" onClick={loadReport} disabled={loading}>
            {loading ? 'Loading…' : 'Apply'}
          </button>
          {loaded && (
            <button type="button" className="btn-secondary" onClick={handleDownload}>
              Download
            </button>
          )}
        </div>
        {error && <p className="error">{error}</p>}
      </section>

      {loaded && !error && (
        <>
          <hr className="section-divider" />
          <section className="section">
            <h2 className="section-title">Report</h2>
          {reportType === 'weekly' && (
            <pre className="draft-body report-summary">{summary || 'No data for the selected range.'}</pre>
          )}
          {reportType === 'monitoring-runs' && (
            <>
              {monitoringRows.length === 0 ? (
                <p className="table-placeholder">No data for the selected range.</p>
              ) : (
                <table className="prompts-table">
                  <thead>
                    <tr>
                      <th>ID</th>
                      <th>Started</th>
                      <th>Finished</th>
                      <th>Status</th>
                      <th>Trigger</th>
                    </tr>
                  </thead>
                  <tbody>
                    {monitoringRows.map((r) => (
                      <tr key={r.id}>
                        <td>{r.id}</td>
                        <td>{r.started_at ? new Date(r.started_at).toLocaleString() : '—'}</td>
                        <td>{r.finished_at ? new Date(r.finished_at).toLocaleString() : '—'}</td>
                        <td>{r.status}</td>
                        <td>{r.trigger_type}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </>
          )}
          {reportType === 'citations' && (
            <>
              {citationRows.length === 0 ? (
                <p className="table-placeholder">No data for the selected range.</p>
              ) : (
                <div style={{ overflowX: 'auto' }}>
                  <table className="prompts-table">
                    <thead>
                      <tr>
                        <th>Run ID</th>
                        <th>Run date</th>
                        <th>Model</th>
                        <th>Prompt ID</th>
                        <th>Cited domain</th>
                        <th>Own domain</th>
                        <th>Snippet</th>
                      </tr>
                    </thead>
                    <tbody>
                      {citationRows.map((r, i) => (
                        <tr key={`${r.run_id}-${r.prompt_id}-${i}`}>
                          <td>{r.run_id}</td>
                          <td>{r.run_date ? new Date(r.run_date).toLocaleString() : '—'}</td>
                          <td>{r.model}</td>
                          <td>{r.prompt_id}</td>
                          <td>{r.cited_domain}</td>
                          <td>{r.is_own_domain ? 'Yes' : 'No'}</td>
                          <td style={{ maxWidth: '200px', overflow: 'hidden', textOverflow: 'ellipsis' }} title={r.raw_snippet}>{r.raw_snippet || '—'}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </>
          )}
            {reportType === 'drafts' && (
            <>
              {draftRows.length === 0 ? (
                <p className="table-placeholder">No data for the selected range.</p>
              ) : (
                <div style={{ overflowX: 'auto' }}>
                  <table className="prompts-table">
                    <thead>
                      <tr>
                        <th>ID</th>
                        <th>Title</th>
                        <th>Status</th>
                        <th>Created</th>
                        <th>Published</th>
                        <th>URL</th>
                      </tr>
                    </thead>
                    <tbody>
                      {draftRows.map((r) => (
                        <tr key={r.id}>
                          <td>{r.id}</td>
                          <td style={{ maxWidth: '220px', overflow: 'hidden', textOverflow: 'ellipsis' }} title={r.title}>{r.title}</td>
                          <td>{r.status}</td>
                          <td>{r.created_at ? new Date(r.created_at).toLocaleString() : '—'}</td>
                          <td>{r.published_at ? new Date(r.published_at).toLocaleString() : '—'}</td>
                          <td style={{ maxWidth: '180px', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                            {r.published_url ? (
                              <a href={r.published_url} target="_blank" rel="noopener noreferrer">{r.published_url}</a>
                            ) : '—'}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </>
          )}
          </section>
        </>
      )}
    </div>
  );
}
