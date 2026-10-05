import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { CheckCircle2, FileVideo, Film, Network, RotateCcw, UploadCloud, X } from 'lucide-react'
import JobMonitor from './JobMonitor'
import { formatWhen, listScenes, uploadVideo } from '../../services/nh5Api'
import './nh5.css'

const ACCEPT = '.mp4,.avi,.mov,.mkv,.jpg,.jpeg,.png,.bmp'
const EMPTY_FIELDS = { scene_id: '', latitude: '', longitude: '', meters_per_pixel: '', speed_limit: '', thorough: false }

export default function VideoUploadPage() {
  const [file, setFile] = useState(null)
  const [fields, setFields] = useState(EMPTY_FIELDS)
  const [scenes, setScenes] = useState([])
  const [uploading, setUploading] = useState(false)
  const [uploadProgress, setUploadProgress] = useState(0)
  const [error, setError] = useState('')
  const [job, setJob] = useState(null)
  const [finished, setFinished] = useState(null)
  const [dragging, setDragging] = useState(false)
  const inputRef = useRef(null)

  useEffect(() => { listScenes().then(setScenes).catch(() => setScenes([])) }, [])

  const set = (key) => (e) => setFields((f) => ({ ...f, [key]: e.target.type === 'checkbox' ? e.target.checked : e.target.value }))

  async function handleSubmit(event, force = false) {
    event?.preventDefault()
    if (!file) { setError('Choose a video (or image) first.'); return }
    setError('')
    setUploading(true)
    setUploadProgress(0)
    try {
      const result = await uploadVideo(file, { ...fields, thorough: fields.thorough ? 'on' : '', force: force ? '1' : '' }, setUploadProgress)
      setJob(result)
      setFinished(null)
    } catch (err) {
      setError(err.message)
    } finally {
      setUploading(false)
    }
  }

  function reset() {
    setJob(null)
    setFinished(null)
    setFile(null)
    setFields(EMPTY_FIELDS)
    if (inputRef.current) inputRef.current.value = ''
  }

  return (
    <div className="nh5-page">
      <div className="page-intro">
        <p className="section-kicker">NH5 DETECTION PIPELINE</p>
        <h1>Video Upload</h1>
        <p className="intro-copy">
          Upload a highway video or image. The YOLOv8 model detects and tracks vehicles, reads Indian number plates,
          raises accident / fire / road-work events and writes an Excel report that is linked into the ontology.
        </p>
      </div>

      {!job ? (
        <form className="nh5-upload-grid" onSubmit={handleSubmit}>
          <div className="viq-card">
            <label
              className={`nh5-dropzone ${dragging ? 'drag' : ''} ${file ? 'has-file' : ''}`}
              onDragLeave={() => setDragging(false)}
              onDragOver={(e) => { e.preventDefault(); setDragging(true) }}
              onDrop={(e) => {
                e.preventDefault()
                setDragging(false)
                if (e.dataTransfer.files?.[0]) setFile(e.dataTransfer.files[0])
              }}
            >
              <input accept={ACCEPT} onChange={(e) => setFile(e.target.files?.[0] || null)} ref={inputRef} type="file" />
              {file ? (
                <>
                  <FileVideo size={34} />
                  <strong>{file.name}</strong>
                  <span>{(file.size / 1024 / 1024).toFixed(1)} MB · click to choose another file</span>
                </>
              ) : (
                <>
                  <UploadCloud size={34} />
                  <strong>Drop a video here or click to browse</strong>
                  <span>MP4, AVI, MOV, MKV or an image (JPG, PNG) · up to 2 GB</span>
                </>
              )}
            </label>
            {uploading && (
              <div className="nh5-upload-progress">
                <div className="nh5-progress"><i style={{ width: `${uploadProgress * 100}%` }} /></div>
                <span>Uploading… {Math.round(uploadProgress * 100)}%</span>
              </div>
            )}
          </div>

          <div className="viq-card nh5-form-card">
            <h2>Processing options</h2>
            <label className="nh5-field">Road map (camera)
              <select onChange={set('scene_id')} value={fields.scene_id}>
                <option value="">None — accident, fire and road-work rules only</option>
                {scenes.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
              </select>
            </label>
            <div className="nh5-field-row">
              <label className="nh5-field">Latitude<input onChange={set('latitude')} placeholder="e.g. 16.5062" value={fields.latitude} /></label>
              <label className="nh5-field">Longitude<input onChange={set('longitude')} placeholder="e.g. 80.6480" value={fields.longitude} /></label>
            </div>
            <div className="nh5-field-row">
              <label className="nh5-field">Meters per pixel<input onChange={set('meters_per_pixel')} placeholder="for speed" value={fields.meters_per_pixel} /></label>
              <label className="nh5-field">Speed limit (km/h)<input onChange={set('speed_limit')} placeholder="e.g. 80" value={fields.speed_limit} /></label>
            </div>
            <label className="nh5-toggle">
              <input checked={fields.thorough} onChange={set('thorough')} type="checkbox" />
              <span>Thorough mode <small>every frame, slower, more plates read</small></span>
            </label>
            {error && <p className="login-error">{error}</p>}
            <button className="primary-action nh5-submit" disabled={uploading || !file} type="submit">
              <UploadCloud size={16} />{uploading ? 'Uploading…' : 'Upload and process'}
            </button>
          </div>
        </form>
      ) : (
        <>
          <div className="nh5-job-head">
            <div>
              <strong>{job.originalFilename}</strong>
              <span>
                {job.duplicate
                  ? `Already processed on ${formatWhen(job.uploadedAt)} with the same settings: showing that result (not counted twice).`
                  : finished?.status === 'done' ? 'Processing complete' : finished?.status === 'error' ? 'Processing failed' : 'Processing…'}
              </span>
            </div>
            <div className="nh5-actions">
              {finished?.status === 'done' && (
                <>
                  <span className="nh5-done-pill"><CheckCircle2 size={14} />{job.duplicate ? 'Already in the Library and ontology' : 'Added to the Library and ontology'}</span>
                  <Link className="nh5-btn" to={`/video-library/${job.jobId}`}><Film size={15} />Open in Library</Link>
                  <Link className="nh5-btn" to={`/ontology?jobId=${job.jobId}`}><Network size={15} />View in Ontology</Link>
                </>
              )}
              {job.duplicate && (
                <button className="nh5-btn" disabled={uploading} onClick={() => handleSubmit(null, true)} type="button">
                  <RotateCcw size={15} />{uploading ? 'Uploading…' : 'Process again anyway'}
                </button>
              )}
              <button className="nh5-btn ghost" onClick={reset} type="button"><X size={15} />{finished ? 'Upload another' : 'Hide'}</button>
            </div>
          </div>
          <JobMonitor jobId={job.jobId} onFinished={setFinished} />
        </>
      )}
    </div>
  )
}
