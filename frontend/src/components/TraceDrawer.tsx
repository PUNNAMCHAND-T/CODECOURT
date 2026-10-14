import {
  Activity,
  CheckCircle,
  Clock,
  Coins,
  Cpu,
  Layers,
  Scale,
  ShieldAlert,
  XCircle,
  Zap,
} from 'lucide-react'
import type { NodeTraceItem } from '../types/review'

interface TraceDrawerProps {
  traces?: NodeTraceItem[]
}

function getNodeIcon(nodeName: string) {
  switch (nodeName) {
    case 'prepare_context':
      return Layers
    case 'security':
    case 'security_reviewer':
      return ShieldAlert
    case 'performance':
    case 'performance_reviewer':
      return Zap
    case 'maintainability':
    case 'maintainability_reviewer':
      return Cpu
    case 'judge':
      return Scale
    default:
      return Activity
  }
}

export function TraceDrawer({ traces = [] }: TraceDrawerProps) {
  if (!traces || traces.length === 0) {
    return (
      <div
        className="p-8 rounded-xl text-center space-y-2 animate-fadeIn"
        style={{ border: '2px dashed var(--cc-border-default)', background: 'var(--cc-bg-subtle)' }}
      >
        <Activity className="w-8 h-8 mx-auto" style={{ color: 'var(--cc-fg-subtle)' }} />
        <h4 className="text-sm font-semibold" style={{ color: 'var(--cc-fg-default)' }}>No Per-Node Traces Available</h4>
        <p className="text-xs max-w-sm mx-auto" style={{ color: 'var(--cc-fg-muted)' }}>
          Per-node traces are captured during multi-agent graph execution for detailed latency and token
          attribution.
        </p>
      </div>
    )
  }

  return (
    <div className="space-y-4 animate-fadeIn">
      <div className="flex items-center justify-between text-xs pb-2" style={{ color: 'var(--cc-fg-muted)', borderBottom: '1px solid var(--cc-border-default)' }}>
        <span>Execution Graph Pipeline ({traces.length} steps recorded)</span>
        <span className="font-mono" style={{ color: 'var(--cc-accent-fg)' }}>LangGraph Pipeline Trace</span>
      </div>

      <div className="space-y-3">
        {traces.map((trace, idx) => {
          const NodeIcon = getNodeIcon(trace.node)
          const isError = Boolean(trace.error)
          const latency = typeof trace.latency_seconds === 'number'
            ? trace.latency_seconds
            : typeof trace.latency_ms === 'number'
            ? (trace.latency_ms as number) / 1000
            : 0

          return (
            <div
              key={`${trace.node}-${idx}`}
              className={`glass-card p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-3 animate-fadeInUp anim-delay-${Math.min(idx + 1, 6)}`}
              style={{
                borderColor: isError ? 'var(--cc-danger-fg)' : undefined,
                background: isError ? 'var(--cc-danger-subtle)' : undefined,
              }}
            >
              <div className="flex items-center gap-3">
                <div
                  className="w-9 h-9 rounded-lg flex items-center justify-center shrink-0"
                  style={{ background: 'var(--cc-bg-subtle)', border: '1px solid var(--cc-border-default)', color: 'var(--cc-accent-fg)' }}
                >
                  <NodeIcon className="w-4 h-4" />
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-semibold capitalize" style={{ color: 'var(--cc-fg-default)' }}>
                      {trace.node.replace('_', ' ')}
                    </span>
                    {isError ? (
                      <XCircle className="w-3.5 h-3.5" style={{ color: 'var(--cc-danger-fg)' }} />
                    ) : (
                      <CheckCircle className="w-3.5 h-3.5" style={{ color: 'var(--cc-success-fg)' }} />
                    )}
                  </div>
                  <span className="text-[11px] font-mono" style={{ color: 'var(--cc-fg-muted)' }}>
                    Step {idx + 1} in execution sequence
                  </span>
                </div>
              </div>

              {/* Metrics Chips */}
              <div className="flex flex-wrap items-center gap-3 text-xs font-mono">
                {latency > 0 && (
                  <div
                    className="flex items-center gap-1 px-2.5 py-1 rounded"
                    style={{ background: 'var(--cc-bg-subtle)', border: '1px solid var(--cc-border-default)', color: 'var(--cc-fg-default)' }}
                  >
                    <Clock className="w-3 h-3" style={{ color: 'var(--cc-fg-subtle)' }} />
                    <span>{latency.toFixed(2)}s</span>
                  </div>
                )}

                {typeof trace.tokens_total === 'number' && trace.tokens_total > 0 && (
                  <div
                    className="px-2.5 py-1 rounded"
                    style={{ background: 'var(--cc-bg-subtle)', border: '1px solid var(--cc-border-default)', color: 'var(--cc-fg-default)' }}
                  >
                    {trace.tokens_total.toLocaleString()} tokens
                  </div>
                )}

                {typeof trace.cost_usd === 'number' && trace.cost_usd > 0 && (
                  <div
                    className="flex items-center gap-1 px-2.5 py-1 rounded"
                    style={{ background: 'var(--cc-bg-subtle)', border: '1px solid var(--cc-border-default)', color: 'var(--cc-success-fg)' }}
                  >
                    <Coins className="w-3 h-3" />
                    <span>${trace.cost_usd.toFixed(5)}</span>
                  </div>
                )}

                {typeof trace.findings_count === 'number' && (
                  <div
                    className="px-2.5 py-1 rounded"
                    style={{ background: 'var(--cc-accent-subtle)', border: '1px solid var(--cc-accent-muted)', color: 'var(--cc-accent-fg)' }}
                  >
                    {trace.findings_count} findings
                  </div>
                )}
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
