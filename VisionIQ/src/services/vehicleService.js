// Vehicle tracking by unique number plate, built by the backend from the processed videos' Excel reports.
const apiBaseUrl = (import.meta.env.VITE_API_URL || '').replace(/\/$/, '')

async function getJson(path, fallback) {
  try {
    const response = await fetch(`${apiBaseUrl}${path}`)
    if (!response.ok) return fallback
    return await response.json()
  } catch {
    return fallback
  }
}

export async function getVehicleIncidents() {
  const result = await getJson('/api/vehicles/incidents', null)
  return result?.incidents || []
}

export async function getCameras() {
  const result = await getJson('/api/cameras', null)
  return result?.cameras || []
}

export async function getVehicleTracking(vehicleNumber) {
  const result = await getJson(`/api/vehicles/${encodeURIComponent(vehicleNumber)}`, null)
  return result?.vehicle || null
}
