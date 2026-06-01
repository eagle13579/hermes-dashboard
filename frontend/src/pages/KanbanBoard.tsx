import { useEffect, useState, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import LoadingSpinner from '@/components/LoadingSpinner'
import ErrorMessage from '@/components/ErrorMessage'
import { cn } from '@/styles/utils'

// ── Types ──

type ColumnId = 'TODO' | 'IN_PROGRESS' | 'REVIEW' | 'DONE'

interface KanbanTask {
  project_name: string
  status: string
  description: string
  team_members: string[]
  progress_pct: number
  last_updated: string
  block_reason: string | null
}

interface ColumnDef {
  id: ColumnId
  title: string
  topBorderClass: string
}

// ── Constants ──

const COLUMNS: ColumnDef[] = [
  { id: 'TODO', title: '待办', topBorderClass: 'border-t-slate-500' },
  { id: 'IN_PROGRESS', title: '进行中', topBorderClass: 'border-t-blue-500' },
  { id: 'REVIEW', title: '审查', topBorderClass: 'border-t-amber-500' },
  { id: 'DONE', title: '完成', topBorderClass: 'border-t-emerald-500' },
]

/** Backend status → ColumnId mapping */
const STATUS_MAP: Record<string, ColumnId> = {
  planning: 'TODO',
  in_progress: 'IN_PROGRESS',
  review: 'REVIEW',
  done: 'DONE',
  blocked: 'TODO',
}

/** ColumnId → backend status for PUT updates */
const TO_BACKEND_STATUS: Record<ColumnId, string> = {
  TODO: 'planning',
  IN_PROGRESS: 'in_progress',
  REVIEW: 'review',
  DONE: 'done',
}

const BASE = '/api'

async function apiFetch<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
  return res.json() as Promise<T>
}

// ── Component ──

export default function KanbanBoard() {
  const navigate = useNavigate()
  const [tasks, setTasks] = useState<KanbanTask[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [draggedTask, setDraggedTask] = useState<string | null>(null)

  const fetchBoard = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await apiFetch<KanbanTask[]>('/kanban')
      setTasks(data)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchBoard()
  }, [fetchBoard])

  // ── Drag & Drop ──

  const handleDragStart = (projectName: string) => {
    setDraggedTask(projectName)
  }

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault()
  }

  const handleDrop = async (targetColumn: ColumnId) => {
    if (!draggedTask) return

    const task = tasks.find((t) => t.project_name === draggedTask)
    if (!task) return

    const currentCol = STATUS_MAP[task.status] ?? 'TODO'
    if (currentCol === targetColumn) {
      setDraggedTask(null)
      return
    }

    const newBackendStatus = TO_BACKEND_STATUS[targetColumn]
    const originalStatus = task.status

    // Optimistic update
    setTasks((prev) =>
      prev.map((t) =>
        t.project_name === draggedTask
          ? { ...t, status: newBackendStatus }
          : t,
      ),
    )
    setDraggedTask(null)

    try {
      await apiFetch(`/kanban/${encodeURIComponent(draggedTask)}/move`, {
        method: 'PUT',
        body: JSON.stringify({ status: newBackendStatus }),
      })
    } catch {
      // Revert on failure
      setTasks((prev) =>
        prev.map((t) =>
          t.project_name === draggedTask
            ? { ...t, status: originalStatus }
            : t,
        ),
      )
    }
  }

  const getTasksForColumn = (colId: ColumnId): KanbanTask[] =>
    tasks.filter((t) => (STATUS_MAP[t.status] ?? 'TODO') === colId)

  // ── Loading State ──

  if (loading) {
    return (
      <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6">
        <h1 className="text-2xl font-bold tracking-tight">看板</h1>
        <p className="mt-1 text-sm text-muted-foreground">加载中...</p>
        <LoadingSpinner className="mt-12" />
      </div>
    )
  }

  // ── Error State ──

  if (error) {
    return (
      <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6">
        <h1 className="text-2xl font-bold tracking-tight">看板</h1>
        <ErrorMessage
          message={`无法加载看板数据: ${error}`}
          onRetry={fetchBoard}
        />
      </div>
    )
  }

  // ── Render ──

  return (
    <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">看板</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            拖拽卡片以更新项目状态
          </p>
        </div>
      </div>

      {/* Board Columns */}
      <div className="mt-6 grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-4">
        {COLUMNS.map((col) => {
          const items = getTasksForColumn(col.id)
          return (
            <div
              key={col.id}
              onDragOver={handleDragOver}
              onDrop={() => handleDrop(col.id)}
              className={cn(
                'flex flex-col rounded-xl border border-border bg-card',
                'border-t-2',
                col.topBorderClass,
              )}
            >
              {/* Column Header */}
              <div className="flex items-center justify-between border-b border-border px-4 py-3">
                <h3 className="text-sm font-semibold">{col.title}</h3>
                <span className="inline-flex items-center justify-center rounded-full bg-secondary px-2 py-0.5 text-xs font-medium text-muted-foreground">
                  {items.length}
                </span>
              </div>

              {/* Task Cards */}
              <div className="flex-1 space-y-3 p-3 min-h-[200px]">
                {items.length === 0 ? (
                  <div className="flex h-24 items-center justify-center text-xs text-muted-foreground">
                    暂无任务
                  </div>
                ) : (
                  items.map((task) => (
                    <div
                      key={task.project_name}
                      draggable
                      onDragStart={() => handleDragStart(task.project_name)}
                      onClick={() =>
                        navigate(
                          `/profile?name=${encodeURIComponent(task.project_name)}`,
                        )
                      }
                      className={cn(
                        'cursor-grab active:cursor-grabbing rounded-lg border border-border bg-background p-3',
                        'transition-all hover:shadow-md hover:border-ring/30',
                        'select-none',
                        draggedTask === task.project_name && 'opacity-50',
                      )}
                    >
                      {/* Title */}
                      <h4 className="truncate text-sm font-medium">
                        {task.project_name}
                      </h4>

                      {/* Description */}
                      {task.description && (
                        <p className="mt-1 line-clamp-2 text-xs text-muted-foreground">
                          {task.description}
                        </p>
                      )}

                      {/* Progress Bar */}
                      <div className="mt-2">
                        <div className="flex items-center justify-between text-[10px] text-muted-foreground">
                          <span>进度</span>
                          <span>{task.progress_pct}%</span>
                        </div>
                        <div className="mt-0.5 h-1 w-full overflow-hidden rounded-full bg-secondary">
                          <div
                            className="h-full rounded-full bg-primary transition-all"
                            style={{
                              width: `${Math.min(100, Math.max(0, task.progress_pct))}%`,
                            }}
                          />
                        </div>
                      </div>

                      {/* Team + Blocked indicator */}
                      <div className="mt-2 flex items-center gap-2">
                        {task.team_members && task.team_members.length > 0 && (
                          <span className="text-[10px] text-muted-foreground">
                            {task.team_members.join(', ')}
                          </span>
                        )}
                        {task.block_reason && (
                          <span className="inline-flex items-center gap-0.5 rounded bg-red-500/10 px-1 py-0.5 text-[10px] font-medium text-red-600 dark:text-red-400">
                            阻塞
                          </span>
                        )}
                      </div>

                      {/* Timestamp */}
                      {task.last_updated && (
                        <p className="mt-1.5 text-[10px] text-muted-foreground/60">
                          {new Date(task.last_updated).toLocaleString('zh-CN')}
                        </p>
                      )}
                    </div>
                  ))
                )}
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
