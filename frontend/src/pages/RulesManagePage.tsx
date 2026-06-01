import { useEffect, useState, useCallback } from 'react'
import LoadingSpinner from '@/components/LoadingSpinner'
import ErrorMessage from '@/components/ErrorMessage'
import { cn } from '@/styles/utils'

// ── Types ──

interface AutoRule {
  id: number | null
  name: string
  trigger_event: string
  condition: string
  action: string
  enabled: boolean
}

interface RuleFormData {
  name: string
  trigger_event: string
  condition: string
  action: string
  enabled: boolean
}

const TRIGGER_EVENTS = [
  { value: 'task_created', label: '任务创建' },
  { value: 'task_moved', label: '任务移动' },
  { value: 'task_blocked', label: '任务阻塞' },
  { value: 'deadline_approaching', label: '截止日期临近' },
]

const ACTION_PRESETS = [
  { value: 'move_to(review)', label: '移动到: 审查(review)' },
  { value: 'move_to(done)', label: '移动到: 完成(done)' },
  { value: 'move_to(in_progress)', label: '移动到: 进行中(in_progress)' },
  { value: 'move_to(blocked)', label: '移动到: 阻塞(blocked)' },
  { value: 'assign_to(Bob)', label: '指派给: Bob' },
  { value: 'assign_to(Alice)', label: '指派给: Alice' },
  { value: 'add_label(needs_review)', label: '添加标签: needs_review' },
  { value: 'add_label(urgent)', label: '添加标签: urgent' },
  { value: 'notify(slack)', label: '通知: Slack' },
  { value: 'notify(email)', label: '通知: Email' },
  { value: 'notify(feishu)', label: '通知: 飞书(Feishu)' },
]

const CONDITION_PRESETS = [
  { value: 'status == done', label: '状态 == done' },
  { value: 'status == in_progress', label: '状态 == in_progress' },
  { value: 'status == blocked', label: '状态 == blocked' },
  { value: 'status == review', label: '状态 == review' },
  { value: 'assignee == Bob', label: '负责人 == Bob' },
  { value: 'assignee == Alice', label: '负责人 == Alice' },
  { value: 'priority == high', label: '优先级 == high' },
  { value: 'priority == medium', label: '优先级 == medium' },
  { value: 'priority == low', label: '优先级 == low' },
]

const TRIGGER_LABELS: Record<string, string> = {
  task_created: '任务创建',
  task_moved: '任务移动',
  task_blocked: '任务阻塞',
  deadline_approaching: '截止日期临近',
}

const BASE = '/api'

async function apiFetch<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText)
    throw new Error(`${res.status} ${text}`)
  }
  return res.json() as Promise<T>
}

const emptyForm: RuleFormData = {
  name: '',
  trigger_event: 'task_moved',
  condition: '',
  action: 'move_to(review)',
  enabled: true,
}

// ── Component ──

