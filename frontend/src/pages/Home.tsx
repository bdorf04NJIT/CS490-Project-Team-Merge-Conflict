type HomeProps = {
  email: string | undefined
  busy: boolean
  onLogout: () => void
}

export default function Home({ email, busy, onLogout }: HomeProps) {
  return (
    <section aria-labelledby="home-heading">
      <h2 id="home-heading" className="text-xl font-medium">Welcome to ReviewLens AI</h2>
      <p className="mt-3 break-words text-slate-600">Signed in as {email}</p>
      <button className="mt-4 rounded border border-slate-400 px-4 py-2 hover:bg-slate-100" onClick={onLogout} disabled={busy}>Log out</button>
    </section>
  )
}
