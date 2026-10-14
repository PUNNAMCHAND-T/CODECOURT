import { useState, type FormEvent } from 'react'
import { AlertCircle, GitPullRequest, Loader2, X } from 'lucide-react'
import { triggerReview } from '../services/api'
import type { ReviewConfig, ReviewItem } from '../types/review'

interface TriggerReviewModalProps {
  isOpen: boolean
  onClose: () => void
  onSuccess: (review: ReviewItem) => void
}

export function TriggerReviewModal({ isOpen, onClose, onSuccess }: TriggerReviewModalProps) {
  const [prUrl, setPrUrl] = useState('')
  const [config, setConfig] = useState<ReviewConfig>('multi_agent_judge')
  const [model, setModel] = useState('gemini-3.8-flash')
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [errorMessage, setErrorMessage] = useState<string | null>(null)

  if (!isOpen) return null

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setErrorMessage(null)

    const trimmedUrl = prUrl.trim()
    if (!trimmedUrl.startsWith('https://github.com/')) {
      setErrorMessage('Please enter a valid GitHub pull request URL (e.g. https://github.com/owner/repo/pull/123)')
      return
    }

    setIsSubmitting(true)
    try {
      const review = await triggerReview({
        pr_url: trimmedUrl,
        config,
        model,
      })
      setPrUrl('')
      onSuccess(review)
      onClose()
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : 'Failed to trigger code review')
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 animate-fadeIn"
      style={{ backgroundColor: 'rgba(0, 0, 0, 0.6)', backdropFilter: 'blur(8px)' }}
      role="dialog"
      aria-modal="true"
      aria-labelledby="modal-title"
    >
      <div
        className="glass-card max-w-lg w-full p-6 relative animate-scaleIn"
        style={{ background: 'var(--cc-bg-default)', border: '1px solid var(--cc-border-default)' }}
      >
        <button
          onClick={onClose}
          disabled={isSubmitting}
          className="absolute top-4 right-4 p-1.5 rounded-lg transition-colors"
          style={{ color: 'var(--cc-fg-muted)' }}
          onMouseEnter={(e) => { e.currentTarget.style.color = 'var(--cc-fg-default)'; e.currentTarget.style.background = 'var(--cc-bg-subtle)' }}
          onMouseLeave={(e) => { e.currentTarget.style.color = 'var(--cc-fg-muted)'; e.currentTarget.style.background = 'transparent' }}
          aria-label="Close dialog"
        >
          <X className="w-5 h-5" />
        </button>

        <div className="flex items-center gap-3 mb-5">
          <div
            className="w-10 h-10 rounded-lg flex items-center justify-center"
            style={{ background: 'var(--cc-accent-subtle)', color: 'var(--cc-accent-fg)' }}
          >
            <GitPullRequest className="w-5 h-5" />
          </div>
          <div>
            <h2 id="modal-title" className="text-lg font-bold" style={{ color: 'var(--cc-fg-default)' }}>Trigger Code Review</h2>
            <p className="text-xs" style={{ color: 'var(--cc-fg-muted)' }}>Dispatch a multi-agent or baseline review on a GitHub PR</p>
          </div>
        </div>

        {errorMessage && (
          <div
            className="mb-4 p-3 rounded-lg flex items-start gap-2.5 text-xs"
            style={{ background: 'var(--cc-danger-subtle)', color: 'var(--cc-danger-fg)', border: '1px solid var(--cc-danger-emphasis)' }}
          >
            <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
            <div className="break-all">{errorMessage}</div>
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label htmlFor="pr-url-input" className="block text-xs font-medium mb-1.5" style={{ color: 'var(--cc-fg-default)' }}>
              GitHub Pull Request URL <span style={{ color: 'var(--cc-accent-fg)' }}>*</span>
            </label>
            <input
              id="pr-url-input"
              type="url"
              required
              placeholder="https://github.com/owner/repository/pull/42"
              value={prUrl}
              onChange={(e) => setPrUrl(e.target.value)}
              disabled={isSubmitting}
              className="glass-input w-full text-sm disabled:opacity-50"
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label htmlFor="config-select" className="block text-xs font-medium mb-1.5" style={{ color: 'var(--cc-fg-default)' }}>
                Architecture Config
              </label>
              <select
                id="config-select"
                value={config}
                onChange={(e) => setConfig(e.target.value as ReviewConfig)}
                disabled={isSubmitting}
                className="glass-input w-full text-xs"
              >
                <option value="multi_agent_judge">Multi-Agent + Judge</option>
                <option value="single_agent">Single Agent (Baseline)</option>
                <option value="multi_agent_no_judge">Multi-Agent No Judge (Ablation)</option>
              </select>
            </div>

            <div>
              <label htmlFor="model-select" className="block text-xs font-medium mb-1.5" style={{ color: 'var(--cc-fg-default)' }}>
                LLM Provider Model
              </label>
              <select
                id="model-select"
                value={model}
                onChange={(e) => setModel(e.target.value)}
                disabled={isSubmitting}
                className="glass-input w-full text-xs"
              >
                <option value="gemini-3.8-flash">Gemini 3.8 Flash</option>
                <option value="fake-llm">Fake LLM (Test mode)</option>
              </select>
            </div>
          </div>

          <div className="pt-2 flex items-center justify-end gap-2.5">
            <button
              type="button"
              onClick={onClose}
              disabled={isSubmitting}
              className="glass-btn px-4 py-2 text-xs font-medium"
            >
              Cancel
            </button>
            <button
              id="submit-trigger-btn"
              type="submit"
              disabled={isSubmitting || !prUrl.trim()}
              className="px-4 py-2 text-xs font-semibold rounded-lg text-white flex items-center gap-2 disabled:opacity-50 transition-all duration-200 hover:shadow-lg active:scale-[0.97]"
              style={{ background: 'var(--cc-gradient-primary)' }}
            >
              {isSubmitting && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
              <span>{isSubmitting ? 'Dispatching...' : 'Start Review'}</span>
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
