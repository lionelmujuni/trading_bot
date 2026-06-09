import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useSettingsStore } from '@/stores/settingsStore'
import { Button } from '@/components/ui/Button'
import { Card, CardContent } from '@/components/ui/Card'
import { Input } from '@/components/ui/Input'
import { Badge } from '@/components/ui/Badge'
import { cn } from '@/lib/utils'
import {
  CheckCircle2, ChevronRight, ChevronLeft, Bot,
  Shield, TrendingUp, Zap, BarChart2, AlertTriangle,
  Copy, ExternalLink, Key, RefreshCw
} from 'lucide-react'

// ── Types ────────────────────────────────────────────────────────────────────

interface WizardState {
  exchange: string
  apiKey: string
  privateKey: string
  tradingMode: 'paper' | 'live'
  totalCapital: string
  positionSizePct: string
  stopLossPct: string
  dailyLossPct: string
  selectedStrategies: string[]
}

const STEPS = [
  'Exchange',
  'API Keys',
  'Risk Settings',
  'Trading Pairs',
  'Strategies',
  'Review',
]

const BUILTIN_STRATEGIES = [
  { id: 'builtin_legacy',        label: 'RSI / MACD / ROC',     risk: 'medium', desc: 'Classic technical indicator confluence.' },
  { id: 'builtin_mean_reversion',label: 'Mean Reversion',        risk: 'low',    desc: 'Bollinger Bands with z-score entries.' },
  { id: 'builtin_momentum',      label: 'Dual MA Momentum',      risk: 'medium', desc: 'Golden cross / death cross signals.' },
  { id: 'builtin_breakout',      label: 'Intraday Breakout',     risk: 'high',   desc: 'Volume-confirmed price breakouts.' },
  { id: 'builtin_regime',        label: 'Regime Detection',      risk: 'medium', desc: 'Dynamically weights other strategies.' },
]

const riskColor: Record<string, string> = {
  low: 'success', medium: 'warning', high: 'danger',
}

// ── Step components ──────────────────────────────────────────────────────────

function StepExchange({ state, setState }: { state: WizardState; setState: (s: Partial<WizardState>) => void }) {
  const exchanges = [
    {
      id: 'kraken',
      name: 'Kraken',
      desc: 'Institutional-grade crypto exchange. Supports all strategy types. Recommended.',
      pros: ['Deep liquidity', 'Low fees (0.16% maker)', 'WebSocket streaming', 'Ed25519 + HMAC auth'],
    },
    {
      id: 'robinhood',
      name: 'Robinhood',
      desc: 'Commission-free US broker. Good for starting out.',
      pros: ['No trading fees', 'Familiar interface', 'Easy setup'],
    },
  ]

  return (
    <div className="space-y-4">
      <p className="text-slate-400 text-sm">Choose the exchange you want to trade on. You can change this later in Settings.</p>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        {exchanges.map((ex) => (
          <button
            key={ex.id}
            onClick={() => setState({ exchange: ex.id })}
            className={cn(
              'rounded-xl border p-4 text-left transition-all',
              state.exchange === ex.id
                ? 'border-blue-500 bg-blue-500/10'
                : 'border-slate-700 bg-slate-800/50 hover:border-slate-500'
            )}
          >
            <div className="flex items-center justify-between mb-2">
              <span className="font-semibold text-white">{ex.name}</span>
              {state.exchange === ex.id && <CheckCircle2 className="h-4 w-4 text-blue-400" />}
              {ex.id === 'kraken' && <Badge variant="info" className="text-[10px]">Recommended</Badge>}
            </div>
            <p className="text-xs text-slate-400 mb-3">{ex.desc}</p>
            <ul className="space-y-1">
              {ex.pros.map((p) => (
                <li key={p} className="flex items-center gap-1.5 text-xs text-slate-300">
                  <CheckCircle2 className="h-3 w-3 text-emerald-400 flex-shrink-0" />
                  {p}
                </li>
              ))}
            </ul>
          </button>
        ))}
      </div>
    </div>
  )
}

