// Terminal store — 管理终端/Socket.IO 连接状态
import { create } from 'zustand'

export interface LogEntry {
  id: string
  timestamp: number
  level: 'info' | 'warn' | 'error' | 'debug'
  message: string
  source?: string
}

interface TerminalState {
  connected: boolean
  logs: LogEntry[]
  commandHistory: string[]

  // Actions
  setConnected: (connected: boolean) => void
  addLog: (entry: LogEntry) => void
  clearLogs: () => void
  addToHistory: (command: string) => void
  clearHistory: () => void
}

export const useTerminalStore = create<TerminalState>((set) => ({
  connected: false,
  logs: [],
  commandHistory: [],

  setConnected: (connected) => set({ connected }),
  addLog: (entry) =>
    set((state) => ({ logs: [...state.logs, entry].slice(-1000) })), // keep last 1000
  clearLogs: () => set({ logs: [] }),
  addToHistory: (command) =>
    set((state) => ({
      commandHistory: [...state.commandHistory, command].slice(-100),
    })),
  clearHistory: () => set({ commandHistory: [] }),
}))
