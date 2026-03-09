const API_BASE = import.meta.env.VITE_API_URL || '';

export interface RunTrend {
  run_id: number;
  model: string;
  started_at: string;
  prompt_count: number;
  cited_prompt_count: number;
  citation_rate_pct: number;
}

export interface CitationTrendsResponse {
  runs: RunTrend[];
}

export interface PromptVisibility {
  id: number;
  text: string;
  cited: boolean;
  brand_mentioned?: boolean;
  competitor_only?: boolean;
}

export interface PromptsVisibilityResponse {
  run_ids: number[];
  prompts: PromptVisibility[];
}

export async function getCitationTrends(runLimit = 30): Promise<CitationTrendsResponse> {
  const res = await fetch(`${API_BASE}/api/citations/trends?run_limit=${runLimit}`);
  if (!res.ok) throw new Error('Failed to fetch citation trends');
  return res.json();
}

export async function getPromptsVisibility(
  runId?: number,
  limit = 200,
  competitorOnly?: boolean
): Promise<PromptsVisibilityResponse> {
  const params = new URLSearchParams();
  if (runId != null) params.set('run_id', String(runId));
  params.set('limit', String(limit));
  if (competitorOnly === true) params.set('competitor_only', 'true');
  const res = await fetch(`${API_BASE}/api/prompts/visibility?${params}`);
  if (!res.ok) throw new Error('Failed to fetch prompts visibility');
  return res.json();
}

export async function getRuns(limit = 20): Promise<{ runs: { id: number; model: string; started_at: string; finished_at: string | null; prompt_count: number; status: string }[] }> {
  const res = await fetch(`${API_BASE}/api/runs?limit=${limit}`);
  if (!res.ok) throw new Error('Failed to fetch runs');
  return res.json();
}

export interface Brief {
  id: number;
  prompt_id: number;
  topic: string;
  angle: string;
  priority_score: number;
  suggested_headings: string;
  entities_to_mention: string;
  schema_to_add: string;
  image_prompts?: string | null;
  image_urls?: string | null;
  status: string;
  created_at: string;
}

export async function getBriefs(limit = 50, status?: string): Promise<{ briefs: Brief[] }> {
  const params = new URLSearchParams({ limit: String(limit) });
  if (status) params.set('status', status);
  const res = await fetch(`${API_BASE}/api/briefs?${params}`);
  if (!res.ok) throw new Error('Failed to fetch briefs');
  return res.json();
}

export interface Draft {
  id: number;
  brief_id: number;
  title: string;
  slug: string;
  body_md: string;
  status: string;
  created_at: string;
  updated_at: string;
  published_at?: string | null;
}

export interface DraftDetail extends Draft {
  body_html?: string | null;
  schema_json?: string | null;
  published_url?: string | null;
  verification_status?: string | null;
  verified_at?: string | null;
  brief?: Brief | null;
  prompt?: { id: number; text: string; niche: string | null; created_at: string } | null;
}

export async function getDrafts(limit = 50, status?: string): Promise<{ drafts: Draft[] }> {
  const params = new URLSearchParams({ limit: String(limit) });
  if (status) params.set('status', status);
  const res = await fetch(`${API_BASE}/api/drafts?${params}`);
  if (!res.ok) throw new Error('Failed to fetch drafts');
  return res.json();
}

export async function approveDraft(
  draftId: number,
  publish: boolean,
  destination?: string
): Promise<{ ok: boolean; published?: boolean; error?: string }> {
  const params = new URLSearchParams({ publish: String(publish) });
  if (destination) params.set('destination', destination);
  const res = await fetch(`${API_BASE}/api/drafts/${draftId}/approve?${params}`, { method: 'POST' });
  const data = await res.json();
  if (!res.ok) return { ok: false, error: data.error || 'Request failed' };
  return data;
}

export async function getDraft(id: number): Promise<DraftDetail> {
  const res = await fetch(`${API_BASE}/api/drafts/${id}`);
  if (!res.ok) throw new Error(res.status === 404 ? 'Draft not found' : 'Failed to fetch draft');
  return res.json();
}

export interface BriefDetail extends Brief {
  prompt?: { id: number; text: string; niche: string | null; created_at: string } | null;
  draft?: { id: number; title: string; slug: string; status: string; created_at: string } | null;
}

export async function getBrief(id: number): Promise<BriefDetail> {
  const res = await fetch(`${API_BASE}/api/briefs/${id}`);
  if (!res.ok) throw new Error(res.status === 404 ? 'Brief not found' : 'Failed to fetch brief');
  return res.json();
}

export async function generateBriefImages(
  briefId: number
): Promise<{ ok: boolean; image_urls?: string[]; error?: string }> {
  const res = await fetch(`${API_BASE}/api/briefs/${briefId}/generate-images`, { method: 'POST' });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || data.error || 'Failed to generate images');
  return data;
}