function StepApiKeys({
  state, setState,
}: { state: WizardState; setState: (s: Partial<WizardState>) => void }) {
  const [testing,    setTesting]    = useState(false)
  const [testResult, setTestResult] = useState<{ ok: boolean; msg: string } | null>(null)
  const [saving,     setSaving]     = useState(false)
  const [saved,      setSaved]      = useState(false)

  // Robinhood keypair generation state
  const [genLoading, setGenLoading] = useState(false)
  const [publicKey,  setPublicKey]  = useState('')
  const [copied,     setCopied]     = useState(false)

  // Kraken permission checklist
  const [krakenChecks, setKrakenChecks] = useState({
    queryFunds:  false,
    queryOrders: false,
    createOrders: false,
  })

  const isKraken    = state.exchange === 'kraken'
  const canTest     = state.apiKey.trim() !== '' && state.privateKey.trim() !== ''
  const allKrakenOk = krakenChecks.queryFunds && krakenChecks.queryOrders && krakenChecks.createOrders

  async function generateKeypair() {
    setGenLoading(true)
    setTestResult(null)
    try {
      const res  = await fetch('/api/setup/robinhood-keypair')
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail ?? 'Keypair generation failed')
      setPublicKey(data.public_key_base64)
      setState({ privateKey: data.private_key_base64 })
    } catch (err: any) {
      setTestResult({ ok: false, msg: err.message })
    } finally {
      setGenLoading(false)
    }
  }

  async function copyToClipboard(text: string) {
    await navigator.clipboard.writeText(text)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  async function testAndSave() {
    setTesting(true)
    setTestResult(null)
    setSaved(false)
    try {
      // 1. Verify credentials with the exchange
      const testRes = await fetch('/api/exchange/test', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          exchange:    state.exchange,
          api_key:     state.apiKey,
          private_key: state.privateKey,
        }),
      })
      const testData = await testRes.json()
      if (!testRes.ok) throw new Error(testData.detail ?? 'Connection failed')

      // 2. Save encrypted credentials to the database
      setSaving(true)
      const saveRes = await fetch('/auth/credentials', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          exchange:    state.exchange,
          api_key:     state.apiKey,
          private_key: state.privateKey,
        }),
      })
      if (!saveRes.ok) {
        const e = await saveRes.json().catch(() => ({}))
        throw new Error(e.detail ?? 'Failed to save credentials')
      }

      setSaved(true)
      setTestResult({
        ok:  true,
        msg: `Connected! Buying power: $${testData.buying_power_usd?.toFixed(2) ?? '—'} — credentials saved securely.`,
      })
    } catch (err: any) {
      setTestResult({ ok: false, msg: err.message })
    } finally {
      setTesting(false)
      setSaving(false)
    }
  }

  return (
    <div className="space-y-5">
      {/* Security notice */}
      <div className="rounded-lg border border-amber-700/40 bg-amber-900/20 p-3 flex gap-2">
        <AlertTriangle className="h-4 w-4 text-amber-400 flex-shrink-0 mt-0.5" />
        <p className="text-xs text-amber-300">
          Keys are encrypted with AES-256 (Fernet) and stored in your local database.
          They are <strong>never</strong> sent off your machine.
        </p>
      </div>

      {isKraken ? (
        /* ── Kraken flow ─────────────────────────────────────────────────── */
        <div className="space-y-4">
          {/* Step 1: Create key on Kraken */}
          <div className="rounded-lg bg-slate-800 p-4 space-y-3 text-xs text-slate-400">
            <p className="font-semibold text-slate-200 text-sm">Step 1 — Create a Kraken API key</p>
            <a
              href="https://www.kraken.com/u/security/api"
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-1.5 rounded-md bg-blue-600/20 border border-blue-600/40 px-3 py-1.5 text-blue-300 hover:bg-blue-600/30 transition-colors text-xs"
            >
              <ExternalLink className="h-3.5 w-3.5" />
              Open Kraken → Settings → API
            </a>
            <p className="font-medium text-slate-300">Required permissions (check all three):</p>
            <div className="space-y-1.5">
              {[
                { key: 'queryFunds',   label: 'Query Funds' },
                { key: 'queryOrders',  label: 'Query Open Orders & Trades' },
                { key: 'createOrders', label: 'Create & Modify Orders' },
              ].map(({ key, label }) => (
                <label key={key} className="flex items-center gap-2 cursor-pointer select-none">
                  <input
                    type="checkbox"
                    className="accent-blue-500"
                    checked={krakenChecks[key as keyof typeof krakenChecks]}
                    onChange={(e) =>
                      setKrakenChecks((c) => ({ ...c, [key]: e.target.checked }))
                    }
                  />
                  <span className={cn('transition-colors', krakenChecks[key as keyof typeof krakenChecks] ? 'text-emerald-300' : '')}>
                    {krakenChecks[key as keyof typeof krakenChecks]
                      ? <CheckCircle2 className="inline h-3 w-3 mr-1 text-emerald-400" />
                      : null}
                    {label}
                  </span>
                </label>
              ))}
            </div>
            {!allKrakenOk && (
              <p className="text-amber-400">Confirm you have enabled all three permissions above.</p>
            )}
          </div>

          {/* Step 2: Paste keys */}
          <div className="space-y-3">
            <p className="text-xs font-semibold text-slate-200">Step 2 — Paste your API credentials</p>
            <Input
              label="API Key"
              placeholder="kraken-api-key-here"
              value={state.apiKey}
              onChange={(e) => setState({ apiKey: e.target.value })}
            />
            <Input
              label="Private Key (Base64)"
              type="password"
              placeholder="base64-encoded-private-key"
              value={state.privateKey}
              onChange={(e) => setState({ privateKey: e.target.value })}
            />
          </div>
        </div>
      ) : (
        /* ── Robinhood flow ──────────────────────────────────────────────── */
        <div className="space-y-4">
          {/* Step 1: Generate keypair */}
          <div className="rounded-lg bg-slate-800 p-4 space-y-3 text-xs text-slate-400">
            <p className="font-semibold text-slate-200 text-sm">Step 1 — Generate your Ed25519 keypair</p>
            <p>
              Robinhood uses Ed25519 cryptographic signing. Generate a keypair below —
              the <strong className="text-slate-300">public key</strong> goes to Robinhood,
              and the <strong className="text-slate-300">private key</strong> stays here.
            </p>
            <Button
              variant="outline"
              size="sm"
              loading={genLoading}
              onClick={generateKeypair}
            >
              <Key className="h-3.5 w-3.5" />
              {publicKey ? 'Regenerate Keypair' : 'Generate Keypair'}
              {publicKey && <RefreshCw className="h-3 w-3 ml-1" />}
            </Button>

            {publicKey && (
              <div className="space-y-2 mt-2">
                <p className="font-medium text-slate-300">Your public key (copy this):</p>
                <div className="flex items-start gap-2">
                  <code className="flex-1 break-all text-emerald-300 text-[10px] leading-relaxed bg-slate-900 rounded p-2">
                    {publicKey}
                  </code>
                  <button
                    onClick={() => copyToClipboard(publicKey)}
                    title="Copy public key"
                    className="mt-1 flex-shrink-0 text-slate-400 hover:text-white transition-colors"
                  >
                    {copied ? (
                      <CheckCircle2 className="h-4 w-4 text-emerald-400" />
                    ) : (
                      <Copy className="h-4 w-4" />
                    )}
                  </button>
                </div>
                <p className="text-slate-500 text-[10px]">
                  Your private key has been pre-filled in the field below — it is not shown in plaintext.
                </p>
              </div>
            )}
          </div>

          {/* Step 2: Register public key on Robinhood */}
          <div className="rounded-lg bg-slate-800 p-4 space-y-2 text-xs text-slate-400">
            <p className="font-semibold text-slate-200 text-sm">Step 2 — Register on Robinhood</p>
            <ol className="list-decimal list-inside space-y-1">
              <li>Go to Robinhood Crypto developer settings</li>
              <li>Create a new API credential</li>
              <li>Paste the public key generated above</li>
              <li>Copy the <strong className="text-slate-300">rh-api-…</strong> identifier they give you</li>
            </ol>
            <a
              href="https://robinhood.com/account/crypto"
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-1.5 rounded-md bg-blue-600/20 border border-blue-600/40 px-3 py-1.5 text-blue-300 hover:bg-blue-600/30 transition-colors"
            >
              <ExternalLink className="h-3.5 w-3.5" />
              Open Robinhood → Account → Crypto
            </a>
          </div>

          {/* Step 3: Paste API key */}
          <div className="space-y-3">
            <p className="text-xs font-semibold text-slate-200">Step 3 — Paste your Robinhood API key</p>
            <Input
              label="API Key (rh-api-…)"
              placeholder="rh-api-xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
              value={state.apiKey}
              onChange={(e) => setState({ apiKey: e.target.value })}
            />
            <Input
              label="Base64 Private Key"
              type="password"
              placeholder="Auto-filled after keypair generation"
              value={state.privateKey}
              onChange={(e) => setState({ privateKey: e.target.value })}
            />
          </div>
        </div>
      )}

      {/* Verify & Save */}
      <div className="flex items-center gap-3 pt-1">
        <Button
          variant="outline"
          size="sm"
          loading={testing || saving}
          disabled={!canTest || (isKraken && !allKrakenOk)}
          onClick={testAndSave}
        >
          {saved ? (
            <><CheckCircle2 className="h-3.5 w-3.5 text-emerald-400" /> Saved</>
          ) : (
            'Verify & Save'
          )}
        </Button>
        {testResult && (
          <span className={cn('text-xs', testResult.ok ? 'text-emerald-400' : 'text-red-400')}>
            {testResult.msg}
          </span>
        )}
      </div>
    </div>
  )
}

