import {
  ChevronRight,
  Database,
  LogOut,
  Menu,
  X,
} from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { NavLink, useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { navigation } from '../data/navigation'
import { projects as defaultProjects } from '../data/projects'

const COLLAPSED_W = 64
const EXPANDED_W = 250

export default function Sidebar({
  projectList = defaultProjects,
  selectedProject,
  connectedProject,
  onSelectProject,
  onCreateProject,
}) {
  const navigate = useNavigate()
  const { pathname } = useLocation()
  const { user, logout } = useAuth()

  // pinned = hamburger locked open; hovered = mouse is over sidebar
  const [pinned, setPinned] = useState(false)
  const [hovered, setHovered] = useState(false)

  const isExpanded = pinned || hovered
  const isProjectsRoute = pathname === '/projects'
  const sidebarRef = useRef(null)

  // Sync a CSS custom property on :root so .main-content can react
  useEffect(() => {
    document.documentElement.style.setProperty(
      '--sidebar-current-w',
      isExpanded ? `${EXPANDED_W}px` : `${COLLAPSED_W}px`
    )
  }, [isExpanded])

  return (
    <aside
      className={`sidebar viq-sidebar ${isExpanded ? 'sidebar--expanded' : 'sidebar--collapsed'} ${pinned ? 'sidebar--pinned' : ''}`}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      ref={sidebarRef}
    >
      {/* ── Top bar: logo + hamburger ── */}
      <div className="sidebar-toprow">
        {/* Logo / brand (only visible when expanded) */}
        <div
          className="brand-lockup"
          onClick={() => navigate('/home')}
          style={{ cursor: 'pointer', flex: 1, overflow: 'hidden' }}
        >
          <div className="brand-mark-leaf" aria-hidden="true">
            <svg width="28" height="28" viewBox="0 0 32 32" fill="none" xmlns="http://www.w3.org/2000/svg">
              <path d="M16 29C16 29 6 22 5 11C4 4 11 2 11 2C11 2 16 8 16 18C16 23 16 29 16 29Z" fill="#8cb86d" />
              <path d="M16 29C16 29 26 22 27 11C28 4 21 2 21 2C21 2 16 8 16 18C16 23 16 29 16 29Z" fill="#436b47" />
              <path d="M16 10L16 29" stroke="#151f17" strokeWidth="1.2" strokeLinecap="round" />
            </svg>
          </div>
          <div className="brand-text sidebar-label-fade">
            <p className="brand-name">Vision IQ</p>
            <p className="brand-caption">Smarter Roads. Safer Tomorrow.</p>
          </div>
        </div>

        {/* Hamburger / close pin button */}
        <button
          aria-label={pinned ? 'Unpin sidebar' : 'Pin sidebar open'}
          className="sidebar-hamburger"
          onClick={() => setPinned(p => !p)}
          type="button"
        >
          {pinned ? <X size={17} /> : <Menu size={17} />}
        </button>
      </div>

      {/* ── Instances / Projects ── */}
      <section aria-labelledby="projects-heading" className="projects-section">
        <p className="nav-eyebrow sidebar-label-fade" id="projects-heading">Projects</p>
        <button
          aria-pressed={isProjectsRoute}
          className={`nav-item ${isProjectsRoute ? 'active' : ''}`}
          onClick={() => {
            onSelectProject?.(defaultProjects[0])
            navigate('/projects')
          }}
          type="button"
        >
          <Database className="nav-icon" size={19} strokeWidth={1.8} />
          <span className="nav-label sidebar-label-fade">Instances</span>
          {connectedProject && (
            <span
              className="nav-connected-dot sidebar-label-fade"
              title="Connected"
            />
          )}
          {/* Tooltip shown only when collapsed */}
          <span className="sidebar-tooltip">Instances</span>
        </button>
      </section>

      {/* ── Main Navigation ── */}
      <nav aria-label="Primary navigation" className="main-nav">
        <p className="nav-eyebrow sidebar-label-fade">Workspace</p>
        {navigation.map(({ label, path, icon: Icon, exact }) => (
          <NavLink
            className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}
            end={exact}
            key={path}
            to={path}
          >
            <Icon className="nav-icon" size={19} strokeWidth={1.75} />
            <span className="nav-label sidebar-label-fade">{label}</span>
            {/* Tooltip shown only when collapsed */}
            <span className="sidebar-tooltip">{label}</span>
          </NavLink>
        ))}
      </nav>

      {/* ── Bottom city art + tagline ── */}
      <div className="sidebar-bottom-block">
        <div className="sidebar-city-graphic sidebar-label-fade" aria-hidden="true">
          <svg viewBox="0 0 230 110" fill="none" xmlns="http://www.w3.org/2000/svg" className="sidebar-graphic-svg">
            <defs>
              <linearGradient id="skyGrad" x1="0%" y1="0%" x2="0%" y2="100%">
                <stop offset="0%" stopColor="#151f17" stopOpacity="0" />
                <stop offset="60%" stopColor="#19281e" stopOpacity="0.85" />
                <stop offset="100%" stopColor="#223326" stopOpacity="1" />
              </linearGradient>
              <linearGradient id="roadGlow1" x1="0%" y1="100%" x2="100%" y2="0%">
                <stop offset="0%" stopColor="#e5a855" stopOpacity="0.95" />
                <stop offset="55%" stopColor="#c79140" stopOpacity="0.7" />
                <stop offset="100%" stopColor="#8fad6b" stopOpacity="0.15" />
              </linearGradient>
              <linearGradient id="roadGlow2" x1="0%" y1="100%" x2="100%" y2="0%">
                <stop offset="0%" stopColor="#f3c675" stopOpacity="0.85" />
                <stop offset="70%" stopColor="#a5c478" stopOpacity="0.5" />
                <stop offset="100%" stopColor="#2e4d34" stopOpacity="0" />
              </linearGradient>
            </defs>
            <rect x="18" y="52" width="13" height="58" fill="#1b2a1e" rx="1" />
            <rect x="34" y="38" width="16" height="72" fill="#1d2e21" rx="1" />
            <rect x="53" y="56" width="11" height="54" fill="#19271c" rx="1" />
            <rect x="68" y="28" width="15" height="82" fill="#203325" rx="1" />
            <polygon points="75.5,16 68,28 83,28" fill="#203325" />
            <rect x="87" y="44" width="18" height="66" fill="#1c2c20" rx="1" />
            <rect x="109" y="34" width="14" height="76" fill="#213526" rx="1" />
            <rect x="127" y="48" width="16" height="62" fill="#1e3023" rx="1" />
            <rect x="147" y="24" width="20" height="86" fill="#24392a" rx="1" />
            <polygon points="157,12 147,24 167,24" fill="#24392a" />
            <rect x="171" y="42" width="15" height="68" fill="#1e3023" rx="1" />
            <rect x="190" y="54" width="16" height="56" fill="#19271c" rx="1" />
            <circle cx="75.5" cy="16" r="1.5" fill="#f5d77f" />
            <circle cx="157" cy="12" r="1.5" fill="#f5d77f" />
            <rect x="38" y="46" width="2" height="3" fill="#dfbe6f" opacity="0.65" />
            <rect x="72" y="38" width="2" height="3" fill="#dfbe6f" opacity="0.75" />
            <rect x="76" y="50" width="2" height="3" fill="#dfbe6f" opacity="0.75" />
            <rect x="113" y="44" width="2" height="3" fill="#dfbe6f" opacity="0.75" />
            <rect x="151" y="34" width="2" height="3" fill="#dfbe6f" opacity="0.8" />
            <rect x="157" y="46" width="2" height="3" fill="#dfbe6f" opacity="0.8" />
            <rect x="175" y="52" width="2" height="3" fill="#dfbe6f" opacity="0.6" />
            <path d="M-10 108 C 35 105, 90 95, 120 76 C 150 58, 175 60, 240 58" stroke="url(#roadGlow1)" strokeWidth="3" strokeLinecap="round" />
            <path d="M-10 114 C 45 112, 100 102, 135 82 C 165 65, 190 64, 240 62" stroke="url(#roadGlow2)" strokeWidth="2.2" strokeLinecap="round" />
            <path d="M-10 102 C 25 100, 75 90, 110 72 C 140 55, 170 54, 240 52" stroke="rgba(230, 167, 86, 0.35)" strokeWidth="1" strokeLinecap="round" />
          </svg>
        </div>

        <div className="sidebar-quote-content sidebar-label-fade">
          <p className="sidebar-quote-text">"Better Insights<br />Brighter Cities"</p>
          <div className="sidebar-quote-divider" />
          <p className="sidebar-quote-brand">VISION IQ</p>
          <p className="sidebar-quote-sub">DRIVEN BY DATA<br />FOR A SAFER TOMORROW.</p>
        </div>
      </div>
    </aside>
  )
}
