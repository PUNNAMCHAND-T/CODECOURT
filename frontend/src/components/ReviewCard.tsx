import {
  Clock,
  Coins,
  ExternalLink,
  ShieldAlert,
} from 'lucide-react'
import type { ReviewItem, ReviewStatus } from '../types/review'

interface ReviewCardProps {
  review: ReviewItem
  onSelectReview?: (reviewId: number) => void
}

function getStatusBadge(status: ReviewStatus) {
  switch (status) {
    case 'completed':
      return {
        label: 'Completed',
        bgVar: 'var(--cc-success-subtle)',
        fgVar: 'var(--cc-success-fg)',
        dotClass: '',
      }
    case 'running':
      return {
        label: 'Running',
        bgVar: 'var(--cc-accent-subtle)',
        fgVar: 'var(--cc-accent-fg)',
        dotClass: 'animate-ping',
      }
    case 'queued':
      return {
        label: 'Queued',
        bgVar: 'var(--cc-warning-subtle)',
        fgVar: 'var(--cc-warning-fg)',
        dotClass: '',
      }
    case 'partial':
      return {
        label: 'Partial',
        bgVar: 'var(--cc-warning-subtle)',
        fgVar: 'var(--cc-warning-fg)',
        dotClass: '',
      }
    case 'failed':
      return {
        label: 'Failed',
        bgVar: 'var(--cc-danger-subtle)',
        fgVar: 'var(--cc-danger-fg)',
        dotClass: '',
      }
  }
}

function getConfigLabel(configKey: string | undefined): { label: string; bgVar: string; fgVar: string } {
  if (configKey === 'multi_agent_judge') {
    return { label: 'Multi-Agent + Judge', bgVar: 'var(--cc-accent-subtle)', fgVar: 'var(--cc-accent-fg)' }
  }
  if (configKey === 'multi_agent_no_judge') {
    return { label: 'Multi-Agent (Ablation)', bgVar: 'var(--cc-done-subtle)', fgVar: 'var(--cc-done-fg)' }
  }
  return { label: 'Single Agent (Baseline)', bgVar: 'var(--cc-bg-subtle)', fgVar: 'var(--cc-fg-muted)' }
}

