/** API base URL. In dev uses VITE_API_URL or localhost:8000. In production uses VITE_API_URL or, if unset, same origin (for proxy setups). */
function getApiBase(): string {
  const fromEnv = import.meta.env.VITE_API_URL;
  if (fromEnv && typeof fromEnv === 'string' && fromEnv.trim() !== '') return fromEnv.trim();
  if (import.meta.env.DEV) return 'http://localhost:8000';
  if (typeof window !== 'undefined' && window.location?.origin) return window.location.origin;
  return '';
}
const API_BASE = getApiBase();

const AUTH_TOKEN_KEY = 'llm_seo_token';

/** Fetch with Authorization Bearer token from localStorage (for authenticated API calls). */
export async function apiFetch(input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
  const token = localStorage.getItem(AUTH_TOKEN_KEY);
  const headers = new Headers(init?.headers);
  if (token) headers.set('Authorization', `Bearer ${token}`);
  return fetch(input, { ...init, headers });
}

export function getStoredToken(): string | null {
  return localStorage.getItem(AUTH_TOKEN_KEY);
}

export function setStoredToken(token: string): void {
  localStorage.setItem(AUTH_TOKEN_KEY, token);
}

export function clearStoredToken(): void {
  localStorage.removeItem(AUTH_TOKEN_KEY);
}

export interface User {
  id: number;
  email: string;
  name?: string | null;
}

export interface AuthResponse {
  token: string;
  user: User;
}

export async function signup(email: string, password: string, name?: string): Promise<AuthResponse> {
  const res = await apiFetch(`${API_BASE}/api/auth/signup`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password, name: name || undefined }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || 'Signup failed');
  }
  return res.json();
}

export async function signin(email: string, password: string): Promise<AuthResponse> {
  const res = await apiFetch(`${API_BASE}/api/auth/signin`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || 'Invalid email or password');
  }
  return res.json();
}

export async function getMe(): Promise<User> {
  const res = await apiFetch(`${API_BASE}/api/auth/me`);
  if (!res.ok) throw new Error('Not authenticated');
  return res.json();
}

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
  const res = await apiFetch(`${API_BASE}/api/citations/trends?run_limit=${runLimit}`);
  if (!res.ok) throw new Error('Failed to fetch citation trends');
  return res.json();
}

export interface DashboardStats {
  total_prompts: number;
  domains_tracked: number;
  last_run_at: string | null;
  prompts_with_own_citation: number;
  prompts_with_brand_mentioned: number;
  prompts_competitor_only: number;
  total_own_citations: number;
  citation_rate_pct: number;
}

export async function getDashboardStats(): Promise<DashboardStats> {
  const res = await apiFetch(`${API_BASE}/api/dashboard/stats`);
  if (!res.ok) throw new Error('Failed to fetch dashboard stats');
  return res.json();
}

export interface LearningSummary {
  hints: { prompt_gen_hints: string; brief_gen_system_extra: string };
  top_uplift: Array<{
    draft_id: number;
    draft_title: string;
    citation_delta: number;
    brand_delta: number | null;
  }>;
}

export async function getLearningSummary(): Promise<LearningSummary> {
  const res = await apiFetch(`${API_BASE}/api/learning/summary`);
  if (!res.ok) throw new Error('Failed to fetch learning summary');
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
  const res = await apiFetch(`${API_BASE}/api/prompts/visibility?${params}`);
  if (!res.ok) throw new Error('Failed to fetch prompts visibility');
  return res.json();
}

export async function getRuns(limit = 20): Promise<{ runs: { id: number; model: string; started_at: string; finished_at: string | null; prompt_count: number; status: string }[] }> {
  const res = await apiFetch(`${API_BASE}/api/runs?limit=${limit}`);
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
  draft?: { id: number } | null;
}

