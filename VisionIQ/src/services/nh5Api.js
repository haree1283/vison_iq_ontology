// Client for the NH5 Highway detection pipeline (YOLOv8 + ByteTrack + PaddleOCR) served by the VisionIQ backend.
const API_URL = (import.meta.env.VITE_API_URL || '').replace(/\/$/, '')

async function call(path, options = {}) {
  let response
  try {
    response = await fetch(`${API_URL}${path}`, options)
  } catch {
    throw new Error('Unable to reach the VisionIQ server.')
  }
  const payload = await response.json().catch(() => ({}))
  if (!response.ok || payload.success === false) {
    const error = new Error(payload.message || `Request failed (HTTP ${response.status}).`)
    error.status = response.status
    throw error
  }
  return payload
}

const json = (method, body) => ({
  method,
  headers: { 'Content-Type': 'application/json' },
  body: body === undefined ? undefined : JSON.stringify(body),
})

export const mediaUrl = (path) => (path ? `${API_URL}${path}` : '')

export const getModelInfo = () => call('/api/nh5/model').then((r) => r.model)

// ---- videos
export function uploadVideo(file, fields = {}, onProgress) {
  // XMLHttpRequest instead of fetch so large uploads can report progress
  return new Promise((resolve, reject) => {
    const form = new FormData()
    form.append('video', file)
    Object.entries(fields).forEach(([key, value]) => {
      if (value !== undefined && value !== null && value !== '') form.append(key, value)
    })
    const xhr = new XMLHttpRequest()
    xhr.open('POST', `${API_URL}/api/nh5/videos`)
    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable && onProgress) onProgress(event.loaded / event.total)
    }
    xhr.onload = () => {
      let payload = {}
      try { payload = JSON.parse(xhr.responseText) } catch { /* not JSON */ }
      if (xhr.status >= 200 && xhr.status < 300 && payload.success !== false) resolve(payload)
      else reject(new Error(payload.message || `Upload failed (HTTP ${xhr.status}).`))
    }
    xhr.onerror = () => reject(new Error('Upload failed: unable to reach the VisionIQ server.'))
    xhr.send(form)
  })
}

export const listVideos = () => call('/api/nh5/videos').then((r) => r.videos)
export const getVideo = (jobId) => call(`/api/nh5/videos/${encodeURIComponent(jobId)}`).then((r) => r.video)
export const getVideoStatus = (jobId) => call(`/api/nh5/videos/${encodeURIComponent(jobId)}/status`).then((r) => r.status)
export const deleteVideo = (jobId) => call(`/api/nh5/videos/${encodeURIComponent(jobId)}`, { method: 'DELETE' })
export const streamUrl = (jobId) => mediaUrl(`/stream/${encodeURIComponent(jobId)}`)

// ---- live camera
export const startLive = (settings) => call('/api/nh5/live/start', json('POST', settings))
export const stopLive = () => call('/api/nh5/live/stop', json('POST', {}))
export const getLiveStatus = () => call('/api/nh5/live/status').then((r) => r.status)
export function liveSocketUrl() {
  const base = API_URL || window.location.origin
  return `${base.replace(/^http/, 'ws')}/live_ws`
}

// ---- road maps
export const listScenes = () => call('/api/nh5/scenes').then((r) => r.scenes)
export const getScene = (id) => call(`/api/nh5/scenes/${encodeURIComponent(id)}`).then((r) => r.scene)
export function createScene(file, name) {
  const form = new FormData()
  form.append('source', file)
  form.append('name', name || '')
  return call('/api/nh5/scenes', { method: 'POST', body: form }).then((r) => r.scene)
}
export const saveScene = (id, data) => call(`/api/nh5/scenes/${encodeURIComponent(id)}`, json('PUT', data)).then((r) => r.scene)
export const deleteScene = (id) => call(`/api/nh5/scenes/${encodeURIComponent(id)}`, { method: 'DELETE' })

// ---- ontology from the Excel reports
export const getOntologyGraph = (jobId) =>
  call(`/api/ontology/graph${jobId ? `?jobId=${encodeURIComponent(jobId)}` : ''}`)

// ---- shared labels
export const VEHICLE_TYPES = [
  ['car', 'Cars'], ['motorcycle', 'Motorcycles'], ['auto', 'Autos'],
  ['bus', 'Buses'], ['truck', 'Trucks'], ['bicycle', 'Bicycles'],
]

export function formatDuration(seconds) {
  if (seconds === null || seconds === undefined) return '–'
  const m = Math.floor(seconds / 60)
  const s = Math.round(seconds % 60)
  return m ? `${m}m ${s}s` : `${s}s`
}

export function formatWhen(iso) {
  if (!iso) return ''
  return String(iso).replace('T', ' ')
}
