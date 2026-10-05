const API_URL = (import.meta.env.VITE_API_URL || window.location.origin).replace(/\/$/, '')

async function request(path, options = {}) {
  let response
  try {
    response = await fetch(`${API_URL}${path}`, {
      headers: { 'Content-Type': 'application/json', ...options.headers },
      ...options,
    })
  } catch {
    throw new Error('Unable to connect to server. Please try again.')
  }

  const payload = await response.json().catch(() => ({}))
  if (!response.ok) {
    const error = new Error(payload.message || 'Authentication request failed.')
    error.status = response.status
    throw error
  }
  return payload
}

export function loginRequest(identifier, password) {
  return request('/api/auth/login', {
    method: 'POST',
    body: JSON.stringify({ identifier, password }),
  })
}

export function signupRequest(username, email, password) {
  return request('/api/auth/signup', {
    method: 'POST',
    body: JSON.stringify({ username, email, password }),
  })
}

export function currentUserRequest(token) {
  return request('/api/auth/me', { headers: { Authorization: `Bearer ${token}` } })
}

export function logoutRequest() {
  // clears the HttpOnly session cookie (the browser can't remove it itself)
  return request('/api/auth/logout', { method: 'POST' }).catch(() => {})
}
