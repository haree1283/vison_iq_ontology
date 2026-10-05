import { useState, useMemo } from 'react'
import {
  AlertTriangle,
  ArrowRight,
  BookOpen,
  Building2,
  Calendar,
  Camera,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Copy,
  ExternalLink,
  Eye,
  FileCheck,
  FileCode,
  FileSpreadsheet,
  FileText,
  Filter,
  Flame,
  Gauge,
  HelpCircle,
  Info,
  Layers,
  MapPin,
  Maximize2,
  Minimize2,
  Network,
  Printer,
  Scale,
  Search,
  Shield,
  ShieldAlert,
  ShieldCheck,
  SlidersHorizontal,
  Sparkles,
  TrafficCone,
  X,
  Zap,
} from 'lucide-react'

import {
  GAZETTE_EVENTS_TIMELINE,
  KNOWLEDGE_BASE_META,
  KNOWLEDGE_TREE,
  OFFENCES_MATRIX,
  REGULATORY_EVENTS_FRAMEWORK,
  ROAD_SAFETY,
  TRAFFIC_INFRASTRUCTURE,
  TRAFFIC_OFFENCES_FRAMEWORK,
  TRAFFIC_RULES,
} from '../data/rulesEventsData'

export default function RulesEventsPage() {
  const [activeTab, setActiveTab] = useState('all') // 'all', 'rules', 'offences', 'infra', 'safety', 'events'
  const [searchQuery, setSearchQuery] = useState('')
  const [selectedSeverity, setSelectedSeverity] = useState('All')
  const [selectedCategory, setSelectedCategory] = useState('All')
  const [treeExpanded, setTreeExpanded] = useState(true)
  const [activeDetailItem, setActiveDetailItem] = useState(null)
  const [copiedNotification, setCopiedNotification] = useState('')

  // Filtered Traffic Rules
  const filteredRules = useMemo(() => {
    return TRAFFIC_RULES.filter((rule) => {
      const matchSearch =
        !searchQuery ||
        rule.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
        rule.statute.toLowerCase().includes(searchQuery.toLowerCase()) ||
        rule.applicableSection.toLowerCase().includes(searchQuery.toLowerCase()) ||
        rule.summary.toLowerCase().includes(searchQuery.toLowerCase()) ||
        rule.keyMandates.some((m) => m.toLowerCase().includes(searchQuery.toLowerCase()))
      return matchSearch
    })
  }, [searchQuery])

  // Filtered Offences Matrix
  const filteredOffences = useMemo(() => {
    return OFFENCES_MATRIX.filter((item) => {
      const matchSearch =
        !searchQuery ||
        item.violation.toLowerCase().includes(searchQuery.toLowerCase()) ||
        item.section.toLowerCase().includes(searchQuery.toLowerCase()) ||
        item.category.toLowerCase().includes(searchQuery.toLowerCase()) ||
        item.penalty1st.toLowerCase().includes(searchQuery.toLowerCase())

      const matchSeverity =
        selectedSeverity === 'All' || item.severity === selectedSeverity

      const matchCat =
        selectedCategory === 'All' || item.category === selectedCategory

      return matchSearch && matchSeverity && matchCat
    })
  }, [searchQuery, selectedSeverity, selectedCategory])

  // Filtered Infrastructure
  const filteredInfrastructure = useMemo(() => {
    return TRAFFIC_INFRASTRUCTURE.filter((item) => {
      return (
        !searchQuery ||
        item.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
        item.standard.toLowerCase().includes(searchQuery.toLowerCase()) ||
        item.summary.toLowerCase().includes(searchQuery.toLowerCase()) ||
        item.specifications.some((s) => s.toLowerCase().includes(searchQuery.toLowerCase()))
      )
    })
  }, [searchQuery])

  // Filtered Road Safety
  const filteredSafety = useMemo(() => {
    return ROAD_SAFETY.filter((item) => {
      return (
        !searchQuery ||
        item.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
        item.statute.toLowerCase().includes(searchQuery.toLowerCase()) ||
        item.summary.toLowerCase().includes(searchQuery.toLowerCase()) ||
        item.keyMandates.some((m) => m.toLowerCase().includes(searchQuery.toLowerCase()))
      )
    })
  }, [searchQuery])

  // Filtered Gazette Events
  const filteredEvents = useMemo(() => {
    return GAZETTE_EVENTS_TIMELINE.filter((ev) => {
      return (
        !searchQuery ||
        ev.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
        ev.gazetteNumber.toLowerCase().includes(searchQuery.toLowerCase()) ||
        ev.eventType.toLowerCase().includes(searchQuery.toLowerCase()) ||
        ev.summary.toLowerCase().includes(searchQuery.toLowerCase()) ||
        ev.impact.toLowerCase().includes(searchQuery.toLowerCase())
      )
    })
  }, [searchQuery])

  // Copy citation to clipboard
  function handleCopyCitation(text, id) {
    navigator.clipboard.writeText(text)
    setCopiedNotification(id)
    setTimeout(() => setCopiedNotification(''), 2500)
  }

  // Quick jump from Tree View
  function handleTreeJump(pillarId, subtopicId) {
    if (pillarId === 'traffic-rules') {
      setActiveTab('rules')
    } else if (pillarId === 'traffic-offences') {
      setActiveTab('offences')
    } else if (pillarId === 'traffic-infrastructure') {
      setActiveTab('infra')
    } else if (pillarId === 'road-safety') {
      setActiveTab('safety')
    } else if (pillarId === 'regulatory-events') {
      setActiveTab('events')
    }

    if (subtopicId) {
      // Find matching item and open details
      const foundRule = TRAFFIC_RULES.find((r) => r.id === subtopicId)
      if (foundRule) return setActiveDetailItem({ type: 'rule', data: foundRule })

      const foundInfra = TRAFFIC_INFRASTRUCTURE.find((i) => i.id === subtopicId)
      if (foundInfra) return setActiveDetailItem({ type: 'infra', data: foundInfra })

      const foundSafety = ROAD_SAFETY.find((s) => s.id === subtopicId)
      if (foundSafety) return setActiveDetailItem({ type: 'safety', data: foundSafety })

      const foundOffenceTopic = TRAFFIC_OFFENCES_FRAMEWORK.find((o) => o.id === subtopicId)
      if (foundOffenceTopic) return setActiveDetailItem({ type: 'offenceFramework', data: foundOffenceTopic })

      const foundEventTopic = REGULATORY_EVENTS_FRAMEWORK.find((e) => e.id === subtopicId)
      if (foundEventTopic) return setActiveDetailItem({ type: 'eventFramework', data: foundEventTopic })
    }
  }

  return (
    <div className="rules-events-container">
      {/* 1. HERO BANNER */}
      <header className="re-hero-banner">
        <div className="re-hero-main">
          <div className="re-hero-emblem-row">
            <span className="re-hero-seal-badge">
              <Scale size={14} /> CENTRAL GOVERNMENT STATUTORY REPOSITORY
            </span>
            <span className="re-hero-version-tag">
              {KNOWLEDGE_BASE_META.version} • {KNOWLEDGE_BASE_META.jurisdiction}
            </span>
          </div>
          <h1 className="re-hero-title">Central Government Traffic Knowledge Base</h1>
          <p className="re-hero-description">
            Statutory codification of vehicular conduct rules, penal offences, civil infrastructure engineering standards, 
            occupant safety requirements, and gazetted regulatory lifecycle events under the{' '}
            <strong>Motor Vehicles Act 1988 (Amended 2019)</strong>, <strong>CMVR 1989</strong>, and Indian Road Congress (IRC) specifications.
          </p>
        </div>

        {/* Quick KPI stats */}
        <div className="re-hero-stats">
          <div className="re-stat-card">
            <div className="re-stat-icon-wrap icon-blue">
              <Layers size={18} />
            </div>
            <div className="re-stat-info">
              <span className="re-stat-num">{KNOWLEDGE_BASE_META.pillarsCount}</span>
              <span className="re-stat-label">Knowledge Pillars</span>
            </div>
          </div>

          <div className="re-stat-card">
            <div className="re-stat-icon-wrap icon-emerald">
              <BookOpen size={18} />
            </div>
            <div className="re-stat-info">
              <span className="re-stat-num">{KNOWLEDGE_BASE_META.topicsCount}</span>
              <span className="re-stat-label">Codified Topics</span>
            </div>
          </div>

          <div className="re-stat-card">
            <div className="re-stat-icon-wrap icon-amber">
              <AlertTriangle size={18} />
            </div>
            <div className="re-stat-info">
              <span className="re-stat-num">{OFFENCES_MATRIX.length}+</span>
              <span className="re-stat-label">Offence Penalties</span>
            </div>
          </div>

          <div className="re-stat-card">
            <div className="re-stat-icon-wrap icon-violet">
              <FileCheck size={18} />
            </div>
            <div className="re-stat-info">
              <span className="re-stat-num">{GAZETTE_EVENTS_TIMELINE.length}</span>
              <span className="re-stat-label">Gazette Enactments</span>
            </div>
          </div>
        </div>
      </header>

      {/* 2. CONTROLS BAR: SEARCH, PILLAR SELECTOR & TREE TOGGLE */}
      <div className="re-controls-sticky">
        <div className="re-search-input-wrap">
          <Search className="re-search-icon" size={16} />
          <input
            className="re-search-input"
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search rules, Section numbers (e.g. 184, 112, 194E), penalties, IRC codes..."
            type="text"
            value={searchQuery}
          />
          {searchQuery && (
            <button
              className="re-search-clear"
              onClick={() => setSearchQuery('')}
              type="button"
            >
              <X size={14} />
            </button>
          )}
        </div>

        {/* Tabs */}
        <div className="re-tabs-group">
          <button
            className={`re-tab-btn ${activeTab === 'all' ? 'active' : ''}`}
            onClick={() => setActiveTab('all')}
            type="button"
          >
            <Sparkles size={14} /> All Pillars (Overview)
          </button>
          <button
            className={`re-tab-btn ${activeTab === 'rules' ? 'active' : ''}`}
            onClick={() => setActiveTab('rules')}
            type="button"
          >
            <BookOpen size={14} /> Traffic Rules ({TRAFFIC_RULES.length})
          </button>
          <button
            className={`re-tab-btn ${activeTab === 'offences' ? 'active' : ''}`}
            onClick={() => setActiveTab('offences')}
            type="button"
          >
            <AlertTriangle size={14} /> Traffic Offences ({OFFENCES_MATRIX.length})
          </button>
          <button
            className={`re-tab-btn ${activeTab === 'infra' ? 'active' : ''}`}
            onClick={() => setActiveTab('infra')}
            type="button"
          >
            <Building2 size={14} /> Infrastructure ({TRAFFIC_INFRASTRUCTURE.length})
          </button>
          <button
            className={`re-tab-btn ${activeTab === 'safety' ? 'active' : ''}`}
            onClick={() => setActiveTab('safety')}
            type="button"
          >
            <ShieldCheck size={14} /> Road Safety ({ROAD_SAFETY.length})
          </button>
          <button
            className={`re-tab-btn ${activeTab === 'events' ? 'active' : ''}`}
            onClick={() => setActiveTab('events')}
            type="button"
          >
            <FileText size={14} /> Regulatory Events ({GAZETTE_EVENTS_TIMELINE.length})
          </button>
        </div>

        {/* Tree Explorer Toggle */}
        <button
          className={`re-tree-toggle-btn ${treeExpanded ? 'active' : ''}`}
          onClick={() => setTreeExpanded(!treeExpanded)}
          title="Toggle Statutory Hierarchy Tree"
          type="button"
        >
          <Network size={15} />
          <span>Hierarchy Tree</span>
          <ChevronDown
            className={`re-tree-chevron ${treeExpanded ? 'expanded' : ''}`}
            size={14}
          />
        </button>
      </div>

      {/* 3. INTERACTIVE STATUTORY HIERARCHY TREE (COLLAPSIBLE) */}
      {treeExpanded && (
        <section className="re-hierarchy-tree-panel">
          <div className="re-tree-header">
            <div>
              <span className="re-tree-badge">STATUTORY ARCHITECTURE</span>
              <h3>Central Government Traffic Knowledge Base — Complete Hierarchy</h3>
            </div>
            <p className="re-tree-help">
              Click on any subtopic node below to inspect legal sections, penalties, or IRC parameters directly.
            </p>
          </div>

          <div className="re-tree-grid">
            {KNOWLEDGE_TREE.children.map((pillar) => (
              <div className="re-tree-pillar-card" key={pillar.id}>
                <div
                  className="re-tree-pillar-top"
                  onClick={() => handleTreeJump(pillar.id)}
                >
                  <div className="re-tree-pillar-title-group">
                    <span className="re-tree-code-chip">{pillar.count} Topics</span>
                    <h4>{pillar.name}</h4>
                  </div>
                  <ChevronRight size={16} />
                </div>
                <p className="re-tree-pillar-desc">{pillar.description}</p>
                <div className="re-tree-leaves-list">
                  {pillar.children.map((leaf) => (
                    <button
                      className="re-tree-leaf-item"
                      key={leaf.id}
                      onClick={() => handleTreeJump(pillar.id, leaf.id)}
                      type="button"
                    >
                      <span className="re-leaf-bullet">●</span>
                      <span className="re-leaf-name">{leaf.name}</span>
                      <span className="re-leaf-code">{leaf.code}</span>
                    </button>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* COPY NOTIFICATION TOAST */}
      {copiedNotification && (
        <div className="re-toast-notification">
          <CheckCircle2 size={16} /> Legal citation copied to clipboard!
        </div>
      )}

      {/* 4. CONTENT SECTIONS */}

      {/* PILLAR 1: TRAFFIC RULES (14 SUBTOPICS) */}
      {(activeTab === 'all' || activeTab === 'rules') && (
        <section className="re-section-block" id="traffic-rules-section">
          <div className="re-section-header">
            <div className="re-section-title-wrap">
              <span className="re-section-category-tag">PILLAR 1 OF 5 • STATUTORY CONDUCT</span>
              <h2>Traffic Rules</h2>
              <p>
                14 fundamental vehicular conduct mandates governed by the Motor Vehicles Act 1988 (Sections 112–134) 
                and Motor Vehicles (Driving) Regulations 2017.
              </p>
            </div>
            <span className="re-count-indicator">
              Showing {filteredRules.length} of {TRAFFIC_RULES.length} Rules
            </span>
          </div>

          <div className="re-rules-grid">
            {filteredRules.map((rule) => (
              <article className="re-rule-card" key={rule.id}>
                <div className="re-rule-card-header">
                  <div className="re-rule-card-meta">
                    <span className="re-code-tag">{rule.code}</span>
                    <span className={`re-severity-tag severity-${rule.severity.toLowerCase().replace(/[^a-z]/g, '')}`}>
                      {rule.severity} Priority
                    </span>
                  </div>
                  <button
                    className="re-card-action-btn"
                    onClick={() => setActiveDetailItem({ type: 'rule', data: rule })}
                    title="View Full Legal Analysis"
                    type="button"
                  >
                    <Maximize2 size={15} />
                  </button>
                </div>

                <h3 className="re-rule-title">{rule.name}</h3>
                <div className="re-rule-statute">
                  <Scale size={13} />
                  <span>{rule.statute}</span>
                </div>

                <p className="re-rule-summary">{rule.summary}</p>

                <div className="re-rule-mandates-box">
                  <span className="re-box-subtitle">KEY STATUTORY MANDATES</span>
                  <ul className="re-mandates-list">
                    {rule.keyMandates.slice(0, 3).map((mandate, idx) => (
                      <li key={idx}>
                        <CheckCircle2 className="re-bullet-icon" size={13} />
                        <span>{mandate}</span>
                      </li>
                    ))}
                  </ul>
                  {rule.keyMandates.length > 3 && (
                    <button
                      className="re-see-more-link"
                      onClick={() => setActiveDetailItem({ type: 'rule', data: rule })}
                      type="button"
                    >
                      + {rule.keyMandates.length - 3} more statutory provisions
                    </button>
                  )}
                </div>

                <div className="re-rule-penal-row">
                  <div className="re-penal-pill">
                    <span className="re-penal-label">Applicable Section:</span>
                    <strong>{rule.applicableSection}</strong>
                  </div>
                </div>
              </article>
            ))}
          </div>
        </section>
      )}

      {/* PILLAR 2: TRAFFIC OFFENCES (4 SUBTOPICS + PENAL MATRIX) */}
      {(activeTab === 'all' || activeTab === 'offences') && (
        <section className="re-section-block" id="traffic-offences-section">
          <div className="re-section-header">
            <div className="re-section-title-wrap">
              <span className="re-section-category-tag">PILLAR 2 OF 5 • ENFORCEMENT & ADJUDICATION</span>
              <h2>Traffic Offences</h2>
              <p>
                Codified framework covering <strong>Violation taxonomy</strong>, <strong>Applicable sections</strong>,{' '}
                <strong>Compounding & Judicial Penalties</strong>, and <strong>Multi-tier Electronic Enforcement</strong>.
              </p>
            </div>
            <span className="re-count-indicator">
              {filteredOffences.length} Offences Indexed
            </span>
          </div>

          {/* 4 Framework Pillars */}
          <div className="re-offence-framework-grid">
            {TRAFFIC_OFFENCES_FRAMEWORK.map((item) => (
              <div className="re-framework-card" key={item.id}>
                <div className="re-framework-header">
                  <span className="re-code-tag">{item.code}</span>
                  <h4>{item.name}</h4>
                </div>
                <p className="re-framework-desc">{item.description}</p>
                <ul className="re-framework-list">
                  {item.keyMandates.map((pt, idx) => (
                    <li key={idx}>
                      <ChevronRight size={12} />
                      <span>{pt}</span>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>

          {/* Search & Filter Toolbar for Matrix */}
          <div className="re-matrix-toolbar">
            <div className="re-matrix-toolbar-title">
              <AlertTriangle size={17} />
              <h3>Statutory Offences & Penalties Matrix (MV Amendment Act 2019)</h3>
            </div>

            <div className="re-matrix-filters">
              <div className="re-filter-item">
                <label>Severity:</label>
                <select
                  onChange={(e) => setSelectedSeverity(e.target.value)}
                  value={selectedSeverity}
                >
                  <option value="All">All Severities</option>
                  <option value="Critical">Critical</option>
                  <option value="Major">Major</option>
                  <option value="Moderate">Moderate</option>
                </select>
              </div>

              <div className="re-filter-item">
                <label>Category:</label>
                <select
                  onChange={(e) => setSelectedCategory(e.target.value)}
                  value={selectedCategory}
                >
                  <option value="All">All Categories</option>
                  <option value="Speed & Motion">Speed & Motion</option>
                  <option value="Driver Conduct">Driver Conduct</option>
                  <option value="Driver Fitness">Driver Fitness</option>
                  <option value="Public Safety">Public Safety</option>
                  <option value="Protective Gear">Protective Gear</option>
                  <option value="Commercial Cargo">Commercial Cargo</option>
                  <option value="Licensing & Custody">Licensing & Custody</option>
                </select>
              </div>
            </div>
          </div>

          {/* Offences Table */}
          <div className="re-table-wrapper">
            <table className="re-offence-table">
              <thead>
                <tr>
                  <th>VIOLATION</th>
                  <th>APPLICABLE SECTION</th>
                  <th>CATEGORY</th>
                  <th>1ST OFFENCE PENALTY</th>
                  <th>REPEAT OFFENCE PENALTY</th>
                  <th>STATUS</th>
                  <th>ENFORCEMENT MODE</th>
                </tr>
              </thead>
              <tbody>
                {filteredOffences.map((off, idx) => (
                  <tr key={idx}>
                    <td>
                      <div className="re-violation-cell">
                        <strong>{off.violation}</strong>
                        <span className={`re-table-severity severity-${off.severity.toLowerCase()}`}>
                          {off.severity}
                        </span>
                      </div>
                    </td>
                    <td>
                      <code className="re-section-code">{off.section}</code>
                    </td>
                    <td>
                      <span className="re-category-tag">{off.category}</span>
                    </td>
                    <td>
                      <div className="re-penalty-val">{off.penalty1st}</div>
                    </td>
                    <td>
                      <div className="re-repeat-val">{off.penaltyRepeat}</div>
                    </td>
                    <td>
                      <span className={`re-compound-badge ${off.compoundable ? 'compoundable' : 'court-only'}`}>
                        {off.compoundable ? 'Compoundable' : 'Court Trial'}
                      </span>
                    </td>
                    <td>
                      <div className="re-enforce-mode">
                        <Camera size={13} />
                        <span>{off.enforcementMode}</span>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {/* PILLAR 3: TRAFFIC INFRASTRUCTURE (4 SUBTOPICS) */}
      {(activeTab === 'all' || activeTab === 'infra') && (
        <section className="re-section-block" id="traffic-infra-section">
          <div className="re-section-header">
            <div className="re-section-title-wrap">
              <span className="re-section-category-tag">PILLAR 3 OF 5 • PHYSICAL & ELECTRONIC ASSETS</span>
              <h2>Traffic Infrastructure</h2>
              <p>
                Engineering benchmarks, signage legibility, adaptive signals (ATCS), parking geometric design, 
                and road markings per <strong>Indian Road Congress (IRC)</strong> standards.
              </p>
            </div>
            <span className="re-count-indicator">
              {filteredInfrastructure.length} Standards Codified
            </span>
          </div>

          <div className="re-infra-grid">
            {filteredInfrastructure.map((infra) => (
              <article className="re-infra-card" key={infra.id}>
                <div className="re-infra-card-header">
                  <span className="re-code-tag">{infra.code}</span>
                  <span className="re-standard-pill">{infra.standard}</span>
                </div>

                <h3 className="re-infra-title">{infra.name}</h3>
                <p className="re-infra-summary">{infra.summary}</p>

                <div className="re-specs-block">
                  <span className="re-box-subtitle">ENGINEERING & DEPLOYMENT SPECIFICATIONS</span>
                  <ul className="re-specs-list">
                    {infra.specifications.map((spec, sIdx) => (
                      <li key={sIdx}>
                        <CheckCircle2 className="re-bullet-icon" size={13} />
                        <span>{spec}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              </article>
            ))}
          </div>
        </section>
      )}

      {/* PILLAR 4: ROAD SAFETY (3 SUBTOPICS) */}
      {(activeTab === 'all' || activeTab === 'safety') && (
        <section className="re-section-block" id="road-safety-section">
          <div className="re-section-header">
            <div className="re-section-title-wrap">
              <span className="re-section-category-tag">PILLAR 4 OF 5 • SYSTEMIC ACCIDENT PREVENTION</span>
              <h2>Road Safety</h2>
              <p>
                Vehicle crashworthiness benchmarks (Bharat NCAP), Section 136A electronic enforcement statutory guidelines, 
                and MoRTH 500-meter Accident Black Spot remediation protocols.
              </p>
            </div>
            <span className="re-count-indicator">
              {filteredSafety.length} Safety Frameworks
            </span>
          </div>

          <div className="re-safety-grid">
            {filteredSafety.map((safety) => (
              <article className="re-safety-card" key={safety.id}>
                <div className="re-safety-card-header">
                  <span className="re-code-tag">{safety.code}</span>
                  <span className="re-safety-badge">
                    <ShieldCheck size={14} /> Statutory Mandate
                  </span>
                </div>

                <h3 className="re-safety-title">{safety.name}</h3>
                <div className="re-rule-statute">
                  <Scale size={13} />
                  <span>{safety.statute}</span>
                </div>

                <p className="re-safety-summary">{safety.summary}</p>

                <div className="re-safety-mandates-block">
                  <span className="re-box-subtitle">OPERATIONAL REQUIREMENTS</span>
                  <ul className="re-specs-list">
                    {safety.keyMandates.map((m, mIdx) => (
                      <li key={mIdx}>
                        <CheckCircle2 className="re-bullet-icon" size={13} />
                        <span>{m}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              </article>
            ))}
          </div>
        </section>
      )}

      {/* PILLAR 5: GOVERNMENT REGULATORY EVENTS (6 SUBTOPICS + GAZETTE TIMELINE) */}
      {(activeTab === 'all' || activeTab === 'events') && (
        <section className="re-section-block" id="regulatory-events-section">
          <div className="re-section-header">
            <div className="re-section-title-wrap">
              <span className="re-section-category-tag">PILLAR 5 OF 5 • GAZETTE REGULATORY LIFECYCLE</span>
              <h2>Government Regulatory Events</h2>
              <p>
                The complete statutory lifecycle of traffic governance in India: from initial draft gazette publication 
                to final parliamentary notifications, phased commencement, and rule repeals.
              </p>
            </div>
            <span className="re-count-indicator">
              {filteredEvents.length} Gazette Orders Tracked
            </span>
          </div>

          {/* 6 Lifecycle Steps */}
          <div className="re-events-lifecycle-grid">
            {REGULATORY_EVENTS_FRAMEWORK.map((stage) => (
              <div className="re-lifecycle-card" key={stage.id}>
                <div className="re-lifecycle-header">
                  <span className="re-code-tag">{stage.code}</span>
                  <h4>{stage.name}</h4>
                </div>
                <p className="re-lifecycle-desc">{stage.description}</p>
                <div className="re-lifecycle-flow">
                  <span className="re-box-subtitle">STATUTORY WORKFLOW</span>
                  <p>{stage.processFlow}</p>
                </div>
                <div className="re-lifecycle-power">
                  <strong>Power:</strong> <span>{stage.statutoryPower}</span>
                </div>
              </div>
            ))}
          </div>

          {/* Gazette Timeline Feed */}
          <div className="re-timeline-section">
            <div className="re-timeline-heading">
              <Calendar size={18} />
              <h3>Official Gazette of India Regulatory Tracker (MoRTH Notifications)</h3>
            </div>

            <div className="re-timeline-feed">
              {filteredEvents.map((ev) => (
                <div className="re-timeline-item" key={ev.id}>
                  <div className="re-timeline-marker">
                    <span className="re-marker-dot" />
                    <span className="re-marker-line" />
                  </div>

                  <div className="re-timeline-card">
                    <div className="re-timeline-card-header">
                      <div className="re-timeline-meta">
                        <span className="re-event-type-badge">{ev.eventType}</span>
                        <code className="re-gazette-num">{ev.gazetteNumber}</code>
                        <span className="re-gazette-date">Notified: {ev.date}</span>
                        <span className="re-effective-date">Effective: {ev.effectiveDate}</span>
                      </div>
                      <span className={`re-event-status ${ev.status.includes('Full') ? 'active' : 'pending'}`}>
                        {ev.status}
                      </span>
                    </div>

                    <h4 className="re-timeline-title">{ev.title}</h4>
                    <p className="re-timeline-ministry">Authority: {ev.ministry} • Category: {ev.category}</p>
                    <p className="re-timeline-summary">{ev.summary}</p>

                    <div className="re-timeline-impact">
                      <strong>Statutory Impact:</strong> <span>{ev.impact}</span>
                    </div>

                    <div className="re-timeline-actions">
                      <button
                        className="re-copy-btn"
                        onClick={() => handleCopyCitation(`${ev.title} [${ev.gazetteNumber}, dt. ${ev.date}]`, ev.id)}
                        type="button"
                      >
                        <Copy size={13} /> Copy Gazette Citation
                      </button>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </section>
      )}

      {/* 5. MODAL / DRAWER FOR DETAILED INSPECTION */}
      {activeDetailItem && (
        <div className="re-modal-overlay" onClick={() => setActiveDetailItem(null)}>
          <div className="re-modal-content" onClick={(e) => e.stopPropagation()}>
            <div className="re-modal-header">
              <div className="re-modal-title-group">
                <span className="re-code-tag">{activeDetailItem.data.code}</span>
                <h3>{activeDetailItem.data.name}</h3>
              </div>
              <button
                className="re-modal-close"
                onClick={() => setActiveDetailItem(null)}
                type="button"
              >
                <X size={18} />
              </button>
            </div>

            <div className="re-modal-body">
              {activeDetailItem.data.statute && (
                <div className="re-modal-statute">
                  <Scale size={15} />
                  <strong>Statutory Reference:</strong> {activeDetailItem.data.statute}
                </div>
              )}

              {activeDetailItem.data.applicableSection && (
                <div className="re-modal-field">
                  <strong>Applicable Section:</strong> {activeDetailItem.data.applicableSection}
                </div>
              )}

              {activeDetailItem.data.penaltyRange && (
                <div className="re-modal-field">
                  <strong>Statutory Penalty Range:</strong> {activeDetailItem.data.penaltyRange}
                </div>
              )}

              <p className="re-modal-summary">{activeDetailItem.data.summary || activeDetailItem.data.description}</p>

              {activeDetailItem.data.keyMandates && (
                <div className="re-modal-list-section">
                  <h4>All Codified Provisions & Mandates</h4>
                  <ul>
                    {activeDetailItem.data.keyMandates.map((m, i) => (
                      <li key={i}>{m}</li>
                    ))}
                  </ul>
                </div>
              )}

              {activeDetailItem.data.specifications && (
                <div className="re-modal-list-section">
                  <h4>Standard Specifications & Engineering Norms</h4>
                  <ul>
                    {activeDetailItem.data.specifications.map((s, i) => (
                      <li key={i}>{s}</li>
                    ))}
                  </ul>
                </div>
              )}
            </div>

            <div className="re-modal-footer">
              <button
                className="re-modal-action-btn"
                onClick={() => {
                  window.print()
                }}
                type="button"
              >
                <Printer size={14} /> Print Legal Dossier
              </button>
              <button
                className="re-modal-primary-btn"
                onClick={() => setActiveDetailItem(null)}
                type="button"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
