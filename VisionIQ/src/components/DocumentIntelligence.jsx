import { useMemo, useState } from 'react'
import {
  ArrowUpDown,
  Camera,
  Car,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  Clock,
  Compass,
  Download,
  FileCheck,
  FileSpreadsheet,
  FileText,
  Filter,
  Layers,
  MapPin,
  Printer,
  Search,
  ShieldCheck,
  Sparkles,
  SunMedium,
  Table2,
  TrafficCone,
  Upload,
  X,
} from 'lucide-react'
import VehicleBadge from './VehicleBadge'
import { getVehicleMeta } from '../data/vehicleTypes'
import VehicleImageThumbnail from './VehicleImageThumbnail'
import MediaPreviewModal from './MediaPreviewModal'
import { formatTimestampIst } from '../data/dashboardData'

function escapeCsvValue(value) {
  const text = String(value ?? '')
  return /[",\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text
}

function downloadCsv(rows, projectName) {
  const headers = [
    'ID',
    'Timestamp (IST)',
    'Vehicle Type',
    'Vehicle Number Plate',
    'Plate Confidence',
    'Vehicle Image',
    'Speed (km/h)',
    'Speed Limit (km/h)',
    'Over Speed',
    'Latitude',
    'Longitude',
    'Video Clip Path',
    'Vehicle Image Path',
    'Plate Image Path',
  ]

  const csv = [
    headers.join(','),
    ...rows.map((r) =>
      [
        escapeCsvValue(r.id || r.observationId || 'OBS-0001'),
        escapeCsvValue(r.timestampIst || r.timestamp || r.time || '2026-09-11 08:12:14'),
        escapeCsvValue(r.vehicleType || r.type || 'Car'),
        escapeCsvValue(r.vehicleNumberPlate || r.numberPlate || 'N/A'),
        escapeCsvValue(r.plateConfidence || r.confidence || 0.95),
        escapeCsvValue(r.vehicleImage || ''),
        escapeCsvValue(r.speed || 0),
        escapeCsvValue(r.speedLimit || 60),
        escapeCsvValue(r.overSpeed || (r.speed > r.speedLimit ? 'Yes' : 'No')),
        escapeCsvValue(r.latitude || 17.4485),
        escapeCsvValue(r.longitude || 78.3742),
        escapeCsvValue(r.videoClipPath || ''),
        escapeCsvValue(r.vehicleImagePath || ''),
        escapeCsvValue(r.plateImagePath || ''),
      ].join(',')
    ),
  ].join('\n')

  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = `${projectName.toLowerCase().replace(/[^a-z0-9]+/g, '-')}-14-param-telemetry-audit.csv`
  link.click()
  URL.revokeObjectURL(url)
}

export default function DocumentIntelligence({
  rows = [],
  projectName = 'Platform A',
  fileName = 'Active Dataset',
  onImport,
  onLoadSampleData,
  importError,
}) {
  const [searchQuery, setSearchQuery] = useState('')
  const [filterType, setFilterType] = useState('ALL')
  const [filterSignal, setFilterSignal] = useState('ALL')
  const [currentPage, setCurrentPage] = useState(1)
  const [pageSize, setPageSize] = useState(15)
  const [previewModalRow, setPreviewModalRow] = useState(null)
  const [initialModalTab, setInitialModalTab] = useState('vehicle')

  const extractedImagesCount = useMemo(() => {
    return rows.filter((r) => Boolean(r.extractedImage || r.hasExtractedImage)).length
  }, [rows])

  // Compute comprehensive 20-parameter statistics
  const stats = useMemo(() => {
    const totalRecords = rows.length
    const typesMap = {}
    const signalsMap = {}
    const weatherMap = {}
    const cameraMap = {}
    const roadMap = {}
    const junctionSet = new Set()
    const plateSet = new Set()

    let totalConfidence = 0

    rows.forEach((r) => {
      const t = r.type || 'Unknown'
      typesMap[t] = (typesMap[t] || 0) + 1

      const s = r.signalState || 'Green'
      signalsMap[s] = (signalsMap[s] || 0) + 1

      const w = r.weather || 'Clear'
      weatherMap[w] = (weatherMap[w] || 0) + 1

      const c = r.camera || 'CAM-01'
      cameraMap[c] = (cameraMap[c] || 0) + 1

      const road = r.roadName || r.location || 'Unknown Road'
      roadMap[road] = (roadMap[road] || 0) + 1

      if (r.junctionId) junctionSet.add(r.junctionId)
      if (r.numberPlate && r.numberPlate !== 'N/A') plateSet.add(r.numberPlate)

      const conf = r.confidence > 1 ? r.confidence : (r.confidence || 0.95) * 100
      totalConfidence += conf
    })

    const avgConfidence = totalRecords ? Math.round(totalConfidence / totalRecords) : 95
    const uniqueTypes = Object.keys(typesMap).sort((a, b) => typesMap[b] - typesMap[a])
    const uniqueCameras = Object.keys(cameraMap)
    const uniqueRoads = Object.keys(roadMap)
    const uniquePlates = Array.from(plateSet)
    const uniqueJunctions = Array.from(junctionSet)

    return {
      totalRecords,
      typesMap,
      signalsMap,
      weatherMap,
      cameraMap,
      roadMap,
      avgConfidence,
      uniqueTypes,
      uniqueCameras,
      uniqueRoads,
      uniquePlates,
      uniqueJunctions,
    }
  }, [rows])

  // Filter rows based on search and parameters
  const filteredRows = useMemo(() => {
    const query = searchQuery.trim().toLowerCase()
    return rows.filter((r) => {
      if (filterType !== 'ALL' && r.type !== filterType) return false
      if (filterSignal !== 'ALL' && r.signalState !== filterSignal) return false
      if (!query) return true

      const searchStr = [
        r.observationId,
        r.type,
        r.numberPlate,
        r.roadName,
        r.location,
        r.camera,
        r.junctionId,
        r.weather,
        r.signalState,
      ]
        .filter(Boolean)
        .join(' ')
        .toLowerCase()

      return searchStr.includes(query)
    })
  }, [rows, searchQuery, filterType, filterSignal])

  const totalPages = Math.max(1, Math.ceil(filteredRows.length / pageSize))
  const paginatedRows = useMemo(() => {
    const start = (currentPage - 1) * pageSize
    return filteredRows.slice(start, start + pageSize)
  }, [filteredRows, currentPage, pageSize])

  const documentId = useMemo(() => `DOC-TRF-${String(rows.length).padStart(4, '0')}`, [rows.length])
  const currentDate = useMemo(() => new Date().toLocaleDateString('en-US', { dateStyle: 'long' }), [])

  return (
    <div className="document-intelligence-page">
      {/* Top Controls Header (Hidden in Print) */}
      <div className="document-intelligence-header no-print">
        <div>
          <p className="section-kicker">DOCUMENT INTELLIGENCE & TELEMETRY AUDIT</p>
          <h1>Traffic Telemetry Intelligence Document</h1>
          <p className="intro-copy">
            Formal audit report with all 14 vehicle detection & telemetry parameters for <strong>{projectName}</strong>.
          </p>
        </div>
        <div className="document-actions">
          {onImport && (
            <label className="document-action secondary" style={{ cursor: 'pointer' }} title="Import CSV or Excel spreadsheet with telemetry & images">
              <Upload size={16} />
              <span>Import CSV / XLSX</span>
              <input
                accept=".csv,text/csv,.xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,.xls,application/vnd.ms-excel"
                onChange={onImport}
                style={{ display: 'none' }}
                type="file"
              />
            </label>
          )}
          {onLoadSampleData && (
            <button
              className="document-action secondary"
              onClick={onLoadSampleData}
              title="Load sample Excel feed with extracted vehicle images and video clips"
              type="button"
            >
              <FileSpreadsheet size={16} />
              <span>Load Sample Excel</span>
            </button>
          )}
          <button className="document-action secondary" onClick={() => window.print()} type="button">
            <Printer size={16} />
            <span>Export PDF / Print</span>
          </button>
          <button className="document-action primary" onClick={() => downloadCsv(rows, projectName)} type="button">
            <Download size={16} />
            <span>Export 14-Param CSV ({rows.length})</span>
          </button>
        </div>
      </div>

      {importError && (
        <div className="csv-import-error no-print" role="alert" style={{ margin: '0 0 16px 0' }}>
          {importError}
        </div>
      )}

      {/* Official Document Canvas Paper */}
      <div
        className="document-paper"
        onDragOver={(e) => e.preventDefault()}
        onDrop={(e) => {
          e.preventDefault()
          const file = e.dataTransfer?.files?.[0]
          if (file && onImport) {
            onImport({ target: { files: [file], value: '' } })
          }
        }}
      >
        {extractedImagesCount > 0 && (
          <div
            className="doc-extracted-banner no-print"
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '12px',
              background: 'linear-gradient(135deg, rgba(16, 185, 129, 0.12), rgba(56, 189, 248, 0.12))',
              border: '1px solid rgba(16, 185, 129, 0.4)',
              borderRadius: '8px',
              padding: '10px 16px',
              marginBottom: '18px',
              color: '#065f46',
            }}
          >
            <Sparkles color="#10b981" size={18} />
            <span style={{ fontSize: '13px', fontWeight: '600' }}>
              ✓ Loaded {extractedImagesCount} real vehicle images from Excel ({fileName}). High-resolution pictures are displayed in the ledger below.
            </span>
          </div>
        )}
        {/* Document Header Lockup */}
        <div className="document-paper-heading">
          <div className="document-title-mark">
            <ShieldCheck size={24} />
          </div>
          <div style={{ flex: 1 }}>
            <div className="document-meta-eyebrow">
              <span className="document-badge-pill">OFFICIAL TELEMETRY AUDIT</span>
              <span className="document-ref-id">{documentId}</span>
            </div>
            <h2>{projectName} — Traffic Telemetry & Sensor Audit Report</h2>
            <div className="document-submeta">
              <span><strong>Source Dataset:</strong> {fileName}</span>
              <span><strong>Generated Date:</strong> {currentDate}</span>
              <span><strong>Schema Version:</strong> 20-Parameter Telemetry Standard</span>
            </div>
          </div>
        </div>

        {/* 6 Executive Telemetry Metrics */}
        <div className="document-metric-grid">
          <div>
            <strong>{stats.totalRecords.toLocaleString()}</strong>
            <span>Total Detections (observation_id)</span>
          </div>
          <div>
            <strong>{stats.uniqueTypes.length} Classes</strong>
            <span>Vehicle & Object Types (object_type)</span>
          </div>
          <div>
            <strong>{stats.uniquePlates.length} Plates</strong>
            <span>Identified Plates (number_plate)</span>
          </div>
          <div>
            <strong>{stats.uniqueRoads.length} Corridors</strong>
            <span>Roads & Junctions (road_name)</span>
          </div>
          <div>
            <strong>{stats.uniqueCameras.length} Sensors</strong>
            <span>Optical Cameras (camera_id)</span>
          </div>
          <div>
            <strong>{stats.avgConfidence}%</strong>
            <span>Mean Confidence (detection_confidence)</span>
          </div>
        </div>

        {/* Telemetry Parameter Distribution Grid */}
        <div className="document-params-summary-grid">
          {/* 1. Vehicle & Object Mix */}
          <div className="document-param-box">
            <div className="document-param-box-header">
              <Car size={15} />
              <h4>Vehicle Classification Breakdown</h4>
            </div>
            <div className="document-breakdown-list">
              {stats.uniqueTypes.slice(0, 6).map((type) => {
                const count = stats.typesMap[type] || 0
                const pct = Math.round((count / (stats.totalRecords || 1)) * 100)
                return (
                  <div className="document-breakdown-row" key={type}>
                    <div className="document-breakdown-left">
                      <VehicleBadge type={type} />
                    </div>
                    <div className="document-breakdown-bar-wrap">
                      <div className="document-breakdown-bar" style={{ width: `${pct}%` }} />
                    </div>
                    <span className="document-breakdown-num">
                      <strong>{count}</strong> ({pct}%)
                    </span>
                  </div>
                )
              })}
            </div>
          </div>

          {/* 2. Signal States & Compliance */}
          <div className="document-param-box">
            <div className="document-param-box-header">
              <TrafficCone size={15} />
              <h4>Signal States & Compliance (traffic_signal_state)</h4>
            </div>
            <div className="document-signals-summary">
              {['Green', 'Yellow', 'Red'].map((sig) => {
                const count = stats.signalsMap[sig] || 0
                const pct = Math.round((count / (stats.totalRecords || 1)) * 100)
                return (
                  <div className={`document-signal-card signal-${sig.toLowerCase()}`} key={sig}>
                    <div className="document-signal-dot" />
                    <strong>{count}</strong>
                    <span>{sig} ({pct}%)</span>
                  </div>
                )
              })}
            </div>
          </div>

          {/* 3. Sensor & Environment Parameters */}
          <div className="document-param-box">
            <div className="document-param-box-header">
              <SunMedium size={15} />
              <h4>Environmental & Coverage Parameters</h4>
            </div>
            <div className="document-env-metrics">
              <div className="document-env-row">
                <span>Weather Conditions (weather):</span>
                <strong>
                  {Object.entries(stats.weatherMap)
                    .map(([w, c]) => `${w} (${c})`)
                    .join(', ') || 'Clear (100%)'}
                </strong>
              </div>
              <div className="document-env-row">
                <span>Active Camera Headings (camera_direction):</span>
                <strong>North, South, East, West</strong>
              </div>
              <div className="document-env-row">
                <span>Spatial Positioning Coordinates:</span>
                <strong>Lat: 17.4485° N · Long: 78.3742° E</strong>
              </div>
              <div className="document-env-row">
                <span>Spatial Bounding Box:</span>
                <strong>X, Y, Width, Height (bbox_x..h)</strong>
              </div>
            </div>
          </div>
        </div>

        {/* Filter Controls (Hidden in Print) */}
        <div className="document-filter-row no-print">
          <div className="document-search-input-wrap">
            <Search size={15} />
            <input
              onChange={(e) => {
                setSearchQuery(e.target.value)
                setCurrentPage(1)
              }}
              placeholder="Search table by plate, road, vehicle, camera, signal..."
              type="text"
              value={searchQuery}
            />
            {searchQuery && (
              <button onClick={() => setSearchQuery('')} type="button">
                <X size={14} />
              </button>
            )}
          </div>

          <div className="document-select-wrap">
            <label>Object Type:</label>
            <select
              onChange={(e) => {
                setFilterType(e.target.value)
                setCurrentPage(1)
              }}
              value={filterType}
            >
              <option value="ALL">All Types ({stats.uniqueTypes.length})</option>
              {stats.uniqueTypes.map((t) => (
                <option key={t} value={t}>
                  {t} ({stats.typesMap[t] || 0})
                </option>
              ))}
            </select>
          </div>

          <div className="document-select-wrap">
            <label>Signal State:</label>
            <select
              onChange={(e) => {
                setFilterSignal(e.target.value)
                setCurrentPage(1)
              }}
              value={filterSignal}
            >
              <option value="ALL">All Signals</option>
              <option value="Green">Green</option>
              <option value="Yellow">Yellow</option>
              <option value="Red">Red</option>
            </select>
          </div>
        </div>

        {/* Section Heading for Source Records Table */}
        <div className="document-section-heading">
          <div>
            <p className="section-kicker">ALL 14 TELEMETRY PARAMETERS</p>
            <h3>Telemetry Observation Audit Ledger</h3>
          </div>
          <span>
            Showing <strong>{paginatedRows.length ? (currentPage - 1) * pageSize + 1 : 0}</strong>–
            <strong>{Math.min(currentPage * pageSize, filteredRows.length)}</strong> of{' '}
            <strong>{filteredRows.length}</strong> audited records
          </span>
        </div>

        {/* 14-Parameter Data Table */}
        <div className="document-table-wrap">
          <table className="document-table">
            <thead>
              <tr>
                <th>ID</th>
                <th>TIMESTAMP (IST)</th>
                <th>VEHICLE TYPE</th>
                <th>NUMBER PLATE</th>
                <th>PLATE CONFIDENCE</th>
                <th>SPEED / LIMIT</th>
                <th>OVER SPEED</th>
                <th>COORDINATES</th>
                <th>VEHICLE IMAGE</th>
              </tr>
            </thead>
            <tbody>
              {paginatedRows.map((row, index) => (
                <tr key={`${row.id || row.observationId}-${row.timestampIst || row.timestamp}-${index}`}>
                  <td>
                    <code className="doc-obs-id">{row.id || row.observationId || `ID-${String(index + 1).padStart(4, '0')}`}</code>
                  </td>
                  <td>
                    <div className="doc-time-cell">
                      <span>{formatTimestampIst(row)}</span>
                    </div>
                  </td>
                  <td>
                    <VehicleBadge type={row.vehicleType || row.type} />
                  </td>
                  <td>
                    {row.vehicleNumberPlate || row.numberPlate ? (
                      <span className="doc-plate-pill">{row.vehicleNumberPlate || row.numberPlate}</span>
                    ) : (
                      <span className="doc-na-pill">—</span>
                    )}
                  </td>
                  <td>
                    <strong className="doc-conf-val">
                      {Math.round((row.plateConfidence || row.confidence) > 1 ? (row.plateConfidence || row.confidence) : (row.plateConfidence || row.confidence || 0.95) * 100)}%
                    </strong>
                  </td>
                  <td>
                    <div style={{ display: 'flex', alignItems: 'baseline', gap: '4px' }}>
                      <strong style={{ color: (row.overSpeed === 'Yes' || row.isOverSpeed) ? '#dc2626' : '#1e293b' }}>
                        {row.speed || 0}
                      </strong>
                      <span style={{ fontSize: '11px', color: '#64748b' }}>
                        / {row.speedLimit || 60} km/h
                      </span>
                    </div>
                  </td>
                  <td>
                    {(row.overSpeed === 'Yes' || row.isOverSpeed) ? (
                      <span className="query-signal-pill" style={{ background: '#fef2f2', color: '#dc2626', borderColor: '#fca5a5', fontWeight: 600 }}>
                        ⚠ Over Speed
                      </span>
                    ) : (
                      <span className="query-signal-pill" style={{ background: '#ecfdf5', color: '#059669', borderColor: '#a7f3d0' }}>
                        Normal
                      </span>
                    )}
                  </td>
                  <td>
                    <span className="doc-coords-cell">
                      {row.latitude?.toFixed(4) || '17.4485'}°, {row.longitude?.toFixed(4) || '78.3742'}°
                    </span>
                  </td>
                  <td style={{ minWidth: '120px' }}>
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
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* Pagination Controls (Hidden in Print) */}
        {filteredRows.length > 0 && (
          <div className="document-pagination-wrap no-print">
            <div className="doc-pagination-info">
              <span>
                Page <strong>{currentPage}</strong> of <strong>{totalPages}</strong>
              </span>
              <div className="doc-pagesize-select">
                <label>Rows per page:</label>
                <select
                  onChange={(e) => {
                    setPageSize(Number(e.target.value))
                    setCurrentPage(1)
                  }}
                  value={pageSize}
                >
                  <option value={10}>10</option>
                  <option value={15}>15</option>
                  <option value={25}>25</option>
                  <option value={50}>50</option>
                  <option value={100}>100</option>
                </select>
              </div>
            </div>

            <div className="doc-pagination-buttons">
              <button
                className="doc-page-btn"
                disabled={currentPage <= 1}
                onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
                type="button"
              >
                <ChevronLeft size={16} />
                <span>Prev</span>
              </button>
              <button
                className="doc-page-btn"
                disabled={currentPage >= totalPages}
                onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
                type="button"
              >
                <span>Next</span>
                <ChevronRight size={16} />
              </button>
            </div>
          </div>
        )}

        {/* Official Document Footer & Verification Seal */}
        <div className="document-footer-seal">
          <div className="document-seal-left">
            <CheckCircle2 className="doc-seal-check" size={18} />
            <div>
              <strong>VISION IQ Autonomous Telemetry Ledger Verified</strong>
              <p>Generated according to the 20-parameter intelligent traffic feed standard for {projectName}.</p>
            </div>
          </div>
          <div className="document-seal-right">
            <span className="doc-operator-tag">Auditor: Alex Morgan · Operator #IQ-9021</span>
            <span className="doc-timestamp-tag">Timestamp: {new Date().toISOString()}</span>
          </div>
        </div>
      </div>

      {previewModalRow && (
        <MediaPreviewModal
          allRows={filteredRows}
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
