import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { ArrowLeft, Save, Trash2 } from 'lucide-react'
import { deleteScene, getScene, mediaUrl, saveScene } from '../../services/nh5Api'
import './nh5.css'

// Port of the NH5 road-map editor: draw road / roadside / zebra-crossing zones and lanes (with a travel-direction
// arrow) over a frame of a fixed camera. Points are normalized 0..1 of the frame, as event_engine.Scene expects.
const TYPES = {
  road: { label: 'Road area', fill: 'rgba(170,170,170,0.28)', stroke: '#c4c4c4' },
  roadside: { label: 'Roadside / footpath', fill: 'rgba(80,200,110,0.26)', stroke: '#50c86e' },
  crossing: { label: 'Zebra crossing', fill: 'rgba(255,255,255,0.32)', stroke: '#ffffff' },
  lane: { label: 'Lane', fill: 'rgba(0,200,255,0.14)', stroke: '#00c8ff' },
}
const CLOSE_RADIUS_PX = 12

export default function RoadMapEditor() {
  const { sceneId } = useParams()
  const navigate = useNavigate()
  const canvasRef = useRef(null)
  const imgRef = useRef(null)
  const st = useRef({ zones: [], lanes: [], tool: 'road', draft: [], directionLane: null, directionDraft: [], highlight: null, mouse: null })
  const [scene, setScene] = useState(null)
  const [name, setName] = useState('')
  const [tool, setToolState] = useState('road')
  const [, setTick] = useState(0)  // re-render list / hint after state-ref edits
  const [dirty, setDirty] = useState(false)
  const [saveStatus, setSaveStatus] = useState('')
  const [error, setError] = useState('')
  const refresh = () => setTick((n) => n + 1)

  // ---- geometry
  const size = () => ({ w: canvasRef.current?.clientWidth || 1, h: canvasRef.current?.clientHeight || 1 })
  const toPx = (p) => [p[0] * size().w, p[1] * size().h]
  const distPx = (a, b) => { const [ax, ay] = toPx(a); const [bx, by] = toPx(b); return Math.hypot(ax - bx, ay - by) }
  function toNorm(evt) {
    const r = canvasRef.current.getBoundingClientRect()
    const x = Math.min(1, Math.max(0, (evt.clientX - r.left) / r.width))
    const y = Math.min(1, Math.max(0, (evt.clientY - r.top) / r.height))
    return [Math.round(x * 1e5) / 1e5, Math.round(y * 1e5) / 1e5]
  }

  // ---- drawing
  const draw = useCallback(() => {
    const canvas = canvasRef.current
    const img = imgRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    const { w, h } = size()
    const s = st.current
    ctx.clearRect(0, 0, w, h)
    if (img?.complete) ctx.drawImage(img, 0, 0, w, h)

    const polygon = (points, style, emphasized) => {
      if (points.length < 2) return
      ctx.beginPath()
      points.forEach((p, i) => { const [x, y] = toPx(p); if (i) ctx.lineTo(x, y); else ctx.moveTo(x, y) })
      ctx.closePath()
      ctx.fillStyle = style.fill
      ctx.fill()
      ctx.lineWidth = emphasized ? 4 : 2
      ctx.strokeStyle = style.stroke
      ctx.stroke()
    }
    const arrow = (from, to, color) => {
      const [x0, y0] = toPx(from); const [x1, y1] = toPx(to)
      const angle = Math.atan2(y1 - y0, x1 - x0)
      ctx.strokeStyle = color; ctx.fillStyle = color; ctx.lineWidth = 4
      ctx.beginPath(); ctx.moveTo(x0, y0); ctx.lineTo(x1, y1); ctx.stroke()
      ctx.beginPath(); ctx.moveTo(x1, y1)
      ctx.lineTo(x1 - 16 * Math.cos(angle - 0.45), y1 - 16 * Math.sin(angle - 0.45))
      ctx.lineTo(x1 - 16 * Math.cos(angle + 0.45), y1 - 16 * Math.sin(angle + 0.45))
      ctx.closePath(); ctx.fill()
    }
    const label = (text, points, color) => {
      const cx = points.reduce((a, p) => a + p[0], 0) / points.length
      const cy = points.reduce((a, p) => a + p[1], 0) / points.length
      const [x, y] = toPx([cx, cy])
      ctx.font = '600 13px sans-serif'
      const tw = ctx.measureText(text).width
      ctx.fillStyle = 'rgba(0,0,0,0.65)'; ctx.fillRect(x - tw / 2 - 6, y - 11, tw + 12, 20)
      ctx.fillStyle = color; ctx.fillText(text, x - tw / 2, y + 4)
    }

    s.zones.forEach((z, i) => polygon(z.points, TYPES[z.type], s.highlight?.kind === 'zone' && s.highlight.index === i))
    s.lanes.forEach((l, i) => {
      polygon(l.points, TYPES.lane, s.highlight?.kind === 'lane' && s.highlight.index === i)
      if (l.direction) arrow(l.direction[0], l.direction[1], '#ffd400')
      label(l.name, l.points, '#00c8ff')
    })
    if (s.draft.length) {
      const style = TYPES[s.tool]
      ctx.strokeStyle = style.stroke; ctx.lineWidth = 2; ctx.setLineDash([6, 4])
      ctx.beginPath()
      s.draft.forEach((p, i) => { const [x, y] = toPx(p); if (i) ctx.lineTo(x, y); else ctx.moveTo(x, y) })
      if (s.mouse) { const [mx, my] = toPx(s.mouse); ctx.lineTo(mx, my) }
      ctx.stroke(); ctx.setLineDash([])
      s.draft.forEach((p, i) => {
        const [x, y] = toPx(p)
        const closable = i === 0 && s.draft.length >= 3 && s.mouse && distPx(p, s.mouse) < CLOSE_RADIUS_PX
        ctx.beginPath(); ctx.arc(x, y, closable ? 8 : 4, 0, Math.PI * 2)
        ctx.fillStyle = closable ? '#ffd400' : style.stroke; ctx.fill()
      })
    }
    if (s.directionLane !== null && s.directionDraft.length === 1 && s.mouse) arrow(s.directionDraft[0], s.mouse, '#ffd400')
  }, [])

  const resize = useCallback(() => {
    const canvas = canvasRef.current
    const img = imgRef.current
    if (!canvas || !img?.naturalWidth) return
    const w = canvas.parentElement.clientWidth
    const h = Math.round((w * img.naturalHeight) / img.naturalWidth)
    const dpr = window.devicePixelRatio || 1
    canvas.style.width = `${w}px`; canvas.style.height = `${h}px`
    canvas.width = Math.round(w * dpr); canvas.height = Math.round(h * dpr)
    canvas.getContext('2d').setTransform(dpr, 0, 0, dpr, 0, 0)
    draw()
  }, [draw])

  // ---- load
  useEffect(() => {
    getScene(sceneId).then((data) => {
      setScene(data)
      setName(data.name)
      st.current.zones = (data.zones || []).map((z) => ({ type: z.type, points: z.points }))
      st.current.lanes = (data.lanes || []).map((l) => ({ name: l.name, points: l.points, direction: l.direction || null }))
      const img = new Image()
      img.onload = () => { imgRef.current = img; resize(); refresh() }
      img.src = mediaUrl(data.frameUrl)
    }).catch((err) => setError(err.message))
  }, [sceneId, resize])

  useEffect(() => {
    window.addEventListener('resize', resize)
    return () => window.removeEventListener('resize', resize)
  }, [resize])

  // ---- editing
  const markDirty = () => { setDirty(true); setSaveStatus('Unsaved changes') }
  function nextLaneName() {
    const names = new Set(st.current.lanes.map((l) => l.name))
    let n = st.current.lanes.length + 1
    while (names.has(`Lane ${n}`)) n += 1
    return `Lane ${n}`
  }
  function finishDraft() {
    const s = st.current
    if (s.draft.length < 3) return
    if (s.tool === 'lane') {
      s.lanes.push({ name: nextLaneName(), points: s.draft, direction: null })
      s.directionLane = s.lanes.length - 1
      s.directionDraft = []
    } else {
      s.zones.push({ type: s.tool, points: s.draft })
    }
    s.draft = []
    markDirty(); refresh(); draw()
  }
  function cancel() {
    Object.assign(st.current, { draft: [], directionLane: null, directionDraft: [] })
    refresh(); draw()
  }
  function setTool(next) {
    const s = st.current
    if (s.draft.length && next !== s.tool) s.draft = []
    Object.assign(s, { directionLane: null, directionDraft: [], tool: next })
    setToolState(next); draw()
  }

  function handleClick(evt) {
    const s = st.current
    const p = toNorm(evt)
    if (s.directionLane !== null) {
      s.directionDraft.push(p)
      if (s.directionDraft.length === 2) {
        if (distPx(s.directionDraft[0], s.directionDraft[1]) < 10) {
          s.directionDraft = []
        } else {
          s.lanes[s.directionLane].direction = s.directionDraft
          s.directionLane = null
          s.directionDraft = []
          markDirty()
        }
      }
    } else if (s.draft.length >= 3 && distPx(s.draft[0], p) < CLOSE_RADIUS_PX) {
      finishDraft()
      return
    } else {
      s.draft.push(p)
    }
    refresh(); draw()
  }

  useEffect(() => {
    function onKey(evt) {
      if (['INPUT', 'SELECT', 'TEXTAREA'].includes(evt.target.tagName)) return
      const s = st.current
      if (evt.key === 'Enter') { evt.preventDefault(); finishDraft() }
      else if (evt.key === 'Escape') cancel()
      else if (evt.key === 'Backspace' && s.draft.length) { evt.preventDefault(); s.draft.pop(); refresh(); draw() }
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  })

  useEffect(() => {
    const warn = (evt) => { if (dirty) { evt.preventDefault(); evt.returnValue = '' } }
    window.addEventListener('beforeunload', warn)
    return () => window.removeEventListener('beforeunload', warn)
  }, [dirty])

  async function handleSave() {
    setSaveStatus('Saving…')
    try {
      const saved = await saveScene(sceneId, { name, zones: st.current.zones, lanes: st.current.lanes })
      setScene(saved)
      setDirty(false)
      setSaveStatus(`Saved at ${new Date().toLocaleTimeString()}`)
    } catch (err) {
      setSaveStatus(`Not saved: ${err.message}`)
    }
  }

  async function handleDelete() {
    if (!window.confirm('Delete this road map? Videos already processed with it keep their results.')) return
    try {
      await deleteScene(sceneId)
      navigate('/road-maps', { replace: true })
    } catch (err) {
      setError(err.message)
    }
  }

  const s = st.current
  let hint
  if (s.directionLane !== null) {
    const lane = s.lanes[s.directionLane]
    hint = s.directionDraft.length === 0
      ? <><b>{lane.name}:</b> click where traffic in this lane comes <b>from</b>. <kbd>Esc</kbd> skips (wrong-side detection stays off for this lane).</>
      : <><b>{lane.name}:</b> now click where the traffic <b>goes to</b>.</>
  } else {
    const what = TYPES[tool].label.toLowerCase()
    hint = s.draft.length === 0
      ? <>Click to place the corners of the <b>{what}</b>. Click the first point again (or press <kbd>Enter</kbd>) to close it.</>
      : <>{s.draft.length} point{s.draft.length === 1 ? '' : 's'} — click the first point or press <kbd>Enter</kbd> to finish, <kbd>Backspace</kbd> undoes a point, <kbd>Esc</kbd> cancels.</>
  }
  const items = [
    ...s.zones.map((z, i) => ({ kind: 'zone', index: i, style: TYPES[z.type], text: TYPES[z.type].label })),
    ...s.lanes.map((l, i) => ({ kind: 'lane', index: i, style: TYPES.lane, lane: l })),
  ]

  if (error && !scene) return <div className="nh5-page"><Link className="nh5-back" to="/road-maps"><ArrowLeft size={15} />Road Maps</Link><p className="login-error">{error}</p></div>

  return (
    <div className="nh5-page">
      <Link className="nh5-back" to="/road-maps"><ArrowLeft size={15} />Road Maps</Link>
      <div className="page-intro"><p className="section-kicker">ROAD MAP EDITOR</p><h1>{name || 'Road map'}</h1></div>
      <div className="nh5-editor-grid">
        <div className="viq-card nh5-editor-card">
          <div className="nh5-tool-row">
            {Object.entries(TYPES).map(([key, t]) => (
              <button className={`nh5-tool ${tool === key ? 'active' : ''}`} key={key} onClick={() => setTool(key)} type="button">
                <span className="nh5-chip" style={{ background: t.stroke }} />{key === 'road' ? 'Road area' : key === 'roadside' ? 'Roadside' : key === 'crossing' ? 'Zebra crossing' : 'Lane'}
              </button>
            ))}
          </div>
          <div className="nh5-canvas-wrap">
            <canvas
              onClick={handleClick}
              onMouseLeave={() => { st.current.mouse = null; draw() }}
              onMouseMove={(e) => { st.current.mouse = toNorm(e); draw() }}
              ref={canvasRef}
            />
          </div>
          <div className="nh5-hint">{hint}</div>
        </div>
        <div className="viq-card nh5-form-card">
          <label className="nh5-field">Name<input onChange={(e) => { setName(e.target.value); markDirty() }} value={name} /></label>
          <h2>Shapes</h2>
          {!items.length ? <p className="nh5-muted">Nothing drawn yet.</p> : (
            <ul className="nh5-shape-list">
              {items.map((item) => (
                <li
                  key={`${item.kind}-${item.index}`}
                  onMouseEnter={() => { st.current.highlight = { kind: item.kind, index: item.index }; draw() }}
                  onMouseLeave={() => { st.current.highlight = null; draw() }}
                >
                  <span className="nh5-chip" style={{ background: item.style.stroke }} />
                  {item.kind === 'lane' ? (
                    <>
                      <input
                        defaultValue={item.lane.name}
                        onChange={(e) => { item.lane.name = e.target.value.trim() || item.lane.name; markDirty(); draw() }}
                      />
                      <button
                        className={item.lane.direction ? '' : 'warn'}
                        onClick={() => { Object.assign(st.current, { draft: [], directionLane: item.index, directionDraft: [] }); refresh(); draw() }}
                        type="button"
                      >{item.lane.direction ? 'redraw arrow' : 'set direction'}</button>
                    </>
                  ) : <span className="nh5-shape-text">{item.text}</span>}
                  <button
                    className="danger"
                    onClick={() => {
                      if (item.kind === 'zone') st.current.zones.splice(item.index, 1)
                      else st.current.lanes.splice(item.index, 1)
                      st.current.highlight = null
                      cancel(); markDirty()
                    }}
                    type="button"
                  >delete</button>
                </li>
              ))}
            </ul>
          )}
          <button className="primary-action nh5-submit" onClick={handleSave} type="button"><Save size={15} />Save road map</button>
          <p className="nh5-muted nh5-center">{saveStatus}</p>
          <button className="nh5-btn danger" onClick={handleDelete} type="button"><Trash2 size={15} />Delete road map</button>
          {error && <p className="login-error">{error}</p>}
        </div>
      </div>
    </div>
  )
}
