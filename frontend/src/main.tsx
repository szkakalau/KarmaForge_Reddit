import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter, Routes, Route } from 'react-router-dom'
import './index.css'
import { LanguageProvider } from './i18n/LanguageContext'
import Layout from './Layout'
import ErrorBoundary from './ErrorBoundary'
import Landing from './pages/Landing'
import Dashboard from './pages/Dashboard'
import History from './pages/History'
import Analytics from './pages/Analytics'
import Pricing from './pages/Pricing'
import Subscription from './pages/Subscription'
import Admin from './pages/Admin'
import NotFound from './pages/NotFound'
import Login from './pages/Login'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <LanguageProvider>
    <BrowserRouter>
      <Routes>
        {/* Public routes — no sidebar */}
        <Route path="/" element={<Landing />} />
        <Route path="/login" element={<Login />} />
        {/* Authenticated routes — with sidebar */}
        <Route path="/app" element={<ErrorBoundary><Layout /></ErrorBoundary>}>
          <Route index element={<Dashboard />} />
          <Route path="history" element={<History />} />
          <Route path="analytics" element={<Analytics />} />
          <Route path="pricing" element={<Pricing />} />
          <Route path="subscription" element={<Subscription />} />
          <Route path="admin" element={<Admin />} />
        </Route>
        {/* Public pricing page (same component, no sidebar) */}
        <Route path="/pricing" element={<Pricing />} />
        {/* 404 */}
        <Route path="*" element={<NotFound />} />
      </Routes>
    </BrowserRouter>
    </LanguageProvider>
  </StrictMode>,
)
