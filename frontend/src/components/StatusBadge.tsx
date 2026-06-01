import { cn } from '@/styles/utils'

interface StatusBadgeProps {
  status?: string
  className?: string
}

const statusColors: Record<string, string> = {
  active: 'bg-green-500/15 text-green-600 dark:text-green-400 border-green-500/30',
  inactive: 'bg-gray-500/15 text-gray-600 dark:text-gray-400 border-gray-500/30',
  archived: 'bg-yellow-500/15 text-yellow-600 dark:text-yellow-400 border-yellow-500/30',
  draft: 'bg-blue-500/15 text-blue-600 dark:text-blue-400 border-blue-500/30',
  completed: 'bg-emerald-500/15 text-emerald-600 dark:text-emerald-400 border-emerald-500/30',
  pending: 'bg-orange-500/15 text-orange-600 dark:text-orange-400 border-orange-500/30',
}

export default function StatusBadge({ status, className }: StatusBadgeProps) {
  if (!status) return null
  const color = statusColors[status.toLowerCase()] ?? 'bg-muted text-muted-foreground border-border'

  return (
    <span
      className={cn(
        'inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-medium',
        color,
        className,
      )}
    >
      {status}
    </span>
  )
}
