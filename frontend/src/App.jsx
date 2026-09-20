import { useEffect, useState } from 'react'
import QrScanner from 'qr-scanner'
import QRCode from 'qrcode'
import './App.css'

const api = (import.meta.env.VITE_API_URL || 'https://honey-chain-backend-tjvt.onrender.com/api').replace(/\/$/, '')
const HIVE_ID = 'HIVE001'

const request = async (path) => {
  const sessionToken = sessionStorage.getItem('honeychain_session')
  const headers = sessionToken ? { Authorization: `Bearer ${sessionToken}` } : undefined
  const response = await fetch(`${api}${path}`, { credentials: 'include', headers })
  if (!response.ok) {
    if (response.status === 401) sessionStorage.removeItem('honeychain_session')
    const detail = await response.text().catch(() => '')
    const error = new Error(detail || `Request failed (${response.status})`)
    error.status = response.status
    throw error
  }
  return response.json()
}

const post = async (path, body) => {
  const sessionToken = sessionStorage.getItem('honeychain_session')
  const headers = { 'Content-Type': 'application/json', ...(sessionToken ? { Authorization: `Bearer ${sessionToken}` } : {}) }
  const response = await fetch(`${api}${path}`, { method: 'POST', credentials: 'include', headers, body: JSON.stringify(body) })
  if (!response.ok) {
    if (response.status === 401) sessionStorage.removeItem('honeychain_session')
    const detail = await response.text().catch(() => '')
    const error = new Error(detail || `Request failed (${response.status})`)
    error.status = response.status
    throw error
  }
  return response.json()
}

const formatValue = (value, suffix = '') => (value === null || value === undefined || value === '' ? '—' : `${value}${suffix}`)

const formatTimestamp = (value) => {
  if (!value) return 'No timestamp'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' })
}

const getErrorMessage = (error, fallback) => error?.status === 404 ? 'Record not found.' : error?.message === 'Failed to fetch' ? fallback : error?.message || fallback

const sensorMetrics = [
  { key: 'temperature', label: 'Temperature', unit: '°C', color: '#e07a5f' },
  { key: 'humidity', label: 'Humidity', unit: '%', color: '#3d8b9b' },
  { key: 'weight', label: 'Hive weight', unit: 'g', color: '#d4a72c' },
  { key: 'gas_raw', label: 'Air / gas level', unit: 'raw', color: '#6c8c63' },
  { key: 'mic_raw', label: 'Hive activity', unit: 'raw', color: '#8a6f9e' },
]

const parseHoneyChainQr = (value) => {
  const text = value.trim()
  if (!text) return null
  if (/^HC[A-Za-z0-9_-]+$/i.test(text)) return text
  try {
    const url = new URL(text, window.location.origin)
    if (!['http:', 'https:'].includes(url.protocol)) return null
    const match = url.pathname.match(/^\/verify\/([^/]+)\/?$/)
    return match ? decodeURIComponent(match[1]) : null
  } catch {
    return null
  }
}

function QrScannerPanel({ onDetected, onClose }) {
  const [videoElement, setVideoElement] = useState(null)
  const [status, setStatus] = useState('requesting')
  const [message, setMessage] = useState('Requesting camera access…')

  useEffect(() => {
    if (!videoElement) return undefined
    const scanner = new QrScanner(videoElement, (result) => {
      const batchId = parseHoneyChainQr(result.data)
      if (!batchId) {
        setStatus('invalid')
        setMessage('Not a Honey Chain QR code.')
        return
      }
      setStatus('detected')
      setMessage(`QR detected: ${batchId}`)
      scanner.stop()
      onDetected(batchId)
    }, { highlightScanRegion: false, highlightCodeOutline: true, returnDetailedScanResult: true })

    scanner.start().then(() => {
      setStatus('ready')
      setMessage('Scanning for a Honey Chain QR code…')
    }).catch((error) => {
      setStatus(error?.name === 'NotAllowedError' ? 'denied' : 'unavailable')
      setMessage(error?.name === 'NotAllowedError' ? 'Camera permission was denied.' : 'Camera unavailable. Enter the batch ID manually.')
    })
    return () => scanner.destroy()
  }, [videoElement, onDetected])

  return <div className="scanner-backdrop" role="dialog" aria-modal="true" aria-labelledby="scanner-title"><div className="scanner-panel"><div className="scanner-heading"><div><span className="eyebrow">Live camera</span><h2 id="scanner-title">Scan Your Honey Chain QR</h2><p>Point your camera at the QR code on your bottle.</p></div><button className="scanner-close" onClick={onClose} aria-label="Close Scanner">×</button></div><div className="scanner-viewport"><video ref={setVideoElement} muted playsInline aria-label="QR scanner camera preview" /><span className="scanner-frame" /></div><div className={`scanner-status ${status}`}><span className="scanner-status-dot" />{message}</div><button className="button scanner-fallback" onClick={onClose}>Enter Batch ID manually</button></div></div>
}

