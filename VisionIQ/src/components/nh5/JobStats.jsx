import { AlertTriangle, Bike, Bus, Car, CarFront, Gauge, IdCard, Truck, Users } from 'lucide-react'
import { VEHICLE_TYPES, formatDuration } from '../../services/nh5Api'

const TYPE_ICONS = { car: Car, motorcycle: Bike, auto: CarFront, bus: Bus, truck: Truck, bicycle: Bike }

// Live numbers of a processing job or live camera session (the /status payload of the NH5 pipeline).
export default function JobStats({ status, showSpeed = true }) {
  if (!status) return null
  const types = status.vehicle_types || {}
  const total = VEHICLE_TYPES.reduce((n, [key]) => n + (types[key] || 0), 0)
  const plateCounts = status.plate_counts || {}
  const events = (status.events || []).slice().reverse()

  return (
    <div className="nh5-stats">
      <div className="nh5-type-grid">
        <div className="nh5-type total">
          <strong>{total}</strong>
          <span>All vehicles</span>
        </div>
        {VEHICLE_TYPES.map(([key, label]) => {
          const Icon = TYPE_ICONS[key] || Car
          return (
            <div className="nh5-type" key={key}>
              <Icon size={15} />
              <strong>{types[key] || 0}</strong>
              <span>{label}</span>
            </div>
          )
        })}
        <div className="nh5-type">
          <Users size={15} />
          <strong>{status.num_people || 0}</strong>
          <span>People</span>
        </div>
      </div>

      {showSpeed && (
        <div className="nh5-speed-row">
          <Gauge size={15} />
          <span>Frames <b>{status.total_frames ? `${status.frame_idx} / ${status.total_frames}` : status.frame_idx || 0}</b></span>
          <span>Speed <b>{status.processing_fps ? `${status.processing_fps} fps` : '–'}</b></span>
          <span>Per frame <b>{status.ms_per_frame ? `${status.ms_per_frame} ms` : '–'}</b></span>
          {status.status === 'processing' && <span>Time left <b>{formatDuration(status.eta_secs)}</b></span>}
        </div>
      )}

      <div className="nh5-subhead"><IdCard size={15} />Number plates ({(status.plates || []).length})</div>
      {(status.plates || []).length ? (
        <div className="nh5-plate-list">
          {status.plates.map((plate) => (
            <span className="nh5-plate" key={plate}>
              <em>IND</em>{plate}
              {(plateCounts[plate] || 1) > 1 && <b>×{plateCounts[plate]}</b>}
            </span>
          ))}
        </div>
      ) : (
        <p className="nh5-muted">No plate confirmed yet (a plate needs 5 matching reads).</p>
      )}

      <div className="nh5-subhead"><AlertTriangle size={15} />Events ({status.num_events || 0})</div>
      {events.length ? (
        <ul className="nh5-event-list">
          {events.map((ev) => (
            <li className={`sev-${ev.severity}`} key={ev.id}>
              <span>{Number(ev.time_s || 0).toFixed(1)}s</span>
              {ev.label}{ev.track_id !== null && ev.track_id !== undefined ? ` · #${ev.track_id} ${ev.object_class}` : ''}
            </li>
          ))}
        </ul>
      ) : (
        <p className="nh5-muted">No events.</p>
      )}
    </div>
  )
}