export function ReviewCard({ review, onSelectReview }: ReviewCardProps) {
  const pr = review.pull_request
  const counts = review.finding_counts
  const statusInfo = getStatusBadge(review.status)
  const configKey = typeof review.config?.config === 'string'
    ? review.config.config
    : typeof review.config === 'string'
    ? review.config
    : 'multi_agent_judge'
  const configInfo = getConfigLabel(configKey)

  const formattedDate = new Date(review.created_at).toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })

  return (
    <div
      onClick={() => onSelectReview?.(review.id)}
      className="glass-card p-5 flex flex-col justify-between cursor-pointer group"
    >
      <div>
        {/* Top row: Repo + PR # + Status */}
        <div className="flex items-center justify-between gap-2 mb-2.5">
          <div className="flex items-center gap-2 text-xs truncate" style={{ color: 'var(--cc-fg-muted)' }}>
            <span className="font-semibold truncate" style={{ color: 'var(--cc-fg-default)' }}>
              {pr?.repository?.full_name ?? 'Repository'}
            </span>
            <span>•</span>
            <span className="font-mono" style={{ color: 'var(--cc-fg-muted)' }}>#{pr?.number ?? review.pull_request_id}</span>
          </div>

          <div
            className="gh-label text-xs font-medium"
            style={{ background: statusInfo.bgVar, color: statusInfo.fgVar }}
          >
            <span
              className={`w-1.5 h-1.5 rounded-full ${statusInfo.dotClass}`}
              style={{ backgroundColor: statusInfo.fgVar }}
            />
            <span>{statusInfo.label}</span>
          </div>
        </div>

        {/* PR Title */}
        <div className="flex items-start justify-between gap-3 mb-3">
          <h3
            className="text-sm font-semibold line-clamp-2 transition-colors duration-200 group-hover:!color-accent"
            style={{ color: 'var(--cc-fg-default)' }}
            onMouseEnter={(e) => { e.currentTarget.style.color = 'var(--cc-accent-fg)' }}
            onMouseLeave={(e) => { e.currentTarget.style.color = 'var(--cc-fg-default)' }}
          >
            {pr?.title ?? `Pull Request #${pr?.number ?? review.pull_request_id}`}
          </h3>
          {pr?.html_url && (
            <a
              href={pr.html_url}
              target="_blank"
              rel="noopener noreferrer"
              onClick={(e) => e.stopPropagation()}
              className="transition-colors p-1"
              style={{ color: 'var(--cc-fg-subtle)' }}
              title="Open PR on GitHub"
              onMouseEnter={(e) => { e.currentTarget.style.color = 'var(--cc-fg-default)' }}
              onMouseLeave={(e) => { e.currentTarget.style.color = 'var(--cc-fg-subtle)' }}
            >
              <ExternalLink className="w-3.5 h-3.5" />
            </a>
          )}
        </div>

        {/* Architecture & Model Tag */}
        <div className="flex flex-wrap items-center gap-1.5 mb-4 text-[11px]">
          <span
            className="px-2 py-0.5 rounded-full font-medium"
            style={{ background: configInfo.bgVar, color: configInfo.fgVar }}
          >
            {configInfo.label}
          </span>
          <span
            className="px-2 py-0.5 rounded font-mono"
            style={{ background: 'var(--cc-bg-subtle)', color: 'var(--cc-fg-muted)', border: '1px solid var(--cc-border-default)' }}
          >
            {review.model}
          </span>
        </div>
      </div>

      {/* Bottom Section: Findings Breakdown & Resource Metrics */}
      <div className="pt-3 space-y-2.5" style={{ borderTop: '1px solid var(--cc-border-default)' }}>
        {/* Finding Pills */}
        <div className="flex flex-wrap items-center gap-1.5 text-xs">
          <span className="text-[11px] font-medium mr-1" style={{ color: 'var(--cc-fg-muted)' }}>Findings:</span>
          {counts && counts.total > 0 ? (
            <>
              <span
                className="px-2 py-0.5 rounded-full font-semibold"
                style={{ background: 'var(--cc-bg-subtle)', color: 'var(--cc-fg-default)', border: '1px solid var(--cc-border-default)' }}
              >
                {counts.total} total
              </span>
              {counts.high_or_critical > 0 && (
                <span
                  className="px-2 py-0.5 rounded-full font-medium flex items-center gap-1"
                  style={{ background: 'var(--cc-danger-subtle)', color: 'var(--cc-danger-fg)' }}
                >
                  <ShieldAlert className="w-3 h-3" />
                  <span>{counts.high_or_critical} high</span>
                </span>
              )}
              {counts.security > 0 && (
                <span
                  className="px-2 py-0.5 rounded-full text-[11px]"
                  style={{ background: 'var(--cc-danger-subtle)', color: 'var(--cc-danger-fg)' }}
                >
                  {counts.security} sec
                </span>
              )}
              {counts.performance > 0 && (
                <span
                  className="px-2 py-0.5 rounded-full text-[11px]"
                  style={{ background: 'var(--cc-warning-subtle)', color: 'var(--cc-warning-fg)' }}
                >
                  {counts.performance} perf
                </span>
              )}
            </>
          ) : (
            <span className="text-xs italic" style={{ color: 'var(--cc-fg-subtle)' }}>No defects identified</span>
          )}
        </div>

        {/* Cost & Latency & Timestamp */}
        <div className="flex items-center justify-between text-[11px]" style={{ color: 'var(--cc-fg-muted)' }}>
          <div className="flex items-center gap-3 font-mono">
            {review.latency_ms !== null && review.latency_ms > 0 && (
              <span className="flex items-center gap-1">
                <Clock className="w-3 h-3" style={{ color: 'var(--cc-fg-subtle)' }} />
                <span>{(review.latency_ms / 1000).toFixed(1)}s</span>
              </span>
            )}
            {review.cost_usd !== null && (
              <span className="flex items-center gap-1" style={{ color: 'var(--cc-success-fg)' }}>
                <Coins className="w-3 h-3" />
                <span>${review.cost_usd.toFixed(4)}</span>
              </span>
            )}
          </div>
          <span>{formattedDate}</span>
        </div>
      </div>
    </div>
  )
}
