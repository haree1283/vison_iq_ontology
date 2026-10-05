import { ArrowUpRight, Eye, EyeOff, LockKeyhole, Mail, Radar, Sparkles } from 'lucide-react'
import { useState } from 'react'
import { Link, Navigate, useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '../../context/AuthContext'

export default function LoginPage() {
  const { isAuthenticated, login } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const [identifier, setIdentifier] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)

  if (isAuthenticated) return <Navigate replace to={location.state?.from?.pathname || '/home'} />

  async function handleSubmit(event) {
    event.preventDefault()
    if (!identifier.trim() || !password) {
      setError('Enter your email or username and password.')
      return
    }

    setError('')
    setSubmitting(true)
    try {
      await login(identifier, password)
      navigate(location.state?.from?.pathname || '/home', { replace: true })
    } catch (loginError) {
      setError(loginError.message || 'Unable to sign in. Please try again.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <main className="login-page">
      <div className="login-atmosphere" />
      <section className="login-panel" aria-labelledby="login-title">
        <div className="login-brand">
          <span className="login-brand-mark"><Sparkles size={20} /></span>
          <span>VISION IQ</span>
        </div>
        <div className="login-heading">
          <span className="login-kicker"><span className="login-kicker-dot" /> Intelligence workspace</span>
          <h1 id="login-title">Welcome back.</h1>
          <p>Sign in to continue to your VisionIQ workspace.</p>
        </div>
        <form className="login-form" onSubmit={handleSubmit}>
          <label htmlFor="identifier">Email or username</label>
          <div className="login-input-wrap">
            <Mail size={17} />
            <input autoComplete="username" id="identifier" onChange={(event) => setIdentifier(event.target.value)} placeholder="you@example.com" value={identifier} />
          </div>
          <label htmlFor="password">Password</label>
          <div className="login-input-wrap">
            <LockKeyhole size={17} />
            <input autoComplete="current-password" id="password" onChange={(event) => setPassword(event.target.value)} placeholder="Enter your password" type={showPassword ? 'text' : 'password'} value={password} />
            <button aria-label={showPassword ? 'Hide password' : 'Show password'} className="password-toggle" onClick={() => setShowPassword((value) => !value)} type="button">
              {showPassword ? <EyeOff size={17} /> : <Eye size={17} />}
            </button>
          </div>
          {error && <p aria-live="polite" className="login-error">{error}</p>}
          <button className="login-submit" disabled={submitting} type="submit">
            {submitting ? 'Signing in...' : 'Sign in'}
            {!submitting && <ArrowUpRight size={18} />}
          </button>
        </form>
        <p className="login-switch">New to VisionIQ? <Link to="/signup">Create an account</Link></p>
        <div className="login-footer"><span><LockKeyhole size={13} /> Secure workspace access</span><span>Authorized users only</span></div>
      </section>
      <aside className="login-side-note">
        <div className="login-side-topline"><span>VISION IQ / 01</span><span className="login-live-pill"><span /> LIVE SYSTEM</span></div>
        <div className="login-side-copy"><span className="login-side-label">TRAFFIC INTELLIGENCE PLATFORM</span><strong>See the road<br />with clarity.</strong>
        <p>One workspace for connected traffic intelligence, ontology, and operational decisions.</p>
        </div>
        <div className="login-side-metrics"><div><Radar size={17} /><span>Live signals</span><strong>24/7</strong></div><div><Sparkles size={17} /><span>Connected workspace</span><strong>01</strong></div></div>
      </aside>
    </main>
  )
}
