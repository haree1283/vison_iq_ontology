import { getVehicleMeta } from '../data/vehicleTypes'

export default function VehicleBadge({ type, size = 13, className = '' }) {
  const meta = getVehicleMeta(type)
  const Icon = meta.icon

  return (
    <span
      className={`query-type-pill ${className}`.trim()}
      style={{
        background: meta.bg,
        color: meta.color,
        borderColor: meta.border,
      }}
    >
      <Icon size={size} />
      <span>{meta.label}</span>
    </span>
  )
}
