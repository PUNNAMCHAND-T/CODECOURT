import { useState } from 'react'
import {
  AlertOctagon,
  AlertTriangle,
  Check,
  CheckCircle,
  FileCode,
  Info,
  Loader2,
  ShieldAlert,
  Sparkles,
  ThumbsDown,
  ThumbsUp,
  UserCheck,
  X,
  XCircle,
} from 'lucide-react'
import { submitFindingFeedback } from '../services/api'
import type {
  FeedbackItem,
  FindingCategory,
  FindingItem,
  FindingSeverity,
} from '../types/review'

interface FindingCardProps {
  finding: FindingItem
  onAnchorClick?: (file: string, line: number) => void
  onFeedbackChange?: (findingId: number, feedback: FeedbackItem) => void
}

function getSeverityBadge(sev: FindingSeverity) {
  switch (sev) {
    case 'critical':
      return { label: 'Critical', bgVar: 'var(--cc-danger-subtle)', fgVar: 'var(--cc-danger-fg)', icon: AlertOctagon }
    case 'high':
      return { label: 'High', bgVar: 'var(--cc-danger-subtle)', fgVar: 'var(--cc-danger-fg)', icon: ShieldAlert }
    case 'medium':
      return { label: 'Medium', bgVar: 'var(--cc-warning-subtle)', fgVar: 'var(--cc-warning-fg)', icon: AlertTriangle }
    case 'low':
      return { label: 'Low', bgVar: 'var(--cc-accent-subtle)', fgVar: 'var(--cc-accent-fg)', icon: Info }
  }
}

function getCategoryStyle(cat: FindingCategory) {
  switch (cat) {
    case 'security':
      return { bg: 'var(--cc-danger-subtle)', fg: 'var(--cc-danger-fg)' }
    case 'performance':
      return { bg: 'var(--cc-warning-subtle)', fg: 'var(--cc-warning-fg)' }
    case 'maintainability':
      return { bg: 'var(--cc-accent-subtle)', fg: 'var(--cc-accent-fg)' }
    case 'correctness':
      return { bg: 'var(--cc-done-subtle)', fg: 'var(--cc-done-fg)' }
  }
}

