import { useState, useRef, useEffect } from 'react'
import { BrowserRouter, Routes, Route, NavLink, Link, useNavigate, useLocation, Navigate } from 'react-router-dom'
import { ChevronDown, Settings as SettingsIcon, LogOut, BarChart3, Github } from 'lucide-react'
import { Dashboard } from './pages/Dashboard'
import { Briefs } from './pages/Briefs'
import { BriefDetail } from './pages/BriefDetail'
import { Drafts } from './pages/Drafts'
import { DraftDetail } from './pages/DraftDetail'
import { PublishDraft } from './pages/PublishDraft'
import { Prompts } from './pages/Prompts'
import { PromptDetail } from './pages/PromptDetail'
import { GeneratePrompts } from './pages/GeneratePrompts'
import { Reports } from './pages/Reports'
import { Domains } from './pages/Domains'
import { Monitoring } from './pages/Monitoring'
import { HowItWorks } from './pages/HowItWorks'
import { TrialDirectory } from './pages/TrialDirectory'
import { MonitoringExecutionDetail } from './pages/MonitoringExecutionDetail'
import { PromptGeneration } from './pages/PromptGeneration'
import { Settings } from './pages/Settings'
import { ContentSources } from './pages/ContentSources'
import { Signin } from './pages/Signin'
import { Signup } from './pages/Signup'
import { TryTrial } from './pages/TryTrial'
import { Terms } from './pages/Terms'
import { AuthProvider } from './context/AuthContext'
import { useAuth } from './context/useAuth'
import { PageMeta } from './components/PageMeta'
import './App.css'

function HomePage() {
  const { token, loading } = useAuth()
  if (loading) {
    return (
      <div className="page dashboard">
        <p className="auth-loading">Loading…</p>
      </div>
    )
  }
  if (token) {
    return <Dashboard />
  }
  return <TryTrial />
}

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { token, loading } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()

  if (loading) {
    return (
      <div className="page dashboard">
        <p className="auth-loading">Loading…</p>
      </div>
    )
  }
  if (!token) {
    navigate('/signin', { replace: true, state: { from: location } })
    return (
      <div className="page dashboard">
        <p className="auth-loading">Redirecting to sign in…</p>
      </div>
    )
  }
  return <>{children}</>
}

function UserDropdown() {
  const { user, logout } = useAuth()
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    if (open) {
      document.addEventListener('mousedown', handleClickOutside)
      return () => document.removeEventListener('mousedown', handleClickOutside)
    }
  }, [open])

  return (
    <div className="app-header-user" ref={ref}>
      <button
        type="button"
        className="app-header-user-trigger"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        aria-haspopup="true"
      >
        <span className="app-header-user-name">{user?.name || user?.email || 'Account'}</span>
        <ChevronDown className="app-header-icon" size={16} aria-hidden />
      </button>
      {open && (
        <div className="app-header-user-menu" role="menu">
          <div className="app-header-user-email" title={user?.email}>{user?.email}</div>
          <NavLink to="/settings" className="app-header-user-item" role="menuitem" onClick={() => setOpen(false)}>
            <SettingsIcon size={16} className="app-header-item-icon" aria-hidden />
            Settings
          </NavLink>
          <button type="button" className="app-header-user-item app-header-user-signout" role="menuitem" onClick={() => { setOpen(false); logout(); }}>
            <LogOut size={16} className="app-header-item-icon" aria-hidden />
            Sign out
          </button>
        </div>
      )}
    </div>
  )
}

