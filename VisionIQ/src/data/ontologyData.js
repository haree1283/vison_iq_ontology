// src/data/ontologyData.js
// Node categories of the ontology built from the processed videos' Excel reports (backend /api/ontology/graph).

export const ontologyCategories = [
  { name: 'Ontology', label: 'Ontology', color: '#53b9d7' },
  { name: 'OntologyClass', label: 'Classes', color: '#a878d4' },
  { name: 'Vehicle', label: 'Vehicles (unique plates)', color: '#e0932f' },
  { name: 'VehicleGroup', label: 'Vehicles, plate not read', color: '#c7b79a' },
  { name: 'Video', label: 'Videos', color: '#3d9953' },
  { name: 'Camera', label: 'Cameras', color: '#4f82c4' },
  { name: 'Report', label: 'Excel reports', color: '#217346' },
  { name: 'Event', label: 'Events', color: '#cb5e48' },
]

export const categoryColor = Object.fromEntries(ontologyCategories.map((c) => [c.name, c.color]))
export const categoryLabel = Object.fromEntries(ontologyCategories.map((c) => [c.name, c.label]))
