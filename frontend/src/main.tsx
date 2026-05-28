import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter, Routes, Route } from 'react-router-dom'
import './index.css'
import Layout from './Layout'
import ErrorBoundary from './ErrorBoundary'
import Dashboard from './pages/Dashboard'
import History from './pages/History'
import Analytics from './pages/Analytics'
import Login from './pages/Login'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route element={<ErrorBoundary><Layout /></ErrorBoundary>}>
          <Route path="/" element={<Dashboard />} />
          <Route path="/history" element={<History />} />
          <Route path="/analytics" element={<Analytics />} />
        </Route>
      </Routes>
    </BrowserRouter>
  </StrictMode>,
)
