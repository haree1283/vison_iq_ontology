import { createPortal } from 'react-dom'
import { useMemo, useState } from 'react'
import {
  Activity,
  AlertTriangle,
  ArrowLeft,
  BarChart3,
  Camera,
  Car,
  CheckCircle2,
  Database,
  FileText,
  Gauge,
  MapPin,
  Pause,
  Play,
  Radio,
  RefreshCw,
  ShieldCheck,
  Trash2,
  TrendingUp,
  Upload,
  Users,
  Zap,
} from 'lucide-react'
import { Link, useParams } from 'react-router-dom'
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { formatTimestampIst, groupBy, summarizeData } from '../data/dashboardData'
import { getVehicleMeta } from '../data/vehicleTypes'
import VehicleBadge from './VehicleBadge'
import VehicleImageThumbnail from './VehicleImageThumbnail'
import MediaPreviewModal from './MediaPreviewModal'

function getRecordTimestampScore(row) {
  const raw = String(row.timestampIst || row.timestamp || row.time || row.date || '')
  const parsed = Date.parse(raw)
  if (!isNaN(parsed)) return parsed
  const timeMatch = raw.match(/(\d{1,2}):(\d{2}):(\d{2})/)
  if (timeMatch) {
    return Number(timeMatch[1]) * 3600 + Number(timeMatch[2]) * 60 + Number(timeMatch[3])
  }
  const idNum = Number(String(row.id || row.csvRecordId || '').replace(/\D/g, ''))
  return idNum || 0
}

const configs = {
  vehicles: {
    number: '01',
    title: 'Vehicle Analytics',
    eyebrow: 'VEHICLE INTELLIGENCE',
    description: 'Vehicle types, HSRP plates, speeds, and classification mix along the NH-44 corridor.',
    icon: Car,
    chartTitle: 'Vehicles by Classification',
    chartKey: 'type',
    color: '#3b82f6',
  },
  traffic: {
    number: '02',
    title: 'Traffic Flow & Corridor Speed',
    eyebrow: 'FLOW INTELLIGENCE',
    description: 'Highway volume density, high-speed violation heatmaps, and corridor pressure.',
    icon: BarChart3,
    chartTitle: 'Traffic by Highway Checkpoint',
    chartKey: 'location',
    color: '#f59e0b',
  },
  cameras: {
    number: '03',
    title: 'Camera & Checkpoint Monitoring',
    eyebrow: 'COVERAGE INTELLIGENCE',
    description: 'Surveillance camera coverage, optical checkpoint health, and detection telemetry.',
    icon: Camera,
    chartTitle: 'Records by Optical Camera',
    chartKey: 'camera',
    color: '#10b981',
  },
}