function StepRisk({ state, setState }: { state: WizardState; setState: (s: Partial<WizardState>) => void }) {
  return (
    <div className="space-y-5">
      <p className="text-slate-400 text-sm">Configure your risk parameters. The bot will enforce these limits at all times.</p>

      <div className="grid grid-cols-2 gap-3">
        <Input
          label="Total Capital (USD)"
          type="number"
          placeholder="10000"
          value={state.totalCapital}
          onChange={(e) => setState({ totalCapital: e.target.value })}
          hint="Amount the bot is allowed to use"
        />
        <Input
          label="Max Position Size (%)"
          type="number"
          placeholder="10"
          min="1"
          max="100"
          value={state.positionSizePct}
          onChange={(e) => setState({ positionSizePct: e.target.value })}
          hint="Max % of capital per trade"
        />
        <Input
          label="Stop Loss (%)"
          type="number"
          placeholder="3"
          min="0.5"
          max="20"
          value={state.stopLossPct}
          onChange={(e) => setState({ stopLossPct: e.target.value })}
          hint="Exit position if price drops this %"
        />
        <Input
          label="Daily Loss Limit (%)"
          type="number"
          placeholder="5"
          min="1"
          max="50"
          value={state.dailyLossPct}
          onChange={(e) => setState({ dailyLossPct: e.target.value })}
          hint="Bot pauses if daily loss exceeds this"
        />
      </div>

      {/* Paper / Live toggle */}
      <div>
        <p className="text-sm font-medium text-slate-300 mb-2">Trading Mode</p>
        <div className="flex gap-3">
          {(['paper', 'live'] as const).map((m) => (
            <button
              key={m}
              onClick={() => setState({ tradingMode: m })}
              className={cn(
                'flex items-center gap-2 rounded-lg border px-4 py-2.5 text-sm transition-colors',
                state.tradingMode === m
                  ? m === 'live'
                    ? 'border-emerald-500 bg-emerald-500/10 text-emerald-300'
                    : 'border-purple-500 bg-purple-500/10 text-purple-300'
                  : 'border-slate-700 text-slate-400 hover:border-slate-500'
              )}
            >
              {m === 'live' ? <Zap className="h-4 w-4" /> : <Shield className="h-4 w-4" />}
              {m === 'paper' ? 'Paper Trading (Safe)' : 'Live Trading'}
            </button>
          ))}
        </div>
        {state.tradingMode === 'live' && (
          <p className="mt-2 text-xs text-amber-400 flex items-center gap-1">
            <AlertTriangle className="h-3 w-3" />
            Live mode uses real funds. Make sure your settings are correct.
          </p>
        )}
      </div>
    </div>
  )
}

