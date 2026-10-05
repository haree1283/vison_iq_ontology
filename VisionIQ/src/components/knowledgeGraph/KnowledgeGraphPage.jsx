import { useEffect, useMemo, useRef, useState } from 'react'
import { useLocation } from 'react-router-dom'
import cytoscape from 'cytoscape'
import {
  Activity,
  AlertTriangle,
  Bot,
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
import { getCanonicalVehicleDomain, getVehicleMeta, isVehicleTypeMatch } from '../../data/vehicleTypes'
import MediaPreviewModal from '../MediaPreviewModal'

export default function KnowledgeGraphPage({
  rows = [],
  fileName = 'Active Dataset',
  hideFilters = false,
  isQueryEmbedded = false,
}) {
  const location = useLocation()
  const shouldHideFilters = hideFilters || isQueryEmbedded

  // Support AI Queried Knowledge Graph Segment passed from Query Page
  const [segmentFilter, setSegmentFilter] = useState(() => location.state?.queryFilter || null)
  const [segmentExplanation, setSegmentExplanation] = useState(() => location.state?.explanation || '')

  // Primary Modes: 'ALL' | 'VEHICLE' | 'CAMERA'
  const [focusMode, setFocusMode] = useState('ALL')
  // Static frozen snapshot of vehicle (will NEVER change on incoming live rows)
  const [frozenVehicle, setFrozenVehicle] = useState(null)
  // Dynamic camera hub identifier
  const [focusedCamera, setFocusedCamera] = useState(null)
  const [liveDetectionCount, setLiveDetectionCount] = useState(0)
  const [latestLiveAlert, setLatestLiveAlert] = useState(null)
  const [autoStreamActive, setAutoStreamActive] = useState(false)

  // Live dynamic streaming extra counts per vehicle domain
  const [dynamicExtraByType, setDynamicExtraByType] = useState({})

  // Clear dynamic counts when changing camera or focus mode
  useEffect(() => {
    setDynamicExtraByType({})
  }, [focusedCamera, focusMode])

  // Track known observation IDs already rendered in dynamic camera mode
  const renderedObsIdsRef = useRef(new Set())

  // Dynamic active rows (for ALL or CAMERA mode)
  const activeRows = useMemo(() => {
    if (!segmentFilter) return rows
    return rows.filter((r) => {
      if (segmentFilter.vehicleTypes || segmentFilter.vehicleType) {
        const rawTypes = []
        if (Array.isArray(segmentFilter.vehicleTypes)) rawTypes.push(...segmentFilter.vehicleTypes)
        if (Array.isArray(segmentFilter.vehicleType)) rawTypes.push(...segmentFilter.vehicleType)
        else if (typeof segmentFilter.vehicleType === 'string') rawTypes.push(segmentFilter.vehicleType)
        if (rawTypes.length) {
          const matchType = rawTypes.some((t) => isVehicleTypeMatch(r.vehicleType || r.type, t))
          if (!matchType) return false
        }
      }
      if (segmentFilter.location) {
        const loc = (r.roadName || r.location || '').toLowerCase().trim()
        const target = String(Array.isArray(segmentFilter.location) ? segmentFilter.location[0] : segmentFilter.location).toLowerCase().trim()
        if (target && !loc.includes(target) && !target.includes(loc)) {
          const targetWords = target.split(/\s+/).filter((w) => w.length > 2)
          if (!targetWords.some((w) => loc.includes(w))) return false
        }
      }
      if (segmentFilter.camera) {
        const cam = String(r.camera || '').toLowerCase().replace(/[^a-z0-9]/g, '')
        const targetCam = String(Array.isArray(segmentFilter.camera) ? segmentFilter.camera[0] : segmentFilter.camera).toLowerCase().replace(/[^a-z0-9]/g, '')
        if (cam && targetCam && !cam.includes(targetCam) && !targetCam.includes(cam)) return false
      }
      if (segmentFilter.signalState && (r.signalState || '').toLowerCase() !== String(segmentFilter.signalState).toLowerCase()) return false
      if (segmentFilter.weather && !(r.weather || '').toLowerCase().includes(String(segmentFilter.weather).toLowerCase())) return false
      if (segmentFilter.overspeedOnly && !(r.overSpeed === 'Yes' || r.isOverSpeed || (r.speed && r.speedLimit && r.speed > r.speedLimit))) return false
      if (segmentFilter.minSpeed !== null && segmentFilter.minSpeed !== undefined && (r.speed || 0) < Number(segmentFilter.minSpeed)) return false
      if (segmentFilter.maxSpeed !== null && segmentFilter.maxSpeed !== undefined && (r.speed || 0) > Number(segmentFilter.maxSpeed)) return false
      if (segmentFilter.plateSearch) {
        const plate = (r.numberPlate || r.vehicleNumberPlate || '').toUpperCase()
        if (!plate.includes(String(segmentFilter.plateSearch).toUpperCase())) return false
      }
      return true
    })
  }, [rows, segmentFilter])

  // Clear renderedObsIds when camera changes
  useEffect(() => {
    renderedObsIdsRef.current = new Set()
  }, [focusedCamera])

  // Standard graph state
  const [searchTerm, setSearchTerm] = useState('')
  const [showSuggestions, setShowSuggestions] = useState(false)
  const [activeCategory, setActiveCategory] = useState('ALL')
  const [vehicleDomainFilter, setVehicleDomainFilter] = useState('ALL')
  const [segregatedView, setSegregatedView] = useState(true)
  const [selectedNode, setSelectedNode] = useState(null)
  const [previewModalRow, setPreviewModalRow] = useState(null)
  const [recordLimit, setRecordLimit] = useState('ALL')
  const containerRef = useRef(null)
  const cyRef = useRef(null)
  const pinnedNodeRef = useRef(null) // tracks the currently click-selected node id

  // Distinct camera list for quick selection
  const allCameras = useMemo(() => {
    return Array.from(new Set(rows.map((r) => r.camera).filter(Boolean)))
  }, [rows])

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
    const qNorm = q.replace(/[^a-z0-9]/g, '')

    const matchedCameras = allCameras
      .filter((cam) => {
        const cLower = cam.toLowerCase()
        const cNorm = cLower.replace(/[^a-z0-9]/g, '')
        if (cLower.includes(q)) return true
        if (qNorm.length >= 2 && (cNorm.includes(qNorm) || qNorm.includes(cNorm))) return true
        const numMatch = q.match(/\d+/)
        if (numMatch && (q.includes('cam') || q.includes('camera'))) {
          const num = parseInt(numMatch[0], 10)
          const camNumMatch = cam.match(/\d+/)
          if (camNumMatch && parseInt(camNumMatch[0], 10) === num) return true
        }
        return false
      })
      .slice(0, 6)

    const matchedVehicles = rows
      .filter((r) => {
        const plate = (r.numberPlate || r.vehicleNumberPlate || '').toLowerCase()
        const id = String(r.observationId || r.id || '').toLowerCase()
        return plate.includes(q) || id.includes(q)
      })
      .slice(0, 6)

    return { cameras: matchedCameras, vehicles: matchedVehicles }
  }, [searchTerm, allCameras, rows])

  // Compute breakdown of vehicle types for the domain color legend
  const domainBreakdown = useMemo(() => {
    const counts = {}
    const standardDomains = ['Car', 'Bike', 'Truck', 'Auto', 'Van', 'Bus']
    standardDomains.forEach((dom) => {
      const meta = getVehicleMeta(dom)
      const label = dom === 'Bus' ? 'Buss' : `${dom}s`
      counts[dom] = {
        label,
        rawType: dom,
        count: 0,
        color: meta.color,
        bg: meta.bg,
        border: meta.border,
      }
    })

    activeRows.forEach((r) => {
      const rawType = r.vehicleType || r.type || 'Car'
      const domain = getCanonicalVehicleDomain(rawType)
      const meta = getVehicleMeta(domain)
      if (!counts[domain]) {
        counts[domain] = {
          label: domain === 'Bus' ? 'Buss' : `${domain}s`,
          rawType: domain,
          count: 0,
          color: meta.color,
          bg: meta.bg,
          border: meta.border,
        }
      }
      counts[domain].count += 1
    })

    // Accumulate streamed detections
    Object.entries(dynamicExtraByType).forEach(([dom, extra]) => {
      if (counts[dom]) {
        counts[dom].count += extra
      }
    })

    return Object.values(counts).sort((a, b) => b.count - a.count)
  }, [activeRows, dynamicExtraByType])

  // Total count across all vehicle domains including dynamic captures
  const totalAllDomainsCount = useMemo(() => {
    const base = activeRows.length
    const extra = Object.values(dynamicExtraByType).reduce((acc, v) => acc + v, 0)
    return base + extra
  }, [activeRows.length, dynamicExtraByType])

  // Switch to Static Vehicle Mode
  function handleSelectVehicle(vehicleRow) {
    if (!vehicleRow) return
    const plate = vehicleRow.numberPlate || vehicleRow.vehicleNumberPlate || vehicleRow.observationId || vehicleRow.id
    setFocusMode('VEHICLE')
    setFrozenVehicle(vehicleRow)
    setFocusedCamera(null)
    setSearchTerm('')
    setShowSuggestions(false)

    // Pre-populate inspector with this vehicle
    const domain = getCanonicalVehicleDomain(vehicleRow.vehicleType || vehicleRow.type)
    const meta = getVehicleMeta(domain)
    setSelectedNode({
      id: vehicleRow.observationId ? `obs-${vehicleRow.observationId}` : `obs-${vehicleRow.id || plate}`,
      label: plate,
      category: 'Observation',
      vehicleType: domain,
      color: meta.color,
      image: vehicleRow.extractedImage || vehicleRow.vehicleImageDataUrl,
      hasExtractedImage: vehicleRow.hasExtractedImage,
      rawRow: vehicleRow,
      properties: {
        'Number Plate': plate,
        'Vehicle Domain': domain,
        'Timestamp (IST)': vehicleRow.timestampIst || vehicleRow.timestamp || 'N/A',
        'Captured By': vehicleRow.camera || 'N/A',
        'Location': vehicleRow.location || vehicleRow.roadName || 'N/A',
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
    const currentCamRows = activeRows.filter((r) => r.camera === camId)
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
        'Assigned Location': currentCamRows[0]?.location || currentCamRows[0]?.roadName || 'Outer Ring Road (NH-44 Expressway)',
        'Total Ingested Detections': currentCamRows.length,
        'Streaming Status': '🟢 Ingesting Real-Time Dynamic Telemetry',
      },
    })
  }

  // Exit back to Full Network Graph
  function handleExitFocusMode() {
    setFocusMode('ALL')
    setFrozenVehicle(null)
    setFocusedCamera(null)
    setAutoStreamActive(false)
    setLatestLiveAlert(null)
    setSelectedNode(null)
  }

  // Initialize camera or vehicle mode if passed via navigation location.state
  useEffect(() => {
    if (location.state?.camera) {
      handleSelectCamera(location.state.camera)
    } else if (location.state?.queryFilter?.camera) {
      const cam = Array.isArray(location.state.queryFilter.camera)
        ? location.state.queryFilter.camera[0]
        : location.state.queryFilter.camera
      if (cam) handleSelectCamera(cam)
    } else if (location.state?.vehicle) {
      handleSelectVehicle(location.state.vehicle)
    }
  }, [location.state])

  // Construct graph elements depending on mode
  const { currentNodes, currentEdges, stats } = useMemo(() => {
    let edgeIndex = 1

    // =========================================================================
    // 1. STATIC VEHICLE FORENSIC MODE
    // =========================================================================
    if (focusMode === 'VEHICLE' && frozenVehicle) {
      const v = frozenVehicle
      const obsId = v.observationId ? `obs-${v.observationId}` : `obs-${v.id || v.numberPlate}`
      const obsLabel = v.numberPlate && v.numberPlate !== 'N/A' ? v.numberPlate : (v.observationId || 'Vehicle')
      const domain = getCanonicalVehicleDomain(v.vehicleType || v.type)
      const meta = getVehicleMeta(domain)
      const loc = v.location || v.roadName || 'Monitored Corridor'
      const cam = v.camera || 'Surveillance Unit'
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
          image: v.extractedImage || v.vehicleImageDataUrl,
          hasExtractedImage: v.hasExtractedImage,
          rawRow: v,
          properties: {
            'Number Plate': obsLabel,
            'Vehicle Type': domain,
            'Captured By': cam,
            'Location': loc,
            'Speed': `${v.speed || 0} km/h`,
            'Speed Limit': `${v.speedLimit || 60} km/h`,
            'Violation': isOverSpeed ? '⚠️ Overspeed Violation' : 'Compliant',
            'Timestamp': v.timestampIst || v.timestamp || 'N/A',
            'Confidence': `${Math.round(((v.plateConfidence || v.confidence) > 1 ? (v.plateConfidence || v.confidence) : (v.plateConfidence || v.confidence || 0.95) * 100))}%`,
            'Coordinates': `${v.latitude?.toFixed?.(4) || '17.4485'}, ${v.longitude?.toFixed?.(4) || '78.3742'}`,
          },
        },
        // Connected Camera Node
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
        // Connected Location Node
        {
          id: `loc-${loc}`,
          label: `Location: ${loc}`,
          category: 'Location',
          color: '#10b981',
          borderColor: '#ffffff',
          properties: {
            'Monitored Zone': loc,
            'Coordinates': `${v.latitude?.toFixed?.(4) || '17.4485'}, ${v.longitude?.toFixed?.(4) || '78.3742'}`,
          },
        },
        // Connected Vehicle Domain Node
        {
          id: `type-${domain}`,
          label: `${domain} Domain`,
          category: 'VehicleType',
          vehicleType: domain,
          color: meta.color,
          borderColor: '#ffffff',
          properties: {
            'Vehicle Classification': domain,
            'Domain Color': meta.color,
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
            'Violation Type': 'Speed Limit Exceeded',
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
          label: `Signal State: ${v.signalState}`,
          category: 'Signal',
          color: v.signalState === 'Red' ? '#dc2626' : '#d97706',
          borderColor: '#ffffff',
          properties: {
            'Signal Light': v.signalState,
            'Junction': v.junctionId || 'Corridor Junction',
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
        stats: { cameras: 1, locations: 1, types: 1, observations: 1, totalDatasetRows: activeRows.length },
      }
    }

    // =========================================================================
    // 2. SEGREGATED CLUSTERED GRAPH MODE ('ALL' & 'CAMERA')
    // Both modes use the exact segregated domain bounding boxes layout (cose)
    // =========================================================================
    if (!activeRows || !activeRows.length) {
      return { currentNodes: [], currentEdges: [], stats: { cameras: 0, locations: 0, types: 0, observations: 0, totalDatasetRows: 0 } }
    }

    const standardDomains = ['Car', 'Bike', 'Truck', 'Auto', 'Van', 'Bus']
    const rowDomains = Array.from(new Set(activeRows.map((r) => getCanonicalVehicleDomain(r.vehicleType || r.type)).filter(Boolean)))
    const domains = Array.from(new Set([...standardDomains, ...rowDomains]))

    const cameras = Array.from(new Set(activeRows.map((r) => r.camera).filter(Boolean)))
    if (focusMode === 'CAMERA' && focusedCamera && !cameras.includes(focusedCamera)) {
      cameras.push(focusedCamera)
    }

    const locations = Array.from(new Set(activeRows.map((r) => r.location || r.roadName).filter(Boolean)))
    if (locations.length === 0) {
      locations.push('Outer Ring Road (NH-44 Expressway)')
    }

    const nodes = []
    const edges = []

    if (segregatedView) {
      domains.forEach((domain) => {
        const meta = getVehicleMeta(domain)
        const typeRows = activeRows.filter((r) => getCanonicalVehicleDomain(r.vehicleType || r.type) === domain)
        nodes.push({
          id: `group-type-${domain}`,
          label: `${domain.toUpperCase()} DOMAIN · ${typeRows.length} RECORDS`,
          category: 'Group',
          vehicleType: domain,
          color: meta.bg || '#eff6ff',
          borderColor: meta.color || '#2563eb',
          isGroup: true,
          properties: {
            'Cluster Domain': `${domain} Domain`,
            'Total Vehicles': typeRows.length,
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
          label: `MONITORED LOCATIONS · ${locations.length} ZONES`,
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

      // Check for Violations & Signal states in active records
      const overSpeedRows = activeRows.filter((r) => r.overSpeed === 'Yes' || r.isOverSpeed || (r.speed && r.speedLimit && Number(r.speed) > Number(r.speedLimit)))
      const signalRows = activeRows.filter((r) => r.signalState)
      const signalStatesPresent = Array.from(new Set(signalRows.map((r) => r.signalState).filter(Boolean)))

      if (overSpeedRows.length > 0) {
        nodes.push({
          id: 'group-violations',
          label: `⚠️ OVER SPEED VIOLATIONS · ${overSpeedRows.length} INCIDENTS`,
          category: 'Group',
          color: '#fef2f2',
          borderColor: '#ef4444',
          isGroup: true,
          properties: {
            'Cluster Domain': 'Speed Violations',
            'Total Incidents': overSpeedRows.length,
          },
        })
      }

      if (signalStatesPresent.length > 0) {
        nodes.push({
          id: 'group-signals',
          label: `🚥 TRAFFIC SIGNALS & LIGHTS · ${signalStatesPresent.length} STATES`,
          category: 'Group',
          color: '#fffbe0',
          borderColor: '#d97706',
          isGroup: true,
          properties: {
            'Cluster Domain': 'Traffic Signals',
            'Active Signal States': signalStatesPresent.length,
          },
        })
      }
    }

    // Locations
    locations.forEach((loc) => {
      const locRows = activeRows.filter((r) => (r.location || r.roadName) === loc)
      nodes.push({
        id: `loc-${loc}`,
        label: loc,
        category: 'Location',
        color: '#10b981',
        borderColor: '#ffffff',
        parent: segregatedView ? 'group-locations' : undefined,
        properties: {
          'Monitored Road': loc,
          'Active Records': locRows.length,
        },
      })
    })

    // Cameras
    cameras.forEach((cam) => {
      const camRows = activeRows.filter((r) => r.camera === cam)
      const loc = camRows[0]?.location || camRows[0]?.roadName || locations[0] || 'Unknown'
      const isFocused = focusMode === 'CAMERA' && focusedCamera === cam
      nodes.push({
        id: `cam-${cam}`,
        label: cam,
        category: 'Camera',
        color: isFocused ? '#0f172a' : '#475569',
        borderColor: isFocused ? '#10b981' : '#ffffff',
        isCenter: isFocused,
        parent: segregatedView ? 'group-cameras' : undefined,
        properties: {
          'Assigned Location': loc,
          'Frames Captured': camRows.length,
          'Streaming Status': isFocused ? '🟢 Live Telemetry Stream Active (Dynamic)' : 'Standby Surveillance',
        },
      })
      if (loc && loc !== 'Unknown') {
        edges.push({
          id: `edge-${edgeIndex++}`,
          source: `cam-${cam}`,
          target: `loc-${loc}`,
          label: 'MONITORS',
          color: '#94a3b8',
        })
      }
    })

    // Vehicle Domains
    domains.forEach((domain) => {
      const typeRows = activeRows.filter((r) => getCanonicalVehicleDomain(r.vehicleType || r.type) === domain)
      const meta = getVehicleMeta(domain)
      nodes.push({
        id: `type-${domain}`,
        label: domain,
        category: 'VehicleType',
        vehicleType: domain,
        color: meta.color,
        borderColor: '#ffffff',
        parent: segregatedView ? `group-type-${domain}` : undefined,
        properties: {
          'Vehicle Domain': domain,
          'Total Detections': typeRows.length,
        },
      })
    })

    // Violation Nodes (Overspeeding)
    const overSpeedRowsAll = activeRows.filter((r) => r.overSpeed === 'Yes' || r.isOverSpeed || (r.speed && r.speedLimit && Number(r.speed) > Number(r.speedLimit)))
    if (overSpeedRowsAll.length > 0) {
      nodes.push({
        id: 'violation-overspeed',
        label: '⚠️ Overspeed Violation',
        category: 'Violation',
        color: '#ef4444',
        borderColor: '#ffffff',
        parent: segregatedView ? 'group-violations' : undefined,
        properties: {
          'Violation Name': 'Speed Limit Exceeded',
          'Total Violating Vehicles': overSpeedRowsAll.length,
          'Risk Level': 'HIGH',
        },
      })
    }

    // Signal Nodes (Red, Yellow, Green)
    const signalStatesPresentAll = Array.from(new Set(activeRows.map((r) => r.signalState).filter(Boolean)))
    signalStatesPresentAll.forEach((state) => {
      const stateRows = activeRows.filter((r) => r.signalState === state)
      const sigColor = state === 'Red' ? '#dc2626' : state === 'Yellow' ? '#d97706' : '#10b981'
      const sigLabel = state === 'Red' ? '🔴 Red Signal (Stop)' : state === 'Yellow' ? '🟡 Yellow Signal (Caution)' : '🟢 Green Signal (Go)'
      nodes.push({
        id: `signal-${state}`,
        label: sigLabel,
        category: 'Signal',
        color: sigColor,
        borderColor: '#ffffff',
        parent: segregatedView ? 'group-signals' : undefined,
        properties: {
          'Signal State': state,
          'Total Monitored Vehicles': stateRows.length,
        },
      })
    })

    // Observations
    const targetRows = recordLimit === 'ALL'
      ? activeRows
      : activeRows.slice(0, Math.min(Number(recordLimit) || activeRows.length, activeRows.length))

    targetRows.forEach((row, i) => {
      const obsId = row.observationId ? `obs-${row.observationId}` : `obs-${row.id || i + 1}`
      const obsLabel = (row.numberPlate && row.numberPlate !== 'N/A' && row.numberPlate !== 'Unknown')
        ? row.numberPlate
        : (row.observationId || row.id || `Record #${i + 1}`)
      const loc = row.location || row.roadName
      const domain = getCanonicalVehicleDomain(row.vehicleType || row.type)
      const meta = getVehicleMeta(domain)
      const isOver = row.overSpeed === 'Yes' || row.isOverSpeed || (row.speed && row.speedLimit && Number(row.speed) > Number(row.speedLimit))

      nodes.push({
        id: obsId,
        label: obsLabel,
        category: 'Observation',
        vehicleType: domain,
        color: meta.color,
        borderColor: isOver ? '#ef4444' : (meta.border || '#ffffff'),
        parent: segregatedView ? `group-type-${domain}` : undefined,
        image: row.extractedImage || row.vehicleImageDataUrl,
        hasExtractedImage: row.hasExtractedImage,
        rawRow: row,
        properties: {
          'Number Plate': obsLabel,
          'Vehicle Type': domain,
          'Captured By': row.camera || 'N/A',
          'Location': loc || 'N/A',
          'Timestamp': row.timestampIst || row.timestamp || 'N/A',
          'Speed': `${row.speed || 0} km/h (Limit: ${row.speedLimit || 60} km/h)`,
          'Violation Status': isOver ? '⚠️ Overspeed Violation' : 'Compliant',
          'Signal State': row.signalState || 'Normal Flow',
        },
      })

      edges.push({
        id: `edge-${edgeIndex++}`,
        source: obsId,
        target: `type-${domain}`,
        label: 'OF_TYPE',
        color: '#94a3b8',
      })

      if (row.camera && cameras.includes(row.camera)) {
        edges.push({
          id: `edge-${edgeIndex++}`,
          source: obsId,
          target: `cam-${row.camera}`,
          label: 'CAPTURED_BY',
          color: '#94a3b8',
        })
      }

      if (loc && locations.includes(loc)) {
        edges.push({
          id: `edge-${edgeIndex++}`,
          source: obsId,
          target: `loc-${loc}`,
          label: 'OCCURRED_AT',
          color: '#94a3b8',
        })
      }

      // Edge to Violation node if overspeeding
      if (isOver) {
        edges.push({
          id: `edge-${edgeIndex++}`,
          source: obsId,
          target: 'violation-overspeed',
          label: 'TRIGGERED',
          color: '#ef4444',
        })
      }

      // Edge to Signal node if signalState exists
      if (row.signalState && signalStatesPresentAll.includes(row.signalState)) {
        edges.push({
          id: `edge-${edgeIndex++}`,
          source: obsId,
          target: `signal-${row.signalState}`,
          label: 'UNDER_SIGNAL',
          color: row.signalState === 'Red' ? '#dc2626' : row.signalState === 'Yellow' ? '#d97706' : '#10b981',
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
        observations: targetRows.length,
        totalDatasetRows: activeRows.length,
      },
    }
  }, [activeRows, focusMode, frozenVehicle, focusedCamera, recordLimit, segregatedView])

  // Filter visible nodes in ALL and CAMERA mode (in VEHICLE mode, currentNodes are shown)
  const visibleNodes = useMemo(() => {
    if (focusMode === 'VEHICLE') return currentNodes

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

  // Layout configuration per mode
  const layoutConfig = useMemo(() => {
    if (focusMode === 'VEHICLE') {
      return {
        name: 'concentric',
        concentric: (node) => (node.data('isCenter') ? 2 : 1),
        levelWidth: () => 1,
        minNodeSpacing: 80,
        padding: 70,
        animate: true,
        animationDuration: 350,
      }
    }

    // Clustered Force layout for ALL and CAMERA mode
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
      gravity: 0.015,
      numIter: 1000,
      coolingFactor: 0.95,
      stop: () => {
        cyRef.current?.animate({
          fit: { eles: cyRef.current.elements(), padding: 70 },
          duration: 300,
        })
      },
    }
  }, [focusMode, segregatedView])

  // Track initial render IDs
  useEffect(() => {
    renderedObsIdsRef.current = new Set(visibleNodes.map((n) => n.id))
  }, [focusMode, focusedCamera, frozenVehicle])

  // Cytoscape initialization & re-mounting on mode change
  useEffect(() => {
    if (!containerRef.current) return

    const elements = [
      ...visibleNodes.map((n) => ({
        data: {
          id: n.id,
          label: n.label,
          category: n.category,
          color: n.color,
          borderColor: n.borderColor || '#ffffff',
          vehicleType: n.vehicleType || '',
          parent: n.parent || undefined,
          isCenter: n.isCenter || false,
        },
      })),
      ...visibleEdges.map((e) => ({
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
        // ─── Base Nodes ───────────────────────────────────────────────
        {
          selector: 'node',
          style: {
            shape: 'ellipse',
            width: (node) => {
              if (node.data('isCenter')) return 80
              const cat = node.data('category')
              if (cat === 'Location') return 56
              if (cat === 'Camera') return 52
              if (cat === 'VehicleType') return 52
              if (cat === 'Violation') return 50
              if (cat === 'Signal') return 46
              return 40
            },
            height: (node) => {
              if (node.data('isCenter')) return 80
              const cat = node.data('category')
              if (cat === 'Location') return 56
              if (cat === 'Camera') return 52
              if (cat === 'VehicleType') return 52
              if (cat === 'Violation') return 50
              if (cat === 'Signal') return 46
              return 40
            },
            'background-color': 'data(color)',
            'background-opacity': 1,
            'border-width': (node) => (node.data('isCenter') ? 5 : 2.5),
            'border-color': 'data(borderColor)',
            'border-opacity': 1,
            label: 'data(label)',
            color: '#ffffff',
            'font-size': (node) => (node.data('isCenter') ? 12 : (node.data('category') === 'Observation' ? 9 : 10)),
            'font-weight': 700,
            'text-valign': 'bottom',
            'text-halign': 'center',
            'text-margin-y': 8,
            'text-wrap': 'wrap',
            'text-max-width': (node) => (node.data('isCenter') ? 130 : 90),
            'text-background-color': '#18221a',
            'text-background-opacity': 0.82,
            'text-background-padding': '3px',
            'text-background-shape': 'roundrectangle',
          },
        },
        // ─── Center / Hero Node ────────────────────────────────────────
        {
          selector: 'node[?isCenter]',
          style: {
            'border-width': 5,
            'border-color': '#f5d77f',
            'underlay-color': '#f5d77f',
            'underlay-padding': 10,
            'underlay-opacity': 0.25,
          },
        },
        // --- Active (clicked) node -> turns BLUE ---
        {
          selector: 'node.node-active',
          style: {
            'background-color': '#2563eb',
            'border-width': 4,
            'border-color': '#93c5fd',
            'underlay-color': '#2563eb',
            'underlay-padding': 10,
            'underlay-opacity': 0.35,
          },
        },
        // --- Dimmed nodes ---
        {
          selector: 'node.dimmed',
          style: { opacity: 0.22 },
        },
        // --- Neighbor nodes: keep own color + white ring ---
        {
          selector: 'node.neighbor-highlight',
          style: {
            opacity: 1,
            'border-width': 3.5,
            'border-color': '#ffffff',
          },
        },
        // --- Built-in selected ---
        {
          selector: 'node:selected',
          style: {
            'border-width': 4,
            'border-color': '#93c5fd',
          },
        },
        // --- Live streaming pulse ---
        {
          selector: 'node.live-pulse',
          style: {
            'border-width': 5,
            'border-color': '#10b981',
            'underlay-color': '#10b981',
            'underlay-padding': 12,
            'underlay-opacity': 0.55,
          },
        },
        // --- Parent / Group nodes ---
        {
          selector: ':parent',
          style: {
            'background-color': 'data(color)',
            'background-opacity': 0.08,
            'border-width': 1.5,
            'border-style': 'dashed',
            'border-color': 'data(borderColor)',
            'border-opacity': 0.45,
            'corner-radius': 16,
            label: 'data(label)',
            'text-valign': 'top',
            'text-halign': 'center',
            'text-margin-y': -10,
            'font-size': 10,
            'font-weight': 800,
            color: '#94a3b8',
            'text-background-color': '#0d1117',
            'text-background-opacity': 0.75,
            'text-background-padding': '3px',
            'text-background-shape': 'roundrectangle',
            padding: 28,
          },
        },
        // --- Edges: NO labels, Neo4j clean style ---
        {
          selector: 'edge',
          style: {
            width: 1.5,
            'line-color': '#4b5563',
            opacity: 0.6,
            'curve-style': 'bezier',
            'control-point-step-size': 40,
            'target-arrow-shape': 'triangle',
            'target-arrow-color': '#4b5563',
            'arrow-scale': 0.65,
            label: '',
          },
        },
        // --- Dimmed edges ---
        {
          selector: 'edge.dimmed',
          style: { opacity: 0.04 },
        },
        // --- Highlighted edges: dark blue, no label ---
        {
          selector: 'edge.neighbor-highlight',
          style: {
            opacity: 1,
            width: 3,
            'line-color': '#1d4ed8',
            'target-arrow-color': '#1d4ed8',
            label: '',
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

      cy.animate({
        fit: { eles: cy.elements(), padding: 70 },
        duration: 300,
      })
    })

    // ─── Hover: temporarily dim non-neighbors (only when no node is pinned) ───
    cy.on('mouseover', 'node', (evt) => {
      const node = evt.target
      if (node.isParent()) return
      // If a node is already click-selected, don't override with hover state
      if (pinnedNodeRef.current) return
      const connectedEdges = node.connectedEdges()
      const neighborNodes = connectedEdges.connectedNodes().difference(node)

      cy.elements().addClass('dimmed')
      node.removeClass('dimmed')
      connectedEdges.removeClass('dimmed').addClass('neighbor-highlight')
      neighborNodes.removeClass('dimmed').addClass('neighbor-highlight')
    })

    cy.on('mouseout', 'node', () => {
      // Only clear hover dimming if no node is click-pinned
      if (pinnedNodeRef.current) return
      cy.elements().removeClass('dimmed').removeClass('neighbor-highlight')
    })

    // ─── Click: pin-select node + collect all connected link details ─────
    cy.on('tap', 'node', (evt) => {
      const nodeId = evt.target.id()
      const nodeData = evt.target.data()

      // Gather all connected edges and neighbor nodes
      const cyNode = evt.target
      const connectedEdges = cyNode.connectedEdges()
      const connectedLinks = []
      connectedEdges.forEach((edge) => {
        const src = edge.source()
        const tgt = edge.target()
        const neighborNode = src.id() === nodeId ? tgt : src
        connectedLinks.push({
          edgeLabel: edge.data('label') || '',
          direction: src.id() === nodeId ? 'outgoing' : 'incoming',
          neighborId: neighborNode.id(),
          neighborLabel: neighborNode.data('label') || neighborNode.id(),
          neighborCategory: neighborNode.data('category') || '',
          neighborColor: neighborNode.data('color') || '#94a3b8',
        })
      })

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

      if (nodeObj) {
        setSelectedNode({ ...nodeObj, connectedLinks })
      }

      // Pin this selection: dim everything else, highlight connected, active node turns BLUE
      pinnedNodeRef.current = nodeId
      cy.elements().removeClass('dimmed').removeClass('neighbor-highlight').removeClass('node-active')
      cyNode.addClass('node-active')
      connectedEdges.addClass('neighbor-highlight')
      connectedEdges.connectedNodes().difference(cyNode).addClass('neighbor-highlight')
      cy.elements().not(connectedEdges).not(connectedEdges.connectedNodes()).addClass('dimmed')
      cyNode.removeClass('dimmed')
    })

    cy.on('tap', (evt) => {
      if (evt.target === cy) {
        // Click on background → unpin and clear all highlights
        pinnedNodeRef.current = null
        cy.elements().removeClass('dimmed').removeClass('neighbor-highlight').removeClass('node-active')
        setSelectedNode(null)
      }
    })

    cyRef.current = cy

    return () => {
      try {
        if (cy && typeof cy.destroyed === 'function' && !cy.destroyed()) {
          cy.destroy()
        }
      } catch {
        // ignore
      }
    }
  }, [focusMode, focusedCamera, frozenVehicle, visibleNodes, visibleEdges, layoutConfig])

  // =========================================================================
  // DYNAMIC STREAMING INGESTION (Only in Camera mode)
  // When new rows arrive in props.rows for this camera, dynamically append them!
  // =========================================================================
  useEffect(() => {
    if (focusMode !== 'CAMERA' || !focusedCamera || !cyRef.current) return

    const cy = cyRef.current
    if (typeof cy.destroyed === 'function' && cy.destroyed()) return

    const targetCamNorm = focusedCamera.toLowerCase().replace(/[^a-z0-9]/g, '')
    const camRows = rows.filter((r) => {
      if (!r.camera) return false
      const rowCamNorm = r.camera.toLowerCase().replace(/[^a-z0-9]/g, '')
      return rowCamNorm === targetCamNorm || rowCamNorm.includes(targetCamNorm) || targetCamNorm.includes(rowCamNorm)
    })
    if (!camRows.length) return

    // Look for records not yet rendered on the canvas
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

      newRecords.forEach(({ row: r, obsId }) => {
        const obsLabel = (r.numberPlate && r.numberPlate !== 'N/A' && r.numberPlate !== 'Unknown')
          ? r.numberPlate
          : (r.observationId || r.id || 'New Detection')
        const domain = getCanonicalVehicleDomain(r.vehicleType || r.type)
        const meta = getVehicleMeta(domain)

        const parentGroupId = `group-type-${domain}`
        let parentGroup = cy.getElementById(parentGroupId)
        if (!parentGroup.length) {
          cy.add({
            group: 'nodes',
            data: {
              id: parentGroupId,
              label: `${domain.toUpperCase()} DOMAIN · 1 RECORDS`,
              category: 'Group',
              vehicleType: domain,
              color: meta.bg || '#eff6ff',
              borderColor: meta.color || '#2563eb',
              isGroup: true,
              properties: {
                'Cluster Domain': `${domain} Domain`,
                'Total Vehicles': 1,
              },
            },
          })
          parentGroup = cy.getElementById(parentGroupId)
        }

        const domainNodeId = `type-${domain}`
        if (!cy.getElementById(domainNodeId).length) {
          cy.add({
            group: 'nodes',
            data: {
              id: domainNodeId,
              label: domain,
              category: 'VehicleType',
              vehicleType: domain,
              color: meta.color,
              borderColor: '#ffffff',
              parent: parentGroupId,
              properties: {
                'Classification': domain,
                'Color': meta.color,
              },
            },
          })
        }

        const existingChildren = cy.nodes(`[parent = "${parentGroupId}"]`)
        let posX, posY
        if (existingChildren.length > 0) {
          const bb = existingChildren.boundingBox()
          posX = bb.x1 + Math.random() * (Math.max(bb.w, 60))
          posY = bb.y1 + Math.random() * (Math.max(bb.h, 60))
        } else {
          const angle = Math.random() * Math.PI * 2
          posX = camPos.x + Math.cos(angle) * 280
          posY = camPos.y + Math.sin(angle) * 280
        }

        const isOver = r.isOverSpeed || r.overSpeed === 'Yes' || (Number(r.speed) > Number(r.speedLimit || 60))

        cy.add([
          {
            group: 'nodes',
            data: {
              id: obsId,
              label: obsLabel,
              category: 'Observation',
              vehicleType: domain,
              color: meta.color,
              borderColor: isOver ? '#ef4444' : '#10b981',
              parent: parentGroupId,
              rawRow: r,
              image: r.extractedImage || r.vehicleImageDataUrl || r.vehicleImagePath || r.vehicleImage,
              hasExtractedImage: r.hasExtractedImage,
              properties: {
                'Number Plate': obsLabel,
                'Vehicle Type': domain,
                'Captured By': focusedCamera,
                'Timestamp': r.timestampIst || r.timestamp || 'Live Stream',
                'Speed': `${r.speed || 0} km/h`,
                'Speed Limit': `${r.speedLimit || 60} km/h`,
                'Violation Status': isOver ? '⚠️ Overspeed Violation' : 'Compliant',
                'Dynamic Ingested': '🟢 Real-time Telemetry Stream',
              },
            },
            position: { x: posX, y: posY },
            classes: 'live-pulse',
          },
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
        ])

        const countInGroup = cy.nodes(`[parent = "${parentGroupId}"][category = "Observation"]`).length
        parentGroup.data('label', `${domain.toUpperCase()} DOMAIN · ${countInGroup} RECORDS`)

        setDynamicExtraByType((prev) => ({
          ...prev,
          [domain]: (prev[domain] || 0) + 1,
        }))

        setTimeout(() => {
          if (cyRef.current && typeof cyRef.current.destroyed === 'function' && !cyRef.current.destroyed()) {
            const el = cyRef.current.getElementById(obsId)
            if (el.length) el.removeClass('live-pulse')
          }
        }, 2800)
      })

      // Update live total
      setLiveDetectionCount((prev) => prev + newRecords.length)

      // Toast alert
      const latest = newRecords[0].row
      const latestPlate = latest.numberPlate || latest.observationId || 'Vehicle'
      const latestType = latest.vehicleType || latest.type || 'Detection'
      setLatestLiveAlert(`⚡ Live capture on ${focusedCamera}: ${latestPlate} (${latestType})`)
      const timer = setTimeout(() => setLatestLiveAlert(null), 3800)
      return () => clearTimeout(timer)
    }
  }, [rows, focusMode, focusedCamera])

  function handleTriggerLiveDetection() {
    if (!focusedCamera || !cyRef.current) return
    const cy = cyRef.current
    if (typeof cy.destroyed === 'function' && cy.destroyed()) return

    const camNode = cy.getElementById(`cam-${focusedCamera}`)
    const camPos = camNode.length ? camNode.position() : { x: 400, y: 300 }

    const types = ['Car', 'Bike', 'Auto', 'Truck', 'Bus', 'Van']
    const randomType = types[Math.floor(Math.random() * types.length)]
    const randomPlate = `TS 09 ${String.fromCharCode(65 + Math.floor(Math.random() * 26))}${String.fromCharCode(65 + Math.floor(Math.random() * 26))} ${1000 + Math.floor(Math.random() * 9000)}`
    const randomSpeed = Math.floor(38 + Math.random() * 55)
    const isOver = randomSpeed > 60
    const signalState = Math.random() > 0.85 ? 'Red' : (Math.random() > 0.7 ? 'Yellow' : 'Green')
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
      roadName: 'Outer Ring Road (NH-44 Expressway)',
      location: 'Outer Ring Road (NH-44 Expressway)',
      confidence: 0.96,
    }

    renderedObsIdsRef.current.add(obsId)

    const domain = getCanonicalVehicleDomain(randomType)
    const meta = getVehicleMeta(domain)

    // 1. Ensure parent group exists: `group-type-${domain}`
    const parentGroupId = `group-type-${domain}`
    let parentGroup = cy.getElementById(parentGroupId)
    if (!parentGroup.length) {
      cy.add({
        group: 'nodes',
        data: {
          id: parentGroupId,
          label: `${domain.toUpperCase()} DOMAIN · 1 RECORDS`,
          category: 'Group',
          vehicleType: domain,
          color: meta.bg || '#eff6ff',
          borderColor: meta.color || '#2563eb',
          isGroup: true,
          properties: {
            'Cluster Domain': `${domain} Domain`,
            'Total Vehicles': 1,
          },
        },
      })
      parentGroup = cy.getElementById(parentGroupId)
    }

    // 2. Ensure domain type anchor node exists
    const domainNodeId = `type-${domain}`
    if (!cy.getElementById(domainNodeId).length) {
      cy.add({
        group: 'nodes',
        data: {
          id: domainNodeId,
          label: domain,
          category: 'VehicleType',
          vehicleType: domain,
          color: meta.color,
          borderColor: '#ffffff',
          parent: parentGroupId,
          properties: {
            'Classification': domain,
            'Color': meta.color,
          },
        },
      })
    }

    // 3. Position the new observation inside its domain bounding box
    const existingChildren = cy.nodes(`[parent = "${parentGroupId}"]`)
    let posX, posY
    if (existingChildren.length > 0) {
      const bb = existingChildren.boundingBox()
      posX = bb.x1 + Math.random() * (Math.max(bb.w, 60))
      posY = bb.y1 + Math.random() * (Math.max(bb.h, 60))
    } else {
      const angle = Math.random() * Math.PI * 2
      posX = camPos.x + Math.cos(angle) * 280
      posY = camPos.y + Math.sin(angle) * 280
    }

    const addedElements = [
      {
        group: 'nodes',
        data: {
          id: obsId,
          label: randomPlate,
          category: 'Observation',
          vehicleType: domain,
          color: meta.color,
          borderColor: isOver ? '#ef4444' : (meta.border || '#10b981'),
          parent: parentGroupId,
          rawRow: simRow,
          properties: {
            'Number Plate': randomPlate,
            'Vehicle Type': domain,
            'Captured By': focusedCamera,
            'Timestamp': simRow.timestampIst,
            'Speed': `${randomSpeed} km/h`,
            'Speed Limit': '60 km/h',
            'Violation Status': isOver ? '⚠️ Overspeed Violation' : 'Compliant',
            'Signal Status': signalState,
            'Dynamic Ingestion': '🟢 Real-Time Camera Stream',
          },
        },
        position: { x: posX, y: posY },
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

    cy.add(addedElements)

    // 4. Update parent group label with new vehicle count
    const totalInGroup = cy.nodes(`[parent = "${parentGroupId}"][category = "Observation"]`).length
    parentGroup.data('label', `${domain.toUpperCase()} DOMAIN · ${totalInGroup} RECORDS`)

    // 5. Update Camera Node properties in real time
    if (camNode.length) {
      const p = camNode.data('properties') || {}
      const prevCount = parseInt(p['Total Ingested Detections'] || 0, 10) || 0
      const prevViol = parseInt(p['Speed Violations Logged'] || 0, 10) || 0
      camNode.data('properties', {
        ...p,
        'Total Ingested Detections': prevCount + 1,
        'Speed Violations Logged': prevViol + (isOver ? 1 : 0),
        'Last Ingestion Heartbeat': simRow.timestampIst,
      })
    }

    setLiveDetectionCount((prev) => prev + 1)
    setDynamicExtraByType((prev) => ({
      ...prev,
      [domain]: (prev[domain] || 0) + 1,
    }))
    setLatestLiveAlert(`⚡ Live capture on ${focusedCamera}: ${randomPlate} (${domain}) ${isOver ? `⚠️ ${randomSpeed} km/h` : ''}`)

    setTimeout(() => {
      if (cyRef.current && typeof cyRef.current.destroyed === 'function' && !cyRef.current.destroyed()) {
        const el = cyRef.current.getElementById(obsId)
        if (el.length) el.removeClass('live-pulse')
      }
    }, 2800)
    setTimeout(() => setLatestLiveAlert(null), 3800)
  }

  // Automatic stream ingestion effect when toggle is active (2.6s interval)
  useEffect(() => {
    if (!autoStreamActive || focusMode !== 'CAMERA' || !focusedCamera) return
    const interval = setInterval(() => {
      handleTriggerLiveDetection()
    }, 2600)
    return () => clearInterval(interval)
  }, [autoStreamActive, focusMode, focusedCamera])

  // Handle Search Submission (Auto-detects Vehicle Plate vs Camera)
  function handleSearchSubmit(e) {
    e?.preventDefault?.()
    const query = searchTerm.trim()
    if (!query) return

    // 0. If user types "all cameras" or "all"
    if (
      query.toLowerCase().includes('all camera') ||
      query.toLowerCase() === 'all' ||
      query.toLowerCase() === 'cameras' ||
      query.toLowerCase() === 'all cameras'
    ) {
      handleExitFocusMode()
      return
    }

    // 1. Check if matches a camera
    const qLower = query.toLowerCase()
    const qNorm = qLower.replace(/[^a-z0-9]/g, '')
    const matchedCam = allCameras.find((c) => {
      const cLower = c.toLowerCase()
      const cNorm = cLower.replace(/[^a-z0-9]/g, '')
      if (cLower === qLower || cLower.includes(qLower)) return true
      if (qNorm.length >= 2 && (cNorm === qNorm || cNorm.includes(qNorm))) return true
      const numMatch = qLower.match(/\d+/)
      if (numMatch && (qLower.includes('cam') || qLower.includes('camera'))) {
        const num = parseInt(numMatch[0], 10)
        const camNumMatch = c.match(/\d+/)
        if (camNumMatch && parseInt(camNumMatch[0], 10) === num) return true
      }
      return false
    })

    if (
      matchedCam &&
      (qLower.includes('cam') ||
        query.toUpperCase().startsWith('CAM') ||
        matchedCam.toLowerCase() === qLower ||
        qNorm.length >= 3)
    ) {
      handleSelectCamera(matchedCam)
      return
    }

    // 2. Check if matches a vehicle plate
    const matchedVehicle = rows.find((r) => {
      const plate = (r.numberPlate || r.vehicleNumberPlate || '').toLowerCase()
      const id = String(r.observationId || r.id || '').toLowerCase()
      return plate.includes(query.toLowerCase()) || id === query.toLowerCase()
    })

    if (matchedVehicle) {
      handleSelectVehicle(matchedVehicle)
      return
    }

    // If query contains 'cam' but wasn't exact match, pick first matching camera
    if (searchSuggestions.cameras.length > 0) {
      handleSelectCamera(searchSuggestions.cameras[0])
      return
    }

    // If matches vehicles in suggestion
    if (searchSuggestions.vehicles.length > 0) {
      handleSelectVehicle(searchSuggestions.vehicles[0])
      return
    }

    setShowSuggestions(false)
  }

  // Zoom / Viewport controls
  function handleZoomIn() {
    const cy = cyRef.current
    if (!cy) return
    cy.animate({
      zoom: {
        level: Math.min(3.5, cy.zoom() * 1.3),
        renderedPosition: { x: cy.width() / 2, y: cy.height() / 2 },
      },
      duration: 180,
    })
  }

  function handleZoomOut() {
    const cy = cyRef.current
    if (!cy) return
    cy.animate({
      zoom: {
        level: Math.max(0.04, cy.zoom() * 0.75),
        renderedPosition: { x: cy.width() / 2, y: cy.height() / 2 },
      },
      duration: 180,
    })
  }

  function handleFit() {
    const cy = cyRef.current
    if (!cy) return
    cy.animate({
      fit: { eles: cy.elements(), padding: 70 },
      duration: 260,
    })
  }

  function handleRelayout() {
    const cy = cyRef.current
    if (!cy) return
    cy.layout({
      ...layoutConfig,
      animate: true,
      animationDuration: 400,
      stop: () => {
        cy.animate({ fit: { eles: cy.elements(), padding: 70 }, duration: 250 })
      },
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
    <div
      className={`ontology-page knowledge-graph-page ${shouldHideFilters ? 'embedded-mode' : ''}`}
      style={shouldHideFilters ? { padding: 0, minHeight: '620px', height: '620px' } : undefined}
    >
      {/* Topbar */}
      {!shouldHideFilters && (
        <div className="ontology-topbar">
          <div>
            <div className="ontology-kicker">
              {focusMode === 'VEHICLE'
                ? '🔒 STATIC VEHICLE FORENSICS'
                : focusMode === 'CAMERA'
                ? '🟢 DYNAMIC LIVE CAMERA STREAM'
                : `INSTANCE GRAPH · ${fileName.toUpperCase()}`}
            </div>
            <h1>Knowledge Graph</h1>
            <p>
              {focusMode === 'VEHICLE'
                ? `Isolated static forensic topology for ${frozenVehicle?.numberPlate || 'Vehicle'}. All connected entities frozen without live shifts.`
                : focusMode === 'CAMERA'
                ? `Live dynamic monitoring hub for ${focusedCamera}. New detections automatically append to this graph in real time.`
                : `Interactive network graph showing entity instances and relationships from ${fileName} (${activeRows.length} records).`}
            </p>
          </div>

          <div className="ontology-stat-card">
            <Network size={18} />
            <div>
              <strong>{visibleNodes.length}</strong>
              <span>Entities</span>
            </div>
            <div className="ontology-stat-divider" />
            <div>
              <strong>{visibleEdges.length}</strong>
              <span>Relationships</span>
            </div>
            <div className="ontology-stat-divider" />
            <div>
              <strong>
                {focusMode === 'CAMERA' ? liveDetectionCount : stats.observations}
              </strong>
              <span>{focusMode === 'CAMERA' ? 'Live Detections' : 'Records'}</span>
            </div>
            <div className="ontology-stat-divider" />
            <div>
              <strong>{stats.cameras}</strong>
              <span>Cameras</span>
            </div>
          </div>
        </div>
      )}

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
                Displaying what all is connected (Camera, Road Location, Vehicle Domain, Violations). Live telemetry updates are paused for this vehicle so graph remains 100% static.
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
                Active real-time hub. Whenever new data is detected by this camera, it will dynamically update and attach to this graph.
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

      {/* AI Queried Segment Banner */}
      {!shouldHideFilters && segmentFilter && focusMode === 'ALL' && (
        <div className="kg-active-segment-alert">
          <div className="kg-segment-alert-left">
            <Bot size={18} />
            <div>
              <strong>AI Queried Knowledge Graph Segment</strong>
              <p>{segmentExplanation || 'Filtered subgraph matching your natural language query'}</p>
            </div>
          </div>
          <div className="kg-segment-alert-right">
            <span className="kg-segment-pill">{activeRows.length} events retrieved</span>
            <button
              className="kg-segment-clear-btn"
              onClick={() => {
                setSegmentFilter(null)
                setSegmentExplanation('')
              }}
              type="button"
            >
              <X size={14} />
              <span>Show Full Knowledge Graph</span>
            </button>
          </div>
        </div>
      )}

      {/* Workspace */}
      <div className="ontology-workspace">
        <div className="ontology-main">
          {/* Toolbar */}
          <div className="ontology-toolbar" style={shouldHideFilters ? { justifyContent: 'space-between', padding: '8px 14px' } : undefined}>
            {shouldHideFilters ? (
              <>
                <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                  <span style={{ fontSize: '13px', fontWeight: 700, color: '#0f172a', display: 'flex', alignItems: 'center', gap: '6px' }}>
                    <Network size={15} style={{ color: '#2563eb' }} />
                    Knowledge Graph Subgraph
                  </span>
                  <span style={{ fontSize: '11px', color: '#64748b', background: '#f1f5f9', padding: '3px 9px', borderRadius: '10px', fontWeight: 600 }}>
                    {visibleNodes.length} Entities · {visibleEdges.length} Links
                  </span>
                </div>
                <div className="ontology-toolbar-actions">
                  <button onClick={handleZoomIn} title="Zoom In" type="button">
                    <Plus size={17} />
                  </button>
                  <button onClick={handleZoomOut} title="Zoom Out" type="button">
                    <Minus size={17} />
                  </button>
                  <button onClick={handleFit} title="Fit to Screen" type="button">
                    <Maximize size={16} />
                  </button>
                  <button onClick={handleRelayout} title="Re-layout Graph" type="button">
                    <RefreshCw size={16} />
                  </button>
                </div>
              </>
            ) : (
              <>
                {/* Search Input with Dynamic Auto-complete */}
                <div className="kg-search-container">
                  <form className="ontology-search" onSubmit={handleSearchSubmit}>
                    <Search size={16} />
                    <input
                      onBlur={() => setTimeout(() => setShowSuggestions(false), 250)}
                      onChange={(e) => {
                        setSearchTerm(e.target.value)
                        setShowSuggestions(true)
                      }}
                      onFocus={() => setShowSuggestions(true)}
                      placeholder="Search vehicle plate (e.g. TS 09, AP 28), camera (e.g. CAM-01)..."
                      type="text"
                      value={searchTerm}
                    />
                    {searchTerm && (
                      <button
                        className="ontology-search-clear"
                        onClick={() => {
                          setSearchTerm('')
                          setShowSuggestions(false)
                        }}
                        type="button"
                      >
                        <X size={14} />
                      </button>
                    )}
                  </form>

                  {/* Suggestions Dropdown */}
                  {showSuggestions && (searchSuggestions.cameras.length > 0 || searchSuggestions.vehicles.length > 0) && (
                    <div className="kg-suggestions-dropdown">
                      {searchSuggestions.cameras.map((cam) => (
                        <div
                          className="kg-suggestion-item"
                          key={cam}
                          onClick={() => handleSelectCamera(cam)}
                        >
                          <div className="kg-suggestion-item-left">
                            <Camera size={14} style={{ color: '#059669' }} />
                            <span>{cam}</span>
                          </div>
                          <span className="kg-suggestion-badge" style={{ background: '#ecfdf5', color: '#059669' }}>
                            🟢 Dynamic Camera Stream
                          </span>
                        </div>
                      ))}

                      {searchSuggestions.vehicles.map((vh, idx) => {
                        const plate = vh.numberPlate || vh.vehicleNumberPlate || vh.observationId || `Vehicle #${idx + 1}`
                        const dom = getCanonicalVehicleDomain(vh.vehicleType || vh.type)
                        const meta = getVehicleMeta(dom)
                        return (
                          <div
                            className="kg-suggestion-item"
                            key={vh.id || plate}
                            onClick={() => handleSelectVehicle(vh)}
                          >
                            <div className="kg-suggestion-item-left">
                              <Car size={14} style={{ color: meta.color }} />
                              <span>{plate} ({dom})</span>
                            </div>
                            <span className="kg-suggestion-badge" style={{ background: '#eff6ff', color: '#2563eb' }}>
                              🔒 Static Forensic Subgraph
                            </span>
                          </div>
                        )
                      })}
                    </div>
                  )}
                </div>

                {/* Category Filter Pills (When in ALL mode) */}
                {focusMode === 'ALL' && (
                  <div className="kg-category-filters">
                    {[
                      { key: 'ALL', label: `All (${currentNodes.length})` },
                      { key: 'Location', label: `Locations (${stats.locations})` },
                      { key: 'Camera', label: `Cameras (${stats.cameras})` },
                      { key: 'VehicleType', label: `Types (${stats.types})` },
                      { key: 'Observation', label: `Records (${stats.observations})` },
                    ].map(({ key, label }) => (
                      <button
                        className={`kg-filter-btn ${activeCategory === key ? 'active' : ''}`}
                        key={key}
                        onClick={() => setActiveCategory(key)}
                        type="button"
                      >
                        {label}
                      </button>
                    ))}
                  </div>
                )}

                {/* Quick Mode Switcher */}
                <div className="kg-mode-pills-group">
                  <button
                    className={`kg-mode-pill ${focusMode === 'ALL' ? 'active' : ''}`}
                    onClick={handleExitFocusMode}
                    title="View full interconnected knowledge graph"
                    type="button"
                  >
                    <Network size={13} />
                    <span>Full Graph</span>
                  </button>

                  <button
                    className={`kg-mode-pill ${focusMode === 'CAMERA' ? 'active-dynamic' : ''}`}
                    onClick={() => {
                      if (allCameras[0]) handleSelectCamera(allCameras[0])
                    }}
                    title="Dynamic live camera hub (auto-updates on new telemetry)"
                    type="button"
                  >
                    <Radio size={13} />
                    <span>Dynamic Camera Stream</span>
                  </button>
                </div>

                {/* Records & Layout Controls (In ALL mode) */}
                {focusMode === 'ALL' && (
                  <div className="kg-toolbar-controls">
                    <div className="kg-control-group">
                      <span className="kg-control-label">Records:</span>
                      <select
                        aria-label="Records displayed in knowledge graph"
                        className="kg-select-control"
                        onChange={(e) => setRecordLimit(e.target.value)}
                        value={recordLimit}
                      >
                        <option value="ALL">All ({activeRows.length})</option>
                        {activeRows.length > 250 && <option value="250">Top 250</option>}
                        {activeRows.length > 100 && <option value="100">Top 100</option>}
                        {activeRows.length > 50 && <option value="50">Top 50</option>}
                        {activeRows.length > 20 && <option value="20">Top 20</option>}
                      </select>
                    </div>

                    <div className="kg-control-group">
                      <span className="kg-control-label">Grouping:</span>
                      <button
                        className={`kg-segregation-toggle ${segregatedView ? 'active' : ''}`}
                        onClick={() => setSegregatedView(!segregatedView)}
                        title="Toggle segregated type clusters"
                        type="button"
                      >
                        <Layers size={13} />
                        <span>{segregatedView ? 'Segregated' : 'Free Net'}</span>
                      </button>
                    </div>
                  </div>
                )}

                {/* Actions */}
                <div className="ontology-toolbar-actions">
                  <button onClick={handleZoomIn} title="Zoom In" type="button">
                    <Plus size={17} />
                  </button>
                  <button onClick={handleZoomOut} title="Zoom Out" type="button">
                    <Minus size={17} />
                  </button>
                  <button onClick={handleFit} title="Fit to Screen" type="button">
                    <Maximize size={16} />
                  </button>
                  <button onClick={handleRelayout} title="Re-layout Graph" type="button">
                    <RefreshCw size={16} />
                  </button>
                </div>
              </>
            )}
          </div>

          {/* Quick Select Bar for Cameras & Recent Vehicles */}
          {!shouldHideFilters && (
            <div className="kg-quick-modes-bar">
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
                <span style={{ fontSize: '11px', fontWeight: 700, color: '#64748b', display: 'inline-flex', alignItems: 'center', gap: '4px' }}>
                  <Camera size={13} style={{ color: '#059669' }} /> Stream Camera:
                </span>
                {allCameras.slice(0, 5).map((cam) => {
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
          )}

          {/* Vehicle Domain Colors Legend & Quick-Filter Bar */}
          {focusMode !== 'VEHICLE' && (
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
                    <span className="kg-domain-name">All Domains</span>
                    <span className="kg-domain-count" style={{ background: '#f1f5f9', color: '#334155' }}>
                      ({totalAllDomainsCount})
                    </span>
                  </button>
                  {domainBreakdown.map((item) => {
                    const isActive = vehicleDomainFilter.toLowerCase() === item.rawType.toLowerCase()
                    return (
                      <button
                        className={`kg-domain-pill ${isActive ? 'active' : ''}`}
                        key={item.rawType}
                        onClick={() => setVehicleDomainFilter(isActive ? 'ALL' : item.rawType)}
                        style={{
                          borderColor: isActive ? item.color : '#e2e8f0',
                          backgroundColor: isActive ? item.bg : '#ffffff',
                        }}
                        title={`Show all ${item.rawType}s (${item.count} detections with color ${item.color})`}
                        type="button"
                      >
                        <span
                          className="kg-domain-dot"
                          style={{ backgroundColor: item.color }}
                        />
                        <span className="kg-domain-name">{item.label}</span>
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
                <button
                  className="kg-domain-reset-btn"
                  onClick={() => setVehicleDomainFilter('ALL')}
                  type="button"
                >
                  <X size={12} />
                  <span>Show All Vehicles</span>
                </button>
              )}
            </div>
          )}

          {/* Graph Canvas Wrapper */}
          <div className="ontology-graph-wrapper">
            <div ref={containerRef} style={{ width: '100%', height: '100%' }} />

            {/* Real-time Dynamic Detection Toast (In Camera Stream Mode) */}
            {latestLiveAlert && (
              <div className="kg-live-toast">
                <Zap size={14} style={{ color: '#34d399' }} />
                <span>{latestLiveAlert}</span>
              </div>
            )}

            <div className="ontology-layout-badge">
              {focusMode === 'VEHICLE' ? (
                <>
                  <Lock size={14} style={{ color: '#0284c7' }} />
                  <span>Static Vehicle Subgraph (All Connected Entities Isolated)</span>
                </>
              ) : focusMode === 'CAMERA' ? (
                <>
                  <span className="kg-live-dot pulse" style={{ width: 8, height: 8 }} />
                  <span>Dynamic Real-Time Camera Stream ({focusedCamera})</span>
                </>
              ) : (
                <>
                  <Network size={14} />
                  <span>{segregatedView ? 'Segregated Type Clusters (COSE Engine)' : 'Force Layout (Cytoscape)'}</span>
                </>
              )}
            </div>

            <div className="ontology-graph-info">
              {visibleNodes.length} nodes · {visibleEdges.length} edges
            </div>
          </div>
        </div>

        {/* Selected Entity Details Drawer */}
        {selectedNode && (
          <div className="kg-details-panel">
            <div className="kg-details-header">
              <div className="kg-details-title-row">
                <span className="kg-badge" style={{ backgroundColor: selectedNode.color || '#2563eb', color: '#ffffff' }}>
                  {selectedNode.category === 'Observation'
                    ? `${selectedNode.vehicleType || 'Vehicle'} · Detection`
                    : selectedNode.category}
                </span>
                <button className="ontology-details-close" onClick={() => setSelectedNode(null)} type="button">
                  <X size={16} />
                </button>
              </div>
              <h2>{selectedNode.label}</h2>
              <span className="kg-node-id">ID: {selectedNode.id}</span>

              {/* Mode Transition Shortcuts */}
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
                    <Lock size={14} />
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
                    <Radio size={14} />
                    <span>Stream Camera Telemetry (Dynamic)</span>
                  </button>
                </div>
              )}
            </div>

            <div className="kg-details-body">
              {/* Media Card if image exists */}
              {selectedNode.image && (
                <div
                  className="kg-inspector-media-card"
                  style={{
                    background: '#0f172a',
                    borderRadius: '10px',
                    padding: '8px',
                    marginBottom: '14px',
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
                    title="Click to inspect high-resolution surveillance modal"
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

              <h3>Attributes & Telemetry</h3>
              <div className="kg-property-list">
                {Object.entries(selectedNode.properties || {}).map(([key, val]) => (
                  <div className="kg-property-row" key={key}>
                    <span className="kg-prop-key">{key}</span>
                    <strong className="kg-prop-val">{String(val)}</strong>
                  </div>
                ))}
              </div>

              {/* ── Connected Links ── */}
              <div style={{ marginTop: '18px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '10px' }}>
                  <h3 style={{ margin: 0, fontSize: '13px', fontWeight: 700, color: '#1e293b' }}>
                    Connected Relationships
                  </h3>
                  <span style={{
                    fontSize: '11px',
                    color: '#0284c7',
                    fontWeight: 700,
                    background: '#f0f9ff',
                    padding: '2px 9px',
                    borderRadius: '12px',
                    border: '1px solid #bae6fd',
                  }}>
                    {(selectedNode.connectedLinks || connectedRelationships).length} links
                  </span>
                </div>

                <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                  {/* Use rich connectedLinks if available (from tap handler), else fallback */}
                  {selectedNode.connectedLinks && selectedNode.connectedLinks.length > 0
                    ? selectedNode.connectedLinks.map((link, i) => (
                      <div
                        key={i}
                        style={{
                          display: 'flex',
                          alignItems: 'center',
                          gap: '8px',
                          background: '#f8fafc',
                          border: '1px solid #e2e8f0',
                          borderRadius: '10px',
                          padding: '8px 12px',
                          fontSize: '12px',
                        }}
                      >
                        {/* Direction arrow */}
                        <span style={{
                          fontSize: '14px',
                          color: link.direction === 'outgoing' ? '#0284c7' : '#7c3aed',
                          fontWeight: 800,
                          flex: '0 0 16px',
                          textAlign: 'center',
                        }}>
                          {link.direction === 'outgoing' ? '→' : '←'}
                        </span>

                        {/* Relationship type badge */}
                        <span style={{
                          background: link.direction === 'outgoing' ? '#dbeafe' : '#ede9fe',
                          color: link.direction === 'outgoing' ? '#1d4ed8' : '#6d28d9',
                          fontWeight: 700,
                          fontSize: '10px',
                          letterSpacing: '0.06em',
                          padding: '2px 7px',
                          borderRadius: '6px',
                          flex: '0 0 auto',
                          whiteSpace: 'nowrap',
                        }}>
                          {link.edgeLabel || 'LINK'}
                        </span>

                        {/* Neighbor node info */}
                        <div style={{ display: 'flex', alignItems: 'center', gap: '6px', flex: 1, minWidth: 0 }}>
                          {/* Color dot for neighbor category */}
                          <span style={{
                            width: 10,
                            height: 10,
                            borderRadius: '50%',
                            background: link.neighborColor || '#94a3b8',
                            flexShrink: 0,
                            border: '1.5px solid rgba(0,0,0,0.1)',
                          }} />
                          <div style={{ minWidth: 0 }}>
                            <div style={{
                              fontWeight: 600,
                              color: '#1e293b',
                              fontSize: '11.5px',
                              whiteSpace: 'nowrap',
                              overflow: 'hidden',
                              textOverflow: 'ellipsis',
                            }}>
                              {link.neighborLabel}
                            </div>
                            <div style={{ fontSize: '10px', color: '#64748b', marginTop: '1px' }}>
                              {link.neighborCategory}
                            </div>
                          </div>
                        </div>
                      </div>
                    ))
                    : connectedRelationships.map((e) => (
                      <div className="kg-edge-item" key={e.id}>
                        <span className="kg-edge-label" style={{ backgroundColor: e.color || undefined }}>{e.label}</span>
                        <span className="kg-edge-target" title={e.source === selectedNode.id ? e.target : e.source}>
                          {e.source === selectedNode.id ? `→ ${e.target}` : `← ${e.source}`}
                        </span>
                      </div>
                    ))
                  }
                </div>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Media Inspection Modal */}
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
