import { useEffect, useState, useCallback, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import StatusBadge from '@/components/StatusBadge'
import LoadingSpinner from '@/components/LoadingSpinner'
import ErrorMessage from '@/components/ErrorMessage'
import { cn } from '@/styles/utils'
import {
  Plus,
  Play,
  Square,
  ExternalLink,
  RefreshCw,
  Trash2,
  X,
  AlertCircle,
  CheckCircle2,
} from 'lucide-react'

// ── Types matching backend ProfileInfo ──

interface ProfileItem {
  name: string
  soul_summary?: string | null
  config?: Record<string, unknown>
  pid?: number | null
  port?: number | null
  running: boolean
}

interface CreateProfilePayload {
  name: string
  clone_from?: string | null
}

// ── API helper ──

const BASE = '/api'

async function apiFetch<T>(
  path: string,
  options?: RequestInit,
): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...options?.headers },
    ...options,
  })
  if (!res.ok) {
    const detail = await res.json().catch(() => null)
    throw new Error(detail?.detail ?? `${res.status} ${res.statusText}`)
  }
  return res.json() as Promise<T>
}

// ── Helpers ──

function deriveStatus(profile: ProfileItem): string {
  return profile.running ? 'active' : 'inactive'
}

function getLastActive(profile: ProfileItem): string {
  const cfg = profile.config ?? {}
  // Check common timestamp fields in config
  for (const key of ['last_active', 'updated_at', 'last_used', 'lastSeen']) {
    const val = cfg[key]
    if (val && typeof val === 'string') {
      try {
        return new Date(val).toLocaleString('zh-CN')
      } catch {
        // fall through
      }
    }
  }
  // Check nested metadata
  const meta = cfg['metadata'] as Record<string, unknown> | undefined
  if (meta) {
    for (const key of ['last_active', 'updated_at', 'last_used']) {
      const val = meta[key]
      if (val && typeof val === 'string') {
        try {
          return new Date(val).toLocaleString('zh-CN')
        } catch {
          // fall through
        }
      }
    }
  }
  return '—'
}

// ── Create Profile Modal ──

interface CreateModalProps {
  open: boolean
  onClose: () => void
  onCreated: () => void
  existingNames: string[]
}

