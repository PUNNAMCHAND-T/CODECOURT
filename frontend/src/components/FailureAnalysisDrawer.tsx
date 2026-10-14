import { Bug, Code2, ShieldAlert } from 'lucide-react'
import type { FailureAnalysisData } from '../types/eval'

interface FailureAnalysisDrawerProps {
  data: FailureAnalysisData
}

const FAILURE_LABELS: Record<string, { label: string; desc: string; color: string; barColor: string }> = {
  clean_pr_false_alarm: {
    label: 'Clean PR False Alarm',
    desc: 'Spurious comments hallucinated on benign control PRs',
    color: 'var(--cc-danger-fg)',
    barColor: 'var(--cc-danger-emphasis)',
  },
  missed_injected_bug: {
    label: 'Missed Injected Bug',
    desc: 'False negative where model produced zero matching findings',
    color: 'var(--cc-warning-fg)',
    barColor: 'var(--cc-warning-emphasis)',
  },
  wrong_line_drift: {
    label: 'Localization Drift',
    desc: 'Correct bug flagged within 3 lines of ground truth interval',
    color: 'var(--cc-accent-fg)',
    barColor: 'var(--cc-accent-emphasis)',
  },
  category_mismatch: {
    label: 'Category Mismatch',
    desc: 'Correct line range flagged under wrong bug taxonomy',
    color: 'var(--cc-done-fg)',
    barColor: 'var(--cc-done-emphasis)',
  },
  extra_duplicate_noise: {
    label: 'Duplicate Noise',
    desc: 'Redundant findings emitted by multiple parallel reviewers',
    color: 'var(--cc-warning-fg)',
    barColor: '#d97706',
  },
  ungrounded_extra_finding: {
    label: 'Ungrounded Finding',
    desc: 'Extraneous comment with no relation to injected bug',
    color: '#ec4899',
    barColor: '#db2777',
  },
}