function MetricCard({ metric, value }) {
  return <div className="metric-card"><span className="metric-label">{metric.label}</span><strong>{formatValue(value, metric.unit === 'raw' ? '' : ` ${metric.unit}`)}</strong><span className="metric-unit">{metric.unit === 'raw' ? 'sensor signal' : 'current reading'}</span></div>
}

function TrendChart({ metric, readings }) {
  const points = [...readings].filter((reading) => Number.isFinite(Number(reading[metric.key]))).reverse().map((reading, index) => ({ value: Number(reading[metric.key]), timestamp: formatTimestamp(reading.timestamp), index }))
  const width = 360
  const height = 150
  const padding = { top: 16, right: 12, bottom: 30, left: 34 }
  const values = points.map((point) => point.value)
  const min = values.length ? Math.min(...values) : 0
  const max = values.length ? Math.max(...values) : 1
  const range = max - min || 1
  const x = (index) => padding.left + (points.length === 1 ? (width - padding.left - padding.right) / 2 : index * (width - padding.left - padding.right) / (points.length - 1))
  const y = (value) => padding.top + (max - value) * (height - padding.top - padding.bottom) / range
  const path = points.map((point, index) => `${index ? 'L' : 'M'} ${x(index)} ${y(point.value)}`).join(' ')

  return <article className="trend-card"><div className="trend-heading"><div><h3>{metric.label}</h3><span>{metric.unit === 'raw' ? 'Raw sensor signal' : `Measured in ${metric.unit}`}</span></div><span className="trend-count">{points.length} readings</span></div>{points.length < 2 ? <div className="chart-empty">More readings are needed to show a trend.</div> : <svg className="trend-chart" viewBox={`0 0 ${width} ${height}`} role="img" aria-label={`${metric.label} trend`}><line x1={padding.left} x2={width - padding.right} y1={height - padding.bottom} y2={height - padding.bottom} className="chart-axis" /><line x1={padding.left} x2={padding.left} y1={padding.top} y2={height - padding.bottom} className="chart-axis" /><path d={path} fill="none" stroke={metric.color} strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />{points.map((point, index) => <circle key={`${point.timestamp}-${index}`} cx={x(index)} cy={y(point.value)} r="4" fill={metric.color}><title>{`${point.value} ${metric.unit} · ${point.timestamp}`}</title></circle>)}<text x={padding.left} y={height - 8} className="chart-label">{points[0].timestamp}</text><text x={width - padding.right} y={height - 8} textAnchor="end" className="chart-label">{points[points.length - 1].timestamp}</text><text x={padding.left - 8} y={padding.top + 4} textAnchor="end" className="chart-label">{max.toFixed(metric.unit === 'raw' ? 0 : 1)}</text><text x={padding.left - 8} y={height - padding.bottom + 4} textAnchor="end" className="chart-label">{min.toFixed(metric.unit === 'raw' ? 0 : 1)}</text></svg>}</article>
}

function HealthPanel({ health }) {
  if (!health) return <div className="empty-state">No health data is available for this hive.</div>
  return <div className="health-content"><div className="health-score"><strong>{health.health_score ?? '—'}</strong><span>/ 100</span></div><span className={`status-badge ${health.risk_level || 'unknown'}`}>{health.risk_level || 'unknown'} risk</span><div className="health-copy"><h3>What to do next</h3><p>{health.recommendation || 'Continue monitoring the hive.'}</p>{health.reasons?.length ? <ul>{health.reasons.map((reason, index) => <li key={index}>{reason}</li>)}</ul> : <p className="muted">No conditions reported.</p>}</div><span className="timestamp">Updated {formatTimestamp(health.timestamp)}</span></div>
}

