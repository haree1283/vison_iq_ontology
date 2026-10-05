import { useEffect, useRef } from 'react'
import cytoscape from 'cytoscape'
import { categoryColor } from '../../data/ontologyData'

export default function OntologyGraph({
  nodes,
  relationships,
  selectedNode,
  searchTerm,
  onNodeSelect,
  onReady,
}) {
  const containerRef = useRef(null)
  const cyRef = useRef(null)

  useEffect(() => {
    if (!containerRef.current) return

    const elements = [
      ...nodes.map((node) => ({
        data: {
          id: node.id,
          label: node.label,
          category: node.category,
        },
      })),

      ...relationships.map((relationship) => ({
        data: {
          id: relationship.id,
          source: relationship.source,
          target: relationship.target,
          label: relationship.label,
        },
      })),
    ]

    const cy = cytoscape({
      container: containerRef.current,

      elements,

      minZoom: 0.08,
      maxZoom: 4,

      wheelSensitivity: 0.18,

      layout: {
        name: 'cose',
        animate: false,
        fit: true,
        padding: 60,
        nodeRepulsion: 9000,
        idealEdgeLength: 150,
        gravity: 0.3,
        numIter: 1000,
      },

      style: [
        {
          selector: 'node',
          style: {
            width: 42,
            height: 42,
            label: 'data(label)',
            'background-color': '#94a3b8',
            color: '#1e293b',
            'font-size': 11,
            'font-weight': 600,
            'text-valign': 'center',
            'text-halign': 'center',
            'text-wrap': 'wrap',
            'text-max-width': 100,
            'border-width': 2,
            'border-color': '#ffffff',
            'overlay-opacity': 0,
            'min-zoomed-font-size': 8,
          },
        },

        ...Object.entries(categoryColor).map(([category, color]) => ({
          selector: `node[category = "${category}"]`,
          style: { 'background-color': color },
        })),

        {
          selector: 'node[category = "Vehicle"]',
          style: { width: 54, height: 54, 'font-size': 12, 'font-weight': 800, shape: 'round-rectangle' },
        },

        {
          selector: 'node[category = "Report"]',
          style: { shape: 'round-rectangle', color: '#ffffff' },
        },

        {
          selector: 'node[category = "Ontology"]',
          style: { width: 64, height: 64 },
        },

        {
          selector: 'edge',
          style: {
            width: 1,
            'line-color': '#b7c0ca',
            'target-arrow-color': '#94a3b8',
            'target-arrow-shape': 'triangle',
            'curve-style': 'bezier',
            label: 'data(label)',
            color: '#64748b',
            'font-size': 8,
            'text-rotation': 'autorotate',
            'text-background-color': '#ffffff',
            'text-background-opacity': 0.8,
            'text-background-padding': 2,
            'min-zoomed-font-size': 7,
          },
        },

        {
          selector: 'node:selected',
          style: {
            'border-width': 5,
            'border-color': '#2563eb',
            'overlay-color': '#2563eb',
            'overlay-opacity': 0.12,
          },
        },

        {
          selector: '.search-match',
          style: {
            'border-width': 5,
            'border-color': '#f59e0b',
            'overlay-color': '#f59e0b',
            'overlay-opacity': 0.15,
          },
        },

        {
          selector: '.dimmed',
          style: {
            opacity: 0.16,
          },
        },

        {
          selector: '.highlight-edge',
          style: {
            width: 3,
            'line-color': '#2563eb',
            'target-arrow-color': '#2563eb',
            opacity: 1,
          },
        },
      ],
    })

    cyRef.current = cy

    cy.on('tap', 'node', (event) => {
      const nodeId = event.target.id()
      onNodeSelect(nodeId)
    })

    cy.on('mouseover', 'node', (event) => {
      event.target.style('border-width', 4)
    })

    cy.on('mouseout', 'node', (event) => {
      if (!event.target.selected()) {
        event.target.style('border-width', 2)
      }
    })

    if (onReady) {
      onReady({
        zoomIn: () => {
          cy.zoom({
            level: Math.min(cy.zoom() * 1.35, cy.maxZoom()),
            renderedPosition: {
              x: cy.width() / 2,
              y: cy.height() / 2,
            },
          })
        },

        zoomOut: () => {
          cy.zoom({
            level: Math.max(cy.zoom() / 1.35, cy.minZoom()),
            renderedPosition: {
              x: cy.width() / 2,
              y: cy.height() / 2,
            },
          })
        },

        fit: () => {
          cy.fit(undefined, 70)
        },

        relayout: () => {
          cy.layout({
            name: 'cose',
            animate: true,
            animationDuration: 600,
            padding: 70,
            nodeRepulsion: 9000,
            idealEdgeLength: 150,
            gravity: 0.3,
            numIter: 1000,
          }).run()
        },
      })
    }

    return () => {
      cy.destroy()
      cyRef.current = null
    }
  }, [])

  useEffect(() => {
    const cy = cyRef.current

    if (!cy) return

    cy.nodes().removeClass('search-match')
    cy.nodes().removeClass('dimmed')

    const term = searchTerm.trim().toLowerCase()

    if (!term) return

    const matches = cy.nodes().filter((node) => {
      const label = String(node.data('label') || '').toLowerCase()
      const category = String(node.data('category') || '').toLowerCase()

      return (
        label.includes(term) ||
        category.includes(term)
      )
    })

    cy.nodes().addClass('dimmed')
    matches.removeClass('dimmed')
    matches.addClass('search-match')

    if (matches.length > 0) {
      cy.animate({
        fit: {
          eles: matches,
          padding: 120,
        },
        duration: 500,
      })
    }
  }, [searchTerm])

  useEffect(() => {
    const cy = cyRef.current

    if (!cy) return

    cy.nodes().unselect()
    cy.edges().removeClass('highlight-edge')

    if (!selectedNode) return

    const node = cy.getElementById(selectedNode)

    if (node.length === 0) return

    node.select()

    node.connectedEdges().addClass('highlight-edge')

    cy.animate({
      center: {
        eles: node,
      },
      duration: 450,
    })
  }, [selectedNode])

  return (
    <div
      ref={containerRef}
      className="ontology-graph-canvas"
    />
  )
}