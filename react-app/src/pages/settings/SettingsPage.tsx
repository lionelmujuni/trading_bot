import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { Badge } from '@/components/ui/Badge'
import { useSettingsStore } from '@/stores/settingsStore'
import { cn } from '@/lib/utils'
import { AlertTriangle, CheckCircle2, XCircle } from 'lucide-react'

export default function SettingsPage() {
  const { exchange, tradingMode } = useSettingsStore()

  const [apiKey, setApiKey] = useState('')
  const [privateKey, setPrivateKey] = useState('')
  const [testResult, setTestResult] = useState<{ ok: boolean; msg: string } | null>(null)

  const [capital, setCapital] = useState('')
  const [posSizePct, setPosSizePct] = useState('')
  const [slPct, setSlPct] = useState('')
  const [dailyLossPct, setDailyLossPct] = useState('')

  const [configSaved, setConfigSaved] = useState(false)
  const [testLoading, setTestLoading] = useState(false)

  async function handleTestCredentials() {
    setTestLoading(true)
    setTestResult(null)
    try {
      const res = await fetch('/api/exchange/test', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ exchange, api_key: apiKey, private_key: privateKey }),
      })
      const d = await res.json()
      if (res.ok) setTestResult({ ok: true, msg: `Connected! Buying power: $${d.buying_power_usd}` })
      else setTestResult({ ok: false, msg: d.detail ?? 'Failed' })
    } catch {
      setTestResult({ ok: false, msg: 'Server error' })
    } finally {
      setTestLoading(false)
    }
  }

  const saveConfig = useMutation({
    mutationFn: () =>
      fetch('/api/config', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          ...(capital && { total_capital: parseFloat(capital) }),
          ...(posSizePct && { max_position_size_pct: parseFloat(posSizePct) / 100 }),
          ...(slPct && { stop_loss_pct: parseFloat(slPct) / 100 }),
          ...(dailyLossPct && { max_daily_loss_pct: parseFloat(dailyLossPct) / 100 }),
        }),
      }).then((r) => r.json()),
    onSuccess: () => {
      setConfigSaved(true)
      setTimeout(() => setConfigSaved(false), 3000)
    },
  })

  return (
    <div className="p-6 space-y-6 max-w-2xl">
      <h1 className="text-xl font-bold text-white">Settings</h1>

      {/* Exchange credentials */}
      <Card>
        <CardHeader>
          <CardTitle>Exchange Credentials</CardTitle>
          <Badge variant="info">{exchange.toUpperCase()}</Badge>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="rounded-lg border border-amber-700/40 bg-amber-900/10 p-3 flex gap-2 text-xs text-amber-300">
            <AlertTriangle className="h-4 w-4 flex-shrink-0 mt-0.5" />
            Keys are stored in <code>.env</code> on the local server only. Never sent to any third party.
          </div>
          <Input label="API Key" placeholder="Leave blank to keep existing" value={apiKey} onChange={(e: React.ChangeEvent<HTMLInputElement>) => setApiKey(e.target.value)} />
          <Input label="Private Key" type="password" placeholder="Leave blank to keep existing" value={privateKey} onChange={(e: React.ChangeEvent<HTMLInputElement>) => setPrivateKey(e.target.value)} />
          <div className="flex items-center gap-3">
            <Button variant="outline" size="sm" loading={testLoading} disabled={!apiKey || !privateKey} onClick={handleTestCredentials}>
              Test Connection
            </Button>
            {testResult && (
              <span className={cn('text-xs flex items-center gap-1.5', testResult.ok ? 'text-emerald-400' : 'text-red-400')}>
                {testResult.ok ? <CheckCircle2 className="h-3.5 w-3.5" /> : <XCircle className="h-3.5 w-3.5" />}
                {testResult.msg}
              </span>
            )}
          </div>
        </CardContent>
      </Card>

      {/* Risk configuration */}
      <Card>
        <CardHeader>
          <CardTitle>Risk Parameters</CardTitle>
          <Badge variant={tradingMode === 'live' ? 'live' : 'paper'}>{tradingMode.toUpperCase()}</Badge>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-2 gap-3">
            <Input label="Total Capital (USD)" type="number" placeholder="Current value from .env" value={capital} onChange={(e: React.ChangeEvent<HTMLInputElement>) => setCapital(e.target.value)} />
            <Input label="Max Position Size (%)" type="number" placeholder="e.g. 10" value={posSizePct} onChange={(e: React.ChangeEvent<HTMLInputElement>) => setPosSizePct(e.target.value)} />
            <Input label="Stop Loss (%)" type="number" placeholder="e.g. 3" value={slPct} onChange={(e: React.ChangeEvent<HTMLInputElement>) => setSlPct(e.target.value)} />
            <Input label="Daily Loss Limit (%)" type="number" placeholder="e.g. 5" value={dailyLossPct} onChange={(e: React.ChangeEvent<HTMLInputElement>) => setDailyLossPct(e.target.value)} />
          </div>
          <div className="flex items-center gap-3">
            <Button size="sm" loading={saveConfig.isPending} onClick={() => saveConfig.mutate()}>
              Save Settings
            </Button>
            {configSaved && <span className="text-xs text-emerald-400 flex items-center gap-1"><CheckCircle2 className="h-3.5 w-3.5" /> Saved — restart bot to apply</span>}
          </div>
        </CardContent>
      </Card>

      {/* Danger zone */}
      <Card className="border-red-700/40">
        <CardHeader><CardTitle className="text-red-400">Danger Zone</CardTitle></CardHeader>
        <CardContent className="space-y-3">
          <p className="text-xs text-slate-500">These actions cannot be undone.</p>
          <div className="flex items-center justify-between rounded-lg border border-slate-700 p-3">
            <div>
              <p className="text-sm font-medium text-slate-300">Reset Onboarding</p>
              <p className="text-xs text-slate-500">Re-run the setup wizard on next page load.</p>
            </div>
            <Button
              variant="outline"
              size="sm"
              className="border-red-700 text-red-400 hover:bg-red-900/20"
              onClick={() => useSettingsStore.getState().setOnboardingComplete(false)}
            >
              Reset
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
