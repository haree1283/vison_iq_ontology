import { BadgeCheck, BellRing, Mail, ShieldCheck, Sparkles, UserCircle } from 'lucide-react'
import { useAuth } from '../context/AuthContext'

export default function ProfilePage() {
  const { user } = useAuth()
  const initials = (user?.displayName || user?.username || 'VI').slice(0, 2).toUpperCase()

  return (
    <div className="account-page">
      <div className="page-intro">
        <div>
          <p className="section-kicker">ACCOUNT</p>
          <h1>Profile</h1>
          <p className="intro-copy">Your VisionIQ workspace identity, access, and operational preferences.</p>
        </div>
      </div>

      <section className="profile-hero">
        <div className="profile-avatar">{user?.profilePhoto ? <img alt="Profile" src={user.profilePhoto} /> : initials}</div>
        <div className="profile-identity">
          <p className="section-kicker">ACTIVE MEMBER</p>
          <h2>{user?.displayName || user?.username || 'VisionIQ user'}</h2>
          <p>{user?.jobTitle || 'VisionIQ operator'}</p>
          <span className="profile-badge"><BadgeCheck size={14} /> Verified operator</span>
        </div>
      </section>

      <section className="account-detail-grid">
        <div className="account-detail"><Mail size={19} /><span>Email</span><strong>{user?.email || 'Not provided'}</strong></div>
        <div className="account-detail"><UserCircle size={19} /><span>Username</span><strong>{user?.username || 'Not provided'}</strong></div>
        <div className="account-detail"><ShieldCheck size={19} /><span>Access level</span><strong>{user?.role || 'Operator'}</strong></div>
      </section>

      <section className="profile-panels">
        <div className="profile-panel">
          <div className="panel-heading compact">
            <div>
              <p className="section-kicker">WORKSPACE</p>
              <h3>Operational snapshot</h3>
            </div>
          </div>
          <div className="mini-stat-grid">
            <div>
              <strong>12</strong>
              <span>Active data sources</span>
            </div>
            <div>
              <strong>96.4%</strong>
              <span>Model health</span>
            </div>
            <div>
              <strong>15</strong>
              <span>Events today</span>
            </div>
          </div>
        </div>

        <div className="profile-panel">
          <div className="panel-heading compact">
            <div>
              <p className="section-kicker">PREFERENCES</p>
              <h3>Signal settings</h3>
            </div>
          </div>
          <ul className="feature-list">
            <li><Sparkles size={16} /> AI summaries enabled</li>
            <li><BellRing size={16} /> Live alerts enabled</li>
            <li><ShieldCheck size={16} /> Access controls active</li>
          </ul>
        </div>
      </section>
    </div>
  )
}