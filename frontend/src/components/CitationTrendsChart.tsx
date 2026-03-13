import { useMemo } from 'react';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from 'recharts';
import type { RunTrend } from '../api/client';

interface Props {
  runs: RunTrend[];
}

export function CitationTrendsChart({ runs }: Props) {
  const allModels = ['openai', 'anthropic', 'perplexity', 'gemini'];

  const data = useMemo(() => {
    const byDate: Record<string, Record<string, string | number>> = {};
    for (const r of runs) {
      const date = r.started_at.slice(0, 10);
      if (!byDate[date]) {
        byDate[date] = { date };
        for (const m of allModels) byDate[date][m] = 0;
      }
      byDate[date][r.model] = r.citation_rate_pct;
    }
    return Object.entries(byDate)
      .map(([, row]) => ({ ...row }))
      .sort((a, b) => String(a.date).localeCompare(String(b.date)));
  }, [runs]);

  const models = useMemo(() => {
    const fromRuns = new Set(runs.map((r) => r.model));
    return allModels.filter((m) => fromRuns.has(m)).length > 0
      ? allModels
      : Array.from(fromRuns);
  }, [runs]);

  const colors: Record<string, string> = {
    openai: '#0d9488',
    anthropic: '#b45309',
    perplexity: '#4f46e5',
    gemini: '#2563eb',
  };

  if (runs.length === 0) {
    return (
      <div className="chart-placeholder">
        No run data yet. Run the monitor to populate.
      </div>
    );
  }

  return (
    <ResponsiveContainer width="100%" height={320}>
      <LineChart data={data} margin={{ top: 8, right: 16, left: 8, bottom: 8 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#ddd" />
        <XAxis dataKey="date" stroke="#555" />
        <YAxis stroke="#555" tickFormatter={(v) => `${v}%`} />
        <Tooltip
          contentStyle={{ background: '#fff', border: '1px solid #ccc', color: '#333' }}
          formatter={(value: number | undefined) => [value != null ? `${value}%` : '—', 'Citation rate']}
          labelFormatter={(label) => `Date: ${label}`}
        />
        <Legend />
        {models.map((model) => (
          <Line
            key={model}
            type="monotone"
            dataKey={model}
            name={model}
            stroke={colors[model] || '#666'}
            strokeWidth={2}
            dot={{ r: 3 }}
          />
        ))}
      </LineChart>
    </ResponsiveContainer>
  );
}
