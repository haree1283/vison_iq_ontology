import React, { useEffect, useState } from 'react'
import {
  Bike,
  Bus,
  Camera,
  Car,
  Check,
  ChevronLeft,
  ChevronRight,
  Clock,
  Copy,
  Download,
  ExternalLink,
  Eye,
  EyeOff,
  FileSpreadsheet,
  FileVideo,
  Gauge,
  Image as ImageIcon,
  MapPin,
  RotateCcw,
  Sparkles,
  Truck,
  X,
  ZoomIn,
  ZoomOut,
  Maximize2,
  Minimize2,
} from 'lucide-react'
import SurveillanceVideoPlayer from './SurveillanceVideoPlayer'
import { formatTimestampIst } from '../data/dashboardData'


function VehicleTypeIcon({ type, size = 15 }) {
  const t = String(type || '').toLowerCase()
  if (t.includes('bike') || t.includes('motorcycle') || t.includes('scooter') || t.includes('two')) {
    return <Bike size={size} />
  }
  if (t.includes('bus')) {
    return <Bus size={size} />
  }
  if (t.includes('truck') || t.includes('heavy') || t.includes('lorry')) {
    return <Truck size={size} />
  }
  return <Car size={size} />
}


export default function MediaPreviewModal({
  isOpen,
  onClose,
  row,
  allRows = [],
  onSelectRow,
  initialTab = 'vehicle',
}) {
  const [activeMediaTab, setActiveMediaTab] = useState(initialTab) // 'vehicle' | 'plate' | 'video'
  const [copiedPath, setCopiedPath] = useState(false)
  const [copiedPlate, setCopiedPlate] = useState(false)
  const [imgLoadError, setImgLoadError] = useState(false)
  const [plateLoadError, setPlateLoadError] = useState(false)
  const [showOverlays, setShowOverlays] = useState(true)
  const [zoomLevel, setZoomLevel] = useState(1)
  const [fitMode, setFitMode] = useState('cover')

  useEffect(() => {
    setActiveMediaTab(initialTab || 'vehicle')
    setZoomLevel(1)
  }, [initialTab, row?.id, row?.observationId])

  useEffect(() => {
    setImgLoadError(false)
    setPlateLoadError(false)
    setZoomLevel(1)
  }, [row?.id, row?.observationId])

  useEffect(() => {
    function handleKeyDown(e) {
      if (!isOpen) return
      if (e.key === 'Escape') {
        onClose?.()
      } else if (e.key === 'ArrowLeft' && allRows.length > 1 && onSelectRow) {
        navigateRow(-1)
      } else if (e.key === 'ArrowRight' && allRows.length > 1 && onSelectRow) {
        navigateRow(1)
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [isOpen, row, allRows, onSelectRow])

  if (!isOpen || !row) return null

  const currentIndex = allRows.findIndex(
    (r) =>
      (r.id && r.id === row.id) ||
      (r.observationId && r.observationId === row.observationId)
  )

  function navigateRow(direction) {
    if (currentIndex === -1 || !allRows.length) return
    const nextIdx = currentIndex + direction
    if (nextIdx < 0 || nextIdx >= allRows.length) return
    onSelectRow?.(allRows[nextIdx])
  }

  const isOverSpeed =
    row.overSpeed === 'Yes' ||
    row.isOverSpeed ||
    Number(row.speed) > Number(row.speedLimit)

  const plateConfidencePercent = Math.round(
    (row.plateConfidence || row.confidence) > 1
      ? row.plateConfidence || row.confidence
      : (row.plateConfidence || row.confidence || 0.95) * 100
  )

  // Extract raw paths
  const rawVideo =
    row.videoClipPath ||
    row.videoUrl ||
    row.url ||
    row.video ||
    row['Video URL'] ||
    row['Video Clip Path'] ||
    row['Vedio Clip Path'] ||
    row['Video Link'] ||
    row['video_url'] ||
    row['URL'] ||
    row['link'] ||
    ''

  const hasRealVideo = Boolean(
    rawVideo &&
    !rawVideo.includes('youtube.com/watch?v=1EiC9bvVGnk') &&
    (rawVideo.startsWith('http') || rawVideo.startsWith('/') || rawVideo.includes('.'))
  )

  const videoUrl = rawVideo || 'https://www.youtube.com/watch?v=1EiC9bvVGnk'

  function normalizeMediaPath(raw) {
    const s = String(raw || '').trim();
    if (!s) return '';
    if (s.startsWith('http://') || s.startsWith('https://') || s.startsWith('data:')) return s;
    if (s.startsWith('/')) return s;
    if (s.startsWith('images/')) return '/' + s;
    if (s.includes('.jp') || s.includes('.png')) return '/images/' + s.replace(/^.*[\\/]/, '');
    return s;
  }

  const vehicleImagePath = normalizeMediaPath(
    row.vehicleImagePath ||
    row.vehicleImage ||
    row['Vehicle Image Path'] ||
    row['vehicle_photos'] ||
    row.extractedImageName
  );

  const plateImagePath =
    row.plateImagePath ||
    row['Plate Image Path'] ||
    row['plate_photos'] ||
    ''

  function getBasename(pathStr) {
    if (!pathStr || typeof pathStr !== 'string') return 'Unknown'
    const parts = pathStr.split('/')
    return parts[parts.length - 1] || pathStr
  }

  const currentActivePath =
    activeMediaTab === 'video'
      ? (hasRealVideo ? rawVideo : 'No video clip linked')
      : activeMediaTab === 'plate'
      ? (plateImagePath || 'ANPR OCR extraction')
      : (vehicleImagePath || 'vehicle_capture.jpg')

  function handleCopyPath() {
    if (navigator.clipboard) {
      navigator.clipboard.writeText(currentActivePath)
      setCopiedPath(true)
      setTimeout(() => setCopiedPath(false), 2000)
    }
  }

  function handleCopyPlate() {
    const plate = row.vehicleNumberPlate || row.numberPlate || ''
    if (plate && navigator.clipboard) {
      navigator.clipboard.writeText(plate)
      setCopiedPlate(true)
      setTimeout(() => setCopiedPlate(false), 2000)
    }
  }

  // Determine actual image source for vehicle
  const vehicleSrc =
    row.extractedImage ||
    (!imgLoadError && vehicleImagePath && (vehicleImagePath.startsWith('http') || vehicleImagePath.startsWith('data:') || vehicleImagePath.startsWith('/'))
      ? vehicleImagePath
      : (!imgLoadError && row.vehicleImage && (row.vehicleImage.startsWith('http') || row.vehicleImage.startsWith('data:') || row.vehicleImage.startsWith('/'))
        ? row.vehicleImage
        : row.extractedImage || null))

  // Determine actual image source for plate
  const plateSrc =
    (!plateLoadError && plateImagePath && (plateImagePath.startsWith('http') || plateImagePath.startsWith('data:') || plateImagePath.startsWith('/'))
      ? plateImagePath
      : null)

  function handleDownloadAsset() {
    const targetUrl =
      activeMediaTab === 'plate' && plateSrc
        ? plateSrc
        : vehicleSrc
    if (!targetUrl) return
    const link = document.createElement('a')
    link.href = targetUrl
    link.download = `${row.id || 'capture'}_${activeMediaTab}_${row.vehicleType || 'vehicle'}.jpg`
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
  }

  function handleZoom(delta) {
    setZoomLevel((prev) => Math.min(2.5, Math.max(0.75, +(prev + delta).toFixed(2))))
  }

  function handleResetZoom() {
    setZoomLevel(1)
  }

  const plateNumber = row.vehicleNumberPlate || row.numberPlate || 'Not Detected'
  const vehicleTypeLabel = row.vehicleType || row.type || 'Vehicle'

  return (
    <div className="media-modal-backdrop" onClick={onClose} role="dialog" aria-modal="true">
      <div
        className="media-modal-container media-modal-natural"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Modern Clean Header */}
        <div className="media-natural-header">
          <div className="media-natural-title-col">
            <div className="media-natural-meta-tags">
              <span className="natural-tag tag-event">Detection Event</span>
              <span className="natural-tag tag-id">#{row.id || row.observationId || 'Capture'}</span>
              <span className="natural-tag tag-type">
                <VehicleTypeIcon type={vehicleTypeLabel} size={13} />
                <span>{vehicleTypeLabel}</span>
              </span>
              {row.hasExtractedImage && (
                <span className="natural-tag tag-source">
                  <FileSpreadsheet size={12} />
                  <span>Excel Source</span>
                </span>
              )}
            </div>

            <div className="media-natural-heading-row">
              <h2>
                <span className="vehicle-class-name">{vehicleTypeLabel}</span>
                <span className="heading-sep">—</span>
                <span className="plate-highlight">{plateNumber}</span>
              </h2>
            </div>

            <div className="media-natural-subline">
              <span className="subline-item">
                <Clock size={12} />
                <span>{formatTimestampIst(row)}</span>
              </span>
              <span className="subline-dot">·</span>
              <span className="subline-item">
                <MapPin size={12} />
                <span>
                  {row.roadName || row.location || 'Corridor Camera Point'}
                  {row.latitude && row.longitude ? ` (${row.latitude.toFixed(4)}°N, ${row.longitude.toFixed(4)}°E)` : ''}
                </span>
              </span>
            </div>
          </div>

          <div className="media-natural-header-actions">
            {allRows.length > 1 && (
              <div className="media-nav-stepper">
                <button
                  className="media-stepper-btn"
                  disabled={currentIndex <= 0}
                  onClick={() => navigateRow(-1)}
                  title={currentIndex <= 0 ? 'First record' : 'Previous record (Left Arrow)'}
                  type="button"
                >
                  <ChevronLeft size={16} />
                </button>
                <span className="media-stepper-counter">
                  {currentIndex >= 0 ? currentIndex + 1 : 1} / {allRows.length}
                </span>
                <button
                  className="media-stepper-btn"
                  disabled={currentIndex >= allRows.length - 1}
                  onClick={() => navigateRow(1)}
                  title={currentIndex >= allRows.length - 1 ? 'Last record' : 'Next record (Right Arrow)'}
                  type="button"
                >
                  <ChevronRight size={16} />
                </button>
              </div>
            )}

            <button
              className="media-modal-close-btn"
              onClick={onClose}
              title="Close (Esc)"
              type="button"
            >
              <X size={18} />
            </button>
          </div>
        </div>

        <div className="media-natural-body">
          {/* Clean 3-Tab Media Switcher */}
          <div className="media-natural-tabs">
            <button
              className={`media-tab-card ${activeMediaTab === 'vehicle' ? 'is-active' : ''}`}
              onClick={() => setActiveMediaTab('vehicle')}
              type="button"
            >
              <div className="tab-icon-wrap icon-cyan">
                <ImageIcon size={18} />
              </div>
              <div className="tab-meta-col">
                <span className="tab-kicker">VEHICLE CAPTURE</span>
                <strong className="tab-filename" title={vehicleImagePath}>
                  {getBasename(vehicleImagePath || 'vehicle_snapshot.jpg')}
                </strong>
                <span className="tab-status-text">Optical Inspection</span>
              </div>
              <span className="tab-active-indicator" />
            </button>

            <button
              className={`media-tab-card ${activeMediaTab === 'plate' ? 'is-active' : ''}`}
              onClick={() => setActiveMediaTab('plate')}
              type="button"
            >
              <div className="tab-icon-wrap icon-emerald">
                <Eye size={18} />
              </div>
              <div className="tab-meta-col">
                <span className="tab-kicker">LICENSE PLATE ANPR</span>
                <strong className="tab-filename" title={plateImagePath}>
                  {plateSrc ? getBasename(plateImagePath) : 'ANPR Recognition'}
                </strong>
                <span className="tab-status-text">{plateConfidencePercent}% Confidence</span>
              </div>
              <span className="tab-active-indicator" />
            </button>

            <button
              className={`media-tab-card ${activeMediaTab === 'video' ? 'is-active' : ''}`}
              onClick={() => setActiveMediaTab('video')}
              type="button"
            >
              <div className="tab-icon-wrap icon-blue">
                <FileVideo size={18} />
              </div>
              <div className="tab-meta-col">
                <span className="tab-kicker">VIDEO RECORDING</span>
                <strong className="tab-filename" title={hasRealVideo ? rawVideo : 'No Video'}>
                  {hasRealVideo ? getBasename(rawVideo) : 'Snapshot Only'}
                </strong>
                <span className="tab-status-text">
                  {hasRealVideo ? 'Surveillance Stream' : 'Photo Captured'}
                </span>
              </div>
              <span className="tab-active-indicator" />
            </button>
          </div>

          {/* Clean Source Info Bar */}
          <div className="media-natural-source-bar">
            <div className="source-uri-wrap">
              <span className="source-uri-tag">SOURCE URI</span>
              <code className="source-uri-text" title={currentActivePath}>
                {currentActivePath}
              </code>
            </div>

            <div className="source-actions-wrap">
              <button
                className="source-action-btn"
                onClick={handleCopyPath}
                title="Copy source path"
                type="button"
              >
                {copiedPath ? <Check color="#34d399" size={12} /> : <Copy size={12} />}
                <span>{copiedPath ? 'Copied' : 'Copy'}</span>
              </button>

              {currentActivePath && (currentActivePath.startsWith('http') || currentActivePath.startsWith('/')) && (
                <a
                  className="source-action-btn"
                  href={currentActivePath}
                  rel="noopener noreferrer"
                  target="_blank"
                  title="Open source file in new tab"
                >
                  <ExternalLink size={12} />
                  <span>Open ↗</span>
                </a>
              )}
            </div>
          </div>

          {/* Main Natural Viewport Area */}
          <div className="media-natural-viewport">
            {activeMediaTab === 'video' ? (
              /* TAB 3: VIDEO STREAM */
              hasRealVideo ? (
                <SurveillanceVideoPlayer
                  autoPlay={true}
                  row={row}
                  videoClipPath={videoUrl}
                />
              ) : (
                <div className="media-natural-video-standby">
                  <div className="standby-icon-circle">
                    <FileVideo size={36} />
                  </div>
                  <h3>No Video Clip Recorded</h3>
                  <p>
                    This telemetry observation was registered as an optical photo capture.
                    Continuous surveillance video was not attached or triggered for record #{row.id || 'N/A'}.
                  </p>
                  <button
                    className="standby-action-btn"
                    onClick={() => setActiveMediaTab('vehicle')}
                    type="button"
                  >
                    <ImageIcon size={15} />
                    <span>View Vehicle Capture Photo</span>
                  </button>
                </div>
              )
            ) : activeMediaTab === 'plate' ? (
              /* TAB 2: ANPR PLATE INSPECTION */
              <div className="media-natural-plate-view">
                {plateSrc ? (
                  /* If a dedicated plate image exists, show with ambient backdrop */
                  <div className="media-natural-frame">
                    <div
                      className="media-ambient-glow"
                      style={{ backgroundImage: `url(${plateSrc})` }}
                    />
                    <div
                      className="media-natural-stage"
                      style={{ transform: `scale(${zoomLevel})` }}
                    >
                      <img
                        alt={`License plate crop for ${plateNumber}`}
                        className="media-natural-plate-img"
                        onError={() => setPlateLoadError(true)}
                        src={plateSrc}
                      />
                    </div>
                  </div>
                ) : (
                  /* Realistic ANPR OCR Inspection Card with Authentic Plate Rendering */
                  <div className="anpr-natural-inspector-card">
                    <div className="anpr-card-header">
                      <div className="anpr-badge-row">
                        <span className="anpr-pill anpr-pill-verified">
                          <Check size={12} />
                          OCR Verified
                        </span>
                        <span className="anpr-pill anpr-pill-conf">
                          {plateConfidencePercent}% Recognition Confidence
                        </span>
                      </div>
                      <span className="anpr-camera-tag">
                        <Camera size={12} />
                        {row.camera || 'CAM-01'}
                      </span>
                    </div>

                    {/* Authentic High-Security Indian License Plate (HSRP) Rendering */}
                    <div className="hsrp-plate-container">
                      <div className="hsrp-plate-surface">
                        <div className="hsrp-ind-strip">
                          <div className="hsrp-chakra-symbol" />
                          <span className="hsrp-ind-text">IND</span>
                        </div>
                        <div className="hsrp-number-text">
                          {plateNumber}
                        </div>
                        <div className="hsrp-hologram-seal" />
                      </div>
                      <div className="hsrp-plate-caption">
                        High-Security Registration Plate (HSRP) Standard
                      </div>
                    </div>

                    {/* Structured Inspection Grid */}
                    <div className="anpr-details-grid">
                      <div className="anpr-metric-cell">
                        <span className="cell-label">Registration Plate</span>
                        <strong className="cell-value cell-highlight">{plateNumber}</strong>
                      </div>
                      <div className="anpr-metric-cell">
                        <span className="cell-label">Vehicle Classification</span>
                        <strong className="cell-value">{vehicleTypeLabel}</strong>
                      </div>
                      <div className="anpr-metric-cell">
                        <span className="cell-label">Speed Recorded</span>
                        <strong className={`cell-value ${isOverSpeed ? 'text-violation' : ''}`}>
                          {row.speed || 0} km/h {isOverSpeed && '(Overspeed)'}
                        </strong>
                      </div>
                      <div className="anpr-metric-cell">
                        <span className="cell-label">Capture Timestamp</span>
                        <strong className="cell-value">{formatTimestampIst(row)}</strong>
                      </div>
                      <div className="anpr-metric-cell cell-wide">
                        <span className="cell-label">Deployment Location</span>
                        <strong className="cell-value">{row.roadName || row.location || 'Corridor Point'}</strong>
                      </div>
                    </div>

                    <div className="anpr-card-footer">
                      <button
                        className="anpr-copy-btn"
                        onClick={handleCopyPlate}
                        type="button"
                      >
                        {copiedPlate ? <Check size={13} color="#34d399" /> : <Copy size={13} />}
                        <span>{copiedPlate ? 'Plate Number Copied' : 'Copy Plate Number'}</span>
                      </button>
                      <button
                        className="anpr-switch-btn"
                        onClick={() => setActiveMediaTab('vehicle')}
                        type="button"
                      >
                        <ImageIcon size={13} />
                        <span>Inspect Full Photo</span>
                      </button>
                    </div>
                  </div>
                )}
              </div>
            ) : (
              /* TAB 1: VEHICLE CAPTURE PHOTO */
              <div className="media-natural-frame">
                {vehicleSrc ? (
                  <>
                    {/* Soft ambient blurred backdrop: blends vertical/aspect photos naturally */}
                    <div
                      className="media-ambient-glow"
                      style={{ backgroundImage: `url(${vehicleSrc})` }}
                    />

                    {/* Centered natural foreground photo */}
                    <div
                      className="media-natural-stage"
                      style={{ transform: `scale(${zoomLevel})` }}
                    >
                      <img
                        alt={`Vehicle capture #${row.id || 'obs'}`}
                        className="media-natural-img"
                        style={{ objectFit: fitMode, width: '100%', height: '100%', minHeight: '480px' }}
                        onError={() => setImgLoadError(true)}
                        src={vehicleSrc}
                      />
                    </div>

                    {/* Clean, Non-Intrusive Overlays (Toggleable) */}
                    {showOverlays && (
                      <div className="media-natural-overlays">
                        {/* Top-Left: Camera info */}
                        <div className="natural-chip chip-top-left">
                          <Camera size={13} />
                          <span>{row.camera || 'CAM-01'}</span>
                          <span className="chip-bullet">·</span>
                          <span>Optical Capture</span>
                        </div>

                        {/* Top-Right: Timestamp */}
                        <div className="natural-chip chip-top-right">
                          <Clock size={13} />
                          <span>{row.timestampIst || row.timestamp || 'Recorded'} IST</span>
                        </div>

                        {/* Bottom-Left: Target Identification */}
                        <div className="natural-chip chip-bottom-left">
                          <span className="chip-plate-tag">{plateNumber}</span>
                          <span className="chip-conf-tag">{plateConfidencePercent}% match</span>
                        </div>

                        {/* Bottom-Right: Speed & Limit */}
                        <div className={`natural-chip chip-bottom-right ${isOverSpeed ? 'is-overspeed' : ''}`}>
                          <Gauge size={13} />
                          <span>{row.speed || 0} km/h</span>
                          <span className="chip-bullet">/</span>
                          <span>Limit {row.speedLimit || 60} km/h</span>
                          {isOverSpeed && <span className="speed-alert-pill">OVERSPEED</span>}
                        </div>
                      </div>
                    )}
                  </>
                ) : (
                  <div className="media-natural-placeholder">
                    <ImageIcon size={44} />
                    <p>No optical capture asset available for target #{row.id || 'N/A'}</p>
                  </div>
                )}

              </div>
            )}
          </div>

          {/* Clean Natural Bottom Toolbar */}
          <div className="media-natural-bottom-bar">
            <div className="natural-bar-info">
              <span className="natural-status-badge">
                <span className="status-dot" />
                Verified Capture
              </span>
              <span className="info-sep">·</span>
              <span className="info-item">
                Class: <strong>{vehicleTypeLabel}</strong>
              </span>
              <span className="info-sep">·</span>
              <span className="info-item">
                Confidence: <strong>{plateConfidencePercent}%</strong>
              </span>
            </div>

            <div className="natural-bar-controls">
                            {/* Fill / Fit toggle */}
              {activeMediaTab === 'vehicle' && vehicleSrc && (
                <button
                  className={`natural-ctrl-btn ${fitMode === 'cover' ? 'btn-active' : ''}`}
                  onClick={() => setFitMode((m) => (m === 'cover' ? 'contain' : 'cover'))}
                  title={fitMode === 'cover' ? 'Filling complete box (click for fit aspect)' : 'Fitting aspect (click to fill complete box)'}
                  type="button"
                >
                  {fitMode === 'cover' ? <Minimize2 size={14} /> : <Maximize2 size={14} />}
                  <span>{fitMode === 'cover' ? 'Fill Box' : 'Fit Aspect'}</span>
                </button>
              )}

              {/* Toggle Overlays button */}
              {activeMediaTab === 'vehicle' && vehicleSrc && (
                <button
                  className={`natural-ctrl-btn ${!showOverlays ? 'btn-active' : ''}`}
                  onClick={() => setShowOverlays((v) => !v)}
                  title={showOverlays ? 'Hide overlay labels for clean view' : 'Show overlay labels'}
                  type="button"
                >
                  {showOverlays ? <EyeOff size={14} /> : <Eye size={14} />}
                  <span>{showOverlays ? 'Clean View' : 'Show Labels'}</span>
                </button>
              )}

              {/* Zoom controls */}
              {activeMediaTab === 'vehicle' && vehicleSrc && (
                <div className="natural-zoom-group">
                  <button
                    className="natural-ctrl-btn zoom-btn"
                    disabled={zoomLevel <= 0.75}
                    onClick={() => handleZoom(-0.25)}
                    title="Zoom Out"
                    type="button"
                  >
                    <ZoomOut size={14} />
                  </button>
                  <button
                    className="natural-ctrl-btn zoom-indicator"
                    onClick={handleResetZoom}
                    title="Reset Zoom to 100%"
                    type="button"
                  >
                    <span>{Math.round(zoomLevel * 100)}%</span>
                  </button>
                  <button
                    className="natural-ctrl-btn zoom-btn"
                    disabled={zoomLevel >= 2.5}
                    onClick={() => handleZoom(0.25)}
                    title="Zoom In"
                    type="button"
                  >
                    <ZoomIn size={14} />
                  </button>
                </div>
              )}

              {/* Download button */}
              <button
                className="natural-download-btn"
                onClick={handleDownloadAsset}
                title="Save high-resolution photo"
                type="button"
              >
                <Download size={14} />
                <span>Save Asset</span>
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
