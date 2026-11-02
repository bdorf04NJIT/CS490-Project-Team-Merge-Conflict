import { useState } from 'react'
import CreateTargetForm from '../components/CreateTargetForm'
import TargetList from '../components/TargetList'

type HomeProps = {
  email: string | undefined
  accessToken: string
  busy: boolean
  onLogout: () => void
}

export default function Home({ email, accessToken, busy, onLogout }: HomeProps) {
  const [refreshKey, setRefreshKey] = useState(0)
  return (
    <section aria-labelledby="home-heading">
      <h2 id="home-heading" className="text-xl font-medium">
        Welcome to ReviewLens AI
      </h2>
      <p className="mt-3 break-words text-slate-600">Signed in as {email}</p>
      <button
        className="mt-4 rounded border border-slate-400 px-4 py-2 hover:bg-slate-100"
        onClick={onLogout}
        disabled={busy}
      >
        Log out
      </button>
      <TargetList accessToken={accessToken} refreshKey={refreshKey} />
      <CreateTargetForm accessToken={accessToken} onCreated={() => setRefreshKey((n) => n + 1)} />
    </section>
  )
}