export interface CitationCountByModel {
  own: number;
  other: number;
}

export interface PromptListItem {
  id: number;
  text: string;
  niche: string | null;
  created_at: string;
  citation_counts?: Record<string, CitationCountByModel>;
  mention_counts?: Record<string, CitationCountByModel>;
  /** Competitor brands/domains mentioned in answer text (from discovery list) */
  mentioned_competitors?: string[];
}

export interface CitationItem {
  run_id: number;
  model: string;
  cited_domain: string;
  raw_snippet: string | null;
  created_at: string;
  is_own_domain?: number;
}

export interface MentionItem {
  run_id: number;
  model: string;
  mentioned: string;
  is_own_domain?: number;
}

export interface PromptDetail extends PromptListItem {
  runs: {
    id: number;
    model: string;
    started_at: string;
    prompt_count: number;
    cited: boolean;
    had_own_citation?: number;
    brand_mentioned?: number;
    competitor_only?: number;
    /** When competitor_only=Yes, domains cited in this run (other than ours) */
    others_cited?: string[];
  }[];
  citations: CitationItem[];
  mentions?: MentionItem[];
  /** Competitor brands/domains mentioned in answer text */
  mentioned_competitors?: string[];
  /** Stored LLM response text by run_id (for display / re-process) */
  response_by_run?: Record<number, { model: string; response_text: string }>;
}

export async function getPrompts(
  limit = 100,
  offset = 0,
  niche?: string
): Promise<{ prompts: PromptListItem[]; total: number }> {
  const params = new URLSearchParams({ limit: String(limit), offset: String(offset) });
  if (niche) params.set('niche', niche);
  const res = await fetch(`${API_BASE}/api/prompts?${params}`);
  if (!res.ok) throw new Error('Failed to fetch prompts');
  return res.json();
}

export async function getPrompt(id: number): Promise<PromptDetail> {
  const res = await fetch(`${API_BASE}/api/prompts/${id}`);
  if (!res.ok) throw new Error(res.status === 404 ? 'Prompt not found' : 'Failed to fetch prompt');
  return res.json();
}

export interface CmsOptions {
  wordpress: boolean;
  webflow: boolean;
  ghost: boolean;
  hashnode: boolean;
}

export async function getCmsOptions(): Promise<CmsOptions> {
  const res = await fetch(`${API_BASE}/api/cms/options`);
  if (!res.ok) throw new Error('Failed to fetch CMS options');
  return res.json();
}

export async function submitPublishedUrl(
  draftId: number,
  url: string
): Promise<{ ok: boolean; url: string; verification_status: string; error?: string }> {
  const res = await fetch(`${API_BASE}/api/drafts/${draftId}/submit-url`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ url }),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || 'Failed to submit URL');
  return data;
}

export async function verifyDraftUrl(
  draftId: number
): Promise<{ ok: boolean; verification_status: string; error?: string }> {
  const res = await fetch(`${API_BASE}/api/drafts/${draftId}/verify`, { method: 'POST' });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || 'Failed to verify');
  return data;
}

export async function getWeeklyReport(): Promise<{ summary: string }> {
  const res = await fetch(`${API_BASE}/api/reports/weekly`);
  if (!res.ok) throw new Error('Failed to fetch report');
  return res.json();
}

// ---------- Domains ----------
export interface Domain {
  id: number;
  domain: string;
  brand_names: string[];
  created_at: string;
  updated_at: string;
}

export async function getDomains(): Promise<{ domains: Domain[] }> {
  const res = await fetch(`${API_BASE}/api/domains`);
  if (!res.ok) throw new Error('Failed to fetch domains');
  return res.json();
}

export async function createDomain(domain: string, brandNames: string[] = []): Promise<Domain> {
  const res = await fetch(`${API_BASE}/api/domains`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ domain: domain.trim(), brand_names: brandNames }),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || 'Failed to create domain');
  return data;
}

export async function getDomain(id: number): Promise<Domain> {
  const res = await fetch(`${API_BASE}/api/domains/${id}`);
  if (!res.ok) throw new Error(res.status === 404 ? 'Domain not found' : 'Failed to fetch domain');
  return res.json();
}