function StepStrategies({ state, setState }: { state: WizardState; setState: (s: Partial<WizardState>) => void }) {
  function toggle(id: string) {
    setState({
      selectedStrategies: state.selectedStrategies.includes(id)
        ? state.selectedStrategies.filter((s) => s !== id)
        : [...state.selectedStrategies, id],
    })
  }

  return (
    <div className="space-y-4">
      <p className="text-slate-400 text-sm">Select which strategies the bot should use. You can adjust these later on the Strategies page.</p>
      <div className="space-y-2">
        {BUILTIN_STRATEGIES.map((s) => {
          const active = state.selectedStrategies.includes(s.id)
          return (
            <button
              key={s.id}
              onClick={() => toggle(s.id)}
              className={cn(
                'w-full rounded-lg border p-3 text-left transition-all',
                active ? 'border-blue-500 bg-blue-500/10' : 'border-slate-700 bg-slate-800/50 hover:border-slate-500'
              )}
            >
              <div className="flex items-center justify-between">
                <span className="text-sm font-medium text-slate-200">{s.label}</span>
                <div className="flex items-center gap-2">
                  <Badge variant={riskColor[s.risk] as any} className="text-[10px]">{s.risk} risk</Badge>
                  {active && <CheckCircle2 className="h-4 w-4 text-blue-400" />}
                </div>
              </div>
              <p className="text-xs text-slate-400 mt-0.5">{s.desc}</p>
            </button>
          )
        })}
      </div>
    </div>
  )
}

