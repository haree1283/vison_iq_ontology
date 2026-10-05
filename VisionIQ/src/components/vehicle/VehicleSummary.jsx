import { Activity, Camera, Clock3, MapPin, ShieldAlert } from 'lucide-react'

export default function VehicleSummary({ vehicle }) {
  const first = vehicle.observations[0]
  const last = vehicle.observations[vehicle.observations.length - 1]
  const fields = [
    ['Vehicle number', vehicle.vehicleNumber, Activity],
    ['Incident', vehicle.incidentType, ShieldAlert],
    ['First detected', first.cameraId, Camera],
    ['Collision time', new Date(vehicle.incidentTime).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }), Clock3],
    ['Last camera', last.cameraId, MapPin],
  ]

  return <section className="vehicle-panel vehicle-summary-panel"><div className="vehicle-panel-heading"><div><p className="section-kicker">VEHICLE INFORMATION</p><h2>{vehicle.vehicleNumber}</h2></div><span className={`vehicle-status status-${vehicle.status.toLowerCase()}`}>{vehicle.status}</span></div><div className="vehicle-summary-grid">{fields.map(([label, value, Icon]) => <div key={label}><Icon size={16} /><span>{label}</span><strong>{value}</strong></div>)}</div></section>
}
