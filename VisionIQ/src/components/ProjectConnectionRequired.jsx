import { ArrowRight, FolderKanban, Plug } from 'lucide-react'
import { Link } from 'react-router-dom'

export default function ProjectConnectionRequired() {
  return (
    <div className="project-coming-soon-page">
      <div className="project-coming-soon-icon"><FolderKanban size={25} /></div>
      <p className="section-kicker">NO ACTIVE PROJECT</p>
      <h1>Connect a project</h1>
      <p>Select a project from the Projects section, then connect it to access this workspace and its operations.</p>
      <div className="project-coming-soon-status"><Plug size={15} /> Waiting for a project connection</div>
      <Link to="/projects" className="proj-btn-primary" style={{ marginTop: '16px', display: 'inline-flex', alignItems: 'center', gap: '8px', textDecoration: 'none' }}>
        Open Projects View <ArrowRight size={14} />
      </Link>
    </div>
  )
}

