import { lazy, Suspense, useEffect, useRef, useState } from 'react'
import { io } from 'socket.io-client'
import { Navigate, Route, Routes, useLocation } from 'react-router-dom'

import DashboardHub from './components/DashboardHub'
import ProjectConnectionRequired from './components/ProjectConnectionRequired'
import ProjectComingSoon from './components/ProjectComingSoon'
import DataImportRequired from './components/DataImportRequired'
import { ErrorBoundary } from './components/ErrorBoundary'
import Sidebar from './components/Sidebar'
import Topbar from './components/Topbar'
import LoginPage from './components/auth/LoginPage'
import SignupPage from './components/auth/SignupPage'
import ProtectedRoute from './components/auth/ProtectedRoute'
import { useAuth } from './context/AuthContext'

// pages load on first visit (keeps the initial download small: cytoscape, recharts, xlsx, ... come with their page)
const DashboardDetail = lazy(() => import('./components/DashboardDetail'))
const OntologyPage = lazy(() => import('./components/ontology/OntologyPage'))
const KnowledgeGraphPage = lazy(() => import('./components/knowledgeGraph/KnowledgeGraphPage'))
const DocumentIntelligence = lazy(() => import('./components/DocumentIntelligence'))
const QueryPage = lazy(() => import('./components/QueryPage'))
const RulesEventsPage = lazy(() => import('./components/RulesEventsPage'))
const ProfilePage = lazy(() => import('./components/ProfilePage'))
const SettingsPage = lazy(() => import('./components/SettingsPage'))
const VehicleInformation = lazy(() => import('./components/VehicleInformation'))
const PlaceholderPage = lazy(() => import('./components/PlaceholderPage'))
const ProjectsPage = lazy(() => import('./components/projects/ProjectsPage'))
const VideoUploadPage = lazy(() => import('./components/nh5/VideoUploadPage'))
const VideoLibraryPage = lazy(() => import('./components/nh5/VideoLibraryPage'))
const VideoDetailPage = lazy(() => import('./components/nh5/VideoDetailPage'))
const LiveCameraPage = lazy(() => import('./components/nh5/LiveCameraPage'))
const RoadMapsPage = lazy(() => import('./components/nh5/RoadMapsPage'))
const RoadMapEditor = lazy(() => import('./components/nh5/RoadMapEditor'))
const DetectionModelPage = lazy(() => import('./components/nh5/DetectionModelPage'))

import {
  normalizeTrafficData,
  parseTrafficCsv,
} from './data/dashboardData'
import { routePaths } from './data/navigation'
import { projects } from './data/projects'

const storedProjectsKey = 'vision-iq-created-projects'
const storedCamerasKey = 'vision-iq-added-cameras'
const storedRemovedCamerasKey = 'vision-iq-removed-cameras'
const storedNotificationsKey = 'vision-iq-stream-notifications'
const apiBaseUrl = (import.meta.env.VITE_API_URL || window.location.origin).replace(/\/$/, '')
const ALL_RECORDS_LABEL = 'All processed videos'
const MAX_ROWS = 20000

function rowKey(row) {
  return `${row.sourceFile || row.fileName || 'db'}::${row.csvRecordId || row.observationId || row.id || `${row.timestamp}-${row.vehicleNumberPlate}`}`
}

function prependStreamRows(previousRows, incomingRows, maxCapacity = MAX_ROWS) {
  if (!incomingRows || !incomingRows.length) return previousRows
  const incomingKeys = new Set(incomingRows.map(rowKey))
  // Filter out any older instance of these records so looped records refresh at top of stream
  const olderRows = previousRows.filter((row) => !incomingKeys.has(rowKey(row)))
  const updated = [...incomingRows, ...olderRows]
  return updated.slice(0, maxCapacity)
}

function prependUniqueRows(previousRows, incomingRows) {
  return prependStreamRows(previousRows, incomingRows)
}

function appendUniqueRows(previousRows, incomingRows) {
  return prependStreamRows(previousRows, incomingRows)
}

