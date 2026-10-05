import { AlertTriangle, ArrowUpRight, Camera, Clock3 } from 'lucide-react'

export default function VehicleList({ vehicles, selectedVehicle, onSelect }) {
  return (
    <section className="vehicle-panel vehicle-list-panel">
      <div className="vehicle-panel-heading"><div><p className="section-kicker">INCIDENT QUEUE</p><h2>Collision vehicles</h2></div><span>{vehicles.length} active cases</span></div>
      <div className="vehicle-list">
        {vehicles.map((vehicle) => {
          const lastObservation = vehicle.observations[vehicle.observations.length - 1]
          const selected = selectedVehicle?.vehicleNumber === vehicle.vehicleNumber
          return (
            <button className={`vehicle-list-item ${selected ? 'selected' : ''}`} key={vehicle.vehicleNumber} onClick={() => onSelect(vehicle)} type="button">
              <span className="vehicle-list-icon"><AlertTriangle size={17} /></span>
              <span className="vehicle-list-copy"><strong>{vehicle.vehicleNumber}</strong><span>{vehicle.incidentType} · {vehicle.collisionCamera}</span></span>
              <span className="vehicle-list-meta"><span><Clock3 size={12} />{new Date(vehicle.incidentTime).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span><span><Camera size={12} />{lastObservation.cameraId}</span></span>
              <span className={`vehicle-status status-${vehicle.status.toLowerCase()}`}>{vehicle.status}</span><ArrowUpRight size={16} />
            </button>
          )
        })}
      </div>
    </section>
  )
}
