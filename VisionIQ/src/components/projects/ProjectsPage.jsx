import { useState } from 'react'
import {
  Activity,
  Check,
  ChevronDown,
  ChevronRight,
  Copy,
  Database,
  FileSpreadsheet,
  FolderOpen,
  MoreHorizontal,
  Play,
  Plus,
  Power,
  Search,
  Sparkles,
  Trash2,
  Upload,
} from 'lucide-react'
import { Link } from 'react-router-dom'

export default function ProjectsPage({
  projectList = [],
  selectedProject,
  connectedProject,
  onSelectProject,
  onProjectConnect,
  onProjectDisconnect,
  onDeleteProject,
  onCreateProject,
  onImport,
  onLoadSampleData,
  fileName,
  hasImportedFile,
  rows = [],
  importError,
  setImportError,
  dbStats,
}) {
  const [searchQuery, setSearchQuery] = useState('')
  const [sortBy, setSortBy] = useState('created')
  const [showSortMenu, setShowSortMenu] = useState(false)
  const [copiedKey, setCopiedKey] = useState(null)
  const [expandedProjects, setExpandedProjects] = useState({})
  const [showCreateModal, setShowCreateModal] = useState(false)
  const [newProjectName, setNewProjectName] = useState('')
  const [openMenuKey, setOpenMenuKey] = useState(null)

  const activeProject = selectedProject || projectList[0]

  function toggleExpand(key) {
    setExpandedProjects((prev) => ({
      ...prev,
      [key]: prev[key] === undefined ? false : !prev[key],
    }))
  }

  function handleCopy(text, key) {
    if (!text) return
    navigator.clipboard?.writeText?.(text)
    setCopiedKey(key)
    setTimeout(() => setCopiedKey(null), 1800)
  }

  function handleCreate(e) {
    e.preventDefault()
    const trimmed = newProjectName.trim()
    if (!trimmed) return
    onCreateProject?.(trimmed)
    setNewProjectName('')
    setShowCreateModal(false)
  }

  const filteredProjects = projectList
    .filter((p) =>
      (p.name || '').toLowerCase().includes(searchQuery.toLowerCase()),
    )
    .sort((a, b) => {
      if (sortBy === 'name') return (a.name || '').localeCompare(b.name || '')
      if (sortBy === 'status') {
        const aConn = connectedProject?.key === a.key ? 1 : 0
        const bConn = connectedProject?.key === b.key ? 1 : 0
        return bConn - aConn
      }
      return 0
    })

  const uniqueCameras = new Set(rows.map((r) => r?.camera).filter(Boolean)).size
  const uniqueLocations = new Set(rows.map((r) => r?.location).filter(Boolean)).size

  return (
    <div className="proj-page-container">
      {/* TOP HEADER CONTROLS */}
      <div className="proj-topbar">
        <div className="proj-search-box">
          <Search size={16} className="proj-search-icon" />
          <input
            type="text"
            placeholder="Search projects..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />
        </div>

        <div className="proj-topbar-actions">
          <div className="proj-sort-wrap">
            <button
              className="proj-btn-filter"
              onClick={() => setShowSortMenu(!showSortMenu)}
              type="button"
            >
              <span>{sortBy === 'name' ? 'Name' : sortBy === 'status' ? 'Status' : 'Created'}</span>
              <ChevronDown size={14} />
            </button>
            {showSortMenu && (
              <div
                className="proj-dropdown-menu"
                onMouseLeave={() => setShowSortMenu(false)}
              >
                <button
                  className="proj-dropdown-item"
                  onClick={() => {
                    setSortBy('created')
                    setShowSortMenu(false)
                  }}
                  type="button"
                >
                  Sort by Created
                </button>
                <button
                  className="proj-dropdown-item"
                  onClick={() => {
                    setSortBy('name')
                    setShowSortMenu(false)
                  }}
                  type="button"
                >
                  Sort by Name
                </button>
                <button
                  className="proj-dropdown-item"
                  onClick={() => {
                    setSortBy('status')
                    setShowSortMenu(false)
                  }}
                  type="button"
                >
                  Sort by Connected
                </button>
              </div>
            )}
          </div>

          <button
            className="proj-btn-create"
            onClick={() => setShowCreateModal(true)}
            type="button"
          >
            <Plus size={15} />
            <span>New Project</span>
          </button>
        </div>
      </div>

      {importError && (
        <div className="proj-error-banner" role="alert" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '12px' }}>
          <span>{importError}</span>
          {setImportError && (
            <button
              type="button"
              onClick={() => setImportError('')}
              style={{
                background: 'transparent',
                border: 'none',
                color: 'inherit',
                cursor: 'pointer',
                fontWeight: 'bold',
                padding: '2px 8px',
                fontSize: '14px',
                opacity: 0.8,
              }}
              title="Dismiss error"
            >
              ✕
            </button>
          )}
        </div>
      )}

      {/* CREATE MODAL */}
      {showCreateModal && (
        <div className="proj-modal-overlay" onClick={() => setShowCreateModal(false)}>
          <div className="proj-modal-card" onClick={(e) => e.stopPropagation()}>
            <h3>Create New Intelligence Project</h3>
            <p>Define a new project workspace for city surveillance and traffic analytics.</p>
            <form onSubmit={handleCreate}>
              <input
                autoFocus
                placeholder="e.g. Cyberabad Expressway Surveillance"
                value={newProjectName}
                onChange={(e) => setNewProjectName(e.target.value)}
              />
              <div className="proj-modal-actions">
                <button
                  type="button"
                  className="proj-btn-secondary"
                  onClick={() => setShowCreateModal(false)}
                >
                  Cancel
                </button>
                <button type="submit" className="proj-btn-primary">
                  Create Project
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* PAGE TITLE */}
      <div className="proj-section-header">
        <h1>Projects</h1>
        <p>Manage surveillance workspaces, connected camera feeds, and analytics pipelines.</p>
      </div>

      {/* PROJECT CARDS LIST */}
      <div className="proj-cards-list">
        {filteredProjects.map((project) => {
          const isSelected = activeProject && (activeProject.key === project.key || activeProject.name === project.name)
          const isConnected = connectedProject && (connectedProject.key === project.key || connectedProject.name === project.name)

          const projectId = project.key || `proj-${project.name?.toLowerCase().replace(/[^a-z0-9]+/g, '-') || 'workspace'}`

          return (
            <div
              key={project.key || project.name}
              className={`proj-card ${isSelected ? 'selected' : ''}`}
              onClick={() => onSelectProject?.(project)}
            >
              {/* CARD TOP ROW: TITLE & ACTION BUTTONS */}
              <div className="proj-card-header">
                <div className="proj-card-title-group">
                  <h2>{project.name}</h2>
                </div>

                <div className="proj-card-actions" onClick={(e) => e.stopPropagation()}>
                  {/* PLAY / POWER CIRCULAR BUTTON */}
                  <button
                    className={`proj-circle-btn ${isConnected ? 'active' : ''}`}
                    onClick={() => {
                      if (isConnected) {
                        onProjectDisconnect?.()
                      } else {
                        onProjectConnect?.(project)
                      }
                    }}
                    title={isConnected ? 'Disconnect / Stop Project' : 'Connect / Start Project'}
                    type="button"
                  >
                    {isConnected ? <Power size={14} /> : <Play size={13} style={{ marginLeft: '2px' }} />}
                  </button>

                  {/* CONNECT / DISCONNECT PRIMARY BUTTON */}
                  {isConnected ? (
                    <button
                      className="proj-action-btn connected"
                      onClick={onProjectDisconnect}
                      type="button"
                    >
                      <span>Disconnect</span>
                      <ChevronDown size={14} />
                    </button>
                  ) : (
                    <button
                      className="proj-action-btn connect"
                      onClick={() => onProjectConnect?.(project)}
                      type="button"
                    >
                      <span>Connect</span>
                      <ChevronDown size={14} />
                    </button>
                  )}

                  {/* MORE OPTIONS BUTTON */}
                  <div className="proj-more-dropdown-wrap">
                    <button
                      className="proj-more-btn"
                      onClick={() => setOpenMenuKey(openMenuKey === project.key ? null : project.key)}
                      type="button"
                    >
                      <MoreHorizontal size={16} />
                    </button>

                    {openMenuKey === project.key && (
                      <div className="proj-dropdown-menu" onMouseLeave={() => setOpenMenuKey(null)}>
                        {project.created && (
                          <button
                            className="proj-dropdown-item delete"
                            onClick={() => {
                              setOpenMenuKey(null)
                              onDeleteProject?.(project)
                            }}
                            type="button"
                          >
                            <Trash2 size={13} />
                            <span>Delete Project</span>
                          </button>
                        )}
                        <button
                          className="proj-dropdown-item"
                          onClick={() => {
                            setOpenMenuKey(null)
                            handleCopy(projectId, `id-${projectId}`)
                          }}
                          type="button"
                        >
                          <Copy size={13} />
                          <span>Copy Project ID</span>
                        </button>
                      </div>
                    )}
                  </div>
                </div>
              </div>

              {/* STATUS ROW */}
              <div className="proj-status-row">
                {isConnected ? (
                  <span className="proj-status-badge connected">
                    <span className="proj-status-dot">●</span> CONNECTED
                  </span>
                ) : (
                  <span className="proj-status-badge stopped">
                    <span className="proj-status-square">■</span> STOPPED
                  </span>
                )}
              </div>

              {/* METADATA ROW: PROJECT ID | PLATFORM VERSION */}
              <div className="proj-meta-row">
                <div className="proj-meta-item">
                  <span className="proj-meta-label">Project ID:</span>
                  <span className="proj-meta-val">{projectId}</span>
                  <button
                    className="proj-copy-icon"
                    onClick={(e) => {
                      e.stopPropagation()
                      handleCopy(projectId, `id-${projectId}`)
                    }}
                    title="Copy Project ID"
                    type="button"
                  >
                    {copiedKey === `id-${projectId}` ? (
                      <Check size={13} className="text-green" />
                    ) : (
                      <Copy size={13} />
                    )}
                  </button>
                </div>

                <span className="proj-meta-divider">|</span>

                <div className="proj-meta-item">
                  <span className="proj-meta-label">Engine:</span>
                  <span className="proj-meta-val">Platform A v1.0</span>
                </div>
              </div>

              {/* ONLY IF CONNECTED: SHOW IMPORT FILES / DATASET SECTION */}
              {isConnected && (
                <div className="proj-connected-section" onClick={(e) => e.stopPropagation()}>
                  {hasImportedFile ? (
                    <div className="proj-feed-detail-row">
                      <div className="proj-feed-icon">
                        <FileSpreadsheet size={18} />
                      </div>
                      <div className="proj-feed-meta">
                        <strong>{fileName}</strong>
                        <span>
                          {dbStats && dbStats.totalPool > 0
                            ? `${dbStats.totalPool.toLocaleString()} vehicle detections in database (${rows.length.toLocaleString()} live in session) · ${uniqueCameras} cameras · ${uniqueLocations} locations`
                            : `${rows.length.toLocaleString()} vehicle detections · ${uniqueCameras} cameras · ${uniqueLocations} locations`}
                        </span>
                      </div>
                      <div className="proj-feed-status-pill">Active Live Feed</div>

                      <div className="proj-feed-actions">
                        <label className="proj-btn-import" title="Import new CSV or Excel dataset">
                          <Upload size={13} />
                          <span>Import Files</span>
                          <input
                            accept=".csv,text/csv,.xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,.xls,application/vnd.ms-excel"
                            onChange={(e) => onImport?.(e)}
                            style={{ display: 'none' }}
                            type="file"
                          />
                        </label>
                        <Link to="/dashboards" className="proj-feed-open-link">
                          Open in Dashboards →
                        </Link>
                      </div>
                    </div>
                  ) : (
                    <div className="proj-import-panel">
                      <div className="proj-import-actions">
                        <label className="proj-btn-import primary" title="Import CSV or Excel Dataset">
                          <Upload size={14} />
                          <span>Import Files</span>
                          <input
                            accept=".csv,text/csv,.xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,.xls,application/vnd.ms-excel"
                            onChange={(e) => onImport?.(e)}
                            style={{ display: 'none' }}
                            type="file"
                          />
                        </label>

                        {onLoadSampleData && (
                          <button
                            className="proj-btn-feed-action"
                            onClick={() => onLoadSampleData?.()}
                            title="Populate dataset with sample traffic detections feed"
                            type="button"
                          >
                            <Sparkles size={13} />
                            <span>Load Sample Feed</span>
                          </button>
                        )}
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}
