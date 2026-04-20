export default function DiscrepanciesPage() {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-3 p-6 text-center">
      <div className="rounded-full bg-zinc-100 p-3">
        <svg className="h-6 w-6 text-zinc-400" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126ZM12 15.75h.007v.008H12v-.008Z" />
        </svg>
      </div>
      <h2 className="text-sm font-medium text-zinc-700">Discrepancies — Phase 6 / 11</h2>
      <p className="max-w-sm text-xs text-zinc-400">
        Discrepancy review will be built in Phases 6 and 11. Overlapping monthly movement data differences and review workflows will appear here.
      </p>
    </div>
  )
}
