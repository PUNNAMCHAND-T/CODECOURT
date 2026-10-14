/**
 * TypeScript types matching backend review, pull request, and finding schemas.
 */

export type ReviewStatus = 'queued' | 'running' | 'completed' | 'partial' | 'failed'

export type ReviewConfig = 'single_agent' | 'multi_agent_no_judge' | 'multi_agent_judge'

export type FindingCategory = 'security' | 'performance' | 'maintainability' | 'correctness'

export type FindingSeverity = 'low' | 'medium' | 'high' | 'critical'

export type FindingStatus = 'active' | 'merged' | 'dropped'

export interface FindingSummaryCounts {
  total: number
  security: number
  performance: number
  maintainability: number
  correctness: number
  high_or_critical: number
}

export interface RepositorySummary {
  id: number
  owner: string
  name: string
  full_name: string
  is_private: boolean
}

export interface PullRequestSummary {
  id: number
  repository_id: number
  number: number
  title: string
  state: string
  author: string
  html_url: string
  head_ref: string
  base_ref: string
  changed_files: number
  additions: number
  deletions: number
  repository?: RepositorySummary
}

export interface FindingItem {
  id: number
  review_id: number
  agent: string
  category: FindingCategory
  severity: FindingSeverity
  file: string
  line_start: number
  line_end: number
  title: string
  explanation: string
  evidence: string
  suggested_fix: string | null
  confidence: number
  status: FindingStatus
  merged_from: string[] | null
  decision_reason: string | null
  drop_reason: string | null
  created_at: string
  feedback?: FeedbackItem | null
}

export interface FeedbackItem {
  id: number
  finding_id: number
  action: 'accepted' | 'dismissed'
  reason: string | null
  user_id: string | null
  created_at: string
  updated_at: string
}

export interface FeedbackSummary {
  total: number
  accepted: number
  dismissed: number
  acceptance_rate: number
}

export interface NodeTraceItem {
  node: string
  latency_seconds?: number
  tokens_prompt?: number
  tokens_completion?: number
  tokens_total?: number
  cost_usd?: number
  findings_count?: number
  is_dry_run?: boolean
  error?: string | null
  [key: string]: unknown
}

export interface ReviewItem {
  id: number
  pull_request_id: number
  status: ReviewStatus
  config: Record<string, unknown>
  model: string
  trigger_type: string
  tokens_total: number | null
  cost_usd: number | null
  latency_ms: number | null
  error_message: string | null
  created_at: string
  started_at: string | null
  completed_at: string | null
  pull_request?: PullRequestSummary
  finding_counts?: FindingSummaryCounts
}

export interface ReviewDetail extends ReviewItem {
  findings: FindingItem[]
  diff_text?: string | null
  traces?: NodeTraceItem[]
}

export interface ReviewListResponse {
  items: ReviewItem[]
  total: number
}

export interface ReviewTriggerRequest {
  pr_url: string
  config: ReviewConfig
  model: string
}