function normalizeStreamRows(rows) {
  const normalizedRows = normalizeTrafficData(rows)
  const now = Date.now()
  return normalizedRows.map((row, index) => ({
    ...row,
    csvRecordId: rows[index]?.csvRecordId || row.csvRecordId,
    sourceFile: rows[index]?.sourceFile || row.sourceFile,
    events: rows[index]?.events || row.events || '',
    _streamId: `${row.id || row.csvRecordId || index}-${rows[index]?._streamSeq || ''}-${now}-${Math.random().toString(36).slice(2, 6)}`,
  }))
}

export default function App() {
  const { isAuthenticated, loading } = useAuth()
  const { pathname } = useLocation()
  const [searchOpen, setSearchOpen] = useState(false)
  const [projectList, setProjectList] = useState(() => {
    try {
      const storedProjects = JSON.parse(
        localStorage.getItem(storedProjectsKey) || '[]',
      )
      return [...projects, ...storedProjects.filter((project) => project.created)]
    } catch {
      return projects
    }
  })
  const [selectedProject, setSelectedProject] = useState(projects[0])
  const [connectedProject, setConnectedProject] = useState(projects[0])
  const [trafficData, setTrafficData] = useState([])
  const [addedCameras, setAddedCameras] = useState(() => {
    try {
      return JSON.parse(localStorage.getItem(storedCamerasKey) || '[]')
    } catch {
      return []
    }
  })
  const [removedCameras, setRemovedCameras] = useState(() => {
    try {
      return JSON.parse(localStorage.getItem(storedRemovedCamerasKey) || '[]')
    } catch {
      return []
    }
  })
  const [fileName, setFileName] = useState(ALL_RECORDS_LABEL)
  const [importError, setImportError] = useState('')
  const [streamNotifications, setStreamNotifications] = useState(() => {
    try {
      return JSON.parse(localStorage.getItem(storedNotificationsKey) || '[]')
    } catch {
      return []
    }
  })
  const [notificationSoundEnabled, setNotificationSoundEnabled] = useState(() => {
    try {
      return localStorage.getItem('vision-iq-notification-sound') !== 'off'
    } catch {
      return true
    }
  })
  const notificationSoundEnabledRef = useRef(notificationSoundEnabled)

  useEffect(() => {
    notificationSoundEnabledRef.current = notificationSoundEnabled
    try {
      localStorage.setItem(
        'vision-iq-notification-sound',
        notificationSoundEnabled ? 'on' : 'off',
      )
    } catch {
      // ignore localStorage write errors
    }
  }, [notificationSoundEnabled])

  function playNotificationTone() {
    if (!notificationSoundEnabledRef.current) return
    try {
      const AudioContextClass = window.AudioContext || window.webkitAudioContext
      if (!AudioContextClass) return
      const ctx = new AudioContextClass()
      const now = ctx.currentTime

      const notificationSound = new Audio('/notification_sound.mp3')
      notificationSound.volume = 1
      notificationSound.currentTime = 0
      notificationSound.play().catch(() => undefined)
      window.setTimeout(() => {
        notificationSound.pause()
        notificationSound.currentTime = 0
      }, 1000)
      const osc1 = ctx.createOscillator()
      const osc2 = ctx.createOscillator()
      const gain = ctx.createGain()

      osc1.type = 'sine'
      osc2.type = 'triangle'
      osc1.frequency.setValueAtTime(587.33, now)
      osc1.frequency.exponentialRampToValueAtTime(880, now + 0.12)
      osc2.frequency.setValueAtTime(293.66, now)
      osc2.frequency.exponentialRampToValueAtTime(440, now + 0.12)

      gain.gain.setValueAtTime(0.0001, now)
      gain.gain.exponentialRampToValueAtTime(0.12, now + 0.02)
      gain.gain.exponentialRampToValueAtTime(0.0001, now + 0.22)

      osc1.connect(gain)
      osc2.connect(gain)
      gain.connect(ctx.destination)

      osc1.start(now)
      osc2.start(now)
      osc1.stop(now + 0.23)
      osc2.stop(now + 0.23)
      setTimeout(() => ctx.close().catch(() => { }), 400)
    } catch {
      // audio autoplay policies can suppress this until first user gesture
    }
  }

  const [streamPaused, setStreamPaused] = useState(false)
  const [latestBatchInfo, setLatestBatchInfo] = useState({
    batchCount: 0,
    timestamp: null,
    overspeedCount: 0,
    delta: 0,
    isManual: false,
    fileName: ALL_RECORDS_LABEL,
  })
  const [dbStats, setDbStats] = useState({
    totalRecords: 0,
    totalPool: 0,
    overspeedRate: '0%',
    avgSpeed: 0,
    cameras: 0,
    plates: 0,
    vehicleTypes: {},
    activeCorridor: 'NH5 Highway',
  })

  function refreshStats() {
    fetch(`${apiBaseUrl}/api/vehicles/stats`)
      .then((res) => res.json())
      .then((data) => {
        if (data.success && data.stats) {
          setDbStats(data.stats)
        }
      })
      .catch(() => undefined)
  }

  useEffect(() => {
    if (!isAuthenticated) return
    refreshStats()
  }, [isAuthenticated])

  const userUploadedFileRef = useRef(false)

  const handleFetchRandomBatch = async () => {
    try {
      const response = await fetch(`${apiBaseUrl}/api/vehicles/stream-control`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'trigger' }),
      })
      const data = await response.json()
      if (data.success && Array.isArray(data.vehicles) && data.vehicles.length) {
        const streamRows = normalizeStreamRows(data.vehicles)
        setTrafficData((currentRows) => prependStreamRows(currentRows, streamRows))
        const overspeeds = streamRows.filter((r) => r.isOverSpeed || r.overSpeed === 'Yes').length
        setLatestBatchInfo({
          batchCount: streamRows.length,
          timestamp: new Date().toLocaleTimeString(),
          overspeedCount: overspeeds,
          delta: streamRows.length,
          isManual: true,
          fileName: ALL_RECORDS_LABEL,
        })
        playNotificationTone()
      }
    } catch (error) {
      console.warn('Unable to trigger random batch:', error)
    }
  }

  const handleToggleStreamPause = async () => {
    try {
      const nextAction = streamPaused ? 'resume' : 'pause'
      const response = await fetch(`${apiBaseUrl}/api/vehicles/stream-control`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: nextAction }),
      })
      const data = await response.json()
      if (data.success) {
        setStreamPaused(data.isPaused)
      }
    } catch (error) {
      console.warn('Unable to toggle stream pause:', error)
    }
  }

  useEffect(() => {
    if (!isAuthenticated) return undefined

    let isCancelled = false

    async function loadInitialVehicles() {
      try {
        const response = await fetch(`${apiBaseUrl}/api/vehicles?limit=${MAX_ROWS}`)
        if (!response.ok) return
        const data = await response.json()
        if (!isCancelled && !userUploadedFileRef.current && Array.isArray(data.vehicles) && data.vehicles.length) {
          const streamRows = normalizeStreamRows(data.vehicles)
          setTrafficData((currentRows) => (userUploadedFileRef.current ? currentRows : prependStreamRows(currentRows, streamRows)))
          setFileName((currentName) => currentName || ALL_RECORDS_LABEL)
          setLatestBatchInfo({
            batchCount: streamRows.length,
            timestamp: new Date().toLocaleTimeString(),
            overspeedCount: streamRows.filter((r) => r.isOverSpeed || r.overSpeed === 'Yes').length,
            delta: streamRows.length,
            isManual: false,
            fileName: ALL_RECORDS_LABEL,
          })
        }
      } catch (error) {
        console.warn('Unable to load initial vehicles from database:', error.message)
      }
    }

    loadInitialVehicles()

    const socket = io(apiBaseUrl, {
      transports: ['websocket', 'polling'],
      reconnectionAttempts: 10,
    })

    socket.on('newVehicleBatch', (incomingVehicles) => {
      if (!Array.isArray(incomingVehicles) || !incomingVehicles.length || isCancelled) return
      const streamRows = normalizeStreamRows(incomingVehicles)
      if (!userUploadedFileRef.current) {
        const batchSourceFile = incomingVehicles[0]?.sourceFile || incomingVehicles[0]?.fileName
        setTrafficData((currentRows) => prependStreamRows(currentRows, streamRows))
        if (batchSourceFile) {
          setFileName((currentName) => currentName && currentName !== ALL_RECORDS_LABEL ? currentName : ALL_RECORDS_LABEL)
        }
        const overspeeds = streamRows.filter((r) => r.isOverSpeed || r.overSpeed === 'Yes').length
        setLatestBatchInfo((prev) => ({
          batchCount: streamRows.length,
          timestamp: new Date().toLocaleTimeString(),
          overspeedCount: overspeeds,
          delta: streamRows.length,
          isManual: false,
          fileName: prev.fileName || ALL_RECORDS_LABEL,
        }))
        const firstRow = streamRows[0]
        const label = firstRow.vehicleNumberPlate || firstRow.plateNumber || firstRow.id || 'Live vehicle'
        const type = firstRow.vehicleType || firstRow.type || 'Detection'
        const sourceLabel = batchSourceFile ? batchSourceFile.replace(/\.[^/.]+$/, '') : 'Surveillance'
        setStreamNotifications((prev) => [
          {
            id: `${Date.now()}-${Math.random().toString(16).slice(2, 6)}`,
            title: `+${streamRows.length} ${sourceLabel} Records: ${label}`,
            message: `${type} captured at ${firstRow.location || firstRow.roadName || 'Traffic Corridor'}.`,
            timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
          },
          ...prev.slice(0, 11),
        ])
        playNotificationTone()
      }
    })

    // a processed video was added to / deleted from the Video Library
    socket.on('nh5LibraryChanged', (payload) => {
      if (isCancelled) return
      const removed = payload?.removed || []
      if (removed.length) {
        setTrafficData((currentRows) => currentRows.filter((row) => !removed.some((jobId) => String(row.sourceFile || '').includes(`[${jobId}]`))))
      }
      refreshStats()
    })

    socket.on('vehicleStreamComplete', (payload) => {
      if (!userUploadedFileRef.current) {
        setStreamNotifications((prev) => [
          {
            id: `${Date.now()}-complete`,
            title: 'Telemetry Stream Cycle Completed',
            message: payload?.fileName
              ? `Completed random polling cycle across ${payload.totalRows || 0} records in ${payload.fileName}.`
              : 'Dataset processing cycle completed.',
            timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
          },
          ...prev.slice(0, 11),
        ])
      }
    })

    socket.on('vehicleStreamStatus', (status) => {
      if (!isCancelled) {
        if (status?.fileName) {
          setFileName(status.fileName)
        }
        if (typeof status?.isPaused === 'boolean') {
          setStreamPaused(status.isPaused)
        }
        if (status?.totalPool) {
          setDbStats((prev) => ({
            ...prev,
            totalPool: status.totalPool,
            totalRecords: status.totalPool,
          }))
        }
        if (status?.batchCount) {
          setLatestBatchInfo((prev) => ({
            ...prev,
            batchCount: status.batchCount,
            timestamp: status.timestamp || new Date().toLocaleTimeString(),
            overspeedCount: status.overspeeding || status.overspeed || 0,
            delta: status.batchCount,
            fileName: status.fileName || prev.fileName,
          }))
        }
      }
    })

    return () => {
      isCancelled = true
      socket.disconnect()
    }
  }, [isAuthenticated])

  useEffect(() => {
    try {
      localStorage.setItem(
        storedProjectsKey,
        JSON.stringify(projectList.filter((project) => project.created)),
      )
    } catch {
      // ignore localStorage write errors
    }
  }, [projectList])

  useEffect(() => {
    try {
      localStorage.setItem(storedCamerasKey, JSON.stringify(addedCameras))
    } catch {
      // ignore localStorage write errors
    }
  }, [addedCameras])

  useEffect(() => {
    try {
      localStorage.setItem(storedRemovedCamerasKey, JSON.stringify(removedCameras))
    } catch {
      // ignore localStorage write errors
    }
  }, [removedCameras])

  useEffect(() => {
    try {
      localStorage.setItem(storedNotificationsKey, JSON.stringify(streamNotifications))
    } catch {
      // ignore localStorage write errors
    }
  }, [streamNotifications])

  const hasImportedFile = Boolean(trafficData.length > 0 && fileName)

  if (loading) return <div className="auth-loading">Checking your session...</div>
  if (!isAuthenticated || pathname === '/login' || pathname === '/signup') {
    return (
      <Routes>
        <Route path="/signup" element={isAuthenticated ? <Navigate replace to="/home" /> : <SignupPage />} />
        <Route path="*" element={isAuthenticated ? <Navigate replace to="/home" /> : <LoginPage />} />
      </Routes>
    )
  }

  function handleSelectProject(project) {
    setSelectedProject(project)
  }

  function handleCreateProject(name) {
    const newProject = {
      name,
      caption: 'Created project',
      status: 'Active',
      modules: '7 modules',
      dashboards: '3 dashboards',
      data: 'CSV analytics',
      created: true,
      createdAt: new Date().toISOString(),
    }
    setProjectList((current) => [...current, newProject])
    setSelectedProject(newProject)
  }

  function handleDeleteProject(name) {
    setProjectList((current) => current.filter((p) => p.name !== name))
    if (selectedProject?.name === name) {
      setSelectedProject(projectList.find((p) => p.name !== name) || projects[0])
    }
    if (connectedProject?.name === name) {
      setConnectedProject(null)
      userUploadedFileRef.current = false
      setTrafficData([])
      setFileName('')
    }
  }

  function handleProjectConnect(project) {
    setConnectedProject(project)
    setSelectedProject(project)
  }

  function handleProjectDisconnect() {
    setConnectedProject(null)
    userUploadedFileRef.current = false
    setTrafficData([])
    setFileName('')
  }

  function handleAddCamera(camera) {
    setAddedCameras((currentCameras) => [...currentCameras, camera])
  }

  function handleRemoveCamera(cameraId) {
    setAddedCameras((currentCameras) => currentCameras.filter((camera) => camera.id !== cameraId))
    setRemovedCameras((currentCameras) => currentCameras.includes(cameraId) ? currentCameras : [...currentCameras, cameraId])
  }

  async function handleImport(event) {
    const file = event.target.files?.[0]
    if (!file) return

    try {
      setImportError('')
      // 1. Parse uploaded CSV or XLSX on client
      const importedRows = await parseTrafficCsv(file)
      if (!importedRows || !importedRows.length) {
        throw new Error('No valid records found in the selected file.')
      }

      // 2. Extract clean telemetry metadata (strip large base64/synthetic SVGs so payload remains fast and lightweight)
      const cleanRows = importedRows.map((r, idx) => ({
        id: r.id || r.observationId || r.csvRecordId || `REC-${idx + 1}`,
        timestamp: r.timestampIst || r.timestamp || r.time || '',
        vehicleType: r.vehicleType || r.type || 'Car',
        numberPlate: r.vehicleNumberPlate || r.numberPlate || r.plate || '',
        plateConfidence: r.plateConfidence || r.confidence || 0.95,
        speed: Number(r.speed) || 60,
        speedLimit: Number(r.speedLimit) || 60,
        overSpeed: r.overSpeed || (r.isOverSpeed ? 'Yes' : 'No'),
        isOverSpeed: Boolean(r.isOverSpeed || r.overSpeed === 'Yes'),
        latitude: Number(r.latitude) || 17.385044,
        longitude: Number(r.longitude) || 78.486671,
        videoClipPath: r.videoClipPath && !r.videoClipPath.startsWith('data:') ? r.videoClipPath : '',
        vehicleImagePath: r.vehicleImagePath && !r.vehicleImagePath.startsWith('data:') ? r.vehicleImagePath : '',
        plateImagePath: r.plateImagePath && !r.plateImagePath.startsWith('data:') ? r.plateImagePath : '',
        events: r.events || (r.isOverSpeed ? 'Overspeeding' : 'Standard detection'),
        camera: r.camera || '',
        location: r.location || r.roadName || '',
      }))

      // 3. Upload and store records in MySQL database
      // Upload in chunks of 2,500 if file is large, ensuring fast and reliable transfers
      const CHUNK_SIZE = 2500
      let lastResult = null

      if (cleanRows.length <= CHUNK_SIZE) {
        const response = await fetch(`${apiBaseUrl}/api/vehicles/upload`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            fileName: file.name,
            rows: cleanRows,
            isAppend: false,
            isLastChunk: true,
            totalRecords: cleanRows.length,
          }),
        })

        const contentType = response.headers.get('content-type') || ''
        if (contentType.includes('application/json')) {
          lastResult = await response.json()
        } else {
          const text = await response.text()
          throw new Error(
            response.ok
              ? 'Server returned non-JSON response.'
              : `Upload failed (status ${response.status}): ${text.slice(0, 150)}`
          )
        }

        if (!response.ok || !lastResult.success) {
          throw new Error(lastResult?.message || `Database upload failed (status ${response.status}).`)
        }
      } else {
        // Chunked upload for large datasets
        for (let i = 0; i < cleanRows.length; i += CHUNK_SIZE) {
          const chunk = cleanRows.slice(i, i + CHUNK_SIZE)
          const isFirst = i === 0
          const isLast = i + CHUNK_SIZE >= cleanRows.length

          const response = await fetch(`${apiBaseUrl}/api/vehicles/upload`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              fileName: file.name,
              rows: chunk,
              isAppend: !isFirst,
              isLastChunk: isLast,
              totalRecords: cleanRows.length,
            }),
          })

          const contentType = response.headers.get('content-type') || ''
          let chunkResult
          if (contentType.includes('application/json')) {
            chunkResult = await response.json()
          } else {
            const text = await response.text()
            throw new Error(`Upload failed (status ${response.status}): ${text.slice(0, 150)}`)
          }

          if (!response.ok || !chunkResult.success) {
            throw new Error(chunkResult?.message || `Chunk upload failed at record ${i}.`)
          }
          lastResult = chunkResult
        }
      }

      // 4. Immediately update dashboard state with newly uploaded dataset
      userUploadedFileRef.current = false // Live stream sequentially draws random batches from DB for this file!
      setFileName(file.name)

      // Initial batch from the new uploaded dataset (1-20 records)
      const initialBatch = lastResult?.initialBatch && lastResult.initialBatch.length
        ? normalizeStreamRows(lastResult.initialBatch)
        : importedRows.slice(0, Math.floor(Math.random() * 20) + 1)

      setTrafficData(initialBatch)

      setLatestBatchInfo({
        batchCount: initialBatch.length,
        timestamp: new Date().toLocaleTimeString(),
        overspeedCount: initialBatch.filter((r) => r.isOverSpeed || r.overSpeed === 'Yes').length,
        delta: initialBatch.length,
        isManual: true,
        fileName: file.name,
      })

      // Fetch fresh database stats for the uploaded file
      fetch(`${apiBaseUrl}/api/vehicles/stats?fileName=${encodeURIComponent(file.name)}`)
        .then((res) => {
          if (res.ok && res.headers.get('content-type')?.includes('application/json')) {
            return res.json()
          }
          return null
        })
        .then((data) => {
          if (data && data.success && data.stats) {
            setDbStats(data.stats)
          }
        })
        .catch(() => undefined)

      setStreamNotifications((prev) => [
        {
          id: `${Date.now()}-upload`,
          title: `Dataset Uploaded: ${file.name}`,
          message: `Stored ${cleanRows.length.toLocaleString()} records in MySQL database. Telemetry stream is now live for ${file.name}.`,
          timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        },
        ...prev.slice(0, 11),
      ])

      playNotificationTone()
    } catch (error) {
      console.error('Import error:', error)
      setImportError(error.message || 'Unable to import file.')
    } finally {
      event.target.value = ''
    }
  }

  return (
    <ProtectedRoute>
      <ErrorBoundary>
        <div className="app-shell">
          <Sidebar
            connectedProject={connectedProject}
            onCreateProject={handleCreateProject}
            onSelectProject={handleSelectProject}
            projectList={projectList}
            selectedProject={selectedProject}
          />

          <main className="main-content">
            <Topbar
              notificationSoundEnabled={notificationSoundEnabled}
              searchOpen={searchOpen}
              setSearchOpen={setSearchOpen}
              setNotificationSoundEnabled={setNotificationSoundEnabled}
              streamNotifications={streamNotifications}
            />

            <section className="content-wrap">
              <Suspense fallback={<div className="auth-loading">Loading…</div>}>
              <Routes>
                {/* HOME */}
                <Route path="/" element={<Navigate replace to="/home" />} />
                <Route
                  path="/home"
                  element={
                    !connectedProject ? (
                      <ProjectConnectionRequired />
                    ) : (
                      <PlaceholderPage
                        cameraCount={addedCameras.length}
                        dbStats={dbStats}
                        fileName={fileName}
                        latestBatchInfo={latestBatchInfo}
                        onFetchRandomBatch={handleFetchRandomBatch}
                        onToggleStreamPause={handleToggleStreamPause}
                        rows={trafficData}
                        streamNotifications={streamNotifications}
                        streamPaused={streamPaused}
                      />
                    )
                  }
                />

                {/* PROJECTS MANAGEMENT (NEO4J DESKTOP STYLE) */}
                <Route
                  path="/projects"
                  element={
                    <ProjectsPage
                      connectedProject={connectedProject}
                      dbStats={dbStats}
                      fileName={fileName}
                      hasImportedFile={hasImportedFile}
                      importError={importError}
                      onCreateProject={handleCreateProject}
                      onDeleteProject={handleDeleteProject}
                      onImport={handleImport}
                      onProjectConnect={handleProjectConnect}
                      onProjectDisconnect={handleProjectDisconnect}
                      onSelectProject={handleSelectProject}
                      projectList={projectList}
                      rows={trafficData}
                      selectedProject={selectedProject}
                      setImportError={setImportError}
                    />
                  }
                />

                {/* ONTOLOGY */}
                <Route
                  path="/ontology"
                  element={
                    !connectedProject ? (
                      <ProjectConnectionRequired />
                    ) : (
                      <OntologyPage
                        fileName={fileName}
                        importError={importError}
                        onImport={handleImport}
                        projectName={connectedProject.name}
                        rows={trafficData}
                      />
                    )
                  }
                />

                {/* KNOWLEDGE GRAPH */}
                <Route
                  path="/knowledge-graph"
                  element={
                    !connectedProject ? (
                      <ProjectConnectionRequired />
                    ) : (
                      <KnowledgeGraphPage
                        fileName={fileName}
                        importError={importError}
                        onImport={handleImport}
                        projectName={connectedProject.name}
                        rows={trafficData}
                      />
                    )
                  }
                />

                {/* QUERY */}
                <Route
                  path="/query"
                  element={
                    !connectedProject ? (
                      <ProjectConnectionRequired />
                    ) : (
                      <QueryPage fileName={fileName} rows={trafficData} />
                    )
                  }
                />

                {/* DOCUMENT INTELLIGENCE */}
                <Route
                  path="/document-intelligence"
                  element={
                    !connectedProject ? (
                      <ProjectConnectionRequired />
                    ) : (
                      <DocumentIntelligence
                        fileName={fileName}
                        importError={importError}
                        onImport={handleImport}
                        projectName={connectedProject.name}
                        rows={trafficData}
                      />
                    )
                  }
                />

                {/* DASHBOARDS HUB */}
                <Route
                  path="/dashboards"
                  element={
                    !connectedProject ? (
                      <ProjectConnectionRequired />
                    ) : (
                      <DashboardHub
                        dbStats={dbStats}
                        fileName={fileName}
                        hasImportedFile={hasImportedFile}
                        importError={importError}
                        latestBatchInfo={latestBatchInfo}
                        onFetchRandomBatch={handleFetchRandomBatch}
                        onImport={handleImport}
                        onToggleStreamPause={handleToggleStreamPause}
                        projectName={connectedProject.name}
                        rows={trafficData}
                        streamPaused={streamPaused}
                      />
                    )
                  }
                />

                {/* DASHBOARD DETAILS */}
                <Route
                  path="/dashboards/:kind"
                  element={
                    !connectedProject ? (
                      <ProjectConnectionRequired />
                    ) : (
                      <DashboardDetail
                        addedCameras={addedCameras}
                        dbStats={dbStats}
                        fileName={fileName}
                        importError={importError}
                        latestBatchInfo={latestBatchInfo}
                        onAddCamera={handleAddCamera}
                        onFetchRandomBatch={handleFetchRandomBatch}
                        onImport={handleImport}
                        onRemoveCamera={handleRemoveCamera}
                        onToggleStreamPause={handleToggleStreamPause}
                        projectName={connectedProject.name}
                        removedCameras={removedCameras}
                        rows={trafficData}
                        streamPaused={streamPaused}
                      />
                    )
                  }
                />

                {/* NH5 DETECTION PIPELINE: uploads, live camera, library, road maps, model */}
                <Route path="/video-upload" element={<VideoUploadPage />} />
                <Route path="/live-camera" element={<LiveCameraPage />} />
                <Route path="/video-library" element={<VideoLibraryPage rows={trafficData} />} />
                <Route path="/video-library/:jobId" element={<VideoDetailPage />} />
                <Route path="/road-maps" element={<RoadMapsPage />} />
                <Route path="/road-maps/:sceneId" element={<RoadMapEditor />} />
                <Route path="/detection-model" element={<DetectionModelPage />} />

                {/* VEHICLE INFORMATION */}
                <Route path="/vehicle-information" element={<VehicleInformation />} />

                {/* RULES & EVENTS: CENTRAL GOVERNMENT TRAFFIC KNOWLEDGE BASE */}
                <Route path="/rules-events" element={<RulesEventsPage />} />

                {/* PROFILE & SETTINGS */}
                <Route path="/profile" element={<ProfilePage />} />
                <Route
                  path="/settings"
                  element={
                    <SettingsPage
                      notificationSoundEnabled={notificationSoundEnabled}
                      setNotificationSoundEnabled={setNotificationSoundEnabled}
                    />
                  }
                />

                {/* OTHER PLATFORM PAGES */}
                {routePaths
                  .filter(
                    (path) =>
                      path !== '/home' &&
                      !path.startsWith('/dashboards') &&
                      path !== '/ontology' &&
                      path !== '/knowledge-graph' &&
                      path !== '/query' &&
                      path !== '/document-intelligence' &&
                      path !== '/vehicle-information' &&
                      path !== '/rules-events' &&
                      !['/video-upload', '/live-camera', '/video-library', '/road-maps', '/detection-model'].includes(path) &&
                      path !== '/profile' &&
                      path !== '/settings'
                  )
                  .map((path) => (
                    <Route element={<PlaceholderPage />} key={path} path={path} />
                  ))}

                {/* UNKNOWN URL */}
                <Route path="*" element={<Navigate replace to="/home" />} />
              </Routes>
              </Suspense>
            </section>
          </main>
        </div>
      </ErrorBoundary>
    </ProtectedRoute>
  )
}
