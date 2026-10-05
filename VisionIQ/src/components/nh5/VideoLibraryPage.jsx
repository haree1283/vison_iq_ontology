import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { AlertTriangle, Film, IdCard, Loader2, Radio, Search, UploadCloud } from 'lucide-react'
import { formatWhen, listVideos, mediaUrl } from '../../services/nh5Api'
import './nh5.css'

export default function VideoLibraryPage({ rows = [] }) {
  const [videos, setVideos] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [query, setQuery] = useState('')

  useEffect(() => {
    let active = true
    let timer
    async function load() {
      try {
        const items = await listVideos()
        if (!active) return
        setVideos(items)
        setError('')
        // keep refreshing while something is still processing / live
        if (items.some((v) => !['done', 'error'].includes(v.status))) timer = setTimeout(load, 3000)
      } catch (err) {
        if (active) setError(err.message)
      } finally {
        if (active) setLoading(false)
      }
    }
    load()
    return () => { active = false; clearTimeout(timer) }
  }, [rows.length])

  const shown = useMemo(() => {
    const q = query.trim().toLowerCase()
    if (!q) return videos
    return videos.filter((v) => [v.originalFilename, v.sceneName, ...(v.plates || [])].some((x) => String(x || '').toLowerCase().includes(q)))
  }, [videos, query])

  return (
    <div className="nh5-page">
      <div className="nh5-page-head">
        <div className="page-intro">
          <p className="section-kicker">NH5 DETECTION PIPELINE</p>
          <h1>Video Library</h1>
          <p className="intro-copy">Every processed video and live camera session, newest first — annotated video, number plates, events and the Excel report.</p>
        </div>
        <Link className="primary-action nh5-head-action" to="/video-upload"><UploadCloud size={16} />Upload video</Link>
      </div>

      <div className="nh5-toolbar">
        <div className="nh5-search"><Search size={15} /><input onChange={(e) => setQuery(e.target.value)} placeholder="Search file name, road map or plate…" value={query} /></div>
        <span className="nh5-muted">{shown.length} of {videos.length} item(s)</span>
      </div>

      {error && <p className="login-error">{error}</p>}
      {loading ? (
        <p className="nh5-muted">Loading…</p>
      ) : !videos.length ? (
        <div className="viq-card nh5-empty">
          <Film size={34} />
          <h2>The library is empty</h2>
          <p>Upload a video or start a live camera session — results appear here when processing finishes.</p>
          <div className="nh5-actions">
            <Link className="nh5-btn" to="/video-upload"><UploadCloud size={15} />Upload video</Link>
            <Link className="nh5-btn" to="/live-camera"><Radio size={15} />Live camera</Link>
          </div>
        </div>
      ) : (
        <div className="nh5-library-grid">
          {shown.map((v) => {
            const busy = !['done', 'error'].includes(v.status)
            const events = Object.values(v.eventCounts || {}).reduce((a, b) => a + b, 0)
            return (
              <Link className="viq-card nh5-video-card" key={v.jobId} to={`/video-library/${v.jobId}`}>
                <div className="nh5-thumb">
                  {v.thumbnail ? <img alt={v.originalFilename} src={mediaUrl(v.thumbnail)} /> : <Film size={30} />}
                  <span className={`nh5-status-badge st-${v.status}`}>
                    {busy && <Loader2 className="nh5-spin" size={12} />}
                    {v.kind === 'live' && !busy ? 'live session' : v.status}
                  </span>
                </div>
                <div className="nh5-video-body">
                  <strong title={v.originalFilename}>{v.originalFilename}</strong>
                  <span className="nh5-muted">{formatWhen(v.uploadedAt)}{v.sceneName ? ` · ${v.sceneName}` : ''}</span>
                  <div className="nh5-chip-row">
                    <span>{v.numVehicles || 0} vehicles</span>
                    <span><IdCard size={12} />{(v.plates || []).length} plates</span>
                    {events > 0 && <span className="warn"><AlertTriangle size={12} />{events} events</span>}
                  </div>
                </div>
              </Link>
            )
          })}
        </div>
      )}
    </div>
  )
}
