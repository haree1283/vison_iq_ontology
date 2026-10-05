import { useEffect, useRef, useState } from 'react'
import { Loader2 } from 'lucide-react'
import JobStats from './JobStats'
import { getVideoStatus, mediaUrl, streamUrl } from '../../services/nh5Api'

const FINISHED = new Set(['done', 'error'])

// Follows one processing job: live annotated preview (MJPEG) + progress + counts; the finished video afterwards.
export default function JobMonitor({ jobId, onFinished }) {
  const [status, setStatus] = useState(null)
  const [error, setError] = useState('')
  const finishedRef = useRef(false)

  useEffect(() => {
    finishedRef.current = false
    let timer
    let active = true
    async function poll() {
      try {
        const s = await getVideoStatus(jobId)
        if (!active) return
        setStatus(s)
        setError('')
        if (FINISHED.has(s.status)) {
          if (!finishedRef.current) {
            finishedRef.current = true
            onFinished?.(s)
          }
          return
        }
      } catch (err) {
        if (!active) return
        setError(err.message)
      }
      timer = setTimeout(poll, 1500)
    }
    poll()
    return () => { active = false; clearTimeout(timer) }
  }, [jobId])

  const done = status?.status === 'done'
  const progress = status?.total_frames ? Math.min(100, (status.frame_idx / status.total_frames) * 100) : null

  return (
    <div className="nh5-monitor">
      <div className="viq-card nh5-viewer-card">
        <div className="nh5-viewer">
          {done ? (
            <video controls key="done" src={mediaUrl(`/media/${jobId}/annotated.mp4`)} />
          ) : status?.status === 'error' ? (
            <div className="nh5-viewer-empty">Processing failed: {status.error}</div>
          ) : (
            <img alt="Annotated preview" src={streamUrl(jobId)} />
          )}
          <span className={`nh5-status-badge st-${status?.status || 'processing'}`}>
            {!status || !FINISHED.has(status.status) ? <Loader2 className="nh5-spin" size={13} /> : null}
            {status?.status || 'starting'}
          </span>
        </div>
        {progress !== null && !done && (
          <div className="nh5-progress"><i style={{ width: `${progress}%` }} /></div>
        )}
        {status?.status === 'finalizing' && (
          <p className="nh5-muted nh5-pad">Writing the annotated video and the Excel report…</p>
        )}
      </div>
      <div className="viq-card nh5-side-card">
        {error && <p className="login-error">{error}</p>}
        <JobStats status={status} />
      </div>
    </div>
  )
}
