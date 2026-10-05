import { useMemo, useState } from 'react'
import { Search, SlidersHorizontal } from 'lucide-react'
import { categoryColor, categoryLabel } from '../../data/ontologyData'

export default function OntologySidebar({
  nodes,
  relationships,
  activeCategory,
  setActiveCategory,
  selectedNode,
  setSelectedNode,
}) {
  const [tab, setTab] = useState('nodes')
  const [categorySearch, setCategorySearch] = useState('')

  const categories = useMemo(() => {
    const counts = {}

    nodes.forEach((node) => {
      counts[node.category] =
        (counts[node.category] || 0) + 1
    })

    return Object.entries(counts)
      .map(([name, count]) => ({
        name,
        count,
      }))
      .sort((a, b) => b.count - a.count)
  }, [nodes])

  const filteredCategories = categories.filter(
    (category) =>
      category.name
        .toLowerCase()
        .includes(categorySearch.toLowerCase())
  )

  return (
    <aside className="ontology-sidebar">
      <div className="ontology-sidebar-tabs">
        <button
          className={tab === 'nodes' ? 'active' : ''}
          onClick={() => setTab('nodes')}
        >
          Nodes
        </button>

        <button
          className={tab === 'relationships' ? 'active' : ''}
          onClick={() => setTab('relationships')}
        >
          Relationships
        </button>
      </div>

      {tab === 'nodes' ? (
        <>
          <div className="ontology-filter-box">
            <Search size={15} />

            <input
              value={categorySearch}
              onChange={(event) =>
                setCategorySearch(event.target.value)
              }
              placeholder="Filter categories"
            />
          </div>

          <div className="ontology-radio-row">
            <label>
              <input
                type="radio"
                checked={!activeCategory}
                onChange={() => setActiveCategory('')}
              />
              All
            </label>

            <label>
              <input
                type="radio"
                checked={Boolean(activeCategory)}
                onChange={() => {}}
              />
              Filtered
            </label>
          </div>

          <div className="ontology-category-list">
            {filteredCategories.map((category) => (
              <button
                key={category.name}
                className={`ontology-category ${
                  activeCategory === category.name
                    ? 'selected'
                    : ''
                }`}
                onClick={() => {
                  setActiveCategory(
                    activeCategory === category.name
                      ? ''
                      : category.name
                  )
                }}
              >
                <span
                  className="ontology-category-dot"
                  data-category={category.name}
                  style={{ background: categoryColor[category.name] }}
                />

                <span className="ontology-category-name">
                  {categoryLabel[category.name] || category.name}
                </span>

                <span className="ontology-category-count">
                  {category.count}
                </span>
              </button>
            ))}
          </div>
        </>
      ) : (
        <div className="ontology-relations-panel">
          <div className="ontology-relation-total">
            <SlidersHorizontal size={16} />

            <span>
              {relationships.length} relationships
            </span>
          </div>

          <div className="ontology-relation-list">
            {relationships.map((relationship) => (
              <button
                key={relationship.id}
                className="ontology-relation-item"
                onClick={() =>
                  setSelectedNode(relationship.source)
                }
              >
                <strong>{relationship.label}</strong>

                <span>
                  {relationship.source}
                  {' → '}
                  {relationship.target}
                </span>
              </button>
            ))}
          </div>
        </div>
      )}
    </aside>
  )
}