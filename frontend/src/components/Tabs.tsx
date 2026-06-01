import * as TabsPrimitive from '@radix-ui/react-tabs'
import { cn } from '@/styles/utils'
import type { ReactNode } from 'react'

interface TabItem {
  value: string
  label: string
  content: ReactNode
}

interface TabsProps {
  tabs: TabItem[]
  defaultValue?: string
  className?: string
}

export default function Tabs({ tabs, defaultValue, className }: TabsProps) {
  const defaultVal = defaultValue ?? tabs[0]?.value
  if (!defaultVal || tabs.length === 0) return null

  return (
    <TabsPrimitive.Root defaultValue={defaultVal} className={cn('w-full', className)}>
      <TabsPrimitive.List className="inline-flex h-10 w-full items-center gap-0.5 border-b border-border">
        {tabs.map((tab) => (
          <TabsPrimitive.Trigger
            key={tab.value}
            value={tab.value}
            className={cn(
              'inline-flex items-center justify-center whitespace-nowrap rounded-t-md px-4 py-2 text-sm font-medium transition-all',
              'text-muted-foreground hover:text-foreground',
              'data-[state=active]:bg-card data-[state=active]:text-foreground data-[state=active]:border-b-2 data-[state=active]:border-primary',
            )}
          >
            {tab.label}
          </TabsPrimitive.Trigger>
        ))}
      </TabsPrimitive.List>
      {tabs.map((tab) => (
        <TabsPrimitive.Content key={tab.value} value={tab.value} className="mt-4">
          {tab.content}
        </TabsPrimitive.Content>
      ))}
    </TabsPrimitive.Root>
  )
}