function FarmerView({ onConsumer }) {
  const [dashboard, setDashboard] = useState(null)
  const [hive, setHive] = useState(null)
  const [readings, setReadings] = useState([])
  const [health, setHealth] = useState(null)
  const [batchId, setBatchId] = useState('')
  const [batchData, setBatchData] = useState(null)
  const [trace, setTrace] = useState([])
  const [ledger, setLedger] = useState(null)
  const [loading, setLoading] = useState(true)
  const [batchLoading, setBatchLoading] = useState(false)
  const [error, setError] = useState('')

  const loadFarmer = async (showLoading = true) => {
    if (showLoading) setLoading(true)
    try {
      const [dashboardData, hives, sensorData, healthData] = await Promise.all([request('/dashboard'), request('/hives'), request(`/sensors/${HIVE_ID}`), request(`/health/${HIVE_ID}`)])
      setDashboard(dashboardData); setHive((hives || []).find((item) => item.hive_id === HIVE_ID) || null); setReadings(Array.isArray(sensorData) ? sensorData : []); setHealth(healthData); setError('')
    } catch (requestError) { setError(getErrorMessage(requestError, 'Unable to connect to the Honey Chain API.')) } finally { setLoading(false) }
  }

  const loadBatch = async () => {
    const id = batchId.trim()
    if (!id) return
    setBatchLoading(true)
    try {
      const [batch, traceData, ledgerData] = await Promise.all([request(`/batches/${id}`), request(`/trace/${id}`), request(`/ledger/${id}`)])
      setBatchData(batch); setTrace(Array.isArray(traceData) ? traceData : []); setLedger(ledgerData); setError('')
    } catch (requestError) { setBatchData(null); setTrace([]); setLedger(null); setError(getErrorMessage(requestError, 'Unable to load this batch.')) } finally { setBatchLoading(false) }
  }

  useEffect(() => {
    loadFarmer(false)
    const interval = window.setInterval(() => loadFarmer(false), 5000)
    return () => window.clearInterval(interval)
  }, [])

  const latest = readings[0] || dashboard?.latest_sensor
  const status = hive?.status || 'unknown'

  return <div className="view-stack"><section className="page-intro"><div><span className="eyebrow">Farmer workspace / live hive</span><h2>Smart hive dashboard</h2><p>Monitor the latest field readings and the conditions that need your attention.</p></div><button className="button secondary-button" onClick={loadFarmer} disabled={loading}>{loading ? 'Refreshing…' : 'Refresh readings'}</button></section>{error && <div className="alert" role="alert">{error}</div>}<section className="overview-grid"><article className="overview-card hive-overview"><div className="section-kicker">Monitored hive</div><div className="hive-title"><div><h3>{HIVE_ID}</h3><span>{hive?.name || 'Field hive'}</span></div><span className={`status-dot ${status}`}>{status}</span></div><p>{hive?.location || 'Location not available'}</p><div className="overview-footer"><span>Latest update</span><strong>{formatTimestamp(latest?.timestamp)}</strong></div></article><article className="overview-card health-overview"><div className="section-kicker">Current health</div><HealthPanel health={health} /></article></section><section className="section-block"><div className="section-heading"><div><span className="section-kicker">Live sensors</span><h2>Current conditions</h2></div><span className="data-note">{readings.length ? `${readings.length} stored readings` : 'Waiting for readings'}</span></div>{loading ? <div className="loading-state">Loading live sensor data…</div> : latest ? <div className="metrics-grid">{sensorMetrics.map((metric) => <MetricCard key={metric.key} metric={metric} value={latest[metric.key]} />)}</div> : <div className="empty-state">No sensor readings are available for {HIVE_ID}.</div>}</section><section className="section-block"><div className="section-heading"><div><span className="section-kicker">Real sensor history</span><h2>Reading trends</h2></div><span className="data-note">From GET /sensors/{HIVE_ID}</span></div><div className="charts-grid">{sensorMetrics.map((metric) => <TrendChart key={metric.key} metric={metric} readings={readings} />)}</div></section><section className="section-block records-section"><div className="section-heading"><div><span className="section-kicker">Traceability tools</span><h2>Batch and harvest records</h2></div></div><div className="batch-loader"><input aria-label="Batch ID" value={batchId} onChange={(event) => setBatchId(event.target.value)} onKeyDown={(event) => event.key === 'Enter' && loadBatch()} placeholder="Enter batch ID, e.g. HC2026-001" /><button className="button primary-button" onClick={loadBatch} disabled={batchLoading}>{batchLoading ? 'Loading…' : 'Load record'}</button><button className="button text-button" onClick={onConsumer}>Open consumer view</button></div>{batchData && <div className="record-grid"><div><span>Batch ID</span><strong>{batchData.batch_id}</strong></div><div><span>Hive</span><strong>{batchData.hive_id}</strong></div><div><span>Harvest date</span><strong>{batchData.harvest_date}</strong></div><div><span>Weight</span><strong>{formatValue(batchData.weight, ' g')}</strong></div><div><span>Status</span><strong>{batchData.status}</strong></div><div><span>Ledger integrity</span><strong className={ledger?.ledger_integrity ? 'good-text' : 'warning-text'}>{ledger ? (ledger.ledger_integrity ? 'Verified' : 'Needs review') : '—'}</strong></div></div>}{batchData && <div className="trace-row">{trace.map((item) => <div className="trace-item" key={item.id}><span>{item.event_type}</span><strong>{item.description}</strong><small>{formatTimestamp(item.timestamp)}</small></div>)}</div>}</section></div>
}

function BatchQrPanel({ batchId }) {
  const [image, setImage] = useState('')
  const [error, setError] = useState('')
  const publicUrl = (import.meta.env.VITE_PUBLIC_APP_URL || window.location.origin).replace(/\/$/, '')
  const verificationUrl = `${publicUrl}/verify/${encodeURIComponent(batchId)}`

  useEffect(() => {
    QRCode.toDataURL(verificationUrl, { width: 240, margin: 2 }).then(setImage).catch(() => setError('Unable to generate the QR image.'))
  }, [verificationUrl])

  return <div className="batch-qr-card"><div><span className="section-kicker">Bottle QR</span><h3>{batchId}</h3><p>Scan to open the public Honey Chain verification page.</p><code>{verificationUrl}</code></div>{error ? <p className="action-error">{error}</p> : image ? <img src={image} alt={`Honey Chain verification QR for ${batchId}`} /> : <span className="muted">Generating QR…</span>}</div>
}

