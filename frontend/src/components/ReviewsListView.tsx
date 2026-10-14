import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  AlertCircle,
  CheckCircle,
  Coins,
  FileCode,
  Filter,
  GitPullRequest,
  Plus,
  RefreshCw,
  Search,
  ShieldCheck,
} from 'lucide-react'
import { fetchReviews } from '../services/api'
import type { ReviewItem } from '../types/review'
import { ReviewCard } from './ReviewCard'
import { TriggerReviewModal } from './TriggerReviewModal'

interface ReviewsListViewProps {
  onSelectReview?: (reviewId: number) => void
}

const STATUS_FILTERS: { label: string; value: string }[] = [
  { label: 'All', value: 'all' },
  { label: 'Completed', value: 'completed' },
  { label: 'Running', value: 'running' },
  { label: 'Queued', value: 'queued' },
  { label: 'Partial', value: 'partial' },
  { label: 'Failed', value: 'failed' },
]

export function ReviewsListView({ onSelectReview }: ReviewsListViewProps) {
  const [reviews, setReviews] = useState<ReviewItem[]>([])
  const [totalCount, setTotalCount] = useState<number>(0)
  const [isLoading, setIsLoading] = useState<boolean>(true)
  const [error, setError] = useState<string | null>(null)
  const [statusFilter, setStatusFilter] = useState<string>('all')
  const [searchQuery, setSearchQuery] = useState<string>('')
  const [isModalOpen, setIsModalOpen] = useState<boolean>(false)

  const loadReviews = useCallback(async () => {
    setIsLoading(true)
    setError(null)
    try {
      const data = await fetchReviews(statusFilter === 'all' ? undefined : statusFilter)
      setReviews(data.items)
      setTotalCount(data.total)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load reviews')
      setReviews([])
    } finally {
      setIsLoading(false)
    }
  }, [statusFilter])

  useEffect(() => {
    loadReviews()
  }, [loadReviews])

  const hasActiveReviews = useMemo(() => {
    return reviews.some((r) => r.status === 'queued' || r.status === 'running')
  }, [reviews])

  // T5.5: Poll every 3 seconds while any review is queued or running
  useEffect(() => {
    if (!hasActiveReviews) return

    const timer = setInterval(async () => {
      try {
        const data = await fetchReviews(statusFilter === 'all' ? undefined : statusFilter)
        setReviews(data.items)
        setTotalCount(data.total)
      } catch {
        // Suppress background poll errors
      }
    }, 3000)

    return () => clearInterval(timer)
  }, [hasActiveReviews, statusFilter])

  const filteredReviews = useMemo(() => {
    if (!searchQuery.trim()) return reviews
    const query = searchQuery.toLowerCase()
    return reviews.filter((r) => {
      const title = r.pull_request?.title?.toLowerCase() ?? ''
      const repo = r.pull_request?.repository?.full_name?.toLowerCase() ?? ''
      const num = r.pull_request?.number?.toString() ?? ''
      return title.includes(query) || repo.includes(query) || num.includes(query)
    })
  }, [reviews, searchQuery])

  // Summary Metrics
  const stats = useMemo(() => {
    let completed = 0
    let findings = 0
    let cost = 0.0
    for (const r of reviews) {
      if (r.status === 'completed') completed += 1
      if (r.finding_counts?.total) findings += r.finding_counts.total
      if (r.cost_usd) cost += r.cost_usd
    }
    return {
      total: totalCount,
      completed,
      findings,
      costUsd: cost,
    }
  }, [reviews, totalCount])

  const handleReviewTriggered = (newReview: ReviewItem) => {
    setReviews((prev) => [newReview, ...prev])
    setTotalCount((prev) => prev + 1)
  }

  return (
    <div className="space-y-6 animate-fadeInUp">
      {/* Top Banner & Action */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight flex items-center gap-2" style={{ color: 'var(--cc-fg-default)' }}>
            <span>Pull Request Reviews</span>
          </h1>
          <p className="text-sm mt-1" style={{ color: 'var(--cc-fg-muted)' }}>
            Real-time multi-agent code reviews with specialized reviewers and judge synthesis
          </p>
        </div>
        <div className="flex items-center gap-2.5">
          {hasActiveReviews && (
            <div className="gh-label gh-label-accent flex items-center gap-1.5 animate-pulse text-xs font-medium">
              <span className="w-2 h-2 rounded-full" style={{ backgroundColor: 'var(--cc-accent-fg)' }} />
              <span>Live Updates</span>
            </div>
          )}
          <button
            onClick={loadReviews}
            disabled={isLoading}
            className="glass-btn p-2 disabled:opacity-50"
            title="Refresh reviews"
            aria-label="Refresh reviews"
          >
            <RefreshCw className={`w-4 h-4 ${isLoading ? 'animate-spin' : ''}`} />
          </button>
          <button
            id="trigger-review-btn"
            onClick={() => setIsModalOpen(true)}
            className="flex items-center gap-2 px-4 py-2 text-sm font-semibold rounded-lg text-white transition-all duration-200 hover:shadow-lg active:scale-[0.97] animate-gradientShift"
            style={{ background: 'var(--cc-gradient-primary)' }}
          >
            <Plus className="w-4 h-4" />
            <span>Trigger Review</span>
          </button>
        </div>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {[
          { label: 'Total Reviews', value: stats.total, Icon: GitPullRequest, color: 'var(--cc-accent-fg)' },
          { label: 'Completed', value: stats.completed, Icon: CheckCircle, color: 'var(--cc-success-fg)' },
          { label: 'Findings Detected', value: stats.findings, Icon: ShieldCheck, color: 'var(--cc-warning-fg)' },
          { label: 'Total Cost', value: `$${stats.costUsd.toFixed(4)}`, Icon: Coins, color: 'var(--cc-success-fg)', isGreen: true },
        ].map((kpi, i) => (
          <div
            key={kpi.label}
            className={`glass-card p-4 animate-fadeInUp anim-delay-${i + 1}`}
          >
            <div className="flex items-center justify-between text-xs font-medium mb-1.5" style={{ color: 'var(--cc-fg-muted)' }}>
              <span>{kpi.label}</span>
              <kpi.Icon className="w-4 h-4" style={{ color: kpi.color }} />
            </div>
            <div
              className="text-2xl font-bold"
              style={{ color: kpi.isGreen ? 'var(--cc-success-fg)' : 'var(--cc-fg-default)' }}
            >
              {kpi.value}
            </div>
          </div>
        ))}
      </div>

      {/* Filter and Search Bar */}
      <div
        className="glass-card flex flex-col md:flex-row items-stretch md:items-center justify-between gap-3 p-2.5"
      >
        <div className="flex items-center overflow-x-auto gap-1 py-0.5">
          <Filter className="w-4 h-4 mr-2 shrink-0 ml-1.5" style={{ color: 'var(--cc-fg-subtle)' }} />
          {STATUS_FILTERS.map((f) => (
            <button
              key={f.value}
              onClick={() => setStatusFilter(f.value)}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-all duration-200 whitespace-nowrap ${
                statusFilter === f.value
                  ? 'text-white'
                  : ''
              }`}
              style={{
                background: statusFilter === f.value ? 'var(--cc-accent-emphasis)' : 'transparent',
                color: statusFilter === f.value ? '#fff' : 'var(--cc-fg-muted)',
              }}
              onMouseEnter={(e) => {
                if (statusFilter !== f.value) {
                  e.currentTarget.style.background = 'var(--cc-bg-subtle)'
                  e.currentTarget.style.color = 'var(--cc-fg-default)'
                }
              }}
              onMouseLeave={(e) => {
                if (statusFilter !== f.value) {
                  e.currentTarget.style.background = 'transparent'
                  e.currentTarget.style.color = 'var(--cc-fg-muted)'
                }
              }}
            >
              {f.label}
            </button>
          ))}
        </div>

        <div className="relative min-w-[240px]">
          <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2" style={{ color: 'var(--cc-fg-subtle)' }} />
          <input
            type="text"
            placeholder="Search by repo or PR title..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="glass-input w-full pl-9 pr-3.5 py-1.5 text-xs"
          />
        </div>
      </div>

      {/* Main Content Area: Loading, Error, Empty, or Cards */}
      {isLoading ? (
        <div className="py-16 text-center space-y-3 animate-fadeIn">
          <div
            className="w-8 h-8 mx-auto border-2 border-t-transparent rounded-full animate-spin"
            style={{ borderColor: 'var(--cc-accent-fg)', borderTopColor: 'transparent' }}
          />
          <p className="text-sm" style={{ color: 'var(--cc-fg-muted)' }}>Loading reviews...</p>
        </div>
      ) : error ? (
        <div
          className="py-12 px-6 rounded-xl text-center max-w-md mx-auto space-y-3 animate-scaleIn"
          style={{ background: 'var(--cc-danger-subtle)', border: '1px solid var(--cc-danger-emphasis)' }}
        >
          <AlertCircle className="w-8 h-8 mx-auto" style={{ color: 'var(--cc-danger-fg)' }} />
          <h3 className="text-base font-semibold" style={{ color: 'var(--cc-danger-fg)' }}>Unable to load reviews</h3>
          <p className="text-xs" style={{ color: 'var(--cc-danger-fg)', opacity: 0.8 }}>{error}</p>
          <button
            onClick={loadReviews}
            className="px-4 py-2 text-white text-xs font-semibold rounded-lg transition-colors"
            style={{ background: 'var(--cc-danger-emphasis)' }}
          >
            Try Again
          </button>
        </div>
      ) : filteredReviews.length === 0 ? (
        <div
          className="py-16 px-6 rounded-xl text-center max-w-md mx-auto space-y-3 animate-fadeInUp"
          style={{ border: '2px dashed var(--cc-border-default)' }}
        >
          <div
            className="w-12 h-12 rounded-xl flex items-center justify-center mx-auto"
            style={{ background: 'var(--cc-bg-subtle)', border: '1px solid var(--cc-border-default)', color: 'var(--cc-fg-subtle)' }}
          >
            <FileCode className="w-6 h-6" />
          </div>
          <h3 className="text-base font-semibold" style={{ color: 'var(--cc-fg-default)' }}>No reviews found</h3>
          <p className="text-xs" style={{ color: 'var(--cc-fg-muted)' }}>
            {searchQuery
              ? `No reviews match "${searchQuery}". Try adjusting your search query.`
              : 'Trigger your first GitHub pull request review to evaluate multi-agent performance.'}
          </p>
          {!searchQuery && (
            <button
              onClick={() => setIsModalOpen(true)}
              className="px-4 py-2 text-white text-xs font-semibold rounded-lg shadow-md transition-all duration-200 hover:shadow-lg active:scale-[0.97]"
              style={{ background: 'var(--cc-gradient-primary)' }}
            >
              Trigger First Review
            </button>
          )}
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {filteredReviews.map((review, i) => (
            <div key={review.id} className={`animate-fadeInUp anim-delay-${Math.min(i + 1, 6)}`}>
              <ReviewCard review={review} onSelectReview={onSelectReview} />
            </div>
          ))}
        </div>
      )}

      {/* Trigger Review Modal */}
      <TriggerReviewModal
        isOpen={isModalOpen}
        onClose={() => setIsModalOpen(false)}
        onSuccess={handleReviewTriggered}
      />
    </div>
  )
}
