import { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import {
  AlertTriangle, ArrowLeft, CarFront, Download, IdCard, Network, Trash2, Users,
} from 'lucide-react'
import JobMonitor from './JobMonitor'
import { deleteVideo, formatWhen, getVideo, mediaUrl } from '../../services/nh5Api'
import './nh5.css'

const PAGE = 60

export default function VideoDetailPage() {
  const { jobId } = useParams()
  const navigate = useNavigate()
  const [video, setVideo] = useState(null)
  const [error, setError] = useState('')
  const [typeFilter, setTypeFilter] = useState('')
  const [shown, setShown] = useState(PAGE)
  const [deleting, setDeleting] = useState(false)
  const [reload, setReload] = useState(0)

  useEffect(() => {
    let active = true
    getVideo(jobId).then((v) => { if (active) { setVideo(v); setError('') } }).catch((err) => active && setError(err.message))
    return () => { active = false }
  }, [jobId, reload])

  const vehicles = useMemo(
    () => (video?.vehicles || []).filter((v) => !typeFilter || v.vehicleType === typeFilter),
    [video, typeFilter],
  )
  const types = useMemo(() => Array.from(new Set((video?.vehicles || []).map((v) => v.vehicleType).filter(Boolean))), [video])

  async function handleDelete() {
    if (!window.confirm(`Delete "${video.originalFilename}" from the library? Its annotated video, Excel report and records are removed.`)) return
    setDeleting(true)
    try {
      await deleteVideo(jobId)
      navigate('/video-library', { replace: true })
    } catch (err) {
      setError(err.message)
      setDeleting(false)
    }
  }

  if (error && !video) {
    return (
      <div className="nh5-page">
        <Link className="nh5-back" to="/video-library"><ArrowLeft size={15} />Video Library</Link>
        <p className="login-error">{error}</p>
      </div>
    )
  }
  if (!video) return <div className="nh5-page"><p className="nh5-muted">Loading…</p></div>

  if (video.processing) {
    return (
      <div className="nh5-page">
        <Link className="nh5-back" to="/video-library"><ArrowLeft size={15} />Video Library</Link>
        <div className="page-intro"><p className="section-kicker">PROCESSING</p><h1>{video.originalFilename || jobId}</h1></div>
        <JobMonitor jobId={jobId} onFinished={() => setReload((n) => n + 1)} />
      </div>
    )
  }

  const eventTotal = video.events.length
  return (
    <div className="nh5-page">
      <Link className="nh5-back" to="/video-library"><ArrowLeft size={15} />Video Library</Link>
      <div className="nh5-page-head">
        <div className="page-intro">
          <p className="section-kicker">{video.kind === 'live' ? 'LIVE CAMERA SESSION' : 'PROCESSED VIDEO'} · {formatWhen(video.uploadedAt)}</p>
          <h1>{video.originalFilename}</h1>
          <p className="intro-copy">
            Model {video.modelName}{video.sceneName ? ` · road map ${video.sceneName}` : ''}
            {video.totalFrames ? ` · ${video.totalFrames} frames` : ''}{video.processingFps ? ` · ${video.processingFps} fps` : ''}
          </p>
        </div>
        <div className="nh5-actions">
          {video.report && <a className="nh5-btn excel" href={mediaUrl(video.report)}><Download size={15} />report.xlsx</a>}
          <Link className="nh5-btn" to={`/ontology?jobId=${jobId}`}><Network size={15} />View in Ontology</Link>
          <button className="nh5-btn danger" disabled={deleting} onClick={handleDelete} type="button"><Trash2 size={15} />Delete</button>
        </div>
      </div>
      {error && <p className="login-error">{error}</p>}

      <div className="nh5-detail-top">
        <div className="viq-card nh5-viewer-card">
          <div className="nh5-viewer">
            {video.video ? <video controls src={mediaUrl(video.video)} /> : <div className="nh5-viewer-empty">No annotated video.</div>}
          </div>
        </div>
        <div className="nh5-kpis">
          <div className="viq-card nh5-kpi"><CarFront size={18} /><strong>{video.numVehicles}</strong><span>Vehicles tracked</span></div>
          <div className="viq-card nh5-kpi"><IdCard size={18} /><strong>{video.uniquePlates.length}</strong><span>Unique plates</span></div>
          <div className="viq-card nh5-kpi"><Users size={18} /><strong>{video.numPeople}</strong><span>People</span></div>
          <div className="viq-card nh5-kpi"><AlertTriangle size={18} /><strong>{eventTotal}</strong><span>Events</span></div>
          <div className="viq-card nh5-kpi nh5-kpi-wide">
            {Object.entries(video.vehicleTypes || {}).map(([t, n]) => <span className="nh5-type-pill" key={t}>{t} <b>{n}</b></span>)}
          </div>
        </div>
      </div>

      <section className="viq-card nh5-section">
        <div className="viq-card-header"><div className="viq-card-title-group"><IdCard className="viq-card-icon" size={19} /><h2>Unique number plates</h2></div></div>
        {video.uniquePlates.length ? (
          <div className="nh5-plates-grid">
            {video.uniquePlates.map((p) => (
              <div className="nh5-plate-card" key={p.plate}>
                {p.vehicleImage && <img alt={p.plate} src={mediaUrl(p.vehicleImage)} />}
                <div>
                  <span className="nh5-plate big"><em>IND</em>{p.plate}</span>
                  {p.plateImage && <img alt={`${p.plate} plate`} className="nh5-plate-crop" src={mediaUrl(p.plateImage)} />}
                  <span className="nh5-muted">{p.vehicleTypes.join(', ')} · {p.tracks} track(s) · {Math.round((p.plateConfidence > 1 ? p.plateConfidence / 100 : p.plateConfidence) * 100)}% OCR</span>
                  <span className="nh5-muted">{formatWhen(p.firstSeen)}</span>
                  <Link className="nh5-link" to={`/vehicle-information?plate=${encodeURIComponent(p.plate)}`}>Track across videos →</Link>
                </div>
              </div>
            ))}
          </div>
        ) : <p className="nh5-muted nh5-pad">No number plate was read with enough confidence in this video.</p>}
      </section>

      <section className="viq-card nh5-section">
        <div className="viq-card-header"><div className="viq-card-title-group"><AlertTriangle className="viq-card-icon" size={19} /><h2>Events</h2></div></div>
        {eventTotal ? (
          <div className="nh5-event-cards">
            {video.events.map((e) => (
              <div className={`nh5-event-card sev-${e.severity}`} key={e.id}>
                {e.snapshot && <a href={mediaUrl(e.snapshot)} rel="noreferrer" target="_blank"><img alt={e.label} src={mediaUrl(e.snapshot)} /></a>}
                <div>
                  <strong>{e.label}</strong>
                  <span className="nh5-muted">{e.severity} · {Number(e.timeInVideoS || 0).toFixed(1)}s · {e.objectClass}{e.plateNumber && e.plateNumber !== 'n/a' ? ` · ${e.plateNumber}` : ''}</span>
                  <span className="nh5-muted">{e.timestamp}</span>
                </div>
              </div>
            ))}
          </div>
        ) : <p className="nh5-muted nh5-pad">No events in this video.</p>}
      </section>

      <section className="viq-card nh5-section">
        <div className="viq-card-header">
          <div className="viq-card-title-group"><CarFront className="viq-card-icon" size={19} /><h2>Vehicles ({vehicles.length})</h2></div>
          <select className="nh5-select" onChange={(e) => { setTypeFilter(e.target.value); setShown(PAGE) }} value={typeFilter}>
            <option value="">All types</option>
            {types.map((t) => <option key={t} value={t}>{t}</option>)}
          </select>
        </div>
        <div className="nh5-table-wrap">
          <table className="nh5-table">
            <thead><tr><th>Track</th><th>Photo</th><th>Type</th><th>Number plate</th><th>First seen</th><th>Frames</th><th>Speed</th><th>Events</th></tr></thead>
            <tbody>
              {vehicles.slice(0, shown).map((v) => (
                <tr key={v.id}>
                  <td>#{v.trackId}</td>
                  <td>{v.vehicleImage ? <a href={mediaUrl(v.vehicleImage)} rel="noreferrer" target="_blank"><img alt="" src={mediaUrl(v.vehicleImage)} /></a> : '–'}</td>
                  <td>{v.vehicleType}</td>
                  <td>{v.plate ? <span className="nh5-plate"><em>IND</em>{v.plate}</span> : <span className="nh5-muted">not read</span>}</td>
                  <td>{v.timestamp}</td>
                  <td>{v.timesSeen ?? '–'}</td>
                  <td>{typeof v.speedKmh === 'number' ? `${v.speedKmh} km/h` : <span className="nh5-muted">{v.speedKmh || '–'}</span>}</td>
                  <td>{(v.events || []).length ? v.events.map((e) => (typeof e === 'string' ? e : e.label)).join(', ') : '–'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {vehicles.length > shown && (
          <button className="nh5-btn ghost nh5-more" onClick={() => setShown((n) => n + PAGE)} type="button">Show more ({vehicles.length - shown} left)</button>
        )}
      </section>
    </div>
  )
}