function HarvestPanel() {
  const [form, setForm] = useState({ batch_id: '', harvest_date: '', weight: '' })
  const [event, setEvent] = useState({ batch_id: '', event_type: 'processing', description: '' })
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)
  const [qrBatchId, setQrBatchId] = useState('')

  const createBatch = async (submitEvent) => {
    submitEvent.preventDefault()
    setSaving(true); setError(''); setMessage('')
    try {
      const id = form.batch_id.trim()
      await post('/batches', { ...form, hive_id: HIVE_ID, weight: Number(form.weight) })
      await post(`/batches/${id}/anchor`, {})
      setMessage(`Batch ${id} created, anchored, and linked to ${HIVE_ID}.`)
      setEvent((current) => ({ ...current, batch_id: form.batch_id }))
      setQrBatchId(form.batch_id)
    } catch (requestError) { setError(getErrorMessage(requestError, 'Unable to create the batch.')) } finally { setSaving(false) }
  }

  const addTraceEvent = async (submitEvent) => {
    submitEvent.preventDefault()
    setSaving(true); setError(''); setMessage('')
    try {
      await post(`/trace/${event.batch_id.trim()}`, { event_type: event.event_type, description: event.description })
      setMessage(`${event.event_type} event added to ${event.batch_id}.`)
      setEvent((current) => ({ ...current, description: '' }))
    } catch (requestError) { setError(getErrorMessage(requestError, 'Unable to add the trace event.')) } finally { setSaving(false) }
  }

  return <section className="farmer-actions section-block"><div className="section-heading"><div><span className="section-kicker">Operational workflow</span><h2>Record harvest and journey events</h2></div><span className="data-note">Uses the existing batch and trace APIs</span></div><div className="action-forms"><form onSubmit={createBatch}><h3>Create honey batch</h3><label>Batch ID<input required value={form.batch_id} onChange={(event) => setForm({ ...form, batch_id: event.target.value })} placeholder="HC2026-001" /></label><label>Harvest date<input required type="date" value={form.harvest_date} onChange={(event) => setForm({ ...form, harvest_date: event.target.value })} /></label><label>Harvest weight (g)<input required min="0" max="1000" step="any" type="number" value={form.weight} onChange={(event) => setForm({ ...form, weight: event.target.value })} /></label><button className="button primary-button" disabled={saving}>Create batch</button></form><form onSubmit={addTraceEvent}><h3>Add traceability event</h3><label>Batch ID<input required value={event.batch_id} onChange={(input) => setEvent({ ...event, batch_id: input.target.value })} placeholder="Existing batch ID" /></label><label>Event type<select value={event.event_type} onChange={(input) => setEvent({ ...event, event_type: input.target.value })}><option>processing</option><option>packaging</option><option>distribution</option></select></label><label>Description<textarea required value={event.description} onChange={(input) => setEvent({ ...event, description: input.target.value })} placeholder="Describe the recorded event" /></label><button className="button secondary-button" disabled={saving}>Add event</button></form></div><button className="button text-button" onClick={() => event.batch_id.trim() && setQrBatchId(event.batch_id.trim())}>View bottle QR for an existing batch</button>{message && <p className="action-success" role="status">{message}</p>}{error && <p className="action-error" role="alert">{error}</p>}{qrBatchId && <BatchQrPanel batchId={qrBatchId} />}</section>
}

