import {
  AlertTriangle,
  Box,
  Camera,
  CarFront,
  CircleDot,
  Download,
  ExternalLink,
  FileSpreadsheet,
  Film,
  Info,
  Layers,
} from 'lucide-react'
import { Link } from 'react-router-dom'
import { categoryColor, categoryLabel } from '../../data/ontologyData'
import { mediaUrl } from '../../services/nh5Api'

const iconMap = {
  Ontology: Info,
  OntologyClass: Box,
  Vehicle: CarFront,
  VehicleGroup: Layers,
  Video: Film,
  Camera,
  Report: FileSpreadsheet,
  Event: AlertTriangle,
}

export default function OntologyDetails({ node, relationships, nodesById = {}, onSelectNode }) {
  if (!node) {
    return (
      <div className="ontology-details-empty">
        <Info size={28} />
        <h3>Select a node</h3>
        <p>Click any node in the ontology graph to view its information and relationships.</p>
      </div>
    )
  }

  const Icon = iconMap[node.category] || CircleDot
  const outgoing = relationships.filter((item) => item.source === node.id)
  const incoming = relationships.filter((item) => item.target === node.id)
  const properties = Object.entries(node.properties || {}).filter(([, v]) => v !== null && v !== undefined && v !== '')
  const media = node.media || {}
  const nameOf = (id) => nodesById[id]?.label || id

  return (
    <div className="ontology-details">
      <div className="ontology-details-header">
        <div className="ontology-details-icon" style={{ background: categoryColor[node.category], color: '#fff' }}>
          <Icon size={20} />
        </div>
        <div>
          <div className="ontology-details-category">{categoryLabel[node.category] || node.category}</div>
          <h2>{node.label}</h2>
        </div>
      </div>

      {(media.vehicleImage || media.plateImage || media.thumbnail || media.snapshot) && (
        <div className="onto-media-row">
          {[media.vehicleImage, media.plateImage, media.thumbnail, media.snapshot].filter(Boolean).map((src) => (
            <a href={mediaUrl(src)} key={src} rel="noreferrer" target="_blank">
              <img alt={node.label} src={mediaUrl(src)} />
            </a>
          ))}
        </div>
      )}

      <div className="ontology-detail-section">
        <h4>Description</h4>
        <p>{node.description || 'No description available.'}</p>
      </div>

      {properties.length > 0 && (
        <div className="ontology-detail-section">
          <h4>Properties</h4>
          {properties.map(([key, value]) => (
            <div className="ontology-info-row" key={key}>
              <span>{key}</span>
              <strong>{String(value)}</strong>
            </div>
          ))}
        </div>
      )}

      <div className="onto-detail-actions">
        {node.jobId && (
          <Link className="onto-action" to={`/video-library/${node.jobId}`}><Film size={14} />Open in Video Library</Link>
        )}
        {media.video && (
          <a className="onto-action" href={mediaUrl(media.video)} rel="noreferrer" target="_blank"><ExternalLink size={14} />Annotated video</a>
        )}
        {media.download && (
          <a className="onto-action excel" href={mediaUrl(media.download)}><Download size={14} />Download report.xlsx</a>
        )}
        {media.clip && (
          <a className="onto-action" href={mediaUrl(media.clip)} rel="noreferrer" target="_blank"><ExternalLink size={14} />Event clip</a>
        )}
        {node.plate && (
          <Link className="onto-action" to={`/vehicle-information?plate=${encodeURIComponent(node.plate)}`}><CarFront size={14} />Track this vehicle</Link>
        )}
      </div>

      <div className="ontology-detail-section">
        <h4>Relationships</h4>
        {outgoing.length === 0 && incoming.length === 0 ? (
          <p>No relationships found.</p>
        ) : (
          <div className="ontology-relationship-list">
            {[...outgoing.map((r) => ({ r, dir: 'out', other: r.target })), ...incoming.map((r) => ({ r, dir: 'in', other: r.source }))].map(({ r, dir, other }) => (
              <button
                className="ontology-relationship onto-rel-button"
                key={`${dir}-${r.id}`}
                onClick={() => onSelectNode?.(other)}
                type="button"
              >
                <span className="relationship-direction">{dir === 'out' ? '→' : '←'}</span>
                <div>
                  <strong>{r.label}</strong>
                  <small>
                    {dir === 'out' ? '→ ' : '← '}{nameOf(other)}
                    {r.properties?.rows ? ` · ${r.properties.sheet} sheet row ${r.properties.rows}` : ''}
                  </small>
                </div>
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
