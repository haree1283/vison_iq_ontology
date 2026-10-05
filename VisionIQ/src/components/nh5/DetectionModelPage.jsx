import { useEffect, useState } from 'react'
import { AlertTriangle, Cpu, IdCard, Layers, Radar } from 'lucide-react'
import { getModelInfo } from '../../services/nh5Api'
import './nh5.css'

export default function DetectionModelPage() {
  const [model, setModel] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => { getModelInfo().then(setModel).catch((err) => setError(err.message)) }, [])

  return (
    <div className="nh5-page">
      <div className="page-intro">
        <p className="section-kicker">NH5 DETECTION PIPELINE</p>
        <h1>Detection Model</h1>
        <p className="intro-copy">The model that processes every upload and live camera session.</p>
      </div>
      {error && <p className="login-error">{error}</p>}
      {model && (
        <>
          <div className="nh5-kpis nh5-kpis-row">
            <div className="viq-card nh5-kpi"><Cpu size={18} /><strong>{model.name}</strong><span>{model.modelFile}</span></div>
            <div className="viq-card nh5-kpi"><Layers size={18} /><strong>{model.architecture}</strong><span>{model.classes.length} classes</span></div>
            <div className="viq-card nh5-kpi"><Radar size={18} /><strong>{model.device.toUpperCase()}</strong><span>{model.tracker} tracking</span></div>
            <div className="viq-card nh5-kpi"><IdCard size={18} /><strong>OCR</strong><span>{model.ocrEngine}</span></div>
          </div>
          <section className="viq-card nh5-section">
            <p className="nh5-pad">{model.summary}</p>
            <div className="nh5-subhead nh5-pad-x">Detected classes</div>
            <div className="nh5-chip-row nh5-pad">
              {model.classes.map((c, i) => <span key={c}><b>{i}</b>&nbsp;{c}</span>)}
            </div>
          </section>
          <section className="viq-card nh5-section">
            <div className="viq-card-header"><div className="viq-card-title-group"><AlertTriangle className="viq-card-icon" size={19} /><h2>Event rules</h2></div></div>
            <ul className="nh5-event-list nh5-pad">
              {model.eventTypes.map((e) => (
                <li className={`sev-${e.severity}`} key={e.type}><span>{e.severity}</span>{e.label}</li>
              ))}
            </ul>
            <p className="nh5-muted nh5-pad">Accident, fire and road-work rules always run. Pedestrian, jaywalking, lane-change,
              wrong-side and stopped-vehicle rules need a road map for the camera.</p>
          </section>
        </>
      )}
    </div>
  )
}
