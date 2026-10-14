import { useCallback, useEffect, useState } from 'react'
import {
  Activity,
  CheckCircle2,
  Cpu,
  Moon,
  RefreshCw,
  Scale,
  ShieldAlert,
  Sun,
  Zap,
} from 'lucide-react'
import { EvaluationResultsView } from './components/EvaluationResultsView'
import { ReviewDetailView } from './components/ReviewDetailView'
import { ReviewsListView } from './components/ReviewsListView'
import { fetchHealth } from './services/api'
import { useTheme } from './context/ThemeContext'

interface HealthData {
  status: string
  timestamp: string
}

type TabType = 'reviews' | 'eval' | 'health'

export default function App() {
  const { toggleTheme, isDark } = useTheme()
  const [activeTab, setActiveTab] = useState<TabType>('reviews')
  const [selectedReviewId, setSelectedReviewId] = useState<number | null>(null)
  const [health, setHealth] = useState<HealthData | null>(null)
  const [isHealthLoading, setIsHealthLoading] = useState<boolean>(true)
  const [healthError, setHealthError] = useState<string | null>(null)
  const [latencyMs, setLatencyMs] = useState<number | null>(null)

  const checkHealth = useCallback(async () => {
    setIsHealthLoading(true)
    setHealthError(null)
    const startTime = performance.now()
    try {
      const data = await fetchHealth()
      const duration = Math.round(performance.now() - startTime)
      setLatencyMs(duration)
      setHealth(data)
    } catch (err) {
      setHealthError(err instanceof Error ? err.message : 'API offline')
      setHealth(null)
    } finally {
      setIsHealthLoading(false)
    }
  }, [])

  useEffect(() => {
    checkHealth()
  }, [checkHealth])

  const handleReviewsTabClick = () => {
    setActiveTab('reviews')
    setSelectedReviewId(null)
  }

  return (
    <div
      className="min-h-screen flex flex-col transition-colors duration-300"
      style={{ backgroundColor: 'var(--cc-bg-canvas)', color: 'var(--cc-fg-default)' }}
    >
      {/* ======== GitHub-Style Header ======== */}
      <header className="gh-header sticky top-0 z-40">
        <div className="max-w-[1280px] mx-auto px-4 sm:px-6 lg:px-8">
          <div className="h-16 flex items-center justify-between">
            {/* Left: Logo + Nav */}
            <div className="flex items-center gap-6">
              {/* Logo */}
              <div
                onClick={handleReviewsTabClick}
                className="flex items-center gap-3 cursor-pointer select-none group"
              >
                <div
                  className="w-9 h-9 rounded-lg flex items-center justify-center text-white font-bold animate-gradientShift"
                  style={{ background: 'var(--cc-gradient-primary)' }}
                >
                  <Scale className="w-5 h-5" />
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-lg font-bold tracking-tight" style={{ color: 'var(--cc-fg-default)' }}>
                    CodeCourt
                  </span>
                  <span
                    className="gh-label gh-label-accent text-[11px]"
                  >
                    Phase 5
                  </span>
                </div>
              </div>

              {/* Navigation Tabs */}
              <nav className="hidden sm:flex items-center gap-1">
                <button
                  onClick={handleReviewsTabClick}
                  className={`gh-nav-tab ${activeTab === 'reviews' ? 'active' : ''}`}
                >
                  Reviews
                </button>
                <button
                  onClick={() => {
                    setActiveTab('eval')
                    setSelectedReviewId(null)
                  }}
                  className={`gh-nav-tab ${activeTab === 'eval' ? 'active' : ''}`}
                >
                  Benchmarks
                </button>
                <button
                  onClick={() => setActiveTab('health')}
                  className={`gh-nav-tab ${activeTab === 'health' ? 'active' : ''}`}
                >
                  System
                </button>
              </nav>
            </div>

            {/* Right: Status + Theme Toggle */}
            <div className="flex items-center gap-3">
              {/* API Status Indicator */}
              <div
                className="gh-label flex items-center gap-2 text-xs font-medium"
                style={{
                  background: isHealthLoading
                    ? 'var(--cc-warning-subtle)'
                    : health?.status === 'healthy'
                    ? 'var(--cc-success-subtle)'
                    : 'var(--cc-danger-subtle)',
                  color: isHealthLoading
                    ? 'var(--cc-warning-fg)'
                    : health?.status === 'healthy'
                    ? 'var(--cc-success-fg)'
                    : 'var(--cc-danger-fg)',
                }}
              >
                <span
                  className={`w-2 h-2 rounded-full ${
                    isHealthLoading
                      ? 'animate-ping'
                      : health?.status === 'healthy'
                      ? 'animate-pulse'
                      : ''
                  }`}
                  style={{
                    backgroundColor: isHealthLoading
                      ? 'var(--cc-warning-fg)'
                      : health?.status === 'healthy'
                      ? 'var(--cc-success-fg)'
                      : 'var(--cc-danger-fg)',
                  }}
                />
                <span>
                  {isHealthLoading ? 'Pinging...' : health?.status === 'healthy' ? 'API Online' : 'Offline'}
                </span>
              </div>

              {/* Refresh health */}
              <button
                onClick={checkHealth}
                disabled={isHealthLoading}
                className="glass-btn p-2 disabled:opacity-50"
                title="Refresh health status"
                aria-label="Refresh health status"
              >
                <RefreshCw className={`w-4 h-4 ${isHealthLoading ? 'animate-spin' : ''}`} />
              </button>

              {/* Theme Toggle */}
              <button
                onClick={toggleTheme}
                className="glass-btn p-2 group"
                title={`Switch to ${isDark ? 'light' : 'dark'} theme`}
                aria-label="Toggle theme"
              >
                <div className="relative w-4 h-4">
                  <Sun
                    className={`w-4 h-4 absolute inset-0 transition-all duration-300 ${
                      isDark ? 'opacity-0 rotate-90 scale-0' : 'opacity-100 rotate-0 scale-100'
                    }`}
                    style={{ color: 'var(--cc-warning-fg)' }}
                  />
                  <Moon
                    className={`w-4 h-4 absolute inset-0 transition-all duration-300 ${
                      isDark ? 'opacity-100 rotate-0 scale-100' : 'opacity-0 -rotate-90 scale-0'
                    }`}
                    style={{ color: 'var(--cc-accent-fg)' }}
                  />
                </div>
              </button>
            </div>
          </div>

          {/* Mobile nav */}
          <nav className="sm:hidden flex items-center gap-1 pb-2 overflow-x-auto">
            <button
              onClick={handleReviewsTabClick}
              className={`gh-nav-tab text-sm ${activeTab === 'reviews' ? 'active' : ''}`}
            >
              Reviews
            </button>
            <button
              onClick={() => { setActiveTab('eval'); setSelectedReviewId(null) }}
              className={`gh-nav-tab text-sm ${activeTab === 'eval' ? 'active' : ''}`}
            >
              Benchmarks
            </button>
            <button
              onClick={() => setActiveTab('health')}
              className={`gh-nav-tab text-sm ${activeTab === 'health' ? 'active' : ''}`}
            >
              System
            </button>
          </nav>
        </div>
      </header>

      {/* ======== Main Content ======== */}
      <main className="flex-1 max-w-[1280px] w-full mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {activeTab === 'reviews' ? (
          selectedReviewId !== null ? (
            <ReviewDetailView
              reviewId={selectedReviewId}
              onBack={() => setSelectedReviewId(null)}
            />
          ) : (
            <ReviewsListView onSelectReview={(id) => setSelectedReviewId(id)} />
          )
        ) : activeTab === 'eval' ? (
          <EvaluationResultsView />
        ) : (
          /* ======== Health / System Tab ======== */
          <div className="space-y-6 animate-fadeInUp">
            {/* Health Card */}
            <div className="glass-card p-6">
              <div className="flex items-center justify-between pb-4 mb-6" style={{ borderBottom: '1px solid var(--cc-border-default)' }}>
                <div className="flex items-center gap-2">
                  <Activity className="w-5 h-5" style={{ color: 'var(--cc-accent-fg)' }} />
                  <h2 className="text-lg font-semibold" style={{ color: 'var(--cc-fg-default)' }}>Backend API Health</h2>
                </div>
                <span className="text-xs font-mono" style={{ color: 'var(--cc-fg-subtle)' }}>GET /api/health</span>
              </div>

              {healthError ? (
                <div
                  className="rounded-lg p-4 text-xs"
                  style={{ background: 'var(--cc-danger-subtle)', color: 'var(--cc-danger-fg)', border: '1px solid var(--cc-danger-emphasis)' }}
                >
                  {healthError}
                </div>
              ) : health ? (
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                  <div className="p-4 rounded-lg" style={{ background: 'var(--cc-bg-subtle)', border: '1px solid var(--cc-border-default)' }}>
                    <span className="text-xs font-medium" style={{ color: 'var(--cc-fg-muted)' }}>Status</span>
                    <div className="mt-1 flex items-center gap-2">
                      <CheckCircle2 className="w-4 h-4" style={{ color: 'var(--cc-success-fg)' }} />
                      <span className="text-lg font-bold uppercase tracking-wide" style={{ color: 'var(--cc-success-fg)' }}>
                        {health.status}
                      </span>
                    </div>
                  </div>
                  <div className="p-4 rounded-lg" style={{ background: 'var(--cc-bg-subtle)', border: '1px solid var(--cc-border-default)' }}>
                    <span className="text-xs font-medium" style={{ color: 'var(--cc-fg-muted)' }}>Response Latency</span>
                    <p className="mt-1 text-lg font-bold font-mono" style={{ color: 'var(--cc-fg-default)' }}>
                      {latencyMs !== null ? `${latencyMs} ms` : '—'}
                    </p>
                  </div>
                  <div className="p-4 rounded-lg" style={{ background: 'var(--cc-bg-subtle)', border: '1px solid var(--cc-border-default)' }}>
                    <span className="text-xs font-medium" style={{ color: 'var(--cc-fg-muted)' }}>Server Timestamp</span>
                    <p className="mt-1 text-sm font-mono truncate" style={{ color: 'var(--cc-fg-muted)' }}>{health.timestamp}</p>
                  </div>
                </div>
              ) : null}
            </div>

            {/* Architecture Overview Cards */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              {[
                {
                  icon: ShieldAlert,
                  title: 'Security Reviewer',
                  desc: 'Detects SQL injection, secret exposure, auth flaws, and unsafe deserialization.',
                  gradient: 'var(--cc-gradient-danger)',
                  color: 'var(--cc-danger-fg)',
                  subtle: 'var(--cc-danger-subtle)',
                },
                {
                  icon: Zap,
                  title: 'Performance Reviewer',
                  desc: 'Flags N+1 queries, unindexed lookups, memory leaks, and algorithmic bottlenecks.',
                  gradient: 'linear-gradient(135deg, var(--cc-warning-fg) 0%, #e3b341 100%)',
                  color: 'var(--cc-warning-fg)',
                  subtle: 'var(--cc-warning-subtle)',
                },
                {
                  icon: Cpu,
                  title: 'Maintainability Reviewer',
                  desc: 'Identifies API breaking changes, cyclomatic complexity, coupling, and dead code.',
                  gradient: 'var(--cc-gradient-primary)',
                  color: 'var(--cc-accent-fg)',
                  subtle: 'var(--cc-accent-subtle)',
                },
              ].map((card, i) => (
                <div
                  key={card.title}
                  className={`glass-card p-5 space-y-3 animate-fadeInUp anim-delay-${i + 1}`}
                >
                  <div
                    className="w-9 h-9 rounded-lg flex items-center justify-center animate-float"
                    style={{ background: card.subtle, color: card.color, animationDelay: `${i * 0.5}s` }}
                  >
                    <card.icon className="w-5 h-5" />
                  </div>
                  <h3 className="font-semibold text-sm" style={{ color: 'var(--cc-fg-default)' }}>{card.title}</h3>
                  <p className="text-xs leading-relaxed" style={{ color: 'var(--cc-fg-muted)' }}>
                    {card.desc}
                  </p>
                </div>
              ))}
            </div>
          </div>
        )}
      </main>

      {/* ======== Footer ======== */}
      <footer
        className="py-4 text-center text-xs transition-colors duration-300"
        style={{ borderTop: '1px solid var(--cc-border-default)', color: 'var(--cc-fg-subtle)' }}
      >
        CodeCourt &middot; Multi-Agent Code Review &middot; FastAPI, LangGraph & React
      </footer>
    </div>
  )
}
