export interface AggregateMetric {
  mean: number
  std: number
  min: number
  max: number
  formatted: string
}

export interface ConfigComparison {
  config: string
  label: string
  model: string
  split: string
  num_runs: number
  precision: AggregateMetric
  recall: AggregateMetric
  f1: AggregateMetric
  fdr: AggregateMetric
  clean_specificity: AggregateMetric
  buggy_detection_rate: AggregateMetric
  mean_latency_s: AggregateMetric
  cost_per_pr_usd: AggregateMetric
  tokens_per_pr: AggregateMetric
}

export interface EvalRunSummaryItem {
  run_id: string
  config: string
  model: string
  split: string
  total_cases: number
  completed_cases: number
  partial_cases: number
  failed_cases: number
  total_findings: number
  total_tokens: number
  total_cost_usd: number
  duration_seconds: number
  created_at: string
}

export interface BenchmarkOverview {
  split: string
  total_cases: number
  num_runs_per_config: number
  model: string
  comparisons: ConfigComparison[]
  runs: EvalRunSummaryItem[]
  report_markdown: string
}

export interface FailureAnalysisData {
  total_evaluated_cases: number
  total_failures: number
  by_failure_mode: Record<string, number>
  by_category: Record<string, number>
  by_language: Record<string, number>
  report_markdown: string
}
