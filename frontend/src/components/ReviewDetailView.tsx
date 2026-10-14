import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  AlertCircle, ArrowLeft, Clock, Coins, Cpu, ExternalLink,
  FileDiff, Filter, RefreshCw, ShieldAlert, ThumbsUp,
} from 'lucide-react'
import { fetchReviewDetail, fetchReviewDiff } from '../services/api'
import type { FeedbackItem, ReviewDetail } from '../types/review'
import { DiffViewer } from './DiffViewer'
import { FindingCard } from './FindingCard'
import { TraceDrawer } from './TraceDrawer'

interface ReviewDetailViewProps {
  reviewId: number
  onBack: () => void
}

type DetailTab = 'diff' | 'findings' | 'traces'

export function ReviewDetailView({ reviewId, onBack }: ReviewDetailViewProps) {
  const [detail, setDetail] = useState<ReviewDetail | null>(null)
  const [diffText, setDiffText] = useState<string | null>(null)
  const [isLoading, setIsLoading] = useState<boolean>(true)
  const [error, setError] = useState<string | null>(null)
  const [activeTab, setActiveTab] = useState<DetailTab>('diff')
  const [catFilter, setCatFilter] = useState<string>('all')
  const [statusFilter, setStatusFilter] = useState<string>('all')

  const loadDetail = useCallback(async () => {
    setIsLoading(true)
    setError(null)
    try {
      const [reviewData, diffData] = await Promise.all([
        fetchReviewDetail(reviewId),
        fetchReviewDiff(reviewId).catch(() => ({ diff_text: null })),
      ])
      setDetail(reviewData)
      setDiffText(diffData.diff_text ?? reviewData.diff_text ?? null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load review details')
    } finally {
      setIsLoading(false)
    }
  }, [reviewId])

  useEffect(() => {
    loadDetail()
  }, [loadDetail])

  // T5.5: Poll every 3s if review is actively queued or running
  useEffect(() => {
    if (!detail || (detail.status !== 'queued' && detail.status !== 'running')) return
    const timer = setInterval(async () => {
      try {
        const updated = await fetchReviewDetail(reviewId)
        setDetail(updated)
        if (updated.status !== 'queued' && updated.status !== 'running') {
          fetchReviewDiff(reviewId).then((d) => setDiffText(d.diff_text ?? null)).catch(() => {})
        }
      } catch {
        // Ignore background polling errors
      }
    }, 3000)
    return () => clearInterval(timer)
  }, [detail?.status, reviewId])

  const filteredFindings = useMemo(() => {
    if (!detail?.findings) return []
    return detail.findings.filter((f) => {
      const matchCat = catFilter === 'all' || f.category === catFilter
      const matchStatus = statusFilter === 'all' || f.status === statusFilter
      return matchCat && matchStatus
    })
  }, [detail, catFilter, statusFilter])

  const handleFeedbackChange = useCallback((findingId: number, fb: FeedbackItem) => {
    setDetail((prev) => {
      if (!prev) return prev
      return {
        ...prev,
        findings: prev.findings.map((f) => (f.id === findingId ? { ...f, feedback: fb } : f)),
      }
    })
  }, [])

  const feedbackStats = useMemo(() => {
    const list = detail?.findings ?? []
    const reviewed = list.filter((f) => f.feedback)
    const accepted = reviewed.filter((f) => f.feedback?.action === 'accepted').length
    const rate = reviewed.length > 0 ? Math.round((accepted / reviewed.length) * 100) : null
    return { count: reviewed.length, accepted, rate, total: list.length }
  }, [detail])

  const handleAnchorClick = (_file: string, _line: number) => {
    setActiveTab('diff')
  }

  if (isLoading) {
    return (
      <div className="py-24 text-center space-y-3 animate-fadeIn">
        <div
          className="w-8 h-8 mx-auto border-2 border-t-transparent rounded-full animate-spin"
          style={{ borderColor: 'var(--cc-accent-fg)', borderTopColor: 'transparent' }}
        />
        <p className="text-sm" style={{ color: 'var(--cc-fg-muted)' }}>Loading review #{reviewId} details & findings...</p>
      </div>
    )
  }

  if (error || !detail) {
    return (
      <div
        className="py-12 px-6 rounded-xl text-center max-w-md mx-auto space-y-3 animate-scaleIn"
        style={{ background: 'var(--cc-danger-subtle)', border: '1px solid var(--cc-danger-emphasis)' }}
      >
        <AlertCircle className="w-8 h-8 mx-auto" style={{ color: 'var(--cc-danger-fg)' }} />
        <h3 className="text-base font-semibold" style={{ color: 'var(--cc-danger-fg)' }}>Review Not Found</h3>
        <p className="text-xs" style={{ color: 'var(--cc-danger-fg)', opacity: 0.8 }}>{error ?? 'Unable to find review details'}</p>
        <div className="flex items-center justify-center gap-3 pt-2">
          <button onClick={onBack} className="glass-btn px-3.5 py-1.5 text-xs">Back to List</button>
          <button
            onClick={loadDetail}
            className="px-3.5 py-1.5 text-xs text-white rounded-lg font-semibold"
            style={{ background: 'var(--cc-danger-emphasis)' }}
          >
            Retry
          </button>
        </div>
      </div>
    )
  }

  const pr = detail.pull_request
  const findings = detail.findings || []

  const getStatusStyle = () => {
    if (detail.status === 'completed') return { color: 'var(--cc-success-fg)' }
    if (detail.status === 'running' || detail.status === 'queued') return { color: 'var(--cc-warning-fg)' }
    return { color: 'var(--cc-danger-fg)' }
  }

  return (
    <div className="space-y-6 animate-fadeInUp">
      {/* Top Header & Breadcrumb */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4" style={{ borderBottom: '1px solid var(--cc-border-default)' }}>
        <div className="flex items-center gap-3">
          <button
            onClick={onBack}
            className="glass-btn p-2"
            title="Return to reviews list"
          >
            <ArrowLeft className="w-4 h-4" />
          </button>
          <div>
            <div className="flex items-center gap-2 text-xs font-mono" style={{ color: 'var(--cc-fg-muted)' }}>
              <span className="font-semibold" style={{ color: 'var(--cc-fg-default)' }}>
                {pr?.repository?.full_name ?? 'Repository'}
              </span>
              <span>•</span>
              <span>PR #{pr?.number ?? detail.pull_request_id}</span>
              <span>•</span>
              <span
                className="uppercase font-sans font-semibold inline-flex items-center"
                style={getStatusStyle()}
              >
                {(detail.status === 'running' || detail.status === 'queued') && (
                  <span
                    className="w-1.5 h-1.5 rounded-full animate-ping inline-block mr-1.5"
                    style={{ backgroundColor: 'var(--cc-warning-fg)' }}
                  />
                )}
                <span>{detail.status}</span>
              </span>
            </div>
            <h1 className="text-xl font-bold tracking-tight mt-0.5" style={{ color: 'var(--cc-fg-default)' }}>
              {pr?.title ?? `Review Run #${detail.id}`}
            </h1>
          </div>
        </div>

        <div className="flex items-center gap-3">
          {pr?.html_url && (
            <a
              href={pr.html_url}
              target="_blank"
              rel="noopener noreferrer"
              className="glass-btn flex items-center gap-1 px-3 py-1.5 text-xs"
            >
              <span>View on GitHub</span>
              <ExternalLink className="w-3.5 h-3.5" />
            </a>
          )}
          <button
            onClick={loadDetail}
            className="glass-btn p-1.5"
            title="Refresh review"
          >
            <RefreshCw className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* Metric Summary Bar */}
      <div
        className="glass-card grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3 p-3.5 text-xs"
      >
        <div>
          <span className="block mb-0.5" style={{ color: 'var(--cc-fg-muted)' }}>Architecture</span>
          <span className="font-semibold" style={{ color: 'var(--cc-accent-fg)' }}>
            {typeof detail.config?.config === 'string' ? detail.config.config : 'multi_agent_judge'}
          </span>
        </div>
        <div>
          <span className="block mb-0.5" style={{ color: 'var(--cc-fg-muted)' }}>Model</span>
          <span className="font-mono" style={{ color: 'var(--cc-fg-default)' }}>{detail.model}</span>
        </div>
        <div>
          <span className="block mb-0.5" style={{ color: 'var(--cc-fg-muted)' }}>Execution Latency</span>
          <span className="font-mono flex items-center gap-1" style={{ color: 'var(--cc-fg-default)' }}>
            <Clock className="w-3.5 h-3.5" style={{ color: 'var(--cc-fg-subtle)' }} />
            <span>{detail.latency_ms ? `${(detail.latency_ms / 1000).toFixed(2)}s` : '—'}</span>
          </span>
        </div>
        <div>
          <span className="block mb-0.5" style={{ color: 'var(--cc-fg-muted)' }}>Total Cost</span>
          <span className="font-mono flex items-center gap-1" style={{ color: 'var(--cc-success-fg)' }}>
            <Coins className="w-3.5 h-3.5" />
            <span>${(detail.cost_usd ?? 0).toFixed(4)}</span>
          </span>
        </div>
        <div>
          <span className="block mb-0.5" style={{ color: 'var(--cc-fg-muted)' }}>Acceptance Rate</span>
          <span className="font-mono flex items-center gap-1" style={{ color: 'var(--cc-fg-default)' }}>
            <ThumbsUp className="w-3.5 h-3.5" style={{ color: 'var(--cc-accent-fg)' }} />
            {feedbackStats.rate !== null ? (
              <span style={{ color: 'var(--cc-success-fg)' }} className="font-semibold">
                {feedbackStats.rate}% ({feedbackStats.accepted}/{feedbackStats.count})
              </span>
            ) : (
              <span className="text-[11px]" style={{ color: 'var(--cc-fg-subtle)' }}>Unreviewed</span>
            )}
          </span>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex items-center gap-2 pb-2" style={{ borderBottom: '1px solid var(--cc-border-default)' }}>
        {[
          { id: 'diff' as const, label: 'PR Diff & Anchored Findings', icon: FileDiff },
          { id: 'findings' as const, label: `All Findings (${findings.length})`, icon: ShieldAlert },
          { id: 'traces' as const, label: `Pipeline Traces (${detail.traces?.length ?? 0})`, icon: Cpu },
        ].map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            onClick={() => setActiveTab(id)}
            className={`gh-nav-tab flex items-center gap-2 text-xs font-semibold ${activeTab === id ? 'active' : ''}`}
          >
            <Icon className="w-4 h-4" />
            <span>{label}</span>
          </button>
        ))}
      </div>

      {/* Tab 1: Diff & Anchored Findings */}
      {activeTab === 'diff' && <DiffViewer diffText={diffText} findings={findings} />}

      {/* Tab 2: Findings List with Filters */}
      {activeTab === 'findings' && (
        <div className="space-y-5 animate-fadeIn">
          {/* Filter Bar */}
          <div className="glass-card flex flex-wrap items-center justify-between gap-3 p-2.5 text-xs">
            <div className="flex items-center gap-2">
              <Filter className="w-3.5 h-3.5" style={{ color: 'var(--cc-fg-subtle)' }} />
              <span style={{ color: 'var(--cc-fg-muted)' }}>Category:</span>
              {['all', 'security', 'performance', 'maintainability', 'correctness'].map((c) => (
                <button
                  key={c}
                  onClick={() => setCatFilter(c)}
                  className="px-2.5 py-1 rounded text-xs capitalize transition-colors"
                  style={{
                    background: catFilter === c ? 'var(--cc-accent-emphasis)' : 'transparent',
                    color: catFilter === c ? '#fff' : 'var(--cc-fg-muted)',
                  }}
                >
                  {c}
                </button>
              ))}
            </div>

            <div className="flex items-center gap-2">
              <span style={{ color: 'var(--cc-fg-muted)' }}>Status:</span>
              {['all', 'active', 'merged', 'dropped'].map((s) => (
                <button
                  key={s}
                  onClick={() => setStatusFilter(s)}
                  className="px-2.5 py-1 rounded text-xs capitalize transition-colors"
                  style={{
                    background: statusFilter === s ? 'var(--cc-accent-emphasis)' : 'transparent',
                    color: statusFilter === s ? '#fff' : 'var(--cc-fg-muted)',
                  }}
                >
                  {s}
                </button>
              ))}
            </div>
          </div>

          {filteredFindings.length === 0 ? (
            <div
              className="p-12 text-center rounded-xl text-xs"
              style={{ border: '2px dashed var(--cc-border-default)', color: 'var(--cc-fg-muted)' }}
            >
              No findings match the selected filters.
            </div>
          ) : (
            <div className="space-y-4">
              {filteredFindings.map((f, i) => (
                <div key={f.id} className={`animate-fadeInUp anim-delay-${Math.min(i + 1, 6)}`}>
                  <FindingCard
                    finding={f}
                    onAnchorClick={handleAnchorClick}
                    onFeedbackChange={handleFeedbackChange}
                  />
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Tab 3: Execution Graph Traces */}
      {activeTab === 'traces' && <TraceDrawer traces={detail.traces} />}
    </div>
  )
}
