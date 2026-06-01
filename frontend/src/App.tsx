import { Routes, Route, Navigate } from 'react-router-dom'
import { Navbar } from '@/components'
import HomePage from '@/pages/HomePage.tsx'
import ProfileWorkspace from '@/pages/ProfileWorkspace.tsx'
import ProfileManager from '@/pages/ProfileManager.tsx'
import DataBrowser from '@/pages/DataBrowser.tsx'
import KanbanBoard from '@/pages/KanbanBoard.tsx'
import RulesManagePage from '@/pages/RulesManagePage.tsx'
import LoginPage from '@/pages/LoginPage.tsx'

function App() {
  const isLoggedIn = !!localStorage.getItem('auth_token')

  if (!isLoggedIn) {
    return (
      <div className="min-h-screen bg-background text-foreground">
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="*" element={<Navigate to="/login" replace />} />
        </Routes>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-background text-foreground">
      <Navbar />
      <main>
        <Routes>
          <Route path="/" element={<HomePage />} />
          <Route path="/profile" element={<ProfileWorkspace />} />
          <Route path="/profiles" element={<ProfileManager />} />
          <Route path="/data" element={<DataBrowser />} />
          <Route path="/kanban" element={<KanbanBoard />} />
          <Route path="/rules" element={<RulesManagePage />} />
          <Route path="/login" element={<LoginPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
    </div>
  )
}

export default App