function ConsumerView({ initialBatchId = '' }) {
  const [batchId, setBatchId] = useState(initialBatchId)
  const [result, setResult] = useState(null)
  const [qr, setQr] = useState(null)
  const [hiveLocation, setHiveLocation] = useState('Location unavailable')
  const [state, setState] = useState('idle')
  const [error, setError] = useState('')

  const verifyBatch = async () => {
    const id = batchId.trim()
    if (!id) return
    setState('loading')
    setError('')
    setResult(null)
    setQr(null)

    try {
      const verification = await request(`/verify/${id}`)
      setResult(verification)
      setState('success')

      try {
        const qrData = await request(`/batches/${id}/qr`)
        setQr(qrData)
      } catch {
        setQr(null)
      }
    } catch (requestError) {
      setError(getErrorMessage(requestError, 'Verification could not be completed.'))
      setState(requestError?.status === 404 ? 'not-found' : 'error')
    }
  }

  useEffect(() => {
    if (initialBatchId) verifyBatch()
  }, [initialBatchId])

  useEffect(() => {
    if (!result?.hive_id) return
    request('/hives').then((hives) => {
      const source = Array.isArray(hives) ? hives.find((hive) => hive.hive_id === result.hive_id) : null
      setHiveLocation(source?.location || 'Location unavailable')
    }).catch(() => setHiveLocation('Location unavailable'))
  }, [result])

  return <div className="consumer-view"><section className="consumer-hero"><span className="eyebrow">Consumer verification</span><h2>Verified Honey Journey</h2><p>Enter the batch ID on your jar to view its recorded source, harvest details, and traceability integrity.</p><div className="verify-form"><input aria-label="Batch ID" value={batchId} onChange={(event) => setBatchId(event.target.value)} onKeyDown={(event) => event.key === 'Enter' && verifyBatch()} placeholder="Batch ID" /><button className="button primary-button" onClick={verifyBatch} disabled={state === 'loading'}>{state === 'loading' ? 'Checking…' : 'Verify batch'}</button></div></section>{state === 'not-found' && <div className="consumer-message warning-message"><strong>Batch not found</strong><span>Check the ID and try again.</span></div>}{state === 'error' && <div className="consumer-message error-message"><strong>Verification unavailable</strong><span>{error}</span></div>}{result && <section className="verification-result"><div className="verified-banner"><div className="verified-mark">{result.ledger_integrity ? '✓' : '!'}</div><div><span className="section-kicker">Verification result</span><h2>{result.ledger_integrity ? 'Ledger integrity verified' : 'Record integrity needs review'}</h2><p>{result.ledger_integrity ? 'Hash-linked records make changes to recorded traceability history detectable.' : 'The recorded traceability history could not be fully validated.'}</p></div><span className="integrity-pill">{result.ledger_integrity ? 'Verified' : 'Review needed'}</span></div><div className="consumer-details"><div><span>Batch ID</span><strong>{result.batch_id}</strong></div><div><span>Source hive</span><strong>{result.hive_id}</strong></div><div><span>Location</span><strong>{hiveLocation}</strong></div><div><span>Harvest date</span><strong>{result.harvest_date}</strong></div><div><span>Harvest quantity</span><strong>{formatValue(result.quantity_kg, ' kg')}</strong></div><div><span>Batch status</span><strong>{result.status}</strong></div></div><div className="timeline"><div className="section-heading"><div><span className="section-kicker">Your honey's journey</span><h3>Traceability timeline</h3></div></div>{result.traceability?.length ? result.traceability.map((item) => <div className="timeline-item" key={item.id}><span className="timeline-dot" /><div><strong>{item.event_type}</strong><p>{item.description}</p><small>{formatTimestamp(item.timestamp)}</small></div></div>) : <div className="empty-state">No traceability events are available.</div>}</div>{(result.verification_url || qr?.verification_url) && <div className="public-target"><span>Public verification target</span><code>{result.verification_url || qr.verification_url}</code></div>}<span className="verification-time">Checked {formatTimestamp(result.verification_timestamp)}</span></section>}</div>
}

function AuthPage({ mode }) {
  const isRegister = mode === 'register'
  const [form, setForm] = useState({ full_name: '', email: '', phone: '', farmer_id: '', farm_name: '', farm_location: '', experience: '', password: '', confirm_password: '' })
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)

  const submit = async (event) => {
    event.preventDefault()
    setError(''); setMessage('')
    if (isRegister && form.password !== form.confirm_password) {
      setError('Passwords do not match.')
      return
    }
    setSaving(true)
    try {
      const result = await post(isRegister ? '/auth/register' : '/auth/login', isRegister ? form : { email: form.email, password: form.password })
      if (isRegister) {
        setMessage('Registration submitted. An administrator must verify your farmer account before login.')
        setForm({ full_name: '', email: '', phone: '', farmer_id: '', farm_name: '', farm_location: '', experience: '', password: '', confirm_password: '' })
      } else {
        sessionStorage.setItem('honeychain_session', result.session_token)
        navigate(result.role === 'ADMIN' ? '/admin' : '/farmer')
      }
    } catch (requestError) {
      setError(getErrorMessage(requestError, 'Unable to complete this request.'))
    } finally { setSaving(false) }
  }

  const fields = isRegister
    ? [['full_name', 'Full Name'], ['email', 'Email'], ['phone', 'Phone'], ['farmer_id', 'Farmer ID'], ['farm_name', 'Farm Name'], ['farm_location', 'Farm Location'], ['experience', 'Experience']]
    : [['email', 'Email']]

  return <section className="auth-page"><div className="auth-card"><span className="eyebrow">{isRegister ? 'Farmer onboarding' : 'Secure access'}</span><h2>{isRegister ? 'Register your farm' : 'Farmer login'}</h2><p>{isRegister ? 'Submit your farm details for administrator verification.' : 'Verified farmers can access hive operations and traceability tools.'}</p><form onSubmit={submit}>{fields.map(([key, label]) => <label key={key}>{label}<input required type={key === 'email' ? 'email' : 'text'} value={form[key]} onChange={(event) => setForm({ ...form, [key]: event.target.value })} /></label>)}<label>Password<input required type="password" minLength="8" value={form.password} onChange={(event) => setForm({ ...form, password: event.target.value })} /></label>{isRegister && <label>Confirm Password<input required type="password" minLength="8" value={form.confirm_password} onChange={(event) => setForm({ ...form, confirm_password: event.target.value })} /></label>}<button className="button primary-button" disabled={saving}>{saving ? 'Submitting…' : isRegister ? 'Submit registration' : 'Log in'}</button></form>{message && <p className="action-success" role="status">{message}</p>}{error && <p className="action-error" role="alert">{error}</p>}<button className="button text-button" onClick={() => navigate(isRegister ? '/login' : '/register')}>{isRegister ? 'Already registered? Log in' : 'Need a farmer account? Register'}</button></div></section>
}

