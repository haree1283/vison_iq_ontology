import { AlertTriangle, ArrowLeft, BarChart3, Bus, Car, CarFront, MapPinned, ShieldCheck, Target, Truck } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { Bar, BarChart, Cell, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import VehicleList from './vehicle/VehicleList'
import VehicleMap from './vehicle/VehicleMap'
import VehicleSearch from './vehicle/VehicleSearch'
import VehicleSummary from './vehicle/VehicleSummary'
import VehicleTimeline from './vehicle/VehicleTimeline'
import { getCameras, getVehicleIncidents, getVehicleTracking } from '../services/vehicleService'

export default function VehicleInformation() {
  const [vehicles, setVehicles] = useState([])
  const [cameras, setCameras] = useState([])
  const [selectedVehicle, setSelectedVehicle] = useState(null)
  const [searchValue, setSearchValue] = useState('')
  const [searched, setSearched] = useState(false)

  const [searchParams] = useSearchParams()
  const plateParam = searchParams.get('plate') || ''

  useEffect(() => {
    Promise.all([getVehicleIncidents(), getCameras()]).then(async ([incidentData, cameraData]) => {
      setVehicles(incidentData)
      setCameras(cameraData)
      if (plateParam) {
        setSearchValue(plateParam)
        setSelectedVehicle(await getVehicleTracking(plateParam))
        setSearched(true)
      } else {
        setSelectedVehicle(incidentData[0] || null)
      }
    })
  }, [plateParam])

  async function handleSearch(event) {
    event.preventDefault()
    const query = searchValue.trim()
    if (!query) { setSearched(false); setSelectedVehicle(vehicles[0] || null); return }
    const vehicle = await getVehicleTracking(query)
    setSelectedVehicle(vehicle)
    setSearched(true)
  }

  function clearSearch() { setSearchValue(''); setSearched(false); setSelectedVehicle(vehicles[0] || null) }

  const confidences = vehicles.flatMap((vehicle) => vehicle.observations.map((o) => o.confidence)).filter((c) => typeof c === 'number')
  const avgConfidence = confidences.length ? Math.round((confidences.reduce((a, b) => a + b, 0) / confidences.length) * 1000) / 10 : null
  const trackedCount = vehicles.filter((vehicle) => vehicle.status === 'Tracking').length
  const collisionVehicles = vehicles.filter((vehicle) => /collision|accident/i.test(vehicle.incidentType))
  const collisionCount = collisionVehicles.length
  const collisionTypes = ['Car', 'Bike', 'Auto', 'Bus', 'Truck'].map((type) => ({ type, count: collisionVehicles.filter((vehicle) => vehicle.vehicleType === type).length }))
  const chartColors = { Car: '#3978db', Bike: '#2b9c7b', Auto: '#d98a43', Bus: '#8a63c7', Truck: '#d94d58' }
  const maxCollisionCount = Math.max(...collisionTypes.map((item) => item.count), 1)
  const vehicleIcon = { Car, Bike: CarFront, Auto: CarFront, Bus, Truck }

  return <div className="vehicle-information-page"><div className="page-intro vehicle-information-intro"><div><p className="section-kicker">VEHICLE FORENSICS</p><h1>Vehicle Tracking & Incident Intelligence</h1><p className="intro-copy">Trace collision vehicles across the camera network and reconstruct every known movement.</p></div><div className="vehicle-hero-mark"><CarFront size={26} /></div></div><VehicleSearch onChange={setSearchValue} onClear={clearSearch} onSubmit={handleSearch} value={searchValue} />{searched && !selectedVehicle ? <div className="vehicle-empty-state"><AlertTriangle size={28} /><h2>No vehicle found</h2><p>No tracking information is available for <strong>{searchValue}</strong>.</p><button className="secondary-action" onClick={clearSearch} type="button">Back to all vehicles</button></div> : <><div className="vehicle-stat-grid"><div><span><AlertTriangle size={15} />Total incidents</span><strong>{collisionCount}</strong><small>Across the camera network</small></div><div><span><Target size={15} />Vehicles tracked</span><strong>{trackedCount}</strong><small>Cases with an active route</small></div><div><span><MapPinned size={15} />Cameras online</span><strong>{cameras.filter((camera) => camera.status === 'Active').length}</strong><small>Operational sources</small></div><div><span><ShieldCheck size={15} />Network confidence</span><strong>{avgConfidence === null ? '–' : `${avgConfidence}%`}</strong><small>Average plate OCR confidence</small></div></div><section className="collision-intelligence-grid"><div className="vehicle-panel collision-chart-panel"><div className="vehicle-panel-heading"><div><p className="section-kicker">COLLISION PROFILE</p><h2>Vehicles by type</h2></div><span><BarChart3 size={14} />{collisionCount} cases</span></div><div className="collision-bars">{collisionTypes.map((item) => { const Icon = vehicleIcon[item.type]; return <div className="collision-bar-row" key={item.type}><span className="collision-bar-label"><Icon size={16} />{item.type}</span><div className="collision-bar-track"><i style={{ width: `${(item.count / maxCollisionCount) * 100}%`, background: chartColors[item.type] }} /></div><strong>{item.count}</strong></div> })}</div></div><div className="vehicle-panel collision-donut-panel"><div className="vehicle-panel-heading"><div><p className="section-kicker">INCIDENT MIX</p><h2>Collision distribution</h2></div></div><div className="collision-donut"><ResponsiveContainer height="100%" width="100%"><PieChart><Pie data={collisionTypes.filter((item) => item.count)} dataKey="count" nameKey="type" innerRadius={48} outerRadius={74} paddingAngle={4}>{collisionTypes.filter((item) => item.count).map((item) => <Cell fill={chartColors[item.type]} key={item.type} />)}</Pie><Tooltip /></PieChart></ResponsiveContainer><strong>{collisionCount}</strong><span>incidents</span></div><div className="collision-legend">{collisionTypes.map((item) => <span key={item.type}><i style={{ background: chartColors[item.type] }} />{item.type}<b>{item.count}</b></span>)}</div></div><div className="vehicle-panel collision-column-panel"><div className="vehicle-panel-heading"><div><p className="section-kicker">COMPARISON VIEW</p><h2>Collision count chart</h2></div></div><div className="collision-recharts"><ResponsiveContainer height="100%" width="100%"><BarChart data={collisionTypes} margin={{ left: -20, right: 8, top: 10, bottom: 0 }}><XAxis axisLine={false} dataKey="type" tick={{ fill: '#71807a', fontSize: 10 }} tickLine={false} /><YAxis allowDecimals={false} axisLine={false} tick={{ fill: '#71807a', fontSize: 10 }} tickLine={false} /><Tooltip /><Bar dataKey="count" radius={[5, 5, 0, 0]}>{collisionTypes.map((item) => <Cell fill={chartColors[item.type]} key={item.type} />)}</Bar></BarChart></ResponsiveContainer></div></div></section>{!searched && <VehicleList onSelect={setSelectedVehicle} selectedVehicle={selectedVehicle} vehicles={vehicles} />}{selectedVehicle && <div className="vehicle-detail-layout"><div className="vehicle-detail-column"><button className="vehicle-back-button" onClick={() => { setSearched(false); setSelectedVehicle(null) }} type="button"><ArrowLeft size={15} />Back to all vehicles</button><VehicleSummary vehicle={selectedVehicle} /><VehicleTimeline vehicle={selectedVehicle} /></div><VehicleMap cameras={cameras} vehicle={selectedVehicle} /></div>}</>}</div>
}
