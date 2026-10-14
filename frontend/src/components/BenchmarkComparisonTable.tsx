import { Award, CheckCircle, Clock, Coins, Layers, ShieldCheck } from 'lucide-react'
import type { ConfigComparison } from '../types/eval'

interface BenchmarkComparisonTableProps {
  comparisons: ConfigComparison[]
}

export function BenchmarkComparisonTable({ comparisons }: BenchmarkComparisonTableProps) {
  return (
    <div
      className="overflow-x-auto rounded-xl shadow-lg"
      style={{ border: '1px solid var(--cc-border-default)', background: 'var(--cc-bg-default)' }}
    >
      <table className="w-full text-left text-xs" style={{ color: 'var(--cc-fg-muted)' }}>
        <thead
          className="uppercase text-[10px] tracking-wider"
          style={{ background: 'var(--cc-bg-subtle)', color: 'var(--cc-fg-subtle)', borderBottom: '1px solid var(--cc-border-default)' }}
        >
          <tr>
            <th scope="col" className="px-4 py-3.5">
              Review Architecture
            </th>
            <th scope="col" className="px-3 py-3.5 text-center">
              Precision (μ ± σ)
            </th>
            <th scope="col" className="px-3 py-3.5 text-center">
              Recall (μ ± σ)
            </th>
            <th scope="col" className="px-3 py-3.5 text-center font-bold" style={{ color: 'var(--cc-accent-fg)' }}>
              F1 Score (μ ± σ)
            </th>
            <th scope="col" className="px-3 py-3.5 text-center">
              False Discovery (FDR)
            </th>
            <th scope="col" className="px-3 py-3.5 text-center">
              Clean Specificity
            </th>
            <th scope="col" className="px-3 py-3.5 text-center">
              Mean Latency
            </th>
            <th scope="col" className="px-3 py-3.5 text-center">
              Cost / PR
            </th>
          </tr>
        </thead>
        <tbody>
          {comparisons.map((c) => {
            const isJudge = c.config === 'multi_agent_judge'
            const isAblation = c.config === 'multi_agent_no_judge'

            return (
              <tr
                key={c.config}
                className="transition-colors"
                style={{
                  background: isJudge ? 'var(--cc-accent-subtle)' : 'transparent',
                  borderBottom: '1px solid var(--cc-border-muted)',
                }}
                onMouseEnter={(e) => {
                  if (!isJudge) e.currentTarget.style.background = 'var(--cc-bg-subtle)'
                }}
                onMouseLeave={(e) => {
                  if (!isJudge) e.currentTarget.style.background = 'transparent'
                }}
              >
                {/* Architecture Column */}
                <td className="px-4 py-3.5 font-medium" style={{ color: 'var(--cc-fg-default)' }}>
                  <div className="flex items-center gap-2.5">
                    <div
                      className="w-7 h-7 rounded-lg flex items-center justify-center shrink-0"
                      style={{
                        background: isJudge
                          ? 'var(--cc-accent-subtle)'
                          : isAblation
                          ? 'var(--cc-warning-subtle)'
                          : 'var(--cc-bg-subtle)',
                        color: isJudge
                          ? 'var(--cc-accent-fg)'
                          : isAblation
                          ? 'var(--cc-warning-fg)'
                          : 'var(--cc-fg-muted)',
                        border: `1px solid ${isJudge ? 'var(--cc-accent-muted)' : isAblation ? 'var(--cc-warning-emphasis)' : 'var(--cc-border-default)'}`,
                      }}
                    >
                      {isJudge ? (
                        <Award className="w-3.5 h-3.5" />
                      ) : isAblation ? (
                        <Layers className="w-3.5 h-3.5" />
                      ) : (
                        <ShieldCheck className="w-3.5 h-3.5" />
                      )}
                    </div>
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="font-semibold" style={{ color: 'var(--cc-fg-default)' }}>{c.label}</span>
                        {isJudge && (
                          <span className="gh-label gh-label-success text-[10px] font-semibold">
                            Full Pipeline
                          </span>
                        )}
                        {isAblation && (
                          <span className="gh-label gh-label-warning text-[10px]">
                            Ablation
                          </span>
                        )}
                      </div>
                      <span className="text-[11px] font-mono" style={{ color: 'var(--cc-fg-subtle)' }}>
                        {c.num_runs} runs &middot; {c.model}
                      </span>
                    </div>
                  </div>
                </td>

                {/* Precision */}
                <td className="px-3 py-3.5 text-center font-mono" style={{ color: 'var(--cc-fg-default)' }}>
                  {c.precision.formatted}
                </td>

                {/* Recall */}
                <td className="px-3 py-3.5 text-center font-mono" style={{ color: 'var(--cc-fg-default)' }}>
                  {c.recall.formatted}
                </td>

                {/* F1 Score */}
                <td className="px-3 py-3.5 text-center font-mono font-bold" style={{ color: 'var(--cc-accent-fg)' }}>
                  {c.f1.formatted}
                </td>

                {/* FDR */}
                <td className="px-3 py-3.5 text-center font-mono">
                  <span
                    style={{
                      color: c.fdr.mean === 0 ? 'var(--cc-success-fg)' : 'var(--cc-danger-fg)',
                      fontWeight: c.fdr.mean > 0 ? 600 : 400,
                    }}
                  >
                    {c.fdr.formatted}
                  </span>
                </td>

                {/* Clean Specificity */}
                <td className="px-3 py-3.5 text-center font-mono">
                  <span className="flex items-center justify-center gap-1" style={{ color: 'var(--cc-success-fg)' }}>
                    <CheckCircle className="w-3 h-3" />
                    <span>{c.clean_specificity.formatted}</span>
                  </span>
                </td>

                {/* Mean Latency */}
                <td className="px-3 py-3.5 text-center font-mono" style={{ color: 'var(--cc-fg-default)' }}>
                  <span className="flex items-center justify-center gap-1">
                    <Clock className="w-3 h-3" style={{ color: 'var(--cc-fg-subtle)' }} />
                    <span>{c.mean_latency_s.formatted}</span>
                  </span>
                </td>

                {/* Cost / PR */}
                <td className="px-3 py-3.5 text-center font-mono" style={{ color: 'var(--cc-success-fg)' }}>
                  <span className="flex items-center justify-center gap-1">
                    <Coins className="w-3 h-3" />
                    <span>${c.cost_per_pr_usd.mean.toFixed(4)}</span>
                  </span>
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
