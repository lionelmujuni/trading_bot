import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { GoogleOAuthProvider } from '@react-oauth/google'
import './index.css'
import App from './App.tsx'
import { useAuthStore } from './stores/authStore.ts'

// ── Global fetch interceptor ─────────────────────────────────────────────────
// Automatically attaches the JWT Authorization header to all /api/* and
// authenticated /auth/* requests. Redirects to /login on 401.

const _PUBLIC_AUTH = ['/auth/register', '/auth/login', '/auth/google']
const _originalFetch = window.fetch.bind(window)

window.fetch = async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
  const url =
    typeof input === 'string'
      ? input
      : input instanceof URL
        ? input.href
        : (input as Request).url ?? ''

  const isApiPath = url.startsWith('/api/') || url.startsWith('/auth/')
  const isPublic  = _PUBLIC_AUTH.some((p) => url.startsWith(p))
  const needsAuth = isApiPath && !isPublic

  if (needsAuth) {
    const { token } = useAuthStore.getState()
    if (token) {
      init = {
        ...init,
        headers: { Authorization: `Bearer ${token}`, ...(init?.headers ?? {}) },
      }
    }
  }

  const response = await _originalFetch(input, init as RequestInit)

  if (response.status === 401 && needsAuth) {
    useAuthStore.getState().logout()
    if (!window.location.pathname.startsWith('/login') && !window.location.pathname.startsWith('/register')) {
      window.location.href = '/login'
    }
  }

  return response
}

// ── Render ───────────────────────────────────────────────────────────────────

const GOOGLE_CLIENT_ID = import.meta.env.VITE_GOOGLE_CLIENT_ID ?? ''

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <GoogleOAuthProvider clientId={GOOGLE_CLIENT_ID}>
      <App />
    </GoogleOAuthProvider>
  </StrictMode>,
)
