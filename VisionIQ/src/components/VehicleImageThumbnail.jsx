import React, { useEffect, useState } from 'react'
import { Eye, FileVideo, Image as ImageIcon, Play, Sparkles } from 'lucide-react'
import { generateSurveillanceSvgDataUrl } from '../data/dashboardData'

export default function VehicleImageThumbnail({
  row,
  onClick,
  onPlayVideo,
  size = 'table', // 'sm' | 'md' | 'lg' | 'table'
  showBadge = true,
}) {
  const [imageLoadError, setImageLoadError] = useState(false)
  if (!row) return null

  useEffect(() => {
    setImageLoadError(false)
  }, [row.id, row.observationId])

  const syntheticSvg =
    row.syntheticImageDataUrl ||
    (typeof row.vehicleImageDataUrl === 'string' && row.vehicleImageDataUrl.startsWith('data:image/svg')
      ? row.vehicleImageDataUrl
      : generateSurveillanceSvgDataUrl(row, 0))

  // Priority 1: Image directly extracted from Excel (.xlsx) archive
  // Priority 2: Direct URL or base64 image from CSV / Excel row (unless failed to load)
  // Priority 3: Generated surveillance telemetry graphic
  let directPath = null
  if (!imageLoadError) {
    const rawPath = row.vehicleImagePath || row.vehicleImage || ''
    if (rawPath) {
      if (rawPath.startsWith('http') || rawPath.startsWith('data:')) {
        directPath = rawPath
      } else if (rawPath.startsWith('/')) {
        directPath = rawPath
      } else if (rawPath.startsWith('images/')) {
        directPath = `/${rawPath}`
      } else if (rawPath.includes('.jp') || rawPath.includes('.png')) {
        directPath = `/images/${rawPath.replace(/^.*[\\/]/, '')}`
      }
    }
  }

  const imgSrc =
    row.extractedImage ||
    directPath ||
    (typeof row.vehicleImageDataUrl === 'string' && row.vehicleImageDataUrl.startsWith('data:')
      ? row.vehicleImageDataUrl
      : syntheticSvg)

  const hasExtracted = Boolean(row.hasExtractedImage || row.extractedImage)
  const hasVideo = Boolean(row.videoClipPath || row.videoUrl || row.video)

  const sizeClasses = {
    sm: 'veh-thumb-sm', // 44x30
    md: 'veh-thumb-md', // 56x38
    lg: 'veh-thumb-lg', // 76x50
    table: 'veh-thumb-table', // 100x64 (Large prominent table card)
  }

  return (
    <div
      className={`vehicle-image-thumb-wrap ${sizeClasses[size] || sizeClasses.table} ${
        hasExtracted ? 'has-xlsx-image' : ''
      }`}
      onClick={(e) => {
        e.stopPropagation()
        onClick?.(row)
      }}
      title={
        hasExtracted
          ? `Extracted from Excel (${row.extractedImageName || 'image.png'}) - Click to inspect media evidence`
          : `Vehicle Capture (${row.vehicleImage || 'Image'}) - Click to inspect media evidence`
      }
      role="button"
      tabIndex={0}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault()
          onClick?.(row)
        }
      }}
    >
      {(imgSrc || syntheticSvg) && !imageLoadError ? (
        <img
          alt={row.vehicleImage || 'Vehicle capture'}
          className="vehicle-image-thumb-img"
          loading="lazy"
          onError={(e) => {
            setImageLoadError(true)
            if (syntheticSvg && e.currentTarget.src !== syntheticSvg) {
              e.currentTarget.src = syntheticSvg
            }
          }}
          src={imgSrc || syntheticSvg}
        />
      ) : (
        <div className="vehicle-image-thumb-empty">
          <ImageIcon size={18} />
        </div>
      )}

      {/* Hover Overlay */}
      <div className="vehicle-thumb-hover-overlay">
        <Eye size={13} />
        <span>Inspect</span>
      </div>

      {/* XLSX Extracted Badge */}
      {showBadge && hasExtracted && (
        <span className="vehicle-thumb-xlsx-badge" title="Extracted from Excel .xlsx">
          <Sparkles size={8} />
        </span>
      )}

      {/* Video Clip Indicator Pill */}
      {hasVideo && (
        <span
          className="vehicle-thumb-video-badge"
          onClick={(e) => {
            if (onPlayVideo) {
              e.stopPropagation()
              onPlayVideo(row)
            }
          }}
          title={`Video Clip: ${row.videoClipPath} (Click to play)`}
        >
          <Play size={8} style={{ fill: '#ffffff' }} />
          <span>Clip</span>
        </span>
      )}
    </div>
  )
}
