import {
  Ambulance,
  Bike,
  Bus,
  Car,
  CarFront,
  Footprints,
  Navigation,
  Tractor,
  Train,
  TramFront,
  Truck,
  Users,
  Van,
} from 'lucide-react'

export const VEHICLE_CONFIGS = {
  car: {
    label: 'Car',
    icon: Car,
    color: '#2563eb', // Vibrant Royal Blue
    bg: '#eff6ff',
    border: '#bfdbfe',
  },
  cars: {
    label: 'Cars',
    icon: Car,
    color: '#2563eb',
    bg: '#eff6ff',
    border: '#bfdbfe',
  },
  bike: {
    label: 'Bike',
    icon: Bike,
    color: '#06b6d4', // Vivid Cyan / Teal - highly distinct from Car's blue
    bg: '#ecfeff',
    border: '#a5f3fc',
  },
  bikes: {
    label: 'Bikes',
    icon: Bike,
    color: '#06b6d4',
    bg: '#ecfeff',
    border: '#a5f3fc',
  },
  bicycle: {
    label: 'Bicycle',
    icon: Bike,
    color: '#0d9488',
    bg: '#f0fdfa',
    border: '#99f6e4',
  },
  motorcycle: {
    label: 'Motorcycle',
    icon: Bike,
    color: '#06b6d4',
    bg: '#ecfeff',
    border: '#a5f3fc',
  },
  bus: {
    label: 'Bus',
    icon: Bus,
    color: '#8b5cf6', // Vivid Purple
    bg: '#f5f3ff',
    border: '#ddd6fe',
  },
  buses: {
    label: 'Buses',
    icon: Bus,
    color: '#8b5cf6',
    bg: '#f5f3ff',
    border: '#ddd6fe',
  },
  truck: {
    label: 'Truck',
    icon: Truck,
    color: '#f97316', // Vibrant Orange
    bg: '#fff7ed',
    border: '#fed7aa',
  },
  trucks: {
    label: 'Trucks',
    icon: Truck,
    color: '#f97316',
    bg: '#fff7ed',
    border: '#fed7aa',
  },
  tractor: {
    label: 'Tractor',
    icon: Tractor,
    color: '#c2410c', // Terracotta / Rust
    bg: '#fff7ed',
    border: '#fed7aa',
  },
  tractors: {
    label: 'Tractors',
    icon: Tractor,
    color: '#c2410c',
    bg: '#fff7ed',
    border: '#fed7aa',
  },
  tractr: {
    label: 'Tractor',
    icon: Tractor,
    color: '#c2410c',
    bg: '#fff7ed',
    border: '#fed7aa',
  },
  jeep: {
    label: 'Jeep',
    icon: CarFront,
    color: '#059669', // Emerald Green
    bg: '#ecfdf5',
    border: '#a7f3d0',
  },
  jeeps: {
    label: 'Jeeps',
    icon: CarFront,
    color: '#059669',
    bg: '#ecfdf5',
    border: '#a7f3d0',
  },
  suv: {
    label: 'SUV',
    icon: CarFront,
    color: '#059669',
    bg: '#ecfdf5',
    border: '#a7f3d0',
  },
  auto: {
    label: 'Auto',
    icon: Navigation,
    color: '#eab308', // Warm Gold / Yellow
    bg: '#fefce8',
    border: '#fef08a',
  },
  autos: {
    label: 'Autos',
    icon: Navigation,
    color: '#eab308',
    bg: '#fefce8',
    border: '#fef08a',
  },
  rickshaw: {
    label: 'Rickshaw',
    icon: Navigation,
    color: '#eab308',
    bg: '#fefce8',
    border: '#fef08a',
  },
  van: {
    label: 'Van',
    icon: Van,
    color: '#475569',
    bg: '#f8fafc',
    border: '#cbd5e1',
  },
  vans: {
    label: 'Vans',
    icon: Van,
    color: '#475569',
    bg: '#f8fafc',
    border: '#cbd5e1',
  },
  train: {
    label: 'Train',
    icon: Train,
    color: '#4338ca',
    bg: '#eef2ff',
    border: '#c7d2fe',
  },
  trains: {
    label: 'Trains',
    icon: Train,
    color: '#4338ca',
    bg: '#eef2ff',
    border: '#c7d2fe',
  },
  tram: {
    label: 'Tram',
    icon: TramFront,
    color: '#0f766e',
    bg: '#f0fdfa',
    border: '#99f6e4',
  },
  ambulance: {
    label: 'Ambulance',
    icon: Ambulance,
    color: '#e11d48',
    bg: '#fff1f2',
    border: '#fecdd3',
  },
  pedestrian: {
    label: 'Pedestrians',
    icon: Footprints,
    color: '#16a34a',
    bg: '#f0fdf4',
    border: '#bbf7d0',
  },
  pedestrians: {
    label: 'Pedestrians',
    icon: Footprints,
    color: '#16a34a',
    bg: '#f0fdf4',
    border: '#bbf7d0',
  },
  edisetrains: {
    label: 'Pedestrians',
    icon: Footprints,
    color: '#16a34a',
    bg: '#f0fdf4',
    border: '#bbf7d0',
  },
  edisetrain: {
    label: 'Pedestrians',
    icon: Footprints,
    color: '#16a34a',
    bg: '#f0fdf4',
    border: '#bbf7d0',
  },
}

