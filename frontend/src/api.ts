// In dev, Vite proxies /api → localhost:8000. In production, use VITE_API_URL.
const BASE = import.meta.env.VITE_API_URL || '/api';

async function request(path: string, options: RequestInit = {}) {
  const token = localStorage.getItem('kf_token');
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(options.headers as Record<string, string> || {}),
  };
  if (token) headers['Authorization'] = `Bearer ${token}`;

  const res = await fetch(`${BASE}${path}`, { ...options, headers });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    let message = `${res.status} ${res.statusText}`;
    if (typeof body.detail === 'string') {
      message = body.detail;
    } else if (Array.isArray(body.detail)) {
      message = body.detail.map((e: { msg?: string }) => e.msg || JSON.stringify(e)).join('; ');
    } else if (body.detail) {
      message = JSON.stringify(body.detail);
    }
    throw new Error(message);
  }
  return res.json();
}

export interface TitleItem {
  title: string;
  score: number;
  hook_type: string;
  pattern_id: string;
}

export interface GenerationResponse {
  generation_id: string;
  matched_subreddits: { subreddit: string; score: number }[];
  titles: TitleItem[];
  metadata: Record<string, unknown> | null;
}

export interface FullGenerationResponse extends GenerationResponse {
  selected_title: string | null;
  selected_pattern_id: string | null;
  body: string | null;
  self_check: { passed: boolean; dimensions: Record<string, unknown>; suggestions: string[] } | null;
}

export interface SelfCheckResult {
  passed: boolean;
  dimensions: Record<string, { 得分?: number; score?: number; 状态?: string; status?: string; 触发的反模式?: string[] }>;
  suggestions: string[];
}

export interface ReviseResult {
  revised_body: string;
}

export interface TrackResponse {
  generation_id: string;
  performance: string;
  subreddit_median: number;
  upvotes: number;
  num_comments: number;
}

export interface HistoryItem {
  generation_id: string;
  subreddit: string;
  title: string;
  upvotes: number;
  num_comments: number;
  upvote_ratio: number;
  performance: string;
  tracked_at: string;
}


export interface PredictionItem {
  title: string
  score: number
  hook_type: string
  pattern_id: string
  predicted_range: string
  confidence: string
  reasoning: string
}

export interface PredictResponse {
  generation_id: string
  subreddit: string
  predictions: PredictionItem[]
}

// ── Billing & Quota ────────────────────────────────────────────────

export interface QuotaInfo {
  used: number
  limit: number
  tier: string
  remaining: number
}

export interface BillingStatus {
  plan: string
  status: string
  cancel_at_period_end: boolean
  current_period_end: string | null
  stripe_customer_id: string | null
}

export interface AsyncJobStatus {
  generation_id: string
  status: string  // "pending" | "processing" | "done" | "failed"
  result: FullGenerationResponse | null
  error: string | null
}

export class QuotaExceededError extends Error {
  used: number
  limit: number
  tier: string

  constructor(detail: { used: number; limit: number; tier: string; upgrade_url: string }) {
    super('Quota exceeded')
    this.name = 'QuotaExceededError'
    this.used = detail.used
    this.limit = detail.limit
    this.tier = detail.tier
  }
}

export const api = {
  get: (path: string) => request(path) as Promise<unknown>,

  generateTitles: (user_input: string, target_subreddit?: string, n_titles = 3) =>
    request('/generate/titles', {
      method: 'POST',
      body: JSON.stringify({ user_input, target_subreddit: target_subreddit || null, n_titles }),
    }) as Promise<GenerationResponse>,

  generateFull: (user_input: string, target_subreddit?: string, n_titles = 3, title_index = 0) =>
    request(`/generate/full?title_index=${title_index}`, {
      method: 'POST',
      body: JSON.stringify({ user_input, target_subreddit: target_subreddit || null, n_titles }),
    }) as Promise<FullGenerationResponse>,

  generateAsync: (user_input: string, target_subreddit?: string, n_titles = 3, title_index = 0) =>
    request(`/generate/async?title_index=${title_index}`, {
      method: 'POST',
      body: JSON.stringify({ user_input, target_subreddit: target_subreddit || null, n_titles }),
    }) as Promise<{ generation_id: string; status: string; message: string }>,

  getJobStatus: (generationId: string) =>
    request(`/generate/${generationId}/status`) as Promise<AsyncJobStatus>,

  getQuota: () =>
    request('/usage') as Promise<QuotaInfo>,

  getBillingStatus: () =>
    request('/billing/status') as Promise<BillingStatus>,

  createCheckout: (successUrl?: string, cancelUrl?: string) =>
    request('/billing/create-checkout', {
      method: 'POST',
      body: JSON.stringify({ success_url: successUrl, cancel_url: cancelUrl }),
    }) as Promise<{ url: string; session_id: string }>,

  createPortal: () =>
    request('/billing/portal', { method: 'POST' }) as Promise<{ url: string }>,

  predict: (user_input: string, target_subreddit: string, n_titles = 3) =>
    request('/generate/predict', {
      method: 'POST',
      body: JSON.stringify({ user_input, target_subreddit, n_titles }),
    }) as Promise<PredictResponse>,

  track: (data: {
    generation_id: string; subreddit: string; title: string; body?: string;
    pattern_id?: string; upvotes: number; num_comments: number;
    upvote_ratio: number; url?: string;
  }) => request('/track/', { method: 'POST', body: JSON.stringify(data) }) as Promise<TrackResponse>,

  getHistory: (limit = 20) => request(`/track/history?limit=${limit}`) as Promise<HistoryItem[]>,

  recheck: (title: string, body: string, pattern_id: string, subreddit = '') =>
    request('/generate/recheck', {
      method: 'POST',
      body: JSON.stringify({ title, body, pattern_id, subreddit }),
    }) as Promise<SelfCheckResult>,

  revise: (title: string, body: string, suggestions: string[], subreddit = '') =>
    request('/generate/revise', {
      method: 'POST',
      body: JSON.stringify({ title, body, suggestions, subreddit }),
    }) as Promise<ReviseResult>,

  login: (email: string, password: string) =>
    request('/auth/login', { method: 'POST', body: JSON.stringify({ email, password }) }) as Promise<{ token: string; user: Record<string, unknown> }>,

  register: (email: string, password: string, display_name?: string) =>
    request('/auth/register', { method: 'POST', body: JSON.stringify({ email, password, display_name }) }) as Promise<{ token: string; user: Record<string, unknown> }>,
};
