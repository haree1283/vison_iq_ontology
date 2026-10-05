import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { Camera, Film, Play, Square, VideoOff } from 'lucide-react'
import JobStats from './JobStats'
import { getLiveStatus, listScenes, liveSocketUrl, startLive, stopLive } from '../../services/nh5Api'
import './nh5.css'

const EMPTY_FIELDS = { sceneId: '', latitude: '', longitude: '', metersPerPixel: '', speedLimit: '', thorough: false }

// Camera frames come from THIS browser (getUserMedia), are sent as JPEGs over the /live_ws websocket, and the
// server answers each frame with its detection boxes, drawn on a canvas over the local preview -- same flow as
// the NH5 website's live page. The session is recorded and lands in the Video Library when it stops.
export default function LiveCameraPage() {
  const videoRef = useRef(null)
  const overlayRef = useRef(null)
  const captureRef = useRef(null)
  const streamRef = useRef(null)
  const wsRef = useRef(null)
  const [fields, setFields] = useState(EMPTY_FIELDS)
  const [scenes, setScenes] = useState([])
  const [running, setRunning] = useState(false)
  const [starting, setStarting] = useState(false)
  const [error, setError] = useState('')
  const [status, setStatus] = useState(null)
  const [jobId, setJobId] = useState(null)

  useEffect(() => { listScenes().then(setScenes).catch(() => setScenes([])) }, [])

  // server-side truth for the sidebar, independent of which browser drives the camera
  useEffect(() => {
    let active = true
    let timer
    async function poll() {
      try {
        const s = await getLiveStatus()
        if (!active) return
        setStatus(s)
        if (s.job_id) setJobId(s.job_id)
        if (s.error) setError(s.error)
      } catch { /* keep polling */ }
      timer = setTimeout(poll, 1500)
    }
    poll()
    return () => { active = false; clearTimeout(timer) }
  }, [])

  useEffect(() => () => { stopTracks(); try { wsRef.current?.close() } catch { /* ignore */ } }, [])

  const set = (key) => (e) => setFields((f) => ({ ...f, [key]: e.target.type === 'checkbox' ? e.target.checked : e.target.value }))

  function drawBoxes(boxes) {
    const canvas = overlayRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    ctx.clearRect(0, 0, canvas.width, canvas.height)
    for (const b of boxes) {
      const [x0, y0, x1, y1] = b.box
      const [r, g, bl] = b.color || [79, 124, 255]
      ctx.strokeStyle = `rgb(${r},${g},${bl})`
      ctx.lineWidth = 2
      ctx.strokeRect(x0, y0, x1 - x0, y1 - y0)
      ctx.font = '13px sans-serif'
      const w = ctx.measureText(b.label).width + 8
      ctx.fillStyle = `rgb(${r},${g},${bl})`
      ctx.fillRect(x0, Math.max(0, y0 - 18), w, 18)
      ctx.fillStyle = '#0a0c10'
      ctx.fillText(b.label, x0 + 4, Math.max(12, y0 - 5))
    }
  }

  function sendFrame() {
    const ws = wsRef.current
    const video = videoRef.current
    const capture = captureRef.current
    if (!ws || ws.readyState !== WebSocket.OPEN || !video || video.paused || video.ended) return
    capture.getContext('2d').drawImage(video, 0, 0, capture.width, capture.height)
    capture.toBlob((blob) => {
      if (blob && wsRef.current && wsRef.current.readyState === WebSocket.OPEN) wsRef.current.send(blob)
    }, 'image/jpeg', 0.7)
  }

  function stopTracks() {
    streamRef.current?.getTracks().forEach((t) => t.stop())
    streamRef.current = null
    setRunning(false)
  }

  async function start() {
    setError('')
    setStarting(true)
    try {
      let stream
      try {
        stream = await navigator.mediaDevices.getUserMedia({ video: { width: { ideal: 1280 }, height: { ideal: 720 } }, audio: false })
      } catch (e) {
        throw new Error(`Could not access the camera: ${e.message} (allow camera permission; the page must be opened via https:// or localhost).`)
      }
      streamRef.current = stream
      const video = videoRef.current
      video.srcObject = stream
      await video.play()
      const w = video.videoWidth
      const h = video.videoHeight
      captureRef.current.width = w
      captureRef.current.height = h
      overlayRef.current.width = w
      overlayRef.current.height = h

      const started = await startLive({ ...fields, thorough: fields.thorough ? 'on' : '' })
      setJobId(started.jobId)
      setRunning(true)

      const ws = new WebSocket(liveSocketUrl())
      ws.binaryType = 'blob'
      ws.onopen = () => { ws.send(JSON.stringify({ width: w, height: h, fps: 6 })); sendFrame() }
      ws.onmessage = (ev) => { drawBoxes(JSON.parse(ev.data)); sendFrame() }  // paced: next frame after each answer
      ws.onclose = () => stopTracks()
      ws.onerror = () => setError('Live connection dropped.')
      wsRef.current = ws
    } catch (err) {
      setError(err.message)
      stopTracks()
    } finally {
      setStarting(false)
    }
  }

  async function stop() {
    const ws = wsRef.current
    wsRef.current = null
    if (ws) {
      // a deliberate stop: don't report the socket's closing as a dropped connection
      ws.onerror = null
      ws.onclose = null
      ws.onmessage = null
      try { ws.close() } catch { /* ignore */ }
    }
    try { await stopLive() } catch (err) { setError(err.message) }
    stopTracks()
    const canvas = overlayRef.current
    canvas?.getContext('2d').clearRect(0, 0, canvas.width, canvas.height)
  }

  const sessionElsewhere = status?.running && !running

  return (
    <div className="nh5-page">
      <div className="page-intro">
        <p className="section-kicker">NH5 DETECTION PIPELINE</p>
        <h1>Live Camera</h1>
        <p className="intro-copy">Run the detector on this device's camera in real time. The session is recorded with the same
          tracking, plate reading, events and Excel report as an uploaded video, and saved to the Video Library when you stop.</p>
      </div>

      <div className="nh5-monitor">
        <div className="viq-card nh5-viewer-card">
          <div className="nh5-viewer nh5-live-viewer">
            <video muted playsInline ref={videoRef} style={{ display: running ? 'block' : 'none' }} />
            <canvas className="nh5-overlay" ref={overlayRef} style={{ display: running ? 'block' : 'none' }} />
            <canvas ref={captureRef} style={{ display: 'none' }} />
            {!running && (
              <div className="nh5-viewer-empty">
                <VideoOff size={30} />
                {sessionElsewhere ? 'A live session is running from another browser.' : 'Camera is not running.'}
              </div>
            )}
            {running && <span className="nh5-status-badge st-live"><span className="nh5-rec" />LIVE</span>}
          </div>
          <div className="nh5-live-controls">
            {!running ? (
              <>
                <div className="nh5-field-row four">
                  <label className="nh5-field">Road map
                    <select onChange={set('sceneId')} value={fields.sceneId}>
                      <option value="">None</option>
                      {scenes.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
                    </select>
                  </label>
                  <label className="nh5-field">Latitude<input onChange={set('latitude')} value={fields.latitude} /></label>
                  <label className="nh5-field">Longitude<input onChange={set('longitude')} value={fields.longitude} /></label>
                  <label className="nh5-field">Speed limit<input onChange={set('speedLimit')} placeholder="km/h" value={fields.speedLimit} /></label>
                </div>
                <div className="nh5-live-buttons">
                  <label className="nh5-toggle"><input checked={fields.thorough} onChange={set('thorough')} type="checkbox" /><span>Thorough mode</span></label>
                  <button className="primary-action nh5-submit" disabled={starting} onClick={start} type="button"><Play size={16} />{starting ? 'Starting…' : 'Start camera'}</button>
                </div>
              </>
            ) : (
              <div className="nh5-live-buttons">
                <span className="nh5-muted"><Camera size={14} /> Streaming frames to the detector…</span>
                <button className="nh5-btn danger" onClick={stop} type="button"><Square size={15} />Stop and save</button>
              </div>
            )}
            {error && <p className="login-error">{error}</p>}
            {jobId && !running && status?.status !== 'idle' && (
              <Link className="nh5-link" to={`/video-library/${jobId}`}><Film size={14} /> Open the last session in the Video Library →</Link>
            )}
          </div>
        </div>
        <div className="viq-card nh5-side-card">
          <div className="nh5-subhead">Session status: <b>{status?.status || '–'}</b>{status?.scene_name ? ` · ${status.scene_name}` : ''}</div>
          <JobStats showSpeed={false} status={status} />
        </div>
      </div>
    </div>
  )
}