function AdminPage() {
  const [farmers, setFarmers] = useState([])
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)

  const loadFarmers = async () => {
    try { setFarmers(await request('/admin/farmers?status=PENDING')); setError('') } catch (requestError) { setError(getErrorMessage(requestError, 'Admin access is required.')) } finally { setLoading(false) }
  }

  const decide = async (farmerId, action) => {
    try { await post(`/admin/farmers/${encodeURIComponent(farmerId)}/${action}`, {}); await loadFarmers() } catch (requestError) { setError(getErrorMessage(requestError, 'Unable to update farmer status.')) }
  }

  useEffect(() => { loadFarmers() }, [])
  return <section className="auth-page"><div className="admin-panel"><div className="page-intro"><div><span className="eyebrow">Administration</span><h2>Pending farmer verification</h2><p>Review registration requests before granting traceability write access.</p></div><button className="button secondary-button" onClick={loadFarmers}>Refresh</button></div>{error && <div className="alert" role="alert">{error}</div>}{loading ? <div className="loading-state">Loading requests…</div> : farmers.length ? <div className="admin-table">{farmers.map((farmer) => <div className="admin-row" key={farmer.farmer_id}><div><strong>{farmer.full_name}</strong><span>{farmer.farm_name} · {farmer.farmer_id}</span><small>{farmer.email} · {farmer.farm_location || 'Location not provided'}</small></div><div className="admin-actions"><button className="button primary-button" onClick={() => decide(farmer.farmer_id, 'approve')}>Approve</button><button className="button secondary-button" onClick={() => decide(farmer.farmer_id, 'reject')}>Reject</button></div></div>)}</div> : <div className="empty-state">No pending farmer registrations.</div>}</div></section>
}

function FarmerGate() {
  const [farmer, setFarmer] = useState(null)
  const [error, setError] = useState('')
  useEffect(() => { request('/auth/me').then(setFarmer).catch((requestError) => setError(requestError?.status === 403 ? 'Your farmer account is awaiting verification.' : 'Please log in to open the farmer dashboard.')) }, [])
  if (error) return <section className="auth-page"><div className="auth-card"><span className="eyebrow">Farmer workspace</span><h2>{error}</h2><button className="button primary-button" onClick={() => navigate('/login')}>Open farmer login</button></div></section>
  if (!farmer) return <section className="auth-page"><div className="loading-state">Checking farmer session…</div></section>
  return <><section className="farmer-identity"><span className="eyebrow">Verified Farmer</span><strong>{farmer.full_name}</strong><span>{farmer.farm_name} · {farmer.farmer_id}</span><b>{farmer.status}</b></section><FarmerView onConsumer={() => navigate('/verify')} /><HarvestPanel /></>
}

function navigate(path) {
  window.history.pushState({}, '', path)
  window.dispatchEvent(new PopStateEvent('popstate'))
}

function LiveHivePreview() {
  const [data, setData] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    Promise.all([request('/dashboard'), request(`/health/${HIVE_ID}`)]).then(([dashboard, health]) => {
      setData({ reading: dashboard?.latest_sensor, health })
    }).catch(() => setError('Live hive data is unavailable right now.'))
  }, [])

  const reading = data?.reading
  return <section className="live-preview" id="live-hive"><div className="section-intro"><span className="eyebrow">Real-time field view</span><h2>Live Smart Hive</h2><p>Current values from the Honey Chain sensor API. Raw environment and acoustic signals are shown without unsupported conversions.</p></div>{error ? <div className="public-empty">{error}</div> : !data ? <div className="public-empty">Connecting to Honey Chain…</div> : !reading ? <div className="public-empty">Waiting for hive data.</div> : <div className="live-preview-grid"><div className="live-preview-status"><span className="live-dot" /> LIVE / {HIVE_ID}<strong>{data.health?.health_score ?? '—'}<small> health score</small></strong><span className={`status-badge ${data.health?.risk_level || 'unknown'}`}>{data.health?.risk_level || 'unknown'} risk</span><p>{data.health?.recommendation || 'Continue routine monitoring.'}</p></div><div className="live-preview-metrics">{sensorMetrics.map((metric) => <div key={metric.key}><span>{metric.label}</span><strong>{formatValue(reading[metric.key], metric.unit === 'raw' ? '' : ` ${metric.unit}`)}</strong></div>)}</div></div>}</section>
}

