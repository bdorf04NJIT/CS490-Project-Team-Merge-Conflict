import { useEffect, useState } from 'react'
import { listTargets } from '../api/targets'
import type { AnalysisTarget } from '../api/targets'

type Props = { accessToken: string; activeId: string; onSwitch: (id: string) => void }

export default function TargetSwitcher({ accessToken, activeId, onSwitch }: Props) {
  const [targets, setTargets] = useState<AnalysisTarget[] | null>(null)

  useEffect(() => {
    let cancelled = false
    listTargets(accessToken)
      .then((list) => {
        if (!cancelled) setTargets(list)
      })
      .catch(() => {
        if (!cancelled) setTargets([])
      })
    return () => {
      cancelled = true
    }
  }, [accessToken])

  if (!targets || targets.length < 2 || !targets.some((t) => t.id === activeId)) return null

  return (
    <div className="flex items-center gap-2">
      <label htmlFor="target-switcher" className="text-sm font-medium text-slate-700">
        Switch target
      </label>
      <select
        id="target-switcher"
        value={activeId}
        onChange={(event) => {
          if (event.target.value !== activeId) onSwitch(event.target.value)
        }}
        className="max-w-[16rem] rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-sm text-slate-900 focus:border-indigo-500 focus:ring-2 focus:ring-indigo-200 focus:outline-none"
      >
        {targets.map((target) => (
          <option key={target.id} value={target.id}>
            {target.name}
          </option>
        ))}
      </select>
    </div>
  )
}
