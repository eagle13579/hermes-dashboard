import { useEffect, useRef, useState, useCallback } from 'react'
import LoadingSpinner from '@/components/LoadingSpinner'
import ErrorMessage from '@/components/ErrorMessage'
import StatusBadge from '@/components/StatusBadge'
import * as echarts from 'echarts'
import { Users, Wifi, Cpu, Search, UserPlus, UserCheck, UserX, Filter } from 'lucide-react'

// ── Types ─────────────────────────────────────────────────────────────

interface LegionStats {
  total_employees: number
  elite_count: number
  standard_count: number
  shell_count: number
  online_services: number
  services_total: number
  active_profiles: number
  total_profiles: number
  imported_skills: number
}

interface LegionOverview {
  legion_stats: LegionStats
  health_pct: number
  generated_at: string
}

interface EmployeeInfo {
  name: string
  employee_id: string
  level: string
  department: string
  type: string
  status: string
  soul_level: string
  has_awakening: boolean
  mental_models: string[]
  emotional_anchors: { anchor: string; strength: string }[]
  capabilities: string[]
}

interface EmployeesResponse {
  items: EmployeeInfo[]
  total: number
  page: number
  page_size: number
  total_pages: number
}

interface SoulDistribution {
  elite: number
  standard: number
  shell: number
  with_awakening: number
  total_souls: number
}

// ── Helpers ───────────────────────────────────────────────────────────

const BASE = '/api'

