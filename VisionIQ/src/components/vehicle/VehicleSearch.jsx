import { Search, X } from 'lucide-react'

export default function VehicleSearch({ value, onChange, onSubmit, onClear }) {
  return (
    <form className="vehicle-search" onSubmit={onSubmit}>
      <Search size={18} />
      <input aria-label="Search vehicle number" onChange={(event) => onChange(event.target.value)} placeholder="Search vehicle number, for example MP44AB1234" value={value} />
      {value && <button aria-label="Clear vehicle search" className="vehicle-search-clear" onClick={onClear} type="button"><X size={16} /></button>}
      <button className="primary-action vehicle-search-submit" type="submit">Search</button>
    </form>
  )
}
