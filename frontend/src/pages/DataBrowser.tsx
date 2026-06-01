import { useEffect, useState, useCallback } from 'react'
import Tabs from '@/components/Tabs'
import StatusBadge from '@/components/StatusBadge'
import { Card, CardGrid } from '@/components/Card'
import LoadingSpinner from '@/components/LoadingSpinner'
import ErrorMessage from '@/components/ErrorMessage'
import type { PalaceSkill, LibraryItem, ProductItem } from '@/store/profileStore'

const BASE = '/api'

async function apiFetch<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`)
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
  return res.json() as Promise<T>
}

/* ── Palace Skills Tab ── */
function PalaceSkillsTab() {
  const [data, setData] = useState<PalaceSkill[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const fetchData = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const d = await apiFetch<PalaceSkill[]>('/palace/skills')
      setData(d ?? [])
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { fetchData() }, [fetchData])

  if (loading) return <LoadingSpinner />
  if (error) return <ErrorMessage message={error} onRetry={fetchData} />

  if (data.length === 0) return <p className="text-sm text-muted-foreground py-8 text-center">暂无技能数据</p>

  return (
    <CardGrid>
      {data.map((skill, idx) => (
        <Card key={skill.name ?? idx}>
          <div className="flex items-start justify-between gap-2">
            <h3 className="font-medium">{skill.name}</h3>
            {skill.level && <StatusBadge status={skill.level} />}
          </div>
          {skill.description && (
            <p className="mt-1.5 text-sm text-muted-foreground line-clamp-2">{skill.description}</p>
          )}
          <div className="mt-3 flex flex-wrap gap-1.5">
            {skill.category && (
              <span className="rounded-full bg-secondary px-2 py-0.5 text-[11px] font-medium text-muted-foreground">
                {skill.category}
              </span>
            )}
            {skill.palace && (
              <span className="rounded-full bg-secondary px-2 py-0.5 text-[11px] font-medium text-muted-foreground">
                {skill.palace}
              </span>
            )}
          </div>
        </Card>
      ))}
    </CardGrid>
  )
}

/* ── Library Tab ── */
function LibraryTab() {
  const [data, setData] = useState<LibraryItem[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const fetchData = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const d = await apiFetch<LibraryItem[]>('/palace/library')
      setData(d ?? [])
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { fetchData() }, [fetchData])

  if (loading) return <LoadingSpinner />
  if (error) return <ErrorMessage message={error} onRetry={fetchData} />

  if (data.length === 0) return <p className="text-sm text-muted-foreground py-8 text-center">暂无图书馆资源</p>

  return (
    <div className="space-y-3">
      {data.map((item, idx) => (
        <Card key={item.id ?? idx}>
          <div className="flex items-start justify-between gap-2">
            <h3 className="font-medium">{item.title ?? item.id}</h3>
            {item.category && <StatusBadge status={item.category} />}
          </div>
          {item.summary && (
            <p className="mt-1.5 text-sm text-muted-foreground">{item.summary}</p>
          )}
          <div className="mt-3 flex flex-wrap items-center gap-2">
            {item.tags && item.tags.length > 0 && (
              <div className="flex flex-wrap gap-1.5">
                {item.tags.map((tag) => (
                  <span
                    key={tag}
                    className="rounded-full border border-border bg-card px-2 py-0.5 text-[11px] text-muted-foreground"
                  >
                    #{tag}
                  </span>
                ))}
              </div>
            )}
            {item.source && (
              <span className="text-[11px] text-muted-foreground/60">来源: {item.source}</span>
            )}
          </div>
        </Card>
      ))}
    </div>
  )
}

/* ── Products Tab ── */
function ProductsTab() {
  const [data, setData] = useState<ProductItem[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const fetchData = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const d = await apiFetch<ProductItem[]>('/palace/products')
      setData(d ?? [])
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { fetchData() }, [fetchData])

  if (loading) return <LoadingSpinner />
  if (error) return <ErrorMessage message={error} onRetry={fetchData} />

  if (data.length === 0) return <p className="text-sm text-muted-foreground py-8 text-center">暂无产品数据</p>

  return (
    <CardGrid>
      {data.map((item, idx) => (
        <Card key={item.name ?? idx}>
          <div className="flex items-start justify-between gap-2">
            <h3 className="font-medium">{item.name}</h3>
            {item.status && <StatusBadge status={item.status} />}
          </div>
          {item.description && (
            <p className="mt-1.5 text-sm text-muted-foreground line-clamp-3">{item.description}</p>
          )}
          <div className="mt-3 flex items-center gap-3 text-xs text-muted-foreground">
            {item.version && <span>v{item.version}</span>}
            {item.updated_at && (
              <span>更新于 {new Date(item.updated_at).toLocaleDateString('zh-CN')}</span>
            )}
          </div>
        </Card>
      ))}
    </CardGrid>
  )
}

/* ── Main Export ── */
export default function DataBrowser() {
  return (
    <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6">
      <h1 className="text-2xl font-bold tracking-tight">数据浏览器</h1>
      <p className="mt-1 text-sm text-muted-foreground">
        浏览和分析主宫殿知识库数据
      </p>

      <div className="mt-6">
        <Tabs
          tabs={[
            { value: 'skills', label: '主宫殿技能', content: <PalaceSkillsTab /> },
            { value: 'library', label: 'L1图书馆', content: <LibraryTab /> },
            { value: 'products', label: 'L5产品', content: <ProductsTab /> },
          ]}
        />
      </div>
    </div>
  )
}
