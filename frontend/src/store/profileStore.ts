import { create } from 'zustand'

// ── Shared API types ──

export interface ProjectItem {
  name: string
  description?: string
  status?: string
  progress_pct?: number
  updated_at?: string
  created_at?: string
}

export interface KanbanItem {
  project: string
  title?: string
  status?: string
  progress_pct?: number
  updated_at?: string
}

export interface ProfileDetail {
  name: string
  description?: string
  status?: string
  created_at?: string
  updated_at?: string
}

export interface SoulData {
  identity?: Record<string, unknown>
  mental_models?: Record<string, unknown>
  capabilities?: string[]
  [key: string]: unknown
}

export interface SkillItem {
  name: string
  description?: string
  category?: string
  level?: string
}

export interface PalaceSkill {
  name: string
  description?: string
  category?: string
  level?: string
  palace?: string
}

export interface LibraryItem {
  id: string
  title: string
  category?: string
  summary?: string
  tags?: string[]
  source?: string
}

export interface ProductItem {
  name: string
  description?: string
  status?: string
  version?: string
  updated_at?: string
}

// ── Profile State ──

interface ProfileState {
  // Profile list
  profiles: ProjectItem[]
  profilesLoading: boolean
  profilesError: string | null

  // Selected profile detail
  selectedProfile: ProfileDetail | null
  profileLoading: boolean
  profileError: string | null

  // Soul data
  soulData: SoulData | null
  soulLoading: boolean
  soulError: string | null

  // Skills
  skills: SkillItem[]
  skillsLoading: boolean
  skillsError: string | null

  // Memory
  memory: unknown
  memoryLoading: boolean
  memoryError: string | null

  // Kanban
  kanbanProjects: KanbanItem[]
  kanbanSingle: KanbanItem | null
  kanbanLoading: boolean
  kanbanError: string | null

  // Palace
  palaceSkills: PalaceSkill[]
  palaceSkillsLoading: boolean
  palaceSkillsError: string | null
  library: LibraryItem[]
  libraryLoading: boolean
  libraryError: string | null
  products: ProductItem[]
  productsLoading: boolean
  productsError: string | null

  // Legion
  legionOverview: unknown
  legionEmployees: unknown
  legionLoading: boolean
  legionError: string | null

  // Actions
  fetchProfiles: () => Promise<void>
  fetchProfile: (name: string) => Promise<void>
  fetchSoul: (name: string) => Promise<void>
  fetchSkills: (name: string) => Promise<void>
  fetchMemory: (name: string) => Promise<void>
  fetchKanbanProjects: () => Promise<void>
  fetchKanbanSingle: (project: string) => Promise<void>
  fetchPalaceSkills: () => Promise<void>
  fetchLibrary: () => Promise<void>
  fetchProducts: () => Promise<void>
  fetchLegionOverview: () => Promise<void>
  fetchLegionEmployees: () => Promise<void>
}

const BASE = '/api'

