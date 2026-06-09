import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import Editor from '@monaco-editor/react'
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Badge } from '@/components/ui/Badge'
import { Input } from '@/components/ui/Input'
import { cn } from '@/lib/utils'
import { Plus, Trash2, Play, CheckCircle2, XCircle, Lock } from 'lucide-react'
import { useMarketStore } from '@/stores/marketStore'
import { fmtPct, fmtUSD, fmt } from '@/lib/utils'

const STARTER_TEMPLATE = `# Custom Strategy Template
# Available in 'data' dict:
#   data['close']   – list of close prices (newest last)
#   data['high']    – list of highs
#   data['low']     – list of lows
#   data['volume']  – list of volumes
#   data['rsi']     – current RSI value (float)
#   data['macd']    – current MACD value (float)
#   data['bb_upper'], data['bb_lower'], data['bb_mid'] – Bollinger Bands
#   data['ema_short'], data['ema_long'] – EMA 12 / EMA 26
#   data['zscore']  – z-score vs 20-period mean
#
# Return one of:
#   'buy'    – open long position
#   'sell'   – close long / open short (if allowed)
#   'hold'   – do nothing

def generate_signal(data):
    # Example: simple RSI mean-reversion
    rsi = data['rsi']
    zscore = data['zscore']
    
    if rsi < 35 and zscore < -2.0:
        return 'buy'
    elif rsi > 70 or zscore > 1.5:
        return 'sell'
    
    return 'hold'
`

const RISK_COLORS: Record<string, string> = { low: 'success', medium: 'warning', high: 'danger' }

