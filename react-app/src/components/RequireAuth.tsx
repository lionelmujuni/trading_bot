import { Navigate, Outlet } from 'react-router-dom'
import { useAuthStore } from '@/stores/authStore'

/**
 * Route wrapper that redirects unauthenticated users to /login.
 * Use as a layout route: <Route element={<RequireAuth />}> ... </Route>
 */
export function RequireAuth() {
  const token = useAuthStore((s) => s.token)
  if (!token) return <Navigate to="/login" replace />
  return <Outlet />
}