async function apiFetch<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`)
  if (!res.ok) {
    throw new Error(`${res.status} ${res.statusText}`)
  }
  return res.json() as Promise<T>
}

export const useProfileStore = create<ProfileState>((set) => ({
  // Initial state
  profiles: [],
  profilesLoading: false,
  profilesError: null,
  selectedProfile: null,
  profileLoading: false,
  profileError: null,
  soulData: null,
  soulLoading: false,
  soulError: null,
  skills: [],
  skillsLoading: false,
  skillsError: null,
  memory: null,
  memoryLoading: false,
  memoryError: null,
  kanbanProjects: [],
  kanbanSingle: null,
  kanbanLoading: false,
  kanbanError: null,
  palaceSkills: [],
  palaceSkillsLoading: false,
  palaceSkillsError: null,
  library: [],
  libraryLoading: false,
  libraryError: null,
  products: [],
  productsLoading: false,
  productsError: null,
  legionOverview: null,
  legionEmployees: null,
  legionLoading: false,
  legionError: null,

  // ── Actions ──

  fetchProfiles: async () => {
    set({ profilesLoading: true, profilesError: null })
    try {
      const data = await apiFetch<ProjectItem[]>('/profiles')
      set({ profiles: data, profilesLoading: false })
    } catch (e) {
      set({ profilesError: (e as Error).message, profilesLoading: false })
    }
  },

  fetchProfile: async (name: string) => {
    set({ profileLoading: true, profileError: null })
    try {
      const data = await apiFetch<ProfileDetail>(`/profiles/${name}`)
      set({ selectedProfile: data, profileLoading: false })
    } catch (e) {
      set({ profileError: (e as Error).message, profileLoading: false })
    }
  },

  fetchSoul: async (name: string) => {
    set({ soulLoading: true, soulError: null })
    try {
      const data = await apiFetch<SoulData>(`/profiles/${name}/soul`)
      set({ soulData: data, soulLoading: false })
    } catch (e) {
      set({ soulError: (e as Error).message, soulLoading: false })
    }
  },

  fetchSkills: async (name: string) => {
    set({ skillsLoading: true, skillsError: null })
    try {
      const data = await apiFetch<SkillItem[]>(`/profiles/${name}/skills`)
      set({ skills: data, skillsLoading: false })
    } catch (e) {
      set({ skillsError: (e as Error).message, skillsLoading: false })
    }
  },

  fetchMemory: async (name: string) => {
    set({ memoryLoading: true, memoryError: null })
    try {
      const data = await apiFetch<unknown>(`/profiles/${name}/memory`)
      set({ memory: data, memoryLoading: false })
    } catch (e) {
      set({ memoryError: (e as Error).message, memoryLoading: false })
    }
  },

  fetchKanbanProjects: async () => {
    set({ kanbanLoading: true, kanbanError: null })
    try {
      const data = await apiFetch<KanbanItem[]>('/kanban')
      set({ kanbanProjects: data, kanbanLoading: false })
    } catch (e) {
      set({ kanbanError: (e as Error).message, kanbanLoading: false })
    }
  },

  fetchKanbanSingle: async (project: string) => {
    set({ kanbanLoading: true, kanbanError: null })
    try {
      const data = await apiFetch<KanbanItem>(`/kanban/${project}`)
      set({ kanbanSingle: data, kanbanLoading: false })
    } catch (e) {
      set({ kanbanError: (e as Error).message, kanbanLoading: false })
    }
  },

  fetchPalaceSkills: async () => {
    set({ palaceSkillsLoading: true, palaceSkillsError: null })
    try {
      const data = await apiFetch<PalaceSkill[]>('/palace/skills')
      set({ palaceSkills: data, palaceSkillsLoading: false })
    } catch (e) {
      set({ palaceSkillsError: (e as Error).message, palaceSkillsLoading: false })
    }
  },

  fetchLibrary: async () => {
    set({ libraryLoading: true, libraryError: null })
    try {
      const data = await apiFetch<LibraryItem[]>('/palace/library')
      set({ library: data, libraryLoading: false })
    } catch (e) {
      set({ libraryError: (e as Error).message, libraryLoading: false })
    }
  },

  fetchProducts: async () => {
    set({ productsLoading: true, productsError: null })
    try {
      const data = await apiFetch<ProductItem[]>('/palace/products')
      set({ products: data, productsLoading: false })
    } catch (e) {
      set({ productsError: (e as Error).message, productsLoading: false })
    }
  },

  fetchLegionOverview: async () => {
    set({ legionLoading: true, legionError: null })
    try {
      const data = await apiFetch<unknown>('/legion/overview')
      set({ legionOverview: data, legionLoading: false })
    } catch (e) {
      set({ legionError: (e as Error).message, legionLoading: false })
    }
  },

  fetchLegionEmployees: async () => {
    set({ legionLoading: true, legionError: null })
    try {
      const data = await apiFetch<unknown>('/legion/employees')
      set({ legionEmployees: data, legionLoading: false })
    } catch (e) {
      set({ legionError: (e as Error).message, legionLoading: false })
    }
  },
}))