export async function updateDomain(id: number, domain: string, brandNames: string[]): Promise<Domain> {
  const res = await fetch(`${API_BASE}/api/domains/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ domain: domain.trim(), brand_names: brandNames }),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || 'Failed to update domain');
  return data;
}

export async function deleteDomain(id: number): Promise<void> {
  const res = await fetch(`${API_BASE}/api/domains/${id}`, { method: 'DELETE' });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(data.detail || 'Failed to delete domain');
  }
}

export interface DomainProfile {
  domain_id: number;
  domain: string;
  category?: string;
  niche?: string;
  value_proposition?: string;
  key_topics?: string[];
  target_audience?: string;
  competitors?: string[];
  discovered_at?: string | null;
}

export async function getDomainProfile(domainId: number): Promise<DomainProfile> {
  const res = await fetch(`${API_BASE}/api/domains/${domainId}/profile`);
  if (!res.ok) throw new Error(res.status === 404 ? 'Domain not found' : 'Failed to fetch profile');
  return res.json();
}

export interface DomainProfileUpdate {
  category?: string;
  niche?: string;
  value_proposition?: string;
  key_topics?: string[];
  target_audience?: string;
  competitors?: string[];
}

export async function updateDomainProfile(
  domainId: number,
  profile: DomainProfileUpdate
): Promise<DomainProfile> {
  const res = await fetch(`${API_BASE}/api/domains/${domainId}/profile`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(profile),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || 'Failed to update profile');
  return data;
}

export async function runDiscoveryForDomain(domainId: number): Promise<{ ok: boolean; domain?: string; error?: string }> {
  const res = await fetch(`${API_BASE}/api/domains/${domainId}/discover`, { method: 'POST' });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || 'Discovery failed');
  return data;
}

// ---------- Discovery ----------
export interface DiscoveryStatus {
  domains_count: number;
  profiles_count: number;
  discovery_done: boolean;
}

export async function getDiscoveryStatus(): Promise<DiscoveryStatus> {
  const res = await fetch(`${API_BASE}/api/discovery/status`);
  if (!res.ok) throw new Error('Failed to fetch discovery status');
  return res.json();
}

export async function runDiscovery(): Promise<{ ok: boolean; profiles_updated: string[] }> {
  const res = await fetch(`${API_BASE}/api/discovery/run`, { method: 'POST' });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || 'Discovery failed');
  return data;
}

// ---------- Prompt generation (gated by discovery) ----------
export async function generatePrompts(options: { count?: number; prompts_per_domain?: number }): Promise<{ ok: boolean; inserted: number }> {
  const res = await fetch(`${API_BASE}/api/prompts/generate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(options),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || 'Prompt generation failed');
  return data;
}

// ---------- Monitoring ----------
export interface MonitoringSettings {
  enabled: boolean;
  frequency_minutes: number | null;
  domain_ids: number[] | null;
  models: string[] | null;
  prompt_limit: number | null;
  delay_seconds: number | null;
  updated_at: string | null;
}

export async function getMonitoringSettings(): Promise<MonitoringSettings> {
  const res = await fetch(`${API_BASE}/api/monitoring/settings`);
  if (!res.ok) throw new Error('Failed to fetch monitoring settings');
  return res.json();
}

export async function updateMonitoringSettings(settings: Partial<MonitoringSettings>): Promise<MonitoringSettings> {
  const res = await fetch(`${API_BASE}/api/monitoring/settings`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(settings),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || 'Failed to update settings');
  return data;
}

export async function runMonitoringNow(options?: { models?: string[]; prompt_limit?: number; domain_ids?: number[]; delay_seconds?: number | null }): Promise<{ ok: boolean; execution_id: number }> {
  const res = await fetch(`${API_BASE}/api/monitoring/run`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(options || {}),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || 'Monitoring run failed');
  return data;
}

export interface MonitoringExecution {
  id: number;
  started_at: string;
  finished_at: string | null;
  trigger_type: string;
  status: string;
  settings_snapshot?: Record<string, unknown> | null;
}

export interface PromptVisibilityRun {
  run_id: number;
  model: string;
  had_own_citation: boolean;
  brand_mentioned: boolean;
  competitor_only: boolean;
}

export interface PromptVisibilityItem {
  prompt_id: number;
  text: string;
  niche: string;
  visibility_by_run: PromptVisibilityRun[];
}

export interface MonitoringExecutionDetail extends MonitoringExecution {
  runs: { id: number; execution_id: number | null; model: string; started_at: string; finished_at: string | null; prompt_count: number; status: string }[];
  prompt_visibility?: PromptVisibilityItem[];
}

export async function getMonitoringExecutions(limit = 20, offset = 0): Promise<{ executions: MonitoringExecution[]; total: number }> {
  const res = await fetch(`${API_BASE}/api/monitoring/executions?limit=${limit}&offset=${offset}`);
  if (!res.ok) throw new Error('Failed to fetch executions');
  return res.json();
}

export async function getMonitoringExecution(id: number): Promise<MonitoringExecutionDetail> {
  const res = await fetch(`${API_BASE}/api/monitoring/executions/${id}`);
  if (!res.ok) throw new Error(res.status === 404 ? 'Execution not found' : 'Failed to fetch execution');
  return res.json();
}