function StepReview({ state, onLaunch, launching }: { state: WizardState; onLaunch: () => void; launching: boolean }) {
  const rows = [
    { label: 'Exchange', value: state.exchange.toUpperCase() },
    { label: 'Mode', value: state.tradingMode === 'live' ? '🔴 LIVE' : '🟣 PAPER' },
    { label: 'Total Capital', value: `$${state.totalCapital || '—'}` },
    { label: 'Max Position Size', value: `${state.positionSizePct || '—'}%` },
    { label: 'Stop Loss', value: `${state.stopLossPct || '—'}%` },
    { label: 'Daily Loss Limit', value: `${state.dailyLossPct || '—'}%` },
    { label: 'Strategies', value: `${state.selectedStrategies.length} selected` },
  ]

  return (
    <div className="space-y-5">
      <p className="text-slate-400 text-sm">Review your configuration before launching the bot.</p>
      <div className="rounded-lg border border-slate-700 divide-y divide-slate-700/60">
        {rows.map(({ label, value }) => (
          <div key={label} className="flex items-center justify-between px-4 py-2.5">
            <span className="text-sm text-slate-400">{label}</span>
            <span className="text-sm font-medium text-slate-200">{value}</span>
          </div>
        ))}
      </div>
      <Button size="lg" className="w-full" loading={launching} onClick={onLaunch}>
        <Bot className="h-4 w-4" />
        Launch Bot
      </Button>
    </div>
  )
}

// ── Main wizard ──────────────────────────────────────────────────────────────

