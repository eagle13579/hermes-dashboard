import { useState, useEffect, useCallback, useRef } from 'react'
import LoadingSpinner from '@/components/LoadingSpinner'
import ErrorMessage from '@/components/ErrorMessage'
import { Search, FileText, Code, Brain, BookOpen, ExternalLink } from 'lucide-react'

// ── Types ─────────────────────────────────────────────────────────────

interface SearchResult {
  type: string
  title: string
  summary: string
  score: number
  source_path?: string
  profile?: string
}

interface SearchResponse {
  results: SearchResult[]
  total: number
  offset: number
  limit: number
}

// ── Helpers ───────────────────────────────────────────────────────────

const BASE = '/api'

async function apiFetch<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`)
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
  return res.json() as Promise<T>
}

const TYPE_META: Record<string, { label: string; icon: typeof FileText; color: string }> = {
  skill: { label: '技能', icon: Code, color: 'text-blue-500' },
  code: { label: '代码', icon: FileText, color: 'text-green-500' },
  mental_model: { label: '心智模型', icon: Brain, color: 'text-purple-500' },
  doc: { label: '文档', icon: BookOpen, color: 'text-amber-500' },
}

function getTypeMeta(type: string) {
  return TYPE_META[type] ?? { label: type, icon: FileText, color: 'text-gray-400' }
}

function formatScore(score: number): string {
  return `${Math.round(score * 100)}%`
}

// ── Component ─────────────────────────────────────────────────────────

export default function SearchPage() {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<SearchResult[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [searched, setSearched] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  const doSearch = useCallback(async () => {
    const q = query.trim()
    if (!q) return

    setLoading(true)
    setError(null)
    setSearched(true)

    try {
      const data = await apiFetch<SearchResponse>(
        `/knowledge/search?q=${encodeURIComponent(q)}&limit=50`
      )
      setResults(data.results ?? [])
      setTotal(data.total ?? 0)
    } catch (e) {
      setError((e as Error).message)
      setResults([])
      setTotal(0)
    } finally {
      setLoading(false)
    }
  }, [query])

  useEffect(() => {
    // focus input on mount
    inputRef.current?.focus()
  }, [])

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') doSearch()
  }

  // ── Render ──────────────────────────────────────────────────────────

  return (
    <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6">
      {/* Header */}
      <div className="mb-8">
        <h1 className="text-2xl font-bold tracking-tight">知识搜索</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          跨源搜索技能、代码资产、心智模型和产品文档
        </p>
      </div>

      {/* Search Input */}
      <div className="relative mb-8">
        <Search className="absolute left-4 top-1/2 h-5 w-5 -translate-y-1/2 text-muted-foreground" />
        <input
          ref={inputRef}
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="输入关键词搜索知识库..."
          className="w-full rounded-xl border border-border bg-card py-3.5 pl-12 pr-4 text-sm text-foreground placeholder:text-muted-foreground/60 focus:border-primary/50 focus:outline-none focus:ring-2 focus:ring-primary/20 transition-all"
        />
        <button
          onClick={doSearch}
          disabled={!query.trim() || loading}
          className="absolute right-2 top-1/2 -translate-y-1/2 rounded-lg bg-primary px-4 py-1.5 text-xs font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
        >
          {loading ? '搜索中...' : '搜索'}
        </button>
      </div>

      {/* Loading */}
      {loading && <LoadingSpinner />}

      {/* Error */}
      {error && <ErrorMessage message={error} onRetry={doSearch} />}

      {/* Results */}
      {!loading && !error && searched && (
        <>
          {/* Summary */}
          <div className="mb-4 flex items-center gap-2 text-sm text-muted-foreground">
            {total > 0 ? (
              <span>共找到 <strong className="text-foreground">{total}</strong> 条结果</span>
            ) : (
              <span>未找到匹配结果</span>
            )}
          </div>

          {/* Result List */}
          <div className="space-y-3">
            {results.map((item, idx) => {
              const meta = getTypeMeta(item.type)
              const Icon = meta.icon
              return (
                <div
                  key={`${item.source_path ?? ''}-${idx}`}
                  className="rounded-xl border border-border bg-card p-4 shadow-sm transition-all hover:border-ring/30 hover:shadow-md"
                >
                  <div className="flex items-start justify-between gap-3">
                    {/* Left: Type badge + content */}
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2 mb-1.5">
                        <span className={`inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-[11px] font-medium ${meta.color} border-current/20 bg-current/5`}>
                          <Icon className="h-3 w-3" />
                          {meta.label}
                        </span>
                        {item.profile && (
                          <span className="text-[11px] text-muted-foreground">
                            @{item.profile}
                          </span>
                        )}
                      </div>
                      <h3 className="font-medium text-foreground truncate">
                        {item.title}
                      </h3>
                      {item.summary && (
                        <p className="mt-1 text-sm text-muted-foreground line-clamp-2">
                          {item.summary}
                        </p>
                      )}
                      {item.source_path && (
                        <p className="mt-1.5 text-[11px] text-muted-foreground/60 truncate font-mono">
                          {item.source_path}
                        </p>
                      )}
                    </div>

                    {/* Right: Score */}
                    <div className="flex flex-col items-end gap-1 flex-shrink-0">
                      <span className="inline-flex items-center rounded-full border border-emerald-500/20 bg-emerald-500/10 px-2 py-0.5 text-xs font-semibold text-emerald-500">
                        {formatScore(item.score)}
                      </span>
                      <span className="text-[10px] text-muted-foreground">匹配度</span>
                    </div>
                  </div>
                </div>
              )
            })}
          </div>
        </>
      )}

      {/* Initial state */}
      {!loading && !error && !searched && (
        <div className="flex flex-col items-center justify-center py-20 text-center">
          <Search className="mb-4 h-12 w-12 text-muted-foreground/30" />
          <p className="text-sm text-muted-foreground">
            输入关键词开始搜索知识库内容
          </p>
          <p className="mt-1 text-xs text-muted-foreground/60">
            支持搜索技能、代码资产、心智模型和产品文档
          </p>
        </div>
      )}
    </div>
  )
}
