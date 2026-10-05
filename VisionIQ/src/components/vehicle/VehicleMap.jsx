import { useEffect, useRef, useState } from 'react'
import { Camera, MapPin, Navigation, Radio } from 'lucide-react'

const googleMapsKey = import.meta.env.VITE_GOOGLE_MAPS_API_KEY

function loadGoogleMaps() {
  if (window.google?.maps) return Promise.resolve(window.google.maps)
  if (!googleMapsKey) return Promise.resolve(null)
  if (window.__visionIqMapsPromise) return window.__visionIqMapsPromise
  window.__visionIqMapsPromise = new Promise((resolve, reject) => {
    const script = document.createElement('script')
    script.src = `https://maps.googleapis.com/maps/api/js?key=${googleMapsKey}`
    script.async = true
    script.onload = () => resolve(window.google.maps)
    script.onerror = reject
    document.head.appendChild(script)
  })
  return window.__visionIqMapsPromise
}

const hasCoords = (p) => Number.isFinite(p?.latitude) && Number.isFinite(p?.longitude)

function FallbackMap({ cameras: allCameras, vehicle }) {
  // points without GPS (videos uploaded without latitude/longitude) cannot be placed on the map
  const cameras = allCameras.filter(hasCoords)
  const route = (vehicle?.observations || []).filter(hasCoords)
  const allPoints = [...cameras, ...route]
  const latitudes = allPoints.map((point) => point.latitude)
  const longitudes = allPoints.map((point) => point.longitude)
  const minLat = Math.min(...latitudes)
  const maxLat = Math.max(...latitudes)
  const minLng = Math.min(...longitudes)
  const maxLng = Math.max(...longitudes)
  const x = (lng) => `${18 + ((lng - minLng) / ((maxLng - minLng) || 1)) * 64}%`
  const y = (lat) => `${82 - ((lat - minLat) / ((maxLat - minLat) || 1)) * 64}%`

  return <div className="vehicle-map-fallback"><div className="vehicle-map-fallback-grid" /><div className="vehicle-map-fallback-label"><Radio size={14} />Google Maps preview</div>{cameras.map((camera) => <span className="map-camera-dot" key={camera.id} style={{ left: x(camera.longitude), top: y(camera.latitude) }} title={`${camera.id} · ${camera.name}`}><Camera size={12} /></span>)}{route.map((point, index) => <span className={`map-route-dot ${index === 0 ? 'collision' : ''}`} key={`${point.cameraId}-${point.timestamp}`} style={{ left: x(point.longitude), top: y(point.latitude) }} title={`${point.cameraId} · ${point.location}`} />)}{route.length > 1 && <svg className="map-route-line" preserveAspectRatio="none" viewBox="0 0 100 100"><polyline fill="none" points={route.map((point) => `${Number.parseFloat(x(point.longitude))},${Number.parseFloat(y(point.latitude))}`).join(' ')} /></svg>}<div className="vehicle-map-fallback-note">Add <strong>VITE_GOOGLE_MAPS_API_KEY</strong> to enable the interactive map.</div></div>
}

export default function VehicleMap({ cameras: allCameras, vehicle }) {
  const mapRef = useRef(null)
  const [mapsReady, setMapsReady] = useState(false)
  const cameras = allCameras.filter(hasCoords)
  const route = (vehicle?.observations || []).filter(hasCoords)

  useEffect(() => { let active = true; loadGoogleMaps().then((maps) => { if (active && maps) setMapsReady(true) }).catch(() => undefined); return () => { active = false } }, [])

  useEffect(() => {
    if (!mapsReady || !mapRef.current) return
    const maps = window.google.maps
    const points = [...cameras, ...route]
    if (!points.length) return
    const map = new maps.Map(mapRef.current, { center: { lat: points[0].latitude, lng: points[0].longitude }, zoom: 13, mapTypeControl: false, streetViewControl: false, fullscreenControl: false })
    const bounds = new maps.LatLngBounds()
    cameras.forEach((camera) => { const marker = new maps.Marker({ map, position: { lat: camera.latitude, lng: camera.longitude }, title: camera.id, icon: { path: maps.SymbolPath.CIRCLE, scale: 7, fillColor: '#3978db', fillOpacity: 1, strokeColor: '#fff', strokeWeight: 2 } }); const info = new maps.InfoWindow({ content: `<strong>${camera.id}</strong><br>${camera.name}<br>${camera.status}<br>${camera.latitude.toFixed(6)}, ${camera.longitude.toFixed(6)}` }); marker.addListener('click', () => info.open({ map, anchor: marker })) })
    const routePath = route.map((point) => { const position = { lat: point.latitude, lng: point.longitude }; bounds.extend(position); const marker = new maps.Marker({ map, position, title: `${point.cameraId} · ${point.detectionType}`, icon: { path: maps.SymbolPath.CIRCLE, scale: point === route[0] ? 9 : 6, fillColor: point === route[0] ? '#dc4c55' : '#27a37e', fillOpacity: 1, strokeColor: '#fff', strokeWeight: 2 } }); const info = new maps.InfoWindow({ content: `<strong>${point.cameraId}</strong><br>${point.detectionType}<br>${point.location}<br>${new Date(point.timestamp).toLocaleTimeString()}<br>Confidence: ${Math.round(point.confidence * 100)}%` }); marker.addListener('click', () => info.open({ map, anchor: marker })); return position })
    if (routePath.length > 1) new maps.Polyline({ map, path: routePath, geodesic: true, strokeColor: '#2a9a86', strokeOpacity: .9, strokeWeight: 4 })
    cameras.forEach((camera) => bounds.extend({ lat: camera.latitude, lng: camera.longitude }))
    map.fitBounds(bounds)
  }, [cameras, mapsReady, route])

  return <section className="vehicle-panel vehicle-map-panel"><div className="vehicle-panel-heading"><div><p className="section-kicker">SPATIAL INTELLIGENCE</p><h2>Camera network & route</h2></div><span><Navigation size={14} />{route.length ? `${route.length} route points` : cameras.length ? 'All cameras' : 'Add latitude/longitude when uploading to see the map'}</span></div><div className="vehicle-map-shell">{mapsReady ? <div className="vehicle-google-map" ref={mapRef} /> : <FallbackMap cameras={allCameras} vehicle={vehicle} />}</div><div className="vehicle-map-legend"><span><i className="legend-camera" />Camera network</span><span><i className="legend-route" />Vehicle route</span><span><i className="legend-collision" />Collision point</span></div></section>
}