function CreateProfileModal({ open, onClose, onCreated, existingNames }: CreateModalProps) {
  const [name, setName] = useState('')
  const [cloneFrom, setCloneFrom] = useState('')
  const [creating, setCreating] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)

  const reset = useCallback(() => {
    setName('')
    setCloneFrom('')
    setCreating(false)
    setError(null)
    setSuccess(null)
  }, [])

  useEffect(() => {
    if (!open) reset()
  }, [open, reset])

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    const trimmed = name.trim()
    if (!trimmed) {
      setError('请输入 Profile 名称')
      return
    }
    if (!/^[a-zA-Z0-9_-]+$/.test(trimmed)) {
      setError('名称只能包含字母、数字、下划线和连字符')
      return
    }
    if (existingNames.includes(trimmed)) {
      setError(`Profile "${trimmed}" 已存在`)
      return
    }

    setCreating(true)
    setError(null)
    setSuccess(null)

    try {
      const body: CreateProfilePayload = { name: trimmed }
      if (cloneFrom.trim()) body.clone_from = cloneFrom.trim()

      await apiFetch('/profiles', {
        method: 'POST',
        body: JSON.stringify(body),
      })

      setSuccess(`Profile "${trimmed}" 创建成功`)
      setTimeout(() => {
        reset()
        onClose()
        onCreated()
      }, 1200)
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setCreating(false)
    }
  }

  if (!open) return null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="w-full max-w-md rounded-xl border border-border bg-card p-6 shadow-xl">
        {/* Header */}
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold">创建新 Profile</h2>
          <button
            onClick={onClose}
            className="rounded-md p-1 text-muted-foreground hover:text-foreground transition-colors"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="mt-5 space-y-4">
          {/* Name */}
          <div>
            <label className="block text-sm font-medium text-foreground mb-1">
              Profile 名称 <span className="text-destructive">*</span>
            </label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="my-agent"
              disabled={creating}
              className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground/50 focus:outline-none focus:ring-2 focus:ring-ring disabled:opacity-50"
              autoFocus
            />
            <p className="mt-1 text-xs text-muted-foreground">
              只允许字母、数字、下划线、连字符
            </p>
          </div>

          {/* Clone from */}
          <div>
            <label className="block text-sm font-medium text-foreground mb-1">
              从已有 Profile 克隆配置（可选）
            </label>
            <input
              type="text"
              value={cloneFrom}
              onChange={(e) => setCloneFrom(e.target.value)}
              placeholder="existing-profile"
              disabled={creating}
              className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground/50 focus:outline-none focus:ring-2 focus:ring-ring disabled:opacity-50"
            />
          </div>

          {/* Feedback */}
          {error && (
            <div className="flex items-start gap-2 rounded-lg border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive">
              <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
              <span>{error}</span>
            </div>
          )}
          {success && (
            <div className="flex items-start gap-2 rounded-lg border border-green-500/30 bg-green-500/10 p-3 text-sm text-green-600 dark:text-green-400">
              <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0" />
              <span>{success}</span>
            </div>
          )}

          {/* Actions */}
          <div className="flex items-center justify-end gap-3 pt-2">
            <button
              type="button"
              onClick={onClose}
              disabled={creating}
              className="rounded-lg border border-border bg-card px-4 py-2 text-sm font-medium text-foreground hover:bg-secondary transition-colors disabled:opacity-50"
            >
              取消
            </button>
            <button
              type="submit"
              disabled={creating}
              className="inline-flex items-center gap-1.5 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 transition-colors disabled:opacity-50"
            >
              {creating ? (
                <>
                  <div className="h-4 w-4 animate-spin rounded-full border-2 border-current border-t-transparent" />
                  创建中...
                </>
              ) : (
                <>
                  <Plus className="h-4 w-4" />
                  创建
                </>
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

// ── Main ProfileManager Page ──

export default function ProfileManager() {
  const navigate = useNavigate()

  const [profiles, setProfiles] = useState<ProfileItem[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [showCreate, setShowCreate] = useState(false)
  const [actionLoading, setActionLoading] = useState<string | null>(null)

  // ── Fetch profiles ──

  const fetchProfiles = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await apiFetch<ProfileItem[]>('/profiles')
      setProfiles(data)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchProfiles()
  }, [fetchProfiles])

  // ── Start profile ──

  const handleStart = async (name: string) => {
    setActionLoading(name)
    try {
      await apiFetch(`/profiles/${encodeURIComponent(name)}/start`, {
        method: 'POST',
      })
      await fetchProfiles()
    } catch (e) {
      alert(`启动失败: ${(e as Error).message}`)
    } finally {
      setActionLoading(null)
    }
  }

  // ── Stop profile ──

  const handleStop = async (name: string) => {
    setActionLoading(name)
    try {
      await apiFetch(`/profiles/${encodeURIComponent(name)}/stop`, {
        method: 'POST',
      })
      await fetchProfiles()
    } catch (e) {
      alert(`停止失败: ${(e as Error).message}`)
    } finally {
      setActionLoading(null)
    }
  }

  // ── Delete profile ──

  const handleDelete = async (name: string) => {
    if (!confirm(`确定要删除 Profile "${name}" 吗？此操作不可撤销。`)) return
    setActionLoading(name)
    try {
      await apiFetch(`/profiles/${encodeURIComponent(name)}`, {
        method: 'DELETE',
      })
      await fetchProfiles()
    } catch (e) {
      alert(`删除失败: ${(e as Error).message}`)
    } finally {
      setActionLoading(null)
    }
  }

  // ── View detail ──

  const handleViewDetail = (name: string) => {
    navigate(`/profile?name=${encodeURIComponent(name)}`)
  }

  // ── Loading state ──

  if (loading) {
    return (
      <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6">
        <h1 className="text-2xl font-bold tracking-tight">Profile 管理</h1>
        <p className="mt-1 text-sm text-muted-foreground">加载中...</p>
        <LoadingSpinner className="mt-12" />
      </div>
    )
  }

  // ── Error state ──

  if (error) {
    return (
      <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6">
        <h1 className="text-2xl font-bold tracking-tight">Profile 管理</h1>
        <ErrorMessage message={`无法加载数据: ${error}`} onRetry={fetchProfiles} />
      </div>
    )
  }

  const isLoadingRow = (name: string) => actionLoading === name

  return (
    <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6">
      {/* ── Header ── */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Profile 管理</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            管理 Hermes 所有 Profile 的生命周期
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={fetchProfiles}
            className="inline-flex items-center gap-1.5 rounded-lg border border-border bg-card px-3 py-2 text-sm font-medium text-foreground hover:bg-secondary transition-colors"
            title="刷新"
          >
            <RefreshCw className="h-4 w-4" />
            刷新
          </button>
          <button
            onClick={() => setShowCreate(true)}
            className="inline-flex items-center gap-1.5 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 transition-colors"
          >
            <Plus className="h-4 w-4" />
            创建 Profile
          </button>
        </div>
      </div>

      {/* ── Stats bar ── */}
      <div className="mt-6 grid gap-4 sm:grid-cols-3">
        <div className="rounded-xl border border-border bg-card p-4">
          <p className="text-xs font-medium text-muted-foreground">总计</p>
          <p className="mt-1 text-2xl font-bold">{profiles.length}</p>
        </div>
        <div className="rounded-xl border border-border bg-card p-4">
          <p className="text-xs font-medium text-muted-foreground">运行中</p>
          <p className="mt-1 text-2xl font-bold text-green-600 dark:text-green-400">
            {profiles.filter((p) => p.running).length}
          </p>
        </div>
        <div className="rounded-xl border border-border bg-card p-4">
          <p className="text-xs font-medium text-muted-foreground">已停止</p>
          <p className="mt-1 text-2xl font-bold text-muted-foreground">
            {profiles.filter((p) => !p.running).length}
          </p>
        </div>
      </div>

      {/* ── Profile Table ── */}
      {profiles.length === 0 ? (
        <div className="mt-12 flex flex-col items-center gap-3 text-center">
          <div className="rounded-full border border-border bg-card p-4">
            <Plus className="h-8 w-8 text-muted-foreground" />
          </div>
          <p className="text-sm text-muted-foreground">暂无 Profile 数据</p>
          <button
            onClick={() => setShowCreate(true)}
            className="inline-flex items-center gap-1.5 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 transition-colors"
          >
            <Plus className="h-4 w-4" />
            创建第一个 Profile
          </button>
        </div>
      ) : (
        <div className="mt-6 overflow-hidden rounded-xl border border-border">
          <table className="w-full text-left text-sm">
            {/* Table Head */}
            <thead>
              <tr className="border-b border-border bg-muted/50">
                <th className="px-4 py-3 font-semibold text-foreground">名称</th>
                <th className="px-4 py-3 font-semibold text-foreground">状态</th>
                <th className="px-4 py-3 font-semibold text-foreground">端口</th>
                <th className="px-4 py-3 font-semibold text-foreground">最后活跃</th>
                <th className="px-4 py-3 font-semibold text-foreground text-right">操作</th>
              </tr>
            </thead>
            {/* Table Body */}
            <tbody>
              {profiles.map((profile) => {
                const loadingRow = isLoadingRow(profile.name)
                return (
                  <tr
                    key={profile.name}
                    className={cn(
                      'border-b border-border transition-colors last:border-b-0',
                      'hover:bg-muted/30',
                    )}
                  >
                    {/* Name */}
                    <td className="px-4 py-3">
                      <button
                        onClick={() => handleViewDetail(profile.name)}
                        className="font-medium text-foreground hover:text-primary transition-colors"
                      >
                        {profile.name}
                      </button>
                      {profile.soul_summary && (
                        <p className="mt-0.5 max-w-xs truncate text-xs text-muted-foreground">
                          {profile.soul_summary}
                        </p>
                      )}
                    </td>

                    {/* Status */}
                    <td className="px-4 py-3">
                      <StatusBadge status={deriveStatus(profile)} />
                      {profile.pid && (
                        <span className="ml-2 text-[11px] text-muted-foreground">
                          PID: {profile.pid}
                        </span>
                      )}
                    </td>

                    {/* Port */}
                    <td className="px-4 py-3">
                      {profile.port ? (
                        <code className="rounded bg-muted px-2 py-0.5 text-xs font-mono text-foreground">
                          :{profile.port}
                        </code>
                      ) : (
                        <span className="text-muted-foreground/50">—</span>
                      )}
                    </td>

                    {/* Last Active */}
                    <td className="px-4 py-3 text-muted-foreground">
                      {getLastActive(profile)}
                    </td>

                    {/* Actions */}
                    <td className="px-4 py-3">
                      <div className="flex items-center justify-end gap-1.5">
                        {/* Start */}
                        {!profile.running && (
                          <button
                            onClick={() => handleStart(profile.name)}
                            disabled={loadingRow}
                            className="inline-flex items-center gap-1 rounded-md border border-border px-2.5 py-1.5 text-xs font-medium text-foreground hover:bg-secondary transition-colors disabled:opacity-40"
                            title="启动"
                          >
                            {loadingRow ? (
                              <div className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-current border-t-transparent" />
                            ) : (
                              <Play className="h-3.5 w-3.5 text-green-500" />
                            )}
                            启动
                          </button>
                        )}

                        {/* Stop */}
                        {profile.running && (
                          <button
                            onClick={() => handleStop(profile.name)}
                            disabled={loadingRow}
                            className="inline-flex items-center gap-1 rounded-md border border-border px-2.5 py-1.5 text-xs font-medium text-foreground hover:bg-secondary transition-colors disabled:opacity-40"
                            title="停止"
                          >
                            {loadingRow ? (
                              <div className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-current border-t-transparent" />
                            ) : (
                              <Square className="h-3.5 w-3.5 text-orange-500" />
                            )}
                            停止
                          </button>
                        )}

                        {/* View Detail */}
                        <button
                          onClick={() => handleViewDetail(profile.name)}
                          className="inline-flex items-center gap-1 rounded-md border border-border px-2.5 py-1.5 text-xs font-medium text-foreground hover:bg-secondary transition-colors"
                          title="查看详情"
                        >
                          <ExternalLink className="h-3.5 w-3.5" />
                          详情
                        </button>

                        {/* Delete */}
                        <button
                          onClick={() => handleDelete(profile.name)}
                          disabled={loadingRow}
                          className="inline-flex items-center gap-1 rounded-md border border-destructive/30 px-2.5 py-1.5 text-xs font-medium text-destructive hover:bg-destructive/10 transition-colors disabled:opacity-40"
                          title="删除"
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </button>
                      </div>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* ── Create Modal ── */}
      <CreateProfileModal
        open={showCreate}
        onClose={() => setShowCreate(false)}
        onCreated={fetchProfiles}
        existingNames={profiles.map((p) => p.name)}
      />
    </div>
  )
}