export default function StrategiesPage() {
  const qc = useQueryClient()
  const [selected, setSelected] = useState<any | null>(null)
  const [isNew, setIsNew] = useState(false)
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [code, setCode] = useState(STARTER_TEMPLATE)
  const [backtestResult, setBacktestResult] = useState<any | null>(null)
  const [validateMsg, setValidateMsg] = useState<{ ok: boolean; msg: string } | null>(null)
  const activeSymbol = useMarketStore((s) => s.activeSymbol)

  const { data: allStrategies } = useQuery({
    queryKey: ['strategies'],
    queryFn: () => fetch('/api/strategies').then((r) => r.json()),
  })

const builtin = allStrategies?.builtin ?? []
  const user = allStrategies?.user ?? []

  const saveMutation = useMutation({
    mutationFn: (body: any) =>
      fetch(selected && !isNew ? `/api/strategies/${selected.id}` : '/api/strategies', {
        method: selected && !isNew ? 'PUT' : 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      }).then((r) => {
        if (!r.ok) return r.json().then((e) => Promise.reject(e.detail))
        return r.json()
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['strategies'] })
      setValidateMsg({ ok: true, msg: 'Strategy saved successfully!' })
    },
    onError: (e: any) => setValidateMsg({ ok: false, msg: String(e) }),
  })

  const deleteMutation = useMutation({
    mutationFn: (id: number) =>
      fetch(`/api/strategies/${id}`, { method: 'DELETE' }).then((r) => {
        if (!r.ok) throw new Error('Delete failed')
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['strategies'] })
      setSelected(null)
    },
  })

  const backtestMutation = useMutation({
    mutationFn: ({ id, symbol }: { id: number; symbol: string }) =>
      fetch(`/api/strategies/${id}/backtest?symbol=${encodeURIComponent(symbol)}&limit=500`, { method: 'POST' })
        .then((r) => r.json()),
    onSuccess: (data) => setBacktestResult(data),
  })

  function handleSelectBuiltin(s: any) {
    setSelected(s)
    setIsNew(false)
    setCode('# Built-in strategy — not editable.\n# Fork it into a new strategy to customize.')
    setName(s.name)
    setDescription(s.description)
    setBacktestResult(null)
    setValidateMsg(null)
  }

  function handleSelectUser(s: any) {
    setSelected(s)
    setIsNew(false)
    setCode(s.code ?? STARTER_TEMPLATE)
    setName(s.name)
    setDescription(s.description ?? '')
    setBacktestResult(null)
    setValidateMsg(null)
  }

  function handleNew() {
    setSelected(null)
    setIsNew(true)
    setCode(STARTER_TEMPLATE)
    setName('')
    setDescription('')
    setBacktestResult(null)
    setValidateMsg(null)
  }

  async function handleValidate() {
    setValidateMsg(null)
    try {
      const res = await fetch('/api/strategies', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: name || 'temp_validate', description, code, parameters: [], custom_metrics: [] }),
      })
      if (res.ok) {
        const d = await res.json()
        // Delete the temp saved one
        await fetch(`/api/strategies/${d.id}`, { method: 'DELETE' })
        setValidateMsg({ ok: true, msg: 'Code is valid and compiles successfully.' })
      } else {
        const e = await res.json()
        setValidateMsg({ ok: false, msg: e.detail ?? 'Validation failed' })
      }
    } catch {
      setValidateMsg({ ok: false, msg: 'Validation request failed' })
    }
    qc.invalidateQueries({ queryKey: ['strategies'] })
  }

  function handleSave() {
    saveMutation.mutate({ name, description, code, parameters: [], custom_metrics: [] })
  }

  const isBuiltin = selected && !selected.code && !isNew
  const canEdit = !isBuiltin
  const canBacktest = selected && !isNew && selected.id && typeof selected.id === 'number'

  return (
    <div className="p-6 h-full">
      <div className="flex items-center justify-between mb-5">
        <h1 className="text-xl font-bold text-white">Strategy Builder</h1>
        <Button size="sm" onClick={handleNew}><Plus className="h-4 w-4" /> New Strategy</Button>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-4 gap-5 h-[calc(100vh-10rem)]">
        {/* Strategy list */}
        <div className="xl:col-span-1 overflow-y-auto space-y-3">
          {/* Built-in */}
          <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider px-1">Built-in</p>
          {builtin.map((s: any) => (
            <button
              key={s.id}
              onClick={() => handleSelectBuiltin(s)}
              className={cn(
                'w-full rounded-lg border p-3 text-left transition-colors',
                selected?.id === s.id ? 'border-blue-500 bg-blue-500/10' : 'border-slate-700 bg-slate-800/30 hover:border-slate-500'
              )}
            >
              <div className="flex items-center justify-between mb-1">
                <span className="text-xs font-medium text-slate-200 truncate pr-2">{s.name}</span>
                <Lock className="h-3 w-3 text-slate-500 flex-shrink-0" />
              </div>
              <Badge variant={RISK_COLORS[s.risk_level] as any} className="text-[9px]">{s.risk_level}</Badge>
            </button>
          ))}

          {/* User */}
          {user.length > 0 && (
            <>
              <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider px-1 mt-4">Custom</p>
              {user.map((s: any) => (
                <button
                  key={s.id}
                  onClick={() => handleSelectUser(s)}
                  className={cn(
                    'w-full rounded-lg border p-3 text-left transition-colors',
                    selected?.id === s.id ? 'border-blue-500 bg-blue-500/10' : 'border-slate-700 bg-slate-800/30 hover:border-slate-500'
                  )}
                >
                  <span className="text-xs font-medium text-slate-200 truncate block">{s.name}</span>
                  <Badge variant={s.enabled ? 'success' : 'default'} className="text-[9px] mt-1">{s.enabled ? 'Active' : 'Disabled'}</Badge>
                </button>
              ))}
            </>
          )}
        </div>

        {/* Editor + results */}
        <div className="xl:col-span-3 flex flex-col gap-4 overflow-hidden">
          {(isNew || selected) && (
            <>
              {/* Name + desc inputs */}
              {canEdit && (
                <div className="grid grid-cols-2 gap-3">
                  <Input label="Strategy Name" value={name} onChange={(e) => setName(e.target.value)} placeholder="My Momentum Strategy" />
                  <Input label="Description" value={description} onChange={(e) => setDescription(e.target.value)} placeholder="Short description..." />
                </div>
              )}

              {/* Monaco editor */}
              <Card className="flex-1 overflow-hidden">
                <CardHeader>
                  <CardTitle>Strategy Code (Python)</CardTitle>
                  {isBuiltin && (
                    <div className="flex items-center gap-1.5 text-xs text-slate-500">
                      <Lock className="h-3 w-3" /> Read-only
                    </div>
                  )}
                </CardHeader>
                <div className="flex-1" style={{ height: 320 }}>
                  <Editor
                    height="100%"
                    language="python"
                    theme="vs-dark"
                    value={code}
                    onChange={(v) => canEdit && setCode(v ?? '')}
                    options={{
                      readOnly: !canEdit,
                      minimap: { enabled: false },
                      fontSize: 13,
                      lineNumbers: 'on',
                      wordWrap: 'on',
                      scrollBeyondLastLine: false,
                      automaticLayout: true,
                    }}
                  />
                </div>
              </Card>

              {/* Action bar */}
              {canEdit && (
                <div className="flex items-center gap-3 flex-wrap">
                  <Button variant="outline" size="sm" onClick={handleValidate}>
                    <CheckCircle2 className="h-4 w-4" /> Validate
                  </Button>
                  <Button size="sm" loading={saveMutation.isPending} onClick={handleSave} disabled={!name.trim()}>
                    Save Strategy
                  </Button>
                  {canBacktest && (
                    <Button
                      variant="outline"
                      size="sm"
                      loading={backtestMutation.isPending}
                      onClick={() => backtestMutation.mutate({ id: selected.id, symbol: activeSymbol })}
                    >
                      <Play className="h-4 w-4" /> Run Backtest
                    </Button>
                  )}
                  {selected && !isNew && (
                    <Button
                      variant="destructive"
                      size="sm"
                      loading={deleteMutation.isPending}
                      onClick={() => deleteMutation.mutate(selected.id)}
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </Button>
                  )}
                  {validateMsg && (
                    <div className={cn('flex items-center gap-1.5 text-xs', validateMsg.ok ? 'text-emerald-400' : 'text-red-400')}>
                      {validateMsg.ok ? <CheckCircle2 className="h-3.5 w-3.5" /> : <XCircle className="h-3.5 w-3.5" />}
                      {validateMsg.msg}
                    </div>
                  )}
                </div>
              )}

              {/* Backtest results */}
              {backtestResult && <BacktestPanel result={backtestResult} />}
            </>
          )}

          {!isNew && !selected && (
            <div className="flex-1 flex items-center justify-center text-slate-600 text-sm">
              Select a strategy from the list or create a new one
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

function BacktestPanel({ result }: { result: any }) {
  const stats = result.stats ?? {}
  return (
    <Card>
      <CardHeader><CardTitle>Backtest Results</CardTitle></CardHeader>
      <CardContent>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-4">
          {[
            { label: 'Total Return', value: fmtPct(stats.total_return_pct) },
            { label: 'Win Rate', value: `${fmt(stats.win_rate, 1)}%` },
            { label: 'Total Trades', value: stats.total_trades ?? '—' },
            { label: 'Max Drawdown', value: fmtPct(stats.max_drawdown_pct) },
            { label: 'Sharpe Ratio', value: fmt(stats.sharpe_ratio) },
            { label: 'Profit Factor', value: fmt(stats.profit_factor) },
            { label: 'Avg Win', value: fmtPct(stats.avg_win_pct) },
            { label: 'Avg Loss', value: fmtPct(stats.avg_loss_pct) },
          ].map(({ label, value }) => (
            <div key={label} className="rounded-lg bg-slate-800 p-3">
              <p className="text-[10px] text-slate-500 uppercase mb-0.5">{label}</p>
              <p className="text-sm font-semibold text-slate-200">{value}</p>
            </div>
          ))}
        </div>
        {result.trades?.length > 0 && (
          <div className="overflow-x-auto">
            <p className="text-xs text-slate-500 mb-2">Last {Math.min(result.trades.length, 10)} trades</p>
            <table className="w-full text-xs">
              <thead><tr className="border-b border-slate-700">
                {['Type', 'Entry', 'Exit', 'P&L'].map((h) => <th key={h} className="text-left px-2 py-1 text-slate-500">{h}</th>)}
              </tr></thead>
              <tbody>
                {result.trades.slice(-10).map((t: any, i: number) => (
                  <tr key={i} className="border-b border-slate-800/50">
                    <td className="px-2 py-1"><Badge variant={t.type === 'buy' ? 'success' : 'danger'} className="text-[9px]">{t.type}</Badge></td>
                    <td className="px-2 py-1 text-slate-400">{fmtUSD(t.entry_price)}</td>
                    <td className="px-2 py-1 text-slate-400">{fmtUSD(t.exit_price)}</td>
                    <td className={cn('px-2 py-1 font-medium', t.pnl_pct >= 0 ? 'text-emerald-400' : 'text-red-400')}>{fmtPct(t.pnl_pct)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </CardContent>
    </Card>
  )
}
