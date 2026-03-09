import {
  useReactTable,
  getCoreRowModel,
  getFilteredRowModel,
  getSortedRowModel,
  flexRender,
  createColumnHelper,
  type SortingState,
} from '@tanstack/react-table';
import { useState } from 'react';
import type { PromptVisibility } from '../api/client';

const columnHelper = createColumnHelper<PromptVisibility>();

const columns = [
  columnHelper.accessor('cited', {
    header: 'Cited',
    cell: (info) => (info.getValue() ? '✓' : '—'),
    size: 80,
  }),
  columnHelper.accessor((r) => r.brand_mentioned ?? false, {
    id: 'brand_mentioned',
    header: 'Brand mentioned',
    cell: (info) => (info.getValue() ? '✓' : '—'),
    size: 100,
  }),
  columnHelper.accessor((r) => r.competitor_only ?? false, {
    id: 'competitor_only',
    header: 'Competitor-only',
    cell: (info) => (info.getValue() ? '✓' : '—'),
    size: 110,
  }),
  columnHelper.accessor('text', {
    header: 'Prompt',
    cell: (info) => info.getValue(),
  }),
];

interface Props {
  prompts: PromptVisibility[];
}

export function PromptsVisibilityTable({ prompts }: Props) {
  const [sorting, setSorting] = useState<SortingState>([{ id: 'cited', desc: false }]);
  const [filter, setFilter] = useState('');

  const table = useReactTable({
    data: prompts,
    columns,
    state: { sorting, globalFilter: filter },
    onSortingChange: setSorting,
    onGlobalFilterChange: setFilter,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
  });

  if (prompts.length === 0) {
    return (
      <div className="table-placeholder">
        No prompts. Generate prompts and run the monitor first.
      </div>
    );
  }

  return (
    <div className="prompts-table-wrap">
      <input
        type="text"
        placeholder="Filter prompts..."
        value={filter}
        onChange={(e) => setFilter(e.target.value)}
        className="table-filter"
      />
      <table className="prompts-table">
        <thead>
          {table.getHeaderGroups().map((hg) => (
            <tr key={hg.id}>
              {hg.headers.map((h) => (
                <th key={h.id} onClick={h.column.getToggleSortingHandler()}>
                  {flexRender(h.column.columnDef.header, h.getContext())}
                  {h.column.getIsSorted() ? (h.column.getIsSorted() === 'asc' ? ' ↑' : ' ↓') : ''}
                </th>
              ))}
            </tr>
          ))}
        </thead>
        <tbody>
          {table.getRowModel().rows.map((row) => (
            <tr key={row.id} data-cited={row.original.cited} data-competitor-only={row.original.competitor_only ?? false}>
              {row.getVisibleCells().map((cell) => (
                <td key={cell.id}>{flexRender(cell.column.columnDef.cell, cell.getContext())}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
