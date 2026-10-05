import { useMemo, useState } from 'react'
import {
  Activity,
  AlertTriangle,
  ArrowRight,
  BarChart3,
  Camera,
  Car,
  CheckCircle2,
  Database,
  Gauge,
  MapPin,
  Pause,
  Play,
  Radio,
  RefreshCw,
  ShieldCheck,
  TrendingUp,
  Upload,
  Zap,
} from 'lucide-react'
import { Link } from 'react-router-dom'
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
import { groupBy, summarizeData } from '../data/dashboardData'
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

export default function DashboardHub({
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
  const [isFetchingBatch, setIsFetchingBatch] = useState(false)

  const safeRows = Array.isArray(rows) ? rows : []
  const summary = summarizeData(safeRows)

  // Compute live vehicle statistics from the active stream window
  const overspeedRows = safeRows.filter((r) => r.isOverSpeed || r.overSpeed === 'Yes')
  const overspeedCount = overspeedRows.length
  const overspeedPercent = safeRows.length ? Math.round((overspeedCount / safeRows.length) * 100) : 0

  const averageSpeed = safeRows.length
    ? Math.round(safeRows.reduce((acc, r) => acc + Number(r.speed || 0), 0) / safeRows.length)
    : 62

  const averageConfidence = safeRows.length
    ? Math.round(
        safeRows.reduce((acc, r) => {
          const conf = Number(r.plateConfidence || r.confidence || 0.94)
          return acc + (conf > 1 ? conf : conf * 100)
        }, 0) / safeRows.length,
      )
    : 96

  // Vehicle type distribution for Bar Chart
  const vehicleTypeData = groupBy(safeRows, 'type')
    .sort((a, b) => b.value - a.value)
    .slice(0, 8)

  // Speed compliance distribution for Donut Chart
  const speedProfileData = [
    { name: 'Normal (<= 60 km/h)', value: safeRows.length - overspeedCount, color: '#10b981' },
    { name: 'Over Speed (> 60 km/h)', value: overspeedCount, color: '#ef4444' },
  ].filter((d) => d.value > 0)

  // Top corridor checkpoints
  const topLocations = groupBy(safeRows, 'location')
    .sort((a, b) => b.value - a.value)
    .slice(0, 4)

  // Strictly select the latest 12 records for display at the bottom
  const latestDetections = useMemo(() => {
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

  const handleManualBatchClick = async () => {
    if (!onFetchRandomBatch || isFetchingBatch) return
    setIsFetchingBatch(true)
    try {
      await onFetchRandomBatch()
    } finally {
      setTimeout(() => setIsFetchingBatch(false), 500)
    }
  }

  const dashboardCards = [
    {
      path: '/dashboards/vehicles',
      number: '01',
      title: 'Vehicle Analytics',
      subtitle: `${summary.total} Monitored Vehicles`,
      description: 'Vehicle types, HSRP plates, speed profiling, and ANPR accuracy metrics.',
      icon: Car,
      accent: '#3b82f6',
      badge: `${vehicleTypeData.length} Types Active`,
    },
    {
      path: '/dashboards/traffic',
      number: '02',
      title: 'Traffic Flow & Corridor Speed',
      subtitle: `${averageSpeed} km/h Avg Velocity`,
      description: 'Highway volume density, high-speed violation heatmaps, and corridor pressure.',
      icon: BarChart3,
      accent: '#f59e0b',
      badge: `${overspeedPercent}% Overspeeding`,
    },
    {
      path: '/dashboards/cameras',
      number: '03',
      title: 'Camera Network & Gateways',
      subtitle: `${summary.uniqueCameras || 6} Checkpoint Feeds`,
      description: 'ANPR optical cameras, gateway coverage along NH-44, and checkpoint health.',
      icon: Camera,
      accent: '#10b981',
      badge: 'All Feeds Ready',
    },
  ]

  return (
    <div className="dashboard-page dashboard-hub nh44-theme">
      {/* PAGE HEADER */}
      <div className="page-intro nh44-header">
        <div>
          <div className="nh44-badge-row">
            <span className="nh44-highway-tag">
              <Radio size={13} className="nh44-pulse-icon" />
              {fileName?.includes('NH44') ? 'NH-44 HYDERABAD-BENGALURU HIGHWAY RADAR' : `${fileName || 'HIGHWAY'} RADAR FEED`}
            </span>
            <span className="nh44-db-pill">
              <Database size={13} />
              {dbStats?.totalRecords ? `${Number(dbStats.totalRecords).toLocaleString()} Records Ingested (MySQL)` : 'MySQL Database Connected'}
            </span>
          </div>
          <h1>Highway Traffic Intelligence</h1>
          <p className="intro-copy">
            Live telemetry connected to {projectName}. Processing random batches (1–20 records) from {fileName || 'MySQL database archive'}.
          </p>
        </div>
        <div className="header-actions">
          <label className="csv-import-button">
            <Upload size={16} />
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

      {/* LIVE TELEMETRY & STREAM CONTROL CONSOLE */}
      <div className="nh44-stream-console">
        <div className="stream-console-status">
          <div className={`radar-indicator ${streamPaused ? 'paused' : 'active'}`}>
            <span className="radar-ring" />
            <span className="radar-dot" />
          </div>
          <div className="stream-status-text">
            <div className="stream-status-title">
              <strong>{streamPaused ? 'Stream Paused' : 'Live Highway Feed Active'}</strong>
              <span className="stream-source-tag">Source: {fileName || 'NH44_vehicles_5000_merged_with_images.xlsx'}</span>
            </div>
            <div className="stream-status-meta">
              {latestBatchInfo?.batchCount ? (
                <span className="batch-flash-pill">
                  <Zap size={13} />
                  +<strong>{latestBatchInfo.batchCount}</strong> records arrived in this batch (Random range 1–20)
                  <span className="batch-total-growth">
                    • Cumulative Total: <strong>{safeRows.length}</strong> records (Increasing ▲)
                  </span>
                  {latestBatchInfo.overspeedCount > 0 && (
                    <span className="batch-overspeed-tag">
                      ({latestBatchInfo.overspeedCount} speed violation{latestBatchInfo.overspeedCount > 1 ? 's' : ''})
                    </span>
                  )}
                </span>
              ) : (
                <span>Streaming live telemetry from MySQL database... Total: <strong>{safeRows.length}</strong> records</span>
              )}
            </div>
          </div>
        </div>

        <div className="stream-console-actions">
          <button
            className={`nh44-control-btn nh44-trigger-btn ${isFetchingBatch ? 'is-loading' : ''}`}
            onClick={handleManualBatchClick}
            type="button"
            title="Pulls a random batch of 1 to 20 records from all records in the database"
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

      {/* DYNAMIC KPI METRICS ROW */}
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
              <span className="kpi-delta-tag alert">
                {overspeedPercent}% rate
              </span>
            </div>
            <span className="kpi-subtext">Exceeding 60 km/h limit on NH-44</span>
          </div>
        </div>

        <div className="nh44-kpi-card">
          <div className="kpi-icon-wrap" style={{ background: '#fffbeb', color: '#d97706' }}>
            <Gauge size={22} />
          </div>
          <div className="kpi-content">
            <span className="kpi-label">Corridor Avg Speed</span>
            <div className="kpi-value-row">
              <strong className="kpi-number">{averageSpeed}</strong>
              <span className="kpi-unit">km/h</span>
            </div>
            <span className="kpi-subtext">Calculated across live batch stream</span>
          </div>
        </div>

        <div className="nh44-kpi-card">
          <div className="kpi-icon-wrap" style={{ background: '#ecfdf5', color: '#059669' }}>
            <ShieldCheck size={22} />
          </div>
          <div className="kpi-content">
            <span className="kpi-label">ANPR Optical Match</span>
            <div className="kpi-value-row">
              <strong className="kpi-number">{averageConfidence}%</strong>
              <span className="kpi-delta-tag success">High Quality</span>
            </div>
            <span className="kpi-subtext">HSRP plate detection confidence</span>
          </div>
        </div>

        <div className="nh44-kpi-card">
          <div className="kpi-icon-wrap" style={{ background: '#f3e8ff', color: '#7c3aed' }}>
            <Database size={22} />
          </div>
          <div className="kpi-content">
            <span className="kpi-label">Database Pool</span>
            <div className="kpi-value-row">
              <strong className="kpi-number">{dbStats?.totalRecords || dbStats?.totalPool ? Number(dbStats.totalRecords || dbStats.totalPool).toLocaleString() : '0'}</strong>
              <span className="kpi-unit">records</span>
            </div>
            <span className="kpi-subtext">All {dbStats?.totalRecords || dbStats?.totalPool ? Number(dbStats.totalRecords || dbStats.totalPool).toLocaleString() : '0'} vehicle records</span>
          </div>
        </div>
      </div>

      {/* THREE INTERACTIVE DASHBOARD MODULES */}
      <div className="dashboard-card-grid nh44-modules-grid">
        {dashboardCards.map(({ path, number, title, subtitle, description, icon: Icon, accent, badge }) => (
          <Link className="dashboard-card nh44-module-card" key={path} to={path}>
            <div className="nh44-card-header">
              <div className="card-top-icon" style={{ borderColor: `${accent}40`, color: accent }}>
                <Icon size={20} />
              </div>
              <div className="card-meta">
                <span className="dashboard-card-number">{number}</span>
                <span className="card-badge-pill" style={{ color: accent, borderColor: `${accent}30`, background: `${accent}10` }}>
                  {badge}
                </span>
              </div>
            </div>
            <div className="card-main">
              <h2>{title}</h2>
              <p className="card-subtitle">{subtitle}</p>
              <p className="card-description">{description}</p>
            </div>
            <div className="card-bottom">
              <span className="dashboard-card-link">
                Launch Dashboard <ArrowRight size={15} />
              </span>
            </div>
          </Link>
        ))}
      </div>

      {/* DYNAMIC VISUAL ANALYTICS SECTION */}
      <div className="nh44-analytics-section">
        {/* VEHICLE CLASSIFICATION CHART */}
        <div className="dashboard-panel nh44-chart-panel">
          <div className="panel-heading">
            <div>
              <p className="section-kicker">REAL-TIME CLASSIFICATION</p>
              <h2>Vehicle Type Distribution</h2>
            </div>
            <span className="nh44-live-pill">
              <Activity size={13} />
              Updated with live batch
            </span>
          </div>
          <div className="chart-frame" style={{ height: '240px', marginTop: '12px' }}>
            <ResponsiveContainer height="100%" width="100%">
              <BarChart data={vehicleTypeData} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                <CartesianGrid stroke="#f1f5f9" vertical={false} />
                <XAxis
                  axisLine={false}
                  dataKey="name"
                  tick={{ fill: '#64748b', fontSize: 11, fontWeight: 500 }}
                  tickLine={false}
                />
                <YAxis axisLine={false} tick={{ fill: '#64748b', fontSize: 11 }} tickLine={false} />
                <Tooltip
                  content={({ active, payload }) => {
                    if (active && payload && payload.length) {
                      const data = payload[0].payload
                      const meta = getVehicleMeta(data.name)
                      return (
                        <div className="chart-tooltip-box">
                          <strong style={{ color: meta.color }}>{data.name}</strong>
                          <p>{data.value} detections</p>
                          <small>{Math.round((data.value / (safeRows.length || 1)) * 100)}% of active stream</small>
                        </div>
                      )
                    }
                    return null
                  }}
                />
                <Bar dataKey="value" radius={[6, 6, 0, 0]}>
                  {vehicleTypeData.map((entry) => {
                    const meta = getVehicleMeta(entry.name)
                    return <Cell fill={meta.color} key={entry.name} />
                  })}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* SPEED COMPLIANCE & CORRIDOR PRESSURE */}
        <div className="dashboard-panel nh44-chart-panel">
          <div className="panel-heading">
            <div>
              <p className="section-kicker">SAFETY PROFILE</p>
              <h2>Speed & Corridor Pressure</h2>
            </div>
            <span className="nh44-live-pill">Limit: 60 km/h</span>
          </div>

          <div className="nh44-split-analytics">
            {/* Speed Profile Donut */}
            <div className="speed-donut-wrap">
              <div style={{ height: '160px', position: 'relative' }}>
                <ResponsiveContainer height="100%" width="100%">
                  <PieChart>
                    <Pie
                      cx="50%"
                      cy="50%"
                      data={speedProfileData}
                      dataKey="value"
                      innerRadius={48}
                      outerRadius={70}
                      paddingAngle={4}
                    >
                      {speedProfileData.map((entry) => (
                        <Cell fill={entry.color} key={entry.name} />
                      ))}
                    </Pie>
                    <Tooltip />
                  </PieChart>
                </ResponsiveContainer>
                <div className="speed-donut-center">
                  <strong>{overspeedPercent}%</strong>
                  <span>Speeding</span>
                </div>
              </div>
              <div className="speed-donut-legend">
                <div className="donut-legend-item">
                  <span className="legend-dot" style={{ background: '#10b981' }} />
                  <span>Normal: {safeRows.length - overspeedCount}</span>
                </div>
                <div className="donut-legend-item">
                  <span className="legend-dot" style={{ background: '#ef4444' }} />
                  <span>Over Speed: {overspeedCount}</span>
                </div>
              </div>
            </div>

            {/* Corridor Checkpoints */}
            <div className="corridor-pressure-wrap">
              <p className="corridor-title">Top Highway Checkpoints</p>
              <div className="corridor-list">
                {topLocations.map((loc, idx) => {
                  const percent = Math.round((loc.value / (safeRows.length || 1)) * 100)
                  return (
                    <div className="corridor-item" key={loc.name}>
                      <div className="corridor-header">
                        <span className="corridor-rank">0{idx + 1}</span>
                        <span className="corridor-name">{loc.name}</span>
                        <strong className="corridor-count">{loc.value}</strong>
                      </div>
                      <div className="corridor-bar-track">
                        <div
                          className="corridor-bar-fill"
                          style={{
                            width: `${percent}%`,
                            background: idx === 0 ? '#3b82f6' : idx === 1 ? '#06b6d4' : '#8b5cf6',
                          }}
                        />
                      </div>
                    </div>
                  )
                })}
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* REAL-TIME LATEST DETECTIONS TABLE */}
      {safeRows.length > 0 && (
        <div className="dashboard-panel traffic-table-panel nh44-table-panel" style={{ marginTop: '24px' }}>
          <div className="panel-heading">
            <div>
              <p className="section-kicker">LIVE OPTICAL DETECTIONS</p>
              <h2>Latest Detections Feed (NH-44 Corridor)</h2>
            </div>
            <div className="table-heading-right">
              <span className="nh44-live-indicator">
                <span className="pulse-dot" />
                Live Feed
              </span>
              <span className="record-count">
                Displaying latest {latestDetections.length} of {safeRows.length} active records
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
                {latestDetections.map((row, index) => {
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
                        <span className="nh44-confidence-badge" style={{ color: confidenceVal >= 90 ? '#059669' : '#d97706' }}>
                          {confidenceVal}%
                        </span>
                      </td>
                      <td>
                        <span className="nh44-location-cell">
                          <MapPin size={13} />
                          {row.location || row.camera || 'NH-44 Corridor Gateway'}
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
          allRows={latestDetections}
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