export async function getBriefs(limit = 50, status?: string): Promise<{ briefs: Brief[] }> {
  const params = new URLSearchParams({ limit: String(limit) });
  if (status) params.set('status', status);
  const res = await apiFetch(`${API_BASE}/api/briefs?${params}`);
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
  image_urls?: string | null;
}

export interface DraftPublication {
  id: number;
  content_source_id: number | null;
  content_source_name: string | null;
  content_source_type: string | null;
  published_url: string | null;
  status: string;
  error_message: string | null;
  published_at: string | null;
  created_at: string;
}

export interface DraftDetail extends Draft {
  body_html?: string | null;
  schema_json?: string | null;
  published_url?: string | null;
  verification_status?: string | null;
  verified_at?: string | null;
  brief?: Brief | null;
  prompt?: { id: number; text: string; niche: string | null; created_at: string } | null;
  publications?: DraftPublication[];
}

export async function getDrafts(limit = 50, status?: string): Promise<{ drafts: Draft[] }> {
  const params = new URLSearchParams({ limit: String(limit) });
  if (status) params.set('status', status);
  const res = await apiFetch(`${API_BASE}/api/drafts?${params}`);
  if (!res.ok) throw new Error('Failed to fetch drafts');
  return res.json();
}

export async function approveDraft(
  draftId: number,
  publish: boolean,
  destination?: string,
  contentSourceId?: number
): Promise<{ ok: boolean; published?: boolean; error?: string }> {
  const params = new URLSearchParams({ publish: String(publish) });
  if (destination) params.set('destination', destination);
  if (contentSourceId != null) params.set('content_source_id', String(contentSourceId));
  const res = await apiFetch(`${API_BASE}/api/drafts/${draftId}/approve?${params}`, { method: 'POST' });
  const data = await res.json();
  if (!res.ok) return { ok: false, error: data.error || 'Request failed' };
  return data;
}

export async function getDraft(id: number): Promise<DraftDetail> {
  const res = await apiFetch(`${API_BASE}/api/drafts/${id}`);
  if (!res.ok) throw new Error(res.status === 404 ? 'Draft not found' : 'Failed to fetch draft');
  return res.json();
}

