import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Card, CardGrid } from '@/components/Card'
import StatusBadge from '@/components/StatusBadge'
import LoadingSpinner from '@/components/LoadingSpinner'
import ErrorMessage from '@/components/ErrorMessage'
import * as echarts from 'echarts'
import type { ProjectItem, KanbanItem } from '@/store/profileStore'

// ── Types ─────────────────────────────────────────────────────────────

interface MergedItem {
  name: string
  description?: string
  status?: string
  progress_pct?: number
  updated_at?: string
  source: 'profile' | 'kanban'
}

interface HealthSample {
  timestamp: string
  status: 'up' | 'down'
  response_time_ms: number
  services_online: number
  services_total: number
}

interface HealthHistory {
  samples: HealthSample[]
  range_hours: number
  total: number
  source: string
}

interface ServiceInfo {
  name: string
  port: number
  category: string
  status: 'up' | 'down'
  response_time_ms: number
}

interface CurrentHealth {
  overall_status: string
  uptime_pct: number
  avg_response_time_ms: number
  services: ServiceInfo[]
  total_services: number
  online_services: number
  generated_at: string
}

// ── Helpers ───────────────────────────────────────────────────────────

const BASE = '/api'

async function apiFetch<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`)
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
  return res.json() as Promise<T>
}

// ── Component ─────────────────────────────────────────────────────────

export default function HomePage() {
  const navigate = useNavigate()
  const chartRef = useRef<HTMLDivElement>(null)
  const chartInstance = useRef<echarts.ECharts | null>(null)

  // Existing state
  const [profiles, setProfiles] = useState<ProjectItem[]>([])
  const [kanbanItems, setKanbanItems] = useState<KanbanItem[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Health state
  const [healthHistory, setHealthHistory] = useState<HealthHistory | null>(null)
  const [currentHealth, setCurrentHealth] = useState<CurrentHealth | null>(null)
  const [healthLoading, setHealthLoading] = useState(true)

  // ── Data fetching ─────────────────────────────────────────────────

  const fetchData = async () => {
    setLoading(true)
    setError(null)
    try {
      const [profilesData, kanbanData] = await Promise.all([
        apiFetch<ProjectItem[]>('/profiles').catch(() => [] as ProjectItem[]),
        apiFetch<KanbanItem[]>('/kanban').catch(() => [] as KanbanItem[]),
      ])
      setProfiles(profilesData)
      setKanbanItems(kanbanData)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setLoading(false)
    }
  }

  const fetchHealth = async () => {
    setHealthLoading(true)
    try {
      const [history, current] = await Promise.all([
        apiFetch<HealthHistory>('/health/history?hours=24').catch(() => null),
        apiFetch<CurrentHealth>('/health/current').catch(() => null),
      ])
      setHealthHistory(history)
      setCurrentHealth(current)
    } catch {
      // Health data is optional
    } finally {
      setHealthLoading(false)
    }
  }

  useEffect(() => {
    fetchData()
    fetchHealth()
  }, [])

  // ── ECharts ───────────────────────────────────────────────────────

  useEffect(() => {
    if (!chartRef.current || !healthHistory?.samples?.length) return

    // Dispose previous instance
    if (chartInstance.current) {
      chartInstance.current.dispose()
    }

    const chart = echarts.init(chartRef.current, undefined, { renderer: 'canvas' })
    chartInstance.current = chart

    const samples = healthHistory.samples
    const timestamps = samples.map((s) => {
      const d = new Date(s.timestamp)
      return `${d.getHours().toString().padStart(2, '0')}:${d.getMinutes().toString().padStart(2, '0')}`
    })

    // 在线率（百分比）
    const uptimeSeries = samples.map((s) =>
      s.services_total > 0
        ? Math.round((s.services_online / s.services_total) * 100)
        : 0
    )

    // 响应时间
    const responseSeries = samples.map((s) => s.response_time_ms)

    // 标注 down 事件
    const markAreas = samples
      .map((s, idx) =>
        s.status === 'down'
          ? [
              {
                xAxis: idx - 0.5,
                itemStyle: { color: 'rgba(239, 68, 68, 0.08)' },
              },
              {
                xAxis: idx + 0.5,
                itemStyle: { color: 'rgba(239, 68, 68, 0.08)' },
              },
            ]
          : []
      )
      .flat()

    const option: echarts.EChartsOption = {
      backgroundColor: 'transparent',
      tooltip: {
        trigger: 'axis',
        backgroundColor: 'rgba(15, 23, 42, 0.9)',
        borderColor: 'rgba(148, 163, 184, 0.2)',
        textStyle: { color: '#e2e8f0', fontSize: 12 },
      },
      legend: {
        data: ['在线率', '响应时间'],
        top: 0,
        right: 0,
        textStyle: { color: '#94a3b8', fontSize: 11 },
        itemWidth: 12,
        itemHeight: 8,
      },
      grid: {
        left: 8,
        right: 8,
        top: 32,
        bottom: 8,
        containLabel: true,
      },
      xAxis: {
        type: 'category',
        data: timestamps,
        axisLine: { lineStyle: { color: 'rgba(148,163,184,0.2)' } },
        axisLabel: {
          color: '#64748b',
          fontSize: 10,
          interval: Math.max(0, Math.floor(timestamps.length / 8) - 1),
        },
        splitLine: { show: false },
      },
      yAxis: [
        {
          type: 'value',
          name: '在线率 %',
          nameTextStyle: { color: '#64748b', fontSize: 10 },
          min: 0,
          max: 100,
          axisLabel: { color: '#64748b', fontSize: 10, formatter: '{value}%' },
          splitLine: { lineStyle: { color: 'rgba(148,163,184,0.08)', type: 'dashed' } },
        },
        {
          type: 'value',
          name: '响应时间 ms',
          nameTextStyle: { color: '#64748b', fontSize: 10 },
          axisLabel: { color: '#64748b', fontSize: 10 },
          splitLine: { show: false },
        },
      ],
      series: [
        {
          name: '在线率',
          type: 'line',
          smooth: true,
          symbol: 'none',
          lineStyle: { color: '#22c55e', width: 2 },
          areaStyle: {
            color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
              { offset: 0, color: 'rgba(34, 197, 94, 0.25)' },
              { offset: 1, color: 'rgba(34, 197, 94, 0.02)' },
            ]),
          },
          data: uptimeSeries,
          markArea: markAreas.length > 0 ? { data: markAreas } : undefined,
        },
        {
          name: '响应时间',
          type: 'line',
          yAxisIndex: 1,
          smooth: true,
          symbol: 'none',
          lineStyle: { color: '#3b82f6', width: 2 },
          areaStyle: {
            color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
              { offset: 0, color: 'rgba(59, 130, 246, 0.2)' },
              { offset: 1, color: 'rgba(59, 130, 246, 0.02)' },
            ]),
          },
          data: responseSeries,
        },
      ],
    }

    chart.setOption(option)

    // Resize observer
    const observer = new ResizeObserver(() => chart.resize())
    observer.observe(chartRef.current)

    return () => {
      observer.disconnect()
      chart.dispose()
      chartInstance.current = null
    }
  }, [healthHistory])

  // ── Derived data ─────────────────────────────────────────────────

  // Merge profiles and kanban items into a unified card list
  const merged: MergedItem[] = [
    ...profiles.map((p) => ({ ...p, source: 'profile' as const })),
    ...kanbanItems.map((k) => ({ name: k.project, status: k.status, progress_pct: k.progress_pct, updated_at: k.updated_at, source: 'kanban' as const })),
  ]

  // Deduplicate by name (kanban items override profiles with same name)
  const nameMap = new Map<string, MergedItem>()
  for (const item of merged) {
    const existing = nameMap.get(item.name)
    if (!existing || item.source === 'kanban') {
      nameMap.set(item.name, item)
    }
  }
  const cards = Array.from(nameMap.values())

  // Stats
  const totalProjects = cards.length
  const activeProjects = cards.filter((c) => c.status?.toLowerCase() === 'active').length
  const completedProjects = cards.filter((c) => c.status?.toLowerCase() === 'completed').length

  // ── Loading State ──
  if (loading) {
    return (
      <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6">
        <h1 className="text-2xl font-bold tracking-tight">项目总览</h1>
        <p className="mt-1 text-sm text-muted-foreground">加载中...</p>
        <LoadingSpinner className="mt-12" />
      </div>
    )
  }

  // ── Error State ──
  if (error) {
    return (
      <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6">
        <h1 className="text-2xl font-bold tracking-tight">项目总览</h1>
        <ErrorMessage message={`无法加载数据: ${error}`} onRetry={fetchData} />
      </div>
    )
  }

  // ── Health quick stats ──────────────────────────────────────────
  const healthStats = currentHealth
    ? [
        {
          label: '服务总数',
          value: `${currentHealth.online_services} / ${currentHealth.total_services}`,
          sub: '在线 / 总计',
          color: 'text-blue-600 dark:text-blue-400',
        },
        {
          label: '在线率',
          value: `${currentHealth.uptime_pct}%`,
          sub: currentHealth.overall_status === 'healthy' ? '健康' : currentHealth.overall_status === 'degraded' ? '降级' : '严重',
          color: currentHealth.uptime_pct >= 95
            ? 'text-green-600 dark:text-green-400'
            : currentHealth.uptime_pct >= 75
              ? 'text-yellow-600 dark:text-yellow-400'
              : 'text-red-600 dark:text-red-400',
        },
        {
          label: '平均响应',
          value: `${currentHealth.avg_response_time_ms} ms`,
          sub: currentHealth.avg_response_time_ms < 50 ? '快速' : currentHealth.avg_response_time_ms < 100 ? '正常' : '慢速',
          color: currentHealth.avg_response_time_ms < 50
            ? 'text-green-600 dark:text-green-400'
            : currentHealth.avg_response_time_ms < 100
              ? 'text-yellow-600 dark:text-yellow-400'
              : 'text-red-600 dark:text-red-400',
        },
      ]
    : []

  return (
    <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6">
      {/* ── Header ───────────────────────────────────────────── */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">项目总览</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Hermes 生态系统全局看板
          </p>
        </div>
        {/* Overall health badge */}
        {currentHealth && (
          <span className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-medium ${
            currentHealth.overall_status === 'healthy'
              ? 'border-green-500/30 bg-green-500/15 text-green-600 dark:text-green-400'
              : currentHealth.overall_status === 'degraded'
                ? 'border-yellow-500/30 bg-yellow-500/15 text-yellow-600 dark:text-yellow-400'
                : currentHealth.overall_status === 'critical'
                  ? 'border-red-500/30 bg-red-500/15 text-red-600 dark:text-red-400'
                  : 'border-gray-500/30 bg-gray-500/15 text-gray-600 dark:text-gray-400'
          }`}>
            <span className={`inline-block h-2 w-2 rounded-full ${
              currentHealth.overall_status === 'healthy' ? 'bg-green-500' :
              currentHealth.overall_status === 'degraded' ? 'bg-yellow-500' :
              currentHealth.overall_status === 'critical' ? 'bg-red-500' : 'bg-gray-500'
            }`} />
            系统 {currentHealth.overall_status === 'healthy' ? '健康' :
                   currentHealth.overall_status === 'degraded' ? '降级' :
                   currentHealth.overall_status === 'critical' ? '严重' : '未知'}
          </span>
        )}
      </div>

      {/* ── Health Trend Chart ────────────────────────────────── */}
      {!healthLoading && healthHistory && (
        <div className="mt-6">
          <div className="rounded-xl border border-border bg-card p-5 shadow-sm">
            <div className="flex items-center justify-between mb-3">
              <h2 className="text-sm font-semibold text-foreground">健康趋势（过去 {healthHistory.range_hours} 小时）</h2>
              <span className="text-[10px] text-muted-foreground">
                {healthHistory.source === 'sqlite' ? '来自数据库' : '模拟数据'} · {healthHistory.total} 个采样点
              </span>
            </div>
            <div ref={chartRef} className="h-52 w-full" />
          </div>
        </div>
      )}

      {/* ── Health Quick Stats + Service List ─────────────────── */}
      {currentHealth && (
        <div className="mt-6 grid gap-4 lg:grid-cols-3">
          {/* Quick Stats */}
          <div className="rounded-xl border border-border bg-card p-4 shadow-sm lg:col-span-1">
            <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-3">服务健康概览</h3>
            <div className="space-y-3">
              {healthStats.map((stat, i) => (
                <div key={i} className="flex items-center justify-between">
                  <span className="text-xs text-muted-foreground">{stat.label}</span>
                  <div className="text-right">
                    <p className={`text-sm font-bold ${stat.color}`}>{stat.value}</p>
                    <p className="text-[10px] text-muted-foreground">{stat.sub}</p>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Service List */}
          <div className="rounded-xl border border-border bg-card p-4 shadow-sm lg:col-span-2">
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">服务列表</h3>
              <span className="text-[10px] text-muted-foreground">
                {currentHealth.online_services}/{currentHealth.total_services} 在线
              </span>
            </div>
            <div className="space-y-1.5 max-h-64 overflow-y-auto pr-1">
              {currentHealth.services.map((svc) => (
                <div
                  key={svc.port}
                  className="flex items-center justify-between rounded-lg px-3 py-2 text-sm hover:bg-muted/30 transition-colors"
                >
                  <div className="flex items-center gap-2.5 min-w-0">
                    <span
                      className={`inline-block h-2 w-2 flex-shrink-0 rounded-full ${
                        svc.status === 'up' ? 'bg-green-500' : 'bg-red-500'
                      }`}
                    />
                    <span className="truncate font-medium text-foreground">{svc.name}</span>
                    <span className={`text-[10px] px-1.5 py-0.5 rounded-full border ${
                      svc.category === 'P0核心'
                        ? 'border-red-500/30 bg-red-500/10 text-red-600 dark:text-red-400'
                        : svc.category === 'P1扩展'
                          ? 'border-yellow-500/30 bg-yellow-500/10 text-yellow-600 dark:text-yellow-400'
                          : 'border-blue-500/30 bg-blue-500/10 text-blue-600 dark:text-blue-400'
                    }`}>
                      {svc.category}
                    </span>
                  </div>
                  <div className="flex items-center gap-3 flex-shrink-0">
                    <span className="text-xs text-muted-foreground">
                      {svc.status === 'up' ? `${svc.response_time_ms}ms` : '离线'}
                    </span>
                    <StatusBadge status={svc.status === 'up' ? 'active' : 'inactive'} />
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* ── Stats bar ─────────────────────────────────────────── */}
      <div className="mt-6 grid gap-4 sm:grid-cols-3">
        <div className="rounded-xl border border-border bg-card p-4">
          <p className="text-xs font-medium text-muted-foreground">总项目</p>
          <p className="mt-1 text-2xl font-bold">{totalProjects}</p>
        </div>
        <div className="rounded-xl border border-border bg-card p-4">
          <p className="text-xs font-medium text-muted-foreground">活跃中</p>
          <p className="mt-1 text-2xl font-bold text-green-600 dark:text-green-400">{activeProjects}</p>
        </div>
        <div className="rounded-xl border border-border bg-card p-4">
          <p className="text-xs font-medium text-muted-foreground">已完成</p>
          <p className="mt-1 text-2xl font-bold text-emerald-600 dark:text-emerald-400">{completedProjects}</p>
        </div>
      </div>

      {/* ── Card grid ─────────────────────────────────────────── */}
      {cards.length === 0 ? (
        <div className="mt-12 text-center text-sm text-muted-foreground">
          暂无数据
        </div>
      ) : (
        <CardGrid className="mt-6">
          {cards.map((item) => (
            <Card
              key={item.name}
              hoverable
              onClick={() => navigate(`/profile?name=${encodeURIComponent(item.name)}`)}
            >
              <div className="flex items-start justify-between gap-2">
                <h3 className="font-semibold truncate">{item.name}</h3>
                <StatusBadge status={item.status} />
              </div>
              {item.description && (
                <p className="mt-1.5 text-sm text-muted-foreground line-clamp-2">
                  {item.description}
                </p>
              )}
              {/* Progress bar */}
              {item.progress_pct !== undefined && item.progress_pct !== null && (
                <div className="mt-3">
                  <div className="flex items-center justify-between text-xs text-muted-foreground">
                    <span>进度</span>
                    <span>{item.progress_pct}%</span>
                  </div>
                  <div className="mt-1 h-1.5 w-full overflow-hidden rounded-full bg-secondary">
                    <div
                      className="h-full rounded-full bg-primary transition-all"
                      style={{ width: `${Math.min(100, Math.max(0, item.progress_pct))}%` }}
                    />
                  </div>
                </div>
              )}
              {item.updated_at && (
                <p className="mt-2 text-xs text-muted-foreground">
                  更新于 {new Date(item.updated_at).toLocaleString('zh-CN')}
                </p>
              )}
              <div className="mt-2">
                <span className="text-[10px] uppercase tracking-wider text-muted-foreground/60">
                  {item.source === 'profile' ? 'Profile' : '看板'}
                </span>
              </div>
            </Card>
          ))}
        </CardGrid>
      )}
    </div>
  )
}
