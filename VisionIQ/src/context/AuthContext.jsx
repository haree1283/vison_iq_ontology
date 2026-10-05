import { createContext, useContext, useEffect, useState } from 'react'
import { currentUserRequest, loginRequest, logoutRequest, signupRequest } from '../services/authApi'

const AuthContext = createContext(null)
const tokenKey = 'vision-iq-auth-token'
const userKey = 'vision-iq-auth-user'

function readStoredUser() {
  try {
    return JSON.parse(localStorage.getItem(userKey) || 'null')
  } catch {
    return null
  }
}

export function AuthProvider({ children }) {
  const [token, setToken] = useState(() => localStorage.getItem(tokenKey))
  const [user, setUser] = useState(readStoredUser)
  const [loading, setLoading] = useState(Boolean(token))

  useEffect(() => {
    if (!token) {
      setLoading(false)
      return undefined
    }

    let active = true
    currentUserRequest(token)
      .then(({ user: currentUser }) => {
        if (!active) return
        setUser(currentUser)
        localStorage.setItem(userKey, JSON.stringify(currentUser))
      })
      .catch(() => {
        if (!active) return
        localStorage.removeItem(tokenKey)
        localStorage.removeItem(userKey)
        setToken(null)
        setUser(null)
      })
      .finally(() => active && setLoading(false))

    return () => { active = false }
  }, [token])

  function startSession(result) {
    localStorage.setItem(tokenKey, result.token)
    localStorage.setItem(userKey, JSON.stringify(result.user))
    setToken(result.token)
    setUser(result.user)
    return result.user
  }

  async function login(identifier, password) {
    return startSession(await loginRequest(identifier, password))
  }

  async function signup(username, email, password) {
    return startSession(await signupRequest(username, email, password))
  }

  function updateProfile(profile) {
    setUser((currentUser) => {
      const updatedUser = { ...currentUser, ...profile }
      localStorage.setItem(userKey, JSON.stringify(updatedUser))
      return updatedUser
    })
  }

  function logout() {
    logoutRequest()
    localStorage.removeItem(tokenKey)
    localStorage.removeItem(userKey)
    setToken(null)
    setUser(null)
  }

  return (
    <AuthContext.Provider value={{ user, token, login, signup, logout, updateProfile, isAuthenticated: Boolean(token && user), loading }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) throw new Error('useAuth must be used inside AuthProvider')
  return context
}