function AppHeader() {
  const { token } = useAuth()

  if (!token) {
    return (
      <header className="app-header">
        <div className="app-header-inner">
          <NavLink to="/" className="app-header-brand"><BarChart3 size={20} className="app-header-brand-icon" aria-hidden /> TRUSEO</NavLink>
          <nav className="app-header-nav">
            <NavLink to="/how-it-works" className={({ isActive }) => isActive ? 'active' : ''}>How it works</NavLink>
            <a href="https://github.com/manishneo123/llm-seo" target="_blank" rel="noopener noreferrer" className="app-header-nav-link app-header-github" aria-label="GitHub repository">
              <Github size={18} aria-hidden />
            </a>
          </nav>
        </div>
      </header>
    )
  }

  return (
    <header className="app-header">
      <div className="app-header-inner">
        <NavLink to="/" className="app-header-brand"><BarChart3 size={20} className="app-header-brand-icon" aria-hidden /> TRUSEO</NavLink>
        <nav className="app-header-nav">
          <NavLink to="/" end className={({ isActive }) => isActive ? 'active' : ''}>Dashboard</NavLink>
          <NavLink to="/domains" className={({ isActive }) => isActive ? 'active' : ''}>Domains</NavLink>
          <NavLink to="/prompts" className={({ isActive }) => isActive ? 'active' : ''}>Prompts</NavLink>
          <NavLink to="/briefs" className={({ isActive }) => isActive ? 'active' : ''}>Briefs</NavLink>
          <NavLink to="/drafts" className={({ isActive }) => isActive ? 'active' : ''}>Drafts</NavLink>
          <div className="app-header-dropdown">
            <button type="button" className="app-header-dropdown-trigger" aria-haspopup="true" aria-expanded={undefined}>
              More
            </button>
            <div className="app-header-dropdown-menu">
              <NavLink to="/how-it-works" className={({ isActive }) => isActive ? 'active' : ''}>How it works</NavLink>
              <NavLink to="/trial-directory" className={({ isActive }) => isActive ? 'active' : ''}>Trial directory</NavLink>
              <NavLink to="/content-sources" className={({ isActive }) => isActive ? 'active' : ''}>Content sources</NavLink>
              <NavLink to="/prompt-generation" className={({ isActive }) => isActive ? 'active' : ''}>Prompt generation</NavLink>
              <NavLink to="/monitoring" className={({ isActive }) => isActive ? 'active' : ''}>Monitoring</NavLink>
              <NavLink to="/reports" className={({ isActive }) => isActive ? 'active' : ''}>Reports</NavLink>
            </div>
          </div>
          <a href="https://github.com/manishneo123/llm-seo" target="_blank" rel="noopener noreferrer" className="app-header-nav-link app-header-github" aria-label="GitHub repository">
            <Github size={18} aria-hidden />
          </a>
        </nav>
        <UserDropdown />
      </div>
    </header>
  )
}

function AppFooter() {
  return (
    <footer className="app-footer">
      <div className="app-footer-inner">
        <span className="app-footer-copy">© {new Date().getFullYear()} TRUSEO</span>
        <nav className="app-footer-links">
          <Link to="/trial-directory">Trial directory</Link>
          <Link to="/terms">Terms &amp; conditions</Link>
        </nav>
      </div>
    </footer>
  )
}

function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="app-layout">
      <PageMeta />
      <div className="app-center">
        <AppHeader />
        <main className="app-body">
          {children}
        </main>
        <AppFooter />
      </div>
    </div>
  )
}

function AppRoutes() {
  return (
    <AppLayout>
      <Routes>
        <Route path="/signin" element={<Signin />} />
        <Route path="/signup" element={<Signup />} />
        <Route path="/how-it-works" element={<HowItWorks />} />
        <Route path="/trial-directory" element={<TrialDirectory />} />
         <Route path="/terms" element={<Terms />} />
        <Route path="/try" element={<Navigate to="/" replace />} />
        <Route path="/try/:slug" element={<TryTrial />} />
        <Route path="/" element={<HomePage />} />
        <Route path="/domains" element={<ProtectedRoute><Domains /></ProtectedRoute>} />
        <Route path="/prompts" element={<ProtectedRoute><Prompts /></ProtectedRoute>} />
        <Route path="/prompts/generate" element={<ProtectedRoute><GeneratePrompts /></ProtectedRoute>} />
        <Route path="/prompts/:id" element={<ProtectedRoute><PromptDetail /></ProtectedRoute>} />
        <Route path="/briefs" element={<ProtectedRoute><Briefs /></ProtectedRoute>} />
        <Route path="/briefs/:id" element={<ProtectedRoute><BriefDetail /></ProtectedRoute>} />
        <Route path="/drafts" element={<ProtectedRoute><Drafts /></ProtectedRoute>} />
        <Route path="/drafts/:id" element={<ProtectedRoute><DraftDetail /></ProtectedRoute>} />
        <Route path="/drafts/:id/publish" element={<ProtectedRoute><PublishDraft /></ProtectedRoute>} />
        <Route path="/content-sources" element={<ProtectedRoute><ContentSources /></ProtectedRoute>} />
        <Route path="/prompt-generation" element={<ProtectedRoute><PromptGeneration /></ProtectedRoute>} />
        <Route path="/monitoring" element={<ProtectedRoute><Monitoring /></ProtectedRoute>} />
        <Route path="/monitoring/executions/:id" element={<ProtectedRoute><MonitoringExecutionDetail /></ProtectedRoute>} />
        <Route path="/reports" element={<ProtectedRoute><Reports /></ProtectedRoute>} />
        <Route path="/settings" element={<ProtectedRoute><Settings /></ProtectedRoute>} />
      </Routes>
    </AppLayout>
  )
}

function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <AppRoutes />
      </AuthProvider>
    </BrowserRouter>
  )
}

export default App
