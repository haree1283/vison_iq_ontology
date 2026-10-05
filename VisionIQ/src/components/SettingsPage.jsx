import { Bell, Camera, Save, ShieldCheck } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useAuth } from '../context/AuthContext'

export default function SettingsPage({
  notificationSoundEnabled = true,
  setNotificationSoundEnabled = () => {},
}) {
  const { user, updateProfile } = useAuth()
  const [form, setForm] = useState({ displayName: '', username: '', jobTitle: '', phone: '', location: '' })
  const [saved, setSaved] = useState(false)

  useEffect(() => {
    setForm({
      displayName: user?.displayName || user?.username || '',
      username: user?.username || '',
      jobTitle: user?.jobTitle || '',
      phone: user?.phone || '',
      location: user?.location || '',
    })
  }, [user])

  function updateField(event) {
    setForm((current) => ({ ...current, [event.target.name]: event.target.value }))
    setSaved(false)
  }

  function handlePhoto(event) {
    const [file] = event.target.files || []
    if (!file) return
    const reader = new FileReader()
    reader.onload = () => updateProfile({ profilePhoto: reader.result })
    reader.readAsDataURL(file)
  }

  function handleSubmit(event) {
    event.preventDefault()
    updateProfile(form)
    setSaved(true)
  }

  return (
    <div className="account-page">
      <div className="page-intro">
        <div>
          <p className="section-kicker">ACCOUNT</p>
          <h1>Settings</h1>
          <p className="intro-copy">Keep your profile details, alerts, and workspace behavior aligned with your team.</p>
        </div>
      </div>

      <div className="settings-shell">
        <form className="settings-panel" onSubmit={handleSubmit}>
          <div className="settings-panel-heading">
            <div>
              <p className="section-kicker">PERSONAL DETAILS</p>
              <h2>Profile information</h2>
            </div>
            <label className="photo-upload">
              <Camera size={17} />
              <span>Change photo</span>
              <input accept="image/*" onChange={handlePhoto} type="file" />
            </label>
          </div>

          <div className="settings-form-grid">
            <label>Display name<input name="displayName" onChange={updateField} value={form.displayName} /></label>
            <label>Username<input name="username" onChange={updateField} value={form.username} /></label>
            <label>Job title<input name="jobTitle" onChange={updateField} placeholder="e.g. Traffic operations lead" value={form.jobTitle} /></label>
            <label>Phone<input name="phone" onChange={updateField} placeholder="Optional" value={form.phone} /></label>
            <label className="settings-full-width">Location<input name="location" onChange={updateField} placeholder="e.g. Hyderabad, India" value={form.location} /></label>
          </div>

          <div className="settings-actions">
            <span aria-live="polite">{saved ? 'Changes saved locally.' : ''}</span>
            <button className="primary-action" type="submit"><Save size={16} /> Save changes</button>
          </div>
        </form>

        <aside className="settings-side-panel">
          <div className="settings-card">
            <div className="settings-card-heading">
              <p className="section-kicker">ALERTS</p>
              <h3>Notifications</h3>
            </div>
            <div className="settings-toggle-row">
              <div>
                <strong><Bell size={16} /> Data arrival sound</strong>
                <span>Play a 1-second tone when new data arrives.</span>
              </div>
              <button
                aria-label="Toggle new data sound"
                className={`settings-toggle ${notificationSoundEnabled ? 'is-on' : ''}`}
                onClick={() => setNotificationSoundEnabled((current) => !current)}
                type="button"
              >
                <span />
              </button>
            </div>
          </div>

          <div className="settings-card">
            <div className="settings-card-heading">
              <p className="section-kicker">SECURITY</p>
              <h3>Workspace access</h3>
            </div>
            <div className="settings-checklist">
              <span><ShieldCheck size={15} /> Multi-factor checks enabled</span>
              <span><ShieldCheck size={15} /> Export controls enabled</span>
              <span><ShieldCheck size={15} /> Audit trail active</span>
            </div>
          </div>
        </aside>
      </div>
    </div>
  )
}