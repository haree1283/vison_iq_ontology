import {
  AlertCircle,
  Check,
  FileSpreadsheet,
  FolderKanban,
  Plug,
  Sparkles,
  Trash2,
  Upload,
} from 'lucide-react'

export default function ProjectMainBar({
  selectedProject,
  connectedProject,
  onProjectConnect,
  onProjectDisconnect,
  onImport,
  fileName,
  hasImportedFile,
  rows = [],
  importError,
  onLoadSampleData,
  onDeleteProject,
}) {
  if (!selectedProject) return null

  const isConnected = Boolean(
    connectedProject && selectedProject && connectedProject.key === selectedProject.key,
  )

  const uniqueCameras = new Set(rows.map((r) => r?.camera).filter(Boolean)).size
  const uniqueLocations = new Set(rows.map((r) => r?.location).filter(Boolean)).size

  return (
    <div aria-label="Project Actions Bar" className="project-main-bar" role="region">
      <div className="project-main-bar-left">
        <div className="project-main-icon">
          <FolderKanban size={18} strokeWidth={2} />
        </div>
        <div className="project-main-meta">
          <div className="project-main-title-row">
            <span className="project-main-label">PROJECT</span>
            <h2 className="project-main-name">{selectedProject.name}</h2>
            <span
              className={`project-main-badge ${
                isConnected
                  ? 'connected'
                  : selectedProject.comingSoon
                  ? 'coming-soon'
                  : 'idle'
              }`}
            >
              <span className="project-badge-dot" />
              {isConnected
                ? 'Connected'
                : selectedProject.comingSoon
                ? 'Coming soon'
                : selectedProject.status || 'Inactive'}
            </span>
          </div>
          <p className="project-main-subtext">
            {selectedProject.caption}
            {selectedProject.modules ? ` · ${selectedProject.modules}` : ''}
            {selectedProject.dashboards ? ` · ${selectedProject.dashboards}` : ''}
          </p>
        </div>
      </div>

      <div className="project-main-bar-right">
        {isConnected ? (
          <>
            {hasImportedFile ? (
              <div className="main-bar-file-pill">
                <div className="file-pill-info">
                  <FileSpreadsheet className="file-pill-icon" size={16} />
                  <div className="file-pill-text">
                    <strong>{fileName}</strong>
                    <span>
                      {rows.length.toLocaleString()} records · {uniqueCameras} cameras · {uniqueLocations} locations
                    </span>
                  </div>
                </div>
                <label className="main-bar-action-btn secondary file-input-label" title="Upload another CSV or XLSX file">
                  <Upload size={13} />
                  <span>Change File</span>
                  <input
                    accept=".csv,text/csv,.xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,.xls,application/vnd.ms-excel"
                    onChange={onImport}
                    style={{ display: 'none' }}
                    type="file"
                  />
                </label>
              </div>
            ) : (
              <div className="main-bar-upload-group">
                <label className="main-bar-action-btn primary file-input-label">
                  <Upload size={14} />
                  <span>Upload CSV / XLSX</span>
                  <input
                    accept=".csv,text/csv,.xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,.xls,application/vnd.ms-excel"
                    onChange={onImport}
                    style={{ display: 'none' }}
                    type="file"
                  />
                </label>
                {onLoadSampleData && (
                  <button className="main-bar-action-btn sample" onClick={onLoadSampleData} type="button">
                    <Sparkles size={13} />
                    <span>Load Sample Data</span>
                  </button>
                )}
              </div>
            )}

            <button
              className="main-bar-action-btn disconnect"
              onClick={onProjectDisconnect}
              title="Disconnect this project"
              type="button"
            >
              <Plug size={13} />
              <span>Disconnect</span>
            </button>
          </>
        ) : (
          <div className="main-bar-connect-group">
            {selectedProject.comingSoon && !selectedProject.created ? (
              <span className="main-bar-coming-soon-note">
                This project will be available in a future phase.
              </span>
            ) : (
              <button
                className="main-bar-action-btn primary"
                onClick={() => onProjectConnect(selectedProject)}
                type="button"
              >
                <Check size={14} strokeWidth={2.2} />
                <span>Connect Project</span>
              </button>
            )}
          </div>
        )}

        {selectedProject.created && (
          <button
            className="main-bar-action-btn delete"
            onClick={() => onDeleteProject(selectedProject)}
            title="Delete this project"
            type="button"
          >
            <Trash2 size={13} />
            <span>Delete</span>
          </button>
        )}
      </div>

      {importError && (
        <div className="project-main-bar-error">
          <AlertCircle size={14} />
          <span>{importError}</span>
        </div>
      )}
    </div>
  )
}