export function FailureAnalysisDrawer({ data }: FailureAnalysisDrawerProps) {
  const total = Math.max(1, data.total_failures)

  return (
    <div
      className="glass-card space-y-6 p-5 rounded-xl animate-fadeIn"
      style={{
        background: 'var(--cc-glass-bg)',
        border: '1px solid var(--cc-border-default)',
        boxShadow: 'var(--cc-glass-shadow)',
        backdropFilter: 'blur(var(--cc-glass-blur))',
      }}
    >
      <div
        className="flex flex-wrap items-center justify-between gap-4 pb-4"
        style={{ borderBottom: '1px solid var(--cc-border-muted)' }}
      >
        <div>
          <h3
            className="text-sm font-semibold flex items-center space-x-2"
            style={{ color: 'var(--cc-fg-default)' }}
          >
            <ShieldAlert className="w-4 h-4" style={{ color: 'var(--cc-danger-fg)' }} />
            <span>Quantitative Failure Taxonomy Analysis</span>
          </h3>
          <p className="text-xs mt-0.5" style={{ color: 'var(--cc-fg-muted)' }}>
            Classified error distributions across {data.total_evaluated_cases} evaluated PR cases.
          </p>
        </div>
        <div className="flex items-center space-x-3 text-xs font-mono">
          <div
            className="px-3 py-1.5 rounded-lg font-medium"
            style={{
              background: 'var(--cc-bg-subtle)',
              border: '1px solid var(--cc-border-default)',
              color: 'var(--cc-fg-muted)',
            }}
          >
            <span>Total Evaluations: </span>
            <span className="font-semibold" style={{ color: 'var(--cc-fg-default)' }}>
              {data.total_evaluated_cases}
            </span>
          </div>
          <div
            className="px-3 py-1.5 rounded-lg font-medium"
            style={{
              background: 'var(--cc-danger-subtle)',
              border: '1px solid var(--cc-border-default)',
              color: 'var(--cc-danger-fg)',
            }}
          >
            <span>Total Missed/Failed: </span>
            <span className="font-semibold">{data.total_failures}</span>
          </div>
        </div>
      </div>

      {/* Failure Modes Breakdown */}
      <div className="space-y-3">
        <h4
          className="text-xs font-semibold uppercase tracking-wider"
          style={{ color: 'var(--cc-fg-muted)' }}
        >
          Failure Mode Distribution
        </h4>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-xs">
          {Object.entries(data.by_failure_mode).map(([key, count]) => {
            const meta = FAILURE_LABELS[key] || {
              label: key,
              desc: '',
              color: 'var(--cc-fg-muted)',
              barColor: 'var(--cc-accent-emphasis)',
            }
            const pct = Math.round((count / total) * 100)

            return (
              <div
                key={key}
                className="p-3.5 rounded-lg space-y-2 transition-all hover:translate-y-[-1px]"
                style={{
                  background: 'var(--cc-bg-subtle)',
                  border: '1px solid var(--cc-border-muted)',
                }}
              >
                <div className="flex items-center justify-between">
                  <span className="font-semibold" style={{ color: 'var(--cc-fg-default)' }}>
                    {meta.label}
                  </span>
                  <span className="font-mono text-xs font-medium" style={{ color: 'var(--cc-fg-muted)' }}>
                    {count} ({pct}%)
                  </span>
                </div>
                <div
                  className="w-full rounded-full h-1.5 overflow-hidden"
                  style={{ background: 'var(--cc-border-subtle)' }}
                >
                  <div
                    className="h-1.5 rounded-full transition-all duration-500 ease-out"
                    style={{
                      width: `${pct}%`,
                      background: meta.barColor,
                    }}
                  />
                </div>
                <p className="text-[11px] leading-tight" style={{ color: 'var(--cc-fg-subtle)' }}>
                  {meta.desc}
                </p>
              </div>
            )
          })}
        </div>
      </div>

      {/* Category and Language Distributions */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 pt-2">
        {/* By Category */}
        <div
          className="p-4 rounded-lg space-y-2 text-xs"
          style={{
            background: 'var(--cc-bg-subtle)',
            border: '1px solid var(--cc-border-muted)',
          }}
        >
          <div
            className="flex items-center space-x-2 font-semibold mb-2"
            style={{ color: 'var(--cc-fg-default)' }}
          >
            <Bug className="w-3.5 h-3.5" style={{ color: 'var(--cc-warning-fg)' }} />
            <span>Missed Bugs by Category</span>
          </div>
          {Object.entries(data.by_category).map(([cat, count]) => (
            <div
              key={cat}
              className="flex items-center justify-between py-1.5 last:border-0"
              style={{ borderBottom: '1px solid var(--cc-border-subtle)' }}
            >
              <span className="capitalize" style={{ color: 'var(--cc-fg-muted)' }}>
                {cat}
              </span>
              <span className="font-mono font-medium" style={{ color: 'var(--cc-fg-default)' }}>
                {count}
              </span>
            </div>
          ))}
        </div>

        {/* By Language */}
        <div
          className="p-4 rounded-lg space-y-2 text-xs"
          style={{
            background: 'var(--cc-bg-subtle)',
            border: '1px solid var(--cc-border-muted)',
          }}
        >
          <div
            className="flex items-center space-x-2 font-semibold mb-2"
            style={{ color: 'var(--cc-fg-default)' }}
          >
            <Code2 className="w-3.5 h-3.5" style={{ color: 'var(--cc-accent-fg)' }} />
            <span>Evaluations by Language</span>
          </div>
          {Object.entries(data.by_language).map(([lang, count]) => (
            <div
              key={lang}
              className="flex items-center justify-between py-1.5 last:border-0"
              style={{ borderBottom: '1px solid var(--cc-border-subtle)' }}
            >
              <span className="capitalize" style={{ color: 'var(--cc-fg-muted)' }}>
                {lang}
              </span>
              <span className="font-mono font-medium" style={{ color: 'var(--cc-fg-default)' }}>
                {count}
              </span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