function LandingView() {
  const [batchId, setBatchId] = useState('')
  const [step, setStep] = useState(0)
  const [registrationOpen, setRegistrationOpen] = useState(false)
  const [scannerOpen, setScannerOpen] = useState(false)
  const steps = [['SMART HIVE', 'Connected hives capture the conditions that shape every harvest.'], ['MONITORING', 'Real sensor readings give beekeepers visibility into the apiary.'], ['HARVEST', 'Recorded harvest information stays connected to its source hive.'], ['TRACEABILITY', 'Events create a readable journey from harvest through the supply chain.'], ['LEDGER INTEGRITY', 'Hash-linked records make unexpected history changes detectable.'], ['YOUR BOTTLE', 'A public verification path lets consumers explore the recorded journey.']]
  const launchScanner = () => setScannerOpen(true)
  return <div className="landing"><section className="landing-hero" id="top"><div className="hero-copy"><span className="eyebrow light-eyebrow">Connected beekeeping / transparent honey</span><h1>Know Your Honey.<br /><em>From Hive to Bottle, Verified.</em></h1><p>Honey Chain connects smart beekeeping, traceability and consumer verification in one transparent ecosystem.</p><div className="hero-actions"><button className="button honey-button" onClick={() => document.getElementById('verify')?.scrollIntoView({ behavior: 'smooth' })}>Verify Your Bottle</button><button className="button ghost-button" onClick={() => document.getElementById('registration')?.scrollIntoView({ behavior: 'smooth' })}>Register Your Farm</button></div><button className="hero-link" onClick={() => navigate('/farmer')}>Open Farmer Dashboard →</button></div><div className="hero-visual"><div className="hive-orbit"><span className="orbit-ring ring-one" /><span className="orbit-ring ring-two" /><div className="hive-core"><span>HIVE</span><strong>001</strong><small>● LIVE SIGNAL</small></div></div><div className="floating-readout readout-top"><span>FIELD SIGNAL</span><strong>Connected</strong></div><div className="floating-readout readout-bottom"><span>TRACEABILITY</span><strong>Hash-linked</strong></div></div></section><div className="journey-strip">{['🐝 Hive', '📡 Monitoring', '🍯 Harvest', '🔗 Traceability', '📦 Bottle', '📱 Consumer'].map((item) => <span key={item}>{item}</span>)}</div><section className="public-section" id="verify"><div className="section-intro"><span className="eyebrow">Consumer trust layer</span><h2>Verify Your Bottle</h2><p>Scan the Honey Chain QR code on your bottle and discover its recorded journey from hive to bottle.</p></div><div className="verify-panel"><button className="qr-placeholder" onClick={launchScanner}><span>QR</span><small>SCAN BOTTLE</small></button><div><span className="section-kicker">Primary action</span><h3>Scan a Honey Chain QR</h3><p>Point your camera at the QR code, or use the batch ID fallback below.</p><button className="button primary-button scan-button" onClick={launchScanner}>Scan QR Code</button><span className="section-kicker manual-label">Manual fallback</span><h3>Enter a batch ID</h3><div className="landing-verify-form"><input aria-label="Verification batch ID" placeholder="e.g. HC2026-001" value={batchId} onChange={(event) => setBatchId(event.target.value)} /><button className="button primary-button" onClick={() => batchId.trim() && navigate(`/verify/${batchId.trim()}`)}>Verify</button></div></div></div></section><section className="journey-section" id="how-it-works"><div className="section-intro"><span className="eyebrow">One connected story</span><h2>From smart hive to verified bottle.</h2><p>Select a step to see how the recorded journey fits together.</p></div><div className="stepper">{steps.map((item, index) => <button key={item[0]} className={`journey-step ${step === index ? 'selected' : ''}`} onClick={() => setStep(index)}><span>0{index + 1}</span><strong>{item[0]}</strong></button>)}</div><div className="step-detail"><span>0{step + 1}</span><div><strong>{steps[step][0]}</strong><p>{steps[step][1]}</p></div></div></section><section className="public-section story-section" id="beekeepers"><div className="section-intro"><span className="eyebrow">Real field visibility</span><h2>Your Hive Has a Story.</h2><p>Sensor data provides visibility into hive conditions without turning raw signals into unsupported claims.</p></div><div className="stakeholder-grid"><article><span>01 / BEEKEEPERS</span><h3>See the conditions behind each harvest.</h3><p>Monitor readings and health insights from the farmer dashboard.</p><button onClick={() => navigate('/farmer')}>Explore Farmer Dashboard →</button></article><article><span>02 / SUPPLY CHAIN</span><h3>Follow every recorded batch event.</h3><p>Keep harvest and traceability records connected as honey moves.</p><button onClick={() => document.getElementById('traceability')?.scrollIntoView({ behavior: 'smooth' })}>Explore Traceability →</button></article><article><span>03 / CONSUMERS</span><h3>Scan a bottle and discover its journey.</h3><p>Understand the source and integrity of the record in simple language.</p><button onClick={() => document.getElementById('verify')?.scrollIntoView({ behavior: 'smooth' })}>Verify Your Honey →</button></article></div></section><section className="trace-section" id="traceability"><div className="section-intro"><span className="eyebrow light-eyebrow">Recorded journey</span><h2>Every Batch Has a Journey.</h2><p>Honey Chain uses hash-linked records to make changes to recorded traceability history detectable.</p></div><div className="trace-flow">{['HARVEST', 'PROCESSING', 'PACKAGING', 'DISTRIBUTION', 'CONSUMER'].map((item, index) => <div key={item}><span>0{index + 1}</span><strong>{item}</strong></div>)}</div></section><section className="trust-section"><div><span className="eyebrow">Record integrity</span><h2>Recorded. Linked. Verifiable.</h2><p>Each traceability event links to the previous record, making unexpected changes detectable. This verifies record integrity, not chemical purity.</p></div><div className="hash-chain"><span>Batch record</span><b>↓</b><span>Previous hash</span><b>↓</b><span>Current hash</span><b>↓</b><span>Next record</span></div></section><section className="impact-section"><div className="section-intro"><span className="eyebrow">Why it matters</span><h2>Technology that respects the work.</h2></div><div className="impact-list"><span>🐝 Better visibility for beekeepers</span><span>🍯 Traceable honey batches</span><span>📱 Simple consumer verification</span><span>🔗 Tamper-evident records</span><span>🌱 Digital support for rural ecosystems</span></div></section><section className="register-section" id="registration"><div><span className="eyebrow">Future-ready onboarding</span><h2>Bring Your Farm Into Honey Chain</h2><p>Registration storage is not connected yet. This prototype captures the workflow without pretending to create a persistent record.</p></div>{registrationOpen ? <div className="prototype-note">Farm registration prototype only. No data was submitted or stored.<button className="button secondary-button" onClick={() => setRegistrationOpen(false)}>Close</button></div> : <button className="button primary-button" onClick={() => setRegistrationOpen(true)}>Register Farm</button>}</section>{scannerOpen && <QrScannerPanel onClose={() => setScannerOpen(false)} onDetected={(id) => navigate(`/verify/${id}`)} />}</div>
}

