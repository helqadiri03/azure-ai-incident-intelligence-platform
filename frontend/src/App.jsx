import { useState, useEffect, useRef } from 'react'
import './App.css'

// ─── Helpers ────────────────────────────────────────────────────────────────
const SEVERITY_CLASS = {
  Critical: 'badge-critical',
  High:     'badge-high',
  Medium:   'badge-medium',
  Low:      'badge-low',
}

const QUICK_PROMPTS = [
  'Why are my AKS pods restarting?',
  'What caused the most recent Critical incident?',
  'Show me all AKS memory-related failures',
  'What is the average resolution time?',
]

// ─── Confidence Ring (SVG) ───────────────────────────────────────────────────
function ConfidenceRing({ value }) {
  const R = 22
  const CIRC = 2 * Math.PI * R
  const offset = CIRC - value * CIRC
  const pct = Math.round(value * 100)

  return (
    <div className="confidence-ring-wrap" title="Confidence is based on Azure Semantic Ranker scores">
      <div className="confidence-label">
        <div className="confidence-pct">{pct}%</div>
        <div style={{ fontSize: '9px', opacity: 0.7 }}>Retrieval</div>
      </div>
      <svg width="56" height="56" className="ring-svg">
        <defs>
          <linearGradient id="ringGrad" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%"   stopColor="#3b8bff" />
            <stop offset="100%" stopColor="#8b5cf6" />
          </linearGradient>
        </defs>
        <circle className="ring-track" cx="28" cy="28" r={R} strokeWidth="4" />
        <circle
          className="ring-fill"
          cx="28" cy="28" r={R}
          strokeWidth="4"
          strokeDasharray={CIRC}
          strokeDashoffset={offset}
        />
      </svg>
    </div>
  )
}

// ─── Typewriter hook ─────────────────────────────────────────────────────────
function useTypewriter(text, speed = 10, isActive = true) {
  const [displayed, setDisplayed] = useState('')
  const [done, setDone] = useState(!isActive)

  useEffect(() => {
    if (!isActive) {
      setDisplayed(text)
      setDone(true)
      return
    }
    if (!text) { setDisplayed(''); setDone(false); return }
    setDisplayed('')
    setDone(false)
    let i = 0
    const id = setInterval(() => {
      i += 3 // faster typing
      if (i >= text.length) i = text.length
      setDisplayed(text.slice(0, i))
      if (i >= text.length) { clearInterval(id); setDone(true) }
    }, speed)
    return () => clearInterval(id)
  }, [text, isActive])

  return { displayed, done }
}