async function apiFetch<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`)
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
  return res.json() as Promise<T>
}

const SOUL_META: Record<string, { label: string; color: string; icon: typeof Users }> = {
  elite: { label: '精锐', color: '#8b5cf6', icon: UserCheck },
  standard: { label: '标准', color: '#3b82f6', icon: UserPlus },
  shell: { label: '空壳', color: '#64748b', icon: UserX },
}

function getSoulLabel(level: string): string {
  return SOUL_META[level]?.label ?? level
}

// ── Component ─────────────────────────────────────────────────────────

export default function LegionPage() {
  const chartRef = useRef<HTMLDivElement>(null)
  const chartInstance = useRef<echarts.ECharts | null>(null)

  // Overview
  const [overview, setOverview] = useState<LegionOverview | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Employees
  const [employees, setEmployees] = useState<EmployeeInfo[]>([])
  const [totalEmployees, setTotalEmployees] = useState(0)
  const [currentPage, setCurrentPage] = useState(1)
  const [totalPages, setTotalPages] = useState(1)
  const [employeesLoading, setEmployeesLoading] = useState(false)

  // Soul distribution
  const [soulDist, setSoulDist] = useState<SoulDistribution | null>(null)

  // Filters
  const [searchQuery, setSearchQuery] = useState('')
  const [soulFilter, setSoulFilter] = useState('')

  // ── Fetch Data ──────────────────────────────────────────────────────

  const fetchOverview = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [overviewData, soulData] = await Promise.all([
        apiFetch<LegionOverview>('/legion/overview'),
        apiFetch<SoulDistribution>('/legion/soul-distribution').catch(() => null),
      ])
      setOverview(overviewData)
      setSoulDist(soulData)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setLoading(false)
    }
  }, [])

  const fetchEmployees = useCallback(async (page: number) => {
    setEmployeesLoading(true)
    try {
      const data = await apiFetch<EmployeesResponse>(
        `/legion/employees?page=${page}&page_size=50`
      )
      setEmployees(data.items ?? [])
      setTotalEmployees(data.total ?? 0)
      setCurrentPage(data.page ?? 1)
      setTotalPages(data.total_pages ?? 1)
    } catch {
      // employees are non-critical
    } finally {
      setEmployeesLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchOverview()
    fetchEmployees(1)
  }, [fetchOverview, fetchEmployees])

  // ── ECharts Pie ─────────────────────────────────────────────────────

  useEffect(() => {
    if (!chartRef.current) return

    if (chartInstance.current) {
      chartInstance.current.dispose()
    }

    const chart = echarts.init(chartRef.current, undefined, { renderer: 'canvas' })
    chartInstance.current = chart

    const dist = soulDist ?? {
      elite: overview?.legion_stats?.elite_count ?? 0,
      standard: overview?.legion_stats?.standard_count ?? 0,
      shell: overview?.legion_stats?.shell_count ?? 0,
      with_awakening: 0,
      total_souls: 0,
    }

    const total = dist.elite + dist.standard + dist.shell
    const pieData = [
      { value: dist.elite, name: `精锐 (${dist.elite})`, itemStyle: { color: '#8b5cf6' } },
      { value: dist.standard, name: `标准 (${dist.standard})`, itemStyle: { color: '#3b82f6' } },
      { value: dist.shell, name: `空壳 (${dist.shell})`, itemStyle: { color: '#64748b' } },
    ].filter((d) => d.value > 0)

    const option: echarts.EChartsOption = {
      backgroundColor: 'transparent',
      tooltip: {
        trigger: 'item',
        backgroundColor: 'rgba(15, 23, 42, 0.9)',
        borderColor: 'rgba(148, 163, 184, 0.2)',
        textStyle: { color: '#e2e8f0', fontSize: 12 },
        formatter: '{b}: {c} ({d}%)',
      },
      series: [
        {
          type: 'pie',
          radius: ['42%', '70%'],
          center: ['50%', '50%'],
          avoidLabelOverlap: true,
          padAngle: 2,
          itemStyle: {
            borderRadius: 4,
            borderColor: 'rgba(15, 23, 42, 0.8)',
            borderWidth: 2,
          },
          label: {
            show: total > 0,
            color: '#94a3b8',
            fontSize: 11,
            formatter: '{b}',
          },
          labelLine: {
            lineStyle: { color: 'rgba(148, 163, 184, 0.3)' },
          },
          emphasis: {
            label: { show: true, fontSize: 13, fontWeight: 'bold' },
            itemStyle: {
              shadowBlur: 10,
              shadowOffsetX: 0,
              shadowColor: 'rgba(0, 0, 0, 0.5)',
            },
          },
          data: pieData.length > 0 ? pieData : [{ value: 1, name: '暂无数据', itemStyle: { color: '#334155' } }],
        },
      ],
    }

    chart.setOption(option)

    const observer = new ResizeObserver(() => chart.resize())
    observer.observe(chartRef.current)

    return () => {
      observer.disconnect()
      chart.dispose()
      chartInstance.current = null
    }
  }, [soulDist, overview])

  // ── Derived ─────────────────────────────────────────────────────────

  const stats = overview?.legion_stats

  const employeeCards = employees
    .filter((e) => {
      if (searchQuery && !e.name.toLowerCase().includes(searchQuery.toLowerCase())) return false
      if (soulFilter && e.soul_level !== soulFilter) return false
      return true
    })

  // ── Loading State ───────────────────────────────────────────────────

  if (loading) {
    return (
      <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6">
        <h1 className="text-2xl font-bold tracking-tight">AI 数智军团</h1>
        <p className="mt-1 text-sm text-muted-foreground">加载中...</p>
        <LoadingSpinner className="mt-12" />
      </div>
    )
  }

  // ── Error State ─────────────────────────────────────────────────────

  if (error) {
    return (
      <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6">
        <h1 className="text-2xl font-bold tracking-tight">AI 数智军团</h1>
        <ErrorMessage message={error} onRetry={fetchOverview} />
      </div>
    )
  }

  // ── Main Render ─────────────────────────────────────────────────────

  return (
    <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6">
      {/* Header */}
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">AI 数智军团</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            军团状态总览 · 员工管理 · 灵魂分布
          </p>
        </div>
        {/* Health badge */}
        {overview && (
          <span className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-medium ${
            overview.health_pct >= 80
              ? 'border-green-500/30 bg-green-500/15 text-green-600 dark:text-green-400'
              : overview.health_pct >= 50
                ? 'border-yellow-500/30 bg-yellow-500/15 text-yellow-600 dark:text-yellow-400'
                : 'border-red-500/30 bg-red-500/15 text-red-600 dark:text-red-400'
          }`}>
            <span className={`inline-block h-2 w-2 rounded-full ${
              overview.health_pct >= 80 ? 'bg-green-500' :
              overview.health_pct >= 50 ? 'bg-yellow-500' : 'bg-red-500'
            }`} />
            军团健康度 {overview.health_pct}%
          </span>
        )}
      </div>

      {/* ── Stats Cards ──────────────────────────────────────────────── */}
      {stats && (
        <div className="mb-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <div className="rounded-xl border border-border bg-card p-4 shadow-sm">
            <div className="flex items-center gap-2 text-muted-foreground mb-2">
              <Users className="h-4 w-4" />
              <span className="text-xs font-medium">总员工</span>
            </div>
            <p className="text-2xl font-bold">{stats.total_employees}</p>
            <div className="mt-1 flex items-center gap-2 text-[11px] text-muted-foreground">
              <span className="text-purple-400">精锐 {stats.elite_count}</span>
              <span className="text-blue-400">标准 {stats.standard_count}</span>
              <span className="text-gray-400">空壳 {stats.shell_count}</span>
            </div>
          </div>

          <div className="rounded-xl border border-border bg-card p-4 shadow-sm">
            <div className="flex items-center gap-2 text-muted-foreground mb-2">
              <Wifi className="h-4 w-4" />
              <span className="text-xs font-medium">在线服务</span>
            </div>
            <p className="text-2xl font-bold">
              {stats.online_services}
              <span className="text-sm font-normal text-muted-foreground"> / {stats.services_total}</span>
            </p>
            <p className="mt-1 text-[11px] text-muted-foreground">
              注册服务总计
            </p>
          </div>

          <div className="rounded-xl border border-border bg-card p-4 shadow-sm">
            <div className="flex items-center gap-2 text-muted-foreground mb-2">
              <Cpu className="h-4 w-4" />
              <span className="text-xs font-medium">Profile</span>
            </div>
            <p className="text-2xl font-bold">
              {stats.active_profiles}
              <span className="text-sm font-normal text-muted-foreground"> / {stats.total_profiles}</span>
            </p>
            <p className="mt-1 text-[11px] text-muted-foreground">
              活跃 / 总计
            </p>
          </div>

          <div className="rounded-xl border border-border bg-card p-4 shadow-sm">
            <div className="flex items-center gap-2 text-muted-foreground mb-2">
              <Users className="h-4 w-4" />
              <span className="text-xs font-medium">已导入技能</span>
            </div>
            <p className="text-2xl font-bold">{stats.imported_skills}</p>
            <p className="mt-1 text-[11px] text-muted-foreground">
              Dashboard Skill
            </p>
          </div>
        </div>
      )}

      {/* ── Chart + Soul Distribution ────────────────────────────────── */}
      <div className="mb-8 grid gap-6 lg:grid-cols-3">
        {/* Pie Chart */}
        <div className="rounded-xl border border-border bg-card p-5 shadow-sm lg:col-span-1">
          <h3 className="text-sm font-semibold text-foreground mb-3">灵魂等级分布</h3>
          <div ref={chartRef} className="h-64 w-full" />
        </div>

        {/* Quick breakdown */}
        <div className="rounded-xl border border-border bg-card p-5 shadow-sm lg:col-span-2">
          <h3 className="text-sm font-semibold text-foreground mb-4">灵魂质量详情</h3>
          {soulDist ? (
            <div className="space-y-3">
              <div className="flex items-center justify-between rounded-lg bg-purple-500/5 px-4 py-3">
                <div className="flex items-center gap-3">
                  <div className="flex h-8 w-8 items-center justify-center rounded-full bg-purple-500/20">
                    <UserCheck className="h-4 w-4 text-purple-400" />
                  </div>
                  <div>
                    <p className="text-sm font-medium text-foreground">精锐员工</p>
                    <p className="text-[11px] text-muted-foreground">有独立灵魂 + 觉醒记录</p>
                  </div>
                </div>
                <span className="text-xl font-bold text-purple-400">{soulDist.elite}</span>
              </div>

              <div className="flex items-center justify-between rounded-lg bg-blue-500/5 px-4 py-3">
                <div className="flex items-center gap-3">
                  <div className="flex h-8 w-8 items-center justify-center rounded-full bg-blue-500/20">
                    <UserPlus className="h-4 w-4 text-blue-400" />
                  </div>
                  <div>
                    <p className="text-sm font-medium text-foreground">标准员工</p>
                    <p className="text-[11px] text-muted-foreground">有基本灵魂配置</p>
                  </div>
                </div>
                <span className="text-xl font-bold text-blue-400">{soulDist.standard}</span>
              </div>

              <div className="flex items-center justify-between rounded-lg bg-gray-500/5 px-4 py-3">
                <div className="flex items-center gap-3">
                  <div className="flex h-8 w-8 items-center justify-center rounded-full bg-gray-500/20">
                    <UserX className="h-4 w-4 text-gray-400" />
                  </div>
                  <div>
                    <p className="text-sm font-medium text-foreground">空壳员工</p>
                    <p className="text-[11px] text-muted-foreground">仅目录结构，无灵魂</p>
                  </div>
                </div>
                <span className="text-xl font-bold text-gray-400">{soulDist.shell}</span>
              </div>

              <div className="mt-4 flex items-center justify-between border-t border-border pt-3 text-xs text-muted-foreground">
                <span>有觉醒记录</span>
                <span className="font-medium text-foreground">{soulDist.with_awakening} 人</span>
              </div>
            </div>
          ) : stats ? (
            <div className="space-y-3">
              <div className="flex items-center justify-between rounded-lg bg-purple-500/5 px-4 py-3">
                <span className="text-sm text-foreground">精锐</span>
                <span className="text-xl font-bold text-purple-400">{stats.elite_count}</span>
              </div>
              <div className="flex items-center justify-between rounded-lg bg-blue-500/5 px-4 py-3">
                <span className="text-sm text-foreground">标准</span>
                <span className="text-xl font-bold text-blue-400">{stats.standard_count}</span>
              </div>
              <div className="flex items-center justify-between rounded-lg bg-gray-500/5 px-4 py-3">
                <span className="text-sm text-foreground">空壳</span>
                <span className="text-xl font-bold text-gray-400">{stats.shell_count}</span>
              </div>
            </div>
          ) : (
            <p className="text-sm text-muted-foreground text-center py-8">暂无数据</p>
          )}
        </div>
      </div>

      {/* ── Employee List ────────────────────────────────────────────── */}
      <div className="rounded-xl border border-border bg-card p-5 shadow-sm">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-5">
          <h3 className="text-sm font-semibold text-foreground">
            员工列表
            <span className="ml-2 text-xs font-normal text-muted-foreground">
              ({totalEmployees} 人)
            </span>
          </h3>

          <div className="flex items-center gap-2">
            {/* Soul level filter */}
            <div className="relative">
              <select
                value={soulFilter}
                onChange={(e) => setSoulFilter(e.target.value)}
                className="h-8 appearance-none rounded-lg border border-border bg-background pl-3 pr-7 text-xs text-foreground focus:border-primary/50 focus:outline-none focus:ring-2 focus:ring-primary/20 transition-all"
              >
                <option value="">全部等级</option>
                <option value="elite">精锐</option>
                <option value="standard">标准</option>
                <option value="shell">空壳</option>
              </select>
              <Filter className="pointer-events-none absolute right-2 top-1/2 h-3 w-3 -translate-y-1/2 text-muted-foreground" />
            </div>

            {/* Search */}
            <div className="relative">
              <Search className="absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="搜索员工..."
                className="h-8 w-48 rounded-lg border border-border bg-background pl-9 pr-3 text-xs text-foreground placeholder:text-muted-foreground/60 focus:border-primary/50 focus:outline-none focus:ring-2 focus:ring-primary/20 transition-all"
              />
            </div>
          </div>
        </div>

        {/* Table */}
        {employeesLoading ? (
          <LoadingSpinner />
        ) : employeeCards.length === 0 ? (
          <p className="py-8 text-center text-sm text-muted-foreground">
            {searchQuery || soulFilter ? '没有匹配的员工' : '暂无员工数据'}
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border">
                  <th className="py-2.5 pr-4 text-left text-xs font-medium text-muted-foreground">姓名</th>
                  <th className="py-2.5 pr-4 text-left text-xs font-medium text-muted-foreground">ID</th>
                  <th className="py-2.5 pr-4 text-left text-xs font-medium text-muted-foreground">等级</th>
                  <th className="py-2.5 pr-4 text-left text-xs font-medium text-muted-foreground">部门</th>
                  <th className="py-2.5 pr-4 text-left text-xs font-medium text-muted-foreground">类型</th>
                  <th className="py-2.5 pr-4 text-left text-xs font-medium text-muted-foreground">灵魂等级</th>
                  <th className="py-2.5 pr-4 text-left text-xs font-medium text-muted-foreground">状态</th>
                  <th className="py-2.5 text-left text-xs font-medium text-muted-foreground">心智模型</th>
                </tr>
              </thead>
              <tbody>
                {employeeCards.map((emp) => (
                  <tr key={emp.employee_id} className="border-b border-border/50 hover:bg-muted/20 transition-colors">
                    <td className="py-3 pr-4 font-medium text-foreground">{emp.name}</td>
                    <td className="py-3 pr-4 text-xs text-muted-foreground font-mono">{emp.employee_id}</td>
                    <td className="py-3 pr-4 text-xs">{emp.level || '-'}</td>
                    <td className="py-3 pr-4 text-xs text-muted-foreground">{emp.department || '-'}</td>
                    <td className="py-3 pr-4 text-xs text-muted-foreground">{emp.type || '-'}</td>
                    <td className="py-3 pr-4">
                      <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-medium ${
                        emp.soul_level === 'elite'
                          ? 'bg-purple-500/10 text-purple-400'
                          : emp.soul_level === 'standard'
                            ? 'bg-blue-500/10 text-blue-400'
                            : 'bg-gray-500/10 text-gray-400'
                      }`}>
                        {getSoulLabel(emp.soul_level)}
                      </span>
                    </td>
                    <td className="py-3 pr-4">
                      <StatusBadge status={emp.status} />
                    </td>
                    <td className="py-3 text-xs">
                      <div className="flex flex-wrap gap-1">
                        {(emp.mental_models ?? []).length > 0
                          ? emp.mental_models.slice(0, 2).map((m, i) => (
                              <span key={i} className="rounded-md bg-secondary/50 px-1.5 py-0.5 text-[10px] text-muted-foreground">
                                {m}
                              </span>
                            ))
                          : <span className="text-muted-foreground/60">-</span>
                        }
                        {(emp.mental_models ?? []).length > 2 && (
                          <span className="text-[10px] text-muted-foreground/60">
                            +{emp.mental_models.length - 2}
                          </span>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* Pagination */}
        {totalPages > 1 && (
          <div className="flex items-center justify-between mt-4 pt-4 border-t border-border">
            <span className="text-xs text-muted-foreground">
              第 {currentPage} / {totalPages} 页
            </span>
            <div className="flex items-center gap-2">
              <button
                onClick={() => fetchEmployees(Math.max(1, currentPage - 1))}
                disabled={currentPage <= 1}
                className="rounded-lg border border-border bg-background px-3 py-1.5 text-xs font-medium text-foreground hover:bg-secondary disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
              >
                上一页
              </button>
              <button
                onClick={() => fetchEmployees(Math.min(totalPages, currentPage + 1))}
                disabled={currentPage >= totalPages}
                className="rounded-lg border border-border bg-background px-3 py-1.5 text-xs font-medium text-foreground hover:bg-secondary disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
              >
                下一页
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
