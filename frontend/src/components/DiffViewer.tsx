import { useMemo, useState } from 'react'
import {
  ChevronDown,
  ChevronRight,
  FileCode,
  FileDiff,
  ShieldAlert,
} from 'lucide-react'
import type { FindingItem } from '../types/review'

interface DiffViewerProps {
  diffText?: string | null
  findings: FindingItem[]
}

interface DiffLine {
  type: 'context' | 'addition' | 'deletion' | 'header'
  content: string
  oldLineNumber?: number
  newLineNumber?: number
}

interface DiffFile {
  oldPath: string
  newPath: string
  lines: DiffLine[]
}

function parseUnifiedDiff(rawDiff: string): DiffFile[] {
  const files: DiffFile[] = []
  const rawLines = rawDiff.split('\n')
  let currentFile: DiffFile | null = null
  let currentOldLine = 0
  let currentNewLine = 0

  for (const line of rawLines) {
    if (line.startsWith('diff --git ')) {
      if (currentFile) files.push(currentFile)
      const parts = line.split(' ')
      const oldPath = parts[2]?.replace(/^a\//, '') ?? ''
      const newPath = parts[3]?.replace(/^b\//, '') ?? oldPath
      currentFile = { oldPath, newPath, lines: [] }
    } else if (line.startsWith('@@ ')) {
      if (!currentFile) {
        currentFile = { oldPath: 'unknown', newPath: 'unknown', lines: [] }
      }
      const match = line.match(/@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@/)
      if (match) {
        currentOldLine = parseInt(match[1], 10)
        currentNewLine = parseInt(match[2], 10)
      }
      currentFile.lines.push({ type: 'header', content: line })
    } else if (currentFile) {
      if (line.startsWith('+') && !line.startsWith('+++')) {
        currentFile.lines.push({
          type: 'addition',
          content: line.slice(1),
          newLineNumber: currentNewLine++,
        })
      } else if (line.startsWith('-') && !line.startsWith('---')) {
        currentFile.lines.push({
          type: 'deletion',
          content: line.slice(1),
          oldLineNumber: currentOldLine++,
        })
      } else if (!line.startsWith('+++') && !line.startsWith('---')) {
        currentFile.lines.push({
          type: 'context',
          content: line.startsWith(' ') ? line.slice(1) : line,
          oldLineNumber: currentOldLine++,
          newLineNumber: currentNewLine++,
        })
      }
    }
  }

  if (currentFile) files.push(currentFile)
  return files
}

export function DiffViewer({ diffText, findings }: DiffViewerProps) {
  const [collapsedFiles, setCollapsedFiles] = useState<Record<string, boolean>>({})

  const parsedFiles = useMemo(() => {
    if (!diffText?.trim()) return []
    return parseUnifiedDiff(diffText)
  }, [diffText])

  const toggleCollapse = (path: string) => {
    setCollapsedFiles((prev) => ({ ...prev, [path]: !prev[path] }))
  }

  if (!diffText?.trim()) {
    return (
      <div
        className="p-8 rounded-xl text-center space-y-3 animate-fadeIn"
        style={{ border: '2px dashed var(--cc-border-default)', background: 'var(--cc-bg-subtle)' }}
      >
        <FileDiff className="w-8 h-8 mx-auto" style={{ color: 'var(--cc-fg-subtle)' }} />
        <h4 className="text-sm font-semibold" style={{ color: 'var(--cc-fg-default)' }}>Raw PR Diff Not Available</h4>
        <p className="text-xs max-w-md mx-auto" style={{ color: 'var(--cc-fg-muted)' }}>
          The diff text was not cached locally for this review. Inspect the detailed code snippets and
          suggested fixes attached to individual findings below.
        </p>
      </div>
    )
  }

  return (
    <div className="space-y-6 font-mono text-xs animate-fadeIn">
      {parsedFiles.map((file) => {
        const isCollapsed = collapsedFiles[file.newPath] ?? false
        const fileFindings = findings.filter((f) => {
          const normF = f.file.replace(/^[ab]\//, '').toLowerCase()
          const normFile = file.newPath.toLowerCase()
          return normFile.endsWith(normF) || normF.endsWith(normFile)
        })

        return (
          <div
            key={file.newPath}
            id={`file-${file.newPath.replace(/[^a-zA-Z0-9_-]/g, '_')}`}
            className="rounded-xl overflow-hidden"
            style={{ border: '1px solid var(--cc-border-default)', background: 'var(--cc-bg-inset)' }}
          >
            {/* File Header */}
            <div
              onClick={() => toggleCollapse(file.newPath)}
              className="flex items-center justify-between px-4 py-2.5 cursor-pointer select-none transition-colors"
              style={{ background: 'var(--cc-bg-default)', borderBottom: isCollapsed ? 'none' : '1px solid var(--cc-border-default)' }}
            >
              <div className="flex items-center gap-2" style={{ color: 'var(--cc-fg-default)' }}>
                {isCollapsed ? (
                  <ChevronRight className="w-4 h-4" style={{ color: 'var(--cc-fg-muted)' }} />
                ) : (
                  <ChevronDown className="w-4 h-4" style={{ color: 'var(--cc-fg-muted)' }} />
                )}
                <FileCode className="w-4 h-4" style={{ color: 'var(--cc-accent-fg)' }} />
                <span className="font-semibold">{file.newPath}</span>
              </div>

              {fileFindings.length > 0 && (
                <span className="gh-label gh-label-danger text-[11px]">
                  <ShieldAlert className="w-3 h-3" />
                  <span>
                    {fileFindings.length} {fileFindings.length === 1 ? 'finding' : 'findings'}
                  </span>
                </span>
              )}
            </div>

            {/* Diff Lines Body */}
            {!isCollapsed && (
              <div className="overflow-x-auto">
                {file.lines.map((line, idx) => {
                  const lineNum = line.newLineNumber
                  const matchingFindings = lineNum
                    ? fileFindings.filter(
                        (f) => lineNum >= f.line_start && lineNum <= f.line_end,
                      )
                    : []

                  let rowBg = 'transparent'
                  let textColor = 'var(--cc-fg-default)'
                  let sign = ' '

                  if (line.type === 'header') {
                    rowBg = 'var(--cc-bg-subtle)'
                    textColor = 'var(--cc-accent-fg)'
                  } else if (line.type === 'addition') {
                    rowBg = 'var(--cc-success-subtle)'
                    textColor = 'var(--cc-success-fg)'
                    sign = '+'
                  } else if (line.type === 'deletion') {
                    rowBg = 'var(--cc-danger-subtle)'
                    textColor = 'var(--cc-danger-fg)'
                    sign = '-'
                  }

                  return (
                    <div key={idx} className="flex flex-col">
                      <div
                        className="flex items-stretch font-mono text-[11px] leading-5 transition-colors"
                        style={{ background: rowBg }}
                      >
                        {/* Old Line # */}
                        <div
                          className="w-12 px-2 text-right select-none shrink-0"
                          style={{ color: 'var(--cc-fg-subtle)', borderRight: '1px solid var(--cc-border-muted)' }}
                        >
                          {line.oldLineNumber ?? ''}
                        </div>
                        {/* New Line # */}
                        <div
                          className="w-12 px-2 text-right select-none shrink-0"
                          style={{ color: 'var(--cc-fg-subtle)', borderRight: '1px solid var(--cc-border-muted)' }}
                        >
                          {line.newLineNumber ?? ''}
                        </div>
                        {/* Sign */}
                        <div
                          className="w-5 text-center select-none shrink-0"
                          style={{ color: 'var(--cc-fg-subtle)' }}
                        >
                          {sign}
                        </div>
                        {/* Code Content */}
                        <div
                          className="px-2 py-0.5 whitespace-pre flex-1"
                          style={{ color: textColor }}
                        >
                          {line.content}
                        </div>
                      </div>

                      {/* Anchored Finding Callout */}
                      {matchingFindings.map((f) => (
                        <div
                          key={`anchor-${f.id}-${lineNum}`}
                          className="mx-4 my-1.5 p-3 rounded-lg flex items-start gap-3 text-xs"
                          style={{ background: 'var(--cc-accent-subtle)', border: '1px solid var(--cc-accent-muted)' }}
                        >
                          <ShieldAlert className="w-4 h-4 shrink-0 mt-0.5" style={{ color: 'var(--cc-accent-fg)' }} />
                          <div className="space-y-1 flex-1">
                            <div className="flex items-center justify-between">
                              <span className="font-semibold" style={{ color: 'var(--cc-fg-default)' }}>
                                [{f.severity.toUpperCase()}] {f.title}
                              </span>
                              <span className="text-[11px] font-mono" style={{ color: 'var(--cc-accent-fg)' }}>
                                by {f.agent}
                              </span>
                            </div>
                            <p className="text-xs font-sans leading-relaxed" style={{ color: 'var(--cc-fg-muted)' }}>
                              {f.explanation}
                            </p>
                            {f.suggested_fix && (
                              <pre
                                className="p-2 rounded text-[11px] font-mono whitespace-pre-wrap"
                                style={{ background: 'var(--cc-success-subtle)', border: '1px solid var(--cc-success-fg)', color: 'var(--cc-success-fg)' }}
                              >
                                {f.suggested_fix}
                              </pre>
                            )}
                          </div>
                        </div>
                      ))}
                    </div>
                  )
                })}
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}