export function getVehicleMeta(type) {
  if (!type) {
    return {
      label: 'Unknown',
      icon: Car,
      color: '#64748b',
      bg: '#f1f5f9',
      border: '#cbd5e1',
    }
  }

  const normalized = String(type).trim().toLowerCase()

  if (VEHICLE_CONFIGS[normalized]) {
    return { ...VEHICLE_CONFIGS[normalized] }
  }

  // Substring / partial matching
  if (normalized.includes('bike') || normalized.includes('cycle') || normalized.includes('scooter')) {
    return { ...VEHICLE_CONFIGS.bike }
  }
  if (normalized.includes('bus')) {
    return { ...VEHICLE_CONFIGS.bus }
  }
  if (normalized.includes('truck') || normalized.includes('lorry') || normalized.includes('trailer')) {
    return { ...VEHICLE_CONFIGS.truck }
  }
  if (normalized.includes('tractor') || normalized.includes('tractr')) {
    return { ...VEHICLE_CONFIGS.tractor }
  }
  if (normalized.includes('jeep') || normalized.includes('suv') || normalized.includes('4x4')) {
    return { ...VEHICLE_CONFIGS.jeep }
  }
  if (normalized.includes('auto') || normalized.includes('rickshaw')) {
    return { ...VEHICLE_CONFIGS.auto }
  }
  if (normalized.includes('van')) {
    return { ...VEHICLE_CONFIGS.van }
  }
  if (normalized.includes('train') || normalized.includes('rail') || normalized.includes('metro')) {
    return { ...VEHICLE_CONFIGS.train }
  }
  if (normalized.includes('tram')) {
    return { ...VEHICLE_CONFIGS.tram }
  }
  if (
    normalized.includes('pedestrian') ||
    normalized.includes('walk') ||
    normalized.includes('person') ||
    normalized.includes('edisetrain')
  ) {
    return { ...VEHICLE_CONFIGS.pedestrians }
  }
  if (normalized.includes('ambulance') || normalized.includes('emergency')) {
    return { ...VEHICLE_CONFIGS.ambulance }
  }
  if (normalized.includes('car')) {
    return { ...VEHICLE_CONFIGS.car }
  }

  // Fallback for custom vehicle
  return {
    label: type,
    icon: Car,
    color: '#334155',
    bg: '#f8fafc',
    border: '#e2e8f0',
  }
}

