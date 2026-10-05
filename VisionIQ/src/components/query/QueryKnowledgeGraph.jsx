import { useEffect, useMemo, useRef, useState } from 'react'
import cytoscape from 'cytoscape'
import {
  Activity,
  AlertTriangle,
  Camera,
  Car,
  ChevronDown,
  Eye,
  Filter,
  Layers,
  Lock,
  MapPin,
  Maximize,
  Minus,
  Network,
  Plus,
  Radio,
  RefreshCw,
  Search,
  ShieldAlert,
  ShieldCheck,
  Sparkles,
  Zap,
  X,
} from 'lucide-react'
import { getCanonicalVehicleDomain, getVehicleMeta } from '../../data/vehicleTypes'
import MediaPreviewModal from '../MediaPreviewModal'

export function buildCameraGraphSnapshot(focusedCamera, pool) {
  if (!focusedCamera) {
    return { currentNodes: [], currentEdges: [], stats: { cameras: 0, locations: 0, types: 0, observations: 0, totalQueried: 0 } }
  }

  const targetCamNorm = focusedCamera.toLowerCase().replace(/[^a-z0-9]/g, '')
  const camRows = (pool || []).filter((r) => {
    if (!r.camera) return false
    const rowCamNorm = r.camera.toLowerCase().replace(/[^a-z0-9]/g, '')
    return rowCamNorm === targetCamNorm || rowCamNorm.includes(targetCamNorm) || targetCamNorm.includes(rowCamNorm)
  })

  const loc = camRows[0]?.roadName || camRows[0]?.location || 'Outer Ring Road (NH-44 Expressway)'
  const overspeedCount = camRows.filter((r) => r.overSpeed === 'Yes' || r.isOverSpeed || (Number(r.speed) > Number(r.speedLimit || 60))).length
  const uniqueDomains = Array.from(new Set(camRows.map((r) => getCanonicalVehicleDomain(r.type || r.vehicleType)).filter(Boolean)))
  const defaultDomains = ['Car', 'Bike', 'Auto', 'Truck', 'Bus']
  const allDomains = Array.from(new Set([...uniqueDomains, ...defaultDomains]))

  const nodes = [
    // 1. Central Camera Anchor Node (Highlighted Radar Hub)
    {
      id: `cam-${focusedCamera}`,
      label: `Camera ${focusedCamera}`,
      category: 'Camera',
      color: '#0f172a',
      borderColor: '#10b981',
      isCenter: true,
      properties: {
        'Camera ID': focusedCamera,
        'Operational Status': '🟢 Live Telemetry Stream Active (Dynamic)',
        'Monitored Roadway': loc,
        'Surveillance Grid': 'Smart Traffic Surveillance Grid (NH-44)',
        'Traffic Signal Hub': `Adaptive Signal Hub #01 (${focusedCamera})`,
        'ANPR & Optical Sensor': 'Sony STARVIS™ 4K · 30 FPS · AI OCR Engine',
        'Configured Speed Limit': '60 km/h',
        'Coverage Zone': 'Northbound Express Corridor · Lanes 1-4',
        'Total Ingested Detections': camRows.length,
        'Speed Violations Logged': overspeedCount,
        'Stream Protocol': 'RTSP / Low-Latency WebSocket',
        'Sensor Coordinates': '17.4485° N, 78.3742° E',
        'Last Ingestion Heartbeat': new Date().toLocaleTimeString(),
      },
    },
    // 2. Monitored Roadway / Location Node
    {
      id: `loc-${loc}`,
      label: loc,
      category: 'Location',
      color: '#10b981',
      borderColor: '#ffffff',
      properties: {
        'Roadway Name': loc,
        'Monitored By': focusedCamera,
        'Corridor Type': 'Dual Carriageway National Expressway',
        'Active Lanes': '4 Lanes with Emergency Shoulder',
        'Speed Limit': '60 km/h',
        'Surveillance Status': '🟢 Active 24x7 Monitoring',
      },
    },
    // 3. Smart Surveillance Network / Command Grid Node
    {
      id: 'corridor-network',
      label: 'Traffic Command Grid (NH-44)',
      category: 'Network',
      color: '#0284c7',
      borderColor: '#ffffff',
      properties: {
        'Command Grid': 'Integrated Traffic Management Grid (ITMS)',
        'Central Operations': 'TMC Central Command Headquarters',
        'Primary Sensor Station': focusedCamera,
        'Backbone Network': 'High-Speed Optical Fiber Ring (10 Gbps)',
        'Telemetry Protocol': 'Real-Time Apache Kafka / WebSocket',
      },
    },
    // 4. Adaptive Traffic Signal Station Node
    {
      id: `signal-hub-${focusedCamera}`,
      label: 'Adaptive Signal Hub #01',
      category: 'Signal',
      color: '#f59e0b',
      borderColor: '#ffffff',
      properties: {
        'Signal Intersection': `Junction-01 (${focusedCamera} Interlock)`,
        'Controlled By': focusedCamera,
        'Cycle Timing': '90s Dynamic Adaptive Phase',
        'Current State': 'Dynamic Phasing (Green 45s)',
        'Red-Light Enforcement': '🟢 Automated OCR Cross-Reference Active',
      },
    },
    // 5. Automated Speed Enforcement Hub Node
    {
      id: 'violation-overspeed-hub',
      label: 'Speed Enforcement Hub',
      category: 'Violation',
      color: '#ef4444',
      borderColor: '#ffffff',
      properties: {
        'Enforcement Unit': focusedCamera,
        'Statutory Law': 'Section 183 Motor Vehicles Act',
        'Threshold Speed': '60 km/h (Strict Radar Enforcement)',
        'e-Challan Workflow': 'Automated High-Priority Issuance',
        'Total Violations Logged': overspeedCount,
      },
    },
  ]

  let edgeIndex = 1
  const edges = [
    // Camera Infrastructure Connections:
    { id: `edge-${edgeIndex++}`, source: `cam-${focusedCamera}`, target: `loc-${loc}`, label: 'MONITORS', color: '#10b981' },
    { id: `edge-${edgeIndex++}`, source: `cam-${focusedCamera}`, target: 'corridor-network', label: 'PART_OF_GRID', color: '#0284c7' },
    { id: `edge-${edgeIndex++}`, source: `cam-${focusedCamera}`, target: `signal-hub-${focusedCamera}`, label: 'CONTROLS_JUNCTION', color: '#f59e0b' },
    { id: `edge-${edgeIndex++}`, source: `cam-${focusedCamera}`, target: 'violation-overspeed-hub', label: 'ENFORCES_LIMIT', color: '#ef4444' },
  ]

  // Vehicle Type Domain Classification Nodes
  allDomains.forEach((dom) => {
    const meta = getVehicleMeta(dom)
    const countInDom = camRows.filter((r) => getCanonicalVehicleDomain(r.type || r.vehicleType) === dom).length
    nodes.push({
      id: `type-${dom}`,
      label: `${dom} Domain`,
      category: 'VehicleType',
      vehicleType: dom,
      color: meta.color,
      borderColor: '#ffffff',
      properties: {
        'Vehicle Domain': dom,
        'Classification Color': meta.color,
        'Monitored Sensor': focusedCamera,
        'Detections in Corridor': countInDom,
      },
    })
  })

  // Initial vehicle observation nodes captured by this camera
  const displayRows = camRows.slice(0, 25)
  displayRows.forEach((row, i) => {
    const obsId = row.observationId ? `obs-${row.observationId}` : `obs-${row.id || i + 1}`
    const obsLabel = (row.numberPlate && row.numberPlate !== 'N/A' && row.numberPlate !== 'Unknown')
      ? row.numberPlate
      : (row.observationId || row.id || `OBS-${i + 1}`)
    const domain = getCanonicalVehicleDomain(row.type || row.vehicleType)
    const meta = getVehicleMeta(domain)
    const isOver = row.overSpeed === 'Yes' || row.isOverSpeed || (Number(row.speed) > Number(row.speedLimit || 60))

    nodes.push({
      id: obsId,
      label: obsLabel,
      category: 'Observation',
      vehicleType: domain,
      color: meta.color,
      borderColor: isOver ? '#ef4444' : (meta.border || '#10b981'),
      image: row.extractedImage || row.vehicleImageDataUrl || row.vehicleImagePath || row.vehicleImage,
      hasExtractedImage: row.hasExtractedImage,
      rawRow: row,
      properties: {
        'Number Plate': obsLabel,
        'Vehicle Type': domain,
        'Captured By': focusedCamera,
        'Monitored Road': loc,
        'Speed': `${row.speed || 0} km/h`,
        'Speed Limit': `${row.speedLimit || 60} km/h`,
        'Violation Status': isOver ? '⚠️ Overspeed Violation' : 'Compliant',
        'Signal State': row.signalState || 'Green',
        'Timestamp (IST)': row.timestampIst || row.timestamp || 'N/A',
        'Plate Confidence': `${Math.round(((row.plateConfidence || row.confidence) > 1 ? (row.plateConfidence || row.confidence) : (row.plateConfidence || row.confidence || 0.95) * 100))}%`,
      },
    })

    // Edge 1: Vehicle -> Camera
    edges.push({
      id: `edge-${edgeIndex++}`,
      source: obsId,
      target: `cam-${focusedCamera}`,
      label: 'CAPTURED_BY',
      color: '#0284c7',
    })

    // Edge 2: Vehicle -> Domain
    edges.push({
      id: `edge-${edgeIndex++}`,
      source: obsId,
      target: `type-${domain}`,
      label: 'OF_TYPE',
      color: meta.color || '#94a3b8',
    })

    // Edge 3: Vehicle -> Location
    edges.push({
      id: `edge-${edgeIndex++}`,
      source: obsId,
      target: `loc-${loc}`,
      label: 'OCCURRED_AT',
      color: '#10b981',
    })

    // Edge 4: Vehicle -> Overspeed Violation Hub (if speeding)
    if (isOver) {
      edges.push({
        id: `edge-${edgeIndex++}`,
        source: obsId,
        target: 'violation-overspeed-hub',
        label: 'COMMITTED_VIOLATION',
        color: '#ef4444',
      })
    }

    // Edge 5: Vehicle -> Signal Hub (if signal event)
    if (row.signalState && row.signalState !== 'Green') {
      edges.push({
        id: `edge-${edgeIndex++}`,
        source: obsId,
        target: `signal-hub-${focusedCamera}`,
        label: 'UNDER_SIGNAL',
        color: '#f59e0b',
      })
    }
  })

  return {
    currentNodes: nodes,
    currentEdges: edges,
    stats: {
      cameras: 1,
      locations: 1,
      networks: 1,
      signals: 1,
      violations: overspeedCount,
      types: allDomains.length,
      observations: camRows.length,
      totalQueried: (pool || []).length,
    },
  }
}

