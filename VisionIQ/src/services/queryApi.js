const API_URL = (import.meta?.env?.VITE_API_URL || '').replace(/\/$/, '')

/**
 * Check if the backend is connected to the local Ollama server and if qwen3:8b is loaded.
 */
export async function checkOllamaStatus() {
  try {
    const res = await fetch(`${API_URL}/api/query/ollama-status`, {
      headers: { 'Content-Type': 'application/json' },
    })
    if (!res.ok) {
      return { connected: false, message: `Server error: HTTP ${res.status}` }
    }
    return await res.json()
  } catch (err) {
    return { connected: false, message: err.message || 'Cannot reach VisionIQ backend' }
  }
}

/**
 * Client-side immediate natural query rule parser.
 * Provides instant (<1ms) filter computation for zero-latency UI and graph updates.
 */
export function parseQueryClient(query, facets = {}) {
  const q = String(query || '').toLowerCase().trim()
  const filters = {
    vehicleType: null,
    vehicleTypes: [],
    minSpeed: null,
    maxSpeed: null,
    overspeedOnly: null,
    location: null,
    camera: null,
    signalState: null,
    weather: null,
    plateSearch: null,
    sortBy: 'timestamp-desc',
    explanation: `Natural query: "${query}"`,
  }

  if (!q) return filters

  // Overspeed & Reckless Driving
  if (
    q.includes('overspeed') ||
    q.includes('speeding') ||
    q.includes('violation') ||
    q.includes('violator') ||
    q.includes('fast') ||
    q.includes('over speed') ||
    q.includes('rash') ||
    q.includes('reckless') ||
    q.includes('dangerously') ||
    q.includes('challan') ||
    q.includes('over limit') ||
    q.includes('flying')
  ) {
    filters.overspeedOnly = true
  }

  // Speed ranges (e.g. "between 40 and 70", "from 50 to 80")
  const speedRangeMatch = q.match(/(?:between|from)\s*(\d+)\s*(?:and|to|-)\s*(\d+)/i)
  if (speedRangeMatch) {
    filters.minSpeed = parseInt(speedRangeMatch[1], 10)
    filters.maxSpeed = parseInt(speedRangeMatch[2], 10)
  } else {
    // Min speed (e.g. "speed > 60", "speed >= 60", "greater than 60", "over 60", "faster than 60", "above 60", "speed 60 km/h")
    const speedMinMatch = q.match(/(?:speed\s*(?:>|>=|above|over|exceeding|faster than|greater than|more than|higher than|of)?\s*|>|>=|above|over|faster than|greater than|more than|exceeding)\s*(\d+)/i)
    if (speedMinMatch) {
      filters.minSpeed = parseInt(speedMinMatch[1], 10)
    }

    // Max speed (e.g. "speed < 40", "speed <= 40", "slower than 40", "under 40", "below 40", "less than 40")
    const speedMaxMatch = q.match(/(?:speed\s*(?:<|<=|under|below|slower than|less than|lower than)\s*|<|<=|under|below|slower than|less than|lower than)\s*(\d+)/i)
    if (speedMaxMatch) {
      filters.maxSpeed = parseInt(speedMaxMatch[1], 10)
    }
  }

  // Multi-vehicle types detection with broad category groupings
  const detectedTypes = []
  if (/\b(?:car|cars|sedan|suv|hatchback|cab|taxi|four[- ]?wheelers?|4[- ]?wheelers?)\b/i.test(q)) detectedTypes.push('Car')
  if (/\b(?:bike|bikes|motorcycle|motorcycles|scooter|scooters|two[- ]?wheelers?|2[- ]?wheelers?|cycle|cycles|bicycle|bicycles|moped)\b/i.test(q)) detectedTypes.push('Bike')
  if (/\b(?:bus|buses|minibus|coach)\b/i.test(q)) detectedTypes.push('Bus')
  if (/\b(?:truck|trucks|lorry|lorries|trailer|trailers|heavy|dumper|tipper)\b/i.test(q)) detectedTypes.push('Truck')
  if (/\b(?:auto|autos|rickshaw|rickshaws|auto[- ]?rickshaws?|autorickshaw|autorickshaws|3[- ]?wheelers?|three[- ]?wheelers?|tuktuk)\b/i.test(q)) detectedTypes.push('Auto')
  if (/\b(?:tractor|tractors)\b/i.test(q)) detectedTypes.push('Tractor')
  if (/\b(?:jeep|jeeps|4x4|thar)\b/i.test(q)) detectedTypes.push('Jeep')
  if (/\b(?:pedestrian|pedestrians|walking|people|person|edisetrain|edisetrains)\b/i.test(q)) detectedTypes.push('Pedestrian')
  if (/\b(?:van|vans|omni|eeco)\b/i.test(q)) detectedTypes.push('Van')
  if (/\b(?:ambulance|ambulances|emergency)\b/i.test(q)) detectedTypes.push('Ambulance')
  if (/\b(?:train|trains|metro|rail|tram)\b/i.test(q)) detectedTypes.push('Train')

  // Heavy vehicles grouping
  if (/\bheavy(?:\s+vehicles?|\s+transport)?\b/i.test(q)) {
    if (!detectedTypes.includes('Truck')) detectedTypes.push('Truck')
    if (!detectedTypes.includes('Bus')) detectedTypes.push('Bus')
  }
  // Commercial transport grouping
  if (/\bcommercial(?:\s+vehicles?|\s+transport)?\b/i.test(q)) {
    if (!detectedTypes.includes('Truck')) detectedTypes.push('Truck')
    if (!detectedTypes.includes('Bus')) detectedTypes.push('Bus')
    if (!detectedTypes.includes('Auto')) detectedTypes.push('Auto')
  }

  filters.vehicleTypes = detectedTypes
  filters.vehicleType = detectedTypes.length === 1 ? detectedTypes[0] : (detectedTypes.length > 1 ? detectedTypes : null)

  // Signals & Red Light Jumping
  if (
    q.includes('red light') ||
    q.includes('red signal') ||
    q.includes('ran red') ||
    q.includes('jumped red') ||
    q.includes('crossed red') ||
    q.includes('signal jump') ||
    q.includes('signal violation') ||
    /\bred\b/i.test(q)
  ) {
    filters.signalState = 'Red'
  } else if (q.includes('green signal') || q.includes('green light') || /\bgreen\b/i.test(q)) {
    filters.signalState = 'Green'
  } else if (q.includes('yellow') || q.includes('amber')) {
    filters.signalState = 'Yellow'
  }

  // Weather
  if (q.includes('rain') || q.includes('rainy') || q.includes('raining') || q.includes('monsoon') || q.includes('wet')) {
    filters.weather = 'Rainy'
  } else if (q.includes('fog') || q.includes('foggy') || q.includes('mist') || q.includes('misty') || q.includes('smog')) {
    filters.weather = 'Foggy'
  } else if (q.includes('clear') || q.includes('sunny')) {
    filters.weather = 'Clear'
  }

  // Camera matching
  const IGNORE_CAM_WORDS = new Set(['detections', 'records', 'view', 'network', 'graph', 'feed', 's', 'all', 'any'])
  if (facets.cameras && Array.isArray(facets.cameras)) {
    for (const cam of facets.cameras) {
      const camNorm = cam.toLowerCase().replace(/[^a-z0-9]/g, '')
      const qNorm = q.replace(/[^a-z0-9]/g, '')
      if (qNorm.includes(camNorm)) {
        filters.camera = cam
        break
      }
    }
  }
  if (!filters.camera) {
    const camMatch = q.match(/\bcam(?:era)?[-_\s]*(\d+|0[1-9])\b/i)
    if (camMatch && !IGNORE_CAM_WORDS.has(camMatch[1].toLowerCase())) {
      const num = camMatch[1]
      filters.camera = num.length === 1 ? `CAM-0${num}` : `CAM-${num}`
    }
  }

  // Location matching from facets
  const GENERIC_LOC_WORDS = new Set(['road', 'main', 'city', 'street', 'junction', 'lane', 'blvd', 'highway', 'crossing', 'expressway', 'traffic', 'zone', 'area', 'circle', 'bypass', 'way', 'north', 'south', 'east', 'west'])
  if (facets.locations && Array.isArray(facets.locations)) {
    for (const loc of facets.locations) {
      const locLower = loc.toLowerCase()
      if (q.includes(locLower)) {
        filters.location = loc
        break
      }
      const words = locLower.split(/[\s\-_]+/).filter((w) => w.length > 3 && !GENERIC_LOC_WORDS.has(w))
      if (words.length > 0 && words.some((w) => q.includes(w))) {
        filters.location = loc
        break
      }
    }
  }

  // Plate matching pattern: e.g. "TS09AB1234", "TS 09 AB 1234", "MH-12-DE-1433"
  const plateMatch = q.match(/\b([a-z]{2}\s*[-]?\s*[0-9]{1,2}\s*[-]?\s*[a-z]{0,3}\s*[-]?\s*[0-9]{1,4})\b/i)
  if (plateMatch && plateMatch[1].replace(/[^a-z0-9]/gi, '').length >= 4) {
    filters.plateSearch = plateMatch[1].replace(/[\s-]/g, '').toUpperCase()
  }

  // Sort & superlatives
  if (q.includes('fastest') || q.includes('highest speed') || q.includes('top speed') || q.includes('maximum speed')) {
    filters.sortBy = 'speed-desc'
  } else if (q.includes('slowest') || q.includes('lowest speed') || q.includes('traffic jam') || q.includes('crawl')) {
    filters.sortBy = 'speed-asc'
  } else if (q.includes('highest confidence') || q.includes('most confident') || q.includes('clear plate')) {
    filters.sortBy = 'confidence-desc'
  } else if (q.includes('lowest confidence') || q.includes('least confident') || q.includes('blurred') || q.includes('unclear')) {
    filters.sortBy = 'confidence-asc'
  } else if (q.includes('latest') || q.includes('recent') || q.includes('newest')) {
    filters.sortBy = 'timestamp-desc'
  } else if (q.includes('earliest') || q.includes('oldest')) {
    filters.sortBy = 'timestamp-asc'
  }

  // Explanation
  const parts = []
  if (filters.vehicleTypes?.length) parts.push(`Vehicle Type: ${filters.vehicleTypes.join(', ')}`)
  else if (filters.vehicleType) parts.push(`Vehicle Type: ${filters.vehicleType}`)
  if (filters.overspeedOnly) parts.push('Over Speed: Yes')
  if (filters.minSpeed && filters.maxSpeed) parts.push(`Speed: ${filters.minSpeed} - ${filters.maxSpeed} km/h`)
  else if (filters.minSpeed) parts.push(`Speed > ${filters.minSpeed} km/h`)
  else if (filters.maxSpeed) parts.push(`Speed < ${filters.maxSpeed} km/h`)
  if (filters.location) parts.push(`Road: ${filters.location}`)
  if (filters.camera) parts.push(`Camera: ${filters.camera}`)
  if (filters.signalState) parts.push(`Signal: ${filters.signalState}`)
  if (filters.weather) parts.push(`Weather: ${filters.weather}`)
  if (filters.plateSearch) parts.push(`Plate: ${filters.plateSearch}`)

  filters.explanation = parts.length
    ? `Filtered telemetry graph segment for ${parts.join(', ')}`
    : `Retrieved telemetry graph segment matching "${query}"`

  return filters
}

