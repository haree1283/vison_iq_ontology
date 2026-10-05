import Papa from 'papaparse'
import { getCanonicalVehicleDomain } from './vehicleTypes'

// Aliases covering the user's exact 14-column CSV format + legacy variations
const aliases = {
  id: [
    'id',
    'observation_id',
    'observation id',
    'obs_id',
    'record_id',
  ],
  timestamp: [
    'timestamp (ist)',
    'timestamp(ist)',
    'timestamp ist',
    'timestamp',
    'time',
    'datetime',
    'date_time',
    'detection_date',
  ],
  vehicleType: [
    'vehicle type',
    'vehicle_type',
    'object_type',
    'object type',
    'type',
    'object',
    'category',
    'class',
  ],
  numberPlate: [
    'vehicle number plate',
    'vehicle_number_plate',
    'number_plate',
    'number plate',
    'license_plate',
    'license plate',
    'plate',
    'registration',
    'plate_number',
  ],
  plateConfidence: [
    'plate confidence',
    'plate_confidence',
    'detection_confidence',
    'confidence',
    'score',
    'ocr_confidence',
  ],
  vehicleImage: [
    'vehicle image',
    'vehicle_image',
    'image',
    'car_image',
    'vehicle_snapshot',
  ],
  speed: [
    'speed (km/h)',
    'speed(km/h)',
    'speed_kmh',
    'speed kmh',
    'speed (kmph)',
    'speed',
    'velocity',
  ],
  speedLimit: [
    'speed limit (km/h)',
    'speed limit(km/h)',
    'speed_limit (km/h)',
    'speed_limit_kmh',
    'speed_limit',
    'speed limit',
    'limit',
    'posted_speed',
  ],
  overSpeed: [
    'over speed',
    'over_speed',
    'overspeed',
    'speed_violation',
    'violation',
    'is_overspeed',
  ],
  events: [
    'events',
    'event',
    'violation',
    'rule',
  ],
  latitude: [
    'latitude',
    'lat',
    'object_latitude',
    'gps_lat',
  ],
  longitude: [
    'longitude',
    'long',
    'lon',
    'lng',
    'object_longitude',
    'gps_lon',
  ],
  videoClipPath: [
    'video clip path',
    'video_clip_path',
    'vedio clip path',
    'vedio_clip_path',
    'video clip',
    'vedio clip',
    'video_path',
    'vedio_path',
    'video url',
    'video_url',
    'vedio url',
    'vedio_url',
    'videourl',
    'vediourl',
    'clip url',
    'clip_url',
    'video link',
    'videolink',
    'video_link',
    'clip_path',
    'clip',
    'videopath',
    'url',
    'video',
    'vedio',
    'media_url',
    'media url',
    'video_source',
    'source_url',
    'link',
  ],
  vehicleImagePath: [
    'vehicle image path',
    'vehicle_image_path',
    'vehicle_photo_path',
    'car_image_path',
    'image_path',
  ],
  plateImagePath: [
    'plate image path',
    'plate_image_path',
    'license_plate_image_path',
    'number_plate_image_path',
    'plate_photo_path',
  ],
  // Optional secondary / legacy fields
  camera: ['camera_id', 'camera id', 'camera', 'sensor', 'sensor_id'],
  junction: ['junction_id', 'junction id', 'junction', 'intersection'],
  location: ['road_name', 'road name', 'road', 'location', 'area', 'place'],
  date: ['date', 'detection_date'],
  time: ['time', 'timestamp'],
  timezone: ['timezone', 'tz'],
  cameraDirection: ['camera_direction', 'camera direction', 'direction', 'heading'],
  signalState: ['traffic_signal_state', 'traffic signal state', 'signal_state', 'signal', 'light'],
  bboxX: ['bbox_x', 'bbox x', 'x'],
  bboxY: ['bbox_y', 'bbox y', 'y'],
  bboxWidth: ['bbox_width', 'bbox width', 'width', 'w'],
  bboxHeight: ['bbox_height', 'bbox height', 'height', 'h'],
  distance: ['estimated_distance_m', 'estimated distance', 'distance_m', 'distance'],
  weather: ['weather', 'condition', 'weather_condition'],
  pedestrians: ['pedestrians', 'pedestrian_count', 'pedestrian count', 'people'],
  volume: ['volume', 'traffic_volume', 'traffic volume', 'count', 'vehicles'],
}

function cleanKey(str) {
  return String(str || '').toLowerCase().replace(/[^a-z0-9]/g, '')
}