// ─── App ─────────────────────────────────────────────────────────────────────
export default function App() {
  const [question, setQuestion] = useState('')
  const [loading, setLoading]   = useState(false)
  const [error, setError]       = useState(null)
  
  // State for session memory
  const [sessionId, setSessionId] = useState(null)
  const [history, setHistory]     = useState([]) // Array of { q, result, isTyping }
  
  const [apiStatus, setApiStatus] = useState(null)
  const [serverMetrics, setServerMetrics] = useState(null)
  const [showMetrics, setShowMetrics] = useState(false)
  
  const inputRef = useRef(null)
  const bottomRef = useRef(null)

  // Health check & global metrics on mount
  useEffect(() => {
    fetch('/health').then(r => r.json()).then(setApiStatus).catch(() => {})
    fetch('/metrics?raw=true').then(r => r.json()).then(setServerMetrics).catch(() => {})
  }, [])

  // Auto-scroll
  useEffect(() => {
    if (bottomRef.current) bottomRef.current.scrollIntoView({ behavior: 'smooth' })
  }, [history, loading])

  async function handleAsk(qStr) {
    const query = (qStr ?? question).trim()
    if (!query || loading) return
    
    setQuestion('') // clear input immediately
    setLoading(true)
    setError(null)

    try {
      const res = await fetch('/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: query, session_id: sessionId }),
      })
      if (!res.ok) {
        let errMsg = `Server error: ${res.status}`
        try {
          const errData = await res.json()
          if (errData.detail) errMsg = errData.detail
        } catch (_) {}
        throw new Error(errMsg)
      }
      
      const data = await res.json()
      setSessionId(data.session_id)
      setHistory(prev => [...prev, { q: query, result: data, isTyping: true }])
      
      // Update global metrics after a request
      fetch('/metrics?raw=true').then(r => r.json()).then(setServerMetrics).catch(() => {})
      
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  function handleKey(e) {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleAsk() }
  }

  async function handleFeedback(itemIndex, rating) {
    const item = history[itemIndex]
    if (!item || item.feedbackGiven) return
    
    // Optimistic UI update
    setHistory(prev => prev.map((h, i) => i === itemIndex ? { ...h, feedbackGiven: rating } : h))
    
    try {
      await fetch('/feedback', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          session_id: sessionId,
          question: item.q,
          rating: rating
        })
      })
    } catch (e) { console.error('Feedback error', e) }
  }

  return (
    <div className="app-bg">
      {/* ── Header ── */}
      <header className="header">
        <div className="header-logo">
          <div className="logo-icon">⚡</div>
          <div className="logo-text">Azure <span>Incident Intelligence</span></div>
        </div>
        <div className="header-right">
          <button className="metrics-toggle" onClick={() => setShowMetrics(!showMetrics)}>
            📊 Metrics
          </button>
          <div className="header-status">
            <div className={`status-dot ${apiStatus ? '' : 'offline'}`} />
            {apiStatus ? apiStatus.llm_model : 'Connecting…'}
          </div>
        </div>
      </header>
      
      {/* ── Metrics Panel (Absolute) ── */}
      {showMetrics && serverMetrics && (
        <div className="metrics-panel">
          <div className="metric-box">
            <span>Avg Search</span>
            <strong>{Math.round(serverMetrics.avg_search_latency_ms)} ms</strong>
          </div>
          <div className="metric-box">
            <span>Avg LLM</span>
            <strong>{Math.round(serverMetrics.avg_llm_latency_ms)} ms</strong>
          </div>
          <div className="metric-box">
            <span>Total Tokens</span>
            <strong>{serverMetrics.total_tokens_approx.toLocaleString()}</strong>
          </div>
        </div>
      )}

      {/* ── Main Chat Area ── */}
      <main className="main">
        {history.length === 0 && !loading && (
          <section className="hero">
            <div className="hero-badge">⚡ Production RAG · Memory Enabled</div>
            <h1>Ask Anything About<br />Your Azure Incidents</h1>
            <div className="quick-prompts">
              {QUICK_PROMPTS.map(p => (
                <button key={p} className="quick-prompt" onClick={() => handleAsk(p)}>{p}</button>
              ))}
            </div>
          </section>
        )}

        {error && (
          <div style={{ color: '#ef4444', padding: '1rem', textAlign: 'center', fontSize: '0.9rem', width: '100%' }}>
            ⚠ {error}
          </div>
        )}

        <div className="chat-history">
          {history.map((turn, i) => (
            <ChatTurn 
              key={i} 
              turn={turn} 
              index={i} 
              onTypingDone={() => {
                setHistory(prev => prev.map((h, idx) => idx === i ? { ...h, isTyping: false } : h))
              }}
              onFeedback={handleFeedback}
            />
          ))}
          {loading && <LoadingTurn />}
          <div ref={bottomRef} />
        </div>
      </main>
      
      {/* ── Input Area ── */}
      <div className="input-area">
        <div className="search-wrapper">
          <div className="search-box">
            <span className="search-icon">🔍</span>
            <input
              ref={inputRef}
              className="search-input"
              placeholder="Ask a follow-up question…"
              value={question}
              onChange={e => setQuestion(e.target.value)}
              onKeyDown={handleKey}
              disabled={loading}
              autoFocus
            />
            <button className="search-btn" onClick={() => handleAsk()} disabled={loading || !question.trim()}>
              Ask →
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}


// ─── Chat Turn Components ───────────────────────────────────────────────────