export async function updateDraft(
  id: number,
  body: { title?: string; body_md?: string; slug?: string; image_urls?: string[] }
): Promise<{ id: number; title: string; slug: string; body_md: string; status: string; updated_at: string; image_urls?: string | null }> {
  const res = await apiFetch(`${API_BASE}/api/drafts/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || 'Failed to update draft');
  return data;
}

export async function publishDraftToSource(
  draftId: number,
  params: { content_source_id: number; title?: string; body_md?: string }
): Promise<{ ok: boolean; published_url?: string }> {
  const res = await apiFetch(`${API_BASE}/api/drafts/${draftId}/publish`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(params),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || 'Publish failed');
  return data;
}

export interface BriefDetail extends Brief {
  prompt?: { id: number; text: string; niche: string | null; created_at: string } | null;
  draft?: { id: number; title: string; slug: string; status: string; created_at: string } | null;
}

export async function getBrief(id: number): Promise<BriefDetail> {
  const res = await apiFetch(`${API_BASE}/api/briefs/${id}`);
  if (!res.ok) throw new Error(res.status === 404 ? 'Brief not found' : 'Failed to fetch brief');
  return res.json();
}

export async function generateBriefImages(
  briefId: number
): Promise<{ ok: boolean; image_urls?: string[]; error?: string }> {
  const res = await apiFetch(`${API_BASE}/api/briefs/${briefId}/generate-images`, { method: 'POST' });
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
    execution_id?: number;
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
  niche?: string,
  promptGenerationRunId?: number
): Promise<{ prompts: PromptListItem[]; total: number }> {
  const params = new URLSearchParams({ limit: String(limit), offset: String(offset) });
  if (niche) params.set('niche', niche);
  if (promptGenerationRunId != null) params.set('prompt_generation_run_id', String(promptGenerationRunId));
  const res = await apiFetch(`${API_BASE}/api/prompts?${params}`);
  if (!res.ok) throw new Error('Failed to fetch prompts');
  return res.json();
}

export async function getPrompt(id: number): Promise<PromptDetail> {
  const res = await apiFetch(`${API_BASE}/api/prompts/${id}`);
  if (!res.ok) throw new Error(res.status === 404 ? 'Prompt not found' : 'Failed to fetch prompt');
  return res.json();
}

export interface ContentSource {
  id: number;
  name: string;
  type: string;
  config?: Record<string, unknown> | null;
  created_at?: string;
  updated_at?: string;
}

export interface CmsOptions {
  wordpress: boolean;
  webflow: boolean;
  ghost: boolean;
  hashnode: boolean;
  content_sources?: ContentSource[];
}

export async function getCmsOptions(): Promise<CmsOptions> {
  const res = await apiFetch(`${API_BASE}/api/cms/options`);
  if (!res.ok) throw new Error('Failed to fetch CMS options');
  return res.json();
}

export async function listContentSources(): Promise<{ content_sources: ContentSource[] }> {
  const res = await apiFetch(`${API_BASE}/api/content-sources`);
  if (!res.ok) throw new Error('Failed to fetch content sources');
  return res.json();
}

export async function getContentSource(id: number): Promise<ContentSource> {
  const res = await apiFetch(`${API_BASE}/api/content-sources/${id}`);
  if (!res.ok) throw new Error(res.status === 404 ? 'Content source not found' : 'Failed to fetch');
  return res.json();
}

export async function createContentSource(body: { name: string; type: string; config?: Record<string, unknown> }): Promise<ContentSource> {
  const res = await apiFetch(`${API_BASE}/api/content-sources`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || 'Failed to create');
  return data;
}

export async function updateContentSource(id: number, body: { name?: string; type?: string; config?: Record<string, unknown> }): Promise<ContentSource> {
  const res = await apiFetch(`${API_BASE}/api/content-sources/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || 'Failed to update');
  return data;
}

export async function deleteContentSource(id: number): Promise<void> {
  const res = await apiFetch(`${API_BASE}/api/content-sources/${id}`, { method: 'DELETE' });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(data.detail || 'Failed to delete');
  }
}

export async function getContentSourceDomains(sourceId: number): Promise<{ domains: { id: number; domain: string }[] }> {
  const res = await apiFetch(`${API_BASE}/api/content-sources/${sourceId}/domains`);
  if (!res.ok) throw new Error('Failed to fetch domains for source');
  return res.json();
}

export async function validateContentSourceCredentials(sourceId: number): Promise<{ ok: boolean; message: string }> {
  const res = await apiFetch(`${API_BASE}/api/content-sources/${sourceId}/validate`, { method: 'POST' });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || 'Validation request failed');
  return data;
}

