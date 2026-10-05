import {
  Activity,
  ArrowRight,
  ArrowUp,
  BarChart3,
  Bike,
  Building2,
  Bus,
  Calendar,
  Camera,
  Car,
  ChevronDown,
  Clock,
  Eye,
  Flame,
  LayoutGrid,
  MapPin,
  PieChart as PieIcon,
  RefreshCw,
  Sparkles,
  Timer,
  TrendingUp,
  Truck,
  User,
} from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { navigation } from '../data/navigation'
import MediaPreviewModal from './MediaPreviewModal'
import { listVideos } from '../services/nh5Api'

export default function PlaceholderPage({
  cameraCount = 0,
  rows = [],
  fileName = '',
  latestBatchInfo = null,
  dbStats = null,
  onFetchRandomBatch = null,
  onToggleStreamPause = null,
  streamPaused = false,
  streamNotifications = [],
}) {
  const { pathname } = useLocation()
  const navigate = useNavigate()
  const { user } = useAuth()
  const [timeFilter, setTimeFilter] = useState('Today')
  const [trendRange, setTrendRange] = useState('Last 24 Hours')
  const [currentTime, setCurrentTime] = useState(() => new Date())
  const [previewModalRow, setPreviewModalRow] = useState(null)

  useEffect(() => {
    const timer = setInterval(() => setCurrentTime(new Date()), 1000)
    return () => clearInterval(timer)
  }, [])

  const safeRows = Array.isArray(rows) ? rows : []
  const isHomePage = pathname === '/home' || pathname === '/'

  // ---- real numbers from the processed videos (rows = every vehicle record in the database)
  const typeCounts = useMemo(() => {
    const counts = { Car: 0, Bike: 0, Bicycle: 0, Auto: 0, Bus: 0, Truck: 0, Pedestrian: 0, Other: 0 }
    safeRows.forEach((r) => {
      const t = String(r.vehicleType || r.type || 'Other')
      if (t in counts) counts[t] += 1
      else counts.Other += 1
    })
    return counts
  }, [safeRows])
  const vehicleTotal = safeRows.length - typeCounts.Pedestrian
  const twoWheelers = typeCounts.Bike + typeCounts.Bicycle
  const heavyVehicles = typeCounts.Truck + typeCounts.Bus
  const formattedTotal = Number(vehicleTotal).toLocaleString()

  const chartTypes = [
    { key: 'Cars', count: typeCounts.Car, color: 'green', hex: '#3d9953', Icon: Car },
    { key: 'Bikes', count: twoWheelers, color: 'amber', hex: '#d89f4b', Icon: Bike },
    { key: 'Trucks', count: typeCounts.Truck, color: 'terracotta', hex: '#cb5e48', Icon: Truck },
    { key: 'Buses', count: typeCounts.Bus, color: 'blue', hex: '#4f82c4', Icon: Bus },
    { key: 'Auto', count: typeCounts.Auto, color: 'purple', hex: '#8d6ab0', Icon: Car },
    { key: 'Other', count: typeCounts.Other, color: 'slate', hex: '#83929b', Icon: LayoutGrid },
  ]
  const chartMax = Math.max(1, ...chartTypes.map((t) => t.count))
  const axisLabels = [1, 0.75, 0.5, 0.25, 0].map((f) => {
    const v = Math.round(chartMax * f)
    return v >= 1000 ? `${(v / 1000).toFixed(1)}K` : String(v)
  })
  const donutTotal = chartTypes.reduce((n, t) => n + t.count, 0)
  const CIRC = 2 * Math.PI * 54
  let donutOffset = 0
  const donutSlices = chartTypes.filter((t) => t.count > 0).map((t) => {
    const len = (t.count / donutTotal) * CIRC
    const slice = { ...t, len, offset: donutOffset, pct: Math.round((t.count / donutTotal) * 100) }
    donutOffset += len
    return slice
  })

  // detections per hour of day (from the vehicles' timestamps)
  const hourly = useMemo(() => {
    const buckets = Array(24).fill(0)
    safeRows.forEach((r) => {
      const m = String(r.timestampIst || r.timestamp || '').match(/[ T](\d{2}):/)
      if (m) buckets[Number(m[1])] += 1
    })
    return buckets
  }, [safeRows])
  const hourMax = Math.max(1, ...hourly)
  const peakHour = hourly.indexOf(Math.max(...hourly))
  const trendPoints = hourly.map((v, h) => [(h / 23) * 500, 150 - (v / hourMax) * 130])
  const trendLine = trendPoints.map(([x, y], i) => `${i ? 'L' : 'M'}${x.toFixed(1)} ${y.toFixed(1)}`).join(' ')
  const hourAxis = [1, 0.75, 0.5, 0.25, 0].map((f) => String(Math.round(hourMax * f)))

  // latest detections first
  const recentRows = useMemo(
    () => [...safeRows].sort((a, b) => String(b.timestampIst || b.timestamp || '').localeCompare(String(a.timestampIst || a.timestamp || ''))).slice(0, 4),
    [safeRows],
  )

  // most recent processed video for the feed card
  const [latestVideo, setLatestVideo] = useState(null)
  useEffect(() => {
    if (!isHomePage) return
    listVideos().then((vids) => setLatestVideo(vids.find((v) => v.status === 'done') || vids[0] || null)).catch(() => setLatestVideo(null))
  }, [isHomePage, safeRows.length])

  // Format live clock e.g. "10:24:18 AM"
  const formattedClock = currentTime.toLocaleTimeString('en-US', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: true,
  })

  // Fallback for non-home pages
  if (!isHomePage) {
    const page = navigation.find(({ path }) => path === pathname) ?? navigation[0]
    return (
      <div className="workspace-page">
        <div className="workspace-hero">
          <div>
            <p className="section-kicker">OPERATIONAL INTELLIGENCE</p>
            <h1>{page.label}</h1>
            <p className="intro-copy">Explore and manage your {page.label.toLowerCase()} configuration and assets.</p>
          </div>
          <div className="workspace-hero-icon"><Activity size={24} /></div>
        </div>
      </div>
    )
  }

  return (
    <div className="viq-dashboard-container">
      {/* 1. Hero Panoramic Intelligence Banner */}
      <div className="viq-hero-banner">
        {/* City highway glowing backdrop vector */}
        <div className="viq-hero-backdrop" aria-hidden="true">
          <svg viewBox="0 0 1100 240" fill="none" xmlns="http://www.w3.org/2000/svg" preserveAspectRatio="none" className="viq-hero-svg">
            <defs>
              <linearGradient id="heroSky" x1="0%" y1="0%" x2="100%" y2="100%">
                <stop offset="0%" stopColor="#111c14" />
                <stop offset="50%" stopColor="#17261a" />
                <stop offset="100%" stopColor="#223626" />
              </linearGradient>
              <linearGradient id="heroGold1" x1="0%" y1="100%" x2="100%" y2="0%">
                <stop offset="0%" stopColor="#e3a34a" stopOpacity="0.9" />
                <stop offset="60%" stopColor="#d18e38" stopOpacity="0.7" />
                <stop offset="100%" stopColor="#769f5e" stopOpacity="0.1" />
              </linearGradient>
              <linearGradient id="heroGold2" x1="0%" y1="100%" x2="100%" y2="0%">
                <stop offset="0%" stopColor="#f7cc74" stopOpacity="0.95" />
                <stop offset="65%" stopColor="#a3c473" stopOpacity="0.5" />
                <stop offset="100%" stopColor="#304f36" stopOpacity="0" />
              </linearGradient>
            </defs>
            <rect width="1100" height="240" fill="url(#heroSky)" />

            {/* Distant skyline buildings */}
            <rect x="520" y="80" width="30" height="160" fill="#1b2a1e" rx="2" />
            <rect x="560" y="60" width="40" height="180" fill="#1f3223" rx="2" />
            <rect x="610" y="90" width="28" height="150" fill="#18271b" rx="2" />
            <rect x="650" y="45" width="42" height="195" fill="#223827" rx="2" />
            <polygon points="671,25 650,45 692,45" fill="#223827" />
            <rect x="702" y="70" width="38" height="170" fill="#1d2f21" rx="2" />
            <rect x="750" y="55" width="46" height="185" fill="#213626" rx="2" />
            <rect x="806" y="85" width="32" height="155" fill="#19281c" rx="2" />
            <rect x="848" y="38" width="50" height="202" fill="#253c2b" rx="2" />
            <polygon points="873,15 848,38 898,38" fill="#253c2b" />
            <rect x="910" y="65" width="42" height="175" fill="#1f3223" rx="2" />
            <rect x="962" y="92" width="48" height="148" fill="#1a291d" rx="2" />

            {/* Glowing windows on skyline */}
            <circle cx="671" cy="25" r="2.5" fill="#f8de87" />
            <circle cx="873" cy="15" r="2.5" fill="#f8de87" />
            <rect x="570" y="72" width="4" height="6" fill="#f1d479" opacity="0.7" />
            <rect x="660" y="55" width="5" height="7" fill="#f1d479" opacity="0.8" />
            <rect x="674" y="75" width="5" height="7" fill="#f1d479" opacity="0.8" />
            <rect x="762" y="68" width="5" height="7" fill="#f1d479" opacity="0.75" />
            <rect x="860" y="50" width="6" height="8" fill="#f1d479" opacity="0.85" />
            <rect x="874" y="70" width="6" height="8" fill="#f1d479" opacity="0.85" />
            <rect x="920" y="80" width="5" height="7" fill="#f1d479" opacity="0.7" />

            {/* Highway sweep curves */}
            <path d="M420 240 C 560 230, 720 210, 840 170 C 960 130, 1020 135, 1120 130" stroke="url(#heroGold1)" strokeWidth="6" strokeLinecap="round" />
            <path d="M420 240 C 580 236, 750 218, 880 180 C 980 148, 1040 144, 1120 140" stroke="url(#heroGold2)" strokeWidth="4.5" strokeLinecap="round" />
            <path d="M400 235 C 540 226, 700 205, 820 162 C 940 120, 1000 120, 1120 118" stroke="rgba(247, 204, 116, 0.45)" strokeWidth="2.5" strokeLinecap="round" />
          </svg>
        </div>

        {/* Banner Content */}
        <div className="viq-hero-content">
          <div className="viq-hero-left">
            <span className="viq-hero-kicker">REAL-TIME INTELLIGENCE</span>
            <h1 className="viq-hero-title">Vision IQ</h1>
            <p className="viq-hero-desc">Turning Traffic Data into Smarter Decisions.</p>

            <div className="viq-hero-pills">
              <div className="viq-hero-pill">
                <Timer size={14} className="viq-pill-icon" />
                <div className="viq-pill-text">
                  <span className="viq-pill-bold">Monitor</span>
                  <span className="viq-pill-sub">in Real-Time</span>
                </div>
              </div>

              <div className="viq-hero-pill">
                <Sparkles size={14} className="viq-pill-icon" />
                <div className="viq-pill-text">
                  <span className="viq-pill-bold">Analyse</span>
                  <span className="viq-pill-sub">with AI</span>
                </div>
              </div>

              <div className="viq-hero-pill">
                <Building2 size={14} className="viq-pill-icon" />
                <div className="viq-pill-text">
                  <span className="viq-pill-bold">Build</span>
                  <span className="viq-pill-sub">Safer Cities</span>
                </div>
              </div>
            </div>
          </div>

          <div className="viq-hero-right">
            <p className="viq-hero-quote">“Smarter Roads<br />Happier Tomorrows”</p>
          </div>
        </div>
      </div>

      {/* 2. Top 4 Stat KPI Cards (real counts from processed videos) */}
      <div className="viq-stat-cards-grid">
        {[
          { label: 'Total Vehicles', value: vehicleTotal, icon: Car, tone: 'mint', sub: `${dbStats?.plates || 0} unique plates` },
          { label: 'Two Wheelers', value: twoWheelers, icon: Bike, tone: 'amber', sub: 'bikes and bicycles' },
          { label: 'Heavy Vehicles', value: heavyVehicles, icon: Truck, tone: 'peach', sub: 'trucks and buses' },
          { label: 'Pedestrians', value: typeCounts.Pedestrian, icon: User, tone: 'sky', sub: 'people tracked' },
        ].map(({ label, value, icon: Icon, tone, sub }) => (
          <div className="viq-stat-card" key={label}>
            <div className={`viq-stat-icon-wrap ${tone}`}>
              <Icon size={22} strokeWidth={2} />
            </div>
            <div className="viq-stat-info">
              <span className="viq-stat-label">{label}</span>
              <strong className="viq-stat-value">{Number(value).toLocaleString()}</strong>
              <span className="viq-stat-trend viq-stat-sub">{sub}</span>
            </div>
          </div>
        ))}
      </div>

      {/* 3. Middle Row: Vehicle Count by Type & latest processed video */}
      <div className="viq-middle-grid">
        <div className="viq-card viq-bar-chart-card">
          <div className="viq-card-header">
            <div className="viq-card-title-group">
              <BarChart3 className="viq-card-icon" size={19} />
              <h2>Vehicle Count by Type</h2>
            </div>
            <div className="viq-select-dropdown">
              <Calendar size={13} />
              <span>All processed videos</span>
            </div>
          </div>
          <div className="viq-bar-chart-canvas">
            <div className="viq-chart-y-axis">
              {axisLabels.map((l, i) => <span key={i}>{l}</span>)}
            </div>
            <div className="viq-chart-bars-wrap">
              {[0, 25, 50, 75, 100].map((top) => <div className="viq-chart-gridline" key={top} style={{ top: `${top}%` }} />)}
              <div className="viq-chart-bars">
                {chartTypes.map(({ key, count, color, Icon }) => (
                  <div className="viq-bar-col" key={key}>
                    <span className="viq-bar-value">{count.toLocaleString()}</span>
                    <div className={`viq-bar-fill ${color}`} style={{ height: `${(count / chartMax) * 100}%` }} />
                    <div className="viq-bar-label">
                      <Icon size={15} />
                      <span>{key}</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>

        <div className="viq-card viq-live-feed-card">
          <div className="viq-card-header">
            <div className="viq-card-title-group">
              <Camera className="viq-card-icon" size={19} />
              <h2>Latest Processed Video</h2>
            </div>
            <Link className="viq-camera-id-pill" to="/live-camera">
              <span className="live-camera-dot" />
              <span>Open Live Camera</span>
            </Link>
          </div>
          {latestVideo ? (
            <Link className="viq-live-feed-viewport" to={`/video-library/${latestVideo.jobId}`}>
              {latestVideo.thumbnail ? (
                <img alt={latestVideo.originalFilename} className="viq-feed-image" src={latestVideo.thumbnail} />
              ) : (
                <div className="viq-feed-empty">Processing…</div>
              )}
              <div className="viq-feed-live-badge">
                <span className="live-red-dot" />
                <span>{latestVideo.status === 'done' ? 'LATEST' : latestVideo.status.toUpperCase()}</span>
              </div>
            </Link>
          ) : (
            <div className="viq-live-feed-viewport viq-feed-empty-wrap">
              <div className="viq-feed-empty">
                <span>No video processed yet.</span>
                <Link to="/video-upload">Upload a video →</Link>
              </div>
            </div>
          )}
          <div className="viq-feed-footer">
            <div className="viq-feed-location">
              <MapPin size={14} className="feed-location-pin" />
              <span>{latestVideo ? `${latestVideo.originalFilename} · ${latestVideo.numVehicles || 0} vehicles · ${(latestVideo.plates || []).length} plates` : 'NH5 Highway'}</span>
            </div>
            <div className="viq-feed-time">
              <Clock size={14} />
              <span>{formattedClock}</span>
            </div>
          </div>
        </div>
      </div>

      {/* 4. Bottom Row: type distribution, detections per hour, recent detections */}
      <div className="viq-bottom-grid">
        <div className="viq-card viq-donut-card">
          <div className="viq-card-header">
            <div className="viq-card-title-group">
              <BarChart3 className="viq-card-icon" size={19} />
              <h2>Vehicle Type Distribution</h2>
            </div>
          </div>
          <div className="viq-donut-content">
            <div className="viq-donut-graphic">
              <svg viewBox="0 0 160 160" className="viq-donut-svg">
                {donutSlices.length ? donutSlices.map((sl) => (
                  <circle cx="80" cy="80" fill="transparent" key={sl.key} r="54" stroke={sl.hex} strokeDasharray={`${sl.len} ${CIRC - sl.len}`} strokeDashoffset={-sl.offset} strokeWidth="22" />
                )) : <circle cx="80" cy="80" fill="transparent" r="54" stroke="#ece7dd" strokeWidth="22" />}
              </svg>
              <div className="viq-donut-center">
                <strong className="viq-donut-total">{formattedTotal}</strong>
                <span className="viq-donut-sub">Total</span>
              </div>
            </div>
            <div className="viq-donut-legend">
              {chartTypes.map((t) => (
                <div className="viq-legend-row" key={t.key}>
                  <span className="viq-legend-dot" style={{ background: t.hex }} />
                  <span className="viq-legend-name">{t.key}</span>
                  <strong className="viq-legend-val">{donutTotal ? Math.round((t.count / donutTotal) * 100) : 0}%</strong>
                </div>
              ))}
            </div>
          </div>
        </div>

        <div className="viq-card viq-trend-card">
          <div className="viq-card-header">
            <div className="viq-card-title-group">
              <TrendingUp className="viq-card-icon" size={19} />
              <h2>Detections by Hour</h2>
            </div>
            <div className="viq-select-dropdown">
              <span>Time of day</span>
            </div>
          </div>
          <div className="viq-trend-canvas-wrap">
            <div className="viq-chart-y-axis">
              {hourAxis.map((l, i) => <span key={i}>{l}</span>)}
            </div>
            <div className="viq-trend-chart-area">
              {[0, 25, 50, 75, 100].map((top) => <div className="viq-chart-gridline" key={top} style={{ top: `${top}%` }} />)}
              <svg viewBox="0 0 500 160" preserveAspectRatio="none" className="viq-trend-svg">
                <defs>
                  <linearGradient id="trendGradient" x1="0%" y1="0%" x2="0%" y2="100%">
                    <stop offset="0%" stopColor="#3d9953" stopOpacity="0.32" />
                    <stop offset="100%" stopColor="#3d9953" stopOpacity="0.04" />
                  </linearGradient>
                </defs>
                <path d={`${trendLine} L 500 160 L 0 160 Z`} fill="url(#trendGradient)" />
                <path d={trendLine} fill="none" stroke="#3d9953" strokeWidth="2.5" />
              </svg>
              {safeRows.length > 0 && (
                <div className="viq-trend-marker" style={{ left: `${(peakHour / 23) * 100}%`, top: `${(1 - hourly[peakHour] / hourMax) * 81 + 6}%` }}>
                  <div className="viq-marker-pin" />
                  <div className="viq-marker-line" />
                  <div className="viq-marker-tooltip">
                    <strong>{hourly[peakHour].toLocaleString()} detections</strong>
                    <span>{String(peakHour).padStart(2, '0')}:00</span>
                  </div>
                </div>
              )}
            </div>
          </div>
          <div className="viq-trend-x-axis">
            {['00:00', '04:00', '08:00', '12:00', '16:00', '20:00', '23:00'].map((t) => <span key={t}>{t}</span>)}
          </div>
        </div>

        <div className="viq-card viq-detections-card">
          <div className="viq-card-header">
            <div className="viq-card-title-group">
              <Camera className="viq-card-icon" size={19} />
              <h2>Recent Detections</h2>
            </div>
            <button className="viq-view-all-link" onClick={() => navigate('/query')} type="button">
              <span>View All</span>
              <ArrowRight size={13} />
            </button>
          </div>
          <div className="viq-detections-list">
            {recentRows.length === 0 && (
              <p className="viq-detections-empty">No detections yet. <Link to="/video-upload">Upload a video</Link> or start the <Link to="/live-camera">live camera</Link>.</p>
            )}
            {recentRows.map((row) => {
              const plate = row.vehicleNumberPlate || row.numberPlate
              const thumb = row.vehicleImagePath || row.vehicleImage
              return (
                <div
                  className="viq-detection-item"
                  key={row._streamId || row.csvRecordId || row.id}
                  onClick={() => setPreviewModalRow(row)}
                  title="Click to inspect detection evidence"
                >
                  {thumb ? <img alt={plate || 'vehicle'} className="viq-detection-thumb" src={thumb} /> : <span className="viq-detection-thumb" />}
                  <div className="viq-detection-details">
                    <strong className="viq-detection-plate">{plate && plate !== 'Not read' ? plate : 'Plate not read'}</strong>
                    <span className="viq-detection-sub">
                      {row.vehicleType || row.type} • {row.camera}
                    </span>
                  </div>
                  <div className="viq-detection-time">
                    <span>{String(row.timestampIst || row.timestamp || '').slice(11, 16)}</span>
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      </div>

      {/* Media Preview Modal for Inspecting Any Incoming Vehicle */}
      {previewModalRow && (
        <MediaPreviewModal
          allRows={safeRows}
          isOpen={Boolean(previewModalRow)}
          onClose={() => setPreviewModalRow(null)}
          onSelectRow={setPreviewModalRow}
          row={previewModalRow}
        />
      )}
    </div>
  )
}
