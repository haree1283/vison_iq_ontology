import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import {
  FileSpreadsheet,
  Maximize,
  Minus,
  Network,
  Plus,
  RefreshCw,
  Search,
  UploadCloud,
} from 'lucide-react'

import OntologyGraph from './OntologyGraph'
import OntologySidebar from './OntologySidebar'
import OntologyDetails from './OntologyDetails'
import { getOntologyGraph, listVideos } from '../../services/nh5Api'
import '../nh5/nh5.css'

const EMPTY = { nodes: [], relationships: [], summary: {} }

export default function OntologyPage({ rows = [] }) {
  const [searchParams, setSearchParams] = useSearchParams()
  const jobId = searchParams.get('jobId') || ''
  const [graph, setGraph] = useState(EMPTY)
  const [videos, setVideos] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [version, setVersion] = useState(0)
  const [searchTerm, setSearchTerm] = useState('')
  const [activeCategory, setActiveCategory] = useState('')
  const [selectedNode, setSelectedNode] = useState(null)
  const [graphControls, setGraphControls] = useState(null)
  const [showDetails, setShowDetails] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const [data, vids] = await Promise.all([getOntologyGraph(jobId), listVideos()])
      setGraph(data)
      setVideos(vids.filter((v) => v.status === 'done'))
      setError('')
      setVersion((n) => n + 1)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }, [jobId])

  // reload when the filter changes and whenever newly processed vehicles arrive
  useEffect(() => { load() }, [load, rows.length])

  const { nodes, relationships, summary } = graph
  const nodesById = useMemo(() => Object.fromEntries(nodes.map((n) => [n.id, n])), [nodes])
  const visibleNodes = useMemo(
    () => (activeCategory ? nodes.filter((node) => node.category === activeCategory) : nodes),
    [nodes, activeCategory],
  )
  const visibleRelationships = useMemo(() => {
    const ids = new Set(visibleNodes.map((n) => n.id))
    return relationships.filter((r) => ids.has(r.source) && ids.has(r.target))
  }, [visibleNodes, relationships])
  const selectedNodeData = selectedNode ? nodesById[selectedNode] : null
  const hasData = (summary.videos || 0) > 0
  const filteredVideo = videos.find((v) => v.jobId === jobId)

  function selectNode(nodeId) {
    setSelectedNode(nodeId)
    setShowDetails(true)
  }

  return (
    <div className="ontology-page">
      <div className="ontology-topbar">
        <div>
          <div className="ontology-kicker">KNOWLEDGE MODEL · EXCEL REPORTS OF PROCESSED VIDEOS</div>
          <h1>Ontology</h1>
          <p>
            Every processed video's <strong>report.xlsx</strong> is linked into one knowledge graph. Each unique
            number plate is one <strong>Vehicle</strong>, connected to every video, camera, Excel row and event it
            appears in.
          </p>
        </div>

        <div className="ontology-stat-card">
          <Network size={18} />
          <div><strong>{summary.uniquePlates || 0}</strong><span>Unique plates</span></div>
          <div className="ontology-stat-divider" />
          <div><strong>{summary.videos || 0}</strong><span>Videos</span></div>
          <div className="ontology-stat-divider" />
          <div><strong>{summary.events || 0}</strong><span>Events</span></div>
          <div className="ontology-stat-divider" />
          <div><strong>{relationships.length}</strong><span>Links</span></div>
        </div>
      </div>

      <div className="onto-filter-bar">
        <FileSpreadsheet size={16} />
        <label htmlFor="onto-video">Source</label>
        <select
          id="onto-video"
          onChange={(e) => {
            setSelectedNode(null)
            setShowDetails(false)
            setSearchParams(e.target.value ? { jobId: e.target.value } : {})
          }}
          value={jobId}
        >
          <option value="">All processed videos ({videos.length})</option>
          {videos.map((v) => (
            <option key={v.jobId} value={v.jobId}>{v.originalFilename} · {String(v.uploadedAt || '').replace('T', ' ')}</option>
          ))}
        </select>
        {jobId && !filteredVideo && !loading && <span className="onto-filter-note">video not found</span>}
        <button className="onto-refresh" disabled={loading} onClick={load} type="button">
          <RefreshCw size={14} />{loading ? 'Loading…' : 'Refresh'}
        </button>
      </div>

      {error && <p className="login-error">{error}</p>}

      {!loading && !hasData ? (
        <div className="onto-empty">
          <Network size={34} />
          <h2>No processed videos yet</h2>
          <p>Upload a video (or record a live camera session). When processing finishes its Excel report is linked
            into the ontology automatically, with one node per unique number plate.</p>
          <Link className="primary-action onto-empty-action" to="/video-upload"><UploadCloud size={16} />Upload a video</Link>
        </div>
      ) : (
        <div className="ontology-workspace">
          <div className="ontology-main">
            <div className="ontology-toolbar">
              <div className="ontology-search">
                <Search size={16} />
                <input
                  onChange={(event) => setSearchTerm(event.target.value)}
                  placeholder="Search plates, videos, events..."
                  type="text"
                  value={searchTerm}
                />
              </div>
              <div className="ontology-toolbar-actions">
                <button onClick={() => graphControls?.zoomIn()} title="Zoom in" type="button"><Plus size={17} /></button>
                <button onClick={() => graphControls?.zoomOut()} title="Zoom out" type="button"><Minus size={17} /></button>
                <button onClick={() => graphControls?.fit()} title="Fit graph" type="button"><Maximize size={16} /></button>
                <button onClick={() => graphControls?.relayout()} title="Re-layout" type="button"><RefreshCw size={16} /></button>
              </div>
            </div>

            <div className="ontology-graph-wrapper">
              <OntologyGraph
                key={`${version}-${activeCategory}`}
                nodes={visibleNodes}
                onNodeSelect={selectNode}
                onReady={setGraphControls}
                relationships={visibleRelationships}
                searchTerm={searchTerm}
                selectedNode={selectedNode}
              />
              <div className="ontology-graph-info">
                {visibleNodes.length} nodes · {visibleRelationships.length} relationships
              </div>
            </div>
          </div>

          <OntologySidebar
            activeCategory={activeCategory}
            nodes={nodes}
            relationships={relationships}
            selectedNode={selectedNode}
            setActiveCategory={setActiveCategory}
            setSelectedNode={selectNode}
          />
        </div>
      )}

      {showDetails && (
        <div className="ontology-details-drawer">
          <button className="ontology-details-close" onClick={() => setShowDetails(false)} type="button">×</button>
          <OntologyDetails node={selectedNodeData} nodesById={nodesById} onSelectNode={selectNode} relationships={relationships} />
        </div>
      )}
    </div>
  )
}