export async function validateCmsCredentials(params: { destination: string; config?: Record<string, string> }): Promise<{ ok: boolean; message: string }> {
  const res = await apiFetch(`${API_BASE}/api/cms/validate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(params),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || 'Validation request failed');
  return data;
}

export async function getDomainContentSources(domainId: number): Promise<{ content_sources: ContentSource[] }> {
  const res = await apiFetch(`${API_BASE}/api/domains/${domainId}/content-sources`);
  if (!res.ok) throw new Error('Failed to fetch content sources for domain');
  return res.json();
}

export async function addDomainContentSource(domainId: number, contentSourceId: number): Promise<{ ok: boolean }> {
  const res = await apiFetch(`${API_BASE}/api/domains/${domainId}/content-sources`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ content_source_id: contentSourceId }),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || 'Failed to add');
  return data;
}

export async function removeDomainContentSource(domainId: number, contentSourceId: number): Promise<void> {
  const res = await apiFetch(`${API_BASE}/api/domains/${domainId}/content-sources/${contentSourceId}`, { method: 'DELETE' });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(data.detail || 'Failed to remove');
  }
}

export async function submitPublishedUrl(
  draftId: number,
  url: string
): Promise<{ ok: boolean; url: string; verification_status: string; error?: string }> {
  const res = await apiFetch(`${API_BASE}/api/drafts/${draftId}/submit-url`, {
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
  const res = await apiFetch(`${API_BASE}/api/drafts/${draftId}/verify`, { method: 'POST' });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || 'Failed to verify');
  return data;
}

export interface ReportDateParams {
  from_date?: string;
  to_date?: string;
}

export async function getWeeklyReport(params?: ReportDateParams): Promise<{ summary: string }> {
  const sp = new URLSearchParams();
  if (params?.from_date) sp.set('from_date', params.from_date);
  if (params?.to_date) sp.set('to_date', params.to_date);
  const q = sp.toString();
  const url = `${API_BASE}/api/reports/weekly${q ? `?${q}` : ''}`;
  const res = await apiFetch(url);
  if (!res.ok) throw new Error('Failed to fetch report');
  return res.json();
}

export interface MonitoringRunReportRow {
  id: number;
  started_at: string;
  finished_at: string | null;
  status: string;
  trigger_type: string;
}

export async function getMonitoringRunsReport(params?: ReportDateParams): Promise<{ rows: MonitoringRunReportRow[] }> {
  const sp = new URLSearchParams();
  if (params?.from_date) sp.set('from_date', params.from_date);
  if (params?.to_date) sp.set('to_date', params.to_date);
  const q = sp.toString();
  const url = `${API_BASE}/api/reports/monitoring-runs${q ? `?${q}` : ''}`;
  const res = await apiFetch(url);
  if (!res.ok) throw new Error('Failed to fetch monitoring runs report');
  return res.json();
}

export interface CitationReportRow {
  run_id: number;
  run_date: string;
  model: string;
  prompt_id: number;
  cited_domain: string;
  is_own_domain: boolean;
  raw_snippet: string;
}

export async function getCitationsReport(params?: ReportDateParams): Promise<{ rows: CitationReportRow[] }> {
  const sp = new URLSearchParams();
  if (params?.from_date) sp.set('from_date', params.from_date);
  if (params?.to_date) sp.set('to_date', params.to_date);
  const q = sp.toString();
  const url = `${API_BASE}/api/reports/citations${q ? `?${q}` : ''}`;
  const res = await apiFetch(url);
  if (!res.ok) throw new Error('Failed to fetch citations report');
  return res.json();
}

export interface DraftReportRow {
  id: number;
  title: string;
  slug: string;
  status: string;
  created_at: string;
  updated_at: string;
  published_at: string | null;
  published_url: string;
  image_urls: string;
}

export async function getDraftsReport(params?: ReportDateParams): Promise<{ rows: DraftReportRow[] }> {
  const sp = new URLSearchParams();
  if (params?.from_date) sp.set('from_date', params.from_date);
  if (params?.to_date) sp.set('to_date', params.to_date);
  const q = sp.toString();
  const url = `${API_BASE}/api/reports/drafts${q ? `?${q}` : ''}`;
  const res = await apiFetch(url);
  if (!res.ok) throw new Error('Failed to fetch drafts report');
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
  const res = await apiFetch(`${API_BASE}/api/domains`);
  if (!res.ok) throw new Error('Failed to fetch domains');
  return res.json();
}

export async function createDomain(domain: string, brandNames: string[] = []): Promise<Domain> {
  const res = await apiFetch(`${API_BASE}/api/domains`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ domain: domain.trim(), brand_names: brandNames }),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || 'Failed to create domain');
  return data;
}

export async function getDomain(id: number): Promise<Domain> {
  const res = await apiFetch(`${API_BASE}/api/domains/${id}`);
  if (!res.ok) throw new Error(res.status === 404 ? 'Domain not found' : 'Failed to fetch domain');
  return res.json();
}

export async function updateDomain(id: number, domain: string, brandNames: string[]): Promise<Domain> {
  const res = await apiFetch(`${API_BASE}/api/domains/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ domain: domain.trim(), brand_names: brandNames }),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || 'Failed to update domain');
  return data;
}