export default function RulesManagePage() {
  const [rules, setRules] = useState<AutoRule[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [showForm, setShowForm] = useState(false)
  const [editingId, setEditingId] = useState<number | null>(null)
  const [form, setForm] = useState<RuleFormData>(emptyForm)
  const [saving, setSaving] = useState(false)

  const fetchRules = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await apiFetch<AutoRule[]>('/kanban/rules')
      setRules(data)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchRules()
  }, [fetchRules])

  const handleToggle = async (rule: AutoRule) => {
    const newEnabled = !rule.enabled
    try {
      const updated = await apiFetch<AutoRule>(`/kanban/rules/${rule.id}`, {
        method: 'PUT',
        body: JSON.stringify({ enabled: newEnabled }),
      })
      setRules((prev) =>
        prev.map((r) => (r.id === rule.id ? updated : r)),
      )
    } catch (e) {
      setError((e as Error).message)
    }
  }

  const handleDelete = async (ruleId: number) => {
    try {
      await apiFetch(`/kanban/rules/${ruleId}`, { method: 'DELETE' })
      setRules((prev) => prev.filter((r) => r.id !== ruleId))
    } catch (e) {
      setError((e as Error).message)
    }
  }

  const handleEdit = (rule: AutoRule) => {
    setForm({
      name: rule.name,
      trigger_event: rule.trigger_event,
      condition: rule.condition,
      action: rule.action,
      enabled: rule.enabled,
    })
    setEditingId(rule.id)
    setShowForm(true)
  }

  const handleNew = () => {
    setForm(emptyForm)
    setEditingId(null)
    setShowForm(true)
  }

  const handleSave = async () => {
    if (!form.name.trim()) return
    setSaving(true)
    try {
      if (editingId !== null) {
        const updated = await apiFetch<AutoRule>(`/kanban/rules/${editingId}`, {
          method: 'PUT',
          body: JSON.stringify(form),
        })
        setRules((prev) =>
          prev.map((r) => (r.id === editingId ? updated : r)),
        )
      } else {
        const created = await apiFetch<AutoRule>('/kanban/rules', {
          method: 'POST',
          body: JSON.stringify(form),
        })
        setRules((prev) => [...prev, created])
      }
      setShowForm(false)
      setEditingId(null)
      setForm(emptyForm)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setSaving(false)
    }
  }

  const handleCancel = () => {
    setShowForm(false)
    setEditingId(null)
    setForm(emptyForm)
  }

  // ── Render helpers ──

  const renderActionPreview = (action: string) => {
    if (action.startsWith('move_to(')) return '📦 移动状态'
    if (action.startsWith('assign_to(')) return '👤 指派成员'
    if (action.startsWith('add_label(')) return '🏷️ 添加标签'
    if (action.startsWith('notify(')) return '🔔 发送通知'
    return '⚙️ ' + action
  }

  // ── Loading ──

  if (loading) {
    return (
      <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6">
        <h1 className="text-2xl font-bold tracking-tight">自动规则引擎</h1>
        <p className="mt-1 text-sm text-muted-foreground">加载规则列表...</p>
        <LoadingSpinner className="mt-12" />
      </div>
    )
  }

  if (error && rules.length === 0) {
    return (
      <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6">
        <h1 className="text-2xl font-bold tracking-tight">自动规则引擎</h1>
        <ErrorMessage message={`无法加载规则: ${error}`} onRetry={fetchRules} />
      </div>
    )
  }

  // ── Render ──

  return (
    <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">自动规则引擎</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            定义当看板任务发生变化时的自动触发规则
          </p>
        </div>
        <button
          onClick={handleNew}
          className="inline-flex items-center gap-1.5 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground shadow-sm transition-colors hover:bg-primary/90"
        >
          <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 4v16m8-8H4" />
          </svg>
          新建规则
        </button>
      </div>

      {/* Error banner */}
      {error && (
        <div className="mt-4 rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-2 text-sm text-red-600 dark:text-red-400">
          {error}
          <button onClick={() => setError(null)} className="ml-2 underline">关闭</button>
        </div>
      )}

      {/* New/Edit Form */}
      {showForm && (
        <div className="mt-6 rounded-xl border border-border bg-card p-6 shadow-sm">
          <h2 className="text-lg font-semibold">
            {editingId !== null ? '编辑规则' : '新建规则'}
          </h2>
          <div className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {/* Name */}
            <div>
              <label className="block text-sm font-medium text-muted-foreground">规则名称</label>
              <input
                type="text"
                value={form.name}
                onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
                placeholder="例如: 完成自动审查"
                className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-2 text-sm placeholder:text-muted-foreground/40 focus:outline-none focus:ring-1 focus:ring-ring"
              />
            </div>
            {/* Trigger Event */}
            <div>
              <label className="block text-sm font-medium text-muted-foreground">触发事件</label>
              <select
                value={form.trigger_event}
                onChange={(e) => setForm((f) => ({ ...f, trigger_event: e.target.value }))}
                className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
              >
                {TRIGGER_EVENTS.map((ev) => (
                  <option key={ev.value} value={ev.value}>
                    {ev.label}
                  </option>
                ))}
              </select>
            </div>
            {/* Condition */}
            <div>
              <label className="block text-sm font-medium text-muted-foreground">条件</label>
              <div className="mt-1 flex gap-2">
                <input
                  type="text"
                  value={form.condition}
                  onChange={(e) => setForm((f) => ({ ...f, condition: e.target.value }))}
                  placeholder="例如: status == done"
                  className="flex-1 rounded-lg border border-border bg-background px-3 py-2 text-sm placeholder:text-muted-foreground/40 focus:outline-none focus:ring-1 focus:ring-ring"
                />
              </div>
              <div className="mt-1 flex flex-wrap gap-1">
                {CONDITION_PRESETS.slice(0, 4).map((preset) => (
                  <button
                    key={preset.value}
                    type="button"
                    onClick={() => setForm((f) => ({ ...f, condition: preset.value }))}
                    className={cn(
                      'rounded px-1.5 py-0.5 text-[10px] transition-colors',
                      form.condition === preset.value
                        ? 'bg-primary text-primary-foreground'
                        : 'bg-secondary text-muted-foreground hover:text-foreground',
                    )}
                  >
                    {preset.label}
                  </button>
                ))}
              </div>
            </div>
            {/* Action */}
            <div>
              <label className="block text-sm font-medium text-muted-foreground">动作</label>
              <select
                value={form.action}
                onChange={(e) => setForm((f) => ({ ...f, action: e.target.value }))}
                className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
              >
                {ACTION_PRESETS.map((act) => (
                  <option key={act.value} value={act.value}>
                    {act.label}
                  </option>
                ))}
              </select>
              {form.action === 'notify(feishu)' && (
                <p className="mt-1.5 text-xs text-amber-600 dark:text-amber-400">
                  ⚠️ 飞书通知需在 <code className="rounded bg-secondary px-1 py-0.5 font-mono text-[10px]">.env</code> 中配置
                  <code className="rounded bg-secondary px-1 py-0.5 font-mono text-[10px]">FEISHU_APP_ID</code>、
                  <code className="rounded bg-secondary px-1 py-0.5 font-mono text-[10px]">FEISHU_APP_SECRET</code> 和
                  <code className="rounded bg-secondary px-1 py-0.5 font-mono text-[10px]">FEISHU_HOME_CHANNEL</code>
                </p>
              )}
            </div>
          </div>
          {/* Form Actions */}
          <div className="mt-4 flex items-center gap-3">
            <button
              onClick={handleSave}
              disabled={saving || !form.name.trim()}
              className={cn(
                'inline-flex items-center gap-1.5 rounded-lg px-4 py-2 text-sm font-medium shadow-sm transition-colors',
                saving || !form.name.trim()
                  ? 'bg-muted text-muted-foreground cursor-not-allowed'
                  : 'bg-primary text-primary-foreground hover:bg-primary/90',
              )}
            >
              {saving ? '保存中...' : editingId !== null ? '更新规则' : '创建规则'}
            </button>
            <button
              onClick={handleCancel}
              className="rounded-lg border border-border bg-background px-4 py-2 text-sm font-medium text-muted-foreground transition-colors hover:text-foreground"
            >
              取消
            </button>
          </div>
        </div>
      )}

      {/* Rules List */}
      <div className="mt-6 space-y-3">
        {rules.length === 0 ? (
          <div className="flex flex-col items-center justify-center rounded-xl border border-dashed border-border py-16">
            <svg className="h-12 w-12 text-muted-foreground/30" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.066 2.573c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.573 1.066c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.066-2.573c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
              <path strokeLinecap="round" strokeLinejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
            </svg>
            <p className="mt-4 text-sm text-muted-foreground">暂无自动规则</p>
            <p className="text-xs text-muted-foreground/60">点击"新建规则"开始自动化看板流程</p>
          </div>
        ) : (
          rules.map((rule) => (
            <div
              key={rule.id}
              className={cn(
                'flex flex-col gap-3 rounded-xl border p-4 transition-colors sm:flex-row sm:items-center sm:justify-between',
                rule.enabled
                  ? 'border-border bg-card'
                  : 'border-border/50 bg-card/50 opacity-60',
              )}
            >
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <h3 className="truncate text-sm font-semibold">{rule.name}</h3>
                  <span
                    className={cn(
                      'inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-medium',
                      rule.enabled
                        ? 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400'
                        : 'bg-muted text-muted-foreground',
                    )}
                  >
                    {rule.enabled ? '启用' : '禁用'}
                  </span>
                </div>
                <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                  <span className="inline-flex items-center gap-1 rounded bg-secondary px-1.5 py-0.5">
                    📡 {TRIGGER_LABELS[rule.trigger_event] ?? rule.trigger_event}
                  </span>
                  <span className="text-muted-foreground/40">→</span>
                  <span className="inline-flex items-center gap-1 rounded bg-secondary px-1.5 py-0.5 font-mono text-[10px]">
                    if {rule.condition}
                  </span>
                  <span className="text-muted-foreground/40">→</span>
                  <span className="inline-flex items-center gap-1 rounded bg-secondary px-1.5 py-0.5">
                    {renderActionPreview(rule.action)}
                    <span className="font-mono text-[10px]">{rule.action}</span>
                  </span>
                </div>
              </div>

              {/* Actions */}
              <div className="flex items-center gap-2 shrink-0">
                {/* Toggle Switch */}
                <button
                  onClick={() => handleToggle(rule)}
                  className={cn(
                    'relative inline-flex h-5 w-9 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors focus:outline-none',
                    rule.enabled ? 'bg-emerald-500' : 'bg-muted',
                  )}
                >
                  <span
                    className={cn(
                      'pointer-events-none inline-block h-4 w-4 rounded-full bg-white shadow-sm transition-transform',
                      rule.enabled ? 'translate-x-4' : 'translate-x-0',
                    )}
                  />
                </button>
                {/* Edit */}
                <button
                  onClick={() => handleEdit(rule)}
                  className="rounded-lg p-1.5 text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
                  title="编辑"
                >
                  <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
                  </svg>
                </button>
                {/* Delete */}
                <button
                  onClick={() => rule.id !== null && handleDelete(rule.id)}
                  className="rounded-lg p-1.5 text-muted-foreground transition-colors hover:bg-red-500/10 hover:text-red-500"
                  title="删除"
                >
                  <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                  </svg>
                </button>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  )
}
