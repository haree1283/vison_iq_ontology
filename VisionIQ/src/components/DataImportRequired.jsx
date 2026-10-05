import { FileSpreadsheet, Sparkles, Upload } from 'lucide-react'

export default function DataImportRequired({ projectName, featureName = 'data', onImport, onLoadSample }) {
  return (
    <div className="project-coming-soon-page data-import-required-page">
      <div className="project-coming-soon-icon" style={{ background: '#e0ecff', color: '#1d58d8' }}>
        <FileSpreadsheet size={28} />
      </div>

      <p className="section-kicker">PROJECT CONNECTED: {projectName?.toUpperCase() || 'PLATFORM A'}</p>
      <h1>Dataset Required (CSV / XLSX)</h1>
      <p>
        To view and analyze <strong>{featureName}</strong>, please upload a traffic CSV or XLSX Excel file. The system will
        dynamically construct the data models, entity relationships, and visualizations from your dataset.
      </p>

      <div className="data-import-actions">
        <label className="data-import-file-btn">
          <Upload size={16} />
          <span>Upload CSV / XLSX File</span>
          <input
            accept=".csv,text/csv,.xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,.xls,application/vnd.ms-excel"
            onChange={onImport}
            type="file"
            style={{ display: 'none' }}
          />
        </label>

        {onLoadSample && (
          <button className="data-import-sample-btn" onClick={onLoadSample} type="button">
            <Sparkles size={15} />
            <span>Load Sample Dataset</span>
          </button>
        )}
      </div>

      <div className="data-import-hint" style={{ flexWrap: 'wrap', maxWidth: '800px', margin: '14px auto 0' }}>
        <span>Supported CSV / XLSX headings:</span>
        <code>ID</code>
        <code>Timestamp (IST)</code>
        <code>Vehicle Type</code>
        <code>Vehicle Number Plate</code>
        <code>Plate Confidence</code>
        <code>Vehicle Image</code>
        <code>Speed (km/h)</code>
        <code>Speed Limit (km/h)</code>
        <code>Over Speed</code>
        <code>Latitude</code>
        <code>Longitude</code>
        <code>Video Clip Path</code>
        <code>Vehicle Image Path</code>
        <code>Plate Image Path</code>
      </div>
    </div>
  )
}