export async function deleteDomain(id: number): Promise<void> {
  const res = await apiFetch(`${API_BASE}/api/domains/${id}`, { method: 'DELETE' });
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
  const res = await apiFetch(`${API_BASE}/api/domains/${domainId}/profile`);
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
  const res = await apiFetch(`${API_BASE}/api/domains/${domainId}/profile`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(profile),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || 'Failed to update profile');
  return data;
}

export async function runDiscoveryForDomain(domainId: number): Promise<{ ok: boolean; domain?: string; error?: string }> {
  const res = await apiFetch(`${API_BASE}/api/domains/${domainId}/discover`, { method: 'POST' });
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
  const res = await apiFetch(`${API_BASE}/api/discovery/status`);
  if (!res.ok) throw new Error('Failed to fetch discovery status');
  return res.json();
}

export async function runDiscovery(): Promise<{ ok: boolean; profiles_updated: string[] }> {
  const res = await apiFetch(`${API_BASE}/api/discovery/run`, { method: 'POST' });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || 'Discovery failed');
  return data;
}

// ---------- Prompt generation (gated by discovery) ----------
export async function generatePrompts(options: { count?: number; prompts_per_domain?: number }): Promise<{ ok: boolean; inserted: number }> {
  const res = await apiFetch(`${API_BASE}/api/prompts/generate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(options),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || 'Prompt generation failed');
  return data;
}

// ---------- Prompt generation schedule ----------
export interface PromptGenerationSettings {
  enabled: boolean;
  frequency_days: number;
  prompts_per_domain: number | null;
  last_run_at: string | null;
  updated_at: string | null;
}

export async function getPromptGenerationSettings(): Promise<PromptGenerationSettings> {
  const res = await apiFetch(`${API_BASE}/api/prompt-generation/settings`);
  if (!res.ok) throw new Error('Failed to fetch prompt generation settings');
  return res.json();
}

export async function updatePromptGenerationSettings(settings: Partial<PromptGenerationSettings>): Promise<PromptGenerationSettings> {
  const res = await apiFetch(`${API_BASE}/api/prompt-generation/settings`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(settings),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || 'Failed to update settings');
  return data;
}

export async function runPromptGenerationNow(): Promise<{ ok: boolean; inserted: number; run_id?: number }> {
  const res = await apiFetch(`${API_BASE}/api/prompt-generation/run`, { method: 'POST' });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || 'Prompt generation run failed');
  return data;
}

export interface PromptGenerationRun {
  id: number;
  started_at: string;
  finished_at: string | null;
  trigger_type: string;
  status: string;
  inserted_count: number | null;
}

export async function getPromptGenerationRuns(limit = 20, offset = 0): Promise<{ runs: PromptGenerationRun[]; total: number }> {
  const res = await apiFetch(`${API_BASE}/api/prompt-generation/runs?limit=${limit}&offset=${offset}`);
  if (!res.ok) throw new Error('Failed to fetch prompt generation runs');
  return res.json();
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
  const res = await apiFetch(`${API_BASE}/api/monitoring/settings`);
  if (!res.ok) throw new Error('Failed to fetch monitoring settings');
  return res.json();
}

export async function updateMonitoringSettings(settings: Partial<MonitoringSettings>): Promise<MonitoringSettings> {
  const res = await apiFetch(`${API_BASE}/api/monitoring/settings`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(settings),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || 'Failed to update settings');
  return data;
}

export async function runMonitoringNow(options?: { models?: string[]; prompt_limit?: number; domain_ids?: number[]; delay_seconds?: number | null }): Promise<{ ok: boolean; execution_id: number }> {
  const res = await apiFetch(`${API_BASE}/api/monitoring/run`, {
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

export interface TrialDiscovery {
  category: string;
  categories: string[];
  niche: string;
  value_proposition: string;
  key_topics: string[];
  target_audience: string;
  competitors: string[];
  discovered_at?: string;
}

export interface TrialCitation {
  run_id: number;
  prompt_id: number;
  model: string;
  cited_domain: string;
  raw_snippet: string | null;
  is_own_domain: boolean;
}

export interface TrialMention {
  run_id: number;
  prompt_id: number;
  model: string;
  mentioned: string;
  is_own_domain: boolean;
}

export interface TrialPromptResponse {
  prompt_id: number;
  run_id: number;
  model: string;
  response_text: string;
}

export interface MonitoringExecutionDetail extends MonitoringExecution {
  runs: { id: number; execution_id: number | null; model: string; started_at: string; finished_at: string | null; prompt_count: number; status: string }[];
  prompt_visibility?: PromptVisibilityItem[];
  discovery?: TrialDiscovery;
  citations?: TrialCitation[];
  mentions?: TrialMention[];
  prompt_responses?: TrialPromptResponse[];
  queue?: {
    pending: number;
    running: number;
    done: number;
    failed: number;
    total: number;
    delay_seconds?: number;
    avg_task_seconds?: number;
    eta_seconds?: number;
  } | null;
}

export async function getMonitoringExecutions(limit = 20, offset = 0): Promise<{ executions: MonitoringExecution[]; total: number }> {
  const res = await apiFetch(`${API_BASE}/api/monitoring/executions?limit=${limit}&offset=${offset}`);
  if (!res.ok) throw new Error('Failed to fetch executions');
  return res.json();
}

export async function getMonitoringExecution(id: number): Promise<MonitoringExecutionDetail> {
  const res = await apiFetch(`${API_BASE}/api/monitoring/executions/${id}`);
  if (!res.ok) throw new Error(res.status === 404 ? 'Execution not found' : 'Failed to fetch execution');
  return res.json();
}

// ---------- Trial (unauthenticated) ----------
export interface TrialRunResponse {
  token: string;
  execution_id: number;
  slug: string;
  reused?: boolean;
  discovery?: TrialDiscovery;
  /** When sync=true, full execution detail so no polling needed */
  execution?: MonitoringExecutionDetail;
}

function getTrialErrorDetail(err: { detail?: unknown }): string {
  const d = err.detail;
  if (typeof d === 'string') return d;
  if (Array.isArray(d) && d.length > 0 && d[0] && typeof d[0] === 'object' && 'msg' in d[0]) {
    return String((d[0] as { msg: string }).msg);
  }
  return 'Trial failed';
}

/** Throw if response is HTML. Avoids "Unexpected token '<'" when parsing as JSON. */
function ensureJsonResponse(res: Response, requestedUrl?: string): void {
  const ct = (res.headers.get('Content-Type') || '').toLowerCase();
  if (ct.includes('text/html')) {
    const urlHint = requestedUrl ? ` Request: ${requestedUrl}.` : '';
    throw new Error(
      `Server returned HTML instead of JSON.${urlHint} ` +
        'If the URL points to your API (e.g. http://localhost:8000), the API may be down, returning an error page, or another process is using that port. ' +
        'Start the API with: PYTHONPATH=. uvicorn api.main:app --port 8000. ' +
        'If the URL points to your frontend origin, set VITE_API_URL in frontend/.env to your API base and restart dev or rebuild.'
    );
  }
}

export async function runTrial(
  website: string,
  captchaToken?: string | null,
  sync?: boolean
): Promise<TrialRunResponse> {
  const body: { website: string; captcha_token?: string; sync?: boolean } = { website: website.trim() };
  if (captchaToken && captchaToken.trim()) body.captcha_token = captchaToken.trim();
  if (sync === true) body.sync = true;
  let res: Response;
  try {
    res = await fetch(`${API_BASE}/api/trial/run`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
  } catch (e) {
    throw new Error(
      e instanceof Error ? e.message : 'Network error. Check your connection and that the API is reachable.'
    );
  }
  const url = `${API_BASE}/api/trial/run`;
  if (!res.ok) {
    ensureJsonResponse(res, url);
    const err = await res.json().catch(() => ({})) as { detail?: unknown };
    throw new Error(getTrialErrorDetail(err) || `Trial failed (${res.status})`);
  }
  ensureJsonResponse(res, url);
  return res.json();
}

export async function getTrialStatus(token: string): Promise<MonitoringExecutionDetail> {
  const url = `${API_BASE}/api/trial/status?token=${encodeURIComponent(token)}`;
  const res = await fetch(url);
  if (!res.ok) throw new Error(res.status === 404 ? 'Trial session not found' : 'Failed to fetch status');
  ensureJsonResponse(res, url);
  return res.json();
}

export async function getTrialStatusLite(token: string): Promise<MonitoringExecutionDetail> {
  const url = `${API_BASE}/api/trial/status?token=${encodeURIComponent(token)}&lite=1`;
  const res = await fetch(url);
  if (!res.ok) throw new Error(res.status === 404 ? 'Trial session not found' : 'Failed to fetch status');
  ensureJsonResponse(res, url);
  return res.json();
}

export interface TrialDirectoryItem {
  slug: string;
  website: string;
  finished_at: string;
  category?: string | null;
  categories?: string[];
}

export async function getTrialBySlug(slug: string): Promise<MonitoringExecutionDetail> {
  const url = `${API_BASE}/api/trial/by-slug/${encodeURIComponent(slug)}`;
  const res = await fetch(url);
  if (!res.ok) throw new Error(res.status === 404 ? 'No trial results for this domain' : 'Failed to load');
  ensureJsonResponse(res, url);
  return res.json();
}

export async function getTrialDirectory(params?: {
  q?: string;
  category?: string;
  limit?: number;
  offset?: number;
}): Promise<{ trials: TrialDirectoryItem[]; total: number }> {
  const search = new URLSearchParams();
  if (params?.q) search.set('q', params.q);
  if (params?.category) search.set('category', params.category);
  if (params?.limit != null) search.set('limit', String(params.limit));
  if (params?.offset != null) search.set('offset', String(params.offset));
  const qs = search.toString();
  const url = `${API_BASE}/api/trial/directory${qs ? `?${qs}` : ''}`;
  const res = await fetch(url);
  if (!res.ok) throw new Error('Failed to load directory');
  ensureJsonResponse(res, url);
  return res.json();
}

// ---------- Settings: LLM provider API keys and models ----------
export interface LlmProviderSettings {
  openai: string | null;
  perplexity: string | null;
  anthropic: string | null;
  gemini: string | null;
  openai_model: string | null;
  perplexity_model: string | null;
  anthropic_model: string | null;
  gemini_model: string | null;
  updated_at: string | null;
}

export async function getLlmProviderSettings(): Promise<LlmProviderSettings> {
  const res = await apiFetch(`${API_BASE}/api/settings/llm-providers`);
  if (!res.ok) throw new Error('Failed to fetch settings');
  return res.json();
}

export async function updateLlmProviderSettings(settings: {
  openai?: string | null;
  perplexity?: string | null;
  anthropic?: string | null;
  gemini?: string | null;
  openai_model?: string | null;
  perplexity_model?: string | null;
  anthropic_model?: string | null;
  gemini_model?: string | null;
}): Promise<LlmProviderSettings> {
  const res = await apiFetch(`${API_BASE}/api/settings/llm-providers`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(settings),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || 'Failed to update settings');
  return data;
}

export type LlmProviderValidationResult = Record<string, { ok: boolean; error?: string }>;

export async function validateLlmProviderSettings(settings: Record<string, string>): Promise<LlmProviderValidationResult> {
  const res = await apiFetch(`${API_BASE}/api/settings/llm-providers/validate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(settings),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || 'Validation request failed');
  return data;
}