export function FindingCard({ finding, onAnchorClick, onFeedbackChange }: FindingCardProps) {
  const [feedback, setFeedback] = useState<FeedbackItem | null | undefined>(finding.feedback)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [showReasonBox, setShowReasonBox] = useState(false)
  const [pendingAction, setPendingAction] = useState<'accepted' | 'dismissed' | null>(null)
  const [reasonText, setReasonText] = useState('')

  const sevInfo = getSeverityBadge(finding.severity)
  const SevIcon = sevInfo.icon
  const catStyle = getCategoryStyle(finding.category)

  const handleActionClick = async (action: 'accepted' | 'dismissed') => {
    if (action === 'dismissed' && !showReasonBox && !feedback) {
      setPendingAction('dismissed')
      setShowReasonBox(true)
      return
    }
    await sendFeedback(action, reasonText)
  }

  const sendFeedback = async (action: 'accepted' | 'dismissed', reason?: string) => {
    setIsSubmitting(true)
    try {
      const updated = await submitFindingFeedback(finding.id, action, reason || undefined)
      setFeedback(updated)
      setShowReasonBox(false)
      setPendingAction(null)
      setReasonText('')
      onFeedbackChange?.(finding.id, updated)
    } finally {
      setIsSubmitting(false)
    }
  }

  const cardBorderStyle = feedback?.action === 'accepted'
    ? { border: '1px solid var(--cc-success-fg)', opacity: 1 }
    : feedback?.action === 'dismissed'
    ? { border: '1px solid var(--cc-border-default)', opacity: 0.6 }
    : { border: '1px solid var(--cc-border-default)' }

  return (
    <div
      id={`finding-${finding.id}`}
      className="glass-card p-5 space-y-4 transition-all"
      style={cardBorderStyle}
    >
      {/* Header: Severity, Category, File:Lines, Status & Feedback Badge */}
      <div className="flex flex-wrap items-center justify-between gap-2.5">
        <div className="flex flex-wrap items-center gap-2 text-xs">
          <span
            className="gh-label font-semibold"
            style={{ background: sevInfo.bgVar, color: sevInfo.fgVar }}
          >
            <SevIcon className="w-3.5 h-3.5" />
            <span>{sevInfo.label}</span>
          </span>
          <span
            className="gh-label font-medium capitalize"
            style={{ background: catStyle.bg, color: catStyle.fg }}
          >
            {finding.category}
          </span>
          <span
            className="gh-label gh-label-muted font-mono text-[11px]"
          >
            <UserCheck className="w-3 h-3" />
            <span>{finding.agent}</span>
          </span>
        </div>

        <div className="flex items-center gap-2 text-xs">
          {feedback?.action === 'accepted' && (
            <span className="gh-label gh-label-success text-[11px] font-semibold">
              <Check className="w-3.5 h-3.5" />
              <span>Accepted</span>
            </span>
          )}
          {feedback?.action === 'dismissed' && (
            <span className="gh-label gh-label-danger text-[11px] font-semibold">
              <X className="w-3.5 h-3.5" />
              <span>Dismissed</span>
            </span>
          )}
          {finding.status === 'merged' && (
            <span className="gh-label gh-label-accent text-[11px] font-medium">
              <CheckCircle className="w-3 h-3" />
              <span>Merged</span>
            </span>
          )}
          {finding.status === 'dropped' && (
            <span className="gh-label gh-label-muted text-[11px] font-medium">
              <XCircle className="w-3 h-3" />
              <span>Dropped</span>
            </span>
          )}
          <span className="font-mono text-[11px]" style={{ color: 'var(--cc-fg-muted)' }}>
            Score: {(finding.confidence * 100).toFixed(0)}%
          </span>
        </div>
      </div>

      {/* Title & File Anchor */}
      <div>
        <div className="flex items-start justify-between gap-2">
          <h4 className="text-base font-semibold tracking-tight" style={{ color: 'var(--cc-fg-default)' }}>
            {finding.title}
          </h4>
          <button
            onClick={() => onAnchorClick?.(finding.file, finding.line_start)}
            className="glass-btn flex items-center gap-1 font-mono text-xs shrink-0 px-2.5 py-1"
            style={{ color: 'var(--cc-accent-fg)' }}
            title="Jump to diff location"
          >
            <FileCode className="w-3.5 h-3.5" />
            <span>{finding.file}:{finding.line_start === finding.line_end ? finding.line_start : `${finding.line_start}-${finding.line_end}`}</span>
          </button>
        </div>
        <p className="text-xs mt-2 leading-relaxed" style={{ color: 'var(--cc-fg-muted)' }}>{finding.explanation}</p>
      </div>

      {/* Quoted Evidence Snippet */}
      {finding.evidence && (
        <div className="space-y-1.5">
          <span className="text-[11px] font-medium uppercase tracking-wider" style={{ color: 'var(--cc-fg-muted)' }}>
            Evidence Snippet
          </span>
          <pre
            className="p-3 rounded-lg text-xs font-mono overflow-x-auto whitespace-pre-wrap leading-relaxed"
            style={{ background: 'var(--cc-bg-inset)', border: '1px solid var(--cc-border-default)', color: 'var(--cc-fg-muted)' }}
          >
            {finding.evidence}
          </pre>
        </div>
      )}

      {/* Suggested Fix */}
      {finding.suggested_fix && (
        <div className="space-y-1.5">
          <div className="flex items-center gap-1.5 text-[11px] font-medium uppercase tracking-wider" style={{ color: 'var(--cc-success-fg)' }}>
            <Sparkles className="w-3.5 h-3.5" />
            <span>Suggested Remediation</span>
          </div>
          <pre
            className="p-3 rounded-lg text-xs font-mono overflow-x-auto whitespace-pre-wrap leading-relaxed"
            style={{ background: 'var(--cc-success-subtle)', border: '1px solid var(--cc-success-fg)', color: 'var(--cc-success-fg)' }}
          >
            {finding.suggested_fix}
          </pre>
        </div>
      )}

      {/* Judge Decision Rationale */}
      {(finding.decision_reason || finding.drop_reason || (finding.merged_from && finding.merged_from.length > 0)) && (
        <div
          className="p-3 rounded-lg space-y-1 text-xs"
          style={{ background: 'var(--cc-bg-subtle)', border: '1px solid var(--cc-border-default)' }}
        >
          <span className="text-[11px] font-semibold uppercase tracking-wider" style={{ color: 'var(--cc-accent-fg)' }}>
            Judge Node Synthesis:
          </span>
          {finding.decision_reason && (
            <p style={{ color: 'var(--cc-fg-muted)' }}>
              <strong style={{ color: 'var(--cc-fg-subtle)' }}>Reason:</strong> {finding.decision_reason}
            </p>
          )}
          {finding.drop_reason && (
            <p style={{ color: 'var(--cc-danger-fg)' }}>
              <strong style={{ color: 'var(--cc-fg-subtle)' }}>Drop:</strong> {finding.drop_reason}
            </p>
          )}
          {finding.merged_from && finding.merged_from.length > 0 && (
            <p className="font-mono text-[11px]" style={{ color: 'var(--cc-fg-muted)' }}>
              Origins: {finding.merged_from.join(', ')}
            </p>
          )}
        </div>
      )}

      {/* Human Feedback Actions & Dismiss Rationale Box */}
      <div className="pt-3 flex flex-col gap-2.5" style={{ borderTop: '1px solid var(--cc-border-default)' }}>
        <div className="flex items-center justify-between text-xs">
          <span className="text-[11px] font-medium" style={{ color: 'var(--cc-fg-muted)' }}>Developer Feedback:</span>
          <div className="flex items-center gap-2">
            <button
              onClick={() => handleActionClick('accepted')}
              disabled={isSubmitting}
              className="glass-btn flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium transition-all"
              style={{
                background: feedback?.action === 'accepted' ? 'var(--cc-success-emphasis)' : undefined,
                color: feedback?.action === 'accepted' ? '#fff' : 'var(--cc-fg-default)',
                borderColor: feedback?.action === 'accepted' ? 'var(--cc-success-emphasis)' : undefined,
              }}
            >
              <ThumbsUp className="w-3.5 h-3.5" />
              <span>Accept</span>
            </button>
            <button
              onClick={() => handleActionClick('dismissed')}
              disabled={isSubmitting}
              className="glass-btn flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium transition-all"
              style={{
                background: feedback?.action === 'dismissed' ? 'var(--cc-danger-emphasis)' : undefined,
                color: feedback?.action === 'dismissed' ? '#fff' : 'var(--cc-fg-default)',
                borderColor: feedback?.action === 'dismissed' ? 'var(--cc-danger-emphasis)' : undefined,
              }}
            >
              <ThumbsDown className="w-3.5 h-3.5" />
              <span>Dismiss</span>
            </button>
          </div>
        </div>

        {/* Expandable Reason Input */}
        {showReasonBox && (
          <div
            className="p-3 rounded-lg space-y-2 animate-fadeInUp"
            style={{ background: 'var(--cc-bg-subtle)', border: '1px solid var(--cc-border-default)' }}
          >
            <div className="flex items-center justify-between text-[11px]" style={{ color: 'var(--cc-fg-muted)' }}>
              <span>Why is this finding being {pendingAction ?? 'reviewed'}?</span>
              <button onClick={() => setShowReasonBox(false)} style={{ color: 'var(--cc-fg-subtle)' }}>
                <X className="w-3.5 h-3.5" />
              </button>
            </div>
            <div className="flex flex-wrap gap-1.5">
              {['False positive', 'Already addressed', 'Acceptable risk', 'Good catch'].map((preset) => (
                <button
                  key={preset}
                  onClick={() => setReasonText(preset)}
                  className="glass-btn px-2 py-0.5 text-[10px]"
                >
                  {preset}
                </button>
              ))}
            </div>
            <div className="flex items-center gap-2">
              <input
                type="text"
                placeholder="Optional explanation..."
                value={reasonText}
                onChange={(e) => setReasonText(e.target.value)}
                className="glass-input flex-1 text-xs"
              />
              <button
                onClick={() => sendFeedback(pendingAction ?? 'dismissed', reasonText)}
                disabled={isSubmitting}
                className="px-3 py-1 text-white text-xs font-semibold rounded flex items-center gap-1 transition-all"
                style={{ background: 'var(--cc-accent-emphasis)' }}
              >
                {isSubmitting && <Loader2 className="w-3 h-3 animate-spin" />}
                <span>Save</span>
              </button>
            </div>
          </div>
        )}

        {feedback?.reason && (
          <p className="text-[11px] italic" style={{ color: 'var(--cc-fg-muted)' }}>
            Feedback Note: "{feedback.reason}"
          </p>
        )}
      </div>
    </div>
  )
}
