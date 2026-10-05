import { ArrowUpRight, Eye, EyeOff, LockKeyhole, Mail, Radar, Sparkles, UserRound } from 'lucide-react'
import { useState } from 'react'
import { Link, Navigate, useNavigate } from 'react-router-dom'
import { useAuth } from '../../context/AuthContext'

const usernamePattern = /^[A-Za-z0-9._-]{3,30}$/
const emailPattern = /^[^@\s]+@[^@\s]+\.[^@\s]+$/
const minPasswordLength = 8

export default function SignupPage() {
  const { isAuthenticated, signup } = useAuth()
  const navigate = useNavigate()
  const [username, setUsername] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)

  if (isAuthenticated) return <Navigate replace to="/home" />

  function validate() {
    if (!username.trim() || !email.trim() || !password) return 'Fill in username, email and password.'
    if (!usernamePattern.test(username.trim())) return 'Username must be 3-30 characters: letters, numbers, dot, dash or underscore.'
    if (!emailPattern.test(email.trim())) return 'Enter a valid email address.'
    if (password.trim().length < minPasswordLength) return `Password must be at least ${minPasswordLength} characters.`
    if (password !== confirmPassword) return 'Passwords do not match.'
    return ''
  }

  async function handleSubmit(event) {
    event.preventDefault()
    const problem = validate()
    if (problem) {
      setError(problem)
      return
    }

    setError('')
    setSubmitting(true)
    try {
      await signup(username.trim(), email.trim(), password)
      navigate('/home', { replace: true })
    } catch (signupError) {
      setError(signupError.message || 'Unable to create your account. Please try again.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <main className="login-page">
      <div className="login-atmosphere" />
      <section className="login-panel signup-panel" aria-labelledby="signup-title">
        <div className="login-brand">
          <span className="login-brand-mark"><Sparkles size={20} /></span>
          <span>VISION IQ</span>
        </div>
        <div className="login-heading">
          <span className="login-kicker"><span className="login-kicker-dot" /> Intelligence workspace</span>
          <h1 id="signup-title">Create your account.</h1>
          <p>Sign up to start using your VisionIQ workspace.</p>
        </div>
        <form className="login-form" onSubmit={handleSubmit} noValidate>
          <label htmlFor="signup-username">Username</label>
          <div className="login-input-wrap">
            <UserRound size={17} />
            <input autoComplete="username" id="signup-username" onChange={(event) => setUsername(event.target.value)} placeholder="yourname" value={username} />
          </div>
          <label htmlFor="signup-email">Email</label>
          <div className="login-input-wrap">
            <Mail size={17} />
            <input autoComplete="email" id="signup-email" onChange={(event) => setEmail(event.target.value)} placeholder="you@example.com" type="email" value={email} />
          </div>
          <label htmlFor="signup-password">Password</label>
          <div className="login-input-wrap">
            <LockKeyhole size={17} />
            <input autoComplete="new-password" id="signup-password" onChange={(event) => setPassword(event.target.value)} placeholder={`At least ${minPasswordLength} characters`} type={showPassword ? 'text' : 'password'} value={password} />
            <button aria-label={showPassword ? 'Hide password' : 'Show password'} className="password-toggle" onClick={() => setShowPassword((value) => !value)} type="button">
              {showPassword ? <EyeOff size={17} /> : <Eye size={17} />}
            </button>
          </div>
          <label htmlFor="signup-confirm">Confirm password</label>
          <div className="login-input-wrap">
            <LockKeyhole size={17} />
            <input autoComplete="new-password" id="signup-confirm" onChange={(event) => setConfirmPassword(event.target.value)} placeholder="Repeat your password" type={showPassword ? 'text' : 'password'} value={confirmPassword} />
          </div>
          {error && <p aria-live="polite" className="login-error">{error}</p>}
          <button className="login-submit" disabled={submitting} type="submit">
            {submitting ? 'Creating account...' : 'Create account'}
            {!submitting && <ArrowUpRight size={18} />}
          </button>
        </form>
        <p className="login-switch">Already have an account? <Link to="/login">Sign in</Link></p>
        <div className="login-footer"><span><LockKeyhole size={13} /> Secure workspace access</span><span>Passwords are stored hashed</span></div>
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