/**
 * Returns a standardized, single-word canonical domain name for any vehicle string.
 * Examples: 'sedan' -> 'Car', 'motorcycle' -> 'Bike', 'lorry' -> 'Truck', 'rickshaw' -> 'Auto'
 */
export function getCanonicalVehicleDomain(type) {
  if (!type) return 'Other'
  const normalized = String(type).trim().toLowerCase().replace(/[-_]/g, ' ')
  if (
    normalized.includes('bike') ||
    normalized.includes('cycle') ||
    normalized.includes('scooter') ||
    normalized.includes('two wheeler') ||
    normalized.includes('2 wheeler') ||
    normalized.includes('motorcycle') ||
    normalized.includes('motorbike') ||
    normalized.includes('moped')
  ) {
    return 'Bike'
  }
  if (normalized.includes('bus')) {
    return 'Bus'
  }
  if (
    normalized.includes('truck') ||
    normalized.includes('lorry') ||
    normalized.includes('trailer') ||
    normalized.includes('heavy') ||
    normalized.includes('dumper') ||
    normalized.includes('tipper')
  ) {
    return 'Truck'
  }
  if (normalized.includes('tractor') || normalized.includes('tractr')) {
    return 'Tractor'
  }
  if (normalized.includes('suv') || normalized === 'suv') {
    return 'SUV'
  }
  if (normalized.includes('jeep') || normalized.includes('4x4')) {
    return 'Jeep'
  }
  if (
    normalized.includes('auto') ||
    normalized.includes('rickshaw') ||
    normalized.includes('three wheeler') ||
    normalized.includes('3 wheeler')
  ) {
    return 'Auto'
  }
  if (normalized.includes('van')) {
    return 'Van'
  }
  if (normalized.includes('train') || normalized.includes('rail') || normalized.includes('metro') || normalized.includes('tram')) {
    return 'Train'
  }
  if (
    normalized.includes('pedestrian') ||
    normalized.includes('walk') ||
    normalized.includes('person') ||
    normalized.includes('people') ||
    normalized.includes('edisetrain')
  ) {
    return 'Pedestrian'
  }
  if (normalized.includes('ambulance') || normalized.includes('emergency')) {
    return 'Ambulance'
  }
  if (normalized.includes('car') || normalized === 'sedan' || normalized === 'hatchback') {
    return 'Car'
  }
  const meta = getVehicleMeta(type)
  return meta.label || String(type).trim()
}

/**
 * Checks if a row's vehicle type matches a requested filter type.
 * Supports canonical domains (e.g. 'motorcycle' matches 'Bike', 'two-wheeler' matches 'Bike', 'rickshaw' matches 'Auto'),
 * partial substring matches, plurals/singulars, and general aliases.
 */
export function isVehicleTypeMatch(rowType, targetType) {
  if (!targetType) return true
  if (!rowType) return false
  const target = String(targetType).trim().toLowerCase()
  if (target === 'all' || target === 'vehicle' || target === 'vehicles') return true

  const targetDomain = getCanonicalVehicleDomain(target)
  const rowDomain = getCanonicalVehicleDomain(rowType)

  if (targetDomain && rowDomain && targetDomain.toLowerCase() === rowDomain.toLowerCase()) {
    return true
  }

  const rNorm = String(rowType).trim().toLowerCase().replace(/[-_]/g, ' ')
  const tNorm = target.replace(/[-_]/g, ' ')
  if (rNorm.includes(tNorm) || tNorm.includes(rNorm)) return true

  // Singular / plural check
  const rSingular = rNorm.endsWith('s') && rNorm.length > 3 ? rNorm.slice(0, -1) : rNorm
  const tSingular = tNorm.endsWith('s') && tNorm.length > 3 ? tNorm.slice(0, -1) : tNorm
  if (rSingular === tSingular || rNorm.includes(tSingular) || tNorm.includes(rSingular)) return true

  return false
}

