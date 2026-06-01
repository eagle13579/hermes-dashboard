import { useEffect, useState, useCallback } from 'react'
import { useSearchParams, useNavigate } from 'react-router-dom'
import Tabs from '@/components/Tabs'
import StatusBadge from '@/components/StatusBadge'
import { Card } from '@/components/Card'
import LoadingSpinner from '@/components/LoadingSpinner'
import ErrorMessage from '@/components/ErrorMessage'
import LogViewer from '@/components/LogViewer'
import type {
  ProfileDetail,
  SoulData,
  SkillItem,
  KanbanItem,
} from '@/store/profileStore'
import { Link } from 'react-router-dom'

const BASE = '/api'

async function apiFetch<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`)
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
  return res.json() as Promise<T>
}

/* ── Profile Selector (when no name param) ── */
function ProfileSelector() {
  const navigate = useNavigate()
  const [profiles, setProfiles] = useState<{ name: string; description?: string; status?: string }[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const fetchProfiles = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await apiFetch<{ name: string; description?: string; status?: string }[]>('/profiles')
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

  if (loading) return <LoadingSpinner className="mt-16" />
  if (error) return <ErrorMessage message={error} onRetry={fetchProfiles} />

  return (
    <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6">
      <h1 className="text-2xl font-bold tracking-tight">Profile 工作台</h1>
      <p className="mt-1 text-sm text-muted-foreground">请选择一个 Profile 查看详情</p>

      {profiles.length === 0 ? (
        <div className="mt-12 text-center text-sm text-muted-foreground">暂无 Profile 数据</div>
      ) : (
        <div className="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {profiles.map((p) => (
            <Card
              key={p.name}
              hoverable
              onClick={() => navigate(`/profile?name=${encodeURIComponent(p.name)}`)}
            >
              <div className="flex items-start justify-between gap-2">
                <h3 className="font-semibold">{p.name}</h3>
                <StatusBadge status={p.status} />
              </div>
              {p.description && (
                <p className="mt-1.5 text-sm text-muted-foreground line-clamp-2">{p.description}</p>
              )}
            </Card>
          ))}
        </div>
      )}
    </div>
  )
}

/* ── Sub-components for tabs ── */

function SoulTab({ name }: { name: string }) {
  const [data, setData] = useState<SoulData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const fetchData = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const d = await apiFetch<SoulData>(`/profiles/${name}/soul`)
      setData(d)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setLoading(false)
    }
  }, [name])

  useEffect(() => { fetchData() }, [fetchData])

  if (loading) return <LoadingSpinner />
  if (error) return <ErrorMessage message={error} onRetry={fetchData} />

  if (!data) return <p className="text-sm text-muted-foreground">无 SOUL 数据</p>

  return (
    <div className="space-y-6">
      {/* Identity */}
      {data.identity && (
        <section>
          <h3 className="mb-2 text-sm font-semibold text-muted-foreground uppercase tracking-wider">Identity</h3>
          <pre className="overflow-auto rounded-lg border border-border bg-muted/50 p-4 text-xs leading-relaxed">
            {JSON.stringify(data.identity, null, 2)}
          </pre>
        </section>
      )}

      {/* Mental Models */}
      {data.mental_models && (
        <section>
          <h3 className="mb-2 text-sm font-semibold text-muted-foreground uppercase tracking-wider">Mental Models</h3>
          <pre className="overflow-auto rounded-lg border border-border bg-muted/50 p-4 text-xs leading-relaxed">
            {JSON.stringify(data.mental_models, null, 2)}
          </pre>
        </section>
      )}

      {/* Capabilities */}
      {data.capabilities && data.capabilities.length > 0 && (
        <section>
          <h3 className="mb-2 text-sm font-semibold text-muted-foreground uppercase tracking-wider">Capabilities</h3>
          <div className="flex flex-wrap gap-2">
            {data.capabilities.map((cap) => (
              <span
                key={cap}
                className="rounded-full border border-border bg-card px-3 py-1 text-xs font-medium"
              >
                {cap}
              </span>
            ))}
          </div>
        </section>
      )}

      {/* Other fields */}
      {Object.entries(data)
        .filter(([key]) => !['identity', 'mental_models', 'capabilities'].includes(key))
        .map(([key, value]) => (
          <section key={key}>
            <h3 className="mb-2 text-sm font-semibold text-muted-foreground uppercase tracking-wider">
              {key}
            </h3>
            <pre className="overflow-auto rounded-lg border border-border bg-muted/50 p-4 text-xs leading-relaxed">
              {typeof value === 'string' ? value : JSON.stringify(value, null, 2)}
            </pre>
          </section>
        ))}
    </div>
  )
}

function SkillsTab({ name }: { name: string }) {
  const [data, setData] = useState<SkillItem[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const fetchData = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const d = await apiFetch<SkillItem[]>(`/profiles/${name}/skills`)
      setData(d ?? [])
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setLoading(false)
    }
  }, [name])

  useEffect(() => { fetchData() }, [fetchData])

  if (loading) return <LoadingSpinner />
  if (error) return <ErrorMessage message={error} onRetry={fetchData} />

  if (data.length === 0) return <p className="text-sm text-muted-foreground">无技能数据</p>

  return (
    <div className="space-y-3">
      {data.map((skill, idx) => (
        <Card key={skill.name ?? idx}>
          <div className="flex items-start justify-between gap-2">
            <h3 className="font-medium">{skill.name}</h3>
            {skill.level && <StatusBadge status={skill.level} />}
          </div>
          {skill.description && (
            <p className="mt-1 text-sm text-muted-foreground">{skill.description}</p>
          )}
          {skill.category && (
            <p className="mt-1.5 text-xs text-muted-foreground/70">分类: {skill.category}</p>
          )}
        </Card>
      ))}
    </div>
  )
}

function KanbanTab({ name }: { name: string }) {
  const [data, setData] = useState<KanbanItem | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const fetchData = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const d = await apiFetch<KanbanItem>(`/kanban/${name}`)
      setData(d)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setLoading(false)
    }
  }, [name])

  useEffect(() => { fetchData() }, [fetchData])

  if (loading) return <LoadingSpinner />
  if (error) return <ErrorMessage message={error} onRetry={fetchData} />

  if (!data) return <p className="text-sm text-muted-foreground">无看板数据</p>

  return (
    <div className="space-y-4">
      <Card>
        <div className="flex items-start justify-between gap-2">
          <h3 className="font-semibold">{data.project}</h3>
          <StatusBadge status={data.status} />
        </div>
        {data.title && <p className="mt-1.5 text-sm text-muted-foreground">{data.title}</p>}
        {data.progress_pct !== undefined && data.progress_pct !== null && (
          <div className="mt-3">
            <div className="flex items-center justify-between text-xs text-muted-foreground">
              <span>进度</span>
              <span>{data.progress_pct}%</span>
            </div>
            <div className="mt-1 h-1.5 w-full overflow-hidden rounded-full bg-secondary">
              <div
                className="h-full rounded-full bg-primary transition-all"
                style={{ width: `${Math.min(100, Math.max(0, data.progress_pct))}%` }}
              />
            </div>
          </div>
        )}
        {data.updated_at && (
          <p className="mt-2 text-xs text-muted-foreground">
            更新于 {new Date(data.updated_at).toLocaleString('zh-CN')}
          </p>
        )}
      </Card>
    </div>
  )
}

/* ── Profile Detail View (when name param present) ── */
function ProfileDetailView({ name }: { name: string }) {
  const [profile, setProfile] = useState<ProfileDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const fetchProfile = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const d = await apiFetch<ProfileDetail>(`/profiles/${name}`)
      setProfile(d)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setLoading(false)
    }
  }, [name])

  useEffect(() => { fetchProfile() }, [fetchProfile])

  if (loading) return <LoadingSpinner className="mt-16" />
  if (error) return <ErrorMessage message={error} onRetry={fetchProfile} />

  return (
    <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6">
      {/* Header */}
      <div className="flex items-center gap-3">
        <Link
          to="/profile"
          className="text-sm text-muted-foreground hover:text-foreground transition-colors"
        >
          &larr; 返回
        </Link>
        <h1 className="text-2xl font-bold tracking-tight">{profile?.name ?? name}</h1>
        <StatusBadge status={profile?.status} />
      </div>
      {profile?.description && (
        <p className="mt-1 text-sm text-muted-foreground ml-9">{profile.description}</p>
      )}

      {/* Tabs */}
      <div className="mt-6">
        <Tabs
          tabs={[
            { value: 'soul', label: 'SOUL', content: <SoulTab name={name} /> },
            { value: 'skills', label: '技能', content: <SkillsTab name={name} /> },
            { value: 'kanban', label: '看板', content: <KanbanTab name={name} /> },
            { value: 'logs', label: '日志', content: <LogViewer profileName={name} /> },
          ]}
        />
      </div>
    </div>
  )
}

/* ── Main Export ── */
export default function ProfileWorkspace() {
  const [searchParams] = useSearchParams()
  const name = searchParams.get('name')

  if (name) {
    return <ProfileDetailView name={name} />
  }

  return <ProfileSelector />
}