export default function DashboardDetail({
  addedCameras = [],
  onAddCamera,
  onRemoveCamera,
  removedCameras = [],
  rows = [],
  fileName,
  onImport,
  importError,
  projectName,
  latestBatchInfo,
  streamPaused = false,
  onFetchRandomBatch,
  onToggleStreamPause,
  dbStats,
}) {
  const [previewModalRow, setPreviewModalRow] = useState(null)
  const [initialModalTab, setInitialModalTab] = useState('vehicle')
  const [cameraDialogOpen, setCameraDialogOpen] = useState(false)
  const [cameraRemoveDialogOpen, setCameraRemoveDialogOpen] = useState(false)
  const [isFetchingBatch, setIsFetchingBatch] = useState(false)
  const [cameraForm, setCameraForm] = useState({ name: '', location: '', streamUrl: '' })

  const { kind } = useParams()
  const config = configs[kind] || configs.vehicles
  const Icon = config.icon

  const safeRows = Array.isArray(rows) ? rows : []
  const summary = summarizeData(safeRows)

  const chartData = groupBy(safeRows, config.chartKey)
    .sort((a, b) => b.value - a.value)
    .slice(0, 10)

  const pieData = groupBy(safeRows, 'type')
    .sort((a, b) => b.value - a.value)
    .slice(0, 10)

  const topLocations = groupBy(safeRows, 'location')
    .sort((a, b) => b.value - a.value)
    .slice(0, 5)

  const importedCameras = groupBy(safeRows, 'camera').map((camera) => ({
    ...camera,
    id: camera.name,
    status: 'ACTIVE',
  }))

  const cameraRecords = [...importedCameras, ...addedCameras].filter(
    (camera) => !removedCameras.includes(camera.id),
  )
  const topCameras = cameraRecords.sort((a, b) => (b.value || 0) - (a.value || 0)).slice(0, 6)

  const averageSpeed = safeRows.length
    ? Math.round(safeRows.reduce((total, row) => total + Number(row.speed || 0), 0) / safeRows.length)
    : 62

  const overspeedRows = safeRows.filter((row) => row.overSpeed === 'Yes' || row.isOverSpeed)
  const overspeedCount = overspeedRows.length
  const overspeedPercent = safeRows.length ? Math.round((overspeedCount / safeRows.length) * 100) : 0

  function submitCamera(event) {
    event.preventDefault()
    if (!cameraForm.name.trim() || !onAddCamera) return
    onAddCamera({
      id: `CAM-NH44-${Date.now().toString().slice(-4)}`,
      name: cameraForm.name.trim(),
      location: cameraForm.location.trim() || 'NH-44 Corridor',
      streamUrl: cameraForm.streamUrl.trim(),
      value: 0,
      status: 'Active',
    })
    setCameraForm({ name: '', location: '', streamUrl: '' })
    setCameraDialogOpen(false)
  }

  const handleManualBatchClick = async () => {
    if (!onFetchRandomBatch || isFetchingBatch) return
    setIsFetchingBatch(true)
    try {
      await onFetchRandomBatch()
    } finally {
      setTimeout(() => setIsFetchingBatch(false), 500)
    }
  }

  // Strictly select the latest 12 records for display at the bottom of the dashboard
  const latestTenRows = useMemo(() => {
    if (!safeRows.length) return []
    const scored = safeRows.map((row, idx) => ({
      row,
      originalIdx: idx,
      score: getRecordTimestampScore(row),
    }))
    const hasScores = scored.some((s) => s.score > 0)
    if (hasScores) {
      scored.sort((a, b) => {
        if (b.score !== a.score) return b.score - a.score
        return b.originalIdx - a.originalIdx
      })
      return scored.slice(0, 12).map((s) => s.row)
    }
    return safeRows.slice(0, 12)
  }, [safeRows])

  return (
    <div className={`dashboard-page dashboard-detail-page dashboard-kind-${kind || 'vehicles'} nh44-theme`}>
      {/* TOP NAVIGATION & CONTROLS */}
      <div className="detail-back-row">
        <Link className="back-link" to="/dashboards">
          <ArrowLeft size={16} />
          Back to Highway Intelligence Hub
        </Link>
        <div className="header-actions">
          <label className="csv-import-button csv-import-button-small">
            <Upload size={14} />
            Import CSV / XLSX
            <input
              accept=".csv,text/csv,.xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,.xls,application/vnd.ms-excel"
              onChange={onImport}
              type="file"
            />
          </label>
        </div>
      </div>

      {importError && (
        <p className="csv-import-error" role="alert">
          {importError}
        </p>
      )}

      {/* VIEW HERO */}
      <div className="page-intro nh44-header">
        <div>
          <div className="nh44-badge-row">
            <span className="nh44-highway-tag">
              <Radio size={13} className="nh44-pulse-icon" />
              {fileName?.includes('NH44') ? 'NH-44 LIVE RADAR' : `${fileName || 'HIGHWAY'} RADAR`}
            </span>
            <span className="nh44-db-pill">
              <Database size={13} />
              {dbStats?.totalRecords || dbStats?.totalPool ? `${Number(dbStats.totalRecords || dbStats.totalPool).toLocaleString()} Archive Records (MySQL)` : 'MySQL Database Connected'}
            </span>
          </div>
          <h1>{config.title}</h1>
          <p className="intro-copy">{config.description}</p>
        </div>
        <div className="detail-heading-icon" style={{ borderColor: `${config.color}40`, color: config.color }}>
          <Icon size={26} />
        </div>
      </div>

      {/* LIVE HIGHWAY TELEMETRY CONTROL BAR */}
      <div className="nh44-stream-console">
        <div className="stream-console-status">
          <div className={`radar-indicator ${streamPaused ? 'paused' : 'active'}`}>
            <span className="radar-ring" />
            <span className="radar-dot" />
          </div>
          <div className="stream-status-text">
            <div className="stream-status-title">
              <strong>{streamPaused ? 'Stream Paused' : 'Live Highway Telemetry Streaming'}</strong>
              <span className="stream-source-tag">Source: {fileName || 'NH44_vehicles_5000_merged_with_images.xlsx'}</span>
            </div>
            <div className="stream-status-meta">
              {latestBatchInfo?.batchCount ? (
                <span className="batch-flash-pill">
                  <Zap size={13} />
                  +<strong>{latestBatchInfo.batchCount}</strong> records ingested in this batch (Random range 1–20)
                  <span className="batch-total-growth">
                    • Cumulative Total: <strong>{safeRows.length}</strong> records (Increasing ▲)
                  </span>
                  {latestBatchInfo.overspeedCount > 0 && (
                    <span className="batch-overspeed-tag">
                      ({latestBatchInfo.overspeedCount} speeding alerts)
                    </span>
                  )}
                </span>
              ) : (
                <span>Receiving random batches (1–20 rows) from MySQL database... Total: <strong>{safeRows.length}</strong> records</span>
              )}
            </div>
          </div>
        </div>

        <div className="stream-console-actions">
          <button
            className={`nh44-control-btn nh44-trigger-btn ${isFetchingBatch ? 'is-loading' : ''}`}
            onClick={handleManualBatchClick}
            type="button"
            title="Fetch a random batch of 1 to 20 records instantly"
          >
            <RefreshCw size={15} className={isFetchingBatch ? 'spin-icon' : ''} />
            <span>Fetch Random Batch (1–20)</span>
          </button>

          {onToggleStreamPause && (
            <button
              className={`nh44-control-btn nh44-pause-btn ${streamPaused ? 'resume' : ''}`}
              onClick={onToggleStreamPause}
              type="button"
            >
              {streamPaused ? (
                <>
                  <Play size={15} />
                  <span>Resume Stream</span>
                </>
              ) : (
                <>
                  <Pause size={15} />
                  <span>Pause Stream</span>
                </>
              )}
            </button>
          )}
        </div>
      </div>

      {/* KPI METRIC CARDS */}
      <div className="nh44-kpi-grid">
        <div className="nh44-kpi-card">
          <div className="kpi-icon-wrap" style={{ background: '#eff6ff', color: '#2563eb' }}>
            <TrendingUp size={22} />
          </div>
          <div className="kpi-content">
            <span className="kpi-label">Cumulative Ingested Data</span>
            <div className="kpi-value-row">
              <strong className="kpi-number">{safeRows.length}</strong>
              <span className="kpi-delta-tag success">▲ Increasing</span>
            </div>
            <span className="kpi-subtext">Accumulating random batches (1–20) live</span>
          </div>
        </div>

        <div className="nh44-kpi-card">
          <div className="kpi-icon-wrap" style={{ background: '#fef2f2', color: '#ef4444' }}>
            <AlertTriangle size={22} />
          </div>
          <div className="kpi-content">
            <span className="kpi-label">Speeding Violations</span>
            <div className="kpi-value-row">
              <strong className="kpi-number" style={{ color: '#dc2626' }}>
                {overspeedCount}
              </strong>
              <span className="kpi-delta-tag alert">{overspeedPercent}%</span>
            </div>
            <span className="kpi-subtext">Exceeding 60 km/h radar limit</span>
          </div>
        </div>

        <div className="nh44-kpi-card">
          <div className="kpi-icon-wrap" style={{ background: '#fffbeb', color: '#d97706' }}>
            <Gauge size={22} />
          </div>
          <div className="kpi-content">
            <span className="kpi-label">Average Speed</span>
            <div className="kpi-value-row">
              <strong className="kpi-number">{averageSpeed}</strong>
              <span className="kpi-unit">km/h</span>
            </div>
            <span className="kpi-subtext">Monitored along NH-44 corridor</span>
          </div>
        </div>

        <div className="nh44-kpi-card">
          <div className="kpi-icon-wrap" style={{ background: '#ecfdf5', color: '#059669' }}>
            <Camera size={22} />
          </div>
          <div className="kpi-content">
            <span className="kpi-label">Active Checkpoints</span>
            <div className="kpi-value-row">
              <strong className="kpi-number">{summary.uniqueLocations || 4}</strong>
              <span className="kpi-unit">gates</span>
            </div>
            <span className="kpi-subtext">Shamshabad, Shadnagar, Medchal</span>
          </div>
        </div>
      </div>

      {/* TRAFFIC FLOW SPECIFIC SECTION */}
      {kind === 'traffic' && (
        <section className="alternate-dashboard-layout traffic-flow-layout">
          <div className="flow-command-panel">
            <div className="flow-command-copy">
              <p className="section-kicker">LIVE FLOW PULSE</p>
              <h2>Corridor Radar Activity</h2>
              <span>Calculated across {safeRows.length} active detections</span>
            </div>
            <div className="flow-pulse">
              <Activity size={19} />
              <strong>{summary.total.toLocaleString()}</strong>
              <span>active detections</span>
            </div>
            <div className="flow-pulse warm">
              <Gauge size={19} />
              <strong>
                {averageSpeed} <small>km/h</small>
              </strong>
              <span>average speed</span>
            </div>
            <div className="flow-pulse alert">
              <Radio size={19} />
              <strong>{overspeedCount}</strong>
              <span>speed alerts</span>
            </div>
          </div>
          <div className="flow-location-board">
            <div className="alternate-section-heading">
              <div>
                <p className="section-kicker">PRESSURE DISTRIBUTION</p>
                <h2>Corridor Segments</h2>
              </div>
              <span className="nh44-live-indicator">
                <span className="pulse-dot" /> LIVE
              </span>
            </div>
            {topLocations.length ? (
              topLocations.map((location, index) => (
                <div className="flow-location-row" key={location.name}>
                  <span className="flow-location-rank">0{index + 1}</span>
                  <div>
                    <strong>{location.name}</strong>
                    <span>{location.value} detections</span>
                  </div>
                  <b>{Math.round((location.value / (summary.total || 1)) * 100)}%</b>
                  <i>
                    <em
                      style={{
                        width: `${Math.min(100, (location.value / (topLocations[0]?.value || 1)) * 100)}%`,
                      }}
                    />
                  </i>
                </div>
              ))
            ) : (
              <p className="alternate-empty">Waiting for traffic records...</p>
            )}
          </div>
        </section>
      )}

      {/* CAMERA COVERAGE SPECIFIC SECTION */}
      {kind === 'cameras' && (
        <section className="alternate-dashboard-layout camera-coverage-layout">
          <div className="camera-coverage-hero">
            <div>
              <p className="section-kicker">NETWORK MANAGEMENT</p>
              <h2>NH-44 Checkpoint Feeds</h2>
              <span>Active optical cameras capturing live highway events</span>
            </div>
            <div className="coverage-ring">
              <strong>{cameraRecords.length}</strong>
              <span>sources</span>
            </div>
            <div className="camera-control-actions">
              <button
                className="primary-action camera-add-button"
                onClick={() => setCameraDialogOpen(true)}
                type="button"
              >
                <Camera size={15} />
                Add new camera
              </button>
              <button
                className="camera-remove-button"
                onClick={() => setCameraRemoveDialogOpen(true)}
                type="button"
              >
                <Trash2 size={15} />
                Remove camera
              </button>
            </div>
          </div>
          <div className="camera-source-grid">
            {topCameras.length ? (
              topCameras.map((camera, index) => (
                <div className="camera-source-card" key={camera.id || camera.name}>
                  <div className="camera-source-icon">
                    <Camera size={17} />
                  </div>
                  <div>
                    <strong>{camera.name}</strong>
                    <span>
                      {camera.value || 0} records captured
                      {camera.location ? ` · ${camera.location}` : ''}
                    </span>
                  </div>
                  <b className={camera.status === 'Active' || index === 0 ? 'active' : ''}>
                    {camera.status || (index === 0 ? 'LIVE' : 'ACTIVE')}
                  </b>
                </div>
              ))
            ) : (
              <p className="alternate-empty">Waiting for camera records...</p>
            )}
          </div>
        </section>
      )}

      {/* VISUAL ANALYTICS CHARTS */}
      <div className="detail-chart-grid">
        <div className="dashboard-panel chart-panel nh44-chart-panel">
          <div className="panel-heading">
            <div>
              <p className="section-kicker">DATA REPRESENTATION</p>
              <h2>{config.chartTitle}</h2>
            </div>
            <span className="nh44-live-pill">Live Stream</span>
          </div>
          <div className="chart-frame" style={{ height: '260px' }}>
            <ResponsiveContainer height="100%" width="100%">
              <BarChart data={chartData} margin={{ top: 8, right: 8, left: -20, bottom: 4 }}>
                <CartesianGrid stroke="#f1f5f9" vertical={false} />
                <XAxis
                  axisLine={false}
                  dataKey="name"
                  tick={{ fill: '#64748b', fontSize: 10 }}
                  tickLine={false}
                />
                <YAxis axisLine={false} tick={{ fill: '#64748b', fontSize: 10 }} tickLine={false} />
                <Tooltip cursor={{ fill: '#f8fafc' }} />
                <Bar dataKey="value" radius={[5, 5, 0, 0]}>
                  {chartData.map((entry) => {
                    const barColor =
                      config.chartKey === 'type' ? getVehicleMeta(entry.name).color : config.color
                    return <Cell fill={barColor} key={entry.name} />
                  })}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="dashboard-panel chart-panel nh44-chart-panel">
          <div className="panel-heading">
            <div>
              <p className="section-kicker">COMPOSITION</p>
              <h2>Vehicle Classification Mix</h2>
            </div>
            <span className="nh44-live-pill">{pieData.length} Categories</span>
          </div>
          <div className="chart-frame pie-chart-frame" style={{ height: '200px' }}>
            <ResponsiveContainer height="100%" width="100%">
              <PieChart>
                <Pie
                  cx="50%"
                  cy="50%"
                  data={pieData}
                  dataKey="value"
                  innerRadius={50}
                  outerRadius={78}
                  paddingAngle={3}
                >
                  {pieData.map((entry) => (
                    <Cell fill={getVehicleMeta(entry.name).color} key={entry.name} />
                  ))}
                </Pie>
                <Tooltip />
              </PieChart>
            </ResponsiveContainer>
          </div>
          <div className="chart-legend">
            {pieData.map((entry) => {
              const meta = getVehicleMeta(entry.name)
              return (
                <span key={entry.name}>
                  <i style={{ background: meta.color }} />
                  {entry.name} <strong>{entry.value}</strong>
                </span>
              )
            })}
          </div>
        </div>
      </div>

      {/* CAMERA SETUP MODAL */}
      {cameraDialogOpen &&
        createPortal(
          <div className="modal-backdrop" onMouseDown={() => setCameraDialogOpen(false)}>
            <form
              className="camera-dialog"
              onMouseDown={(event) => event.stopPropagation()}
              onSubmit={submitCamera}
            >
              <div className="panel-heading">
                <div>
                  <p className="section-kicker">CHECKPOINT SETUP</p>
                  <h2>Add NH-44 Camera Feed</h2>
                </div>
                <button className="modal-close" onClick={() => setCameraDialogOpen(false)} type="button">
                  ×
                </button>
              </div>
              <label>
                Camera checkpoint name
                <input
                  autoFocus
                  onChange={(event) => setCameraForm({ ...cameraForm, name: event.target.value })}
                  placeholder="e.g. NH44-Shamshabad-South"
                  value={cameraForm.name}
                />
              </label>
              <label>
                Highway Location
                <input
                  onChange={(event) => setCameraForm({ ...cameraForm, location: event.target.value })}
                  placeholder="e.g. NH-44 KM 24.5 South Toll"
                  value={cameraForm.location}
                />
              </label>
              <label>
                Stream URL <span>(optional)</span>
                <input
                  onChange={(event) => setCameraForm({ ...cameraForm, streamUrl: event.target.value })}
                  placeholder="rtsp:// or https://"
                  value={cameraForm.streamUrl}
                />
              </label>
              <button className="primary-action" type="submit">
                <Camera size={15} />
                Add checkpoint
              </button>
            </form>
          </div>,
          document.body,
        )}

      {/* CAMERA REMOVAL MODAL */}
      {cameraRemoveDialogOpen &&
        createPortal(
          <div className="modal-backdrop" onMouseDown={() => setCameraRemoveDialogOpen(false)}>
            <div
              className="camera-dialog camera-remove-dialog"
              onMouseDown={(event) => event.stopPropagation()}
            >
              <div className="panel-heading">
                <div>
                  <p className="section-kicker">CAMERA ADMINISTRATION</p>
                  <h2>Remove Camera Feed</h2>
                </div>
                <button
                  className="modal-close"
                  onClick={() => setCameraRemoveDialogOpen(false)}
                  type="button"
                >
                  ×
                </button>
              </div>
              <p className="camera-dialog-copy">
                Select a checkpoint to remove it from surveillance monitoring.
              </p>
              <div className="camera-remove-list">
                {cameraRecords.length ? (
                  cameraRecords.map((camera) => (
                    <div className="camera-remove-row" key={camera.id}>
                      <div>
                        <strong>{camera.name}</strong>
                        <span>
                          {camera.location || `${camera.value || 0} records captured`} ·{' '}
                          {camera.status || 'ACTIVE'}
                        </span>
                      </div>
                      <button
                        className="camera-remove-confirm"
                        onClick={() => {
                          onRemoveCamera?.(camera.id)
                          setCameraRemoveDialogOpen(false)
                        }}
                        type="button"
                      >
                        <Trash2 size={14} />
                        Remove
                      </button>
                    </div>
                  ))
                ) : (
                  <p className="alternate-empty">No cameras are currently available.</p>
                )}
              </div>
            </div>
          </div>,
          document.body,
        )}

      {/* SOURCE RECORDS TABLE */}
      {safeRows.length > 0 && (
        <div className="dashboard-panel traffic-table-panel nh44-table-panel" style={{ marginTop: '24px' }}>
          <div className="panel-heading">
            <div>
              <p className="section-kicker">SOURCE RECORDS</p>
              <h2>Latest Detections ({config.title})</h2>
            </div>
            <div className="table-heading-right">
              <span className="nh44-live-indicator">
                <span className="pulse-dot" />
                Live Feed
              </span>
              <span className="record-count">
                Displaying latest {latestTenRows.length} of {safeRows.length} records
              </span>
            </div>
          </div>

          <div className="traffic-table-wrapper">
            <table className="traffic-table nh44-table">
              <thead>
                <tr>
                  <th>SURVEILLANCE SNAPSHOT</th>
                  <th>TIMESTAMP (IST)</th>
                  <th>VEHICLE TYPE</th>
                  <th>NUMBER PLATE (HSRP)</th>
                  <th>SPEED / LIMIT</th>
                  <th>RADAR STATUS</th>
                  <th>ANPR OCR</th>
                  <th>HIGHWAY CHECKPOINT</th>
                </tr>
              </thead>
              <tbody>
                {latestTenRows.map((row, index) => {
                  const isOver = row.overSpeed === 'Yes' || row.isOverSpeed
                  const speedNum = Number(row.speed || 0)
                  const speedLimit = Number(row.speedLimit || 60)
                  const plateText = row.vehicleNumberPlate || row.numberPlate
                  const confidenceVal = Math.round(
                    (row.plateConfidence || row.confidence) > 1
                      ? (row.plateConfidence || row.confidence)
                      : ((row.plateConfidence || row.confidence || 0.94) * 100),
                  )

                  return (
                    <tr
                      key={`${row.id || row.csvRecordId || row.observationId}-${index}`}
                      className={index === 0 && latestBatchInfo?.batchCount ? 'row-new-arrival' : ''}
                    >
                      <td style={{ minWidth: '130px' }}>
                        <VehicleImageThumbnail
                          onClick={() => {
                            setInitialModalTab('vehicle')
                            setPreviewModalRow(row)
                          }}
                          onPlayVideo={() => {
                            setInitialModalTab('video')
                            setPreviewModalRow(row)
                          }}
                          row={row}
                          size="table"
                        />
                      </td>
                      <td>
                        <div className="timestamp-cell">
                          <strong>{row.timestampIst || row.timestamp || 'Live'}</strong>
                          {index === 0 && <span className="new-tag">NEW</span>}
                        </div>
                      </td>
                      <td>
                        <VehicleBadge type={row.vehicleType || row.type} />
                      </td>
                      <td>
                        {plateText ? (
                          <div className="hsrp-plate-badge" title="High Security Registration Plate">
                            <span className="hsrp-country">
                              <span className="chakra-dot">☸</span>
                              IND
                            </span>
                            <span className="hsrp-code">{plateText}</span>
                          </div>
                        ) : (
                          <span className="query-plate-na">—</span>
                        )}
                      </td>
                      <td>
                        <div className="speed-metric-cell">
                          <strong className={isOver ? 'speed-val alert' : 'speed-val'}>
                            {speedNum}
                          </strong>
                          <span className="speed-denom">/ {speedLimit} km/h</span>
                        </div>
                      </td>
                      <td>
                        {isOver ? (
                          <span className="nh44-status-pill danger">
                            <AlertTriangle size={12} />
                            +{speedNum - speedLimit} km/h Over
                          </span>
                        ) : (
                          <span className="nh44-status-pill normal">
                            <CheckCircle2 size={12} />
                            Normal
                          </span>
                        )}
                      </td>
                      <td>
                        <span
                          className="nh44-confidence-badge"
                          style={{ color: confidenceVal >= 90 ? '#059669' : '#d97706' }}
                        >
                          {confidenceVal}%
                        </span>
                      </td>
                      <td>
                        <span className="nh44-location-cell">
                          <MapPin size={13} />
                          {row.location || row.camera || 'NH-44 Corridor'}
                        </span>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* MEDIA PREVIEW MODAL */}
      {previewModalRow && (
        <MediaPreviewModal
          allRows={latestTenRows}
          initialTab={initialModalTab}
          isOpen={Boolean(previewModalRow)}
          onClose={() => setPreviewModalRow(null)}
          onSelectRow={setPreviewModalRow}
          row={previewModalRow}
        />
      )}
    </div>
  )
}
