import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { AppLayout } from './components/AppLayout'
import { RequireAuth } from './components/RequireAuth'
import { useSettingsStore } from './stores/settingsStore'
import { useAuthStore } from './stores/authStore'

// Pages
import LoginPage      from './pages/auth/LoginPage'
import RegisterPage   from './pages/auth/RegisterPage'
import OnboardingPage from './pages/onboarding/OnboardingPage'
import DashboardPage  from './pages/dashboard/DashboardPage'
import MarketsPage    from './pages/markets/MarketsPage'
import StrategiesPage from './pages/strategies/StrategiesPage'
import AnalyticsPage  from './pages/analytics/AnalyticsPage'
import PositionsPage  from './pages/positions/PositionsPage'
import SettingsPage   from './pages/settings/SettingsPage'

const queryClient = new QueryClient({
  defaultOptions: { queries: { staleTime: 10_000, retry: 1 } },
})

function AppRoutes() {
  const onboardingComplete = useSettingsStore((s) => s.onboardingComplete)
  const token = useAuthStore((s) => s.token)

  // ── Unauthenticated ──────────────────────────────────────────────────────
  if (!token) {
    return (
      <Routes>
        <Route path="/login"    element={<LoginPage />} />
        <Route path="/register" element={<RegisterPage />} />
        <Route path="*"         element={<Navigate to="/login" replace />} />
      </Routes>
    )
  }

  // ── Authenticated — onboarding pending ──────────────────────────────────
  if (!onboardingComplete) {
    return (
      <Routes>
        <Route element={<RequireAuth />}>
          <Route path="/onboarding" element={<OnboardingPage />} />
          <Route path="*"           element={<Navigate to="/onboarding" replace />} />
        </Route>
      </Routes>
    )
  }

  // ── Authenticated — full app ─────────────────────────────────────────────
  return (
    <Routes>
      <Route element={<RequireAuth />}>
        <Route element={<AppLayout />}>
          <Route path="/"           element={<DashboardPage />} />
          <Route path="/markets"    element={<MarketsPage />} />
          <Route path="/strategies" element={<StrategiesPage />} />
          <Route path="/analytics"  element={<AnalyticsPage />} />
          <Route path="/positions"  element={<PositionsPage />} />
          <Route path="/settings"   element={<SettingsPage />} />
        </Route>
        <Route path="/onboarding" element={<Navigate to="/" replace />} />
        <Route path="/login"      element={<Navigate to="/" replace />} />
        <Route path="/register"   element={<Navigate to="/" replace />} />
        <Route path="*"           element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  )
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <AppRoutes />
      </BrowserRouter>
    </QueryClientProvider>
  )
}