export default function App() {
  const [path, setPath] = useState(window.location.pathname)
  const [menuOpen, setMenuOpen] = useState(false)
  useEffect(() => { const update = () => setPath(window.location.pathname); window.addEventListener('popstate', update); return () => window.removeEventListener('popstate', update) }, [])
  const verifyMatch = path.match(/^\/verify\/(.+)$/)
  const page = verifyMatch ? <ConsumerView initialBatchId={decodeURIComponent(verifyMatch[1])} /> : path === '/verify' ? <ConsumerView /> : path === '/register' ? <AuthPage mode="register" /> : path === '/login' ? <AuthPage mode="login" /> : path === '/admin' ? <AdminPage /> : path === '/farmer' ? <FarmerGate /> : <><LandingView /><LiveHivePreview /></>
  const closeMenu = () => setMenuOpen(false)
  return <main className="app-shell"><header className="site-nav"><button className="brand-lockup" onClick={() => { navigate('/'); closeMenu() }}><span className="brand-mark">HC</span><span><strong>Honey Chain</strong><small>SIH26021 field intelligence</small></span></button><button className="menu-toggle" onClick={() => setMenuOpen((open) => !open)} aria-label="Toggle navigation">☰</button><nav className={menuOpen ? 'open' : ''}><a href="/#top" onClick={closeMenu}>Home</a><a href="/#how-it-works" onClick={closeMenu}>How It Works</a><a href="/#beekeepers" onClick={closeMenu}>For Beekeepers</a><a href="/#traceability" onClick={closeMenu}>Traceability</a><a href="/#verify" onClick={closeMenu}>Verify Honey</a></nav><div className="nav-actions"><button className="nav-verify" onClick={() => { navigate('/verify'); closeMenu() }}>Verify Bottle</button><button className="nav-farmer" onClick={() => { navigate('/farmer'); closeMenu() }}>Farmer Dashboard</button></div></header>{page}<footer className="site-footer"><button onClick={() => navigate('/')}>Honey Chain</button><span>SIH26021</span><div><a href="/#top">Home</a><a href="/#how-it-works">How It Works</a><a href="/#verify">Verify Honey</a><a href="/farmer">Farmer Dashboard</a></div></footer></main>
}