import { Link, useLocation, useNavigate } from 'react-router-dom'
import { cn } from '@/styles/utils'
import { LayoutDashboard, User, Database, Kanban, Settings2, GitBranch, LogOut, LogIn } from 'lucide-react'
import { useState, useEffect } from 'react'

const navItems = [
  { to: '/', label: '首页', icon: LayoutDashboard },
  { to: '/kanban', label: '看板', icon: Kanban },
  { to: '/rules', label: '规则', icon: GitBranch },
  { to: '/profiles', label: 'Profile 管理', icon: Settings2 },
  { to: '/profile', label: 'Profile 工作台', icon: User },
  { to: '/data', label: '数据浏览器', icon: Database },
]

export default function Navbar() {
  const location = useLocation()
  const navigate = useNavigate()
  const [user, setUser] = useState<{ username: string; role: string } | null>(null)

  useEffect(() => {
    const stored = localStorage.getItem('auth_user')
    if (stored) {
      try {
        setUser(JSON.parse(stored))
      } catch {
        setUser(null)
      }
    }
  }, [location.pathname])

  const handleLogout = () => {
    localStorage.removeItem('auth_token')
    localStorage.removeItem('auth_user')
    navigate('/login', { replace: true })
  }

  const isLoggedIn = !!localStorage.getItem('auth_token')
  if (!isLoggedIn) return null

  return (
    <header className="sticky top-0 z-50 w-full border-b border-border bg-background/80 backdrop-blur-sm">
      <div className="mx-auto flex h-14 max-w-7xl items-center justify-between px-4 sm:px-6">
        <Link to="/" className="flex items-center gap-2 font-semibold tracking-tight">
          <span className="flex h-7 w-7 items-center justify-center rounded-md bg-primary text-xs font-bold text-primary-foreground">
            H
          </span>
          Hermes Dashboard
        </Link>
        <nav className="flex items-center gap-1">
          {navItems.map((item) => {
            const Icon = item.icon
            const isActive = location.pathname === item.to
            return (
              <Link
                key={item.to}
                to={item.to}
                className={cn(
                  'inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-medium transition-colors',
                  isActive
                    ? 'bg-secondary text-foreground'
                    : 'text-muted-foreground hover:text-foreground hover:bg-secondary/50',
                )}
              >
                <Icon className="h-4 w-4" />
                {item.label}
              </Link>
            )
          })}
        </nav>
        <div className="flex items-center gap-3">
          {user && (
            <span className="hidden text-xs text-muted-foreground sm:inline">
              <span className="font-medium text-foreground">{user.username}</span>
              <span className="ml-1.5 rounded bg-secondary px-1.5 py-0.5 text-[10px] uppercase">
                {user.role}
              </span>
            </span>
          )}
          <button
            onClick={handleLogout}
            className="inline-flex items-center gap-1 rounded-md px-2 py-1.5 text-sm text-muted-foreground transition-colors hover:text-foreground hover:bg-secondary/50"
            title="退出登录"
          >
            <LogOut className="h-4 w-4" />
            <span className="hidden sm:inline">退出</span>
          </button>
        </div>
      </div>
    </header>
  )
}
