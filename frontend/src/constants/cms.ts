/** Display labels for content source types (dropdowns, tables, publish UI). */
export const SOURCE_TYPE_LABELS: Record<string, string> = {
  hashnode: 'Hashnode',
  ghost: 'Ghost',
  wordpress: 'WordPress',
  webflow: 'Webflow',
  linkedin: 'LinkedIn',
  devto: 'Dev.to',
  notion: 'Notion',
};

export function getSourceTypeLabel(type: string | null | undefined): string {
  if (!type) return type ?? '—';
  return SOURCE_TYPE_LABELS[type] ?? type;
}
