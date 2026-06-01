import { useState, useEffect, useCallback } from 'react'
import LoadingSpinner from '@/components/LoadingSpinner'
import ErrorMessage from '@/components/ErrorMessage'
import { Clock, GitCommit, FilePlus, Scale, CheckCircle2, Sparkles, Filter, X } from 'lucide-react'

// ── Types ─────────────────────────────────────────────────────────────

interface TimelineEvent {
  timestamp: string
  profile_name: string
  event_type: string
  title: string
  description: string
  source_path: string
}

interface EventTypesResponse {
  event_types: string[]
}

// ── Helpers ───────────────────────────────────────────────────────────

const BASE = '/api'

async function apiFetch<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`)
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
  return res.json() as Promise<T>
}

const EVENT_TYPE_META: Record<string, { label: string; icon: typeof GitCommit; color: string }> = {
  code_commit: { label: '代码提交', icon: GitCommit, color: 'text-blue-500' },
  doc_created: { label: '文档创建', icon: FilePlus, color: 'text-green-500' },
  decision_made: { label: '决策', icon: Scale, color: 'text-purple-500' },
  task_completed: { label: '任务完成', icon: CheckCircle2, color: 'text-emerald-500' },
  skill_created: { label: '技能创建', icon: Sparkles, color: 'text-amber-500' },
}

function getEventMeta(type: string) {
  return EVENT_TYPE_META[type] ?? { label: type, icon: GitCommit, color: 'text-gray-400' }
}

function formatTime(iso: string): string {
  const d = new Date(iso)
  const now = new Date()
  const diffMs = now.getTime() - d.getTime()
  const diffMins = Math.floor(diffMs / 60000)
  const diffHours = Math.floor(diffMins / 60)
  const diffDays = Math.floor(diffHours / 24)

  if (diffMins < 1) return '刚刚'
  if (diffMins < 60) return `${diffMins} 分钟前`
  if (diffHours < 24) return `${diffHours} 小时前`
  if (diffDays < 7) return `${diffDays} 天前`

  return d.toLocaleDateString('zh-CN', {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function formatFullTime(iso: string): string {
  const d = new Date(iso)
  return d.toLocaleDateString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

// ── Component ─────────────────────────────────────────────────────────

export default function TimelinePage() {
  const [events, setEvents] = useState<TimelineEvent[]>([])
  const [eventTypes, setEventTypes] = useState<string[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Filters
  const [profileFilter, setProfileFilter] = useState('')
  const [typeFilter, setTypeFilter] = useState('')
  const [profiles, setProfiles] = useState<string[]>([])

  // ── Fetch Data ──────────────────────────────────────────────────────

  const fetchTimeline = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const params = new URLSearchParams()
      params.set('limit', '100')
      if (profileFilter) params.set('profile', profileFilter)
      if (typeFilter) params.set('type', typeFilter)

      const [eventsData, typesData] = await Promise.all([
        apiFetch<TimelineEvent[]>(`/timeline?${params.toString()}`),
        apiFetch<EventTypesResponse>('/timeline/types').catch(() => ({
          event_types: [] as string[],
        })),
      ])
      setEvents(eventsData ?? [])
      setEventTypes(typesData?.event_types ?? [])

      // Extract unique profiles from events
      const uniqueProfiles = [...new Set(eventsData?.map((e) => e.profile_name).filter(Boolean) ?? [])].sort()
      setProfiles(uniqueProfiles)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setLoading(false)
    }
  }, [profileFilter, typeFilter])

  useEffect(() => {
    fetchTimeline()
  }, [fetchTimeline])

  const clearFilters = () => {
    setProfileFilter('')
    setTypeFilter('')
  }

  const hasFilters = profileFilter || typeFilter

  // ── Render ──────────────────────────────────────────────────────────

  return (
    <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6">
      {/* Header */}
      <div className="mb-6">
        <h1 className="text-2xl font-bold tracking-tight">活动时间线</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          所有 Profile 的活动记录，按时间倒序排列
        </p>
      </div>

      {/* Filters */}
      <div className="mb-6 flex flex-wrap items-center gap-3">
        {/* Profile Filter */}
        <div className="relative">
          <Filter className="absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
          <select
            value={profileFilter}
            onChange={(e) => setProfileFilter(e.target.value)}
            className="h-9 appearance-none rounded-lg border border-border bg-card pl-9 pr-8 text-xs font-medium text-foreground focus:border-primary/50 focus:outline-none focus:ring-2 focus:ring-primary/20 transition-all"
          >
            <option value="">全部 Profile</option>
            {profiles.map((p) => (
              <option key={p} value={p}>{p}</option>
            ))}
          </select>
          <div className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground">
            <svg className="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
            </svg>
          </div>
        </div>

        {/* Type Filter */}
        <div className="relative">
          <select
            value={typeFilter}
            onChange={(e) => setTypeFilter(e.target.value)}
            className="h-9 appearance-none rounded-lg border border-border bg-card pl-3 pr-8 text-xs font-medium text-foreground focus:border-primary/50 focus:outline-none focus:ring-2 focus:ring-primary/20 transition-all"
          >
            <option value="">全部类型</option>
            {eventTypes.map((t) => {
              const meta = getEventMeta(t)
              return (
                <option key={t} value={t}>{meta.label}</option>
              )
            })}
          </select>
          <div className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground">
            <svg className="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
            </svg>
          </div>
        </div>

        {/* Clear Filters */}
        {hasFilters && (
          <button
            onClick={clearFilters}
            className="inline-flex items-center gap-1 rounded-lg border border-border bg-card px-3 py-1.5 text-xs font-medium text-muted-foreground hover:text-foreground transition-colors"
          >
            <X className="h-3 w-3" />
            清除筛选
          </button>
        )}

        <span className="ml-auto text-xs text-muted-foreground">
          {events.length} 条记录
        </span>
      </div>

      {/* Loading */}
      {loading && <LoadingSpinner />}

      {/* Error */}
      {error && <ErrorMessage message={error} onRetry={fetchTimeline} />}

      {/* Timeline */}
      {!loading && !error && (
        <>
          {events.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-20 text-center">
              <Clock className="mb-4 h-12 w-12 text-muted-foreground/30" />
              <p className="text-sm text-muted-foreground">暂无活动记录</p>
              {hasFilters && (
                <button
                  onClick={clearFilters}
                  className="mt-2 text-xs text-primary hover:underline"
                >
                  清除筛选条件
                </button>
              )}
            </div>
          ) : (
            <div className="relative">
              {/* Timeline vertical line */}
              <div className="absolute left-[19px] top-2 bottom-2 w-px bg-border" />

              <div className="space-y-4">
                {events.map((event, idx) => {
                  const meta = getEventMeta(event.event_type)
                  const Icon = meta.icon
                  return (
                    <div key={`${event.timestamp}-${idx}`} className="relative flex gap-4">
                      {/* Timeline dot */}
                      <div className={`relative z-10 flex h-[38px] w-[38px] flex-shrink-0 items-center justify-center rounded-full border border-border bg-card`}>
                        <Icon className={`h-4 w-4 ${meta.color}`} />
                      </div>

                      {/* Content card */}
                      <div className="min-w-0 flex-1 rounded-xl border border-border bg-card p-4 shadow-sm transition-all hover:border-ring/30 hover:shadow-md">
                        <div className="flex items-start justify-between gap-3">
                          <div className="min-w-0 flex-1">
                            {/* Type badge + profile */}
                            <div className="flex items-center gap-2 mb-1.5">
                              <span className={`inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-[11px] font-medium ${meta.color} border-current/20 bg-current/5`}>
                                <Icon className="h-3 w-3" />
                                {meta.label}
                              </span>
                              {event.profile_name && (
                                <span className="inline-flex items-center gap-1 rounded-md bg-secondary/50 px-2 py-0.5 text-[11px] font-medium text-muted-foreground">
                                  @{event.profile_name}
                                </span>
                              )}
                            </div>

                            {/* Title */}
                            <h3 className="font-medium text-foreground">
                              {event.title}
                            </h3>

                            {/* Description */}
                            {event.description && (
                              <p className="mt-1 text-sm text-muted-foreground line-clamp-2">
                                {event.description}
                              </p>
                            )}

                            {/* Source path */}
                            {event.source_path && (
                              <p className="mt-1.5 text-[11px] text-muted-foreground/60 truncate font-mono">
                                {event.source_path}
                              </p>
                            )}
                          </div>

                          {/* Timestamp */}
                          <div className="flex flex-col items-end gap-0.5 flex-shrink-0">
                            <span className="text-xs text-muted-foreground whitespace-nowrap">
                              {formatTime(event.timestamp)}
                            </span>
                            <span className="text-[10px] text-muted-foreground/60 whitespace-nowrap">
                              {formatFullTime(event.timestamp)}
                            </span>
                          </div>
                        </div>
                      </div>
                    </div>
                  )
                })}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  )
}