export default function QueryKnowledgeGraph({
  rows = [],
  allRows = [],
  queryLabel = 'Queried Telemetry',
  initialSelectedId = null,
  submittedQuery = '',
  isSpecificVehicle = false,
  isCameraSearch = false,
  isAllCameras = false,
  cameraQueryId = null,
  onClose,
}) {
  // Available pool of rows for live ingestion
  const telemetryPool = useMemo(() => {
    return allRows && allRows.length ? allRows : rows
  }, [allRows, rows])

  // Distinct camera list for quick selection
  const availableCameras = useMemo(() => {
    return Array.from(new Set(telemetryPool.map((r) => r.camera).filter(Boolean)))
  }, [telemetryPool])

  // Initial mode determination based on user query
  const initialMode = useMemo(() => {
    if (isAllCameras) {
      return 'ALL'
    }
    if (isSpecificVehicle || (rows.length === 1 && (rows[0].numberPlate || rows[0].observationId))) {
      return 'VEHICLE'
    }
    if (isCameraSearch || cameraQueryId) {
      return 'CAMERA'
    }
    return 'ALL'
  }, [isAllCameras, isSpecificVehicle, isCameraSearch, cameraQueryId, rows])

  // Primary Modes: 'ALL' | 'VEHICLE' | 'CAMERA'
  const [focusMode, setFocusMode] = useState(initialMode)

  // Static frozen snapshot of vehicle (never altered by incoming live stream)
  const [frozenVehicle, setFrozenVehicle] = useState(() => {
    if (initialMode === 'VEHICLE' && rows.length > 0) {
      return rows[0]
    }
    return null
  })

  // Dynamic camera hub identifier
  const [focusedCamera, setFocusedCamera] = useState(() => {
    if (cameraQueryId) return cameraQueryId
    if (initialMode === 'CAMERA' && rows.length > 0 && rows[0].camera) {
      return rows[0].camera
    }
    return availableCameras[0] || null
  })

  const [liveDetectionCount, setLiveDetectionCount] = useState(0)
  const [latestLiveAlert, setLatestLiveAlert] = useState(null)
  // Dynamic camera mode is automatically streaming by default when searching or entering camera mode
  const [autoStreamActive, setAutoStreamActive] = useState(false) // simulated captures removed: graphs show real detections only

  // Snapshot of nodes for CAMERA mode taken only when entering CAMERA mode or changing focusedCamera
  const initialCameraSnapshot = useMemo(() => {
    if (focusMode !== 'CAMERA' || !focusedCamera) return null
    return buildCameraGraphSnapshot(focusedCamera, telemetryPool)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [focusMode, focusedCamera])

  // Standard graph controls
  const [searchTerm, setSearchTerm] = useState('')
  const [showSuggestions, setShowSuggestions] = useState(false)
  const [activeCategory, setActiveCategory] = useState('ALL')
  const [vehicleDomainFilter, setVehicleDomainFilter] = useState('ALL')
  const [segregatedView, setSegregatedView] = useState(true)
  const [selectedNode, setSelectedNode] = useState(null)
  const [previewModalRow, setPreviewModalRow] = useState(null)
  const containerRef = useRef(null)
  const cyRef = useRef(null)

  // Track rendered node IDs in dynamic camera mode
  const renderedObsIdsRef = useRef(new Set())

  // Keep focusMode in sync if parent query changes
  useEffect(() => {
    if (isAllCameras) {
      setFocusMode('ALL')
      setFrozenVehicle(null)
      setFocusedCamera(null)
      setAutoStreamActive(false)
    } else if (isSpecificVehicle && rows.length > 0) {
      setFocusMode('VEHICLE')
      setFrozenVehicle(rows[0])
      setAutoStreamActive(false)
    } else if (isCameraSearch || cameraQueryId) {
      setFocusMode('CAMERA')
      const targetCam = cameraQueryId || rows[0]?.camera || availableCameras[0]
      if (targetCam) {
        setFocusedCamera(targetCam)
      }
      setAutoStreamActive(false)
    }
  }, [isAllCameras, isSpecificVehicle, isCameraSearch, cameraQueryId, submittedQuery])

  // Recent vehicles for quick selection
  const sampleVehicles = useMemo(() => {
    const map = new Map()
    for (const r of rows) {
      const plate = r.numberPlate || r.vehicleNumberPlate || r.observationId || r.id
      if (plate && !map.has(plate)) {
        map.set(plate, r)
        if (map.size >= 8) break
      }
    }
    return Array.from(map.values())
  }, [rows])

  // Search auto-suggestions
  const searchSuggestions = useMemo(() => {
    const q = searchTerm.trim().toLowerCase()
    if (!q) return { cameras: [], vehicles: [] }

    const matchedCameras = availableCameras
      .filter((cam) => cam.toLowerCase().includes(q))
      .slice(0, 4)

    const matchedVehicles = telemetryPool
      .filter((r) => {
        const plate = (r.numberPlate || r.vehicleNumberPlate || '').toLowerCase()
        const id = String(r.observationId || r.id || '').toLowerCase()
        return plate.includes(q) || id.includes(q)
      })
      .slice(0, 6)

    return { cameras: matchedCameras, vehicles: matchedVehicles }
  }, [searchTerm, availableCameras, telemetryPool])

  // Compute breakdown of vehicle types for the domain color legend
  const domainBreakdown = useMemo(() => {
    const counts = {}
    rows.forEach((r) => {
      const rawType = r.type || r.vehicleType || 'Car'
      const domain = getCanonicalVehicleDomain(rawType)
      const meta = getVehicleMeta(domain)
      if (!counts[domain]) {
        counts[domain] = {
          label: domain,
          rawType: domain,
          count: 0,
          color: meta.color,
          bg: meta.bg,
          border: meta.border,
        }
      }
      counts[domain].count += 1
    })
    return Object.values(counts).sort((a, b) => b.count - a.count)
  }, [rows])

  // Switch to Static Vehicle Mode
  function handleSelectVehicle(vehicleRow) {
    if (!vehicleRow) return
    const plate = vehicleRow.numberPlate || vehicleRow.vehicleNumberPlate || vehicleRow.observationId || vehicleRow.id
    setFocusMode('VEHICLE')
    setFrozenVehicle(vehicleRow)
    setFocusedCamera(null)
    setSearchTerm('')
    setShowSuggestions(false)

    const domain = getCanonicalVehicleDomain(vehicleRow.vehicleType || vehicleRow.type)
    const meta = getVehicleMeta(domain)
    setSelectedNode({
      id: vehicleRow.observationId ? `obs-${vehicleRow.observationId}` : `obs-${vehicleRow.id || plate}`,
      label: plate,
      category: 'Observation',
      vehicleType: domain,
      color: meta.color,
      image: vehicleRow.extractedImage || vehicleRow.vehicleImageDataUrl || vehicleRow.vehicleImagePath || vehicleRow.vehicleImage,
      hasExtractedImage: vehicleRow.hasExtractedImage,
      rawRow: vehicleRow,
      properties: {
        'Number Plate': plate,
        'Vehicle Domain': domain,
        'Timestamp (IST)': vehicleRow.timestampIst || vehicleRow.timestamp || 'N/A',
        'Captured By': vehicleRow.camera || 'N/A',
        'Location': vehicleRow.roadName || vehicleRow.location || 'N/A',
        'Speed (km/h)': `${vehicleRow.speed || 0} km/h`,
        'Speed Limit': `${vehicleRow.speedLimit || 60} km/h`,
        'Violation Status': vehicleRow.overSpeed || (Number(vehicleRow.speed) > Number(vehicleRow.speedLimit || 60) ? 'Overspeeding' : 'Compliant'),
        'Plate Confidence': `${Math.round(((vehicleRow.plateConfidence || vehicleRow.confidence) > 1 ? (vehicleRow.plateConfidence || vehicleRow.confidence) : (vehicleRow.plateConfidence || vehicleRow.confidence || 0.95) * 100))}%`,
      },
    })
  }

  // Switch to Dynamic Camera Mode
  function handleSelectCamera(camId) {
    if (!camId) return
    setFocusMode('CAMERA')
    setFocusedCamera(camId)
    setAutoStreamActive(false)
    setFrozenVehicle(null)
    setSearchTerm('')
    setShowSuggestions(false)
    const currentCamRows = telemetryPool.filter((r) => r.camera === camId)
    setLiveDetectionCount(currentCamRows.length)

    setSelectedNode({
      id: `cam-${camId}`,
      label: camId,
      category: 'Camera',
      color: '#0f172a',
      borderColor: '#10b981',
      properties: {
        'Camera ID': camId,
        'Operational Status': '🟢 Live Telemetry Stream Active (Dynamic)',
        'Assigned Road': currentCamRows[0]?.roadName || currentCamRows[0]?.location || 'Outer Ring Road (NH-44 Expressway)',
        'Total Ingested Detections': currentCamRows.length,
        'Streaming Status': '🟢 Ingesting Real-Time Dynamic Telemetry',
      },
    })
  }

  function handleExitFocusMode() {
    setFocusMode('ALL')
    setFrozenVehicle(null)
    setFocusedCamera(null)
    setAutoStreamActive(false)
    setLatestLiveAlert(null)
    setSelectedNode(null)
  }

  // Build Graph Nodes & Edges
  const { currentNodes, currentEdges, stats } = useMemo(() => {
    let edgeIndex = 1

    // =========================================================================
    // 1. STATIC VEHICLE FORENSIC MODE (Strictly Static & Shows All Connections)
    // =========================================================================
    if (focusMode === 'VEHICLE' && frozenVehicle) {
      const v = frozenVehicle
      const obsId = v.observationId ? `obs-${v.observationId}` : `obs-${v.id || v.numberPlate}`
      const obsLabel = v.numberPlate && v.numberPlate !== 'N/A' && v.numberPlate !== 'Unknown'
        ? v.numberPlate
        : (v.observationId || 'Vehicle')
      const domain = getCanonicalVehicleDomain(v.vehicleType || v.type)
      const meta = getVehicleMeta(domain)
      const loc = v.roadName || v.location || 'Monitored Road'
      const cam = v.camera || 'Surveillance Camera'
      const isOverSpeed = v.isOverSpeed || v.overSpeed === 'Yes' || (Number(v.speed) > Number(v.speedLimit || 60))

      const nodes = [
        // Central Vehicle Node
        {
          id: obsId,
          label: obsLabel,
          category: 'Observation',
          vehicleType: domain,
          color: meta.color,
          borderColor: '#2563eb',
          isCenter: true,
          image: v.extractedImage || v.vehicleImageDataUrl || v.vehicleImagePath || v.vehicleImage,
          hasExtractedImage: v.hasExtractedImage,
          rawRow: v,
          properties: {
            'Number Plate': obsLabel,
            'Vehicle Type': domain,
            'Captured By': cam,
            'Location': loc,
            'Speed': `${v.speed || 0} km/h`,
            'Speed Limit': `${v.speedLimit || 60} km/h`,
            'Violation Status': isOverSpeed ? '⚠️ Overspeed Violation' : 'Compliant',
            'Timestamp': v.timestampIst || v.timestamp || 'N/A',
            'Confidence': `${Math.round(((v.plateConfidence || v.confidence) > 1 ? (v.plateConfidence || v.confidence) : (v.plateConfidence || v.confidence || 0.95) * 100))}%`,
            'Coordinates': `${v.latitude?.toFixed?.(4) || '17.4485'}, ${v.longitude?.toFixed?.(4) || '78.3742'}`,
          },
        },
        // Camera Node
        {
          id: `cam-${cam}`,
          label: `Camera: ${cam}`,
          category: 'Camera',
          color: '#475569',
          borderColor: '#ffffff',
          properties: {
            'Camera ID': cam,
            'Assigned Zone': loc,
            'Role': 'Capturing Sensor',
          },
        },
        // Location Node
        {
          id: `loc-${loc}`,
          label: `Location: ${loc}`,
          category: 'Location',
          color: '#10b981',
          borderColor: '#ffffff',
          properties: {
            'Monitored Road': loc,
            'Coordinates': `${v.latitude?.toFixed?.(4) || '17.4485'}, ${v.longitude?.toFixed?.(4) || '78.3742'}`,
          },
        },
        // Domain Classification Node
        {
          id: `type-${domain}`,
          label: `${domain} Domain`,
          category: 'VehicleType',
          vehicleType: domain,
          color: meta.color,
          borderColor: '#ffffff',
          properties: {
            'Classification': domain,
            'Assigned Color': meta.color,
          },
        },
      ]

      const edges = [
        { id: `edge-${edgeIndex++}`, source: obsId, target: `cam-${cam}`, label: 'CAPTURED_BY', color: '#0284c7' },
        { id: `edge-${edgeIndex++}`, source: obsId, target: `loc-${loc}`, label: 'OCCURRED_AT', color: '#10b981' },
        { id: `edge-${edgeIndex++}`, source: obsId, target: `type-${domain}`, label: 'OF_TYPE', color: meta.color },
        { id: `edge-${edgeIndex++}`, source: `cam-${cam}`, target: `loc-${loc}`, label: 'MONITORS', color: '#94a3b8' },
      ]

      // Optional Violation Node
      if (isOverSpeed) {
        nodes.push({
          id: 'violation-overspeed',
          label: `Overspeed (${v.speed} km/h > ${v.speedLimit || 60} km/h)`,
          category: 'Violation',
          color: '#ef4444',
          borderColor: '#ffffff',
          properties: {
            'Violation': 'Excess Speed Detected',
            'Recorded Speed': `${v.speed} km/h`,
            'Allowed Speed': `${v.speedLimit || 60} km/h`,
            'Severity': 'High',
          },
        })
        edges.push({
          id: `edge-${edgeIndex++}`,
          source: obsId,
          target: 'violation-overspeed',
          label: 'TRIGGERED',
          color: '#ef4444',
        })
      }

      // Optional Signal State Node
      if (v.signalState && v.signalState !== 'Green') {
        nodes.push({
          id: `signal-${v.signalState}`,
          label: `Signal: ${v.signalState}`,
          category: 'Signal',
          color: v.signalState === 'Red' ? '#dc2626' : '#d97706',
          borderColor: '#ffffff',
          properties: {
            'Traffic Signal': v.signalState,
            'Junction': v.junctionId || 'Road Junction',
          },
        })
        edges.push({
          id: `edge-${edgeIndex++}`,
          source: obsId,
          target: `signal-${v.signalState}`,
          label: 'UNDER_SIGNAL',
          color: '#d97706',
        })
      }

      return {
        currentNodes: nodes,
        currentEdges: edges,
        stats: { cameras: 1, locations: 1, types: 1, observations: 1, totalQueried: rows.length },
      }
    }

    // =========================================================================
    // 2. DYNAMIC CAMERA STREAMING MODE (Auto-updates with live telemetry)
    // =========================================================================
    if (focusMode === 'CAMERA' && focusedCamera) {
      if (initialCameraSnapshot) {
        return initialCameraSnapshot
      }
      return buildCameraGraphSnapshot(focusedCamera, telemetryPool)
    }

    // =========================================================================
    // 3. FULL QUERIED SUBGRAPH MODE ('ALL')
    // =========================================================================
    if (!rows || !rows.length) {
      return { currentNodes: [], currentEdges: [], stats: { cameras: 0, locations: 0, types: 0, observations: 0, totalQueried: 0 } }
    }

    const cameras = Array.from(new Set(rows.map((r) => r.camera).filter(Boolean)))
    const locations = Array.from(new Set(rows.map((r) => r.roadName || r.location).filter(Boolean)))
    const domains = Array.from(new Set(rows.map((r) => getCanonicalVehicleDomain(r.type || r.vehicleType)).filter(Boolean)))

    const nodes = []
    const edges = []

    if (segregatedView) {
      domains.forEach((domain) => {
        const meta = getVehicleMeta(domain)
        const count = rows.filter((r) => getCanonicalVehicleDomain(r.type || r.vehicleType) === domain).length
        nodes.push({
          id: `group-type-${domain}`,
          label: `${domain.toUpperCase()} DOMAIN · ${count} RECORDS`,
          category: 'Group',
          color: meta.bg || '#f8fafc',
          borderColor: meta.color || '#3b82f6',
          isGroup: true,
          properties: {
            'Cluster Domain': domain,
            'Vehicle Count': count,
          },
        })
      })

      if (cameras.length > 0) {
        nodes.push({
          id: 'group-cameras',
          label: `CAMERAS NETWORK · ${cameras.length} UNITS`,
          category: 'Group',
          color: '#f8fafc',
          borderColor: '#475569',
          isGroup: true,
          properties: {
            'Cluster Domain': 'Surveillance Network',
            'Active Cameras': cameras.length,
          },
        })
      }

      if (locations.length > 0) {
        nodes.push({
          id: 'group-locations',
          label: `MONITORED ROADS · ${locations.length} ZONES`,
          category: 'Group',
          color: '#f0fdf4',
          borderColor: '#10b981',
          isGroup: true,
          properties: {
            'Cluster Domain': 'Roads & Corridors',
            'Monitored Zones': locations.length,
          },
        })
      }
    }

    // Locations
    locations.forEach((loc) => {
      const locRows = rows.filter((r) => (r.roadName || r.location) === loc)
      nodes.push({
        id: `loc-${loc}`,
        label: loc,
        category: 'Location',
        color: '#10b981',
        borderColor: '#ffffff',
        parent: segregatedView ? 'group-locations' : undefined,
        properties: {
          'Road / Junction': loc,
          'Matching Records': locRows.length,
        },
      })
    })

    // Cameras
    cameras.forEach((cam) => {
      const camRows = rows.filter((r) => r.camera === cam)
      const assignedLoc = camRows[0]?.roadName || camRows[0]?.location || (locations.length > 0 ? locations[0] : null)
      nodes.push({
        id: `cam-${cam}`,
        label: cam,
        category: 'Camera',
        color: '#475569',
        borderColor: '#ffffff',
        parent: segregatedView ? 'group-cameras' : undefined,
        properties: {
          'Camera ID': cam,
          'Assigned Road': assignedLoc || 'N/A',
          'Queried Detections': camRows.length,
        },
      })
      if (assignedLoc && locations.includes(assignedLoc)) {
        edges.push({
          id: `edge-cam-${cam}-loc-${assignedLoc}`,
          source: `cam-${cam}`,
          target: `loc-${assignedLoc}`,
          label: 'MONITORS',
          color: '#94a3b8',
        })
      }
    })

    // Domains
    domains.forEach((domain) => {
      const domainRows = rows.filter((r) => getCanonicalVehicleDomain(r.type || r.vehicleType) === domain)
      const meta = getVehicleMeta(domain)
      nodes.push({
        id: `type-${domain}`,
        label: domain,
        category: 'VehicleType',
        vehicleType: domain,
        color: meta.color || '#2563eb',
        borderColor: '#ffffff',
        parent: segregatedView ? `group-type-${domain}` : undefined,
        properties: {
          'Vehicle Domain': domain,
          'Matching Detections': domainRows.length,
        },
      })
    })

    // Observations
    rows.forEach((row, i) => {
      const obsId = row.observationId ? `obs-${row.observationId}` : `obs-${row.id || i + 1}`
      const obsLabel = row.numberPlate && row.numberPlate !== 'N/A' && row.numberPlate !== 'Unknown'
        ? row.numberPlate
        : (row.observationId || row.id || `Detection #${i + 1}`)
      const loc = row.roadName || row.location
      const domain = getCanonicalVehicleDomain(row.type || row.vehicleType)
      const meta = getVehicleMeta(domain)

      nodes.push({
        id: obsId,
        label: obsLabel,
        category: 'Observation',
        vehicleType: domain,
        color: meta.color,
        borderColor: meta.border || '#ffffff',
        parent: segregatedView ? `group-type-${domain}` : undefined,
        image: row.extractedImage || row.vehicleImageDataUrl || row.vehicleImagePath || row.vehicleImage,
        hasExtractedImage: row.hasExtractedImage,
        rawRow: row,
        properties: {
          'Observation ID': row.id || row.observationId || `OBS-${i + 1}`,
          'Number Plate': obsLabel,
          'Vehicle Type': domain,
          'Captured By': row.camera || 'N/A',
          'Road': loc || 'N/A',
          'Timestamp': row.timestampIst || row.timestamp || 'N/A',
          'Speed': `${row.speed || 0} km/h`,
          'Over Speed': row.overSpeed || (row.speed > row.speedLimit ? 'Yes' : 'No'),
        },
      })

      edges.push({
        id: `edge-${obsId}-type-${domain}`,
        source: obsId,
        target: `type-${domain}`,
        label: 'OF_TYPE',
        color: '#94a3b8',
      })

      if (row.camera && cameras.includes(row.camera)) {
        edges.push({
          id: `edge-${obsId}-cam-${row.camera}`,
          source: obsId,
          target: `cam-${row.camera}`,
          label: 'CAPTURED_BY',
          color: '#94a3b8',
        })
      }

      if (loc && locations.includes(loc)) {
        edges.push({
          id: `edge-${obsId}-loc-${loc}`,
          source: obsId,
          target: `loc-${loc}`,
          label: 'OCCURRED_AT',
          color: '#94a3b8',
        })
      }
    })

    return {
      currentNodes: nodes,
      currentEdges: edges,
      stats: {
        cameras: cameras.length,
        locations: locations.length,
        types: domains.length,
        observations: rows.length,
        totalQueried: rows.length,
      },
    }
  }, [rows, focusMode, frozenVehicle, focusedCamera, segregatedView, initialCameraSnapshot])

  // Visible nodes in ALL mode
  const visibleNodes = useMemo(() => {
    if (focusMode !== 'ALL') return currentNodes

    const rawFiltered = currentNodes.filter((node) => {
      if (node.category === 'Group') return true

      const matchCat = activeCategory === 'ALL' || node.category === activeCategory

      let matchDomain = true
      if (vehicleDomainFilter !== 'ALL') {
        const targetDomain = vehicleDomainFilter.toLowerCase()
        if (node.category === 'Observation') {
          matchDomain = (node.vehicleType || '').toLowerCase() === targetDomain
        } else if (node.category === 'VehicleType') {
          matchDomain = (node.vehicleType || node.label || '').toLowerCase() === targetDomain
        }
      }

      const searchLower = searchTerm.toLowerCase()
      const matchSearch =
        !searchTerm ||
        node.label.toLowerCase().includes(searchLower) ||
        node.category.toLowerCase().includes(searchLower) ||
        (node.vehicleType && node.vehicleType.toLowerCase().includes(searchLower))

      return matchCat && matchDomain && matchSearch
    })

    let candidateNodes = rawFiltered
    if (vehicleDomainFilter !== 'ALL') {
      const activeObs = rawFiltered.filter((n) => n.category === 'Observation')
      const activeObsIds = new Set(activeObs.map((n) => n.id))
      const connectedEntityIds = new Set()

      currentEdges.forEach((e) => {
        if (activeObsIds.has(e.source)) connectedEntityIds.add(e.target)
        if (activeObsIds.has(e.target)) connectedEntityIds.add(e.source)
      })

      candidateNodes = rawFiltered.filter((n) => {
        if (n.category === 'Group') return true
        if (n.category === 'Observation') return true
        if (n.category === 'VehicleType') {
          return (n.vehicleType || n.label || '').toLowerCase() === vehicleDomainFilter.toLowerCase()
        }
        return connectedEntityIds.has(n.id)
      })
    }

    const visibleChildParentIds = new Set(
      candidateNodes
        .filter((n) => n.category !== 'Group' && n.parent)
        .map((n) => n.parent)
    )

    return candidateNodes.filter((n) => {
      if (n.category === 'Group') return visibleChildParentIds.has(n.id)
      return true
    })
  }, [currentNodes, currentEdges, focusMode, activeCategory, vehicleDomainFilter, searchTerm])

  const visibleNodeIds = useMemo(() => new Set(visibleNodes.map((n) => n.id)), [visibleNodes])

  const visibleEdges = useMemo(() => {
    return currentEdges.filter(
      (e) => visibleNodeIds.has(e.source) && visibleNodeIds.has(e.target)
    )
  }, [currentEdges, visibleNodeIds])

  // Layout Configuration
  const layoutConfig = useMemo(() => {
    if (focusMode === 'VEHICLE') {
      return {
        name: 'concentric',
        concentric: (node) => (node.data('isCenter') ? 2 : 1),
        levelWidth: () => 1,
        minNodeSpacing: 80,
        padding: 65,
        animate: true,
        animationDuration: 300,
      }
    }

    if (focusMode === 'CAMERA') {
      return {
        name: 'concentric',
        concentric: (node) => {
          if (node.data('isCenter')) return 4
          const cat = node.data('category')
          if (cat === 'Location' || cat === 'Network' || cat === 'Signal' || cat === 'Violation') return 3
          if (cat === 'VehicleType') return 2
          return 1
        },
        levelWidth: () => 1,
        minNodeSpacing: 60,
        padding: 55,
        animate: true,
        animationDuration: 350,
      }
    }

    // Force COSE layout for ALL queried segment
    return {
      name: 'cose',
      animate: false,
      padding: 60,
      componentSpacing: 180,
      nodeDimensionsIncludeLabels: true,
      nodeOverlap: 25,
      nestingFactor: 1.25,
      gravityCompound: 1.0,
      gravityRangeCompound: 1.5,
      nodeRepulsion: (node) => {
        if (node.isParent?.() || node.data('category') === 'Group') return 650000
        const cat = node.data('category')
        if (cat === 'Location') return 240000
        if (cat === 'Camera' || cat === 'VehicleType') return 160000
        return 75000
      },
      idealEdgeLength: (edge) => {
        const lbl = edge.data('label')
        if (lbl === 'OF_TYPE') return 75
        if (lbl === 'MONITORS') return 240
        return 280
      },
      edgeElasticity: 25,
      gravity: 0.012,
      numIter: 1000,
      stop: () => {
        cyRef.current?.animate({
          fit: { eles: cyRef.current.elements(), padding: 50 },
          duration: 250,
        })
      },
    }
  }, [focusMode, segregatedView])

  // Track initial rendered observation IDs
  useEffect(() => {
    renderedObsIdsRef.current = new Set(visibleNodes.map((n) => n.id))
  }, [focusMode, focusedCamera, frozenVehicle])

  // Cytoscape initialization and remount on mode change
  useEffect(() => {
    if (!containerRef.current) return

    const elements = [
      ...visibleNodes.map((n) => ({
        group: 'nodes',
        data: {
          id: n.id,
          label: n.label,
          category: n.category,
          color: n.color,
          borderColor: n.borderColor || '#ffffff',
          vehicleType: n.vehicleType || '',
          parent: (n.parent && visibleNodeIds.has(n.parent)) ? n.parent : undefined,
          isGroup: n.isGroup,
          isCenter: n.isCenter || false,
        },
      })),
      ...visibleEdges.map((e) => ({
        group: 'edges',
        data: {
          id: e.id,
          source: e.source,
          target: e.target,
          label: e.label,
          color: e.color || '#94a3b8',
        },
      })),
    ]

    const cy = cytoscape({
      container: containerRef.current,
      elements,
      minZoom: 0.04,
      maxZoom: 3.5,
      wheelSensitivity: 0.15,
      layout: layoutConfig,
      style: [
        {
          selector: 'node',
          style: {
            width: (node) => {
              if (node.data('isCenter')) return 72
              const cat = node.data('category')
              if (cat === 'Location') return 58
              if (cat === 'Camera') return 48
              if (cat === 'Network') return 54
              if (cat === 'Signal') return 50
              if (cat === 'Violation') return 52
              if (cat === 'VehicleType') return 52
              return 38
            },
            height: (node) => {
              if (node.data('isCenter')) return 72
              const cat = node.data('category')
              if (cat === 'Location') return 58
              if (cat === 'Camera') return 48
              if (cat === 'Network') return 54
              if (cat === 'Signal') return 50
              if (cat === 'Violation') return 52
              if (cat === 'VehicleType') return 52
              return 38
            },
            label: 'data(label)',
            'background-color': 'data(color)',
            color: '#0f172a',
            'font-size': (node) => (node.data('isCenter') ? 13 : (node.data('category') === 'Observation' ? 9.5 : 11.5)),
            'font-weight': (node) => (node.data('isCenter') ? 800 : (node.data('category') === 'Observation' ? 600 : 700)),
            'text-valign': 'bottom',
            'text-margin-y': 7,
            'text-wrap': 'wrap',
            'text-max-width': (node) => (node.data('isCenter') ? 140 : (node.data('category') === 'Observation' ? 85 : 110)),
            'border-width': (node) => (node.data('isCenter') ? 4 : (node.data('category') === 'VehicleType' ? 3.5 : 2.5)),
            'border-color': 'data(borderColor)',
            'border-opacity': 1,
            'text-background-color': '#ffffff',
            'text-background-opacity': 0.94,
            'text-background-padding': 3,
            'text-background-shape': 'roundrectangle',
          },
        },
        // Center Anchor Highlight
        {
          selector: 'node[?isCenter]',
          style: {
            'underlay-color': 'data(color)',
            'underlay-padding': 10,
            'underlay-opacity': 0.28,
            'border-width': 4,
            'border-color': '#0284c7',
          },
        },
        // Dynamic Live Pulse for newly ingested stream nodes
        {
          selector: 'node.live-pulse',
          style: {
            'underlay-color': '#10b981',
            'underlay-padding': 14,
            'underlay-opacity': 0.65,
            'border-width': 4,
            'border-color': '#10b981',
          },
        },
        {
          selector: ':parent',
          style: {
            'background-color': 'data(color)',
            'background-opacity': 0.16,
            'border-width': 2,
            'border-style': 'dashed',
            'border-color': 'data(borderColor)',
            'border-opacity': 0.8,
            'corner-radius': 16,
            label: 'data(label)',
            'text-valign': 'top',
            'text-halign': 'center',
            'text-margin-y': -8,
            'font-size': 11,
            'font-weight': 800,
            color: '#1e293b',
            'text-background-color': '#ffffff',
            'text-background-opacity': 0.94,
            'text-background-padding': 3,
            'text-background-shape': 'roundrectangle',
            padding: 24,
          },
        },
        {
          selector: 'node:selected',
          style: {
            'border-width': 3.5,
            'border-color': '#0f172a',
            'underlay-color': 'data(color)',
            'underlay-padding': 8,
            'underlay-opacity': 0.45,
          },
        },
        {
          selector: 'edge',
          style: {
            width: 1.5,
            'line-color': 'data(color)',
            opacity: 0.65,
            'curve-style': 'bezier',
            'control-point-step-size': 35,
            'target-arrow-shape': 'triangle',
            'target-arrow-color': 'data(color)',
            'arrow-scale': 0.75,
            label: 'data(label)',
            'font-size': 7.5,
            color: '#64748b',
            'text-rotation': 'autorotate',
            'text-margin-y': -6,
            'text-background-color': '#ffffff',
            'text-background-opacity': 0.85,
            'text-background-padding': 2,
            'text-background-shape': 'roundrectangle',
          },
        },
      ],
    })

    cy.ready(() => {
      if (focusMode === 'CAMERA') {
        renderedObsIdsRef.current = new Set()
        currentNodes.forEach((n) => {
          if (n.category === 'Observation') {
            renderedObsIdsRef.current.add(n.id)
          }
        })
        setLiveDetectionCount(renderedObsIdsRef.current.size)
      }

      let targetNode = null
      if (initialSelectedId) {
        targetNode = cy.getElementById(initialSelectedId)
        if (!targetNode.length) targetNode = cy.getElementById(`obs-${initialSelectedId}`)
        if (!targetNode.length) {
          const matched = currentNodes.find(
            (n) =>
              n.properties?.['Number Plate'] === initialSelectedId ||
              n.properties?.['Observation ID'] === initialSelectedId ||
              n.label === initialSelectedId
          )
          if (matched) targetNode = cy.getElementById(matched.id)
        }
      }

      if (!targetNode?.length && focusMode === 'VEHICLE' && frozenVehicle) {
        const obsId = frozenVehicle.observationId ? `obs-${frozenVehicle.observationId}` : `obs-${frozenVehicle.id || frozenVehicle.numberPlate}`
        targetNode = cy.getElementById(obsId)
      }

      if (!targetNode?.length && focusMode === 'CAMERA' && focusedCamera) {
        targetNode = cy.getElementById(`cam-${focusedCamera}`)
      }

      if (targetNode && targetNode.length) {
        targetNode.select()
        const nodeObj = currentNodes.find((n) => n.id === targetNode.id())
        if (nodeObj) setSelectedNode(nodeObj)
        cy.animate({
          center: { eles: targetNode },
          zoom: 1.25,
          duration: 350,
        })
      } else {
        cy.animate({
          fit: { eles: cy.elements(), padding: 60 },
          duration: 300,
        })
      }
    })

    cy.on('tap', 'node', (evt) => {
      const nodeId = evt.target.id()
      const nodeData = evt.target.data()
      const nodeObj = currentNodes.find((n) => n.id === nodeId) || (nodeData ? {
        id: nodeData.id,
        label: nodeData.label,
        category: nodeData.category,
        vehicleType: nodeData.vehicleType,
        color: nodeData.color,
        borderColor: nodeData.borderColor,
        image: nodeData.image,
        hasExtractedImage: nodeData.hasExtractedImage,
        rawRow: nodeData.rawRow,
        properties: nodeData.properties || {},
      } : null)
      setSelectedNode(nodeObj || null)
    })

    cy.on('tap', (evt) => {
      if (evt.target === cy) {
        setSelectedNode(null)
      }
    })

    cyRef.current = cy

    return () => {
      if (cyRef.current) {
        try {
          if (typeof cyRef.current.destroyed === 'function' && !cyRef.current.destroyed()) {
            cyRef.current.destroy()
          }
        } catch {
          // ignore
        }
        cyRef.current = null
      }
    }
  }, [focusMode, focusedCamera, frozenVehicle, visibleNodes, visibleEdges, layoutConfig])

  // =========================================================================
  // DYNAMIC STREAMING INGESTION (Only in Camera mode)
  // Automatically appends new records detected by this camera in real time!
  // =========================================================================
  useEffect(() => {
    if (focusMode !== 'CAMERA' || !focusedCamera || !cyRef.current) return

    const cy = cyRef.current
    if (typeof cy.destroyed === 'function' && cy.destroyed()) return

    const targetCamNorm = focusedCamera.toLowerCase().replace(/[^a-z0-9]/g, '')
    const camRows = telemetryPool.filter((r) => {
      if (!r.camera) return false
      const rowCamNorm = r.camera.toLowerCase().replace(/[^a-z0-9]/g, '')
      return rowCamNorm === targetCamNorm || rowCamNorm.includes(targetCamNorm) || targetCamNorm.includes(rowCamNorm)
    })

    if (!camRows.length) return

    const newRecords = []
    camRows.forEach((r, i) => {
      const obsId = r.observationId ? `obs-${r.observationId}` : `obs-${r.id || `${focusedCamera}-${i}`}`
      if (!renderedObsIdsRef.current.has(obsId) && !cy.getElementById(obsId).length) {
        newRecords.push({ row: r, obsId })
        renderedObsIdsRef.current.add(obsId)
      }
    })

    if (newRecords.length > 0) {
      const camNode = cy.getElementById(`cam-${focusedCamera}`)
      const camPos = camNode.length ? camNode.position() : { x: 400, y: 300 }
      const loc = camNode.length && camNode.data('properties') ? (camNode.data('properties')['Monitored Roadway'] || 'Outer Ring Road (NH-44 Expressway)') : 'Outer Ring Road (NH-44 Expressway)'
      const locNodeId = `loc-${loc}`
      const violHubId = 'violation-overspeed-hub'
      const signalHubId = `signal-hub-${focusedCamera}`

      let newViolationsCount = 0

      newRecords.forEach(({ row: r, obsId }, idx) => {
        const obsLabel = (r.numberPlate && r.numberPlate !== 'N/A' && r.numberPlate !== 'Unknown')
          ? r.numberPlate
          : (r.observationId || r.id || 'New Detection')
        const domain = getCanonicalVehicleDomain(r.type || r.vehicleType)
        const meta = getVehicleMeta(domain)

        const domainNodeId = `type-${domain}`
        if (!cy.getElementById(domainNodeId).length) {
          cy.add({
            group: 'nodes',
            data: {
              id: domainNodeId,
              label: `${domain} Domain`,
              category: 'VehicleType',
              vehicleType: domain,
              color: meta.color,
              borderColor: '#ffffff',
              properties: {
                'Classification': domain,
                'Color': meta.color,
                'Monitored Sensor': focusedCamera,
              },
            },
            position: {
              x: camPos.x + (Math.random() - 0.5) * 260,
              y: camPos.y - 180,
            },
          })
        }

        const total = newRecords.length
        const angle = (idx / total) * Math.PI * 2 + (Math.random() * 0.4 - 0.2)
        const radius = 230 + (idx % 3) * 45 + Math.random() * 40
        const isOver = r.isOverSpeed || r.overSpeed === 'Yes' || (Number(r.speed) > Number(r.speedLimit || 60))
        if (isOver) newViolationsCount += 1

        const addedElements = [
          {
            group: 'nodes',
            data: {
              id: obsId,
              label: obsLabel,
              category: 'Observation',
              vehicleType: domain,
              color: meta.color,
              borderColor: isOver ? '#ef4444' : '#10b981',
              rawRow: r,
              image: r.extractedImage || r.vehicleImageDataUrl || r.vehicleImagePath || r.vehicleImage,
              hasExtractedImage: r.hasExtractedImage,
              properties: {
                'Number Plate': obsLabel,
                'Vehicle Type': domain,
                'Captured By': focusedCamera,
                'Monitored Road': loc,
                'Timestamp': r.timestampIst || r.timestamp || new Date().toLocaleTimeString(),
                'Speed': `${r.speed || 0} km/h`,
                'Speed Limit': `${r.speedLimit || 60} km/h`,
                'Violation Status': isOver ? '⚠️ Overspeed Violation' : 'Compliant',
                'Signal Status': r.signalState || 'Green',
                'Dynamic Ingestion': '🟢 Real-time Telemetry Stream',
              },
            },
            position: {
              x: camPos.x + Math.cos(angle) * radius,
              y: camPos.y + Math.sin(angle) * radius,
            },
            classes: 'live-pulse',
          },
          // 1. Vehicle -> Camera
          {
            group: 'edges',
            data: {
              id: `edge-dyn-cam-${obsId}`,
              source: obsId,
              target: `cam-${focusedCamera}`,
              label: 'CAPTURED_BY',
              color: '#0284c7',
            },
          },
          // 2. Vehicle -> Domain
          {
            group: 'edges',
            data: {
              id: `edge-dyn-type-${obsId}`,
              source: obsId,
              target: domainNodeId,
              label: 'OF_TYPE',
              color: meta.color || '#94a3b8',
            },
          },
        ]

        // 3. Vehicle -> Location
        if (cy.getElementById(locNodeId).length) {
          addedElements.push({
            group: 'edges',
            data: {
              id: `edge-dyn-loc-${obsId}`,
              source: obsId,
              target: locNodeId,
              label: 'OCCURRED_AT',
              color: '#10b981',
            },
          })
        }

        // 4. Vehicle -> Overspeed Hub (if overspeeding)
        if (isOver && cy.getElementById(violHubId).length) {
          addedElements.push({
            group: 'edges',
            data: {
              id: `edge-dyn-viol-${obsId}`,
              source: obsId,
              target: violHubId,
              label: 'COMMITTED_VIOLATION',
              color: '#ef4444',
            },
          })
        }

        // 5. Vehicle -> Signal Hub (if signal event)
        if (r.signalState && r.signalState !== 'Green' && cy.getElementById(signalHubId).length) {
          addedElements.push({
            group: 'edges',
            data: {
              id: `edge-dyn-sig-${obsId}`,
              source: obsId,
              target: signalHubId,
              label: 'UNDER_SIGNAL',
              color: '#f59e0b',
            },
          })
        }

        cy.add(addedElements)

        setTimeout(() => {
          if (cyRef.current && typeof cyRef.current.destroyed === 'function' && !cyRef.current.destroyed()) {
            const el = cyRef.current.getElementById(obsId)
            if (el.length) el.removeClass('live-pulse')
          }
        }, 2800)
      })

      // Update Camera properties
      if (camNode.length) {
        const p = camNode.data('properties') || {}
        const prevCount = parseInt(p['Total Ingested Detections'] || p['Total Detections Ingested'] || 0, 10) || 0
        const prevViol = parseInt(p['Speed Violations Logged'] || 0, 10) || 0
        camNode.data('properties', {
          ...p,
          'Total Ingested Detections': prevCount + newRecords.length,
          'Speed Violations Logged': prevViol + newViolationsCount,
          'Last Ingestion Heartbeat': new Date().toLocaleTimeString(),
        })
      }

      setLiveDetectionCount((prev) => prev + newRecords.length)

      const latest = newRecords[0].row
      const latestPlate = latest.numberPlate || latest.observationId || 'Vehicle'
      const latestType = latest.vehicleType || latest.type || 'Detection'
      setLatestLiveAlert(`⚡ Live capture on ${focusedCamera}: ${latestPlate} (${latestType})`)
      const timer = setTimeout(() => setLatestLiveAlert(null), 3800)
      return () => clearTimeout(timer)
    }
  }, [telemetryPool, focusMode, focusedCamera])

  function handleTriggerLiveDetection() {
    if (!focusedCamera || !cyRef.current) return
    const cy = cyRef.current
    if (typeof cy.destroyed === 'function' && cy.destroyed()) return

    const camNode = cy.getElementById(`cam-${focusedCamera}`)
    const camPos = camNode.length ? camNode.position() : { x: 400, y: 300 }
    const loc = camNode.length && camNode.data('properties') ? (camNode.data('properties')['Monitored Roadway'] || 'Outer Ring Road (NH-44 Expressway)') : 'Outer Ring Road (NH-44 Expressway)'
    const locNodeId = `loc-${loc}`
    const violHubId = 'violation-overspeed-hub'
    const signalHubId = `signal-hub-${focusedCamera}`

    const types = ['Car', 'Bike', 'Auto', 'Truck', 'Bus']
    const randomType = types[Math.floor(Math.random() * types.length)]
    const randomPlate = `TS 09 ${String.fromCharCode(65 + Math.floor(Math.random() * 26))}${String.fromCharCode(65 + Math.floor(Math.random() * 26))} ${1000 + Math.floor(Math.random() * 9000)}`
    const randomSpeed = Math.floor(40 + Math.random() * 55)
    const isOver = randomSpeed > 60
    const signalState = Math.random() > 0.82 ? 'Red' : (Math.random() > 0.65 ? 'Yellow' : 'Green')
    const obsId = `obs-dyn-${Date.now()}-${Math.floor(Math.random() * 1000)}`

    const simRow = {
      id: obsId,
      observationId: obsId,
      camera: focusedCamera,
      numberPlate: randomPlate,
      type: randomType,
      vehicleType: randomType,
      speed: randomSpeed,
      speedLimit: 60,
      overSpeed: isOver ? 'Yes' : 'No',
      isOverSpeed: isOver,
      signalState,
      timestampIst: new Date().toLocaleTimeString(),
      roadName: loc,
      location: loc,
      confidence: 0.96,
    }

    renderedObsIdsRef.current.add(obsId)

    const angle = Math.random() * Math.PI * 2
    const radius = 230 + Math.random() * 85
    const meta = getVehicleMeta(randomType)

    const domainNodeId = `type-${randomType}`
    if (!cy.getElementById(domainNodeId).length) {
      cy.add({
        group: 'nodes',
        data: {
          id: domainNodeId,
          label: `${randomType} Domain`,
          category: 'VehicleType',
          vehicleType: randomType,
          color: meta.color,
          borderColor: '#ffffff',
          properties: {
            'Classification': randomType,
            'Color': meta.color,
            'Monitored Sensor': focusedCamera,
          },
        },
        position: {
          x: camPos.x + (Math.random() - 0.5) * 260,
          y: camPos.y - 180,
        },
      })
    }

    const addedElements = [
      {
        group: 'nodes',
        data: {
          id: obsId,
          label: randomPlate,
          category: 'Observation',
          vehicleType: randomType,
          color: meta.color,
          borderColor: isOver ? '#ef4444' : '#10b981',
          rawRow: simRow,
          properties: {
            'Number Plate': randomPlate,
            'Vehicle Type': randomType,
            'Captured By': focusedCamera,
            'Monitored Road': loc,
            'Timestamp': simRow.timestampIst,
            'Speed': `${randomSpeed} km/h`,
            'Speed Limit': '60 km/h',
            'Violation Status': isOver ? '⚠️ Overspeed Violation' : 'Compliant',
            'Signal Status': signalState,
            'Dynamic Ingestion': '🟢 Real-Time Camera Stream',
          },
        },
        position: {
          x: camPos.x + Math.cos(angle) * radius,
          y: camPos.y + Math.sin(angle) * radius,
        },
        classes: 'live-pulse',
      },
      // 1. Vehicle -> Camera
      {
        group: 'edges',
        data: {
          id: `edge-dyn-cam-${obsId}`,
          source: obsId,
          target: `cam-${focusedCamera}`,
          label: 'CAPTURED_BY',
          color: '#0284c7',
        },
      },
      // 2. Vehicle -> Domain Type
      {
        group: 'edges',
        data: {
          id: `edge-dyn-type-${obsId}`,
          source: obsId,
          target: domainNodeId,
          label: 'OF_TYPE',
          color: meta.color || '#94a3b8',
        },
      },
    ]

    // 3. Vehicle -> Location
    if (cy.getElementById(locNodeId).length) {
      addedElements.push({
        group: 'edges',
        data: {
          id: `edge-dyn-loc-${obsId}`,
          source: obsId,
          target: locNodeId,
          label: 'OCCURRED_AT',
          color: '#10b981',
        },
      })
    }

    // 4. Vehicle -> Overspeed Violation Hub
    if (isOver && cy.getElementById(violHubId).length) {
      addedElements.push({
        group: 'edges',
        data: {
          id: `edge-dyn-viol-${obsId}`,
          source: obsId,
          target: violHubId,
          label: 'COMMITTED_VIOLATION',
          color: '#ef4444',
        },
      })
    }

    // 5. Vehicle -> Signal Hub
    if (signalState !== 'Green' && cy.getElementById(signalHubId).length) {
      addedElements.push({
        group: 'edges',
        data: {
          id: `edge-dyn-sig-${obsId}`,
          source: obsId,
          target: signalHubId,
          label: 'UNDER_SIGNAL',
          color: '#f59e0b',
        },
      })
    }

    cy.add(addedElements)

    // Update Camera Node properties in real time
    if (camNode.length) {
      const p = camNode.data('properties') || {}
      const prevCount = parseInt(p['Total Ingested Detections'] || p['Total Detections Ingested'] || 0, 10) || 0
      const prevViol = parseInt(p['Speed Violations Logged'] || 0, 10) || 0
      camNode.data('properties', {
        ...p,
        'Total Ingested Detections': prevCount + 1,
        'Speed Violations Logged': prevViol + (isOver ? 1 : 0),
        'Last Ingestion Heartbeat': simRow.timestampIst,
      })
    }

    setLiveDetectionCount((prev) => prev + 1)
    setLatestLiveAlert(`⚡ Live capture on ${focusedCamera}: ${randomPlate} (${randomType}) ${isOver ? `⚠️ ${randomSpeed} km/h` : ''}`)

    setTimeout(() => {
      if (cyRef.current && typeof cyRef.current.destroyed === 'function' && !cyRef.current.destroyed()) {
        const el = cyRef.current.getElementById(obsId)
        if (el.length) el.removeClass('live-pulse')
      }
    }, 2800)
    setTimeout(() => setLatestLiveAlert(null), 3800)
  }

  // Automatic stream ingestion effect when toggle is active (2.6s snappy interval)
  useEffect(() => {
    if (!autoStreamActive || focusMode !== 'CAMERA' || !focusedCamera) return
    const interval = setInterval(() => {
      handleTriggerLiveDetection()
    }, 2600)
    return () => clearInterval(interval)
  }, [autoStreamActive, focusMode, focusedCamera])

  // Viewport controls
  function handleZoomIn() {
    const cy = cyRef.current
    if (!cy) return
    cy.animate({
      zoom: { level: Math.min(3, cy.zoom() * 1.3), renderedPosition: { x: cy.width() / 2, y: cy.height() / 2 } },
      duration: 180,
    })
  }

  function handleZoomOut() {
    const cy = cyRef.current
    if (!cy) return
    cy.animate({
      zoom: { level: Math.max(0.04, cy.zoom() * 0.75), renderedPosition: { x: cy.width() / 2, y: cy.height() / 2 } },
      duration: 180,
    })
  }

  function handleFit() {
    const cy = cyRef.current
    if (!cy) return
    cy.animate({ fit: { eles: cy.elements(), padding: 50 }, duration: 260 })
  }

  function handleRelayout() {
    const cy = cyRef.current
    if (!cy) return
    cy.layout({
      ...layoutConfig,
      animate: true,
      animationDuration: 400,
      stop: () => cy.animate({ fit: { eles: cy.elements(), padding: 50 }, duration: 250 }),
    }).run()
  }

  // Calculate dynamic connected relationships directly from live Cytoscape instance
  const connectedRelationships = useMemo(() => {
    if (!selectedNode) return []
    if (cyRef.current && typeof cyRef.current.getElementById === 'function') {
      try {
        const cyNode = cyRef.current.getElementById(selectedNode.id)
        if (cyNode && cyNode.length) {
          const edges = cyNode.connectedEdges()
          if (edges && edges.length > 0) {
            return edges.map((e) => ({
              id: e.id(),
              label: e.data('label') || 'CONNECTED_TO',
              source: e.data('source'),
              target: e.data('target'),
              color: e.data('color'),
            }))
          }
        }
      } catch {
        // fallback
      }
    }
    return currentEdges
      .filter((e) => e.source === selectedNode.id || e.target === selectedNode.id)
      .map((e) => ({
        id: e.id,
        label: e.label,
        source: e.source,
        target: e.target,
        color: e.color,
      }))
  }, [selectedNode, currentEdges, liveDetectionCount])

  return (
    <div className="query-kg-container">
      {/* Knowledge Graph Toolbar */}
      <div className="query-kg-toolbar">
        <div className="query-kg-title">
          <Network className="query-kg-icon" size={18} />
          <div>
            <strong>
              {focusMode === 'VEHICLE'
                ? `Static Vehicle Forensic: ${frozenVehicle?.numberPlate || 'Vehicle'}`
                : focusMode === 'CAMERA'
                ? `Dynamic Live Stream: ${focusedCamera}`
                : `Knowledge Graph for "${queryLabel}"`}
            </strong>
            <span>
              {focusMode === 'CAMERA'
                ? `${liveDetectionCount} live detections logged · Auto-updating graph`
                : focusMode === 'VEHICLE'
                ? 'All connected entities isolated · Live updates frozen'
                : `${stats.totalQueried} matching records · ${visibleNodes.length} entities · ${visibleEdges.length} links`}
            </span>
          </div>
        </div>

        {/* Search Wrap */}
        <div className="query-kg-search-wrap">
          <Search size={14} />
          <input
            onChange={(e) => setSearchTerm(e.target.value)}
            placeholder="Search graph entities..."
            type="text"
            value={searchTerm}
          />
          {searchTerm && (
            <button onClick={() => setSearchTerm('')} type="button">
              <X size={13} />
            </button>
          )}
        </div>

        {/* Quick Mode Switcher */}
        <div className="kg-mode-pills-group">
          <button
            className={`kg-mode-pill ${focusMode === 'ALL' ? 'active' : ''}`}
            onClick={handleExitFocusMode}
            title="View all queried telemetry nodes"
            type="button"
          >
            <Network size={12} />
            <span>Queried Subgraph</span>
          </button>

          <button
            className={`kg-mode-pill ${focusMode === 'CAMERA' ? 'active-dynamic' : ''}`}
            onClick={() => {
              if (availableCameras[0]) handleSelectCamera(availableCameras[0])
            }}
            title="Dynamic live camera hub (auto-updates in real time)"
            type="button"
          >
            <Radio size={12} />
            <span>Dynamic Camera</span>
          </button>
        </div>

        {/* Category Filters (In ALL mode) */}
        {focusMode === 'ALL' && (
          <div className="query-kg-cat-filters">
            {['ALL', 'Location', 'Camera', 'VehicleType', 'Observation'].map((cat) => (
              <button
                className={`query-kg-cat-btn ${activeCategory === cat ? 'active' : ''}`}
                key={cat}
                onClick={() => setActiveCategory(cat)}
                type="button"
              >
                {cat === 'ALL' ? 'All' : cat === 'VehicleType' ? 'Type' : cat}
              </button>
            ))}
          </div>
        )}

        {/* Segregation Toggle Button (In ALL mode) */}
        {focusMode === 'ALL' && (
          <button
            className={`kg-segregation-toggle ${segregatedView ? 'active' : ''}`}
            onClick={() => setSegregatedView(!segregatedView)}
            title="Toggle segregated type clusters"
            type="button"
          >
            <Layers size={13} />
            <span>{segregatedView ? 'Segregated' : 'Free Net'}</span>
          </button>
        )}

        {/* Zoom & Fit Actions */}
        <div className="query-kg-actions">
          <button onClick={handleZoomIn} title="Zoom in" type="button">
            <Plus size={16} />
          </button>
          <button onClick={handleZoomOut} title="Zoom out" type="button">
            <Minus size={16} />
          </button>
          <button onClick={handleFit} title="Fit graph" type="button">
            <Maximize size={15} />
          </button>
          <button onClick={handleRelayout} title="Re-layout graph" type="button">
            <RefreshCw size={15} />
          </button>
          {onClose && (
            <button className="query-kg-close-btn" onClick={onClose} title="Close graph" type="button">
              <X size={16} />
            </button>
          )}
        </div>
      </div>

      {/* Mode Banners */}
      {focusMode === 'VEHICLE' && frozenVehicle && (
        <div className="kg-mode-banner kg-mode-banner-static">
          <div className="kg-mode-banner-left">
            <ShieldCheck size={20} />
            <div>
              <strong>
                Vehicle Forensic Inspection: {frozenVehicle.numberPlate || frozenVehicle.observationId || 'Inspected Vehicle'}
              </strong>
              <p>
                Displaying what all is connected (Camera, Roadway, Domain Classification, Violations). Live telemetry updates are paused for this vehicle so graph remains 100% static.
              </p>
            </div>
          </div>
          <div className="kg-mode-banner-right">
            <button className="kg-mode-exit-btn" onClick={handleExitFocusMode} type="button">
              <X size={14} />
              <span>Exit Static View</span>
            </button>
          </div>
        </div>
      )}

      {focusMode === 'CAMERA' && focusedCamera && (
        <div className="kg-mode-banner kg-mode-banner-dynamic">
          <div className="kg-mode-banner-left">
            <span className="kg-live-dot pulse" />
            <div>
              <strong>🟢 Dynamic Live Camera Stream: {focusedCamera}</strong>
              <p>
                Active real-time hub. Whenever new data is detected by this camera, it will dynamically update and attach to this graph in real time.
              </p>
            </div>
          </div>
          <div className="kg-mode-banner-right">
            <span className="kg-live-counter">
              <Activity size={13} />
              {liveDetectionCount} Detections Logged
            </span>
            <button className="kg-mode-exit-btn" onClick={handleExitFocusMode} type="button">
              <X size={14} />
              <span>Exit Live Stream</span>
            </button>
          </div>
        </div>
      )}

      {/* All Cameras Network Banner */}
      {(isAllCameras || (submittedQuery && (submittedQuery.toLowerCase().includes('all camera') || submittedQuery.toLowerCase().includes('cameras')))) && focusMode === 'ALL' && (
        <div className="kg-mode-banner" style={{ background: 'linear-gradient(135deg, #f0fdf4 0%, #eff6ff 100%)', border: '1.5px solid #059669', color: '#064e3b' }}>
          <div className="kg-mode-banner-left">
            <Camera size={20} style={{ color: '#059669' }} />
            <div>
              <strong>📹 Surveillance Camera Network ({availableCameras.length} Active Stations)</strong>
              <p>
                Displaying all monitoring cameras across the corridor network and their connected roadways. Click any camera below to stream live telemetry dynamically.
              </p>
            </div>
          </div>
          <div className="kg-mode-banner-right">
            <span className="kg-live-counter" style={{ background: '#ecfdf5', color: '#065f46' }}>
              <Activity size={13} /> {availableCameras.length} Stations Online
            </span>
          </div>
        </div>
      )}

      {/* Quick Select Bar for Cameras & Recent Vehicles */}
      <div className="kg-quick-modes-bar">
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
          <span style={{ fontSize: '11px', fontWeight: 700, color: '#64748b', display: 'inline-flex', alignItems: 'center', gap: '4px' }}>
            <Camera size={13} style={{ color: '#059669' }} /> Stream Camera:
          </span>
          {availableCameras.slice(0, 5).map((cam) => {
            const isActive = focusMode === 'CAMERA' && focusedCamera === cam
            return (
              <button
                key={cam}
                onClick={() => handleSelectCamera(cam)}
                style={{
                  border: isActive ? '1.5px solid #059669' : '1px solid #cbd5e1',
                  background: isActive ? '#ecfdf5' : '#ffffff',
                  color: isActive ? '#065f46' : '#334155',
                  fontWeight: isActive ? 700 : 500,
                  borderRadius: '6px',
                  padding: '3px 8px',
                  fontSize: '11px',
                  cursor: 'pointer',
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '4px',
                }}
                type="button"
              >
                <span style={{ width: 6, height: 6, borderRadius: '50%', background: isActive ? '#10b981' : '#94a3b8' }} />
                {cam}
              </button>
            )
          })}
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
          <span style={{ fontSize: '11px', fontWeight: 700, color: '#64748b', display: 'inline-flex', alignItems: 'center', gap: '4px' }}>
            <Lock size={12} style={{ color: '#0284c7' }} /> Inspect Vehicle:
          </span>
          {sampleVehicles.slice(0, 4).map((vh) => {
            const plate = vh.numberPlate || vh.vehicleNumberPlate || vh.observationId
            const isActive = focusMode === 'VEHICLE' && (frozenVehicle?.numberPlate === plate || frozenVehicle?.observationId === plate)
            return (
              <button
                key={plate}
                onClick={() => handleSelectVehicle(vh)}
                style={{
                  border: isActive ? '1.5px solid #0284c7' : '1px solid #cbd5e1',
                  background: isActive ? '#f0f9ff' : '#ffffff',
                  color: isActive ? '#0369a1' : '#334155',
                  fontWeight: isActive ? 700 : 500,
                  borderRadius: '6px',
                  padding: '3px 8px',
                  fontSize: '11px',
                  cursor: 'pointer',
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '4px',
                }}
                type="button"
              >
                <Car size={11} style={{ color: '#0284c7' }} />
                {plate}
              </button>
            )
          })}
        </div>
      </div>

      {/* Domain Color Legend (In ALL mode) */}
      {focusMode === 'ALL' && domainBreakdown.length > 0 && (
        <div className="kg-domain-bar">
          <div className="kg-domain-bar-left">
            <span className="kg-domain-title">
              <Sparkles className="kg-domain-icon" size={13} />
              Vehicle Domains:
            </span>
            <div className="kg-domain-pills">
              <button
                className={`kg-domain-pill ${vehicleDomainFilter === 'ALL' ? 'active' : ''}`}
                onClick={() => setVehicleDomainFilter('ALL')}
                type="button"
              >
                <span className="kg-swatch-all" />
                <span>All Domains ({rows.length})</span>
              </button>
              {domainBreakdown.map((item) => {
                const isActive = vehicleDomainFilter.toLowerCase() === item.label.toLowerCase()
                return (
                  <button
                    className={`kg-domain-pill ${isActive ? 'active' : ''}`}
                    key={item.label}
                    onClick={() => setVehicleDomainFilter(isActive ? 'ALL' : item.label)}
                    style={{
                      borderColor: isActive ? item.color : '#e2e8f0',
                      backgroundColor: isActive ? item.bg : '#ffffff',
                    }}
                    title={`Show all ${item.label}s (${item.count} detections)`}
                    type="button"
                  >
                    <span className="kg-domain-dot" style={{ backgroundColor: item.color }} />
                    <span className="kg-domain-name">{item.label}s</span>
                    <span
                      className="kg-domain-count"
                      style={{
                        backgroundColor: isActive ? item.color : '#f1f5f9',
                        color: isActive ? '#ffffff' : '#475569',
                      }}
                    >
                      {item.count}
                    </span>
                  </button>
                )
              })}
            </div>
          </div>
          {vehicleDomainFilter !== 'ALL' && (
            <button className="kg-domain-reset-btn" onClick={() => setVehicleDomainFilter('ALL')} type="button">
              <X size={12} />
              <span>Show All Vehicles</span>
            </button>
          )}
        </div>
      )}

      {/* Graph Canvas & Side Drawer */}
      <div className="query-kg-canvas-wrapper">
        <div className="query-kg-cy" ref={containerRef} />

        {/* Real-time Dynamic Detection Toast */}
        {latestLiveAlert && (
          <div className="kg-live-toast">
            <Zap size={14} style={{ color: '#34d399' }} />
            <span>{latestLiveAlert}</span>
          </div>
        )}

        <div className="query-kg-watermark">
          {focusMode === 'VEHICLE' ? (
            <>
              <Lock size={14} style={{ color: '#0284c7' }} />
              <span>Static Vehicle Forensic (All Connected Entities Isolated)</span>
            </>
          ) : focusMode === 'CAMERA' ? (
            <>
              <span className="kg-live-dot pulse" style={{ width: 8, height: 8 }} />
              <span>Dynamic Live Camera Stream ({focusedCamera})</span>
            </>
          ) : (
            <>
              <Network size={14} />
              <span>Queried Telemetry Knowledge Graph · Cytoscape Engine</span>
            </>
          )}
        </div>

        {/* Node Properties Drawer */}
        {selectedNode && (
          <div className="query-kg-drawer">
            <div className="query-kg-drawer-header">
              <div
                className="query-kg-drawer-badge"
                style={{
                  backgroundColor: selectedNode.color || '#2563eb',
                  color: selectedNode.category === 'Group' ? '#0f172a' : '#ffffff',
                  border: selectedNode.category === 'Group' ? '1px solid rgba(0,0,0,0.1)' : 'none',
                }}
              >
                {selectedNode.category === 'Observation'
                  ? `${selectedNode.vehicleType || 'Vehicle'} · Detection`
                  : selectedNode.category === 'Group'
                  ? 'Domain Cluster'
                  : selectedNode.category}
              </div>
              <button
                className="query-kg-drawer-close"
                onClick={() => setSelectedNode(null)}
                type="button"
              >
                <X size={15} />
              </button>
            </div>

            <h3 className="query-kg-drawer-title">{selectedNode.label}</h3>
            <span className="query-kg-drawer-id">ID: {selectedNode.id}</span>

            {/* Mode Switching Shortcuts from Drawer */}
            {selectedNode.category === 'Observation' && focusMode !== 'VEHICLE' && selectedNode.rawRow && (
              <div style={{ marginTop: '10px' }}>
                <button
                  onClick={() => handleSelectVehicle(selectedNode.rawRow)}
                  style={{
                    width: '100%',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    gap: '6px',
                    padding: '8px 12px',
                    background: '#0284c7',
                    color: '#ffffff',
                    border: 'none',
                    borderRadius: '6px',
                    fontSize: '12px',
                    fontWeight: 600,
                    cursor: 'pointer',
                  }}
                  type="button"
                >
                  <Lock size={13} />
                  <span>Isolate Connected Graph (Static)</span>
                </button>
              </div>
            )}

            {selectedNode.category === 'Camera' && focusMode !== 'CAMERA' && (
              <div style={{ marginTop: '10px' }}>
                <button
                  onClick={() => handleSelectCamera(selectedNode.label.replace(/^Camera:\s*/, ''))}
                  style={{
                    width: '100%',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    gap: '6px',
                    padding: '8px 12px',
                    background: '#059669',
                    color: '#ffffff',
                    border: 'none',
                    borderRadius: '6px',
                    fontSize: '12px',
                    fontWeight: 600,
                    cursor: 'pointer',
                  }}
                  type="button"
                >
                  <Radio size={13} />
                  <span>Stream Camera Telemetry (Dynamic)</span>
                </button>
              </div>
            )}

            {selectedNode.image && (
              <div
                style={{
                  background: '#0f172a',
                  borderRadius: '10px',
                  padding: '8px',
                  margin: '10px 0 14px 0',
                  border: '1px solid #334155',
                }}
              >
                <div
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    marginBottom: '6px',
                    fontSize: '11px',
                    color: '#94a3b8',
                  }}
                >
                  <span style={{ display: 'inline-flex', alignItems: 'center', gap: '4px' }}>
                    <Camera size={12} /> Surveillance Capture
                  </span>
                  {selectedNode.hasExtractedImage && (
                    <span
                      style={{
                        background: '#064e3b',
                        color: '#34d399',
                        padding: '1px 6px',
                        borderRadius: '8px',
                        fontSize: '10px',
                        fontWeight: 600,
                        display: 'inline-flex',
                        alignItems: 'center',
                        gap: '3px',
                      }}
                    >
                      <Sparkles size={10} /> XLSX Extracted
                    </span>
                  )}
                </div>
                <div
                  onClick={() => selectedNode.rawRow && setPreviewModalRow(selectedNode.rawRow)}
                  style={{
                    cursor: 'pointer',
                    position: 'relative',
                    borderRadius: '6px',
                    overflow: 'hidden',
                    maxHeight: '140px',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    background: '#020617',
                  }}
                  title="Click to open high-resolution surveillance modal"
                >
                  <img
                    alt={selectedNode.label}
                    src={selectedNode.image}
                    style={{ width: '100%', height: 'auto', display: 'block', objectFit: 'contain' }}
                  />
                  <div
                    style={{
                      position: 'absolute',
                      bottom: '4px',
                      right: '4px',
                      background: 'rgba(15, 23, 42, 0.85)',
                      color: '#ffffff',
                      padding: '2px 6px',
                      borderRadius: '4px',
                      fontSize: '10px',
                      display: 'inline-flex',
                      alignItems: 'center',
                      gap: '3px',
                    }}
                  >
                    <Eye size={10} /> Click to Inspect
                  </div>
                </div>
              </div>
            )}

            <div className="query-kg-drawer-section">
              <h4>Entity Properties</h4>
              <div className="query-kg-prop-list">
                {Object.entries(selectedNode.properties || {}).map(([k, v]) => (
                  <div className="query-kg-prop-row" key={k}>
                    <span>{k}</span>
                    <strong>{String(v)}</strong>
                  </div>
                ))}
              </div>
            </div>

            <div className="query-kg-drawer-section">
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                <h4 style={{ margin: 0 }}>Direct Relationships</h4>
                <span style={{ fontSize: '11px', color: '#0284c7', fontWeight: 700, background: '#f0f9ff', padding: '2px 8px', borderRadius: '12px', border: '1px solid #bae6fd' }}>
                  {connectedRelationships.length} Connected
                </span>
              </div>
              <div className="query-kg-rel-list">
                {connectedRelationships.map((e) => (
                  <div className="query-kg-rel-item" key={e.id}>
                    <span className="query-kg-rel-badge" style={{ backgroundColor: e.color || undefined }}>{e.label}</span>
                    <span className="query-kg-rel-node" title={e.source === selectedNode.id ? e.target : e.source}>
                      {e.source === selectedNode.id ? `→ ${e.target}` : `← ${e.source}`}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}
      </div>

      {previewModalRow && (
        <MediaPreviewModal
          allRows={rows}
          isOpen={Boolean(previewModalRow)}
          onClose={() => setPreviewModalRow(null)}
          onSelectRow={setPreviewModalRow}
          row={previewModalRow}
        />
      )}
    </div>
  )
}