function valueFor(row, candidates = []) {
  if (!row || typeof row !== 'object') return ''
  const rowKeys = Object.keys(row)

  // 1. Exact case-insensitive match
  const exactKey = rowKeys.find((k) =>
    candidates.some((c) => c.trim().toLowerCase() === k.trim().toLowerCase())
  )
  if (exactKey && row[exactKey] !== undefined && row[exactKey] !== null) {
    return row[exactKey] instanceof Date ? row[exactKey].toISOString() : String(row[exactKey]).trim()
  }

  // 2. Alphanumeric match ignoring spaces, brackets, slashes
  const cleanedCandidates = candidates.map(cleanKey)
  const fuzzyKey = rowKeys.find((k) => cleanedCandidates.includes(cleanKey(k)))
  if (fuzzyKey && row[fuzzyKey] !== undefined && row[fuzzyKey] !== null) {
    return row[fuzzyKey] instanceof Date ? row[fuzzyKey].toISOString() : String(row[fuzzyKey]).trim()
  }

  return ''
}

function numberOrFallback(value, fallback) {
  if (value === undefined || value === null || value === '') return fallback
  const number = Number.parseFloat(String(value).replace(/,/g, ''))
  return Number.isFinite(number) ? number : fallback
}

export function generateSurveillanceSvgDataUrl(row, index = 0) {
  const type = row.vehicleType || row.type || 'Vehicle'
  const plate = row.vehicleNumberPlate || row.numberPlate || 'N/A'
  const speed = row.speed !== undefined ? row.speed : 50
  const speedLimit = row.speedLimit !== undefined ? row.speedLimit : 60
  const isOverSpeed = row.overSpeed === 'Yes' || row.isOverSpeed || speed > speedLimit
  const timestamp = row.timestampIst || row.timestamp || '08:12:14 IST'
  const camera = row.camera || `CAM-HYD-${String((index % 8) + 1).padStart(3, '0')}-N`
  const conf = Math.round(
    (row.plateConfidence || row.confidence || 0.95) > 1
      ? row.plateConfidence || row.confidence
      : (row.plateConfidence || row.confidence || 0.95) * 100
  )

  const boxColor = isOverSpeed ? '#ef4444' : '#10b981'
  const typeColorMap = {
    Car: '#2563eb',
    Bike: '#ea580c',
    Auto: '#d97706',
    Bus: '#0d9488',
    Truck: '#7c3aed',
    Tractor: '#65a30d',
    Jeep: '#4f46e5',
    Van: '#0284c7',
    Train: '#e11d48',
    Pedestrians: '#ec4899',
  }
  const typeColor = typeColorMap[type] || '#3b82f6'

  const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 320 200" width="320" height="200">
    <defs>
      <linearGradient id="bgGrad_${index}" x1="0%" y1="0%" x2="0%" y2="100%">
        <stop offset="0%" stop-color="#0f172a" />
        <stop offset="100%" stop-color="#1e293b" />
      </linearGradient>
      <linearGradient id="vehGrad_${index}" x1="0%" y1="0%" x2="100%" y2="100%">
        <stop offset="0%" stop-color="${typeColor}" />
        <stop offset="100%" stop-color="#090d16" />
      </linearGradient>
    </defs>
    <rect width="320" height="200" fill="url(#bgGrad_${index})" />
    <line x1="50" y1="30" x2="10" y2="180" stroke="#334155" stroke-width="1.5" />
    <line x1="270" y1="30" x2="310" y2="180" stroke="#334155" stroke-width="1.5" />
    <line x1="160" y1="30" x2="160" y2="180" stroke="#eab308" stroke-dasharray="8 6" stroke-width="1.5" opacity="0.6" />
    <rect x="100" y="60" width="120" height="75" rx="8" fill="url(#vehGrad_${index})" stroke="#475569" stroke-width="1" />
    <rect x="115" y="70" width="90" height="24" rx="4" fill="#090d16" opacity="0.85" />
    <circle cx="112" cy="118" r="6" fill="#fef08a" opacity="0.9" />
    <circle cx="208" cy="118" r="6" fill="#fef08a" opacity="0.9" />
    <rect x="135" y="115" width="50" height="12" rx="2" fill="#ffffff" />
    <text x="160" y="124" font-size="7" font-family="monospace" font-weight="bold" fill="#0f172a" text-anchor="middle">${plate}</text>
    <rect x="92" y="52" width="136" height="92" fill="none" stroke="${boxColor}" stroke-width="2" stroke-dasharray="4 2" />
    <path d="M 88 64 L 88 48 L 104 48" fill="none" stroke="${boxColor}" stroke-width="2.5" />
    <path d="M 232 48 L 248 48 L 248 64" fill="none" stroke="${boxColor}" stroke-width="2.5" />
    <path d="M 88 132 L 88 148 L 104 148" fill="none" stroke="${boxColor}" stroke-width="2.5" />
    <path d="M 232 148 L 248 148 L 248 132" fill="none" stroke="${boxColor}" stroke-width="2.5" />
    <rect x="92" y="38" width="115" height="14" rx="3" fill="${boxColor}" />
    <text x="96" y="48" font-size="8" font-family="sans-serif" font-weight="bold" fill="#ffffff">${type.toUpperCase()} · ${conf}%</text>
    <rect x="0" y="0" width="320" height="22" fill="#090d16" opacity="0.95" />
    <circle cx="12" cy="11" r="4" fill="#ef4444" />
    <text x="22" y="14" font-size="8" font-family="monospace" font-weight="bold" fill="#ffffff">REC</text>
    <text x="50" y="14" font-size="8" font-family="monospace" fill="#94a3b8">${camera}</text>
    <text x="310" y="14" font-size="8" font-family="monospace" fill="#38bdf8" text-anchor="end">1080P · 60FPS</text>
    <rect x="0" y="178" width="320" height="22" fill="#090d16" opacity="0.95" />
    <text x="10" y="192" font-size="8" font-family="monospace" fill="#cbd5e1">${timestamp}</text>
    <rect x="235" y="181" width="75" height="16" rx="3" fill="${boxColor}" />
    <text x="272" y="192" font-size="8" font-family="monospace" font-weight="bold" fill="#ffffff" text-anchor="middle">${speed} / ${speedLimit} km/h</text>
  </svg>`

  return 'data:image/svg+xml;utf8,' + encodeURIComponent(svg)
}

export async function extractImagesFromXlsx(arrayBuffer) {
  try {
    const { default: JSZip } = await import('jszip') // loaded only when a spreadsheet is imported
    const zip = await JSZip.loadAsync(arrayBuffer)

    // 1. Collect all media files in the archive regardless of directory casing or folder depth
    const mediaMap = {}
    const allImages = []
    const imageExtensions = ['.png', '.jpg', '.jpeg', '.webp', '.gif', '.bmp', '.svg', '.tiff', '.tif', '.jfif', '.heic', '.avif']

    // Sort entries to maintain natural numeric order (image1, image2, ..., image10)
    const sortedFilePaths = Object.keys(zip.files).sort((a, b) =>
      a.localeCompare(b, undefined, { numeric: true, sensitivity: 'base' })
    )

    for (const filePath of sortedFilePaths) {
      const zipEntry = zip.files[filePath]
      if (!zipEntry || zipEntry.dir) continue
      const lower = filePath.toLowerCase()
      const hasImageExt = imageExtensions.some((ext) => lower.endsWith(ext))

      if (hasImageExt) {
        const ext = lower.split('.').pop()
        const mime =
          ext === 'png'
            ? 'image/png'
            : ext === 'jpg' || ext === 'jpeg'
            ? 'image/jpeg'
            : ext === 'webp'
            ? 'image/webp'
            : ext === 'gif'
            ? 'image/gif'
            : ext === 'bmp'
            ? 'image/bmp'
            : ext === 'svg'
            ? 'image/svg+xml'
            : 'image/png'

        const base64 = await zipEntry.async('base64')
        const dataUrl = `data:${mime};base64,${base64}`
        const fileName = filePath.split('/').pop()

        const mediaObj = {
          path: filePath,
          fileName,
          name: fileName,
          mime,
          dataUrl,
        }

        mediaMap[filePath] = mediaObj
        mediaMap[fileName] = mediaObj
        mediaMap[fileName.toLowerCase()] = mediaObj
        mediaMap[filePath.toLowerCase()] = mediaObj
        mediaMap[`../media/${fileName}`] = mediaObj
        mediaMap[`media/${fileName}`] = mediaObj
        mediaMap[`xl/media/${fileName}`] = mediaObj
        mediaMap[`/xl/media/${fileName}`] = mediaObj
        mediaMap[`/xl/media/${fileName.toLowerCase()}`] = mediaObj
        allImages.push(mediaObj)
      }
    }

    if (allImages.length === 0) {
      return { imagesByRow: {}, allImages: [] }
    }

    // 2. Parse relationship files (.rels) robustly regardless of attribute ordering
    const relsMap = {}
    for (const [filePath, zipEntry] of Object.entries(zip.files)) {
      const lower = filePath.toLowerCase()
      if (lower.endsWith('.rels')) {
        try {
          const xmlText = await zipEntry.async('text')
          const rels = {}
          const relTagRegex = /<Relationship\b([^>]*)\/?>/gi
          let rm
          while ((rm = relTagRegex.exec(xmlText)) !== null) {
            const attrs = rm[1]
            const id = attrs.match(/\bId="([^"]+)"/i)?.[1]
            const target = attrs.match(/\bTarget="([^"]+)"/i)?.[1]
            if (id && target) {
              const baseName = target.split('/').pop()
              const mediaMatch =
                mediaMap[target] ||
                mediaMap[target.toLowerCase()] ||
                mediaMap[baseName] ||
                mediaMap[baseName.toLowerCase()] ||
                mediaMap[`xl/media/${baseName}`] ||
                mediaMap[`/xl/media/${baseName}`] ||
                mediaMap[`../media/${baseName}`]
              if (mediaMatch) {
                rels[id] = mediaMatch
              }
            }
          }
          relsMap[filePath] = rels
          const baseRelName = filePath.split('/').pop()
          relsMap[baseRelName] = rels
        } catch {
          // ignore xml parse errors
        }
      }
    }

    const imagesByRow = {}

    // 3. Parse drawings XML (xl/drawings/drawing*.xml)
    for (const [filePath, zipEntry] of Object.entries(zip.files)) {
      const lower = filePath.toLowerCase()
      if (lower.includes('drawing') && lower.endsWith('.xml') && !lower.endsWith('.rels')) {
        try {
          const xmlText = await zipEntry.async('text')
          const baseName = filePath.split('/').pop()
          const rels =
            relsMap[`xl/drawings/_rels/${baseName}.rels`] ||
            relsMap[`${baseName}.rels`] ||
            relsMap[Object.keys(relsMap).find((k) => k.includes(baseName))] ||
            {}

          // Match anchors: twoCellAnchor, oneCellAnchor, absoluteAnchor
          const anchorRegex =
            /<(?:[a-zA-Z0-9_-]+:)?(?:twoCellAnchor|oneCellAnchor)[^>]*>([\s\S]*?)<\/(?:[a-zA-Z0-9_-]+:)?(?:twoCellAnchor|oneCellAnchor)>/gi
          let anchorMatch
          while ((anchorMatch = anchorRegex.exec(xmlText)) !== null) {
            const content = anchorMatch[1]
            // Extract row from the <from> coordinate
            const fromMatch = content.match(/<(?:[a-zA-Z0-9_-]+:)?from[^>]*>([\s\S]*?)<\/(?:[a-zA-Z0-9_-]+:)?from>/i)
            const rowStr = fromMatch ? fromMatch[1].match(/<(?:[a-zA-Z0-9_-]+:)?row>(\d+)<\/(?:[a-zA-Z0-9_-]+:)?row>/i)?.[1] : null

            // Extract embed / link attribute specifically from <a:blip> (avoid matching <cNvPr id="...">)
            const blipTagMatch = content.match(/<[^>]*:?blip\b([^>]*)\/?>/i)
            const blipAttrs = blipTagMatch ? blipTagMatch[1] : content
            const rId =
              blipAttrs.match(/\b(?:[a-zA-Z0-9_-]+:)?embed="([^"]+)"/i)?.[1] ||
              blipAttrs.match(/\b(?:[a-zA-Z0-9_-]+:)?link="([^"]+)"/i)?.[1]

            if (rowStr && rId) {
              const excelRow = parseInt(rowStr, 10)
              const media = rels[rId] || mediaMap[rId]
              if (media) {
                // In Excel drawings, row 0 is usually header, so row 1 is data row 0
                if (excelRow >= 1) {
                  imagesByRow[excelRow - 1] = media
                }
                imagesByRow[excelRow] = media
              }
            }
          }
        } catch {
          // ignore
        }
      }
    }

    // 4. Parse modern Excel In-Cell Images (xl/cellimages.xml)
    for (const [filePath, zipEntry] of Object.entries(zip.files)) {
      const lower = filePath.toLowerCase()
      if (lower.includes('cellimage') && lower.endsWith('.xml') && !lower.endsWith('.rels')) {
        try {
          const xmlText = await zipEntry.async('text')
          const cellRelKey = Object.keys(relsMap).find((k) => k.toLowerCase().includes('cellimage'))
          const rels = cellRelKey ? relsMap[cellRelKey] : {}

          const blipMatches = xmlText.matchAll(/<[^>]*:?blip\b[^>]*\b(?:[a-zA-Z0-9_-]+:)?embed="([^"]+)"/gi)
          let cellImgIdx = 0
          for (const bm of blipMatches) {
            const rId = bm[1]
            const media = rels[rId] || mediaMap[rId]
            if (media && !imagesByRow[cellImgIdx]) {
              imagesByRow[cellImgIdx] = media
              cellImgIdx++
            }
          }
        } catch {
          // ignore
        }
      }
    }

    return {
      imagesByRow,
      allImages,
    }
  } catch (err) {
    console.warn('Failed to extract images from XLSX archive:', err)
    return { imagesByRow: {}, allImages: [] }
  }
}

export function normalizeTrafficData(rows, extractedMedia = null) {
  if (!Array.isArray(rows)) return []

  const mediaByRow = extractedMedia?.imagesByRow || {}
  const allMediaList = extractedMedia?.allImages || []

  return rows
    .filter((row) => row && Object.values(row).some(Boolean))
    .map((row, index) => {
      // 1. ID
      const rawId = valueFor(row, aliases.id)
      const id = rawId || `ID-${String(index + 1).padStart(4, '0')}`
      const observationId = id

      // 2. Timestamp (IST)
      const rawTimestamp = valueFor(row, aliases.timestamp) || ''
      const rawDate = valueFor(row, aliases.date)
      const rawTime = valueFor(row, aliases.time)

      let date = rawDate || '2026-09-11'
      let time = rawTime || ''
      let timestamp = rawTimestamp

      if (rawTimestamp) {
        const parts = rawTimestamp.split(/[\sT]+/)
        if (parts.length >= 2) {
          date = parts[0]
          time = parts[1]
        } else if (rawTimestamp.includes(':')) {
          time = rawTimestamp
        } else if (rawTimestamp.includes('-') || rawTimestamp.includes('/')) {
          date = rawTimestamp
        }
      }
      const numericTimestamp = Number(rawTimestamp)
      if (Number.isFinite(numericTimestamp) && numericTimestamp > 1 && numericTimestamp < 100000) {
        const excelDate = new Date(Date.UTC(1899, 11, 30) + numericTimestamp * 86400000)
        date = `${excelDate.getUTCFullYear()}-${String(excelDate.getUTCMonth() + 1).padStart(2, '0')}-${String(excelDate.getUTCDate()).padStart(2, '0')}`
        time = `${String(excelDate.getUTCHours()).padStart(2, '0')}:${String(excelDate.getUTCMinutes()).padStart(2, '0')}:${String(excelDate.getUTCSeconds()).padStart(2, '0')}`
      }
      const numericTime = Number(rawTime)
      if (!time && Number.isFinite(numericTime) && numericTime >= 0 && numericTime < 1) {
        const totalSeconds = Math.round(numericTime * 86400) % 86400
        time = `${String(Math.floor(totalSeconds / 3600)).padStart(2, '0')}:${String(Math.floor((totalSeconds % 3600) / 60)).padStart(2, '0')}:${String(totalSeconds % 60).padStart(2, '0')}`
      }
      if (!time) {
        time = `08:${String(12 + (Math.floor(index * 1.2) % 48)).padStart(2, '0')}:${String((index * 17) % 60).padStart(2, '0')}`
      }
      if (!timestamp) {
        timestamp = `${date} ${time}`
      }

      // 3. Vehicle Type
      const rawType = valueFor(row, aliases.vehicleType) || 'Car'
      const type = getCanonicalVehicleDomain(rawType)
      const vehicleType = type

      // 4. Vehicle Number Plate
      const rawNumberPlate = valueFor(row, aliases.numberPlate)
      const isPed =
        type.toLowerCase().includes('pedestrian') || type.toLowerCase().includes('edisetrain')
      const isTrain = type.toLowerCase().includes('train') || type.toLowerCase().includes('rail')
      const numberPlate =
        rawNumberPlate ||
        (isPed || isTrain
          ? 'N/A'
          : `TS 09 ${String.fromCharCode(65 + (index % 26))}${String.fromCharCode(66 + (index % 25))} ${1000 + ((index * 137) % 8999)}`)
      const vehicleNumberPlate = numberPlate

      // 5. Plate Confidence
      const rawPlateConf = valueFor(row, aliases.plateConfidence)
      let plateConfidence = rawPlateConf !== '' ? numberOrFallback(rawPlateConf, 0.95) : 0.95
      if (plateConfidence > 1 && plateConfidence <= 100) {
        plateConfidence = Number((plateConfidence / 100).toFixed(2))
      }
      const confidence = plateConfidence

      // 6. Extracted Image resolution from Excel archive or direct cell data
      let extractedImage = row.extractedImage || null
      let hasExtractedImage = Boolean(row.hasExtractedImage)
      let extractedImageName = row.extractedImageName || null

      // Check if any cell in this row contains base64 image data
      if (!extractedImage) {
        for (const val of Object.values(row)) {
          if (typeof val === 'string') {
            const s = val.trim()
            if (s.startsWith('data:image/')) {
              extractedImage = s
              hasExtractedImage = true
              break
            }
            if (s.length > 80 && /^[A-Za-z0-9+/=]+$/.test(s.slice(0, 80))) {
              if (s.startsWith('iVBORw0KGgo')) {
                extractedImage = `data:image/png;base64,${s}`
                hasExtractedImage = true
                break
              } else if (s.startsWith('/9j/')) {
                extractedImage = `data:image/jpeg;base64,${s}`
                hasExtractedImage = true
                break
              }
            }
          }
        }
      }

      if (!extractedImage && extractedMedia) {
        // Priority 1: Match by drawing anchor row (check index and index+1 for 0/1-offset)
        if (mediaByRow[index]) {
          extractedImage = mediaByRow[index].dataUrl
          hasExtractedImage = true
          extractedImageName = mediaByRow[index].fileName
        } else if (mediaByRow[index + 1]) {
          extractedImage = mediaByRow[index + 1].dataUrl
          hasExtractedImage = true
          extractedImageName = mediaByRow[index + 1].fileName
        } else if (index > 0 && mediaByRow[index - 1]) {
          extractedImage = mediaByRow[index - 1].dataUrl
          hasExtractedImage = true
          extractedImageName = mediaByRow[index - 1].fileName
        }

        // Priority 2: Match if any cell in the row mentions the image filename
        if (!extractedImage && allMediaList.length > 0) {
          const allCellTexts = Object.values(row).map((v) => String(v || '').toLowerCase())
          const match = allMediaList.find((img) => {
            const name = (img.fileName || img.name || '').toLowerCase()
            const baseName = name.replace(/\.[^.]+$/, '')
            return allCellTexts.some((txt) => txt.includes(name) || (baseName.length >= 3 && txt.includes(baseName)))
          })
          if (match) {
            extractedImage = match.dataUrl
            hasExtractedImage = true
            extractedImageName = match.fileName
          }
        }

        // Priority 3: Single image in workbook -> assign to all rows
        if (!extractedImage && allMediaList.length === 1) {
          extractedImage = allMediaList[0].dataUrl
          hasExtractedImage = true
          extractedImageName = allMediaList[0].fileName
        }

        // Priority 4: Sequential matching to images extracted from Excel archive
        if (!extractedImage && allMediaList.length > 0) {
          const seq = allMediaList[index] || allMediaList[index % allMediaList.length]
          if (seq) {
            extractedImage = seq.dataUrl
            hasExtractedImage = true
            extractedImageName = seq.fileName
          }
        }
      }

      const rawVehicleImage = valueFor(row, aliases.vehicleImage)
      const vehicleImage =
        rawVehicleImage ||
        extractedImageName ||
        `veh_obs_${String(index + 1).padStart(4, '0')}.jpg`

      // 7. Speed (km/h)
      const rawSpeed = valueFor(row, aliases.speed)
      const speed = rawSpeed !== '' ? numberOrFallback(rawSpeed, 45 + ((index * 7) % 45)) : 45 + ((index * 7) % 45)

      // 8. Speed Limit (km/h)
      const rawSpeedLimit = valueFor(row, aliases.speedLimit)
      const speedLimit = rawSpeedLimit !== '' ? numberOrFallback(rawSpeedLimit, 60) : 60

      // 9. Over Speed
      const rawOverSpeed = valueFor(row, aliases.overSpeed).trim().toLowerCase()
      let overSpeed = 'No'
      if (rawOverSpeed) {
        if (['yes', 'true', '1', 'y', 'violation', 'overspeed'].includes(rawOverSpeed)) {
          overSpeed = 'Yes'
        } else if (['no', 'false', '0', 'n'].includes(rawOverSpeed)) {
          overSpeed = 'No'
        } else {
          overSpeed = speed > speedLimit ? 'Yes' : 'No'
        }
      } else {
        overSpeed = speed > speedLimit ? 'Yes' : 'No'
      }
      const isOverSpeed = overSpeed === 'Yes'

      // 10. Latitude & 11. Longitude
      const rawLat = valueFor(row, aliases.latitude)
      const rawLng = valueFor(row, aliases.longitude)
      const latitude = rawLat !== '' ? numberOrFallback(rawLat, 17.4485 + ((index % 5) * 0.005)) : 17.4485 + ((index % 5) * 0.005)
      const longitude = rawLng !== '' ? numberOrFallback(rawLng, 78.3742 + ((index % 5) * 0.004)) : 78.3742 + ((index % 5) * 0.004)

      // 12. Video Clip Path / Video URL (Supports any direct URL, YouTube, Vimeo, Google Drive, or file path)
      let videoClipPath = valueFor(row, aliases.videoClipPath)
      if (!videoClipPath) {
        // Fallback 1: Any key containing 'video', 'vedio', 'clip', 'url', 'link'
        const rowKeys = Object.keys(row || {})
        const matchKey = rowKeys.find((k) => {
          const lk = k.toLowerCase().replace(/[^a-z0-9]/g, '')
          return (
            lk.includes('video') ||
            lk.includes('vedio') ||
            lk.includes('clip') ||
            lk === 'url' ||
            lk.includes('videourl') ||
            lk.includes('link')
          )
        })
        if (matchKey && row[matchKey]) {
          videoClipPath = String(row[matchKey]).trim()
        }
      }
      if (!videoClipPath) {
        // Fallback 2: Any string value in the row that looks like an HTTP/HTTPS URL or video file
        const foundUrl = Object.values(row || {}).find((val) => {
          if (typeof val !== 'string') return false
          const s = val.trim().toLowerCase()
          return (
            s.startsWith('http://') ||
            s.startsWith('https://') ||
            s.includes('youtube.com') ||
            s.includes('youtu.be') ||
            s.includes('.mp4') ||
            s.includes('.webm')
          )
        })
        if (foundUrl) {
          videoClipPath = String(foundUrl).trim()
        }
      }
      // 13. Vehicle Image Path
      const vehicleImagePath = valueFor(row, aliases.vehicleImagePath)

      // 14. Plate Image Path
      const plateImagePath = valueFor(row, aliases.plateImagePath)

      // Derived & backward-compatible context
      const roadName =
        valueFor(row, aliases.location) ||
        `Outer Corridor Sector ${((index % 6) + 1)}`
      const junctionId = valueFor(row, aliases.junction) || `JNC-${String((index % 12) + 1).padStart(2, '0')}`
      const camera = valueFor(row, aliases.camera) || `CAM-HYD-${String((index % 8) + 1).padStart(3, '0')}-N`
      const cameraDirection =
        valueFor(row, aliases.cameraDirection) ||
        (camera.endsWith('-N') ? 'North' : camera.endsWith('-S') ? 'South' : camera.endsWith('-E') ? 'East' : 'West')
      const signalState =
        valueFor(row, aliases.signalState) ||
        (isOverSpeed ? 'Red' : index % 3 === 0 ? 'Green' : index % 3 === 1 ? 'Yellow' : 'Green')
      const weather =
        valueFor(row, aliases.weather) ||
        (index % 4 === 3 ? 'Rainy' : index % 4 === 2 ? 'Sunny' : index % 4 === 1 ? 'Overcast' : 'Clear')
      const timezone = valueFor(row, aliases.timezone) || 'IST'

      const rawVolume = valueFor(row, aliases.volume)
      const rawPeds = valueFor(row, aliases.pedestrians)
      const volume = rawVolume !== '' ? numberOrFallback(rawVolume, 1) : 1
      const pedestrians = rawPeds !== '' ? numberOrFallback(rawPeds, isPed ? 1 : 0) : (isPed ? 1 : 0)

      // Generate a high-fidelity synthetic optical CCTV surveillance graphic
      const syntheticImageDataUrl = generateSurveillanceSvgDataUrl(
        {
          id,
          vehicleType,
          type,
          vehicleNumberPlate,
          numberPlate,
          speed,
          speedLimit,
          overSpeed,
          isOverSpeed,
          plateConfidence,
          timestampIst: timestamp,
          camera,
        },
        index
      )

      // Guaranteed image data URL: Real extracted image from Excel has highest priority,
      // followed by any explicit base64 data URL, followed by guaranteed synthetic SVG.
      const vehicleImageDataUrl =
        extractedImage ||
        (rawVehicleImage && rawVehicleImage.startsWith('data:image') ? rawVehicleImage : null) ||
        (vehicleImagePath && vehicleImagePath.startsWith('data:image') ? vehicleImagePath : null) ||
        row.vehicleImageDataUrl ||
        syntheticImageDataUrl

      return {
        // Exact 14 CSV parameters
        id,
        observationId,
        timestampIst: timestamp,
        timestamp,
        vehicleType,
        type,
        vehicleNumberPlate,
        numberPlate,
        plateConfidence,
        confidence,
        vehicleImage,
        speed,
        speedLimit,
        overSpeed,
        isOverSpeed,
        latitude,
        longitude,
        videoClipPath,
        vehicleImagePath,
        plateImagePath,
        events: valueFor(row, aliases.events),

        // Extracted media attributes
        extractedImage,
        hasExtractedImage,
        extractedImageName,
        syntheticImageDataUrl,
        vehicleImageDataUrl,

        // Supporting / legacy telemetry properties
        camera,
        junctionId,
        roadName,
        location: roadName,
        date,
        time,
        timezone,
        cameraDirection,
        signalState,
        weather,
        volume,
        pedestrians,
        bboxX: numberOrFallback(valueFor(row, aliases.bboxX), 120),
        bboxY: numberOrFallback(valueFor(row, aliases.bboxY), 340),
        bboxWidth: numberOrFallback(valueFor(row, aliases.bboxWidth), 180),
        bboxHeight: numberOrFallback(valueFor(row, aliases.bboxHeight), 140),
        distance: numberOrFallback(valueFor(row, aliases.distance), 18.0),
      }
    })
}

export function parseTrafficDataFile(file) {
  const fileName = (file.name || '').toLowerCase()
  const isExcel =
    fileName.endsWith('.xlsx') ||
    fileName.endsWith('.xls') ||
    (file.type &&
      (file.type.includes('spreadsheet') ||
        file.type.includes('excel') ||
        file.type.includes('officedocument')))

  if (isExcel) {
    return new Promise((resolve, reject) => {
      const reader = new FileReader()
      reader.onload = async (e) => {
        try {
          const buffer = e.target.result
          const data = new Uint8Array(buffer)
          const XLSX = await import('xlsx') // loaded only when a spreadsheet is imported
          const workbook = XLSX.read(data, { type: 'array', cellDates: true })
          let sheetName = workbook.SheetNames[0]
          if (!sheetName) {
            reject(new Error('The Excel workbook does not contain any sheets.'))
            return
          }
          let worksheet = workbook.Sheets[sheetName]
          let rows = XLSX.utils.sheet_to_json(worksheet, { defval: '' })

          // If first sheet is empty or an intro tab, find the sheet that actually contains rows
          if (!rows.length && workbook.SheetNames.length > 1) {
            for (const name of workbook.SheetNames) {
              const ws = workbook.Sheets[name]
              const candidate = XLSX.utils.sheet_to_json(ws, { defval: '' })
              if (candidate.length > 0) {
                sheetName = name
                worksheet = ws
                rows = candidate
                break
              }
            }
          }

          // Extract images embedded in the Excel archive (xl/media, drawings, anchors, cellimages)
          const extractedMedia = await extractImagesFromXlsx(buffer)
          const normalized = normalizeTrafficData(rows, extractedMedia)

          if (!normalized.length) {
            reject(new Error('The Excel sheet does not contain any valid data rows.'))
            return
          }

          for (const r of normalized) {
            r.sourceFile = file.name
            r.fileName = file.name
          }

          normalized.extractedMediaCount = extractedMedia.allImages?.length || 0
          resolve(normalized)
        } catch (error) {
          reject(new Error(error.message || 'Failed to read the Excel file.'))
        }
      }
      reader.onerror = () => reject(new Error('Unable to read the selected file.'))
      reader.readAsArrayBuffer(file)
    })
  }

  // Fallback to CSV parsing with PapaParse
  return new Promise((resolve, reject) => {
    Papa.parse(file, {
      header: true,
      skipEmptyLines: true,
      complete: ({ data, errors }) => {
        if (errors.length) {
          reject(new Error(errors[0].message || 'The CSV could not be read.'))
          return
        }
        const normalized = normalizeTrafficData(data)
        if (!normalized.length) {
          reject(new Error('The CSV does not contain any valid data rows.'))
          return
        }
        for (const r of normalized) {
          r.sourceFile = file.name
          r.fileName = file.name
        }
        resolve(normalized)
      },
      error: (error) => reject(error),
    })
  })
}

export const parseTrafficCsv = parseTrafficDataFile
export const parseTrafficFile = parseTrafficDataFile

export function summarizeData(rows = []) {
  const safeRows = Array.isArray(rows) ? rows : []
  const total = safeRows.reduce((sum, row) => sum + (row.volume || 1), 0)
  const pedestrians = safeRows.reduce((sum, row) => sum + (row.pedestrians || 0), 0)
  const uniqueLocations = new Set(safeRows.map((row) => row.location || row.roadName).filter(Boolean)).size
  const uniqueCameras = new Set(safeRows.map((row) => row.camera).filter(Boolean)).size
  return { total, pedestrians, uniqueLocations, uniqueCameras }
}

export function groupBy(rows = [], key) {
  const safeRows = Array.isArray(rows) ? rows : []
  return Object.entries(
    safeRows.reduce((groups, row) => {
      let value = row[key] || 'Unknown'
      if (key === 'type' || key === 'vehicleType') {
        value = getCanonicalVehicleDomain(value)
      }
      groups[value] = (groups[value] || 0) + (key === 'location' || key === 'roadName' ? row.volume || 1 : 1)
      return groups
    }, {})
  ).map(([name, value]) => ({ name, value }))
}

export function formatTimestampIst(row) {
  const rawValue = row?.timestampIst || row?.timestamp || ''
  const rawDate = row?.date || ''
  const rawTime = row?.time || ''
  const value = String(rawValue || '').trim()
  const source = value || `${rawDate} ${rawTime}`.trim()
  const numericTime = Number(rawTime)
  const normalizedRawTime = Number.isFinite(numericTime) && numericTime >= 0 && numericTime < 1
    ? `${String(Math.floor(numericTime * 24)).padStart(2, '0')}:${String(Math.floor((numericTime * 1440) % 60)).padStart(2, '0')}:${String(Math.floor((numericTime * 86400) % 60)).padStart(2, '0')}`
    : rawTime
  const ymdMatch = source.match(/(\d{4})[-/](\d{1,2})[-/](\d{1,2})/)
  const dmyMatch = source.match(/(\d{1,2})[-/](\d{1,2})[-/](\d{4})/)
  const timeMatch = `${source} ${normalizedRawTime}`.match(/(\d{1,2}):(\d{2})(?::(\d{2}))?\s*(AM|PM)?/i)
  let datePart = ''
  let timePart = ''

  if (ymdMatch || dmyMatch) {
    const dateMatch = ymdMatch || dmyMatch
    const year = ymdMatch ? Number(dateMatch[1]) : Number(dateMatch[3])
    const month = ymdMatch ? Number(dateMatch[2]) : Number(dateMatch[2])
    const day = ymdMatch ? Number(dateMatch[3]) : Number(dateMatch[1])
    datePart = `${String(day).padStart(2, '0')}/${String(month).padStart(2, '0')}/${year}`
  }

  if (timeMatch) {
    let hours = Number(timeMatch[1])
    const meridiem = timeMatch[4]?.toUpperCase()
    if (meridiem === 'PM' && hours < 12) hours += 12
    if (meridiem === 'AM' && hours === 12) hours = 0
    timePart = `${String(hours).padStart(2, '0')}:${timeMatch[2]}:${timeMatch[3] || '00'}`
  }

  if (!datePart && source) {
    const parsed = new Date(source)
    if (!Number.isNaN(parsed.getTime())) {
      datePart = `${String(parsed.getDate()).padStart(2, '0')}/${String(parsed.getMonth() + 1).padStart(2, '0')}/${parsed.getFullYear()}`
    }
  }

  return [datePart || '11/09/2026', timePart || '00:00:00', 'IST'].join(' ')
}