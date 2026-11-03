import { useState } from 'react'
import CreateTargetForm from '../components/CreateTargetForm'
import TargetList from '../components/TargetList'
import { targetIdFromPath, targetPath, usePath } from '../hooks/usePath'
import TargetWorkspace from './TargetWorkspace'

type HomeProps = {
  email: string | undefined
  accessToken: string
  busy: boolean
  onLogout: () => void
}

export default function Home({ email, accessToken, busy, onLogout }: HomeProps) {
  const [refreshKey, setRefreshKey] = useState(0)
  const { path, navigate } = usePath()
  const targetId = targetIdFromPath(path)

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
      {targetId ? (
        <TargetWorkspace
          key={targetId}
          accessToken={accessToken}
          targetId={targetId}
          onBack={() => navigate('/')}
        />
      ) : (
        <>
          <TargetList
            accessToken={accessToken}
            refreshKey={refreshKey}
            onOpen={(id) => navigate(targetPath(id))}
          />
          <CreateTargetForm
            accessToken={accessToken}
            onCreated={() => setRefreshKey((n) => n + 1)}
            onOpen={(id) => navigate(targetPath(id))}
          />
        </>
      )}
    </section>
  )
}
