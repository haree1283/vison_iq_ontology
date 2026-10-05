import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Map, Plus } from 'lucide-react'
import { createScene, formatWhen, listScenes, mediaUrl } from '../../services/nh5Api'
import './nh5.css'

export default function RoadMapsPage() {
  const navigate = useNavigate()
  const [scenes, setScenes] = useState([])
  const [name, setName] = useState('')
  const [file, setFile] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => { listScenes().then(setScenes).catch((err) => setError(err.message)) }, [])

  async function handleCreate(event) {
    event.preventDefault()
    if (!file) { setError('Choose an image or a short video from the camera.'); return }
    setBusy(true)
    setError('')
    try {
      const scene = await createScene(file, name)
      navigate(`/road-maps/${scene.id}`)
    } catch (err) {
      setError(err.message)
      setBusy(false)
    }
  }

  return (
    <div className="nh5-page">
      <div className="page-intro">
        <p className="section-kicker">NH5 DETECTION PIPELINE</p>
        <h1>Road Maps</h1>
        <p className="intro-copy">A road map describes one fixed camera: road area, roadside / footpath, zebra crossings and lanes with
          their travel direction. Choose it when uploading a video or starting the live camera to enable the pedestrian,
          jaywalking, lane-change, wrong-side and stopped-vehicle rules.</p>
      </div>

      <form className="viq-card nh5-scene-form" onSubmit={handleCreate}>
        <h2><Plus size={17} />New road map</h2>
        <label className="nh5-field">Name<input onChange={(e) => setName(e.target.value)} placeholder="e.g. NH5 km 42 northbound" value={name} /></label>
        <label className="nh5-field">Camera image or video
          <input accept=".mp4,.avi,.mov,.mkv,.jpg,.jpeg,.png,.bmp" onChange={(e) => setFile(e.target.files?.[0] || null)} type="file" />
        </label>
        <button className="primary-action nh5-submit" disabled={busy} type="submit">{busy ? 'Reading frame…' : 'Create and draw'}</button>
        {error && <p className="login-error">{error}</p>}
      </form>

      {scenes.length ? (
        <div className="nh5-library-grid">
          {scenes.map((s) => (
            <Link className="viq-card nh5-video-card" key={s.id} to={`/road-maps/${s.id}`}>
              <div className="nh5-thumb"><img alt={s.name} src={mediaUrl(s.previewUrl || s.frameUrl)} /></div>
              <div className="nh5-video-body">
                <strong>{s.name}</strong>
                <span className="nh5-muted">Updated {formatWhen(s.updatedAt)}</span>
                <div className="nh5-chip-row"><span>{s.zoneCount} zones</span><span>{s.laneCount} lanes</span></div>
              </div>
            </Link>
          ))}
        </div>
      ) : (
        <div className="viq-card nh5-empty"><Map size={30} /><p>No road maps yet.</p></div>
      )}
    </div>
  )
}
