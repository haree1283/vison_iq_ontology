import { ArrowLeft, Clock3, FolderKanban } from 'lucide-react'
import { Link } from 'react-router-dom'

export default function ProjectComingSoon({ projectName }) {
  return (
    <div className="project-coming-soon-page">
      <div className="project-coming-soon-icon"><FolderKanban size={25} /></div>
      <p className="section-kicker">{projectName.toUpperCase()}</p>
      <h1>Dashboards coming soon</h1>
      <p>This project is connected, but its dashboard views have not been built yet.</p>
      <div className="project-coming-soon-status"><Clock3 size={15} /> Dashboard work is planned for a future phase</div>
      <Link className="back-link" to="/dashboards"><ArrowLeft size={15} /> Return to dashboards</Link>
    </div>
  )
}
