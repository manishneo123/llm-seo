import { BrowserRouter, Routes, Route, NavLink } from 'react-router-dom'
import { Dashboard } from './pages/Dashboard'
import { Briefs } from './pages/Briefs'
import { BriefDetail } from './pages/BriefDetail'
import { Drafts } from './pages/Drafts'
import { DraftDetail } from './pages/DraftDetail'
import { Prompts } from './pages/Prompts'
import { PromptDetail } from './pages/PromptDetail'
import { GeneratePrompts } from './pages/GeneratePrompts'
import { Reports } from './pages/Reports'
import { Domains } from './pages/Domains'
import { Monitoring } from './pages/Monitoring'
import { MonitoringExecutionDetail } from './pages/MonitoringExecutionDetail'
import './App.css'

function App() {
  return (
    <BrowserRouter>
      <nav className="nav">
        <NavLink to="/" end className={({ isActive }) => isActive ? 'active' : ''}>Dashboard</NavLink>
        <NavLink to="/domains" className={({ isActive }) => isActive ? 'active' : ''}>Domains</NavLink>
        <NavLink to="/prompts" className={({ isActive }) => isActive ? 'active' : ''}>Prompts</NavLink>
        <NavLink to="/briefs" className={({ isActive }) => isActive ? 'active' : ''}>Briefs</NavLink>
        <NavLink to="/drafts" className={({ isActive }) => isActive ? 'active' : ''}>Drafts</NavLink>
        <NavLink to="/monitoring" className={({ isActive }) => isActive ? 'active' : ''}>Monitoring</NavLink>
        <NavLink to="/reports" className={({ isActive }) => isActive ? 'active' : ''}>Reports</NavLink>
      </nav>
      <Routes>
        <Route path="/" element={<Dashboard />} />
        <Route path="/domains" element={<Domains />} />
        <Route path="/prompts" element={<Prompts />} />
        <Route path="/prompts/generate" element={<GeneratePrompts />} />
        <Route path="/prompts/:id" element={<PromptDetail />} />
        <Route path="/briefs" element={<Briefs />} />
        <Route path="/briefs/:id" element={<BriefDetail />} />
        <Route path="/drafts" element={<Drafts />} />
        <Route path="/drafts/:id" element={<DraftDetail />} />
        <Route path="/monitoring" element={<Monitoring />} />
        <Route path="/monitoring/executions/:id" element={<MonitoringExecutionDetail />} />
        <Route path="/reports" element={<Reports />} />
      </Routes>
    </BrowserRouter>
  )
}

export default App
