import { useEffect, useRef, useState, useCallback } from 'react'

/* ── Types ── */

export interface LogEntry {
  line: string
  timestamp: string | null
}

interface LogViewerProps {
  profileName: string
  baseUrl?: string
}

/* ── Helpers ── */

const SEVERITY_COLORS: Record<string, string> = {
  ERROR:   'text-red-500',
  WARNING: 'text-yellow-500',
  WARN:    'text-yellow-500',
  INFO:    'text-green-400',
  DEBUG:   'text-blue-400',
  CRITICAL:'text-red-600',
  FATAL:   'text-red-600',
}

function severityClass(line: string): string {
  for (const [kw, cls] of Object.entries(SEVERITY_COLORS)) {
    if (line.includes(` ${kw} `) || line.startsWith(kw)) return cls
  }
  return 'text-foreground'
}

/* ── Component ── */

export default function LogViewer({ profileName, baseUrl = '/api' }: LogViewerProps) {
  const [logs, setLogs] = useState<LogEntry[]>([])
  const [filter, setFilter] = useState('')
  const [autoScroll, setAutoScroll] = useState(true)
  const [connected, setConnected] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const containerRef = useRef<HTMLDivElement>(null)
  const eventSourceRef = useRef<EventSource | null>(null)

  /* ── Fetch historical logs on mount ── */
  const fetchHistory = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await fetch(`${baseUrl}/profiles/${encodeURIComponent(profileName)}/logs?lines=200`)
      if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
      const data = await res.json()
      setLogs(data.lines ?? [])
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setLoading(false)
    }
  }, [profileName, baseUrl])

  useEffect(() => {
    fetchHistory()
  }, [fetchHistory])

  /* ── SSE connection ── */
  useEffect(() => {
    let cancelled = false

    const connect = () => {
      const url = `${baseUrl}/profiles/${encodeURIComponent(profileName)}/logs/stream`
      const es = new EventSource(url)
      eventSourceRef.current = es

      es.onopen = () => {
        if (!cancelled) setConnected(true)
      }

      es.onmessage = (event) => {
        if (cancelled) return
        try {
          const entry: LogEntry = JSON.parse(event.data)
          if (entry.error) {
            setError(entry.error)
            return
          }
          setLogs((prev) => [...prev, entry])
        } catch {
          // ignore malformed data
        }
      }

      es.onerror = () => {
        if (!cancelled) {
          setConnected(false)
          setError('SSE 连接断开，尝试重连...')
        }
        es.close()
      }
    }

    connect()

    return () => {
      cancelled = true
      if (eventSourceRef.current) {
        eventSourceRef.current.close()
        eventSourceRef.current = null
      }
    }
  }, [profileName, baseUrl])

  /* ── Auto-scroll ── */
  useEffect(() => {
    if (autoScroll && containerRef.current) {
      containerRef.current.scrollTop = containerRef.current.scrollHeight
    }
  }, [logs, autoScroll])

  /* ── Clear logs ── */
  const handleClear = () => {
    setLogs([])
  }

  /* ── Filtered entries ── */
  const filteredLogs = filter
    ? logs.filter((e) => e.line.toLowerCase().includes(filter.toLowerCase()))
    : logs

  return (
    <div className="space-y-3">
      {/* Toolbar */}
      <div className="flex flex-wrap items-center gap-2">
        {/* Connection status */}
        <span
          className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium ${
            connected
              ? 'bg-green-500/10 text-green-400'
              : 'bg-red-500/10 text-red-400'
          }`}
        >
          <span
            className={`h-1.5 w-1.5 rounded-full ${
              connected ? 'bg-green-400' : 'bg-red-400'
            }`}
          />
          {connected ? '已连接' : '未连接'}
        </span>

        {/* Search filter */}
        <input
          type="text"
          placeholder="搜索日志..."
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          className="flex-1 min-w-[160px] rounded-md border border-border bg-muted/50 px-2.5 py-1 text-xs placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring"
        />

        {/* Auto-scroll toggle */}
        <button
          onClick={() => setAutoScroll(!autoScroll)}
          className={`rounded-md border px-2.5 py-1 text-xs font-medium transition-colors ${
            autoScroll
              ? 'border-primary bg-primary/10 text-primary'
              : 'border-border bg-muted/50 text-muted-foreground hover:text-foreground'
          }`}
        >
          自动滚动 {autoScroll ? 'ON' : 'OFF'}
        </button>

        {/* Clear */}
        <button
          onClick={handleClear}
          className="rounded-md border border-border bg-muted/50 px-2.5 py-1 text-xs font-medium text-muted-foreground hover:text-foreground transition-colors"
        >
          清空
        </button>

        {/* Reload */}
        <button
          onClick={fetchHistory}
          className="rounded-md border border-border bg-muted/50 px-2.5 py-1 text-xs font-medium text-muted-foreground hover:text-foreground transition-colors"
          disabled={loading}
        >
          重新加载
        </button>

        {/* Line count */}
        <span className="text-xs text-muted-foreground">
          {filteredLogs.length} / {logs.length} 行
        </span>
      </div>

      {/* Error banner */}
      {error && (
        <div className="rounded-md border border-red-500/30 bg-red-500/5 px-3 py-2 text-xs text-red-400">
          {error}
          <button
            onClick={() => setError(null)}
            className="ml-2 underline hover:text-red-300"
          >
            关闭
          </button>
        </div>
      )}

      {/* Loading state */}
      {loading && (
        <div className="flex items-center justify-center py-8 text-sm text-muted-foreground">
          <svg
            className="mr-2 h-4 w-4 animate-spin"
            xmlns="http://www.w3.org/2000/svg"
            fill="none"
            viewBox="0 0 24 24"
          >
            <circle
              className="opacity-25"
              cx="12"
              cy="12"
              r="10"
              stroke="currentColor"
              strokeWidth="4"
            />
            <path
              className="opacity-75"
              fill="currentColor"
              d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
            />
          </svg>
          加载历史日志...
        </div>
      )}

      {/* Empty state */}
      {!loading && filteredLogs.length === 0 && (
        <div className="flex items-center justify-center py-8 text-sm text-muted-foreground">
          {filter ? '无匹配的日志行' : '暂无日志数据'}
        </div>
      )}

      {/* Log lines */}
      <div
        ref={containerRef}
        className="h-[480px] overflow-auto rounded-lg border border-border bg-[#0d1117] p-3 font-mono text-xs leading-relaxed"
      >
        {filteredLogs.map((entry, idx) => (
          <div key={idx} className="hover:bg-white/[0.03]">
            {entry.timestamp && (
              <span className="text-gray-500 select-none">{entry.timestamp} </span>
            )}
            <span className={severityClass(entry.line)}>{entry.line}</span>
          </div>
        ))}
      </div>
    </div>
  )
}
