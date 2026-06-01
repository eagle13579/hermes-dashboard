import { Link, useLocation } from 'react-router-dom'
import { cn } from '@/styles/utils'
import { LayoutDashboard, User, Database, Kanban, Settings2, GitBranch } from 'lucide-react'

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
      </div>
    </header>
  )
}
