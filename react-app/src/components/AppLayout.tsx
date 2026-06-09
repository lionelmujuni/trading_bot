import { Outlet } from 'react-router-dom'
import { Sidebar } from './Sidebar'
import { useRealtimeSocket } from '@/hooks/useRealtimeSocket'

export function AppLayout() {
  // Mount WebSocket once at root layout level
  useRealtimeSocket()

  return (
    <div className="flex min-h-screen bg-slate-950">
      <Sidebar />
      <main className="ml-56 flex-1 overflow-auto">
        <Outlet />
      </main>
    </div>
  )
}