export default function OnboardingPage() {
  const navigate = useNavigate()
  const setOnboardingComplete = useSettingsStore((s) => s.setOnboardingComplete)
  const setExchange = useSettingsStore((s) => s.setExchange)
  const setTradingMode = useSettingsStore((s) => s.setTradingMode)

  const [step, setStep] = useState(0)
  const [launching, setLaunching] = useState(false)
  const [state, setStateRaw] = useState<WizardState>({
    exchange: 'kraken',
    apiKey: '',
    privateKey: '',
    tradingMode: 'paper',
    totalCapital: '10000',
    positionSizePct: '10',
    stopLossPct: '3',
    dailyLossPct: '5',
    selectedStrategies: ['builtin_mean_reversion', 'builtin_momentum'],
  })

  function setState(patch: Partial<WizardState>) {
    setStateRaw((s) => ({ ...s, ...patch }))
  }

  async function handleLaunch() {
    setLaunching(true)
    try {
      // Save config
      await fetch('/api/config', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          total_capital: parseFloat(state.totalCapital),
          max_position_size_pct: parseFloat(state.positionSizePct) / 100,
          stop_loss_pct: parseFloat(state.stopLossPct) / 100,
          max_daily_loss_pct: parseFloat(state.dailyLossPct) / 100,
          trading_mode: state.tradingMode,
          exchange: state.exchange,
        }),
      })
      // Start bot
      await fetch('/api/bot/start', { method: 'POST' })

      setExchange(state.exchange)
      setTradingMode(state.tradingMode)
      setOnboardingComplete(true)
      navigate('/')
    } catch {
      setLaunching(false)
    }
  }

  const stepContent = [
    <StepExchange key="exchange" state={state} setState={setState} />,
    <StepApiKeys key="keys" state={state} setState={setState} />,
    <StepRisk key="risk" state={state} setState={setState} />,
    <div key="pairs" className="space-y-3">
      <p className="text-slate-400 text-sm">
        The bot will automatically trade all supported pairs for your chosen exchange. You can filter pairs in Settings after setup.
      </p>
      <div className="rounded-lg border border-slate-700 bg-slate-800/50 p-4 text-sm text-slate-300 space-y-2">
        <p className="font-medium text-slate-200">Default Kraken pairs:</p>
        {['XBT/USD', 'ETH/USD', 'SOL/USD', 'ADA/USD', 'DOT/USD'].map((p) => (
          <div key={p} className="flex items-center gap-2">
            <CheckCircle2 className="h-3.5 w-3.5 text-emerald-400" />
            <span>{p}</span>
          </div>
        ))}
      </div>
    </div>,
    <StepStrategies key="strategies" state={state} setState={setState} />,
    <StepReview key="review" state={state} onLaunch={handleLaunch} launching={launching} />,
  ]

  return (
    <div className="min-h-screen bg-slate-950 flex items-center justify-center p-6">
      <div className="w-full max-w-xl">
        {/* Header */}
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center h-12 w-12 rounded-xl bg-blue-600 mb-4">
            <Bot className="h-6 w-6 text-white" />
          </div>
          <h1 className="text-2xl font-bold text-white">Welcome to AlgoTrader</h1>
          <p className="text-slate-400 text-sm mt-1">Set up your trading bot in a few steps</p>
        </div>

        {/* Step indicators */}
        <div className="flex items-center justify-center gap-1.5 mb-6">
          {STEPS.map((label, i) => (
            <div key={label} className="flex items-center gap-1.5">
              <div
                className={cn(
                  'flex items-center justify-center h-7 w-7 rounded-full text-xs font-bold transition-colors',
                  i < step ? 'bg-emerald-600 text-white' :
                  i === step ? 'bg-blue-600 text-white' :
                  'bg-slate-800 text-slate-500'
                )}
              >
                {i < step ? <CheckCircle2 className="h-4 w-4" /> : i + 1}
              </div>
              {i < STEPS.length - 1 && (
                <div className={cn('h-0.5 w-6', i < step ? 'bg-emerald-600' : 'bg-slate-700')} />
              )}
            </div>
          ))}
        </div>

        {/* Card */}
        <Card>
          <div className="px-5 py-4 border-b border-slate-700/40">
            <h2 className="font-semibold text-white">Step {step + 1}: {STEPS[step]}</h2>
          </div>
          <CardContent className="pt-5">{stepContent[step]}</CardContent>
        </Card>

        {/* Navigation */}
        {step < STEPS.length - 1 && (
          <div className="flex items-center justify-between mt-4">
            <Button
              variant="ghost"
              disabled={step === 0}
              onClick={() => setStep((s) => s - 1)}
            >
              <ChevronLeft className="h-4 w-4" /> Back
            </Button>
            <Button onClick={() => setStep((s) => s + 1)}>
              Next <ChevronRight className="h-4 w-4" />
            </Button>
          </div>
        )}
      </div>
    </div>
  )
}