function ChatTurn({ turn, index, onTypingDone, onFeedback }) {
  const { q, result, isTyping, feedbackGiven } = turn
  
  // We now have 4 fields in result.analysis instead of result.answer
  const analysis = result.analysis || {}
  
  // 3-stage typewriter — one per agent output (staggered)
  const rootTyping = useTypewriter(analysis.root_cause_analysis || '', 5, isTyping)
  const recTyping  = useTypewriter(
    analysis.immediate_actions?.join('\n') || '',
    6,
    isTyping && rootTyping.done
  )
  const finalTyping = useTypewriter(analysis.executive_summary || '', 7, isTyping && recTyping.done)
  // riskTyping kept for compatibility (mirrors recTyping done state)
  const riskTyping = recTyping

  const allDone = finalTyping.done

  useEffect(() => {
    if (allDone && isTyping) onTypingDone()
  }, [allDone, isTyping, onTypingDone])

  return (
    <div className="chat-turn">
      <div className="user-bubble">{q}</div>
      
      <div className="results">
        <div className="answer-card">
          <div className="answer-card-header">
            <div className="answer-label">
              <div className="ai-dot">🤖</div> AI Analysis
              <span className={`mode-badge ${result.retriever_mode}`}>
                {result.retriever_mode === 'live' ? '⚡ Hybrid Search' : '🔄 Mock'}
              </span>
            </div>
            <div className="answer-header-right">
              <span className="latency-pill">Search: {result.metrics.search_ms}ms | LLM: {result.metrics.llm_ms}ms</span>
              <ConfidenceRing value={result.confidence} />
            </div>
          </div>
          
          <div className="analysis-grid">

            {/* ── RCA Agent ── */}
            <div className="analysis-section">
              <h4><span className="analysis-icon">🔍</span> Root Cause Analysis
                <span className="confidence-inline">{Math.round((analysis.confidence || 0) * 100)}% confident</span>
              </h4>
              <p>{rootTyping.displayed}{!rootTyping.done && <span className="cursor-blink"/>}</p>
              {rootTyping.done && analysis.evidence?.length > 0 && (
                <div className="evidence-chips">
                  {analysis.evidence.map((e, i) => <span key={i} className="evidence-chip">📌 {e}</span>)}
                </div>
              )}
            </div>

            {/* ── Recommendation Agent ── */}
            {rootTyping.done && (
              <div className="analysis-section recommendation">
                <h4><span className="analysis-icon">💡</span> Immediate Actions</h4>
                {analysis.immediate_actions?.length > 0 ? (
                  <ol className="action-list">
                    {analysis.immediate_actions.map((a, i) => (
                      <li key={i}>{i < analysis.immediate_actions.length - 1 || recTyping.done ? a : recTyping.displayed}</li>
                    ))}
                  </ol>
                ) : <p>{recTyping.displayed}{!recTyping.done && <span className="cursor-blink"/>}</p>}

                {recTyping.done && analysis.long_term_fixes?.length > 0 && (
                  <>
                    <h4 style={{marginTop:'0.75rem'}}><span className="analysis-icon">🔧</span> Long-term Fixes</h4>
                    <ul className="fix-list">
                      {analysis.long_term_fixes.map((f, i) => <li key={i}>{f}</li>)}
                    </ul>
                  </>
                )}
                {recTyping.done && analysis.preventive_recommendations?.length > 0 && (
                  <>
                    <h4 style={{marginTop:'0.75rem'}}><span className="analysis-icon">🛡️</span> Preventive Measures</h4>
                    <ul className="fix-list preventive">
                      {analysis.preventive_recommendations.map((p, i) => <li key={i}>{p}</li>)}
                    </ul>
                  </>
                )}
              </div>
            )}

            {/* ── Summary Agent ── */}
            {recTyping.done && (
              <div className="analysis-section summary">
                <h4>
                  <span className="analysis-icon">📋</span> Executive Summary
                  {analysis.severity && (
                    <span className={`severity-badge sev-${analysis.severity?.toLowerCase()}`}>{analysis.severity}</span>
                  )}
                </h4>
                <p>{finalTyping.displayed}{!finalTyping.done && <span className="cursor-blink"/>}</p>
                {finalTyping.done && (
                  <div className="summary-meta">
                    {analysis.business_impact && <div className="meta-row"><span>💼 Impact</span><span>{analysis.business_impact}</span></div>}
                    {analysis.timeline && <div className="meta-row"><span>⏱️ Timeline</span><span>{analysis.timeline}</span></div>}
                  </div>
                )}
              </div>
            )}

          </div>
          
          {allDone && (
            <div className="feedback-bar">
              <span className="feedback-text">Was this helpful?</span>
              <button 
                className={`feedback-btn ${feedbackGiven === 'helpful' ? 'active' : ''}`}
                onClick={() => onFeedback(index, 'helpful')}
                disabled={feedbackGiven}
              >👍</button>
              <button 
                className={`feedback-btn ${feedbackGiven === 'not_helpful' ? 'active' : ''}`}
                onClick={() => onFeedback(index, 'not_helpful')}
                disabled={feedbackGiven}
              >👎</button>
            </div>
          )}
        </div>

        {allDone && (
          <div className="two-col fade-in">
            <div className="section-card">
              <div className="section-header">
                🔗 Related Incidents <span className="section-count">{result.related_incidents.length}</span>
              </div>
              <div className="incidents-list">
                {result.related_incidents.map(id => (
                  <div className="incident-chip" key={id}>
                    <span className="incident-chip-id">#{id}</span>
                    <span className="incident-chip-icon">→</span>
                  </div>
                ))}
              </div>
            </div>

            <div className="section-card">
              <div className="section-header">
                📄 Cited Sources <span className="section-count">{result.sources.length} chunks</span>
              </div>
              <div className="sources-list">
                {result.sources.map(s => (
                  <div className="source-chunk" key={s.id} data-severity={s.severity}>
                    <div className="source-chunk-header">
                      <span className="badge badge-service">{s.service}</span>
                      <span className={`badge ${SEVERITY_CLASS[s.severity] ?? 'badge-medium'}`}>{s.severity}</span>
                      <span className="badge badge-chunk">{s.chunk_type}</span>
                    </div>
                    <div className="source-meta">
                      Incident #{s.incident_id} • {s.date || 'No Date'} • {s.region || 'Global'}
                    </div>
                    <div className="source-content">{s.content}</div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}


function LoadingTurn() {
  const steps = [
    { label: 'Embedding & Hybrid Search…', delay: 0 },
    { label: 'Semantic Reranking…', delay: 600 },
    { label: 'Generating Answer…', delay: 1200 },
  ]
  const [active, setActive] = useState(0)

  useEffect(() => {
    const timers = steps.map((s, i) => setTimeout(() => setActive(i), s.delay))
    return () => timers.forEach(clearTimeout)
  }, [])

  return (
    <div className="chat-turn">
      <div className="results">
        <div className="loading-state">
          <div className="spinner" />
          <div className="loading-steps">
            {steps.map((s, i) => (
              <div key={i} className={`loading-step ${i < active ? 'done' : i === active ? 'active' : ''}`}>
                {i < active ? '✓' : i === active ? '›' : '·'} {s.label}
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}
