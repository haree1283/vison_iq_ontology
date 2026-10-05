import { Navigate, Outlet, useLocation } from 'react-router-dom'
import { useAuth } from '../../context/AuthContext'

export default function ProtectedRoute({ children }) {
  const { isAuthenticated, loading } = useAuth()
  const location = useLocation()

  if (loading) return <div className="auth-loading">Checking your session...</div>
  if (!isAuthenticated) return <Navigate replace state={{ from: location }} to="/login" />
  return children || <Outlet />
}