/**
 * Send natural language query to backend qwen3:8b endpoint to parse into structured telemetry criteria.
 */
export async function parseNaturalLanguageQuery(query, facets = {}) {
  try {
    const res = await fetch(`${API_URL}/api/query/ai-parse`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query, facets }),
    })
    if (!res.ok) {
      throw new Error(`API responded with HTTP ${res.status}`)
    }
    return await res.json()
  } catch (err) {
    console.warn('[queryApi] AI query backend call failed:', err)
    // Intelligent local client fallback
    const fallbackFilters = parseQueryClient(query, facets)
    return {
      success: true,
      aiSource: 'client-rule-engine',
      filters: fallbackFilters,
      explanation: fallbackFilters.explanation,
      rawQuery: query,
    }
  }
}

/**
 * Fast search across all vehicle records in MySQL database.
 * Returns exact matching vehicles, detection count, and vehicle dossier intelligence summary.
 */
export async function searchVehiclesDatabase(searchTerm, limit = 50) {
  try {
    const res = await fetch(`${API_URL}/api/vehicles/search?q=${encodeURIComponent(searchTerm)}&limit=${limit}`)
    if (!res.ok) return { success: false, vehicles: [], count: 0, dossier: null }
    return await res.json()
  } catch (err) {
    console.warn('[queryApi] Vehicle database search error:', err.message)
    return { success: false, vehicles: [], count: 0, dossier: null }
  }
}

