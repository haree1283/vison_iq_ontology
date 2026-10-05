import React, { useEffect, useMemo, useRef, useState } from 'react'
import {
  AlertCircle,
  AlertTriangle,
  Camera,
  CheckCircle2,
  ExternalLink,
  Eye,
  Maximize2,
  Minimize2,
  Pause,
  Play,
  Radio,
  RotateCcw,
  Shield,
  Tv,
  Volume2,
  VolumeX,
} from 'lucide-react'

export function parseVideoSource(rawUrl) {
  if (!rawUrl || typeof rawUrl !== 'string') {
    return { type: 'none', raw: '' }
  }
  const url = rawUrl.trim()

  // 1. YouTube Matcher
  const ytMatch = url.match(
    /(?:youtube\.com\/(?:[^\/]+\/.+\/|(?:v|e(?:mbed)?)\/|.*[?&]v=|shorts\/)|youtu\.be\/)([^"&?\/\s]{11})/i
  )
  if (ytMatch && ytMatch[1]) {
    const videoId = ytMatch[1]
    return {
      type: 'youtube',
      videoId,
      embedUrl: `https://www.youtube-nocookie.com/embed/${videoId}?autoplay=1&mute=1&playsinline=1&rel=0&modestbranding=1`,
      originalUrl: url,
    }
  }

  // 2. Vimeo Matcher
  const vimeoMatch = url.match(
    /(?:vimeo\.com\/(?:channels\/(?:\w+\/)?|groups\/([^\/]*)\/videos\/|album\/(\d+)\/video\/|video\/|))(\d+)/i
  )
  if (vimeoMatch && (vimeoMatch[3] || vimeoMatch[1])) {
    const vimeoId = vimeoMatch[3] || vimeoMatch[1]
    return {
      type: 'vimeo',
      vimeoId,
      embedUrl: `https://player.vimeo.com/video/${vimeoId}?autoplay=1&muted=1`,
      originalUrl: url,
    }
  }

  // 3. Google Drive Video
  const driveMatch = url.match(/drive\.google\.com\/file\/d\/([a-zA-Z0-9_-]+)/i)
  if (driveMatch && driveMatch[1]) {
    const driveId = driveMatch[1]
    return {
      type: 'gdrive',
      driveId,
      embedUrl: `https://drive.google.com/file/d/${driveId}/preview`,
      originalUrl: url,
    }
  }

  // 4. Standard Web Video / Direct MP4 / WebM / Local LAN URL
  const isDirectWebUrl = url.startsWith('http://') || url.startsWith('https://')
  const isVideoExt = /\.(mp4|webm|ogg|ogv|mov|m4v)(\?.*)?$/i.test(url)
  const isBlobOrData = url.startsWith('blob:') || url.startsWith('data:video')

  return {
    type: isDirectWebUrl || isVideoExt || isBlobOrData ? 'direct' : 'relative',
    src: url,
    originalUrl: url,
  }
}

export default function SurveillanceVideoPlayer({
  videoClipPath,
  row,
  autoPlay = true,
  onClose,
}) {
  const resolvedUrl =
    videoClipPath ||
    row?.videoClipPath ||
    row?.videoUrl ||
    row?.url ||
    row?.video ||
    row?.['Video URL'] ||
    row?.['Video Clip Path'] ||
    row?.['Vedio Clip Path'] ||
    ''

  const videoSource = useMemo(() => parseVideoSource(resolvedUrl), [resolvedUrl])

  const [activeMode, setActiveMode] = useState('video') // 'video' | 'simulation'
  const [videoLoaded, setVideoLoaded] = useState(false)
  const [loadError, setLoadError] = useState(false)
  const [isPlaying, setIsPlaying] = useState(autoPlay)
  const [currentTime, setCurrentTime] = useState(0)
  const [duration, setDuration] = useState(15)
  const [playbackSpeed, setPlaybackSpeed] = useState(1)
  const [isMuted, setIsMuted] = useState(true)
  const [isFullscreen, setIsFullscreen] = useState(false)

  const containerRef = useRef(null)
  const videoRef = useRef(null)
  const canvasRef = useRef(null)
  const animFrameRef = useRef(null)

  const rawType = String(row?.vehicleType || row?.type || 'Car').toLowerCase()
  const isMotorcycle =
    rawType.includes('motorcycle') ||
    rawType.includes('bike') ||
    rawType.includes('scooter') ||
    rawType.includes('two')
  const isBus = rawType.includes('bus')
  const isTruck = rawType.includes('truck') || rawType.includes('heavy')
  const isAuto = rawType.includes('auto') || rawType.includes('rickshaw')
  const isPed = rawType.includes('ped') || rawType.includes('walk')

  const type = row?.vehicleType || row?.type || 'Car'
  const speed = Number(row?.speed) || 48
  const speedLimit = Number(row?.speedLimit) || 60
  const isOverSpeed =
    row?.overSpeed === 'Yes' || row?.isOverSpeed || speed > speedLimit
  const camera = row?.camera || 'CAM-04-HYD'
  const plate = row?.vehicleNumberPlate || row?.numberPlate || 'Plate not read'
  const timestampBase = row?.timestampIst || row?.timestamp || '13:22:04'
  const obsId = row?.id || row?.observationId || '1383'

  // Reset states on URL change
  useEffect(() => {
    setLoadError(false)
    setVideoLoaded(false)
    setActiveMode('video')
  }, [resolvedUrl])

  function handleVideoError() {
    // If local network stream is unreachable, fallback cleanly to simulation without jarring errors
    setLoadError(true)
    setActiveMode('simulation')
  }

  function handleVideoLoadedData() {
    setVideoLoaded(true)
    setLoadError(false)
  }

  function togglePlay() {
    setIsPlaying((prev) => {
      const willPlay = !prev
      if (willPlay && currentTime >= duration) {
        setCurrentTime(0)
        if (videoRef.current) {
          videoRef.current.currentTime = 0
        }
      }
      return willPlay
    })
    if (videoRef.current) {
      if (isPlaying) {
        videoRef.current.pause()
      } else {
        if (videoRef.current.currentTime >= duration) {
          videoRef.current.currentTime = 0
        }
        videoRef.current.play().catch(() => {})
      }
    }
  }

  function toggleFullscreen() {
    if (!containerRef.current) return
    if (!document.fullscreenElement) {
      containerRef.current
        .requestFullscreen()
        .then(() => setIsFullscreen(true))
        .catch(() => {})
    } else {
      document
        .exitFullscreen()
        .then(() => setIsFullscreen(false))
        .catch(() => {})
    }
  }

  function cycleSpeed() {
    const speeds = [1, 1.5, 2, 0.5]
    const nextIdx = (speeds.indexOf(playbackSpeed) + 1) % speeds.length
    const nextSpeed = speeds[nextIdx]
    setPlaybackSpeed(nextSpeed)
    if (videoRef.current) {
      videoRef.current.playbackRate = nextSpeed
    }
  }

  // Realistic AI Surveillance Simulation Canvas (Active when simulation mode or network stream offline)
  useEffect(() => {
    if (activeMode !== 'simulation' && !loadError) return

    let lastTimestamp = performance.now()
    let simTime = currentTime

    function renderFrame(now) {
      const delta = (now - lastTimestamp) / 1000
      lastTimestamp = now

      if (isPlaying) {
        simTime += delta * playbackSpeed
        if (simTime >= duration) {
          simTime = duration
          setIsPlaying(false)
        }
        setCurrentTime(simTime)
      }

      const canvas = canvasRef.current
      if (canvas) {
        const ctx = canvas.getContext('2d')
        const w = canvas.width
        const h = canvas.height

        // 1. Dark asphalt roadway texture with ambient gradient
        const roadGrad = ctx.createLinearGradient(0, 0, 0, h)
        roadGrad.addColorStop(0, '#040711')
        roadGrad.addColorStop(0.3, '#0b1120')
        roadGrad.addColorStop(1, '#020617')
        ctx.fillStyle = roadGrad
        ctx.fillRect(0, 0, w, h)

        // Subtle CCTV Scanlines
        ctx.fillStyle = 'rgba(255, 255, 255, 0.015)'
        for (let y = 0; y < h; y += 3) {
          ctx.fillRect(0, y, w, 1)
        }

        // 2. Highway Lanes in Perspective
        const vanishX = w * 0.5
        const vanishY = h * 0.12

        // Lane Curbs
        ctx.strokeStyle = '#1e293b'
        ctx.lineWidth = 2
        ctx.beginPath()
        ctx.moveTo(vanishX - 40, vanishY)
        ctx.lineTo(w * 0.04, h)
        ctx.moveTo(vanishX + 40, vanishY)
        ctx.lineTo(w * 0.96, h)
        ctx.stroke()

        // Dashed Lane Dividers (animated with velocity)
        const laneOffset = (simTime * (speed * 4)) % 40
        ctx.strokeStyle = 'rgba(148, 163, 184, 0.35)'
        ctx.lineWidth = 1.5
        ctx.setLineDash([16, 24])
        ctx.lineDashOffset = -laneOffset

        ctx.beginPath()
        ctx.moveTo(vanishX - 12, vanishY)
        ctx.lineTo(w * 0.36, h)
        ctx.moveTo(vanishX + 12, vanishY)
        ctx.lineTo(w * 0.64, h)
        ctx.stroke()
        ctx.setLineDash([])

        // Optical flow detection grid overlay
        ctx.strokeStyle = 'rgba(56, 189, 248, 0.05)'
        ctx.lineWidth = 1
        for (let i = 1; i <= 4; i++) {
          const gridY = vanishY + (h - vanishY) * (i / 4.5)
          ctx.beginPath()
          ctx.moveTo(w * 0.08, gridY)
          ctx.lineTo(w * 0.92, gridY)
          ctx.stroke()
        }

        // 3. Target Vehicle Progression
        const progress = (simTime % duration) / duration
        const vehY = vanishY + progress * (h * 0.65)
        const vehScale = 0.55 + (vehY / h) * 0.95

        let vehW = 80 * vehScale
        let vehH = 48 * vehScale
        if (isMotorcycle) {
          vehW = 44 * vehScale
          vehH = 68 * vehScale
        } else if (isTruck || isBus) {
          vehW = 100 * vehScale
          vehH = 85 * vehScale
        }
        const vehX = w * 0.5 - vehW / 2 + Math.sin(simTime * 1.8) * 12

        // Soft ground contact shadow
        ctx.fillStyle = 'rgba(0, 0, 0, 0.6)'
        ctx.beginPath()
        ctx.ellipse(vehX + vehW / 2, vehY + vehH + 3, vehW * 0.55, 6 * vehScale, 0, 0, Math.PI * 2)
        ctx.fill()

        if (isMotorcycle) {
          // --- REALISTIC MOTORCYCLE & RIDER SILHOUETTE ---
          // Rear wheel
          ctx.fillStyle = '#0f172a'
          ctx.beginPath()
          ctx.roundRect(vehX + vehW * 0.35, vehY + vehH * 0.65, vehW * 0.3, vehH * 0.32, 4)
          ctx.fill()

          // Motorcycle body / chassis
          const bikeGrad = ctx.createLinearGradient(vehX, vehY, vehX + vehW, vehY + vehH)
          bikeGrad.addColorStop(0, isOverSpeed ? '#ef4444' : '#0284c7')
          bikeGrad.addColorStop(1, isOverSpeed ? '#991b1b' : '#0369a1')
          ctx.fillStyle = bikeGrad
          ctx.beginPath()
          ctx.roundRect(vehX + vehW * 0.2, vehY + vehH * 0.35, vehW * 0.6, vehH * 0.36, 6)
          ctx.fill()

          // Rider Torso & Jacket
          ctx.fillStyle = '#1e293b'
          ctx.beginPath()
          ctx.roundRect(vehX + vehW * 0.22, vehY + vehH * 0.16, vehW * 0.56, vehH * 0.25, 6)
          ctx.fill()

          // Rider Helmet
          ctx.fillStyle = '#0f172a'
          ctx.beginPath()
          ctx.arc(vehX + vehW * 0.5, vehY + vehH * 0.12, vehW * 0.22, 0, Math.PI * 2)
          ctx.fill()
          // Helmet Visor
          ctx.fillStyle = '#38bdf8'
          ctx.beginPath()
          ctx.arc(vehX + vehW * 0.5, vehY + vehH * 0.12, vehW * 0.16, 0.1, Math.PI * 0.9)
          ctx.fill()

          // Taillight glow
          ctx.fillStyle = '#ef4444'
          ctx.fillRect(vehX + vehW * 0.38, vehY + vehH * 0.6, vehW * 0.24, 4)

          // License Plate on Motorcycle
          ctx.fillStyle = '#ffffff'
          ctx.fillRect(vehX + vehW * 0.25, vehY + vehH * 0.68, vehW * 0.5, vehH * 0.14)
          ctx.fillStyle = '#0f172a'
          ctx.font = `bold ${Math.max(6.5, Math.floor(7.5 * vehScale))}px monospace`
          ctx.textAlign = 'center'
          ctx.fillText(plate, vehX + vehW * 0.5, vehY + vehH * 0.78)
        } else {
          // --- REALISTIC 4-WHEELER / CAR SILHOUETTE ---
          const bodyGrad = ctx.createLinearGradient(vehX, vehY, vehX + vehW, vehY + vehH)
          if (isOverSpeed) {
            bodyGrad.addColorStop(0, '#dc2626')
            bodyGrad.addColorStop(1, '#7f1d1d')
          } else {
            bodyGrad.addColorStop(0, '#2563eb')
            bodyGrad.addColorStop(1, '#1e3a8a')
          }
          ctx.fillStyle = bodyGrad
          ctx.beginPath()
          ctx.roundRect(vehX, vehY + vehH * 0.2, vehW, vehH * 0.78, 6)
          ctx.fill()

          // Windshield & Roof
          ctx.fillStyle = '#090d16'
          ctx.beginPath()
          ctx.roundRect(vehX + vehW * 0.1, vehY, vehW * 0.8, vehH * 0.45, 4)
          ctx.fill()

          // Taillights
          ctx.fillStyle = '#ef4444'
          ctx.fillRect(vehX + 4, vehY + vehH * 0.45, vehW * 0.2, 5)
          ctx.fillRect(vehX + vehW - vehW * 0.2 - 4, vehY + vehH * 0.45, vehW * 0.2, 5)

          // License Plate
          ctx.fillStyle = '#ffffff'
          ctx.fillRect(vehX + vehW * 0.26, vehY + vehH * 0.62, vehW * 0.48, vehH * 0.2)
          ctx.fillStyle = '#0f172a'
          ctx.font = `bold ${Math.max(7, Math.floor(8.5 * vehScale))}px monospace`
          ctx.textAlign = 'center'
          ctx.fillText(plate, vehX + vehW * 0.5, vehY + vehH * 0.76)
        }

        // 4. AI Vision Bounding Box & HUD Reticles
        const pad = 6
        ctx.strokeStyle = isOverSpeed ? '#ef4444' : '#10b981'
        ctx.lineWidth = 1.8
        ctx.strokeRect(vehX - pad, vehY - pad, vehW + pad * 2, vehH + pad * 2)

        // Corner Calibration Brackets
        const cLen = 12
        ctx.lineWidth = 3
        ctx.strokeStyle = isOverSpeed ? '#f87171' : '#34d399'
        // Top-left
        ctx.beginPath()
        ctx.moveTo(vehX - pad, vehY - pad + cLen)
        ctx.lineTo(vehX - pad, vehY - pad)
        ctx.lineTo(vehX - pad + cLen, vehY - pad)
        // Top-right
        ctx.moveTo(vehX + vehW + pad - cLen, vehY - pad)
        ctx.lineTo(vehX + vehW + pad, vehY - pad)
        ctx.lineTo(vehX + vehW + pad, vehY - pad + cLen)
        // Bottom-left
        ctx.moveTo(vehX - pad, vehY + vehH + pad - cLen)
        ctx.lineTo(vehX - pad, vehY + vehH + pad)
        ctx.lineTo(vehX - pad + cLen, vehY + vehH + pad)
        // Bottom-right
        ctx.moveTo(vehX + vehW + pad - cLen, vehY + vehH + pad)
        ctx.lineTo(vehX + vehW + pad, vehY + vehH + pad)
        ctx.lineTo(vehX + vehW + pad, vehY + vehH + pad - cLen)
        ctx.stroke()

        // Tactical Detection Tag
        ctx.fillStyle = isOverSpeed ? 'rgba(220, 38, 38, 0.92)' : 'rgba(5, 150, 105, 0.92)'
        ctx.beginPath()
        ctx.roundRect(vehX - pad, vehY - pad - 22, Math.max(120, vehW + pad * 2), 20, 3)
        ctx.fill()
        ctx.fillStyle = '#ffffff'
        ctx.font = 'bold 10px monospace'
        ctx.textAlign = 'left'
        ctx.fillText(
          `#${obsId} ${type.toUpperCase()} · ${speed} KM/H ${isOverSpeed ? '⚠ OVERSPEED' : ''}`,
          vehX - pad + 6,
          vehY - pad - 8
        )
      }

      animFrameRef.current = requestAnimationFrame(renderFrame)
    }

    animFrameRef.current = requestAnimationFrame(renderFrame)
    return () => {
      if (animFrameRef.current) {
        cancelAnimationFrame(animFrameRef.current)
      }
    }
  }, [isPlaying, currentTime, duration, playbackSpeed, speed, speedLimit, isOverSpeed, type, plate, activeMode, loadError, isMotorcycle, isBus, isTruck, obsId])

  function formatSeconds(secs) {
    const s = Math.floor(secs || 0)
    const ms = Math.floor(((secs || 0) - s) * 100)
    const m = Math.floor(s / 60)
    const remS = s % 60
    return `${String(m).padStart(2, '0')}:${String(remS).padStart(2, '0')}.${String(ms).padStart(2, '0')}`
  }

  const isIframeVideo =
    videoSource.type === 'youtube' ||
    videoSource.type === 'vimeo' ||
    videoSource.type === 'gdrive'

  return (
    <div
      className="surveillance-player-wrapper"
      ref={containerRef}
      style={{
        position: 'relative',
        background: '#020617',
        borderRadius: '12px',
        overflow: 'hidden',
        border: '1px solid #1e293b',
        boxShadow: '0 12px 32px -4px rgba(0, 0, 0, 0.7)',
        width: '100%',
        aspectRatio: '16 / 10',
        display: 'flex',
        flexDirection: 'column',
      }}
    >
      {/* Tactical CCTV Top HUD Bar */}
      <div
        style={{
          position: 'absolute',
          top: 0,
          left: 0,
          right: 0,
          padding: '10px 14px',
          background: 'linear-gradient(180deg, rgba(2, 6, 23, 0.95) 0%, rgba(2, 6, 23, 0.6) 70%, transparent 100%)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          zIndex: 25,
          pointerEvents: 'auto',
        }}
      >
        {/* Left Surveillance Status */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <span
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '6px',
              color: '#ffffff',
              fontWeight: 800,
              fontSize: '11px',
              letterSpacing: '1px',
              fontFamily: 'monospace',
              background: 'rgba(239, 68, 68, 0.2)',
              border: '1px solid rgba(239, 68, 68, 0.4)',
              padding: '2px 8px',
              borderRadius: '4px',
            }}
          >
            <span
              style={{
                width: '7px',
                height: '7px',
                borderRadius: '50%',
                background: '#ef4444',
                boxShadow: '0 0 8px #ef4444',
                animation: 'hudBlink 1s infinite alternate',
              }}
            />
            LIVE REC
          </span>

          <span
            style={{
              fontFamily: 'monospace',
              fontSize: '11.5px',
              color: '#94a3b8',
              letterSpacing: '0.5px',
            }}
          >
            {camera} · <strong style={{ color: '#e2e8f0' }}>{timestampBase} IST</strong>
          </span>
        </div>

        {/* Right Tactical Controls */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          {/* Mode Switcher Pill */}
          <button
            onClick={() => {
              setActiveMode((prev) => (prev === 'video' ? 'simulation' : 'video'))
            }}
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '5px',
              background: activeMode === 'simulation' ? '#0369a1' : 'rgba(30, 41, 59, 0.9)',
              color: '#ffffff',
              border: '1px solid #334155',
              padding: '4px 10px',
              borderRadius: '5px',
              fontSize: '11px',
              fontWeight: 600,
              cursor: 'pointer',
              transition: 'all 0.15s ease',
            }}
            title="Toggle between direct video feed and AI radar vision simulation"
            type="button"
          >
            {activeMode === 'simulation' ? <Tv size={12} /> : <Radio size={12} />}
            <span>{activeMode === 'simulation' ? 'Radar Vision' : 'Direct Video'}</span>
          </button>

          {/* External Tab Popout */}
          {resolvedUrl && (
            <a
              href={resolvedUrl}
              rel="noopener noreferrer"
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '4px',
                background: 'rgba(30, 41, 59, 0.9)',
                color: '#38bdf8',
                border: '1px solid #334155',
                padding: '4px 9px',
                borderRadius: '5px',
                fontSize: '11px',
                fontWeight: 600,
                textDecoration: 'none',
                transition: 'background 0.15s ease',
              }}
              target="_blank"
              title="Open video URL in new tab"
            >
              <span>Open Tab</span>
              <ExternalLink size={11} />
            </a>
          )}
        </div>
      </div>

      {/* Video / Simulation Viewport */}
      <div style={{ position: 'relative', flex: 1, width: '100%', overflow: 'hidden' }}>
        {activeMode === 'video' && !loadError ? (
          isIframeVideo ? (
            /* 1. YouTube / Vimeo / Google Drive */
            <iframe
              allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share"
              allowFullScreen
              key={videoSource.embedUrl}
              src={videoSource.embedUrl}
              style={{
                width: '100%',
                height: '100%',
                border: 'none',
                background: '#000000',
              }}
              title="Surveillance Video Feed"
            />
          ) : (
            /* 2. Direct HTML5 Video Player - CRITICAL: No crossOrigin attribute to allow any LAN/HTTP stream */
            <video
              autoPlay={autoPlay}
              controls={false}
              muted={isMuted}
              onEnded={() => setIsPlaying(false)}
              onError={handleVideoError}
              onLoadedData={handleVideoLoadedData}
              onLoadedMetadata={(e) => {
                if (e.target.duration && !isNaN(e.target.duration)) {
                  setDuration(e.target.duration)
                }
              }}
              onTimeUpdate={(e) => setCurrentTime(e.target.currentTime)}
              playsInline
              preload="auto"
              ref={videoRef}
              src={videoSource.src || resolvedUrl}
              style={{
                width: '100%',
                height: '100%',
                objectFit: 'contain',
                background: '#000000',
                display: 'block',
              }}
            />
          )
        ) : (
          /* 3. Realistic Tactical Surveillance AI Simulation */
          <div style={{ position: 'relative', width: '100%', height: '100%' }}>
            <canvas
              height={360}
              ref={canvasRef}
              style={{
                width: '100%',
                height: '100%',
                display: 'block',
              }}
              width={560}
            />

            {/* Offline Stream Indicator Banner if connection couldn't be established */}
            {loadError && (
              <div
                style={{
                  position: 'absolute',
                  top: '46px',
                  left: '12px',
                  right: '12px',
                  background: 'rgba(15, 23, 42, 0.92)',
                  border: '1px solid rgba(56, 189, 248, 0.3)',
                  backdropFilter: 'blur(4px)',
                  padding: '6px 12px',
                  borderRadius: '6px',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  zIndex: 20,
                  fontSize: '11px',
                  color: '#e2e8f0',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', overflow: 'hidden' }}>
                  <Shield color="#38bdf8" size={14} />
                  <span style={{ color: '#94a3b8' }}>AI Radar Active · Stream Source:</span>
                  <code
                    style={{
                      color: '#38bdf8',
                      fontFamily: 'monospace',
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                      whiteSpace: 'nowrap',
                      maxWidth: '280px',
                    }}
                  >
                    {resolvedUrl}
                  </code>
                </div>

                <div style={{ display: 'flex', gap: '6px', flexShrink: 0 }}>
                  <a
                    href={resolvedUrl}
                    rel="noopener noreferrer"
                    style={{
                      background: '#2563eb',
                      color: '#ffffff',
                      padding: '3px 8px',
                      borderRadius: '4px',
                      textDecoration: 'none',
                      fontWeight: 600,
                      fontSize: '10.5px',
                      display: 'inline-flex',
                      alignItems: 'center',
                      gap: '4px',
                    }}
                    target="_blank"
                  >
                    <span>Direct Play ↗</span>
                  </a>
                  <button
                    onClick={() => {
                      setLoadError(false)
                      setActiveMode('video')
                    }}
                    style={{
                      background: '#334155',
                      color: '#cbd5e1',
                      border: 'none',
                      padding: '3px 8px',
                      borderRadius: '4px',
                      cursor: 'pointer',
                      fontWeight: 600,
                      fontSize: '10.5px',
                    }}
                    type="button"
                  >
                    Retry
                  </button>
                </div>
              </div>
            )}
          </div>
        )}

        {/* Tactical Crosshair Reticles on Viewport Corners */}
        <div
          style={{
            position: 'absolute',
            inset: 0,
            pointerEvents: 'none',
            zIndex: 10,
          }}
        >
          {/* Top-Left Reticle */}
          <span style={{ position: 'absolute', top: '10px', left: '10px', color: 'rgba(56, 189, 248, 0.4)', fontFamily: 'monospace', fontSize: '14px' }}>+</span>
          {/* Top-Right Reticle */}
          <span style={{ position: 'absolute', top: '10px', right: '10px', color: 'rgba(56, 189, 248, 0.4)', fontFamily: 'monospace', fontSize: '14px' }}>+</span>
          {/* Bottom-Left Reticle */}
          <span style={{ position: 'absolute', bottom: '10px', left: '10px', color: 'rgba(56, 189, 248, 0.4)', fontFamily: 'monospace', fontSize: '14px' }}>+</span>
          {/* Bottom-Right Reticle */}
          <span style={{ position: 'absolute', bottom: '10px', right: '10px', color: 'rgba(56, 189, 248, 0.4)', fontFamily: 'monospace', fontSize: '14px' }}>+</span>
        </div>

        {/* Viewport Bottom Overlay HUD Bar */}
        <div
          style={{
            position: 'absolute',
            bottom: '8px',
            left: '12px',
            right: '12px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            pointerEvents: 'none',
            zIndex: 15,
          }}
        >
          <div
            style={{
              background: 'rgba(15, 23, 42, 0.88)',
              border: '1px solid #334155',
              padding: '3px 10px',
              borderRadius: '4px',
              fontSize: '11px',
              color: '#ffffff',
              fontFamily: 'monospace',
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
            }}
          >
            <span style={{ color: '#94a3b8' }}>ANPR:</span>
            <strong style={{ color: '#38bdf8', letterSpacing: '1px' }}>{plate}</strong>
          </div>

          <div
            style={{
              background: isOverSpeed ? 'rgba(220, 38, 38, 0.9)' : 'rgba(16, 185, 129, 0.9)',
              color: '#ffffff',
              padding: '3px 10px',
              borderRadius: '4px',
              fontSize: '11px',
              fontWeight: 700,
              fontFamily: 'monospace',
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
            }}
          >
            <span>RADAR: {speed} km/h</span>
            <span style={{ opacity: 0.8 }}>(LIMIT {speedLimit})</span>
          </div>
        </div>
      </div>

      {/* Tactical Glassmorphism Control Bar */}
      <div
        style={{
          background: '#090d16',
          borderTop: '1px solid #1e293b',
          padding: '8px 14px',
          display: 'flex',
          flexDirection: 'column',
          gap: '6px',
          zIndex: 20,
        }}
      >
        {/* Scrubber Line */}
        <div
          onClick={(e) => {
            const rect = e.currentTarget.getBoundingClientRect()
            const pos = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width))
            setCurrentTime(pos * duration)
            if (videoRef.current) {
              videoRef.current.currentTime = pos * duration
            }
          }}
          style={{
            width: '100%',
            height: '4px',
            background: '#334155',
            borderRadius: '2px',
            cursor: 'pointer',
            position: 'relative',
          }}
        >
          <div
            style={{
              width: `${(currentTime / (duration || 1)) * 100}%`,
              height: '100%',
              background: isOverSpeed ? '#ef4444' : '#38bdf8',
              borderRadius: '2px',
              position: 'relative',
            }}
          >
            <div
              style={{
                position: 'absolute',
                right: '-4px',
                top: '-3px',
                width: '10px',
                height: '10px',
                borderRadius: '50%',
                background: '#ffffff',
                boxShadow: '0 0 6px rgba(56, 189, 248, 0.8)',
              }}
            />
          </div>
        </div>

        {/* Buttons Row */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <button
              onClick={togglePlay}
              style={{
                background: isPlaying ? '#334155' : '#2563eb',
                color: '#ffffff',
                border: 'none',
                borderRadius: '6px',
                width: '28px',
                height: '28px',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                cursor: 'pointer',
                transition: 'background 0.15s ease',
              }}
              title={isPlaying ? 'Pause (Space)' : 'Play (Space)'}
              type="button"
            >
              {isPlaying ? <Pause size={13} /> : <Play size={13} style={{ marginLeft: '1px' }} />}
            </button>

            <button
              onClick={() => {
                setCurrentTime(0)
                if (videoRef.current) videoRef.current.currentTime = 0
                setIsPlaying(true)
              }}
              style={{
                background: 'transparent',
                color: '#94a3b8',
                border: 'none',
                cursor: 'pointer',
                padding: '4px',
                display: 'flex',
                alignItems: 'center',
              }}
              title="Restart"
              type="button"
            >
              <RotateCcw size={13} />
            </button>

            <span
              style={{
                fontFamily: 'monospace',
                fontSize: '11px',
                color: '#cbd5e1',
                paddingLeft: '4px',
              }}
            >
              {formatSeconds(currentTime)} / {formatSeconds(duration)}
            </span>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <button
              onClick={cycleSpeed}
              style={{
                background: '#1e293b',
                color: '#38bdf8',
                border: '1px solid #334155',
                borderRadius: '4px',
                fontSize: '10.5px',
                fontWeight: 700,
                padding: '2px 6px',
                cursor: 'pointer',
              }}
              title="Playback Speed"
              type="button"
            >
              {playbackSpeed}x
            </button>

            <button
              onClick={() => {
                setIsMuted((m) => !m)
                if (videoRef.current) {
                  videoRef.current.muted = !isMuted
                }
              }}
              style={{
                background: 'transparent',
                color: '#94a3b8',
                border: 'none',
                cursor: 'pointer',
                padding: '4px',
                display: 'flex',
                alignItems: 'center',
              }}
              title={isMuted ? 'Unmute' : 'Mute'}
              type="button"
            >
              {isMuted ? <VolumeX size={14} /> : <Volume2 size={14} />}
            </button>

            <button
              onClick={toggleFullscreen}
              style={{
                background: 'transparent',
                color: '#94a3b8',
                border: 'none',
                cursor: 'pointer',
                padding: '4px',
                display: 'flex',
                alignItems: 'center',
              }}
              title="Fullscreen"
              type="button"
            >
              {isFullscreen ? <Minimize2 size={14} /> : <Maximize2 size={14} />}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
