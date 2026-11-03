import { useCallback, useEffect, useState } from 'react'

// Minimal history-based routing: the current path plus a way to change it.
// The URL is only a hint about what to show; the backend decides what data is returned.
export function usePath() {
  const [path, setPath] = useState(() => window.location.pathname)

  useEffect(() => {
    const onPop = () => setPath(window.location.pathname)
    window.addEventListener('popstate', onPop)
    return () => window.removeEventListener('popstate', onPop)
  }, [])

  const navigate = useCallback((to: string) => {
    if (to !== window.location.pathname) window.history.pushState(null, '', to)
    setPath(to)
  }, [])

  return { path, navigate }
}

export function targetPath(id: string) {
  return `/targets/${encodeURIComponent(id)}`
}

export function targetIdFromPath(path: string): string | null {
  const match = /^\/targets\/([^/]+)\/?$/.exec(path)
  if (!match) return null
  try {
    return decodeURIComponent(match[1])
  } catch {
    return null
  }
}
